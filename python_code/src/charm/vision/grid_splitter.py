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


def detect_8x8_grid_lines(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Compatibility function for api_server.py.
    Returns static 8x8 grid lines assuming the image is a perfectly warped board.
    """
    height, width = image.shape[:2]
    x_lines = np.linspace(0, width, 9, dtype=np.int32)
    y_lines = np.linspace(0, height, 9, dtype=np.int32)
    return x_lines, y_lines


def extract_8x8_cells(
    board_image: np.ndarray,
    x_lines: np.ndarray | None = None,
    y_lines: np.ndarray | None = None,
) -> list[SquareCell]:
    """
    Split a board image into 64 cells.
    If lines are provided, use them; otherwise default to static 8x8 split.
    """
    height, width = board_image.shape[:2]

    if x_lines is None or y_lines is None:
        x_lines, y_lines = detect_8x8_grid_lines(board_image)

    cells: list[SquareCell] = []

    for row in range(8):
        for col in range(8):
            x1 = int(x_lines[col])
            y1 = int(y_lines[row])
            x2 = int(x_lines[col + 1])
            y2 = int(y_lines[row + 1])

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
    x_lines: np.ndarray | None = None,
    y_lines: np.ndarray | None = None,
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