from __future__ import annotations

import cv2
import numpy as np


def order_points(points: np.ndarray) -> np.ndarray:
    """
    Order 4 points as:
    top-left, top-right, bottom-right, bottom-left
    """
    pts = np.array(points, dtype=np.float32)

    # First sort by y-coordinate
    y_sorted = pts[np.argsort(pts[:, 1])]

    # Top two points and bottom two points
    top_two = y_sorted[:2]
    bottom_two = y_sorted[2:]

    # Sort top two by x to get top-left and top-right
    top_left, top_right = top_two[np.argsort(top_two[:, 0])]

    # Sort bottom two by x to get bottom-left and bottom-right
    bottom_left, bottom_right = bottom_two[np.argsort(bottom_two[:, 0])]

    return np.array(
        [top_left, top_right, bottom_right, bottom_left],
        dtype=np.float32,
    )


def warp_board(image: np.ndarray, corners: np.ndarray, size: int = 800) -> np.ndarray:
    ordered = order_points(corners)

    destination = np.array(
        [
            [0, 0],
            [size - 1, 0],
            [size - 1, size - 1],
            [0, size - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(ordered, destination)
    warped = cv2.warpPerspective(image, matrix, (size, size))

    return warped