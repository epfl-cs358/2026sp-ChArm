from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from charm.utils.bitmap import build_white_black_bitmaps
from charm.vision.grid_splitter import draw_8x8_grid, extract_8x8_cells
from charm.vision.occupancy_detector import (
    detect_occupancy,
    draw_occupancy_debug,
    occupancy_to_matrix,
)
from charm.vision.piece_color_detector import (
    detect_piece_colors,
    draw_piece_color_debug,
)

_PYTHON_CODE_DIR = Path(__file__).resolve().parents[3]
CV_TUNING_PATH = _PYTHON_CODE_DIR / "cv_tuning.json"

_CV_TUNING_DEFAULTS = {
    "occupancy_threshold": 12.0,
    "occupancy_delta_threshold": 12.0,
    "canny_low": 15,
    "canny_high": 50,
    "occupancy_std_weight": 0.4,
    "white_threshold": 90.0,
    "black_threshold": 90.0,
    "white_delta_threshold": 5.0,
    "black_delta_threshold": -30.0,
}


def load_cv_tuning() -> dict:
    try:
        return {**_CV_TUNING_DEFAULTS, **json.loads(CV_TUNING_PATH.read_text())}
    except Exception:
        return dict(_CV_TUNING_DEFAULTS)


@dataclass
class PipelineOptions:
    occupancy_threshold: Optional[float] = None
    occupancy_delta_threshold: Optional[float] = None
    white_threshold: Optional[float] = None
    black_threshold: Optional[float] = None
    white_delta_threshold: Optional[float] = None
    black_delta_threshold: Optional[float] = None
    warp_size: int = 800
    reference_image_path: Optional[str] = None


@dataclass
class BoardPipelineResult:
    original_image: np.ndarray
    roi_debug_image: np.ndarray
    cropped_board_image: np.ndarray
    preprocessing_debug_image: np.ndarray
    black_mask_debug_image: np.ndarray
    color_mask_debug_image: np.ndarray
    corners_debug_image: np.ndarray
    warped_board: np.ndarray
    grid_debug_image: np.ndarray
    occupancy_debug_image: np.ndarray
    piece_color_debug_image: np.ndarray
    occupancy_matrix: list[list[int]]
    white_bitmap: list[list[int]]
    black_bitmap: list[list[int]]


def run_board_pipeline(
    image_path: str,
    options: Optional[PipelineOptions] = None,
) -> BoardPipelineResult:
    """
    Minimal pipeline for an already-calibrated board image.

    Assumption:
    - The input image is already geometrically corrected before entering here
      (for example by first warp + second refinement).
    - No automatic board detection, ROI cropping, or preprocessing is done here.
    - This pipeline only performs:
        1) normalization to a fixed square size
        2) 8x8 grid splitting
        3) occupancy detection
        4) piece color detection
        5) bitmap generation

    When ``options`` is None (or a field is None), threshold values are loaded
    from ``cv_tuning.json`` so the LCD controller and webapp always share the
    same tuned defaults.
    """
    tuning = load_cv_tuning()
    if options is None:
        options = PipelineOptions()

    occupancy_threshold = options.occupancy_threshold if options.occupancy_threshold is not None else tuning["occupancy_threshold"]
    white_threshold = options.white_threshold if options.white_threshold is not None else tuning["white_threshold"]
    black_threshold = options.black_threshold if options.black_threshold is not None else tuning["black_threshold"]
    warp_size = options.warp_size

    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    roi_debug_image = image.copy()
    cropped_board_image = image.copy()
    preprocessing_debug_image = image.copy()
    corners_debug_image = image.copy()
    black_mask_debug_image = image.copy()
    color_mask_debug_image = image.copy()

    # Normalize to a fixed square size
    warped_board = cv2.resize(
        image,
        (warp_size, warp_size),
        interpolation=cv2.INTER_CUBIC,
    )

    # Draw grid and split cells
    grid_debug_image = draw_8x8_grid(warped_board)
    cells = extract_8x8_cells(warped_board)

    # Occupancy detection
    occupancy_results = detect_occupancy(cells, threshold=occupancy_threshold)
    occupancy_matrix = occupancy_to_matrix(occupancy_results)
    occupancy_debug_image = draw_occupancy_debug(
        warped_board,
        cells,
        occupancy_results,
    )

    # Piece color detection
    color_results = detect_piece_colors(
        cells,
        occupancy_results,
        white_threshold=white_threshold,
        black_threshold=black_threshold,
    )
    piece_color_debug_image = draw_piece_color_debug(
        warped_board,
        cells,
        color_results,
    )
    # Final bitmaps
    white_bitmap, black_bitmap = build_white_black_bitmaps(color_results)

    return BoardPipelineResult(
        original_image=image,
        roi_debug_image=roi_debug_image,
        cropped_board_image=cropped_board_image,
        preprocessing_debug_image=preprocessing_debug_image,
        black_mask_debug_image=black_mask_debug_image,
        color_mask_debug_image=color_mask_debug_image,
        corners_debug_image=corners_debug_image,
        warped_board=warped_board,
        grid_debug_image=grid_debug_image,
        occupancy_debug_image=occupancy_debug_image,
        piece_color_debug_image=piece_color_debug_image,
        occupancy_matrix=occupancy_matrix,
        white_bitmap=white_bitmap,
        black_bitmap=black_bitmap,
    )
