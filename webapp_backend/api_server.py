from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

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
from charm.vision.board_detector import (
    BoardDetectionParams,
    draw_board_detection_step,
    find_largest_quadrilateral,
)
from charm.vision.grid_splitter import (
    detect_8x8_grid_lines,
    draw_8x8_grid,
    extract_8x8_cells,
)
from charm.vision.occupancy_detector import (
    OccupancyResult,
    compute_occupancy_score,
    draw_occupancy_debug,
    occupancy_to_matrix,
)
from charm.vision.piece_color_detector import draw_piece_color_debug

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
RAW_IMAGE_PATH = REPO_ROOT / "latest_raw.jpg"
LEGACY_RAW_IMAGE_PATH = PYTHON_CODE_DIR / "latest_raw.jpg"
SAVED_PARAMS_PATH = REPO_ROOT / "saved_pipeline_params.json"
ANNOTATIONS_PATH = REPO_ROOT / "color_annotations.json"
CLASSIFIER_STATUS_PATH = REPO_ROOT / "models" / "classifier_last_result.json"

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
    canny_low: int = 15
    canny_high: int = 50
    occupancy_std_weight: float = 0.4
    white_threshold: float = 110.5
    black_threshold: float = 110.0
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


class SavedParamsPayload(BaseModel):
    params: PipelineParams
    score: Optional[dict] = None
    labels: Optional[list[list[str]]] = None
    source_image: Optional[str] = None


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
    baud: int = 9600
    square: Optional[str] = None
    uci: Optional[str] = None
    raw: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    corner: Optional[str] = None
    piece_type: Optional[str] = None
    down: bool = False
    capture: bool = False
    castling: bool = False
    promotion: bool = False


class GameStepPayload(BaseModel):
    moves: list[str] = Field(default_factory=list)
    params: PipelineParams = Field(default_factory=PipelineParams)
    capture: bool = False
    max_mismatches: int = 0


class CameraCapturePayload(BaseModel):
    url: Optional[str] = None
    port: Optional[str] = None
    baud: int = 9600


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
    preprocessed = preprocess(warped, p)
    results["preprocessed"] = to_b64(preprocessed)
    timings["preprocess_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    x_lines, y_lines = detect_8x8_grid_lines(preprocessed)
    results["grid_debug"] = to_b64(draw_8x8_grid(preprocessed.copy(), x_lines, y_lines))
    timings["grid_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    occupancy_cells = extract_8x8_cells(preprocessed, x_lines, y_lines)
    color_cells = extract_8x8_cells(warped, x_lines, y_lines)
    scores = [
        compute_occupancy_score(
            c.image,
            canny_low=p.canny_low,
            canny_high=p.canny_high,
            std_weight=p.occupancy_std_weight,
        )
        for c in occupancy_cells
    ]
    occupancy_results = [
        OccupancyResult(
            row=occupancy_cells[i].row,
            col=occupancy_cells[i].col,
            occupied=scores[i] > p.occupancy_threshold,
            score=scores[i],
        )
        for i in range(len(occupancy_cells))
    ]
    results["occupancy_debug"] = to_b64(
        draw_occupancy_debug(preprocessed.copy(), occupancy_cells, occupancy_results)
    )
    results["occupancy_matrix"] = occupancy_to_matrix(occupancy_results)
    scores_grid = [[0.0] * 8 for _ in range(8)]
    for i, c in enumerate(occupancy_cells):
        scores_grid[c.row][c.col] = round(scores[i], 3)
    results["occupancy_scores"] = scores_grid
    timings["occupancy_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    white_bitmap = [[0] * 8 for _ in range(8)]
    black_bitmap = [[0] * 8 for _ in range(8)]
    brightness_grid = [[0.0] * 8 for _ in range(8)]
    color_labels = [["empty"] * 8 for _ in range(8)]

    from charm.vision.piece_color_detector import detect_piece_colors

    color_results = detect_piece_colors(color_cells, occupancy_results, p.white_threshold, p.black_threshold)

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
def robot_position(port: Optional[str] = None, baud: int = 9600):
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
        responses = robot_adapter.send_commands(commands, payload.port, payload.baud)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        robot_adapter.close()
        raise HTTPException(500, str(e))

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
def robot_eeprom(port: Optional[str] = None, baud: int = 9600):
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


@app.get("/api/images/list")
def list_raw_images():
    candidates = sorted(
        PYTHON_CODE_DIR.glob("latest_raw*.jpg"),
        key=lambda p: p.name,
    )
    repo_candidates = sorted(
        REPO_ROOT.glob("latest_raw*.jpg"),
        key=lambda p: p.name,
    )
    seen: set[str] = set()
    images: list[dict] = []
    for path in list(candidates) + list(repo_candidates):
        if path.name not in seen and path.exists():
            seen.add(path.name)
            images.append({"name": path.name, "path": str(path)})
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


@app.get("/api/params/saved")
def get_saved_params():
    if not SAVED_PARAMS_PATH.exists():
        return {"exists": False, "path": str(SAVED_PARAMS_PATH)}
    try:
        return {
            "exists": True,
            "path": str(SAVED_PARAMS_PATH),
            "data": json.loads(SAVED_PARAMS_PATH.read_text()),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to read saved params: {e}")


@app.put("/api/params/saved")
def save_params(payload: SavedParamsPayload):
    data = {
        "params": payload.params.model_dump(exclude={"image_path"}),
        "score": payload.score,
        "labels": payload.labels,
        "source_image": payload.source_image,
        "saved_at": time.time(),
    }
    try:
        SAVED_PARAMS_PATH.write_text(json.dumps(data, indent=2))
    except Exception as e:
        raise HTTPException(500, f"Failed to save params: {e}")

    # Side-effect: upsert into color_annotations.json when labels are provided
    if payload.labels and payload.source_image:
        try:
            board_64 = [
                payload.labels[r][c] for r in range(8) for c in range(8)
            ]
            _upsert_annotation(
                image_id=payload.source_image,
                scene_id=Path(payload.source_image).stem,
                board_64=board_64,
                image_path=payload.source_image,
            )
        except Exception:
            pass  # annotation write failure must not break param save

    return {"status": "saved", "path": str(SAVED_PARAMS_PATH), "data": data}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)
