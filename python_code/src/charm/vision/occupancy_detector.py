from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from charm.vision.grid_splitter import SquareCell


@dataclass
class OccupancyResult:
    row: int
    col: int
    occupied: bool
    score: float


def compute_occupancy_score(
    cell_image: np.ndarray,
    canny_low: int = 15,
    canny_high: int = 50,
    std_weight: float = 0.4,
) -> float:
    """
    Compute a simple edge-density score on the center ROI of the cell.
    Higher score -> more likely occupied.
    """
    h, w = cell_image.shape[:2]

    x1 = int(w * 0.2)
    x2 = int(w * 0.8)
    y1 = int(h * 0.2)
    y2 = int(h * 0.8)

    roi = cell_image[y1:y2, x1:x2]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Lower thresholds catch weak edges from white pieces on light squares.
    edges = cv2.Canny(blurred, canny_low, canny_high)
    edge_score = float(np.mean(edges))

    # White pieces are 3D with shadows; empty squares are flat and uniform.
    # Std dev captures this variance even when edges are weak.
    std_score = float(np.std(blurred)) * std_weight

    return edge_score + std_score


def detect_occupancy(
    cells: list[SquareCell],
    threshold: float = 4.0,
) -> list[OccupancyResult]:
    results: list[OccupancyResult] = []

    for cell in cells:
        score = compute_occupancy_score(cell.image)
        occupied = score > threshold

        results.append(
            OccupancyResult(
                row=cell.row,
                col=cell.col,
                occupied=occupied,
                score=score,
            )
        )

    return results


def occupancy_to_matrix(results: list[OccupancyResult]) -> list[list[int]]:
    matrix = [[0 for _ in range(8)] for _ in range(8)]

    for result in results:
        matrix[result.row][result.col] = 1 if result.occupied else 0

    return matrix


def draw_occupancy_debug(
    board_image: np.ndarray,
    cells: list[SquareCell],
    results: list[OccupancyResult],
) -> np.ndarray:
    debug_image = board_image.copy()

    result_map = {(r.row, r.col): r for r in results}

    for cell in cells:
        result = result_map[(cell.row, cell.col)]

        color = (0, 255, 0) if result.occupied else (0, 0, 255)
        thickness = 3 if result.occupied else 1

        cv2.rectangle(
            debug_image,
            (cell.x1, cell.y1),
            (cell.x2, cell.y2),
            color,
            thickness,
        )

        label = f"{int(result.occupied)}:{result.score:.1f}"
        cv2.putText(
            debug_image,
            label,
            (cell.x1 + 5, cell.y1 + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    return debug_image
