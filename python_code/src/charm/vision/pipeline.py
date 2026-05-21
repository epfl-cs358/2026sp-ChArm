from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class PipelineOptions:
    """Compat shim — the pipeline is fully hardcoded after the cv-vision-updates
    retune, so these fields are accepted but ignored. Kept so callers in
    ``game_session`` / ``vision_integration`` / the webapp keep importing it.
    """

    occupancy_threshold: float = 12.0
    occupancy_delta_threshold: float = 12.0
    white_threshold: float = 90.0
    black_threshold: float = 90.0
    white_delta_threshold: float = 5.0
    black_delta_threshold: float = -30.0
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

    The ``options`` argument is accepted for backward compatibility with callers
    that still pass a ``PipelineOptions`` instance, but the pipeline is fully
    hardcoded after the cv-vision-updates retune (occupancy_threshold=12.0,
    white/black piece thresholds=90, warp size 800). The values inside
    ``options`` are intentionally ignored.
    """
    del options  # compat-only, see docstring
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    # Keep compatibility with the current main.py / result structure.
    # These are placeholder copies because the earlier ROI / corners stages
    # are no longer used in this simplified pipeline.
    roi_debug_image = image.copy()
    cropped_board_image = image.copy()
    preprocessing_debug_image = image.copy()
    corners_debug_image = image.copy()

    # Placeholder debug images to keep the result structure stable
    black_mask_debug_image = image.copy()
    color_mask_debug_image = image.copy()

    # Normalize to a fixed square size
    warped_board = cv2.resize(
        image,
        (800, 800),
        interpolation=cv2.INTER_CUBIC,
    )

    # Draw grid and split cells
    grid_debug_image = draw_8x8_grid(warped_board)
    cells = extract_8x8_cells(warped_board)

    # Occupancy detection
    occupancy_results = detect_occupancy(cells, threshold=12.0)
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
        white_threshold=90,
        black_threshold=90,
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
