from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Literal, Optional

import cv2
import chess
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_CODE_DIR = REPO_ROOT / "python_code"
SRC_PATH = PYTHON_CODE_DIR / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SRC_PATH))

from webapp_backend import robot_adapter
from charm.arduino.uiController_bridge import ArduinoUIControllerLink
from charm.chess_engine import (
    Evaluation,
    classify_move_rating,
    evaluate_position,
    format_score,
    win_percentage_from_cp,
    winning_color,
)
from charm.game.game_controller import GameController, GameControllerConfig
from charm.game.game_session import GameSession, SessionResult
from charm.vision.pipeline import PipelineOptions, run_board_pipeline
from charm.vision.cv_router import (
    AttemptDecision,
    CaptureOutcome,
    CVRouter,
    RouterConfig,
)
from charm.vision.validated_capture import (
    LABELED_DATASETS_ROOT,
    save_validated_capture,
    unflip_bitmap_180,
)

from charm.vision.four_point_calibration import (
    FourPointCalibration,
    InnerWarpCalibration,
    draw_calibration_points,
    load_four_point_calibration,
    load_inner_warp_calibration,
    refine_board_with_inner_corners,
    save_four_point_calibration,
    save_inner_warp_calibration,
    warp_from_calibration,
)
try:
    from charm.vision.board_detector import (
        BoardDetectionParams,
        draw_board_detection_step,
        find_largest_quadrilateral,
    )
except ImportError:
    from dataclasses import dataclass

    from charm.vision.board_detector import (
        draw_detected_corners,
        find_largest_quadrilateral as _find_largest_quadrilateral,
    )

    @dataclass
    class BoardDetectionParams:
        canny_low: int = 50
        canny_high: int = 150
        dilation_iterations: int = 1
        min_area: float = 5000.0
        max_side_ratio: float = 1.35
        min_area_ratio: float = 0.08
        max_area_ratio: float = 0.80
        min_color_ratio: float = 0.12
        padding_ratio: float = 0.015
        hough_refine: bool = False
        hough_canny_low: int = 30
        hough_canny_high: int = 100
        hough_threshold: int = 40
        hough_min_line_ratio: float = 0.33
        hough_max_line_gap: int = 18
        hough_max_line_distance: float = 35.0
        hough_min_area_keep: float = 0.97
        hough_max_area_grow: float = 1.08
        hough_max_corner_shift_ratio: float = 0.08

    def find_largest_quadrilateral(image: np.ndarray, params: BoardDetectionParams | None = None):
        return _find_largest_quadrilateral(image)

    def draw_board_detection_step(
        image: np.ndarray,
        corners: np.ndarray,
        output_size: int = 800,
    ) -> np.ndarray:
        return draw_detected_corners(image, corners)
try:
    from charm.vision.grid_splitter import (
        detect_8x8_grid_lines,
        draw_8x8_grid,
        extract_8x8_cells,
    )
except ImportError:
    from charm.vision.grid_splitter import (
        draw_8x8_grid as _draw_8x8_grid,
        extract_8x8_cells as _extract_8x8_cells,
    )

    def detect_8x8_grid_lines(board_image: np.ndarray):
        height, width = board_image.shape[:2]
        x_lines = [round(i * width / 8) for i in range(9)]
        y_lines = [round(i * height / 8) for i in range(9)]
        return x_lines, y_lines

    def draw_8x8_grid(
        board_image: np.ndarray,
        x_lines: list[int] | None = None,
        y_lines: list[int] | None = None,
    ) -> np.ndarray:
        return _draw_8x8_grid(board_image)

    def extract_8x8_cells(
        board_image: np.ndarray,
        x_lines: list[int] | None = None,
        y_lines: list[int] | None = None,
    ):
        return _extract_8x8_cells(board_image)
from charm.vision.occupancy_detector import (
    detect_occupancy,
    OccupancyResult,
    draw_occupancy_debug,
    occupancy_to_matrix,
)
from charm.vision.piece_color_detector import (
    draw_piece_color_debug,
)

_STATE_TRACKER_PATH = SRC_PATH / "charm" / "game" / "state_tracker.py"
_STATE_TRACKER_SPEC = importlib.util.spec_from_file_location("charm_webapp_state_tracker", _STATE_TRACKER_PATH)
if _STATE_TRACKER_SPEC is None or _STATE_TRACKER_SPEC.loader is None:
    raise RuntimeError(f"Could not load state tracker from {_STATE_TRACKER_PATH}")
_STATE_TRACKER_MODULE = importlib.util.module_from_spec(_STATE_TRACKER_SPEC)
sys.modules[_STATE_TRACKER_SPEC.name] = _STATE_TRACKER_MODULE
_STATE_TRACKER_SPEC.loader.exec_module(_STATE_TRACKER_MODULE)
infer_move_from_bitmaps = _STATE_TRACKER_MODULE.infer_move_from_bitmaps

BOARD_CAL_PATH = PYTHON_CODE_DIR / "board_calibration.json"
INNER_CAL_PATH = PYTHON_CODE_DIR / "inner_warp_calibration.json"
ROBOT_CAL_PATH = PYTHON_CODE_DIR / "robot_calibration.json"
EMPTY_REF_PATH = PYTHON_CODE_DIR / "empty_board_reference.jpg"
RAW_IMAGE_PATH = REPO_ROOT / "latest_raw.jpg"
LEGACY_RAW_IMAGE_PATH = PYTHON_CODE_DIR / "latest_raw.jpg"
ANNOTATIONS_PATH = REPO_ROOT / "color_annotations.json"
CLASSIFIER_STATUS_PATH = REPO_ROOT / "models" / "classifier_last_result.json"
LATEST_CALIBRATED_PATH = PYTHON_CODE_DIR / "latest_calibrated.jpg"
CV_ROUTER_CONFIG_PATH = PYTHON_CODE_DIR / "cv_router_config.json"
CV_TUNING_PATH = PYTHON_CODE_DIR / "cv_tuning.json"

_CV_TUNING_DEFAULTS = {
    "occupancy_threshold": 4.0,
    "occupancy_delta_threshold": 12.0,
    "canny_low": 15,
    "canny_high": 50,
    "occupancy_std_weight": 0.4,
    "white_threshold": 80.0,
    "black_threshold": 80.0,
    "white_delta_threshold": 5.0,
    "black_delta_threshold": -30.0,
}


def _load_cv_tuning() -> dict:
    try:
        return {**_CV_TUNING_DEFAULTS, **json.loads(CV_TUNING_PATH.read_text())}
    except Exception:
        return dict(_CV_TUNING_DEFAULTS)


def _save_cv_tuning(updates: dict) -> dict:
    current = _load_cv_tuning()
    current.update({k: v for k, v in updates.items() if k in _CV_TUNING_DEFAULTS})
    CV_TUNING_PATH.write_text(json.dumps(current, indent=2))
    return current
DIFFICULTY_SKILL_LEVEL = {0: 5, 1: 12, 2: 20}
ROBOT_BAUD_DEFAULT = 115200
_STOCKFISH_FALLBACKS = ["/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"]


def _resolve_stockfish_path(path: str) -> str:
    import shutil
    if shutil.which(path):
        return path
    for fb in _STOCKFISH_FALLBACKS:
        if Path(fb).exists():
            return fb
    return path


def _resolve_skill_level(skill_level: Optional[int], difficulty: int) -> int:
    """Pick the Stockfish skill level (0-20).

    Explicit `skill_level` wins (clamped to 0-20); otherwise the legacy
    DIFFICULTY_SKILL_LEVEL bucket is used.
    """
    if skill_level is not None:
        return max(0, min(20, int(skill_level)))
    return DIFFICULTY_SKILL_LEVEL[difficulty]

_GAME_SESSION = GameSession()

app = FastAPI(title="ChArm Vision API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class PipelineParams(BaseModel):
    auto_detect_board: bool = False
    apply_inner_warp: bool = True
    board_canny_low: int = 50
    board_canny_high: int = 150
    board_dilation_iterations: int = 1
    board_min_area: float = 5000.0
    board_max_side_ratio: float = 1.35
    board_min_area_ratio: float = 0.08
    board_max_area_ratio: float = 0.80
    board_min_color_ratio: float = 0.12
    board_padding_ratio: float = 0.015
    board_hough_refine: bool = False
    board_hough_canny_low: int = 30
    board_hough_canny_high: int = 100
    board_hough_threshold: int = 40
    board_hough_min_line_ratio: float = 0.33
    board_hough_max_line_gap: int = 18
    board_hough_max_line_distance: float = 35.0
    board_hough_min_area_keep: float = 0.97
    board_hough_max_area_grow: float = 1.08
    board_hough_max_corner_shift_ratio: float = 0.08
    clahe_clip_limit: float = 2.5
    clahe_tile_size: int = 8
    saturation_boost: float = 1.2
    brightness_boost: float = 1.05
    sharpen_alpha: float = 1.35
    sharpen_beta: float = -0.35
    occupancy_threshold: float = 4.0
    occupancy_delta_threshold: float = 12.0
    canny_low: int = 15
    canny_high: int = 50
    occupancy_std_weight: float = 0.4
    white_threshold: float = 80
    black_threshold: float = 80
    white_delta_threshold: float = 5.0
    black_delta_threshold: float = -30.0
    warp_size: int = 800
    image_path: Optional[str] = None


class CalibrationUpdate(BaseModel):
    board: Optional[dict] = None
    inner: Optional[dict] = None


class BoardCornerCalibrationPayload(BaseModel):
    top_left: tuple[int, int]
    top_right: tuple[int, int]
    bottom_right: tuple[int, int]
    bottom_left: tuple[int, int]
    image_path: Optional[str] = None
    warp_size: int = 800


class ImagePathPayload(BaseModel):
    path: str


class PipelineSnapshotPayload(BaseModel):
    params: PipelineParams
    images: dict[str, str]
    result: Optional[dict] = None
    labels: Optional[list[list[str]]] = None
    source_image: Optional[str] = None
    name: Optional[str] = None


class AnnotationPayload(BaseModel):
    image_id: str
    scene_id: str
    board_64: list[str]
    image_path: Optional[str] = None


class Point2DPayload(BaseModel):
    x: float
    y: float


class Point3DPayload(BaseModel):
    x: float
    y: float
    z: float


class RobotCalibrationPayload(BaseModel):
    a1: Point2DPayload
    h1: Point2DPayload
    h8: Point2DPayload
    z_hover: float
    z_down: float
    home: Point3DPayload
    capture_bin: Point3DPayload
    pick_z: dict[str, float] = Field(default_factory=dict)
    place_z: dict[str, float] = Field(default_factory=dict)


class RobotCommandPayload(BaseModel):
    command: str
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT
    square: Optional[str] = None
    uci: Optional[str] = None
    raw: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    corner: Optional[str] = None
    piece_type: Optional[str] = None
    captured_piece_type: Optional[str] = None
    down: bool = False
    capture: bool = False
    castling: bool = False
    promotion: bool = False


class GameStepPayload(BaseModel):
    moves: list[str] = Field(default_factory=list)
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = False
    max_mismatches: int = 0


class GameSessionPayload(BaseModel):
    player_color: str = "white"
    difficulty: int = 1
    skill_level: Optional[int] = None
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = True
    max_mismatches: int = 0
    engine_path: str = "stockfish"
    think_time: float = 0.5
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT
    execute_robot: bool = True


class GameSessionTurnPayload(BaseModel):
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = True
    max_mismatches: int = 0
    difficulty: int = 1
    skill_level: Optional[int] = None
    engine_path: str = "stockfish"
    think_time: float = 0.5
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT
    execute_robot: bool = True


class CameraCapturePayload(BaseModel):
    url: Optional[str] = None
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT


class EmptyReferencePayload(BaseModel):
    params: PipelineParams = Field(default_factory=PipelineParams)
    image_path: Optional[str] = None
    capture: bool = True


def _normalize_camera_url(url: Optional[str]) -> Optional[str]:
    if url is None:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"http://{cleaned}"
    if "/" not in cleaned.removeprefix("http://").removeprefix("https://"):
        cleaned = f"{cleaned.rstrip('/')}/capture"
    return cleaned


def _board_from_uci_moves(moves: list[str]) -> chess.Board:
    board = chess.Board()
    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move for current board state: {uci}")
        board.push(move)
    return board


def _safe_snapshot_name(name: Optional[str]) -> str:
    if name:
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name.strip())
        cleaned = cleaned.strip("_")
        if cleaned:
            return cleaned[:80]
    return time.strftime("%Y%m%d_%H%M%S")


def _write_b64_image(path: Path, data: str) -> None:
    if "," in data:
        data = data.split(",", 1)[1]
    path.write_bytes(base64.b64decode(data))


def to_b64(img: np.ndarray, quality: int = 85) -> str:
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode()


def preprocess(img: np.ndarray, p: PipelineParams) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(
        clipLimit=p.clahe_clip_limit,
        tileGridSize=(p.clahe_tile_size, p.clahe_tile_size),
    )
    enhanced = cv2.merge([clahe.apply(l), a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
    sharpened = cv2.addWeighted(enhanced, p.sharpen_alpha, blurred, p.sharpen_beta, 0)
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    hsv = cv2.cvtColor(sharpened, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * p.saturation_boost, 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * p.brightness_boost, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def resolve_latest_raw_path() -> Path:
    for path in (RAW_IMAGE_PATH, LEGACY_RAW_IMAGE_PATH):
        if path.exists():
            return path
    return RAW_IMAGE_PATH


def _calibration_from_quad(corners: np.ndarray) -> FourPointCalibration:
    ordered = corners.astype(int)
    return FourPointCalibration(
        top_left=tuple(map(int, ordered[0])),
        top_right=tuple(map(int, ordered[1])),
        bottom_right=tuple(map(int, ordered[2])),
        bottom_left=tuple(map(int, ordered[3])),
    )


def _board_detection_params(p: PipelineParams) -> BoardDetectionParams:
    return BoardDetectionParams(
        canny_low=p.board_canny_low,
        canny_high=p.board_canny_high,
        dilation_iterations=p.board_dilation_iterations,
        min_area=p.board_min_area,
        max_side_ratio=p.board_max_side_ratio,
        min_area_ratio=p.board_min_area_ratio,
        max_area_ratio=p.board_max_area_ratio,
        min_color_ratio=p.board_min_color_ratio,
        padding_ratio=p.board_padding_ratio,
        hough_refine=p.board_hough_refine,
        hough_canny_low=p.board_hough_canny_low,
        hough_canny_high=p.board_hough_canny_high,
        hough_threshold=p.board_hough_threshold,
        hough_min_line_ratio=p.board_hough_min_line_ratio,
        hough_max_line_gap=p.board_hough_max_line_gap,
        hough_max_line_distance=p.board_hough_max_line_distance,
        hough_min_area_keep=p.board_hough_min_area_keep,
        hough_max_area_grow=p.board_hough_max_area_grow,
        hough_max_corner_shift_ratio=p.board_hough_max_corner_shift_ratio,
    )


def _resolve_board_calibration(
    image: np.ndarray,
    p: PipelineParams,
) -> tuple[FourPointCalibration, str, np.ndarray]:
    if p.auto_detect_board:
        auto_quad = find_largest_quadrilateral(image, _board_detection_params(p))
        if auto_quad is not None:
            return (
                _calibration_from_quad(auto_quad),
                "auto",
                draw_board_detection_step(image, auto_quad, output_size=p.warp_size),
            )

    board_cal = load_four_point_calibration(str(BOARD_CAL_PATH))
    return board_cal, "saved", draw_calibration_points(image, board_cal)



def _classify_with_exemplars(occupancy_cells, config):
    """Run the per-square exemplar classifier on the current cells and produce
    OccupancyResult + PieceColorResult lists that match the existing pipeline
    contract so the same debug-image drawers work unchanged.
    """
    from charm.vision.exemplar_classifier import classify_cell
    from charm.vision.occupancy_detector import OccupancyResult
    from charm.vision.piece_color_detector import PieceColorResult

    occupancy_results: list[OccupancyResult] = []
    color_results: list[PieceColorResult] = []
    for cell in occupancy_cells:
        res = classify_cell(cell.image, cell.row, cell.col, config)
        occupied = res.label != "empty"
        # The "score" field is what the threshold-path debug renders; piggy-back
        # the confidence margin so the existing debug view still has a useful
        # per-cell number. delta is unused on this path.
        occupancy_results.append(
            OccupancyResult(
                row=cell.row,
                col=cell.col,
                occupied=occupied,
                score=float(res.confidence_margin),
            )
        )
        if not occupied:
            color_results.append(
                PieceColorResult(
                    row=cell.row, col=cell.col,
                    occupied=False, color="unknown",
                    brightness_score=0.0,
                )
            )
        else:
            color = res.label  # "white" or "black"
            color_results.append(
                PieceColorResult(
                    row=cell.row, col=cell.col,
                    occupied=True, color=color,  # type: ignore[arg-type]
                    brightness_score=float(res.confidence_margin),
                )
            )
    return occupancy_results, color_results


def _warped_board_for_tuning(params: PipelineParams, image_path: Optional[str]) -> np.ndarray:
    path = Path(image_path) if image_path else resolve_latest_raw_path()
    if not path.exists():
        raise HTTPException(404, f"Image not found: {path}")
    image = cv2.imread(str(path))
    if image is None:
        raise HTTPException(400, f"Failed to decode image: {path}")

    try:
        board_cal, _, _ = _resolve_board_calibration(image, params)
        warped = warp_from_calibration(image, board_cal, params.warp_size)
        if params.apply_inner_warp:
            inner_cal = load_inner_warp_calibration(str(INNER_CAL_PATH))
            warped = refine_board_with_inner_corners(warped, inner_cal, params.warp_size)
        return warped
    except Exception as e:
        raise HTTPException(500, f"Failed to warp board: {e}")


def run_pipeline(image: np.ndarray, p: PipelineParams) -> dict:
    results: dict = {}
    timings: dict = {}

    results["original"] = to_b64(image)

    t = time.perf_counter()
    warped = image
    warp_error = None
    board_detection_mode = "none"
    try:
        board_cal, board_detection_mode, board_edges_debug = _resolve_board_calibration(image, p)
        results["board_edges_debug"] = to_b64(board_edges_debug)
        warped = warp_from_calibration(image, board_cal, p.warp_size)
        results["first_warp"] = to_b64(warped)
        if p.apply_inner_warp:
            inner_cal = load_inner_warp_calibration(str(INNER_CAL_PATH))
            warped = refine_board_with_inner_corners(warped, inner_cal, p.warp_size)
        results["refined_warp"] = to_b64(warped)
    except Exception as e:
        warp_error = str(e)
        warped = cv2.resize(image, (p.warp_size, p.warp_size))
        results["board_edges_debug"] = to_b64(image)
        results["first_warp"] = to_b64(warped)
        results["refined_warp"] = to_b64(warped)
    results["board_detection_mode"] = board_detection_mode
    timings["warp_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    preprocessed = warped.copy()
    results["preprocessed"] = to_b64(preprocessed)
    timings["preprocess_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    x_lines, y_lines = detect_8x8_grid_lines(warped)
    results["grid_debug"] = to_b64(draw_8x8_grid(warped.copy(), x_lines, y_lines))
    timings["grid_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    occupancy_cells = extract_8x8_cells(warped, x_lines, y_lines)
    color_cells = occupancy_cells

    reference_cells = None
    if EMPTY_REF_PATH.exists():
        ref_img = cv2.imread(str(EMPTY_REF_PATH))
        if ref_img is not None:
            if ref_img.shape[:2] != warped.shape[:2]:
                ref_img = cv2.resize(ref_img, (warped.shape[1], warped.shape[0]))
            ref_x, ref_y = detect_8x8_grid_lines(ref_img)
            reference_cells = extract_8x8_cells(ref_img, ref_x, ref_y)

    active_name, active_cfg = _get_active_exemplar_config()
    if active_cfg is not None:
        occupancy_results, color_results = _classify_with_exemplars(
            occupancy_cells, active_cfg
        )
        results["classifier"] = {"active": True, "name": active_name, "kind": "exemplar"}
    else:
        occupancy_results = detect_occupancy(
            occupancy_cells,
            threshold=p.occupancy_threshold,
        )
        color_results = None  # filled in below via threshold path
        results["classifier"] = {"active": False, "name": None, "kind": "threshold"}
    results["empty_reference_active"] = reference_cells is not None
    results["occupancy_debug"] = to_b64(
        draw_occupancy_debug(warped.copy(), occupancy_cells, occupancy_results)
    )
    results["occupancy_matrix"] = occupancy_to_matrix(occupancy_results)
    scores_grid = [[0.0] * 8 for _ in range(8)]
    for r in occupancy_results:
        scores_grid[r.row][r.col] = round(r.score, 3)
    results["occupancy_scores"] = scores_grid
    timings["occupancy_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    white_bitmap = [[0] * 8 for _ in range(8)]
    black_bitmap = [[0] * 8 for _ in range(8)]
    brightness_grid = [[0.0] * 8 for _ in range(8)]
    color_labels = [["empty"] * 8 for _ in range(8)]

    from charm.vision.piece_color_detector import detect_piece_colors

    if color_results is None:
        color_results = detect_piece_colors(
            color_cells,
            occupancy_results,
            white_threshold=p.white_threshold,
            black_threshold=p.black_threshold,
        )

    for r in color_results:
        brightness_grid[r.row][r.col] = round(r.brightness_score, 1)
        if r.occupied:
            color_labels[r.row][r.col] = r.color
            if r.color == "white":
                white_bitmap[r.row][r.col] = 1
            elif r.color == "black":
                black_bitmap[r.row][r.col] = 1

    results["piece_color_debug"] = to_b64(
        draw_piece_color_debug(warped.copy(), color_cells, color_results)
    )
    timings["piece_color_ms"] = round((time.perf_counter() - t) * 1000, 1)

    results["white_bitmap"] = white_bitmap
    results["black_bitmap"] = black_bitmap
    results["brightness_scores"] = brightness_grid
    results["color_labels"] = color_labels
    results["timings"] = timings
    results["total_ms"] = sum(timings.values())
    results["stats"] = {
        "occupied": sum(r.occupied for r in occupancy_results),
        "white_pieces": sum(white_bitmap[r][c] for r in range(8) for c in range(8)),
        "black_pieces": sum(black_bitmap[r][c] for r in range(8) for c in range(8)),
        "unknown_pieces": sum(1 for row in color_labels for label in row if label == "unknown"),
    }
    results["stats"]["unknown_pieces"] = (
        results["stats"]["occupied"]
        - results["stats"]["white_pieces"]
        - results["stats"]["black_pieces"]
    )
    if warp_error:
        results["warp_error"] = warp_error

    return results


def _capture_or_resolve_image(params: PipelineParams, capture: bool) -> Path:
    if capture:
        try:
            from charm.vision.transferphoto import fetch_raw_image

            return Path(fetch_raw_image())
        except Exception as e:
            raise HTTPException(500, f"Capture failed: {e}")
    return Path(params.image_path) if params.image_path else resolve_latest_raw_path()


def _flip_bitmap_180(bitmap: list[list[int]]) -> list[list[int]]:
    """Flip a bitmap 180 degrees (rotate board 180°)."""
    return [[bitmap[7 - r][7 - c] for c in range(8)] for r in range(8)]


def _run_pipeline_and_write_calibrated(params: PipelineParams, capture: bool) -> tuple[Path, dict, Path]:
    path = _capture_or_resolve_image(params, capture)
    if not path.exists():
        raise HTTPException(404, f"Image not found: {path}")

    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(400, f"Failed to decode image: {path}")

    pipeline_result = run_pipeline(img, params)
    pipeline_result["image_path"] = str(path)
    pipeline_result["timestamp"] = time.time()

    try:
        _write_b64_image(LATEST_CALIBRATED_PATH, pipeline_result["refined_warp"])
    except Exception as e:
        raise HTTPException(500, f"Failed to write calibrated board image: {e}")

    return path, pipeline_result, LATEST_CALIBRATED_PATH


def _session_result_payload(result: Optional[SessionResult], board_before: Optional[chess.Board] = None) -> Optional[dict]:
    if result is None:
        return None

    san = None
    if result.move_uci and board_before is not None:
        try:
            move = chess.Move.from_uci(result.move_uci)
            san = board_before.san(move) if move in board_before.legal_moves else None
        except Exception:
            san = None

    return {
        "success": result.success,
        "message": result.message,
        "move_uci": result.move_uci,
        "san": san,
        "mismatch_count": result.mismatch_count,
        "error_code": result.error_code,
    }


def _game_session_payload(
    status: str,
    pipeline_result: Optional[dict] = None,
    started: Optional[SessionResult] = None,
    human_move: Optional[SessionResult] = None,
    human_board_before: Optional[chess.Board] = None,
    robot_move: Optional[SessionResult] = None,
    robot_board_before: Optional[chess.Board] = None,
    robot_command: Optional[dict] = None,
    player_command: Optional[dict] = None,
    evaluation: Optional[dict] = None,
) -> dict:
    board = _GAME_SESSION.get_current_board()
    return {
        "status": status,
        "player_color": _GAME_SESSION.get_player_color(),
        "robot_color": _GAME_SESSION.get_robot_color(),
        "fen": board.fen() if board is not None else None,
        "moves": _GAME_SESSION.get_move_history(),
        "pipeline": pipeline_result,
        "started": _session_result_payload(started),
        "human_move": _session_result_payload(human_move, human_board_before),
        "robot_move": _session_result_payload(robot_move, robot_board_before),
        "robot_command": robot_command,
        "player_command": player_command,
        "evaluation": evaluation,
        "timestamp": time.time(),
    }


def _robot_move_request(move_uci: str, board: chess.Board) -> dict:
    move = chess.Move.from_uci(move_uci)
    piece = board.piece_at(move.from_square)
    captured_piece = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        captured_square = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        captured_piece = board.piece_at(captured_square)
    return {
        "command": "move",
        "uci": move_uci,
        "capture": board.is_capture(move),
        "castling": board.is_castling(move),
        "promotion": bool(move.promotion),
        "piece_type": chess.piece_name(piece.piece_type).lower() if piece else "pawn",
        "captured_piece_type": chess.piece_name(captured_piece.piece_type).lower() if captured_piece else None,
    }


def _execute_robot_session_move(move_uci: str, board: chess.Board, port: Optional[str], baud: int) -> dict:
    payload = _robot_move_request(move_uci, board)
    commands = robot_adapter.commands_for_request(payload)
    responses = robot_adapter.send_commands(commands, port, baud)
    return robot_adapter.response(responses, ROBOT_CAL_PATH)


# ---------------------------------------------------------------------------
# Stockfish evaluation glue
# ---------------------------------------------------------------------------


_RATING_LCD_LABEL = {
    "Blunder": "BLUNDER!",
    "Mistake": "MISTAKE!",
    "Inaccuracy": "INACCURACY",
    "Good": "GOOD",
    "Excellent": "EXCELLENT!",
}


def _evaluation_payload(evaluation: Evaluation) -> dict:
    """Shape an Evaluation for the dashboard's Game Evaluation panel."""
    return {
        "score": format_score(evaluation.score_cp, evaluation.mate),
        "score_cp": evaluation.score_cp,
        "mate": evaluation.mate,
        "winning_color": winning_color(evaluation.score_cp, evaluation.mate),
        "win_percentage": round(win_percentage_from_cp(evaluation.score_cp, evaluation.mate), 1),
        "best_move_uci": evaluation.best_move_uci,
        "best_move_suggestion": evaluation.best_move_san,
    }


def _classify_player_move(
    eval_before: Evaluation,
    eval_after: Evaluation,
    player_turn_white: bool,
) -> dict:
    """Translate before/after Stockfish evals into the player rating block."""
    # Convert White-POV scores to the moving player's POV so a "loss" is
    # always a drop in the moving side's eval.
    sign = 1 if player_turn_white else -1
    cp_before = (eval_before.score_cp or 0) * sign
    cp_after = (eval_after.score_cp or 0) * sign

    mate_before = eval_before.mate
    mate_after = eval_after.mate
    if not player_turn_white:
        mate_before = -mate_before if mate_before is not None else None
        mate_after = -mate_after if mate_after is not None else None

    rating, cp_loss = classify_move_rating(cp_before, cp_after, mate_before, mate_after)
    return {
        "rating": rating,
        "cp_loss": cp_loss,
        "best_move_suggestion": eval_before.best_move_san,
        "best_move_uci": eval_before.best_move_uci,
    }


def _flash_lcd_rating(rating: str) -> None:
    """Best-effort flash of the move-quality term on the LCD."""
    ui_link: Optional[ArduinoUIControllerLink] = _CONTROLLER_STATE.get("ui_link")
    if ui_link is None:
        return
    label = _RATING_LCD_LABEL.get(rating)
    if label is None:
        return
    try:
        ui_link.error_msg(label)
    except Exception as exc:
        print(f"[lcd] flash failed: {exc!r}", flush=True)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


def _robot_calibration_response() -> dict:
    exists = ROBOT_CAL_PATH.exists()
    calibration = robot_adapter.load_calibration(ROBOT_CAL_PATH)
    samples = {square: robot_adapter.square_center(calibration, square) for square in ("a1", "b1", "a2", "e4", "h8")}
    return {
        "exists": exists,
        "path": str(ROBOT_CAL_PATH),
        "calibration": calibration,
        "samples": samples,
    }


@app.get("/api/robot/status")
def robot_status():
    active_port = robot_adapter.connected_port()

    return {
        "serial_connected": active_port is not None,
        "active_port": active_port,
        "detected_port": robot_adapter.find_port(),
        "ports": robot_adapter.list_ports(),
        "robot_calibration": _robot_calibration_response(),
    }


@app.put("/api/robot/calibration")
def update_robot_calibration(payload: RobotCalibrationPayload):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    robot_adapter.save_calibration(ROBOT_CAL_PATH, payload_data)
    return {"status": "saved", **_robot_calibration_response()}


@app.post("/api/robot/disconnect")
def disconnect_robot():
    robot_adapter.close()
    return {"status": "disconnected"}


@app.get("/api/robot/position")
def robot_position(port: Optional[str] = None, baud: int = ROBOT_BAUD_DEFAULT):
    try:
        responses = robot_adapter.send_commands(["pos"], port, baud)
        return robot_adapter.response(responses, ROBOT_CAL_PATH)
    except Exception as e:
        robot_adapter.close()
        raise HTTPException(500, str(e))


@app.post("/api/robot/command")
def robot_command(payload: RobotCommandPayload):
    try:
        payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        commands = robot_adapter.commands_for_request(payload_data)
        max_wait = 180.0 if payload.command == "arm-calibrate" else 8.0
        idle_timeout = 30.0 if payload.command == "arm-calibrate" else 0.25
        print(
            f"[robot] command={payload.command} port={payload.port or 'auto'} "
            f"baud={payload.baud} commands={commands}",
            flush=True,
        )
        stop_on = "Calibration done" if payload.command == "arm-calibrate" else None
        responses = robot_adapter.send_commands(
            commands,
            payload.port,
            payload.baud,
            max_wait=max_wait,
            idle_timeout=idle_timeout,
            stop_on=stop_on,
        )
        print(f"[robot] responses={responses}", flush=True)
        if payload.command == "arm-calibrate" and not any("Calibration done" in line for line in responses):
            raise HTTPException(
                502,
                "Arduino did not report calibration progress. "
                "Expected firmware to print 'Gripper openned for calibration' and 'Calibration done'. "
                f"Responses: {responses}",
            )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        robot_adapter.close()
        raise HTTPException(500, str(e))

    if payload.command == "arm-calibrate" and _controller_is_running():
        try:
            ui_link: Optional[ArduinoUIControllerLink] = _CONTROLLER_STATE.get("ui_link")
            if ui_link is not None:
                ui_link.set_mode(1)
        except Exception as exc:
            print(f"[lcd] SET_MODE 1 after calibration failed: {exc!r}", flush=True)

    return robot_adapter.response(responses, ROBOT_CAL_PATH)


@app.post("/api/robot/inject-cal")
def inject_board_cal(payload: RobotCommandPayload):
    try:
        payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        payload_data["command"] = "inject-cal"
        commands = robot_adapter.commands_for_request(payload_data)
        responses = robot_adapter.send_commands(commands, payload.port, payload.baud)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        robot_adapter.close()
        raise HTTPException(500, str(e))
    return robot_adapter.response(responses, ROBOT_CAL_PATH)


@app.get("/api/robot/eeprom")
def robot_eeprom(port: Optional[str] = None, baud: int = ROBOT_BAUD_DEFAULT):
    try:
        responses = robot_adapter.send_commands(["boardInfo"], port, baud)
        return robot_adapter.response(responses, ROBOT_CAL_PATH)
    except Exception as e:
        robot_adapter.close()
        raise HTTPException(500, str(e))


@app.post("/api/pipeline/run")
def pipeline_run(params: PipelineParams):
    path = Path(params.image_path) if params.image_path else resolve_latest_raw_path()
    if not os.path.exists(path):
        raise HTTPException(404, f"Image not found: {path}")
    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(400, "Failed to decode image")
    result = run_pipeline(img, params)
    result["image_path"] = str(path)
    result["timestamp"] = time.time()
    return result


@app.post("/api/empty-reference/capture")
def capture_empty_reference(payload: Optional[EmptyReferencePayload] = None):
    payload = payload or EmptyReferencePayload()
    params = payload.params

    if payload.capture:
        source_path = str(_capture_or_resolve_image(params, capture=True))
    else:
        source_path = payload.image_path

    warped = _warped_board_for_tuning(params, source_path)
    if not cv2.imwrite(str(EMPTY_REF_PATH), warped):
        raise HTTPException(500, "Failed to write empty reference image")
    return {
        "status": "saved",
        "path": str(EMPTY_REF_PATH),
        "source_image": source_path,
        "image": to_b64(warped),
        "saved_at": time.time(),
    }


@app.get("/api/empty-reference")
def get_empty_reference():
    if not EMPTY_REF_PATH.exists():
        return {"exists": False, "image": None, "saved_at": None}
    img = cv2.imread(str(EMPTY_REF_PATH))
    if img is None:
        return {"exists": False, "image": None, "saved_at": None}
    return {
        "exists": True,
        "image": to_b64(img),
        "path": str(EMPTY_REF_PATH),
        "saved_at": EMPTY_REF_PATH.stat().st_mtime,
    }


@app.delete("/api/empty-reference")
def clear_empty_reference():
    if EMPTY_REF_PATH.exists():
        EMPTY_REF_PATH.unlink()
    return {"status": "cleared"}


@app.post("/api/pipeline/upload")
async def pipeline_upload(file: UploadFile = File(...), params_json: str = "{}"):
    contents = await file.read()
    arr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Invalid image file")
    params = PipelineParams(**json.loads(params_json))
    result = run_pipeline(img, params)
    result["timestamp"] = time.time()
    return result


@app.post("/api/pipeline/snapshot")
def save_pipeline_snapshot(payload: PipelineSnapshotPayload):
    snapshot_dir = PYTHON_CODE_DIR / "webapp_snapshots" / _safe_snapshot_name(payload.name)
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        image_paths: dict[str, str] = {}
        for key, value in payload.images.items():
            if not value:
                continue
            image_path = snapshot_dir / f"{key}.jpg"
            _write_b64_image(image_path, value)
            image_paths[key] = str(image_path)

        summary = {
            "saved_at": time.time(),
            "snapshot_dir": str(snapshot_dir),
            "source_image": payload.source_image,
            "params": payload.params.model_dump(),
            "labels": payload.labels,
            "result": payload.result or {},
            "images": image_paths,
            "python_inputs": {
                "refined_warp": image_paths.get("refined_warp"),
                "raw": image_paths.get("original"),
            },
        }
        summary_path = snapshot_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Failed to save pipeline snapshot: {e}")

    return {
        "status": "saved",
        "path": str(snapshot_dir),
        "summary_path": str(summary_path),
        "refined_warp_path": image_paths.get("refined_warp"),
    }


@app.post("/api/game/step")
def game_step(payload: GameStepPayload):
    try:
        board_before = _board_from_uci_moves(payload.moves)
    except Exception as e:
        raise HTTPException(400, str(e))

    path: Path
    if payload.capture:
        try:
            from charm.vision.transferphoto import fetch_raw_image

            path = Path(fetch_raw_image())
        except Exception as e:
            raise HTTPException(500, f"Capture failed: {e}")
    else:
        path = Path(payload.params.image_path) if payload.params.image_path else resolve_latest_raw_path()

    if not path.exists():
        raise HTTPException(404, f"Image not found: {path}")

    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(400, f"Failed to decode image: {path}")

    pipeline_result = run_pipeline(img, payload.params)
    inference = infer_move_from_bitmaps(
        board_before,
        pipeline_result["white_bitmap"],
        pipeline_result["black_bitmap"],
    )

    accepted = (
        inference.move is not None
        and inference.status == "accepted_legal_move"
        and inference.mismatch_count <= payload.max_mismatches
        and inference.matching_move_count <= 1
    )

    board_after = board_before.copy(stack=True)
    move_uci = inference.move.uci() if inference.move is not None else None
    if accepted and inference.move is not None:
        board_after.push(inference.move)

    pipeline_result["image_path"] = str(path)
    pipeline_result["timestamp"] = time.time()

    return {
        "pipeline": pipeline_result,
        "inference": {
            "accepted": accepted,
            "move_uci": move_uci,
            "status": inference.status,
            "mismatch_count": inference.mismatch_count,
            "matching_move_count": inference.matching_move_count,
            "fen_before": board_before.fen(),
            "fen_after": board_after.fen(),
        },
    }


# ----------------------------------------------------------------------------
# CV router glue
# ----------------------------------------------------------------------------


def _load_router_config() -> RouterConfig:
    return RouterConfig.load(CV_ROUTER_CONFIG_PATH)


def _save_router_config(cfg: RouterConfig) -> None:
    cfg.save(CV_ROUTER_CONFIG_PATH)


def _decode_b64_to_ndarray(b64_str: str) -> Optional[np.ndarray]:
    """Decode a base64-encoded JPEG back into a BGR ndarray for cell slicing."""
    if not b64_str:
        return None
    try:
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        raw = base64.b64decode(b64_str)
        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        return arr
    except Exception:
        return None


def _make_scan_vision(payload) -> "Callable[[], CaptureOutcome]":
    """Return a callable that captures a fresh frame and runs the classical pipeline.

    Two-stage warp + ``run_board_pipeline`` (cv-vision-updates tuned thresholds),
    then a 180° flip. The camera is mounted with the human player on top of the
    image (white pieces at top, black at bottom), but ``state_tracker``
    expects row 0 = rank 8 = black. Flip aligns the two.
    """
    def _do() -> CaptureOutcome:
        if not BOARD_CAL_PATH.exists() or not INNER_CAL_PATH.exists():
            raise RuntimeError("Board calibration missing — calibrate the board first.")
        raw_path = _capture_or_resolve_image(payload.params, payload.capture)
        if not raw_path.exists():
            raise RuntimeError(f"Image not found: {raw_path}")

        raw = cv2.imread(str(raw_path))
        if raw is None:
            raise RuntimeError(f"Failed to decode {raw_path}")

        board_cal = load_four_point_calibration(BOARD_CAL_PATH)
        inner_cal = load_inner_warp_calibration(str(INNER_CAL_PATH))
        first_warp = warp_from_calibration(raw, board_cal, output_size=800)
        refined = refine_board_with_inner_corners(first_warp, inner_cal, output_size=800)
        cv2.imwrite(str(LATEST_CALIBRATED_PATH), refined)

        bp = run_board_pipeline(str(LATEST_CALIBRATED_PATH), options=PipelineOptions())
        wb = _flip_bitmap_180(bp.white_bitmap)
        bb = _flip_bitmap_180(bp.black_bitmap)

        color_labels: list[list[str]] = []
        for r in range(8):
            row: list[str] = []
            for c in range(8):
                if wb[r][c]:
                    row.append("white")
                elif bb[r][c]:
                    row.append("black")
                else:
                    row.append("empty")
            color_labels.append(row)

        payload_dict: dict = {
            "image_path": str(raw_path),
            "timestamp": time.time(),
            "refined_warp": to_b64(bp.warped_board),
            "occupancy_debug": to_b64(bp.occupancy_debug_image),
            "piece_color_debug": to_b64(bp.piece_color_debug_image),
            "grid_debug": to_b64(bp.grid_debug_image),
            "occupancy_matrix": bp.occupancy_matrix,
            "white_bitmap": wb,
            "black_bitmap": bb,
            "color_labels": color_labels,
            "cv_mode": "vision",
        }
        return CaptureOutcome(
            white_bitmap=wb,
            black_bitmap=bb,
            payload=payload_dict,
            refined_image=refined,
        )

    return _do


def _make_scan_cnn(payload) -> "Callable[[], CaptureOutcome]":
    """Return a callable that captures a fresh frame and runs the CNN classifier.

    Same 180° flip as the vision path. Camera mount: white-on-top of image.
    """
    def _do() -> CaptureOutcome:
        if not _read_active_cnn_run_id():
            raise RuntimeError("No active CNN model")
        raw_path = _capture_or_resolve_image(payload.params, payload.capture)
        wb, bb, pipeline_result = _run_cnn_game_scan(raw_path)
        wb = _flip_bitmap_180(wb)
        bb = _flip_bitmap_180(bb)
        pipeline_result["white_bitmap"] = wb
        pipeline_result["black_bitmap"] = bb
        refined_arr = _decode_b64_to_ndarray(pipeline_result.get("refined_warp", ""))
        pipeline_result["cv_mode"] = "cnn"
        return CaptureOutcome(
            white_bitmap=wb,
            black_bitmap=bb,
            payload=pipeline_result,
            refined_image=refined_arr,
        )

    return _do


def _persist_validated_capture(
    capture: CaptureOutcome,
    mode_used: str,
    move_uci: Optional[str],
    session_id: Optional[str],
) -> Optional[dict]:
    """Best-effort: save the 64 cells of a validated frame into the live dataset."""
    cfg = _load_router_config()
    if not cfg.auto_save_validated:
        return None
    if capture is None or capture.refined_image is None:
        return None
    try:
        # capture.white/black_bitmap are post-flip (chess orientation:
        # row 0 = rank 8 = top of state_tracker board). The refined image is
        # in raw image orientation (white-on-top), so un-flip the bitmaps
        # before slicing cells so each crop is labeled with what's physically
        # in that image square.
        summary = save_validated_capture(
            refined_image=capture.refined_image,
            white_bitmap_image_orient=unflip_bitmap_180(capture.white_bitmap),
            black_bitmap_image_orient=unflip_bitmap_180(capture.black_bitmap),
            move_uci=move_uci,
            mode_used=mode_used,
            session_id=session_id,
            dataset_name=cfg.dataset_name,
            datasets_root=LABELED_DATASETS_ROOT,
        )
        return {
            "saved": summary.saved,
            "dataset": cfg.dataset_name,
            "counts": summary.counts,
            "error": summary.error,
        }
    except Exception as exc:
        return {"saved": False, "dataset": cfg.dataset_name, "error": str(exc)}


def _build_router(payload) -> tuple[CVRouter, dict, RouterConfig]:
    """Build a router + per-mode capture fns based on current config and CNN availability.

    When no CNN model is active we drop CNN from the fns dict AND force the
    effective primary to "vision" so the router runs only vision attempts
    (no phantom "cnn not configured" entry in the attempts log).
    """
    cfg = _load_router_config()
    cnn_active = bool(_read_active_cnn_run_id())
    fns: dict = {"vision": _make_scan_vision(payload)}
    if cnn_active:
        fns["cnn"] = _make_scan_cnn(payload)

    effective_primary = cfg.primary if cnn_active else "vision"
    if effective_primary != cfg.primary:
        # Override for this scan only — don't persist; the user might activate a
        # CNN later and we want their saved preference to come back.
        cfg = RouterConfig(
            primary=effective_primary,
            attempts_each=cfg.attempts_each,
            auto_save_validated=cfg.auto_save_validated,
            dataset_name=cfg.dataset_name,
        )
    return CVRouter(config=cfg), fns, cfg


def _router_attempts_summary(result) -> dict:
    return {
        "mode_used": result.mode_used,
        "by_mode": result.attempts_by_mode(),
        "total": len(result.attempts),
        "attempts": [
            {
                "mode": a.mode,
                "index": a.index,
                "success": a.success,
                "error": a.error,
                "elapsed_ms": round(a.elapsed_ms, 1),
            }
            for a in result.attempts
        ],
        "final_error": result.final_error,
    }


@app.get("/api/cv-config")
def get_cv_config():
    cfg = _load_router_config()
    tuning = _load_cv_tuning()
    return {
        "primary": cfg.primary,
        "attempts_each": cfg.attempts_each,
        "auto_save_validated": cfg.auto_save_validated,
        "dataset_name": cfg.dataset_name,
        "cnn_active": bool(_read_active_cnn_run_id()),
        **tuning,
    }


class CvConfigPayload(BaseModel):
    primary: Optional[str] = None
    attempts_each: Optional[int] = None
    auto_save_validated: Optional[bool] = None
    dataset_name: Optional[str] = None
    occupancy_threshold: Optional[float] = None
    occupancy_delta_threshold: Optional[float] = None
    canny_low: Optional[int] = None
    canny_high: Optional[int] = None
    occupancy_std_weight: Optional[float] = None
    white_threshold: Optional[float] = None
    black_threshold: Optional[float] = None
    white_delta_threshold: Optional[float] = None
    black_delta_threshold: Optional[float] = None


@app.post("/api/cv-config")
def post_cv_config(payload: CvConfigPayload):
    cfg = _load_router_config()
    if payload.primary is not None:
        if payload.primary not in ("vision", "cnn"):
            raise HTTPException(400, "primary must be 'vision' or 'cnn'")
        cfg.primary = payload.primary
    if payload.attempts_each is not None:
        if payload.attempts_each < 1 or payload.attempts_each > 20:
            raise HTTPException(400, "attempts_each must be between 1 and 20")
        cfg.attempts_each = int(payload.attempts_each)
    if payload.auto_save_validated is not None:
        cfg.auto_save_validated = bool(payload.auto_save_validated)
    if payload.dataset_name is not None:
        name = payload.dataset_name.strip()
        if not name:
            raise HTTPException(400, "dataset_name cannot be empty")
        cfg.dataset_name = name
    _save_router_config(cfg)
    tuning_updates = {
        k: v for k, v in payload.model_dump().items()
        if k in _CV_TUNING_DEFAULTS and v is not None
    }
    if tuning_updates:
        _save_cv_tuning(tuning_updates)
    return get_cv_config()


@app.get("/api/validated-dataset/stats")
def get_validated_dataset_stats():
    cfg = _load_router_config()
    meta_path = LABELED_DATASETS_ROOT / cfg.dataset_name / "metadata.json"
    if not meta_path.exists():
        return {
            "dataset": cfg.dataset_name,
            "exists": False,
            "captures": 0,
            "last": [],
            "bulk_empty": 0,
            "bulk_white": 0,
            "bulk_black": 0,
        }
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as exc:
        raise HTTPException(500, f"Could not parse metadata: {exc}")
    captures = meta.get("captures") or []
    return {
        "dataset": cfg.dataset_name,
        "exists": True,
        "captures": len(captures),
        "last": captures[-10:],
        "bulk_empty": sum((meta.get("bulk_empty") or {}).values()),
        "bulk_white": sum((meta.get("bulk_white") or {}).values()),
        "bulk_black": sum((meta.get("bulk_black") or {}).values()),
        "path": str(meta_path.parent),
    }


@app.get("/api/game/session")
def game_session_status():
    return _game_session_payload("ok")


@app.post("/api/game/session/reset")
def game_session_reset():
    _GAME_SESSION.reset()
    return _game_session_payload("reset")


@app.post("/api/game/session/start")
def game_session_start(payload: GameSessionPayload):
    if payload.player_color not in {"white", "black"}:
        raise HTTPException(400, "player_color must be 'white' or 'black'")
    if payload.difficulty not in DIFFICULTY_SKILL_LEVEL:
        raise HTTPException(400, "difficulty must be 0, 1, or 2")

    _GAME_SESSION.reset()

    router, fns, cfg = _build_router(payload)
    last_initial: Optional[SessionResult] = None
    last_payload: dict = {}

    def _on_init_attempt(mode, idx, capture: CaptureOutcome) -> AttemptDecision:
        nonlocal last_initial, last_payload
        last_payload = capture.payload
        # initialize_from_bitmaps does not mutate on failure; it does set
        # session state on success — but the router returns immediately on
        # success, so this is safe to call once per attempt.
        last_initial = _GAME_SESSION.initialize_from_bitmaps(
            capture.white_bitmap,
            capture.black_bitmap,
            max_mismatches=payload.max_mismatches,
        )
        return AttemptDecision(
            success=last_initial.success,
            error=None if last_initial.success else last_initial.message,
        )

    router_result = router.scan(fns, _on_init_attempt)
    pipeline_result = last_payload or {}
    pipeline_result["cv_router"] = _router_attempts_summary(router_result)
    initial = last_initial if last_initial is not None else SessionResult(
        success=False,
        message=router_result.final_error or "No scan attempted.",
    )

    if not initial.success:
        expected_board = chess.Board()
        pipeline_result["board_validation_debug"] = {
            "expected_fen": expected_board.fen(),
            "mismatch_count": initial.mismatch_count,
            "observed_white_bitmap": pipeline_result.get("white_bitmap"),
            "observed_black_bitmap": pipeline_result.get("black_bitmap"),
        }
        return _game_session_payload("board_failed", pipeline_result=pipeline_result, started=initial)

    # Persist the validated frame for future CNN training (best-effort).
    pipeline_result["validated_capture"] = _persist_validated_capture(
        router_result.capture,
        mode_used=router_result.mode_used or "unknown",
        move_uci=None,
        session_id="session_start",
    )

    started = _GAME_SESSION.start_game(payload.player_color)
    if not started.success:
        return _game_session_payload("start_failed", pipeline_result=pipeline_result, started=started)

    robot_result = None
    robot_board_before = None
    robot_command = None
    if _GAME_SESSION.robot_moves_first():
        robot_board_before = _GAME_SESSION.get_current_board()
        robot_board_copy = robot_board_before.copy(stack=True) if robot_board_before is not None else None
        robot_result = _GAME_SESSION.compute_robot_move(
            engine_path=payload.engine_path,
            think_time=payload.think_time,
            skill_level=_resolve_skill_level(payload.skill_level, payload.difficulty),
        )
        if robot_result.success and robot_result.move_uci and robot_board_copy is not None:
            if payload.execute_robot:
                try:
                    robot_command = _execute_robot_session_move(
                        robot_result.move_uci,
                        robot_board_copy,
                        payload.port,
                        payload.baud,
                    )
                except Exception as e:
                    robot_adapter.close()
                    raise HTTPException(500, f"Robot command failed: {e}")
            commit_result = _GAME_SESSION.commit_robot_move(robot_result.move_uci)
            if not commit_result.success:
                robot_result = commit_result

    return _game_session_payload(
        "ok",
        pipeline_result=pipeline_result,
        started=started,
        robot_move=robot_result,
        robot_board_before=robot_board_before,
        robot_command=robot_command,
    )


@app.post("/api/game/session/player-done")
def game_session_player_done(payload: GameSessionTurnPayload):
    if not _GAME_SESSION.is_game_started():
        raise HTTPException(400, "Game session has not started. Run /api/game/session/start first.")
    if payload.difficulty not in DIFFICULTY_SKILL_LEVEL:
        raise HTTPException(400, "difficulty must be 0, 1, or 2")

    human_board_before = _GAME_SESSION.get_current_board()
    human_board_copy = human_board_before.copy(stack=True) if human_board_before is not None else None

    router, fns, cfg = _build_router(payload)
    last_human: Optional[SessionResult] = None
    last_payload: dict = {}

    def _on_move_attempt(mode, idx, capture: CaptureOutcome) -> AttemptDecision:
        nonlocal last_human, last_payload
        last_payload = capture.payload
        # process_bitmaps only mutates board state on a successful legal move,
        # so calling it repeatedly across failing attempts is safe; the router
        # returns as soon as success is True so we don't double-commit.
        last_human = _GAME_SESSION.process_bitmaps(
            capture.white_bitmap,
            capture.black_bitmap,
            max_mismatches=payload.max_mismatches,
        )
        return AttemptDecision(
            success=last_human.success,
            error=None if last_human.success else last_human.message,
        )

    router_result = router.scan(fns, _on_move_attempt)
    pipeline_result = last_payload or {}
    pipeline_result["cv_router"] = _router_attempts_summary(router_result)
    human_result = last_human if last_human is not None else SessionResult(
        success=False,
        message=router_result.final_error or "No scan attempted.",
    )

    if not human_result.success:
        return _game_session_payload(
            "player_move_failed",
            pipeline_result=pipeline_result,
            human_move=human_result,
            human_board_before=human_board_copy,
        )

    # Persist the validated frame for future CNN training (best-effort).
    pipeline_result["validated_capture"] = _persist_validated_capture(
        router_result.capture,
        mode_used=router_result.mode_used or "unknown",
        move_uci=human_result.move_uci,
        session_id="player_done",
    )

    current_board = _GAME_SESSION.get_current_board()
    if current_board is not None and current_board.is_game_over():
        return _game_session_payload(
            "game_over",
            pipeline_result=pipeline_result,
            human_move=human_result,
            human_board_before=human_board_copy,
        )

    robot_board_before = _GAME_SESSION.get_current_board()
    robot_board_copy = robot_board_before.copy(stack=True) if robot_board_before is not None else None
    robot_result = _GAME_SESSION.compute_robot_move(
        engine_path=payload.engine_path,
        think_time=payload.think_time,
        skill_level=_resolve_skill_level(payload.skill_level, payload.difficulty),
    )
    robot_command = None
    if not robot_result.success or not robot_result.move_uci or robot_board_copy is None:
        return _game_session_payload(
            "robot_move_failed",
            pipeline_result=pipeline_result,
            human_move=human_result,
            human_board_before=human_board_copy,
            robot_move=robot_result,
            robot_board_before=robot_board_copy,
        )

    if payload.execute_robot:
        try:
            robot_command = _execute_robot_session_move(
                robot_result.move_uci,
                robot_board_copy,
                payload.port,
                payload.baud,
            )
        except Exception as e:
            robot_adapter.close()
            raise HTTPException(500, f"Robot command failed: {e}")

    commit_result = _GAME_SESSION.commit_robot_move(robot_result.move_uci)
    if not commit_result.success:
        robot_result = commit_result

    evaluation = _build_session_evaluation(
        prev_eval=_evaluate_safe(human_board_copy, payload.engine_path, payload.think_time),
        post_player_board=robot_board_copy,
        final_board=_GAME_SESSION.get_current_board(),
        engine_path=payload.engine_path,
        think_time=payload.think_time,
        player_turn_white=human_board_copy is not None and human_board_copy.turn == chess.WHITE,
    )
    if evaluation and evaluation.get("player_move_rating"):
        _flash_lcd_rating(evaluation["player_move_rating"])

    return _game_session_payload(
        "ok",
        pipeline_result=pipeline_result,
        human_move=human_result,
        human_board_before=human_board_copy,
        robot_move=robot_result,
        robot_board_before=robot_board_copy,
        robot_command=robot_command,
        evaluation=evaluation,
    )


# ---------------------------------------------------------------------------
# Manual click-to-move endpoint (Simulation + Remote Physical play modes)
# ---------------------------------------------------------------------------


class ManualStartPayload(BaseModel):
    player_color: Literal["white", "black"] = "white"
    difficulty: int = 1
    skill_level: Optional[int] = None
    engine_path: str = "stockfish"
    think_time: float = 0.1
    execute_robot: bool = False
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT


@app.post("/api/game/session/manual-start")
def game_session_manual_start(payload: ManualStartPayload):
    """Start a session from the standard chess position without using the camera.

    Used by the dashboard's Simulation / Remote-Physical click-to-play modes
    where the player isn't bringing the CV pipeline online. The session is
    seeded with a fresh ``chess.Board()`` and ``start_game`` runs as usual,
    so the rest of the pipeline (manual-move, evaluation, robot reply)
    behaves identically.
    """
    if payload.player_color not in {"white", "black"}:
        raise HTTPException(400, "player_color must be 'white' or 'black'")
    if payload.difficulty not in DIFFICULTY_SKILL_LEVEL:
        raise HTTPException(400, "difficulty must be 0, 1, or 2")

    from charm.game.state_tracker import BoardStateTracker

    _GAME_SESSION.reset()
    _GAME_SESSION.tracker = BoardStateTracker(chess.Board())
    _GAME_SESSION.initialized = True
    _GAME_SESSION.flip_180 = False
    started = _GAME_SESSION.start_game(payload.player_color)
    if not started.success:
        return _game_session_payload("start_failed", started=started)

    # If the player chose black, the robot moves first — run that turn so
    # the dashboard reflects an in-progress game immediately.
    robot_result = None
    robot_board_before = None
    robot_command = None
    if _GAME_SESSION.robot_moves_first():
        robot_board_before = _GAME_SESSION.get_current_board()
        robot_board_copy = robot_board_before.copy(stack=True) if robot_board_before is not None else None
        skill_level = _resolve_skill_level(payload.skill_level, payload.difficulty)
        robot_result = _GAME_SESSION.compute_robot_move(
            engine_path=payload.engine_path,
            think_time=payload.think_time,
            skill_level=skill_level,
        )
        if robot_result.success and robot_result.move_uci and robot_board_copy is not None:
            if payload.execute_robot:
                try:
                    robot_command = _execute_robot_session_move(
                        robot_result.move_uci,
                        robot_board_copy,
                        payload.port,
                        payload.baud,
                    )
                except Exception as exc:
                    robot_adapter.close()
                    raise HTTPException(500, f"Robot command failed: {exc}") from exc
            commit_result = _GAME_SESSION.commit_robot_move(robot_result.move_uci)
            if not commit_result.success:
                robot_result = commit_result

    panel = _build_session_evaluation(
        prev_eval=_evaluate_safe(chess.Board(), payload.engine_path, payload.think_time),
        post_player_board=_GAME_SESSION.get_current_board(),
        final_board=_GAME_SESSION.get_current_board(),
        engine_path=payload.engine_path,
        think_time=payload.think_time,
        player_turn_white=True,
    )
    if panel is not None:
        # No player move yet — clear the rating so the UI doesn't show one.
        panel["player_move_rating"] = None
        panel["player_cp_loss"] = None

    return _game_session_payload(
        "ok",
        started=started,
        robot_move=robot_result,
        robot_board_before=robot_board_before,
        robot_command=robot_command,
        evaluation=panel,
    )


class ManualMovePayload(BaseModel):
    uci: str
    execute_robot: bool = False
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT
    engine_path: str = "stockfish"
    think_time: float = 0.1
    difficulty: int = 1
    skill_level: Optional[int] = None


def _evaluate_safe(
    board: Optional[chess.Board],
    engine_path: str,
    think_time: float,
) -> Optional[Evaluation]:
    if board is None:
        return None
    try:
        return evaluate_position(board, engine_path=engine_path, think_time=think_time)
    except FileNotFoundError:
        return None
    except Exception as exc:
        print(f"[eval] evaluate_position failed: {exc!r}", flush=True)
        return None


def _build_session_evaluation(
    prev_eval: Optional[Evaluation],
    post_player_board: Optional[chess.Board],
    final_board: Optional[chess.Board],
    engine_path: str,
    think_time: float,
    player_turn_white: bool,
) -> Optional[dict]:
    """Bundle pre-move / post-move / final evaluations into the UI payload."""
    if prev_eval is None:
        return None

    post_player_eval = _evaluate_safe(post_player_board, engine_path, think_time)
    final_eval = _evaluate_safe(final_board, engine_path, think_time)

    classification: Optional[dict] = None
    if post_player_eval is not None:
        classification = _classify_player_move(prev_eval, post_player_eval, player_turn_white)

    eval_for_panel = final_eval or post_player_eval or prev_eval
    panel = _evaluation_payload(eval_for_panel)
    panel.update({
        "player_move_rating": classification["rating"] if classification else None,
        "player_cp_loss": classification["cp_loss"] if classification else None,
        # best_move_suggestion = the move Stockfish wanted *before* the
        # player moved, so the UI can say "try X instead".
        "best_move_suggestion": classification["best_move_suggestion"] if classification else panel.get("best_move_suggestion"),
        "best_move_uci": classification["best_move_uci"] if classification else panel.get("best_move_uci"),
    })
    return panel


@app.post("/api/game/session/manual-move")
def game_session_manual_move(payload: ManualMovePayload):
    if not _GAME_SESSION.is_game_started():
        raise HTTPException(400, "Game session has not started. Run /api/game/session/start first.")

    player_board_before = _GAME_SESSION.get_current_board()
    if player_board_before is None:
        raise HTTPException(400, "Game session has no board state.")

    try:
        move = chess.Move.from_uci(payload.uci)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid UCI move: {payload.uci}") from exc

    if move not in player_board_before.legal_moves:
        raise HTTPException(400, f"Move {payload.uci} is not legal in the current position.")

    player_turn_white = player_board_before.turn == chess.WHITE
    player_board_copy = player_board_before.copy(stack=True)

    # 1. Evaluate the position the player faced before moving.
    prev_eval = _evaluate_safe(player_board_before, payload.engine_path, payload.think_time)

    # 2. Optionally execute the player's move on the physical arm.
    player_command: Optional[dict] = None
    if payload.execute_robot:
        try:
            player_command = _execute_robot_session_move(
                payload.uci,
                player_board_copy,
                payload.port,
                payload.baud,
            )
        except Exception as exc:
            robot_adapter.close()
            raise HTTPException(500, f"Player arm move failed: {exc}") from exc

    # 3. Commit the player's move to the shared session.
    commit_player = _GAME_SESSION.commit_robot_move(payload.uci)
    if not commit_player.success:
        raise HTTPException(400, commit_player.message)

    # 4. Evaluate the resulting position (now the bot's turn).
    post_player_board = _GAME_SESSION.get_current_board()
    post_player_eval = _evaluate_safe(post_player_board, payload.engine_path, payload.think_time)

    # 5. Classify the player's move and flash the LCD when appropriate.
    classification = None
    if prev_eval is not None and post_player_eval is not None:
        classification = _classify_player_move(prev_eval, post_player_eval, player_turn_white)
        _flash_lcd_rating(classification["rating"])

    # 6. Bail early if the player's move ended the game.
    if post_player_board is not None and post_player_board.is_game_over():
        panel = _build_session_evaluation(
            prev_eval=prev_eval,
            post_player_board=post_player_board,
            final_board=post_player_board,
            engine_path=payload.engine_path,
            think_time=payload.think_time,
            player_turn_white=player_turn_white,
        )
        return _game_session_payload(
            "game_over",
            human_move=commit_player,
            human_board_before=player_board_copy,
            player_command=player_command,
            evaluation=panel,
        )

    # 7. Compute and (optionally) execute the bot's reply.
    robot_board_before = _GAME_SESSION.get_current_board()
    robot_board_copy = robot_board_before.copy(stack=True) if robot_board_before is not None else None
    skill_level = _resolve_skill_level(payload.skill_level, payload.difficulty)
    robot_result = _GAME_SESSION.compute_robot_move(
        engine_path=payload.engine_path,
        think_time=payload.think_time,
        skill_level=skill_level,
    )
    robot_command: Optional[dict] = None

    if not robot_result.success or not robot_result.move_uci or robot_board_copy is None:
        panel = _build_session_evaluation(
            prev_eval=prev_eval,
            post_player_board=post_player_board,
            final_board=post_player_board,
            engine_path=payload.engine_path,
            think_time=payload.think_time,
            player_turn_white=player_turn_white,
        )
        return _game_session_payload(
            "robot_move_failed",
            human_move=commit_player,
            human_board_before=player_board_copy,
            robot_move=robot_result,
            robot_board_before=robot_board_copy,
            player_command=player_command,
            evaluation=panel,
        )

    if payload.execute_robot:
        try:
            robot_command = _execute_robot_session_move(
                robot_result.move_uci,
                robot_board_copy,
                payload.port,
                payload.baud,
            )
        except Exception as exc:
            robot_adapter.close()
            raise HTTPException(500, f"Robot command failed: {exc}") from exc

    commit_robot = _GAME_SESSION.commit_robot_move(robot_result.move_uci)
    if not commit_robot.success:
        robot_result = commit_robot

    panel = _build_session_evaluation(
        prev_eval=prev_eval,
        post_player_board=post_player_board,
        final_board=_GAME_SESSION.get_current_board(),
        engine_path=payload.engine_path,
        think_time=payload.think_time,
        player_turn_white=player_turn_white,
    )

    return _game_session_payload(
        "ok",
        human_move=commit_player,
        human_board_before=player_board_copy,
        robot_move=robot_result,
        robot_board_before=robot_board_copy,
        robot_command=robot_command,
        player_command=player_command,
        evaluation=panel,
    )


@app.get("/api/calibration")
def get_calibration():
    result: dict = {}
    try:
        result["board"] = json.loads(BOARD_CAL_PATH.read_text())
    except Exception:
        result["board"] = None
    try:
        result["inner"] = json.loads(INNER_CAL_PATH.read_text())
    except Exception:
        result["inner"] = None
    return result


@app.put("/api/calibration")
def update_calibration(update: CalibrationUpdate):
    if update.board:
        BOARD_CAL_PATH.write_text(json.dumps(update.board, indent=2))
    if update.inner:
        INNER_CAL_PATH.write_text(json.dumps(update.inner, indent=2))
    return {"status": "saved"}


@app.post("/api/calibration/board-corners")
def calibrate_board_corners(payload: BoardCornerCalibrationPayload):
    calibration = FourPointCalibration(
        top_left=payload.top_left,
        top_right=payload.top_right,
        bottom_right=payload.bottom_right,
        bottom_left=payload.bottom_left,
    )

    path = Path(payload.image_path) if payload.image_path else resolve_latest_raw_path()
    if not path.exists():
        raise HTTPException(404, f"Image not found: {path}")
    image = cv2.imread(str(path))
    if image is None:
        raise HTTPException(400, f"Failed to decode image: {path}")

    try:
        save_four_point_calibration(calibration, BOARD_CAL_PATH)
        first_warp = warp_from_calibration(image, calibration, output_size=payload.warp_size)
        debug = draw_calibration_points(image, calibration)
    except Exception as e:
        raise HTTPException(500, f"Board calibration failed: {e}")

    return {
        "status": "saved",
        "path": str(BOARD_CAL_PATH),
        "image_path": str(path),
        "board": {
            "top_left": list(calibration.top_left),
            "top_right": list(calibration.top_right),
            "bottom_right": list(calibration.bottom_right),
            "bottom_left": list(calibration.bottom_left),
        },
        "first_warp": to_b64(first_warp),
        "debug": to_b64(debug),
    }


class ArucoCalibratePayload(BaseModel):
    image_path: Optional[str] = None
    capture: bool = True
    warp_size: int = 800
    dictionary: str = "DICT_4X4_50"
    layout: dict[str, str] = Field(
        default_factory=lambda: {"0": "a8", "1": "h8", "2": "h1", "3": "a1"},
    )
    save: bool = False  # only persist to BOARD_CAL_PATH when explicitly applied


_ARUCO_DICT_BY_NAME = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
}


@app.post("/api/calibration/aruco-detect")
def calibrate_aruco(payload: ArucoCalibratePayload):
    from charm.vision.aruco_calibration import (
        compute_board_corners_from_markers,
        detect_aruco_markers,
        draw_aruco_overlay,
    )

    dict_id = _ARUCO_DICT_BY_NAME.get(payload.dictionary)
    if dict_id is None:
        raise HTTPException(400, f"Unsupported dictionary: {payload.dictionary}")

    # Resolve image (fresh capture or saved path).
    if payload.capture:
        try:
            src_path = Path(_capture_or_resolve_image(PipelineParams(), capture=True))
        except HTTPException:
            raise
    else:
        src_path = Path(payload.image_path) if payload.image_path else resolve_latest_raw_path()
    if not src_path.exists():
        raise HTTPException(404, f"Image not found: {src_path}")
    image = cv2.imread(str(src_path))
    if image is None:
        raise HTTPException(400, f"Failed to decode image: {src_path}")

    try:
        marker_layout = {int(k): v for k, v in payload.layout.items()}
    except ValueError as e:
        raise HTTPException(400, f"Layout keys must be integer marker IDs: {e}")

    detections = detect_aruco_markers(image, dictionary_id=dict_id)
    try:
        result = compute_board_corners_from_markers(detections, marker_layout)
    except ValueError as e:
        return {
            "status": "incomplete",
            "image_path": str(src_path),
            "detections": [d.to_json() for d in detections],
            "detected_ids": sorted(d.marker_id for d in detections),
            "expected_ids": sorted(marker_layout.keys()),
            "error": str(e),
        }

    overlay = draw_aruco_overlay(image, result)
    try:
        first_warp = warp_from_calibration(image, result.calibration, output_size=payload.warp_size)
    except Exception as e:
        raise HTTPException(500, f"warp failed: {e}")

    saved = False
    if payload.save:
        save_four_point_calibration(result.calibration, BOARD_CAL_PATH)
        saved = True

    return {
        "status": "ok",
        "image_path": str(src_path),
        "saved": saved,
        "saved_path": str(BOARD_CAL_PATH) if saved else None,
        "board": {
            "top_left": list(result.calibration.top_left),
            "top_right": list(result.calibration.top_right),
            "bottom_right": list(result.calibration.bottom_right),
            "bottom_left": list(result.calibration.bottom_left),
        },
        "detections": [d.to_json() for d in result.detections],
        "used_ids": result.used_ids,
        "missing_ids": result.missing_ids,
        "first_warp": to_b64(first_warp),
        "overlay": to_b64(overlay),
        "layout": {str(k): v for k, v in marker_layout.items()},
    }


@app.get("/api/calibration/aruco-marker")
def aruco_marker_image(marker_id: int, size: int = 600, dictionary: str = "DICT_4X4_50"):
    """Render a single ArUco marker as a PNG so the user can print it.

    Size is in pixels; print at 3.75 cm wide. With a 600px marker this means
    the printer must scale it to 3.75 cm: at 96 dpi -> 142px/inch -> set print
    scale so output is 3.75 cm. Most browsers print at the page's natural DPI;
    callers can pick `size` so the print scaling lands on 3.75 cm cleanly.
    """
    import base64 as _b64
    import io

    dict_id = _ARUCO_DICT_BY_NAME.get(dictionary)
    if dict_id is None:
        raise HTTPException(400, f"Unsupported dictionary: {dictionary}")
    if size <= 0 or size > 2000:
        raise HTTPException(400, "size must be 1..2000")
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
    img = cv2.aruco.generateImageMarker(aruco_dict, int(marker_id), int(size))
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise HTTPException(500, "Failed to encode marker PNG")
    return {
        "marker_id": int(marker_id),
        "dictionary": dictionary,
        "size_px": int(size),
        "image": _b64.b64encode(buf.tobytes()).decode(),
    }


@app.get("/api/images/list")
def list_raw_images():
    candidates = [
        *sorted(PYTHON_CODE_DIR.glob("latest_raw*.jpg"), key=lambda p: p.name),
        *sorted(REPO_ROOT.glob("latest_raw*.jpg"), key=lambda p: p.name),
        *sorted(PYTHON_CODE_DIR.glob("game_*/*.jpg"), key=lambda p: (p.parent.name, p.name)),
        *sorted(PYTHON_CODE_DIR.glob("game_*/*.jpeg"), key=lambda p: (p.parent.name, p.name)),
        *sorted(PYTHON_CODE_DIR.glob("game_*/*.png"), key=lambda p: (p.parent.name, p.name)),
    ]
    seen: set[str] = set()
    images: list[dict] = []
    for path in candidates:
        resolved = str(path.resolve())
        if resolved not in seen and path.exists():
            seen.add(resolved)
            try:
                name = str(path.relative_to(PYTHON_CODE_DIR))
            except ValueError:
                name = path.name
            images.append({"name": name, "path": str(path)})
    return {"images": images}


@app.get("/api/image/raw")
def get_raw_image():
    path = resolve_latest_raw_path()
    if not path.exists():
        raise HTTPException(404, "No raw image found. Run pipeline first or upload one.")
    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(400, f"Failed to decode image: {path}")
    return {"image": to_b64(img), "path": str(path), "timestamp": time.time()}


@app.post("/api/image/read")
def read_image(payload: ImagePathPayload):
    path = Path(payload.path)
    if not path.exists():
        raise HTTPException(404, f"Image not found: {path}")
    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(400, f"Failed to decode image: {path}")
    return {"image": to_b64(img), "path": str(path), "timestamp": time.time()}


@app.post("/api/capture")
def capture_from_camera(payload: CameraCapturePayload):
    try:
        from charm.vision.transferphoto import fetch_raw_image

        url = _normalize_camera_url(payload.url)
        path = fetch_raw_image(url) if url else fetch_raw_image()
        img = cv2.imread(path)
        if img is None:
            raise RuntimeError(f"Failed to decode captured image: {path}")
        return {"status": "ok", "path": path, "image": to_b64(img)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/params/defaults")
def get_defaults():
    return PipelineParams().model_dump(exclude={"image_path"})


def _load_annotations() -> list[dict]:
    if not ANNOTATIONS_PATH.exists():
        return []
    try:
        return json.loads(ANNOTATIONS_PATH.read_text())
    except Exception:
        return []


def _upsert_annotation(
    image_id: str, scene_id: str, board_64: list[str], image_path: Optional[str]
) -> None:
    annotations = _load_annotations()
    existing = next((a for a in annotations if a["image_id"] == image_id), None)
    entry = {
        "image_id": image_id,
        "scene_id": scene_id,
        "board_64": board_64,
        "image_path": image_path,
        "saved_at": time.time(),
    }
    if existing:
        annotations[annotations.index(existing)] = entry
    else:
        annotations.append(entry)
    ANNOTATIONS_PATH.write_text(json.dumps(annotations, indent=2))


@app.post("/api/annotations")
def save_annotation(payload: AnnotationPayload):
    if len(payload.board_64) != 64:
        raise HTTPException(400, "board_64 must have exactly 64 entries")
    try:
        _upsert_annotation(
            payload.image_id, payload.scene_id, payload.board_64, payload.image_path
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to save annotation: {e}")
    return {"status": "saved", "image_id": payload.image_id}


@app.get("/api/annotations")
def list_annotations():
    annotations = _load_annotations()
    white_total = sum(a["board_64"].count("white") for a in annotations)
    black_total = sum(a["board_64"].count("black") for a in annotations)
    scenes = len({a["scene_id"] for a in annotations})
    return {
        "count": len(annotations),
        "n_white": white_total,
        "n_black": black_total,
        "n_scenes": scenes,
        "annotations": [
            {"image_id": a["image_id"], "scene_id": a["scene_id"], "saved_at": a.get("saved_at")}
            for a in annotations
        ],
    }


@app.get("/api/classifier/status")
def classifier_status():
    last_result = None
    if CLASSIFIER_STATUS_PATH.exists():
        try:
            last_result = json.loads(CLASSIFIER_STATUS_PATH.read_text())
        except Exception:
            pass
    return {
        "model_trained": False,
        "model_path": "",
        "last_result": last_result,
    }


@app.post("/api/classifier/retrain")
def retrain_classifier():
    raise HTTPException(501, "kNN classifier has been removed — color detection uses brightness threshold only.")


# ---------------------------------------------------------------------------
# Labeled-data wizard (arm-driven dataset capture + exemplar classifier)
# ---------------------------------------------------------------------------

from webapp_backend.labeling import (
    DatasetSettings,
    DatasetStore,
    square_to_rc as labeling_square_to_rc,
    SQUARES as LABELING_SQUARES,
)
from charm.vision.exemplar_classifier import (
    build_exemplar_config,
    leave_one_out_accuracy,
)

LABELED_DATASETS_DIR = PYTHON_CODE_DIR / "labeled_datasets"
LABEL_STORE = DatasetStore(LABELED_DATASETS_DIR)
LABELING_BUSY: dict[str, bool] = {"busy": False}
ACTIVE_CLASSIFIER_PATH = PYTHON_CODE_DIR / "active_classifier.json"

# In-process cache so we don't reparse exemplar_config.json on every pipeline run.
_ACTIVE_CACHE: dict = {"name": None, "mtime": 0.0, "config": None}


def _load_active_classifier_pointer() -> Optional[str]:
    if not ACTIVE_CLASSIFIER_PATH.exists():
        return None
    try:
        data = json.loads(ACTIVE_CLASSIFIER_PATH.read_text())
        name = data.get("name")
        return str(name) if name else None
    except Exception:
        return None


def _save_active_classifier_pointer(name: Optional[str]) -> None:
    if name is None:
        if ACTIVE_CLASSIFIER_PATH.exists():
            ACTIVE_CLASSIFIER_PATH.unlink()
        return
    ACTIVE_CLASSIFIER_PATH.write_text(json.dumps({"name": name, "saved_at": time.time()}, indent=2))


def _get_active_exemplar_config():
    """Return (name, ExemplarConfig) or (None, None) if no classifier is active.

    Reloads the on-disk exemplar_config.json when its mtime changes so the
    wizard can re-train without restarting the server.
    """
    name = _load_active_classifier_pointer()
    if not name:
        return None, None
    cfg_path = LABEL_STORE.dataset_dir(name) / "exemplar_config.json"
    if not cfg_path.exists():
        return None, None
    mtime = cfg_path.stat().st_mtime
    if _ACTIVE_CACHE["name"] == name and _ACTIVE_CACHE["mtime"] == mtime and _ACTIVE_CACHE["config"] is not None:
        return name, _ACTIVE_CACHE["config"]
    from charm.vision.exemplar_classifier import ExemplarConfig
    try:
        cfg = ExemplarConfig.load(cfg_path)
    except Exception:
        return None, None
    _ACTIVE_CACHE["name"] = name
    _ACTIVE_CACHE["mtime"] = mtime
    _ACTIVE_CACHE["config"] = cfg
    return name, cfg


class LabelingSettingsPayload(BaseModel):
    frames_per_square: int = 5
    settle_ms: int = 600
    source_square: str = "h8"
    piece_type: str = "pawn"
    lighting_note: str = ""


class LabelingCreatePayload(BaseModel):
    name: str
    settings: LabelingSettingsPayload = Field(default_factory=LabelingSettingsPayload)


class LabelingUpdateSettingsPayload(BaseModel):
    settings: LabelingSettingsPayload


class LabelingCaptureEmptyPayload(BaseModel):
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = True
    frames: Optional[int] = None  # override frames-per-square; defaults to settings
    # "overwrite" wipes existing empty frames (default for first capture/recapture);
    # "append" grows the empty-frame bucket so callers can collect more data.
    mode: str = "overwrite"


class LabelingCaptureSquarePayload(BaseModel):
    color: str  # "white" | "black"
    square: str  # e.g. "a1"
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = True
    frames: Optional[int] = None
    # Manual-mode callers move pieces by hand and must not trigger any arm
    # motion. When True, skip the auto-home safety net below.
    skip_arm_home_check: bool = False
    # "overwrite" wipes the (color, square) folder before writing (retake);
    # "append" keeps existing frames and adds new ones with incremented names.
    mode: str = "overwrite"


class LabelingCaptureBulkPayload(BaseModel):
    # Map of square -> label, where label ∈ {"empty", "white", "black"}. Squares
    # not present in this dict are skipped (no crop written).
    labels: dict[str, str]
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = True
    # How many board photos to take this round. Each photo yields one cell
    # per painted square. Defaults to 1 to keep the UX tight.
    frames: int = 1
    settle_ms: Optional[int] = None
    # Bulk paint never moves the arm.
    skip_arm_home_check: bool = True


class LabelingArmPayload(BaseModel):
    color: str
    square: str  # destination square
    action: str  # "pickup_source" | "place_target" | "return_to_source" | "home" | "move_piece" | "pick_and_place"
    from_square: Optional[str] = None
    port: Optional[str] = None
    baud: int = ROBOT_BAUD_DEFAULT


def _meta_response(name: str) -> dict:
    meta = LABEL_STORE.load(name)
    accuracy_path = LABEL_STORE.dataset_dir(name) / "accuracy.json"
    config_path = LABEL_STORE.dataset_dir(name) / "exemplar_config.json"
    return {
        "metadata": meta.to_json(),
        "paths": {
            "dir": str(LABEL_STORE.dataset_dir(name)),
            "exemplar_config": str(config_path) if config_path.exists() else None,
            "accuracy": str(accuracy_path) if accuracy_path.exists() else None,
        },
    }


# Per-motion-command wait. Long enough to cover a full pick-put-home cycle
# on a slow arm, but bounded so a stuck firmware can't hang the API.
_MOTION_MAX_WAIT_S = 60.0

# Tolerances when checking whether the arm has parked at its home pose.
_HOME_XY_TOL_MM = 5.0
_HOME_Z_TOL_MM = 15.0


def _send_motion(commands: list[str], port: Optional[str], baud: int) -> list[str]:
    """Send motion commands, waiting for each to actually finish on the arm.

    Every blocking firmware command (`home`, `pick`, `put`, `moveXYZ`, ...)
    falls through to a trailing `Position: (x, y, z)` print *after* the
    stepper motion completes. We use that as the per-command completion
    marker so `send_commands` doesn't return mid-move.
    """
    return robot_adapter.send_commands(
        commands,
        port,
        baud,
        max_wait=_MOTION_MAX_WAIT_S,
        stop_on="Position:",
    )


def _home_point() -> Optional[dict]:
    try:
        calib = robot_adapter.load_calibration(ROBOT_CAL_PATH)
    except Exception:
        return None
    home_pt = calib.get("home") or {}
    return home_pt or None


def _position_matches_home(pos: Optional[dict], home_pt: dict) -> bool:
    if pos is None:
        return False
    dx = abs(pos.get("x", 0.0) - float(home_pt.get("x", 0.0)))
    dy = abs(pos.get("y", 0.0) - float(home_pt.get("y", 0.0)))
    dz = abs(pos.get("z", 0.0) - float(home_pt.get("z", 0.0)))
    return dx < _HOME_XY_TOL_MM and dy < _HOME_XY_TOL_MM and dz < _HOME_Z_TOL_MM


def _verify_arm_home(responses: list[str], port: Optional[str], baud: int) -> None:
    """Confirm the arm is parked at home. Raises HTTPException if not.

    Uses the trailing `Position:` line that the firmware prints after a
    blocking command — no polling. If the move-response doesn't already
    contain a matching position, do a single explicit `pos` query as a
    safety net before giving up.
    """
    if not port:
        port = robot_adapter.connected_port() or robot_adapter.find_port()
    if not port:
        return
    home_pt = _home_point()
    if not home_pt:
        return
    if _position_matches_home(robot_adapter.parse_position(responses), home_pt):
        return
    try:
        resp = robot_adapter.send_commands(
            ["pos"], port, baud, max_wait=5.0, stop_on="Position:"
        )
        if _position_matches_home(robot_adapter.parse_position(resp), home_pt):
            return
        reported = robot_adapter.parse_position(resp)
    except Exception as e:
        raise HTTPException(504, f"Arm home verification failed: {e}")
    raise HTTPException(
        504,
        f"Arm did not reach home pose. Expected {home_pt}, got {reported}.",
    )


def _rc_to_square(row: int, col: int) -> Optional[str]:
    """Inverse of charm.vision.cnn_dataset._square_to_rc — uses the same 180°
    rotated mapping so a cell saved to bulk/<color>/a1/ truly is a1's cell."""
    if not (0 <= row < 8 and 0 <= col < 8):
        return None
    file = chr(ord("a") + (7 - col))
    rank = row + 1
    return f"{file}{rank}"


def _capture_warped_frames(params: PipelineParams, count: int, settle_ms: int, do_capture: bool) -> list[np.ndarray]:
    """Capture `count` *warped* board frames, sleeping settle_ms between captures.

    Frames are always passed through the full calibration pipeline (outer board
    warp + inner warp) so the saved JPEGs only contain the 800x800 on-board
    region — anything outside the board (the desk, the arm, ambient clutter)
    is cropped out. ``apply_inner_warp`` is forced True here regardless of the
    request payload to guarantee this property for labeled-data captures.
    """
    if count < 1:
        raise HTTPException(400, "frames must be >= 1")
    # Force the inner warp on, even if the caller forgot to set it.
    labeling_params = params.model_copy(update={"apply_inner_warp": True})
    frames: list[np.ndarray] = []
    for _ in range(count):
        source_path = str(_capture_or_resolve_image(labeling_params, capture=do_capture))
        warped = _warped_board_for_tuning(labeling_params, source_path)
        frames.append(warped)
        if settle_ms > 0 and len(frames) < count:
            time.sleep(settle_ms / 1000.0)
    return frames


@app.get("/api/labeling/datasets")
def list_label_datasets():
    return {
        "datasets": [m.to_json() for m in LABEL_STORE.list()],
        "squares": LABELING_SQUARES,
    }


@app.post("/api/labeling/datasets")
def create_label_dataset(payload: LabelingCreatePayload):
    try:
        settings = DatasetSettings(**payload.settings.model_dump())
        meta = LABEL_STORE.create(payload.name, settings)
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _meta_response(meta.name)


@app.get("/api/labeling/datasets/{name}")
def get_label_dataset(name: str):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    return _meta_response(name)


@app.post("/api/labeling/datasets/rescan-all")
def rescan_all_label_datasets():
    """Rebuild metadata.json for every folder under labeled_datasets/.

    Picks up datasets dropped in by hand (e.g. a manually combined folder
    with no metadata) and refreshes counts for ones that were edited
    out-of-band.
    """
    metas = LABEL_STORE.rescan_all()
    return {"rescanned": [m.to_json() for m in metas]}


@app.post("/api/labeling/datasets/{name}/rescan")
def rescan_label_dataset(name: str):
    try:
        meta = LABEL_STORE.rescan(name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"metadata": meta.to_json()}


@app.delete("/api/labeling/datasets/{name}")
def delete_label_dataset(name: str):
    LABEL_STORE.delete(name)
    return {"status": "deleted", "name": name}


@app.put("/api/labeling/datasets/{name}/settings")
def update_label_dataset_settings(name: str, payload: LabelingUpdateSettingsPayload):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    meta = LABEL_STORE.load(name)
    meta.settings = DatasetSettings(**payload.settings.model_dump())
    LABEL_STORE.save(meta)
    return _meta_response(name)


@app.get("/api/labeling/datasets/{name}/thumb")
def get_label_thumb(name: str, color: str, square: str):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    if color == "empty":
        img = LABEL_STORE.read_empty_first_frame(name)
    else:
        try:
            img = LABEL_STORE.read_square_first_frame(name, color, square)
        except ValueError as e:
            raise HTTPException(400, str(e))
    if img is None:
        # Fall back to bulk-paint cells so the gallery / review grid still
        # shows a thumbnail when this square was only captured via bulk.
        if color in ("white", "black"):
            try:
                bulk_dir = LABEL_STORE.bulk_dir(name, color, square)
                if bulk_dir.exists():
                    files = sorted(p for p in bulk_dir.iterdir() if p.suffix == ".jpg")
                    if files:
                        cell_img = cv2.imread(str(files[0]))
                        if cell_img is not None:
                            return {"exists": True, "image": to_b64(cell_img)}
            except Exception:
                pass
        return {"exists": False, "image": None}
    # crop the relevant cell for retake thumbnails (only when color != empty)
    if color != "empty":
        try:
            row, col = labeling_square_to_rc(square)
            x_lines, y_lines = detect_8x8_grid_lines(img)
            cells = extract_8x8_cells(img, x_lines, y_lines)
            cell = next((c for c in cells if c.row == row and c.col == col), None)
            if cell is not None:
                img = cell.image
        except Exception:
            pass
    return {"exists": True, "image": to_b64(img)}


@app.post("/api/labeling/datasets/{name}/capture-empty")
def capture_empty_for_dataset(name: str, payload: LabelingCaptureEmptyPayload):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    if LABELING_BUSY["busy"]:
        raise HTTPException(409, "Labeling capture already running")
    meta = LABEL_STORE.load(name)
    frames_count = int(payload.frames or meta.settings.frames_per_square)
    mode = payload.mode if payload.mode in ("overwrite", "append") else "overwrite"
    LABELING_BUSY["busy"] = True
    try:
        frames = _capture_warped_frames(payload.params, frames_count, meta.settings.settle_ms, payload.capture)
        saved = LABEL_STORE.write_empty_frames(name, frames, mode=mode)
    finally:
        LABELING_BUSY["busy"] = False
    return {"saved_frames": saved, **_meta_response(name)}


@app.post("/api/labeling/datasets/{name}/capture-square")
def capture_square_for_dataset(name: str, payload: LabelingCaptureSquarePayload):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    if LABELING_BUSY["busy"]:
        raise HTTPException(409, "Labeling capture already running")
    meta = LABEL_STORE.load(name)
    color = payload.color.lower()
    if color not in ("white", "black"):
        raise HTTPException(400, "color must be 'white' or 'black'")
    if payload.square.lower() not in LABELING_SQUARES:
        raise HTTPException(400, f"Invalid square: {payload.square}")

    frames_count = int(payload.frames or meta.settings.frames_per_square)
    LABELING_BUSY["busy"] = True
    try:
        # Safety net: sweep callers already homed the arm and waited for the
        # trailing `Position:` marker, but a direct/retake call may not have.
        # If a robot is connected and we have a home calibration, self-heal
        # by sending `home` (which blocks until the move completes) before
        # verifying. Refuse to capture if it still isn't parked.
        # Manual-mode callers opt out entirely so capture never moves the arm.
        port = robot_adapter.connected_port() or robot_adapter.find_port()
        home_pt = _home_point()
        if not payload.skip_arm_home_check and port and home_pt:
            try:
                pos_resp = robot_adapter.send_commands(
                    ["pos"], port, ROBOT_BAUD_DEFAULT, max_wait=5.0, stop_on="Position:"
                )
            except Exception:
                pos_resp = []
            if not _position_matches_home(
                robot_adapter.parse_position(pos_resp), home_pt
            ):
                home_resp = _send_motion(["home"], port, ROBOT_BAUD_DEFAULT)
                _verify_arm_home(home_resp, port, ROBOT_BAUD_DEFAULT)
        frames = _capture_warped_frames(payload.params, frames_count, meta.settings.settle_ms, payload.capture)
        mode = payload.mode if payload.mode in ("overwrite", "append") else "overwrite"
        saved = LABEL_STORE.write_square_frames(
            name, color, payload.square.lower(), frames, mode=mode
        )
    finally:
        LABELING_BUSY["busy"] = False
    return {"saved_frames": saved, **_meta_response(name)}


@app.post("/api/labeling/datasets/{name}/capture-bulk")
def capture_bulk_for_dataset(name: str, payload: LabelingCaptureBulkPayload):
    """Take one (or a few) warped board photos and save per-cell crops for
    every square the caller has labeled.

    The painted-board paradigm: the user places multiple pieces on the board,
    paints each occupied square's color (and optionally marks some empty
    squares), then hits capture. The backend extracts each painted cell from
    the warped image and appends it to ``bulk/<color>/<sq>/`` so the CNN
    dataset builder can pick it up later.
    """
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    if LABELING_BUSY["busy"]:
        raise HTTPException(409, "Labeling capture already running")
    if not payload.labels:
        raise HTTPException(400, "labels is empty — paint at least one square")
    # Normalize and validate labels up front so a bad request fails before we
    # touch the camera.
    norm: dict[str, str] = {}
    for raw_sq, raw_lbl in payload.labels.items():
        sq = str(raw_sq).lower().strip()
        if sq not in LABELING_SQUARES:
            raise HTTPException(400, f"Invalid square in labels: {raw_sq}")
        lbl = str(raw_lbl).lower().strip()
        if lbl not in ("empty", "white", "black"):
            raise HTTPException(400, f"Invalid label for {sq}: {raw_lbl}")
        norm[sq] = lbl

    meta = LABEL_STORE.load(name)
    frames_count = max(1, int(payload.frames or 1))
    settle_ms = (
        int(payload.settle_ms)
        if payload.settle_ms is not None
        else meta.settings.settle_ms
    )
    LABELING_BUSY["busy"] = True
    try:
        # Capture <frames_count> warped board photos. For each, slice into 64
        # cells and append the painted ones.
        labeling_params = payload.params.model_copy(update={"apply_inner_warp": True})
        totals = {"empty": 0, "white": 0, "black": 0}
        for fi in range(frames_count):
            source_path = str(
                _capture_or_resolve_image(labeling_params, capture=payload.capture)
            )
            warped = _warped_board_for_tuning(labeling_params, source_path)
            cells = extract_8x8_cells(warped)
            # Build a square -> cell-image map using the rotated mapping shared
            # by the CNN builder so the crop saved to "a1" is actually a1.
            cells_by_square: dict[str, np.ndarray] = {}
            for cell in cells:
                sq = _rc_to_square(cell.row, cell.col)
                if sq is not None:
                    cells_by_square[sq] = cell.image
            written = LABEL_STORE.write_bulk_cells(name, norm, cells_by_square)
            for k in totals:
                totals[k] += written.get(k, 0)
            if settle_ms > 0 and fi + 1 < frames_count:
                time.sleep(settle_ms / 1000.0)
    finally:
        LABELING_BUSY["busy"] = False
    return {"cells_written": totals, **_meta_response(name)}


@app.post("/api/labeling/datasets/{name}/arm")
def labeling_arm(name: str, payload: LabelingArmPayload):
    """Drive the arm during dataset capture.

    - pickup_source: pick a {color} {piece_type} from the configured source square.
    - place_target: put it on `square`, then home.
    - return_to_source: pick it back from `square`, put it on the source, then home.
    - home: send the arm to its home position and block until it arrives.
    - move_piece: pick from `from_square`, put on `square`, then home.
    - pick_and_place: like move_piece but without the trailing home (caller
      issues `home` separately so the UI can show distinct phases).
    """
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    meta = LABEL_STORE.load(name)
    piece = meta.settings.piece_type
    src = meta.settings.source_square.lower()
    target = payload.square.lower()
    if target not in LABELING_SQUARES:
        raise HTTPException(400, f"Invalid square: {payload.square}")

    action = payload.action
    commands: list[str]
    wait_home_after = False
    if action == "pickup_source":
        commands = [f"pick {piece} {src}"]
    elif action == "place_target":
        # After placing the piece on the target square, send the arm home so
        # captures can be taken reliably with the arm out of the camera view.
        commands = [f"put {piece} {target}", "home"]
        wait_home_after = True
    elif action == "return_to_source":
        commands = [f"pick {piece} {target}", f"put {piece} {src}", "home"]
        wait_home_after = True
    elif action == "home":
        commands = ["home"]
        wait_home_after = True
    elif action == "move_piece":
        from_square = payload.from_square
        if not from_square:
            raise HTTPException(400, "from_square is required for move_piece")
        commands = [f"pick {piece} {from_square.lower()}", f"put {piece} {target}", "home"]
        wait_home_after = True
    elif action == "pick_and_place":
        # Like `move_piece` but without the trailing `home`. Use this when the
        # caller will issue `home` as a separate step (e.g. so the UI can show
        # an explicit "homing" phase between move and capture).
        from_square = payload.from_square
        if not from_square:
            raise HTTPException(400, "from_square is required for pick_and_place")
        commands = [f"pick {piece} {from_square.lower()}", f"put {piece} {target}"]
    else:
        raise HTTPException(400, f"Unknown action: {action}")

    try:
        responses = _send_motion(commands, payload.port, payload.baud)
        # The Arduino's `home` command (like `pick`/`put`) blocks on stepper
        # motion and only prints its trailing `Position:` line once the move
        # is finished — `_send_motion` waits for that marker per command, so
        # by the time we're here the arm has stopped. Verify it actually
        # parked at home before letting the caller capture frames.
        if wait_home_after:
            _verify_arm_home(responses, payload.port, payload.baud)
    except HTTPException:
        raise
    except Exception as e:
        robot_adapter.close()
        raise HTTPException(500, str(e))
    return {
        "status": "ok",
        "action": action,
        "commands": commands,
        "responses": responses,
    }


@app.post("/api/labeling/datasets/{name}/compute-stats")
def compute_dataset_stats(name: str, payload: Optional[PipelineParams] = None):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    params = payload or PipelineParams()

    def _extract_cells(warped: np.ndarray):
        x_lines, y_lines = detect_8x8_grid_lines(warped)
        return extract_8x8_cells(warped, x_lines, y_lines)

    config = build_exemplar_config(
        dataset_name=name,
        extract_cells_fn=_extract_cells,
        iter_empty_frames=lambda: LABEL_STORE.iter_empty_frames(name),
        iter_square_frames=lambda color, sq: LABEL_STORE.iter_square_frames(name, color, sq),
    )
    config_path = LABEL_STORE.dataset_dir(name) / "exemplar_config.json"
    config.save(config_path)

    accuracy = leave_one_out_accuracy(config)
    accuracy_path = LABEL_STORE.dataset_dir(name) / "accuracy.json"
    accuracy_json = {
        "squares": {k: v.to_json() for k, v in accuracy.items()},
        "overall": {
            "total": sum(a.total for a in accuracy.values()),
            "correct": sum(a.correct for a in accuracy.values()),
        },
    }
    accuracy_json["overall"]["accuracy"] = (
        accuracy_json["overall"]["correct"] / accuracy_json["overall"]["total"]
        if accuracy_json["overall"]["total"]
        else 0.0
    )
    accuracy_path.write_text(json.dumps(accuracy_json, indent=2))

    meta = LABEL_STORE.load(name)
    meta.has_exemplar_config = True
    meta.has_accuracy = True
    LABEL_STORE.save(meta)

    return {
        "metadata": meta.to_json(),
        "accuracy": accuracy_json,
        "exemplar_config_path": str(config_path),
    }


class LabelingActivatePayload(BaseModel):
    name: Optional[str] = None


@app.get("/api/labeling/active")
def get_active_classifier():
    name = _load_active_classifier_pointer()
    if not name or not LABEL_STORE.exists(name):
        return {"active": False, "name": None, "has_config": False}
    cfg_path = LABEL_STORE.dataset_dir(name) / "exemplar_config.json"
    return {
        "active": True,
        "name": name,
        "has_config": cfg_path.exists(),
        "config_path": str(cfg_path) if cfg_path.exists() else None,
    }


@app.put("/api/labeling/active")
def set_active_classifier(payload: LabelingActivatePayload):
    """Activate (or, when name is null/empty, deactivate) a dataset's classifier."""
    if not payload.name:
        _save_active_classifier_pointer(None)
        _ACTIVE_CACHE.update({"name": None, "mtime": 0.0, "config": None})
        return {"active": False, "name": None}
    if not LABEL_STORE.exists(payload.name):
        raise HTTPException(404, f"Dataset not found: {payload.name}")
    cfg_path = LABEL_STORE.dataset_dir(payload.name) / "exemplar_config.json"
    if not cfg_path.exists():
        raise HTTPException(
            400,
            f"Dataset {payload.name} has no exemplar_config.json — run compute-stats first.",
        )
    _save_active_classifier_pointer(payload.name)
    _ACTIVE_CACHE.update({"name": None, "mtime": 0.0, "config": None})
    return {"active": True, "name": payload.name, "config_path": str(cfg_path)}


@app.delete("/api/labeling/active")
def clear_active_classifier():
    _save_active_classifier_pointer(None)
    _ACTIVE_CACHE.update({"name": None, "mtime": 0.0, "config": None})
    return {"active": False, "name": None}


@app.get("/api/labeling/datasets/{name}/accuracy")
def get_dataset_accuracy(name: str):
    if not LABEL_STORE.exists(name):
        raise HTTPException(404, f"Dataset not found: {name}")
    accuracy_path = LABEL_STORE.dataset_dir(name) / "accuracy.json"
    if not accuracy_path.exists():
        return {"exists": False, "accuracy": None}
    return {"exists": True, "accuracy": json.loads(accuracy_path.read_text())}


# ============================================================================
# CNN classifier — calibration preflight, dataset build, training, inference.
# All routes live under /api/cnn/* and /api/calibration/status. See
# prompt.md for the contract.
# ============================================================================

import threading
import uuid
import urllib.request
import urllib.error


@app.get("/api/calibration/status")
def get_calibration_status():
    """Preflight badges for the CNN wizard.

    Returns presence of both calibration JSONs, ESP32-CAM reachability,
    and how old the board calibration is in seconds.
    """
    board_present = BOARD_CAL_PATH.exists()
    inner_present = INNER_CAL_PATH.exists()

    age: Optional[float] = None
    if board_present:
        try:
            age = max(0.0, time.time() - BOARD_CAL_PATH.stat().st_mtime)
        except OSError:
            age = None

    reachable = False
    try:
        from charm.vision.transferphoto import ESP32_URL
        req = urllib.request.Request(ESP32_URL, method="HEAD")
        with urllib.request.urlopen(req, timeout=2):
            reachable = True
    except Exception:
        # Some ESP32-CAM firmware doesn't answer HEAD; fall back to GET with
        # a tiny timeout so we don't pull the whole frame.
        try:
            from charm.vision.transferphoto import ESP32_URL
            with urllib.request.urlopen(ESP32_URL, timeout=2) as resp:
                resp.read(64)
                reachable = True
        except Exception:
            reachable = False

    return {
        "board_calibration_present": board_present,
        "inner_warp_present": inner_present,
        "camera_reachable": reachable,
        "board_calibration_age_seconds": age,
    }


# ----------------------------------------------------------------------------
# CNN dataset build (Phase 2)
# ----------------------------------------------------------------------------

CNN_MODELS_DIR = PYTHON_CODE_DIR / "models"
CNN_ACTIVE_POINTER = CNN_MODELS_DIR / "active.json"

_CNN_BUILD_JOBS: dict[str, dict] = {}
_CNN_BUILD_LOCK = threading.Lock()


class CnnBuildDatasetPayload(BaseModel):
    source: str
    output: str
    val_split: float = 0.15


@app.get("/api/cnn/source-datasets")
def cnn_list_source_datasets():
    """List labeled_datasets entries (excluding cnn_*) with frame counts."""
    out = []
    if not LABELED_DATASETS_DIR.exists():
        return {"datasets": []}
    for child in sorted(LABELED_DATASETS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("cnn_"):
            continue
        empty_dir = child / "empty"
        white_dir = child / "white"
        black_dir = child / "black"
        bulk_dir = child / "bulk"
        empty_frames = sum(1 for _ in empty_dir.glob("*.jpg")) if empty_dir.exists() else 0
        white_squares = sum(1 for d in white_dir.iterdir() if d.is_dir()) if white_dir.exists() else 0
        black_squares = sum(1 for d in black_dir.iterdir() if d.is_dir()) if black_dir.exists() else 0
        white_frames = (
            sum(1 for d in white_dir.iterdir() if d.is_dir() for _ in d.glob("*.jpg"))
            if white_dir.exists() else 0
        )
        black_frames = (
            sum(1 for d in black_dir.iterdir() if d.is_dir() for _ in d.glob("*.jpg"))
            if black_dir.exists() else 0
        )
        bulk_cells = {"empty": 0, "white": 0, "black": 0}
        if bulk_dir.exists():
            for cls in ("empty", "white", "black"):
                cls_dir = bulk_dir / cls
                if cls_dir.exists():
                    bulk_cells[cls] = sum(
                        1 for d in cls_dir.iterdir() if d.is_dir() for _ in d.glob("*.jpg")
                    )
        out.append({
            "name": child.name,
            "empty_frames": empty_frames,
            "white_squares": white_squares,
            "white_frames": white_frames,
            "black_squares": black_squares,
            "black_frames": black_frames,
            "bulk_empty_cells": bulk_cells["empty"],
            "bulk_white_cells": bulk_cells["white"],
            "bulk_black_cells": bulk_cells["black"],
            "total_frames": (
                empty_frames + white_frames + black_frames
                + bulk_cells["empty"] + bulk_cells["white"] + bulk_cells["black"]
            ),
        })
    return {"datasets": out}


@app.post("/api/cnn/build-dataset")
def cnn_build_dataset(payload: CnnBuildDatasetPayload):
    from charm.vision.cnn_dataset import build_cnn_dataset, CnnBuildProgress

    source_dir = LABELED_DATASETS_DIR / payload.source
    if not source_dir.exists():
        raise HTTPException(404, f"Source dataset not found: {payload.source}")

    # Note: calibration is intentionally not required here. The labeling pipeline
    # stores pre-warped 800x800 frames, so build_cnn_dataset goes straight to
    # grid splitting and never reads board_calibration.json / inner_warp_calibration.json.
    # Calibration is only needed for live scanning (step 5 of the wizard).

    build_id = uuid.uuid4().hex[:12]
    with _CNN_BUILD_LOCK:
        _CNN_BUILD_JOBS[build_id] = {
            "frames_done": 0,
            "frames_total": 0,
            "current_file": "",
            "cells_written_by_class": {"empty": 0, "white": 0, "black": 0},
            "finished": False,
            "error": None,
            "report": None,
            "started_at": time.time(),
        }

    def _progress(p: CnnBuildProgress) -> None:
        with _CNN_BUILD_LOCK:
            _CNN_BUILD_JOBS[build_id].update({
                "frames_done": p.frames_done,
                "frames_total": p.frames_total,
                "current_file": p.current_file,
                "cells_written_by_class": dict(p.cells_written_by_class),
            })

    def _run() -> None:
        try:
            report = build_cnn_dataset(
                source_dataset_name=payload.source,
                output_dataset_name=payload.output,
                val_split=payload.val_split,
                progress_cb=_progress,
            )
            with _CNN_BUILD_LOCK:
                _CNN_BUILD_JOBS[build_id]["finished"] = True
                _CNN_BUILD_JOBS[build_id]["report"] = {
                    "output_dir": str(report.output_dir),
                    "counts_train": report.counts_train,
                    "counts_val": report.counts_val,
                }
        except Exception as exc:  # noqa: BLE001
            with _CNN_BUILD_LOCK:
                _CNN_BUILD_JOBS[build_id]["finished"] = True
                _CNN_BUILD_JOBS[build_id]["error"] = str(exc)

    threading.Thread(target=_run, daemon=True).start()
    return {"build_id": build_id}


@app.get("/api/cnn/build-status/{build_id}")
def cnn_build_status(build_id: str):
    with _CNN_BUILD_LOCK:
        job = _CNN_BUILD_JOBS.get(build_id)
        if job is None:
            raise HTTPException(404, f"Build job not found: {build_id}")
        return dict(job)


@app.get("/api/cnn/dataset-preview/{output_name}")
def cnn_dataset_preview(output_name: str, per_class: int = 9):
    """Return up to `per_class` random crops per class as base64."""
    import random

    out_dir = LABELED_DATASETS_DIR / output_name
    if not out_dir.exists():
        raise HTTPException(404, f"Dataset not found: {output_name}")

    preview: dict[str, list[str]] = {}
    for split in ("train", "val"):
        for cls in ("empty", "white", "black"):
            cls_dir = out_dir / split / cls
            if not cls_dir.exists():
                continue
            files = list(cls_dir.glob("*.png"))
            if not files:
                continue
            sampled = random.sample(files, min(per_class, len(files)))
            key = f"{split}_{cls}"
            preview[key] = []
            for f in sampled:
                img = cv2.imread(str(f))
                if img is None:
                    continue
                preview[key].append(to_b64(img))
    return {"preview": preview}


# ----------------------------------------------------------------------------
# CNN training (Phase 3)
# ----------------------------------------------------------------------------

_CNN_TRAIN_JOBS: dict[str, dict] = {}
_CNN_TRAIN_LOCK = threading.Lock()


class CnnTrainPayload(BaseModel):
    dataset: str
    epochs: int = 20
    batch_size: int = 32


@app.post("/api/cnn/train")
def cnn_train(payload: CnnTrainPayload):
    dataset_dir = LABELED_DATASETS_DIR / payload.dataset
    if not dataset_dir.exists():
        raise HTTPException(404, f"Dataset not found: {payload.dataset}")
    if not (dataset_dir / "train").exists() or not (dataset_dir / "val").exists():
        raise HTTPException(400, f"Dataset {payload.dataset} has no train/ or val/ subdirs — run build-dataset first.")

    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    job_id = uuid.uuid4().hex[:12]

    with _CNN_TRAIN_LOCK:
        _CNN_TRAIN_JOBS[job_id] = {
            "run_id": run_id,
            "dataset": payload.dataset,
            "epoch": 0,
            "total_epochs": payload.epochs,
            "train_loss": None,
            "train_acc": None,
            "val_loss": None,
            "val_acc": None,
            "finished": False,
            "error": None,
            "started_at": time.time(),
        }

    def _run() -> None:
        try:
            from train_cnn import train  # python_code/train_cnn.py
        except Exception as exc:  # noqa: BLE001
            with _CNN_TRAIN_LOCK:
                _CNN_TRAIN_JOBS[job_id]["finished"] = True
                _CNN_TRAIN_JOBS[job_id]["error"] = f"train_cnn import failed: {exc}"
            return

        def _epoch_cb(snapshot: dict) -> None:
            with _CNN_TRAIN_LOCK:
                _CNN_TRAIN_JOBS[job_id].update(snapshot)

        try:
            train(
                dataset=payload.dataset,
                epochs=payload.epochs,
                batch_size=payload.batch_size,
                run_id=run_id,
                on_epoch_end=_epoch_cb,
            )
            with _CNN_TRAIN_LOCK:
                _CNN_TRAIN_JOBS[job_id]["finished"] = True
        except Exception as exc:  # noqa: BLE001
            with _CNN_TRAIN_LOCK:
                _CNN_TRAIN_JOBS[job_id]["finished"] = True
                _CNN_TRAIN_JOBS[job_id]["error"] = str(exc)

    # train_cnn.py lives at python_code/train_cnn.py — make sure it's importable.
    if str(PYTHON_CODE_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_CODE_DIR))

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "run_id": run_id}


@app.get("/api/cnn/train-status/{job_id}")
def cnn_train_status(job_id: str):
    with _CNN_TRAIN_LOCK:
        job = _CNN_TRAIN_JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, f"Train job not found: {job_id}")
        return dict(job)


@app.get("/api/cnn/train-artifacts/{run_id}")
def cnn_train_artifacts(run_id: str):
    run_dir = CNN_MODELS_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(404, f"Run not found: {run_id}")

    def _b64_png(path: Path) -> Optional[str]:
        if not path.exists():
            return None
        return base64.b64encode(path.read_bytes()).decode()

    metrics: Optional[dict] = None
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text())
        except Exception:
            metrics = None

    return {
        "run_id": run_id,
        "training_curves_png": _b64_png(run_dir / "training_curves.png"),
        "confusion_matrix_png": _b64_png(run_dir / "confusion_matrix.png"),
        "metrics": metrics,
    }


@app.get("/api/cnn/models")
def cnn_list_models():
    out = []
    if not CNN_MODELS_DIR.exists():
        return {"models": []}
    for run_dir in sorted(CNN_MODELS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "metrics.json"
        keras_path = run_dir / "chess_cnn.keras"
        if not keras_path.exists():
            continue
        info: dict = {
            "run_id": run_dir.name,
            "finished_at": keras_path.stat().st_mtime,
            "val_acc": None,
            "dataset": None,
        }
        if meta_path.exists():
            try:
                m = json.loads(meta_path.read_text())
                info["val_acc"] = m.get("val_acc")
                info["dataset"] = m.get("dataset")
            except Exception:
                pass
        out.append(info)
    return {"models": out}


class CnnActivatePayload(BaseModel):
    run_id: str


@app.post("/api/cnn/activate-model")
def cnn_activate_model(payload: CnnActivatePayload):
    run_dir = CNN_MODELS_DIR / payload.run_id
    keras_path = run_dir / "chess_cnn.keras"
    if not keras_path.exists():
        raise HTTPException(404, f"Model not found for run: {payload.run_id}")
    CNN_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    CNN_ACTIVE_POINTER.write_text(json.dumps({"run_id": payload.run_id, "activated_at": time.time()}, indent=2))
    # Drop the cached classifier so the next /scan reloads.
    global _ACTIVE_CNN_CLASSIFIER, _ACTIVE_CNN_RUN_ID
    _ACTIVE_CNN_CLASSIFIER = None
    _ACTIVE_CNN_RUN_ID = None
    return {"run_id": payload.run_id, "active": True}


# ----------------------------------------------------------------------------
# CNN inference (Phase 4)
# ----------------------------------------------------------------------------

_ACTIVE_CNN_CLASSIFIER = None  # CnnBoardClassifier or None
_ACTIVE_CNN_RUN_ID: Optional[str] = None
_LAST_CNN_SCAN: dict = {}  # crops + predictions for /scan-cell drill-down


def _read_active_cnn_run_id() -> Optional[str]:
    if not CNN_ACTIVE_POINTER.exists():
        return None
    try:
        return json.loads(CNN_ACTIVE_POINTER.read_text()).get("run_id")
    except Exception:
        return None


def _load_active_cnn_classifier():
    """Return the active CnnBoardClassifier, loading it on demand."""
    global _ACTIVE_CNN_CLASSIFIER, _ACTIVE_CNN_RUN_ID
    run_id = _read_active_cnn_run_id()
    if not run_id:
        _ACTIVE_CNN_CLASSIFIER = None
        _ACTIVE_CNN_RUN_ID = None
        return None
    if _ACTIVE_CNN_CLASSIFIER is not None and _ACTIVE_CNN_RUN_ID == run_id:
        return _ACTIVE_CNN_CLASSIFIER

    from charm.vision.cnn_classifier import CnnBoardClassifier
    run_dir = CNN_MODELS_DIR / run_id
    model_path = run_dir / "chess_cnn.keras"
    indices_path = run_dir / "class_indices.json"
    if not model_path.exists() or not indices_path.exists():
        _ACTIVE_CNN_CLASSIFIER = None
        _ACTIVE_CNN_RUN_ID = None
        return None
    _ACTIVE_CNN_CLASSIFIER = CnnBoardClassifier(str(model_path), str(indices_path))
    _ACTIVE_CNN_RUN_ID = run_id
    return _ACTIVE_CNN_CLASSIFIER


def _run_cnn_game_scan(raw_path: Path) -> tuple[list, list, dict]:
    """Warp raw image, classify with active CNN, return (white_bitmap, black_bitmap, pipeline_dict).

    pipeline_dict is compatible with _game_session_payload's 'pipeline' field and
    contains the CNN overlay instead of the classical debug images.
    """
    if not BOARD_CAL_PATH.exists() or not INNER_CAL_PATH.exists():
        raise HTTPException(400, "Board calibration missing — calibrate the board first.")

    raw = cv2.imread(str(raw_path))
    if raw is None:
        raise HTTPException(400, f"Could not read image: {raw_path}")

    board_cal = load_four_point_calibration(BOARD_CAL_PATH)
    inner_cal = load_inner_warp_calibration(str(INNER_CAL_PATH))
    first_warp = warp_from_calibration(raw, board_cal, output_size=800)
    refined = refine_board_with_inner_corners(first_warp, inner_cal, output_size=800)

    cv2.imwrite(str(LATEST_CALIBRATED_PATH), refined)

    classifier = _load_active_cnn_classifier()
    if classifier is None:
        raise HTTPException(400, "No active CNN model — activate one from the CNN lab first.")

    cells = extract_8x8_cells(refined)
    result = classifier.classify_cells(cells)

    overlay = refined.copy()
    label_color = {"empty": (160, 160, 160), "white": (255, 255, 255), "black": (40, 40, 40)}
    for pred in result.predictions:
        x = pred.col * (overlay.shape[1] // 8) + 4
        y = pred.row * (overlay.shape[0] // 8) + 20
        cv2.putText(
            overlay,
            f"{pred.label[0].upper()} {pred.confidence:.2f}",
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.38,
            label_color.get(pred.label, (200, 200, 200)),
            1, cv2.LINE_AA,
        )

    pipeline_dict: dict = {
        "image_path": str(raw_path),
        "refined_warp": to_b64(refined),
        "cnn_overlay": to_b64(overlay),
        "white_bitmap": result.white_bitmap,
        "black_bitmap": result.black_bitmap,
        "cnn_active": True,
        "inference_ms": result.inference_ms,
    }
    return result.white_bitmap, result.black_bitmap, pipeline_dict


@app.get("/api/cnn/active-model")
def cnn_active_model():
    run_id = _read_active_cnn_run_id()
    if not run_id:
        return {"run_id": None, "val_acc": None, "dataset": None, "loaded": False}

    info: dict = {"run_id": run_id, "val_acc": None, "dataset": None, "loaded": False}
    metrics_path = CNN_MODELS_DIR / run_id / "metrics.json"
    if metrics_path.exists():
        try:
            m = json.loads(metrics_path.read_text())
            info["val_acc"] = m.get("val_acc")
            info["dataset"] = m.get("dataset")
        except Exception:
            pass
    try:
        info["loaded"] = _load_active_cnn_classifier() is not None
    except Exception:
        info["loaded"] = False
    return info


class CnnScanPayload(BaseModel):
    capture: bool = True
    compare_classical: bool = True


@app.post("/api/cnn/scan")
def cnn_scan(payload: CnnScanPayload):
    classifier = _load_active_cnn_classifier()
    if classifier is None:
        raise HTTPException(400, "No active CNN model. Activate one from /api/cnn/models.")

    if not BOARD_CAL_PATH.exists() or not INNER_CAL_PATH.exists():
        raise HTTPException(400, "Calibrations missing — calibrate the board first.")

    # 1) capture or use latest raw
    if payload.capture:
        from charm.vision.transferphoto import fetch_raw_image
        raw_path = Path(fetch_raw_image())
    else:
        raw_path = resolve_latest_raw_path()
        if not raw_path.exists():
            raise HTTPException(400, "No latest raw image on disk — pass capture=true.")

    raw = cv2.imread(str(raw_path))
    if raw is None:
        raise HTTPException(500, f"Could not read raw image: {raw_path}")

    # 2) two-stage warp
    board_cal = load_four_point_calibration(BOARD_CAL_PATH)
    inner_cal = load_inner_warp_calibration(INNER_CAL_PATH)
    first_warp = warp_from_calibration(raw, board_cal, output_size=800)
    refined = refine_board_with_inner_corners(first_warp, inner_cal, output_size=800)

    # 3) split + classify
    cells = extract_8x8_cells(refined)
    result = classifier.classify_cells(cells)

    # 4) build overlay with grid + labels
    overlay = refined.copy()
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1] - 1, overlay.shape[0] - 1), (60, 60, 60), 1)
    for i in range(1, 8):
        x = i * (overlay.shape[1] // 8)
        y = i * (overlay.shape[0] // 8)
        cv2.line(overlay, (x, 0), (x, overlay.shape[0]), (60, 60, 60), 1)
        cv2.line(overlay, (0, y), (overlay.shape[1], y), (60, 60, 60), 1)
    label_color = {"empty": (160, 160, 160), "white": (255, 255, 255), "black": (40, 40, 40)}
    for pred in result.predictions:
        x = pred.col * (overlay.shape[1] // 8) + 6
        y = pred.row * (overlay.shape[0] // 8) + 22
        cv2.putText(
            overlay,
            f"{pred.label[0].upper()} {pred.confidence:.2f}",
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            label_color.get(pred.label, (200, 200, 200)),
            1,
            cv2.LINE_AA,
        )

    # 5) cell crops in row-major order
    cell_crops_b64 = [to_b64(cell.image) for cell in sorted(cells, key=lambda c: (c.row, c.col))]

    response: dict = {
        "white_bitmap": result.white_bitmap,
        "black_bitmap": result.black_bitmap,
        "predictions": [
            {
                "row": p.row,
                "col": p.col,
                "label": p.label,
                "confidence": p.confidence,
                "probs": p.probs,
            }
            for p in result.predictions
        ],
        "warped_board_b64": to_b64(refined),
        "cnn_overlay_b64": to_b64(overlay),
        "cell_crops_b64": cell_crops_b64,
        "inference_ms": result.inference_ms,
        "classical_comparison": None,
    }

    # 6) optional classical comparison
    if payload.compare_classical:
        try:
            from charm.utils.bitmap import build_white_black_bitmaps
            ref_img = cv2.imread(str(EMPTY_REF_PATH)) if EMPTY_REF_PATH.exists() else None
            reference_cells = None
            if ref_img is not None:
                if ref_img.shape[:2] != refined.shape[:2]:
                    ref_img = cv2.resize(ref_img, (refined.shape[1], refined.shape[0]))
                reference_cells = extract_8x8_cells(ref_img)
            occupancy = detect_occupancy(cells, reference_cells=reference_cells)
            from charm.vision.piece_color_detector import detect_piece_colors
            colors = detect_piece_colors(cells, occupancy, reference_cells=reference_cells)
            cl_white, cl_black = build_white_black_bitmaps(colors)
            disagreements = []
            for r in range(8):
                for c in range(8):
                    cnn_label = "empty"
                    if result.white_bitmap[r][c]:
                        cnn_label = "white"
                    elif result.black_bitmap[r][c]:
                        cnn_label = "black"
                    cl_label = "empty"
                    if cl_white[r][c]:
                        cl_label = "white"
                    elif cl_black[r][c]:
                        cl_label = "black"
                    if cnn_label != cl_label:
                        disagreements.append({
                            "row": r, "col": c, "cnn": cnn_label, "classical": cl_label,
                        })
            response["classical_comparison"] = {
                "white_bitmap": cl_white,
                "black_bitmap": cl_black,
                "disagreement_count": len(disagreements),
                "disagreement_cells": disagreements,
            }
        except Exception as exc:  # noqa: BLE001 — comparison is optional
            response["classical_comparison"] = {"error": str(exc)}

    # cache for /scan-cell
    global _LAST_CNN_SCAN
    _LAST_CNN_SCAN = {
        "cell_crops_b64": cell_crops_b64,
        "predictions": response["predictions"],
        "captured_at": time.time(),
    }

    return response


@app.get("/api/cnn/scan-cell/{row}/{col}")
def cnn_scan_cell(row: int, col: int):
    if not (0 <= row < 8 and 0 <= col < 8):
        raise HTTPException(400, "row and col must be in [0, 8)")
    if not _LAST_CNN_SCAN:
        raise HTTPException(400, "No scan in cache — call POST /api/cnn/scan first.")
    idx = row * 8 + col
    crops = _LAST_CNN_SCAN.get("cell_crops_b64") or []
    preds = _LAST_CNN_SCAN.get("predictions") or []
    if idx >= len(crops) or idx >= len(preds):
        raise HTTPException(500, "Scan cache is incomplete.")
    return {
        "row": row,
        "col": col,
        "crop_b64": crops[idx],
        "prediction": preds[idx],
        "captured_at": _LAST_CNN_SCAN.get("captured_at"),
    }


class CnnFeedbackPayload(BaseModel):
    run_id: str
    row: int
    col: int
    true_label: str
    crop_b64: Optional[str] = None


@app.post("/api/cnn/feedback")
def cnn_feedback(payload: CnnFeedbackPayload):
    """Record a "this prediction was wrong" correction by writing the cell
    crop as a bulk-paint cell back into the source labeling dataset.

    The next CNN dataset build will pick it up automatically (the builder
    iterates ``bulk/<class>/<sq>/`` and copies each cell into train/val).
    Falls back to the legacy jsonl queue when the source can't be resolved
    (e.g. a model trained before source.json existed) so feedback is never
    silently dropped.
    """
    if payload.true_label not in {"empty", "white", "black"}:
        raise HTTPException(400, "true_label must be one of empty/white/black")

    run_id = payload.run_id
    # 1) run_id → cnn_<name> via metrics.json
    metrics_path = CNN_MODELS_DIR / run_id / "metrics.json"
    cnn_dataset = None
    if metrics_path.exists():
        try:
            cnn_dataset = json.loads(metrics_path.read_text()).get("dataset")
        except Exception:
            cnn_dataset = None
    if not cnn_dataset:
        raise HTTPException(404, f"Cannot resolve dataset for run {run_id}")

    # 2) cnn_<name> → source labeling dataset via source.json (written by
    #    build_cnn_dataset). Older runs may not have this — fall back to a
    #    jsonl queue so we don't lose the correction.
    source_json = LABELED_DATASETS_DIR / cnn_dataset / "source.json"
    source_name = None
    if source_json.exists():
        try:
            source_name = json.loads(source_json.read_text()).get("source_dataset")
        except Exception:
            source_name = None

    sq = _rc_to_square(payload.row, payload.col)
    if not sq:
        raise HTTPException(400, f"Invalid cell row={payload.row} col={payload.col}")

    # Decode the 100x100 crop from the scan panel. The frontend always sends
    # one — but be defensive in case it doesn't.
    crop_img = None
    if payload.crop_b64:
        try:
            import base64
            raw = base64.b64decode(payload.crop_b64)
            arr = np.frombuffer(raw, dtype=np.uint8)
            crop_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            crop_img = None

    if source_name and LABEL_STORE.exists(source_name) and crop_img is not None:
        # Append the crop as a single-cell bulk entry so the next CNN build
        # consumes it. Same path as the bulk-paint capture flow.
        labels = {sq: payload.true_label}
        written = LABEL_STORE.write_bulk_cells(
            source_name, labels, {sq: crop_img}
        )
        return {
            "queued": False,
            "appended_to_source": True,
            "source_dataset": source_name,
            "square": sq,
            "true_label": payload.true_label,
            "cells_written": written,
        }

    # Fallback path: keep the legacy jsonl queue so corrections aren't lost
    # when the cnn dataset has no source link or the crop was missing.
    queue_path = LABELED_DATASETS_DIR / cnn_dataset / "retrain_queue.jsonl"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "row": payload.row,
        "col": payload.col,
        "square": sq,
        "true_label": payload.true_label,
        "crop_b64": payload.crop_b64,
        "ts": time.time(),
    }
    with queue_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return {
        "queued": True,
        "queue_path": str(queue_path),
        "reason": (
            "source dataset not resolvable — rebuild the CNN dataset to get a "
            "source.json link, then future feedback will append directly."
        ),
    }


# ───────────────────────────────────────────────────────────────────────────
# In-process LCD controller
# ───────────────────────────────────────────────────────────────────────────
# The webapp button POSTs to /api/controller/start which spins up an
# ArduinoUIControllerLink + GameController inside this server. They share
# the global _GAME_SESSION and the robot_adapter serial connection/lock,
# so the LCD and the webapp can drive the game without serial collisions.

_CONTROLLER_LOCK = threading.Lock()
_CONTROLLER_STATE: dict = {
    "controller": None,      # GameController | None
    "ui_link": None,         # ArduinoUIControllerLink | None
    "started_at": None,      # epoch seconds
    "esp32": None,           # {host, port}
    "arm_port": None,        # str | None
    "last_error": None,      # str | None — set if start failed
    "phase": "idle",
    "phase_error": None,
    "bot_move": None,
    "phase_updated_at": None,
}


def _controller_is_running() -> bool:
    return _CONTROLLER_STATE["controller"] is not None


# Kept for backwards compatibility with old call sites.
def _controller_subprocess_running() -> bool:
    return _controller_is_running()


def _on_phase_change(phase: str, error_message: Optional[str], bot_move: Optional[str]) -> None:
    _CONTROLLER_STATE["phase"] = phase
    _CONTROLLER_STATE["phase_error"] = error_message
    _CONTROLLER_STATE["bot_move"] = bot_move
    _CONTROLLER_STATE["phase_updated_at"] = time.time()


class ControllerStartPayload(BaseModel):
    esp32_host: str = "172.21.70.102"
    esp32_port: int = 8765
    arm_port: Optional[str] = None
    player_color: Literal["white", "black"] = "white"
    difficulty: int = Field(10, ge=1, le=20)
    flip_180: bool = False
    engine_path: str = "stockfish"
    think_time: float = 0.5
    baud: int = ROBOT_BAUD_DEFAULT


@app.post("/api/controller/start")
def controller_start(payload: ControllerStartPayload):
    with _CONTROLLER_LOCK:
        if _controller_is_running():
            started_at = _CONTROLLER_STATE["started_at"]
            raise HTTPException(409, f"Controller already running (started at {started_at})")

        resolved_arm_port = payload.arm_port
        if resolved_arm_port and not Path(resolved_arm_port).exists():
            resolved_arm_port = None
        if resolved_arm_port is None:
            resolved_arm_port = robot_adapter.connected_port() or robot_adapter.find_port()

        # Acquire shared serial+lock from robot_adapter so the LCD-driven
        # arm commands and webapp arm commands serialize on the same lock.
        try:
            arm_ser, arm_lock = robot_adapter.acquire_arm(resolved_arm_port, payload.baud)
        except Exception as exc:
            _CONTROLLER_STATE["last_error"] = f"Arm serial open failed: {exc}"
            raise HTTPException(500, _CONTROLLER_STATE["last_error"]) from exc

        try:
            ui_link = ArduinoUIControllerLink(
                host=payload.esp32_host,
                port=payload.esp32_port,
                on_line=lambda line: print(f"[ESP32] {line}", flush=True),
            )
        except Exception as exc:
            _CONTROLLER_STATE["last_error"] = f"ESP32 TCP connect failed: {exc}"
            raise HTTPException(502, _CONTROLLER_STATE["last_error"]) from exc

        config = GameControllerConfig(
            board_image_provider=lambda: str(LATEST_CALIBRATED_PATH),
            arm_ser=arm_ser,
            arm_lock=arm_lock,
            player_color=payload.player_color,
            flip_180=payload.flip_180,
            engine_path=_resolve_stockfish_path(payload.engine_path),
            think_time=payload.think_time,
            on_phase_change=_on_phase_change,
            write_state_file=False,
        )

        controller = GameController(ui_link=ui_link, session=_GAME_SESSION, config=config)
        controller.set_difficulty(payload.difficulty)
        try:
            controller.start()
        except Exception as exc:
            try:
                ui_link.close()
            except Exception:
                pass
            _CONTROLLER_STATE["last_error"] = f"Controller start failed: {exc}"
            raise HTTPException(500, _CONTROLLER_STATE["last_error"]) from exc

        _CONTROLLER_STATE["controller"] = controller
        _CONTROLLER_STATE["ui_link"] = ui_link
        _CONTROLLER_STATE["started_at"] = time.time()
        _CONTROLLER_STATE["esp32"] = {"host": payload.esp32_host, "port": payload.esp32_port}
        _CONTROLLER_STATE["arm_port"] = resolved_arm_port
        _CONTROLLER_STATE["last_error"] = None
        # GameController.start() already wrote "waiting" via _write_state.
        return {
            "running": True,
            "started_at": _CONTROLLER_STATE["started_at"],
            "esp32_host": payload.esp32_host,
            "esp32_port": payload.esp32_port,
            "arm_port": resolved_arm_port,
        }


@app.get("/api/controller/status")
def controller_status():
    running = _controller_is_running()
    return {
        "running": running,
        "started_at": _CONTROLLER_STATE["started_at"] if running else None,
        "esp32_host": (_CONTROLLER_STATE["esp32"] or {}).get("host") if running else None,
        "esp32_port": (_CONTROLLER_STATE["esp32"] or {}).get("port") if running else None,
        "arm_port": _CONTROLLER_STATE["arm_port"] if running else None,
        "phase": _CONTROLLER_STATE["phase"] if running else "idle",
        "phase_updated_at": _CONTROLLER_STATE["phase_updated_at"] if running else None,
        "last_error": _CONTROLLER_STATE["last_error"],
        # Field kept for client compatibility — empty since we no longer
        # tail a subprocess.
        "log_tail": [],
    }


@app.get("/api/controller/game-state")
def controller_game_state():
    """Live game state surfaced by the in-process GameController.

    Reads from the shared _GAME_SESSION + GameController phase, so the LCD
    and webapp always agree on what the current board, moves, and phase are.
    """
    running = _controller_is_running()
    controller: Optional[GameController] = _CONTROLLER_STATE["controller"]
    board = _GAME_SESSION.get_current_board()
    base = {
        "phase": _CONTROLLER_STATE["phase"] if running else "idle",
        "fen": board.fen() if board is not None else None,
        "moves": _GAME_SESSION.get_move_history(),
        "player_color": _GAME_SESSION.get_player_color(),
        "robot_color": _GAME_SESSION.get_robot_color(),
        "difficulty": controller.current_difficulty if controller is not None else None,
        "error_message": _CONTROLLER_STATE["phase_error"],
        "bot_move": _CONTROLLER_STATE["bot_move"],
        "updated_at": _CONTROLLER_STATE["phase_updated_at"],
    }
    if not running:
        # Surface an idle snapshot but keep the shared session state
        # visible so the dashboard board stays in sync after a stop.
        base["phase"] = "idle"
    return base


@app.post("/api/controller/stop")
def controller_stop():
    with _CONTROLLER_LOCK:
        controller: Optional[GameController] = _CONTROLLER_STATE["controller"]
        ui_link: Optional[ArduinoUIControllerLink] = _CONTROLLER_STATE["ui_link"]
        if controller is None:
            _CONTROLLER_STATE["phase"] = "idle"
            return {"running": False}

        try:
            controller.stop()
        except Exception as exc:
            print(f"[controller] stop raised: {exc!r}", flush=True)
        finally:
            try:
                if ui_link is not None:
                    ui_link.close()
            except Exception:
                pass

        _CONTROLLER_STATE["controller"] = None
        _CONTROLLER_STATE["ui_link"] = None
        _CONTROLLER_STATE["started_at"] = None
        _CONTROLLER_STATE["esp32"] = None
        _CONTROLLER_STATE["arm_port"] = None
        _CONTROLLER_STATE["phase"] = "idle"
        _CONTROLLER_STATE["phase_error"] = None
        _CONTROLLER_STATE["bot_move"] = None
        _CONTROLLER_STATE["phase_updated_at"] = time.time()
        return {"running": False}


# ───────────────────────────────────────────────────────────────────────────
# Webapp → LCD push messages
# ───────────────────────────────────────────────────────────────────────────


class LcdSetModePayload(BaseModel):
    mode: int = Field(..., ge=0, le=15)


class LcdSetDifficultyPayload(BaseModel):
    difficulty: int = Field(..., ge=1, le=20)


@app.post("/api/controller/lcd/set-mode")
def lcd_set_mode(payload: LcdSetModePayload):
    ui_link: Optional[ArduinoUIControllerLink] = _CONTROLLER_STATE["ui_link"]
    if ui_link is None:
        return {"sent": False, "reason": "controller_not_running"}
    try:
        ui_link.set_mode(payload.mode)
    except Exception as exc:
        raise HTTPException(502, f"LCD send failed: {exc}") from exc
    return {"sent": True, "mode": payload.mode}


@app.post("/api/controller/lcd/set-difficulty")
def lcd_set_difficulty(payload: LcdSetDifficultyPayload):
    ui_link: Optional[ArduinoUIControllerLink] = _CONTROLLER_STATE["ui_link"]
    controller: Optional[GameController] = _CONTROLLER_STATE["controller"]
    if ui_link is None:
        return {"sent": False, "reason": "controller_not_running"}
    try:
        ui_link.set_difficulty(payload.difficulty)
        if controller is not None:
            controller.set_difficulty(payload.difficulty)
    except Exception as exc:
        raise HTTPException(502, f"LCD send failed: {exc}") from exc
    return {"sent": True, "difficulty": payload.difficulty}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)
