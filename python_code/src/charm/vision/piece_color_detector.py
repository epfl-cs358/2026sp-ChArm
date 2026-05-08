from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from charm.vision.grid_splitter import SquareCell
from charm.vision.occupancy_detector import OccupancyResult

PieceColorLabel = Literal["white", "black", "unknown"]


@dataclass
class PieceColorResult:
    row: int
    col: int
    occupied: bool
    color: PieceColorLabel
    brightness_score: float


def compute_piece_brightness_score(cell_image: np.ndarray) -> float:
    """
    Compute a brightness score from the center ROI using CLAHE + Otsu binarization.
    Returns mean of the binary image: ~255 for white pieces, ~0 for black pieces.
    This approach is robust to absolute lighting changes since it relies on local contrast.
    """
    h, w = cell_image.shape[:2]

    x1 = int(w * 0.25)
    x2 = int(w * 0.75)
    y1 = int(h * 0.25)
    y2 = int(h * 0.75)

    roi = cell_image[y1:y2, x1:x2]

    # Boost saturation so slightly off-white pieces separate from flat board squares
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 2.5, 0, 255)
    roi_enhanced = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    gray = cv2.cvtColor(roi_enhanced, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    return float(np.mean(blurred))


def detect_piece_colors(
    cells: list[SquareCell],
    occupancy_results: list[OccupancyResult],
    white_threshold: float = 128.0,
    black_threshold: float = 128.0,
) -> list[PieceColorResult]:
    """
    Only classify occupied cells.
    - score >= white_threshold -> white
    - score <= black_threshold -> black
    - otherwise -> unknown
    """
    occupancy_map = {(r.row, r.col): r for r in occupancy_results}
    results: list[PieceColorResult] = []

    for cell in cells:
        occ = occupancy_map[(cell.row, cell.col)]

        if not occ.occupied:
            results.append(
                PieceColorResult(
                    row=cell.row,
                    col=cell.col,
                    occupied=False,
                    color="unknown",
                    brightness_score=0.0,
                )
            )
            continue

        score = compute_piece_brightness_score(cell.image)

        if score >= white_threshold:
            label: PieceColorLabel = "white"
        elif score <= black_threshold:
            label = "black"
        else:
            label = "unknown"

        results.append(
            PieceColorResult(
                row=cell.row,
                col=cell.col,
                occupied=True,
                color=label,
                brightness_score=score,
            )
        )

    return results


def draw_binary_debug(
    cells: list[SquareCell],
    cell_size: int = 100,
) -> np.ndarray:
    """
    Build an 8x8 grid image showing the CLAHE+Otsu binary image for each cell,
    so you can inspect what the brightness scorer actually sees.
    """
    canvas = np.zeros((8 * cell_size, 8 * cell_size), dtype=np.uint8)

    for cell in cells:
        h, w = cell.image.shape[:2]
        x1 = int(w * 0.25)
        x2 = int(w * 0.75)
        y1 = int(h * 0.25)
        y2 = int(h * 0.75)
        roi = cell.image[y1:y2, x1:x2]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        tile = cv2.resize(binary, (cell_size, cell_size), interpolation=cv2.INTER_NEAREST)

        r = cell.row
        c = cell.col
        canvas[r * cell_size:(r + 1) * cell_size, c * cell_size:(c + 1) * cell_size] = tile

    # Convert grayscale to BGR so it fits with the rest of the debug images
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def draw_piece_color_debug(
    board_image: np.ndarray,
    cells: list[SquareCell],
    color_results: list[PieceColorResult],
) -> np.ndarray:
    debug_image = board_image.copy()
    result_map = {(r.row, r.col): r for r in color_results}

    for cell in cells:
        result = result_map[(cell.row, cell.col)]

        if not result.occupied:
            color = (0, 0, 255)  # red
            label = "E"
            thickness = 1
        else:
            if result.color == "white":
                color = (255, 255, 255)
                label = f"W:{result.brightness_score:.0f}"
            elif result.color == "black":
                color = (0, 255, 0)
                label = f"B:{result.brightness_score:.0f}"
            else:
                color = (0, 255, 255)  # yellow
                label = f"U:{result.brightness_score:.0f}"
            thickness = 3

        cv2.rectangle(
            debug_image,
            (cell.x1, cell.y1),
            (cell.x2, cell.y2),
            color,
            thickness,
        )

        text_color = color if result.color != "white" else (0, 0, 0)
        cv2.putText(
            debug_image,
            label,
            (cell.x1 + 5, cell.y1 + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            text_color,
            1,
            cv2.LINE_AA,
        )

    return debug_image