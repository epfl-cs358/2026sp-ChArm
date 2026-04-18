from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from charm.utils.bitmap import build_white_black_bitmaps
from charm.vision.board_detector import (
    draw_black_mask_debug,
    draw_color_mask_debug,
    draw_detected_corners,
    find_largest_quadrilateral,
)
from charm.vision.grid_splitter import draw_8x8_grid, extract_8x8_cells
from charm.vision.occupancy_detector import (
    detect_occupancy,
    draw_occupancy_debug,
    occupancy_to_matrix,
)
from charm.vision.perspective import warp_board
from charm.vision.piece_color_detector import detect_piece_colors, draw_piece_color_debug


@dataclass
class BoardPipelineResult:
    original_image: np.ndarray
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


def run_board_pipeline(image_path: str) -> BoardPipelineResult:
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    black_mask_debug = draw_black_mask_debug(image)
    color_mask_debug = draw_color_mask_debug(image)

    corners = find_largest_quadrilateral(image)
    if corners is None:
        raise ValueError("Could not detect a chessboard quadrilateral in the image.")

    corners_debug = draw_detected_corners(image, corners)

    warped_board = warp_board(
    image,
    corners,
    size=800,
    crop_border=True,
    border_ratio=0.035,)

    grid_debug = draw_8x8_grid(warped_board)

    cells = extract_8x8_cells(warped_board)

    occupancy_results = detect_occupancy(cells, threshold=7.5)
    occupancy_matrix = occupancy_to_matrix(occupancy_results)
    occupancy_debug = draw_occupancy_debug(warped_board, cells, occupancy_results)

    color_results = detect_piece_colors(
        cells,
        occupancy_results,
        white_threshold=150.0,
        black_threshold=110.0,
    )
    piece_color_debug = draw_piece_color_debug(warped_board, cells, color_results)

    white_bitmap, black_bitmap = build_white_black_bitmaps(color_results)

    return BoardPipelineResult(
        original_image=image,
        black_mask_debug_image=black_mask_debug,
        color_mask_debug_image=color_mask_debug,
        corners_debug_image=corners_debug,
        warped_board=warped_board,
        grid_debug_image=grid_debug,
        occupancy_debug_image=occupancy_debug,
        piece_color_debug_image=piece_color_debug,
        occupancy_matrix=occupancy_matrix,
        white_bitmap=white_bitmap,
        black_bitmap=black_bitmap,
    )