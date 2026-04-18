from __future__ import annotations

import cv2
import numpy as np


def order_points(points: np.ndarray) -> np.ndarray:
    """
    Order points as:
    top-left, top-right, bottom-right, bottom-left
    """
    pts = np.array(points, dtype=np.float32)

    y_sorted = pts[np.argsort(pts[:, 1])]

    top_two = y_sorted[:2]
    bottom_two = y_sorted[2:]

    top_left, top_right = top_two[np.argsort(top_two[:, 0])]
    bottom_left, bottom_right = bottom_two[np.argsort(bottom_two[:, 0])]

    return np.array(
        [top_left, top_right, bottom_right, bottom_left],
        dtype=np.float32,
    )


def crop_inner_board(
    warped_image: np.ndarray,
    border_ratio: float = 0.035,
    output_size: int = 800,
) -> np.ndarray:
    """
    Crop away the outer border after warping.

    border_ratio is the fraction removed from each side.
    Example: 0.035 means crop 3.5% from left/right/top/bottom.
    """
    h, w = warped_image.shape[:2]

    dx = int(w * border_ratio)
    dy = int(h * border_ratio)

    cropped = warped_image[dy:h - dy, dx:w - dx]

    resized = cv2.resize(cropped, (output_size, output_size), interpolation=cv2.INTER_LINEAR)
    return resized


def warp_board(
    image: np.ndarray,
    corners: np.ndarray,
    size: int = 800,
    crop_border: bool = True,
    border_ratio: float = 0.035,
) -> np.ndarray:
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

    if crop_border:
        warped = crop_inner_board(
            warped_image=warped,
            border_ratio=border_ratio,
            output_size=size,
        )

    return warped