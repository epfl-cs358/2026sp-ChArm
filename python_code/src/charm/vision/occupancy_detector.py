from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from charm.vision.grid_splitter import SquareCell


@dataclass
class OccupancyResult:
    row: int
    col: int
    occupied: bool
    score: float
    delta: Optional[float] = None


def _center_roi(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    x1, x2 = int(w * 0.3), int(w * 0.7)
    y1, y2 = int(h * 0.3), int(h * 0.7)
    return image[y1:y2, x1:x2]


def compute_occupancy_score(cell_image: np.ndarray) -> float:
    """Edge density + std-dev on a center ROI. Higher = more likely occupied."""
    roi = _center_roi(cell_image)

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(blurred, 15, 50)
    edge_score = float(np.mean(edges))

    std_score = float(np.std(blurred)) * 0.4

    return edge_score + std_score


def compute_reference_delta(cell_image: np.ndarray, reference_image: np.ndarray) -> float:
    """Mean LAB CIE76 distance between center ROIs of cell and reference.

    Robust to square color: white pieces are far from green or pink in LAB even
    when grayscale is similar. ~0 for an empty cell matching the reference;
    typically >15 once a piece is present.
    """
    h = min(cell_image.shape[0], reference_image.shape[0])
    w = min(cell_image.shape[1], reference_image.shape[1])
    a = _center_roi(cell_image[:h, :w])
    b = _center_roi(reference_image[:h, :w])

    a_lab = cv2.cvtColor(a, cv2.COLOR_BGR2LAB).astype(np.float32)
    b_lab = cv2.cvtColor(b, cv2.COLOR_BGR2LAB).astype(np.float32)

    diff = a_lab - b_lab
    dist = np.sqrt(np.sum(diff * diff, axis=2))
    return float(np.mean(dist))


def detect_occupancy(
    cells: list[SquareCell],
    threshold: float = 8.0,
    reference_cells: Optional[list[SquareCell]] = None,
    delta_threshold: float = 12.0,
) -> list[OccupancyResult]:
    """Classify each cell as occupied/empty.

    When `reference_cells` is provided, a cell is occupied iff
    `delta > delta_threshold` AND `score > threshold`. The two signals are
    largely independent: `score` (edge density + std) rejects smooth lighting
    gradients that would otherwise spoof the LAB-delta check, while
    `delta` rejects edge-dense but already-empty patterns. Requiring both is
    robust to lighting drift the reference can't predict (e.g. reflections
    from nearby pieces onto empty squares).

    Without a reference, falls back to the absolute edge+std score alone.
    """
    ref_map = {(c.row, c.col): c for c in reference_cells} if reference_cells else {}

    results: list[OccupancyResult] = []
    for cell in cells:
        score = compute_occupancy_score(cell.image)
        ref_cell = ref_map.get((cell.row, cell.col))
        delta: Optional[float] = None

        if ref_cell is not None:
            delta = compute_reference_delta(cell.image, ref_cell.image)
            occupied = (delta > delta_threshold) and (score > threshold)
        else:
            occupied = score > threshold

        results.append(
            OccupancyResult(
                row=cell.row,
                col=cell.col,
                occupied=occupied,
                score=score,
                delta=delta,
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

        if result.delta is not None:
            label = f"{int(result.occupied)}:d{result.delta:.1f}"
        else:
            label = f"{int(result.occupied)}:{result.score:.1f}"
        cv2.putText(
            debug_image,
            label,
            (cell.x1 + 5, cell.y1 + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.30,
            color,
            1,
            cv2.LINE_AA,
        )

    return debug_image
