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


def extract_8x8_cells(board_image: np.ndarray) -> list[SquareCell]:
    height, width = board_image.shape[:2]
    cell_width = width // 8
    cell_height = height // 8

    cells: list[SquareCell] = []

    for row in range(8):
        for col in range(8):
            x1 = col * cell_width
            y1 = row * cell_height
            x2 = (col + 1) * cell_width
            y2 = (row + 1) * cell_height

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


def draw_8x8_grid(board_image: np.ndarray) -> np.ndarray:
    debug_image = board_image.copy()
    height, width = debug_image.shape[:2]

    cell_width = width // 8
    cell_height = height // 8

    for i in range(9):
        x = i * cell_width
        y = i * cell_height

        cv2.line(debug_image, (x, 0), (x, height), (255, 0, 0), 2)
        cv2.line(debug_image, (0, y), (width, y), (255, 0, 0), 2)

    return debug_image