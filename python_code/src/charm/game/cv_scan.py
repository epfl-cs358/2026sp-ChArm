"""CV scan helpers for the controller (play_game.py / GameController).

Mirrors webapp_backend.api_server._make_scan_vision / _make_scan_cnn but takes
no FastAPI payload, so the controller can use the same CVRouter the webapp
uses without depending on the HTTP layer.

Both scan fns:
  1. fetch a fresh raw frame from the ESP32-CAM
  2. apply the two-stage warp + refine (using the board/inner calibrations on disk)
  3. run the chosen pipeline (classical CV or active CNN)
  4. apply the lab-hardcoded 180° flip (camera mount = white-on-top)
  5. return a CaptureOutcome with chess-oriented bitmaps + refined image

After the router validates a capture, ``persist_validated_capture`` writes
the 64 cell crops into the shared dataset (``labeled_datasets/<name>/``) using
the same on-disk schema the webapp produces, so a model can be retrained on
the combined data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import cv2

from charm.vision.four_point_calibration import (
    load_four_point_calibration,
    load_inner_warp_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)
from charm.vision.cv_router import (
    AttemptDecision,
    CaptureOutcome,
    CVRouter,
    RouterConfig,
)
from charm.vision.pipeline import run_board_pipeline
from charm.vision.validated_capture import (
    LABELED_DATASETS_ROOT,
    save_validated_capture,
    unflip_bitmap_180,
)


PYTHON_CODE_DIR = Path(__file__).resolve().parents[3]
BOARD_CAL_PATH = PYTHON_CODE_DIR / "board_calibration.json"
INNER_CAL_PATH = PYTHON_CODE_DIR / "inner_warp_calibration.json"
LATEST_CALIBRATED_PATH = PYTHON_CODE_DIR / "latest_calibrated.jpg"

# Matches webapp_backend.api_server.CNN_MODELS_DIR / CNN_ACTIVE_POINTER.
CNN_MODELS_DIR = PYTHON_CODE_DIR / "models"
CNN_ACTIVE_POINTER = CNN_MODELS_DIR / "active.json"


def _flip_bitmap_180(b: list[list[int]]) -> list[list[int]]:
    return [list(reversed(row)) for row in reversed(b)]


def _fetch_raw_path() -> Path:
    from charm.vision.transferphoto import fetch_raw_image
    return Path(fetch_raw_image())


def _warp_and_refine(raw_path: Path):
    if not BOARD_CAL_PATH.exists() or not INNER_CAL_PATH.exists():
        raise RuntimeError(
            "Board calibration missing — open the webapp Lab page and calibrate first."
        )
    raw = cv2.imread(str(raw_path))
    if raw is None:
        raise RuntimeError(f"Failed to decode raw image at {raw_path}")
    board_cal = load_four_point_calibration(BOARD_CAL_PATH)
    inner_cal = load_inner_warp_calibration(str(INNER_CAL_PATH))
    first_warp = warp_from_calibration(raw, board_cal, output_size=800)
    refined = refine_board_with_inner_corners(first_warp, inner_cal, output_size=800)
    cv2.imwrite(str(LATEST_CALIBRATED_PATH), refined)
    return refined


def _read_active_cnn_run_id() -> Optional[str]:
    if not CNN_ACTIVE_POINTER.exists():
        return None
    try:
        return json.loads(CNN_ACTIVE_POINTER.read_text()).get("run_id")
    except Exception:
        return None


def _load_active_cnn_classifier():
    run_id = _read_active_cnn_run_id()
    if not run_id:
        return None
    model_dir = CNN_MODELS_DIR / run_id
    model_path = model_dir / "chess_cnn.keras"
    indices_path = model_dir / "class_indices.json"
    if not model_path.exists() or not indices_path.exists():
        return None
    from charm.vision.cnn_classifier import CnnBoardClassifier
    return CnnBoardClassifier(str(model_path), str(indices_path))


def make_scan_vision() -> Callable[[], CaptureOutcome]:
    def _do() -> CaptureOutcome:
        raw_path = _fetch_raw_path()
        refined = _warp_and_refine(raw_path)
        bp = run_board_pipeline(str(LATEST_CALIBRATED_PATH))
        wb = _flip_bitmap_180(bp.white_bitmap)
        bb = _flip_bitmap_180(bp.black_bitmap)
        return CaptureOutcome(
            white_bitmap=wb,
            black_bitmap=bb,
            payload={"cv_mode": "vision", "raw_path": str(raw_path)},
            refined_image=refined,
        )

    return _do


def make_scan_cnn() -> Callable[[], CaptureOutcome]:
    from charm.vision.grid_splitter import extract_8x8_cells

    def _do() -> CaptureOutcome:
        if not _read_active_cnn_run_id():
            raise RuntimeError("No active CNN model")
        raw_path = _fetch_raw_path()
        refined = _warp_and_refine(raw_path)
        classifier = _load_active_cnn_classifier()
        if classifier is None:
            raise RuntimeError("Active CNN model files missing")
        cells = extract_8x8_cells(refined)
        result = classifier.classify_cells(cells)
        wb = [[0] * 8 for _ in range(8)]
        bb = [[0] * 8 for _ in range(8)]
        for pred in result.predictions:
            if pred.label == "white":
                wb[pred.row][pred.col] = 1
            elif pred.label == "black":
                bb[pred.row][pred.col] = 1
        wb = _flip_bitmap_180(wb)
        bb = _flip_bitmap_180(bb)
        return CaptureOutcome(
            white_bitmap=wb,
            black_bitmap=bb,
            payload={"cv_mode": "cnn", "raw_path": str(raw_path)},
            refined_image=refined,
        )

    return _do


def build_router() -> tuple[CVRouter, dict[str, Callable[[], CaptureOutcome]], RouterConfig]:
    """Build router + scan fns mirroring webapp_backend.api_server._build_router.

    Reads ``cv_router_config.json`` for primary mode + attempts_each. If no CNN
    is active, the CNN scan fn is omitted and primary is forced to vision so
    the user doesn't see phantom "CNN unavailable" attempts.
    """
    cfg = RouterConfig.load()
    cnn_active = bool(_read_active_cnn_run_id())

    fns: dict[str, Callable[[], CaptureOutcome]] = {"vision": make_scan_vision()}
    if cnn_active:
        fns["cnn"] = make_scan_cnn()

    effective_primary = cfg.primary if cnn_active else "vision"
    if effective_primary != cfg.primary:
        cfg = RouterConfig(
            primary=effective_primary,
            attempts_each=cfg.attempts_each,
            auto_save_validated=cfg.auto_save_validated,
            dataset_name=cfg.dataset_name,
        )
    return CVRouter(config=cfg), fns, cfg


def persist_validated_capture(
    capture: CaptureOutcome,
    cfg: RouterConfig,
    mode_used: str,
    move_uci: Optional[str],
    session_id: str = "play_game",
) -> None:
    """Append a validated frame to the shared labeled dataset.

    Same on-disk schema as the webapp's _persist_validated_capture so both
    sources of training data go into one pool. Best-effort: failures are
    logged but never block the game.
    """
    if not cfg.auto_save_validated:
        return
    if capture is None or capture.refined_image is None:
        return
    try:
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
        print(
            f"[CAPTURE] dataset={cfg.dataset_name} saved={summary.saved} "
            f"counts={summary.counts} error={summary.error}",
            flush=True,
        )
    except Exception as exc:
        print(f"[CAPTURE] best-effort save failed: {exc!r}", flush=True)
