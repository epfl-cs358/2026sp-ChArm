from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class SquareCell:
    row: int
    col: int
    x1: int
    y1: int
    x2: int
    y2: int
    image: np.ndarray


def _detect_axis_lines(
    projection: np.ndarray,
    length: int,
    expected_lines: np.ndarray,
    search_radius: int,
) -> list[int]:
    lines = [0]

    for idx in range(1, 8):
        expected = int(round(expected_lines[idx]))
        lo = max(lines[-1] + 20, expected - search_radius)
        hi = min(length - 20, expected + search_radius)

        if hi <= lo:
            lines.append(expected)
            continue

        local = projection[lo:hi]
        lines.append(lo + int(np.argmax(local)))

    lines.append(length)
    return lines


def detect_8x8_grid_lines(board_image: np.ndarray) -> tuple[list[int], list[int]]:
    """
    Detect grid lines near the ideal 8x8 split using chroma transitions.

    The perspective warp gets the board close to square, but a few pixels of
    crop/tilt error make the visible square boundaries drift. We search around
    each expected grid line instead of hardcoding exact 100 px steps.
    """
    height, width = board_image.shape[:2]
    lab = cv2.cvtColor(board_image, cv2.COLOR_BGR2LAB)
    chroma = lab[:, :, 1].astype(np.float32)
    chroma = cv2.GaussianBlur(chroma, (0, 0), 3.0)

    vertical_projection = np.mean(np.abs(np.diff(chroma, axis=1)), axis=0)
    horizontal_projection = np.mean(np.abs(np.diff(chroma, axis=0)), axis=1)

    vertical_projection = cv2.GaussianBlur(
        vertical_projection.reshape(1, -1),
        (15, 1),
        0,
    ).reshape(-1)
    horizontal_projection = cv2.GaussianBlur(
        horizontal_projection.reshape(-1, 1),
        (1, 15),
        0,
    ).reshape(-1)

    expected_x = np.linspace(0, width, 9)
    expected_y = np.linspace(0, height, 9)
    search_radius = max(12, min(width, height) // 32)

    x_lines = _detect_axis_lines(
        vertical_projection,
        width,
        expected_x,
        search_radius,
    )
    y_lines = _detect_axis_lines(
        horizontal_projection,
        height,
        expected_y,
        search_radius,
    )

    return x_lines, y_lines


def extract_8x8_cells(
    board_image: np.ndarray,
    x_lines: list[int] | None = None,
    y_lines: list[int] | None = None,
) -> list[SquareCell]:
    height, width = board_image.shape[:2]

    if x_lines is None or y_lines is None:
        x_lines, y_lines = detect_8x8_grid_lines(board_image)

    cells: list[SquareCell] = []

    for row in range(8):
        for col in range(8):
            x1 = max(0, min(width, x_lines[col]))
            y1 = max(0, min(height, y_lines[row]))
            x2 = max(0, min(width, x_lines[col + 1]))
            y2 = max(0, min(height, y_lines[row + 1]))

            cell_img = board_image[y1:y2, x1:x2].copy()

            cells.append(
                SquareCell(
                    row=row,
                    col=col,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    image=cell_img,
                )
            )

    return cells


def draw_8x8_grid(
    board_image: np.ndarray,
    x_lines: list[int] | None = None,
    y_lines: list[int] | None = None,
) -> np.ndarray:
    debug_image = board_image.copy()
    height, width = debug_image.shape[:2]

    if x_lines is None or y_lines is None:
        x_lines, y_lines = detect_8x8_grid_lines(board_image)

    for x in x_lines:
        cv2.line(debug_image, (x, 0), (x, height), (255, 0, 0), 2)
    for y in y_lines:
        cv2.line(debug_image, (0, y), (width, y), (255, 0, 0), 2)

    return debug_image
