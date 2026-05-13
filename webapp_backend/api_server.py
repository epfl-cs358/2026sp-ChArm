from __future__ import annotations

import base64
import json
import os
import sys
import threading
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
sys.path.insert(0, str(SRC_PATH))

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
from charm.vision.piece_color_detector import draw_piece_color_debug, reload_model
from charm.vision.piece_color_knn import (
    DEFAULT_MODEL_PATH,
    build_color_dataset,
    classify_piece_colors,
    compute_image_median_L,
    load_color_model,
    train_color_classifier,
)
from charm.game.state_tracker import infer_move_from_bitmaps
from charm.arduino.arduino_bridge import (
    ArduinoBridge,
    MoveFlags,
    build_move_commands,
    find_arduino_port,
    parse_position_response,
)
from charm.arduino.coordinate_map import (
    DEFAULT_CONFIG_PATH as ROBOT_CAL_PATH,
    BoardCalibration,
    load_calibration as load_robot_calibration,
    save_calibration as save_robot_calibration,
)

BOARD_CAL_PATH = PYTHON_CODE_DIR / "board_calibration.json"
INNER_CAL_PATH = PYTHON_CODE_DIR / "inner_warp_calibration.json"
RAW_IMAGE_PATH = REPO_ROOT / "latest_raw.jpg"
LEGACY_RAW_IMAGE_PATH = PYTHON_CODE_DIR / "latest_raw.jpg"
SAVED_PARAMS_PATH = REPO_ROOT / "saved_pipeline_params.json"
ANNOTATIONS_PATH = REPO_ROOT / "color_annotations.json"
CLASSIFIER_STATUS_PATH = REPO_ROOT / "models" / "classifier_last_result.json"

_robot_bridge: Optional[ArduinoBridge] = None
_robot_bridge_key: Optional[tuple[Optional[str], int, bool]] = None
_robot_bridge_lock = threading.RLock()

app = FastAPI(title="ChArm Vision API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_knn_model = None


def _get_knn_model():
    global _knn_model
    if _knn_model is None:
        _knn_model = load_color_model()
    return _knn_model


class PipelineParams(BaseModel):
    auto_detect_board: bool = True
    apply_inner_warp: bool = False
    board_canny_low: int = 50
    board_canny_high: int = 150
    board_dilation_iterations: int = 1
    board_min_area: float = 5000.0
    board_max_side_ratio: float = 1.18
    board_min_area_ratio: float = 0.08
    board_max_area_ratio: float = 0.80
    board_min_color_ratio: float = 0.12
    board_padding_ratio: float = 0.006
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
    occupancy_threshold: float = 25.0
    canny_low: int = 15
    canny_high: int = 50
    occupancy_std_weight: float = 0.4
    white_threshold: float = 125.0
    black_threshold: float = 110.0
    knn_n_neighbors: int = 5
    color_mode: str = "threshold"  # "threshold" | "knn"
    warp_size: int = 800
    image_path: Optional[str] = None


class CalibrationUpdate(BaseModel):
    board: Optional[dict] = None
    inner: Optional[dict] = None


class SavedParamsPayload(BaseModel):
    params: PipelineParams
    score: Optional[dict] = None
    labels: Optional[list[list[str]]] = None
    source_image: Optional[str] = None


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
    piece_heights: dict[str, float] = Field(default_factory=dict)


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


def _board_from_uci_moves(moves: list[str]) -> chess.Board:
    board = chess.Board()
    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move for current board state: {uci}")
        board.push(move)
    return board


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


def _extract_cells_for_training(
    image_bgr: np.ndarray,
    p: PipelineParams,
) -> list[np.ndarray]:
    """Preprocess + warp + grid-split, return 64 color crops (unenhanced, warped)."""
    try:
        board_cal, _, _ = _resolve_board_calibration(image_bgr, p)
        warped = warp_from_calibration(image_bgr, board_cal, p.warp_size)
        if p.apply_inner_warp:
            inner_cal = load_inner_warp_calibration(str(INNER_CAL_PATH))
            warped = refine_board_with_inner_corners(warped, inner_cal, p.warp_size)
    except Exception:
        warped = cv2.resize(image_bgr, (p.warp_size, p.warp_size))

    preprocessed = preprocess(warped, p)
    x_lines, y_lines = detect_8x8_grid_lines(preprocessed)
    color_cells = extract_8x8_cells(warped, x_lines, y_lines)
    return [c.image for c in color_cells]


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
        compute_occupancy_score(c.image, p.canny_low, p.canny_high, p.occupancy_std_weight)
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
    crops = [c.image for c in color_cells]
    occupancy_mask = [r.occupied for r in occupancy_results]

    white_bitmap = [[0] * 8 for _ in range(8)]
    black_bitmap = [[0] * 8 for _ in range(8)]
    brightness_grid = [[0.0] * 8 for _ in range(8)]
    color_labels = [["empty"] * 8 for _ in range(8)]

    from charm.vision.piece_color_detector import PieceColorResult

    if p.color_mode == "knn":
        model = _get_knn_model()
        if model is not None:
            median_L = compute_image_median_L(crops)
            color_preds = classify_piece_colors(crops, occupancy_mask, model, {"median_L": median_L})
            color_results = [
                PieceColorResult(
                    row=color_cells[i].row,
                    col=color_cells[i].col,
                    occupied=occupancy_mask[i],
                    color=color_preds[i] if occupancy_mask[i] and color_preds[i] in ("white", "black") else "unknown",
                    brightness_score=0.0,
                )
                for i in range(len(color_cells))
            ]
        else:
            color_results = [
                PieceColorResult(row=c.row, col=c.col, occupied=occupancy_mask[i], color="unknown", brightness_score=0.0)
                for i, c in enumerate(color_cells)
            ]
    else:
        # threshold mode — original logic
        from charm.vision.piece_color_detector import classify_piece_color_threshold
        color_results = []
        for i, cell in enumerate(color_cells):
            occ = occupancy_mask[i]
            if not occ:
                color_results.append(PieceColorResult(row=cell.row, col=cell.col, occupied=False, color="unknown", brightness_score=0.0))
            else:
                label, score = classify_piece_color_threshold(cell.image, p.white_threshold, p.black_threshold)
                color_results.append(PieceColorResult(row=cell.row, col=cell.col, occupied=True, color=label, brightness_score=score))

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
    calibration = load_robot_calibration(ROBOT_CAL_PATH)
    samples = {square: calibration.square_center(square) for square in ("a1", "b1", "a2", "e4", "h8")}
    return {
        "exists": exists,
        "path": str(ROBOT_CAL_PATH),
        "calibration": calibration.to_dict(),
        "samples": samples,
    }


def _close_robot_bridge() -> None:
    global _robot_bridge, _robot_bridge_key
    with _robot_bridge_lock:
        if _robot_bridge is not None:
            _robot_bridge.close()
        _robot_bridge = None
        _robot_bridge_key = None


def _get_robot_bridge(port: Optional[str], baud: int, require_calibration: bool) -> ArduinoBridge:
    global _robot_bridge, _robot_bridge_key
    key = (port, baud, require_calibration)
    with _robot_bridge_lock:
        if _robot_bridge is None or _robot_bridge_key != key:
            _close_robot_bridge()
            calibration = load_robot_calibration(ROBOT_CAL_PATH, require_exists=require_calibration)
            _robot_bridge = ArduinoBridge(port=port, baud=baud, calibration=calibration)
            _robot_bridge_key = key
        return _robot_bridge


@app.get("/api/robot/status")
def robot_status():
    ports: list[dict] = []
    try:
        import serial.tools.list_ports

        ports = [
            {"device": p.device, "description": p.description, "manufacturer": p.manufacturer}
            for p in serial.tools.list_ports.comports()
        ]
    except Exception:
        ports = []

    detected_port = None
    try:
        detected_port = find_arduino_port()
    except Exception:
        detected_port = None

    with _robot_bridge_lock:
        serial_connected = _robot_bridge is not None
        active_port = _robot_bridge.port if _robot_bridge is not None else None

    return {
        "serial_connected": serial_connected,
        "active_port": active_port,
        "detected_port": detected_port,
        "ports": ports,
        "robot_calibration": _robot_calibration_response(),
    }


@app.put("/api/robot/calibration")
def update_robot_calibration(payload: RobotCalibrationPayload):
    a8 = (
        payload.a1.x + payload.h8.x - payload.h1.x,
        payload.a1.y + payload.h8.y - payload.h1.y,
    )
    calibration = BoardCalibration.from_three_squares(
        a1=(payload.a1.x, payload.a1.y),
        h1=(payload.h1.x, payload.h1.y),
        a8=a8,
        z_hover=payload.z_hover,
        z_down=payload.z_down,
        home=(payload.home.x, payload.home.y, payload.home.z),
        capture_bin=(payload.capture_bin.x, payload.capture_bin.y, payload.capture_bin.z),
        piece_heights=payload.piece_heights,
    )
    save_robot_calibration(calibration, ROBOT_CAL_PATH)
    _close_robot_bridge()
    return {"status": "saved", **_robot_calibration_response()}


@app.post("/api/robot/disconnect")
def disconnect_robot():
    _close_robot_bridge()
    return {"status": "disconnected"}


@app.get("/api/robot/position")
def robot_position(port: Optional[str] = None, baud: int = 9600):
    try:
        with _robot_bridge_lock:
            bridge = _get_robot_bridge(port, baud, require_calibration=False)
            responses = bridge.position()
        return {
            "status": "ok",
            "position": parse_position_response(responses),
            "responses": responses,
            "timestamp": time.time(),
        }
    except Exception as e:
        _close_robot_bridge()
        raise HTTPException(500, str(e))


@app.post("/api/robot/command")
def robot_command(payload: RobotCommandPayload):
    try:
        with _robot_bridge_lock:
            requires_calibration = False
            bridge = _get_robot_bridge(payload.port, payload.baud, requires_calibration)

            if payload.command == "pos":
                responses = bridge.position()
            elif payload.command == "arm-calibrate":
                responses = bridge.calibrate_arm()
                responses.extend(bridge.position())
            elif payload.command == "board-info":
                responses = bridge.board_info()
            elif payload.command == "board-calibrate":
                responses = bridge.start_board_calibration()
            elif payload.command == "board-cal-key":
                if payload.raw is None:
                    raise HTTPException(400, "raw calibration key is required")
                responses = bridge.board_calibration_key(payload.raw.lower())
            elif payload.command == "board-cal-clear":
                responses = bridge.clear_board_calibration()
            elif payload.command == "capture-corner":
                if payload.corner is None:
                    raise HTTPException(400, "corner is required")
                responses = bridge.capture_board_corner(payload.corner)
            elif payload.command == "goto":
                if payload.x is None or payload.y is None or payload.z is None:
                    raise HTTPException(400, "x, y, z are required")
                responses = bridge.move_xyz(payload.x, payload.y, payload.z)
            elif payload.command == "jog":
                if payload.raw is None:
                    raise HTTPException(400, "raw jog key is required")
                responses = bridge.jog(payload.raw.lower())
            elif payload.command == "move-square":
                if payload.square is None:
                    raise HTTPException(400, "square is required")
                z = bridge.calibration.z_down if payload.down else bridge.calibration.z_hover
                responses = bridge.move_to_square(payload.square, z=z)
            elif payload.command == "move":
                if payload.uci is None:
                    raise HTTPException(400, "uci is required")
                commands = build_move_commands(
                    payload.uci,
                    bridge.calibration,
                    MoveFlags(payload.capture, payload.castling, payload.promotion),
                    piece_type=payload.piece_type,
                )
                responses = []
                for command in commands:
                    responses.extend(bridge.send_command(command))
            elif payload.command == "raw":
                if payload.raw is None:
                    raise HTTPException(400, "raw is required")
                responses = bridge.send_command(payload.raw)
            else:
                raise HTTPException(400, f"Unknown robot command: {payload.command}")
    except HTTPException:
        raise
    except Exception as e:
        _close_robot_bridge()
        raise HTTPException(500, str(e))

    return {
        "status": "ok",
        "responses": responses,
        "position": parse_position_response(responses),
        "timestamp": time.time(),
    }


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


@app.post("/api/capture")
def capture_from_camera(payload: CameraCapturePayload):
    try:
        from charm.vision.transferphoto import fetch_raw_image

        path = fetch_raw_image(payload.url)
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
    model_exists = DEFAULT_MODEL_PATH.exists()
    last_result = None
    if CLASSIFIER_STATUS_PATH.exists():
        try:
            last_result = json.loads(CLASSIFIER_STATUS_PATH.read_text())
        except Exception:
            pass
    return {
        "model_trained": model_exists,
        "model_path": str(DEFAULT_MODEL_PATH),
        "last_result": last_result,
    }


@app.post("/api/classifier/retrain")
def retrain_classifier():
    global _knn_model

    annotations = _load_annotations()
    if len(annotations) == 0:
        raise HTTPException(
            400,
            "No annotations found. Save labels with 'Save JSON' or POST to /api/annotations first.",
        )

    # Default pipeline params for feature extraction
    default_p = PipelineParams()
    annotated_images = []
    missing = []

    for ann in annotations:
        img_path = ann.get("image_path")
        if not img_path or not Path(img_path).exists():
            missing.append(ann["image_id"])
            continue
        img = cv2.imread(img_path)
        if img is None:
            missing.append(ann["image_id"])
            continue
        annotated_images.append(
            {
                "image_id": ann["image_id"],
                "scene_id": ann["scene_id"],
                "board_64": ann["board_64"],
                "image_bgr": img,
            }
        )

    if len(annotated_images) == 0:
        raise HTTPException(
            400,
            f"Could not load any annotated images. Missing/unreadable: {missing}",
        )

    def extract_cells_fn(image_bgr: np.ndarray) -> list[np.ndarray]:
        return _extract_cells_for_training(image_bgr, default_p)

    from charm.vision.piece_color_knn import DEFAULT_DATASET_PATH

    X, y, scene_ids = build_color_dataset(annotated_images, extract_cells_fn, DEFAULT_DATASET_PATH)

    if len(X) == 0:
        raise HTTPException(400, "Dataset is empty — all labels are 'empty'. Add white/black labels.")

    result = train_color_classifier(X, y, scene_ids)
    result["missing_images"] = missing

    # Persist last result for status endpoint
    CLASSIFIER_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLASSIFIER_STATUS_PATH.write_text(json.dumps(result, indent=2))

    # Reload model in process
    _knn_model = load_color_model()
    reload_model()

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)
