from __future__ import annotations

import cv2
import numpy as np


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

    for row in range(8):
        for col in range(8):
            cx = col * cell_width + 10
            cy = row * cell_height + 30
            label = f"{row},{col}"
            cv2.putText(
                debug_image,
                label,
                (cx, cy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )

    return debug_image