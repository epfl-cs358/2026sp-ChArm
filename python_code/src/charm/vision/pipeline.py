from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from charm.vision.board_detector import find_largest_quadrilateral, draw_detected_corners
from charm.vision.grid_splitter import draw_8x8_grid
from charm.vision.perspective import warp_board


@dataclass
class BoardPipelineResult:
    original_image: np.ndarray
    corners_debug_image: np.ndarray
    warped_board: np.ndarray
    grid_debug_image: np.ndarray


def run_board_pipeline(image_path: str) -> BoardPipelineResult:
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    corners = find_largest_quadrilateral(image)
    if corners is None:
        raise ValueError("Could not detect a chessboard quadrilateral in the image.")

    corners_debug = draw_detected_corners(image, corners)
    warped_board = warp_board(image, corners, size=800)
    grid_debug = draw_8x8_grid(warped_board)

    return BoardPipelineResult(
        original_image=image,
        corners_debug_image=corners_debug,
        warped_board=warped_board,
        grid_debug_image=grid_debug,
    )