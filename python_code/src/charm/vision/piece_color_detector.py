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
    Compute a brightness score from the center ROI after a saturation boost.
    This is the threshold classifier's baseline score and is robust to
    slightly off-white pieces on board squares.
    """
    h, w = cell_image.shape[:2]
    x1, x2 = int(w * 0.25), int(w * 0.75)
    y1, y2 = int(h * 0.25), int(h * 0.75)
    roi = cell_image[y1:y2, x1:x2]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 2.5, 0, 255)
    roi_enhanced = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    gray = cv2.cvtColor(roi_enhanced, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return float(np.mean(blurred))


# ---------------------------------------------------------------------------
# Threshold-based classifier (original approach)
# ---------------------------------------------------------------------------


def _compute_brightness_score(cell_image: np.ndarray) -> float:
    return compute_piece_brightness_score(cell_image)


def classify_piece_color_threshold(
    cell_image: np.ndarray,
    white_threshold: float,
    black_threshold: float,
) -> tuple[PieceColorLabel, float]:
    """Original threshold-based color classification."""
    h, w = cell_image.shape[:2]
    gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    x1, x2 = int(w * 0.15), int(w * 0.85)
    y1, y2 = int(h * 0.15), int(h * 0.85)
    roi = blurred[y1:y2, x1:x2]

    if roi.size == 0:
        score = _compute_brightness_score(cell_image)
        if score >= white_threshold:
            return "white", score
        if score <= black_threshold:
            return "black", score
        return "unknown", score

    border_width = max(2, int(min(roi.shape[:2]) * 0.12))
    border = np.concatenate(
        [
            roi[:border_width, :].ravel(),
            roi[-border_width:, :].ravel(),
            roi[:, :border_width].ravel(),
            roi[:, -border_width:].ravel(),
        ]
    )
    background = float(np.median(border))
    diff = roi.astype(np.float32) - background

    bright_mask = diff > 18
    dark_mask = diff < -18
    bright_area = float(np.mean(bright_mask))
    dark_area = float(np.mean(dark_mask))

    bright_score = float(np.mean(roi[bright_mask])) if bright_area > 0.03 else 0.0
    dark_score = float(np.mean(roi[dark_mask])) if dark_area > 0.03 else 255.0
    center_score = _compute_brightness_score(cell_image)

    if bright_area >= 0.04 and bright_score >= white_threshold and bright_area >= dark_area * 0.7:
        return "white", bright_score
    if dark_area >= 0.04 and dark_score <= black_threshold:
        return "black", dark_score
    if center_score >= white_threshold:
        return "white", center_score
    if center_score <= black_threshold:
        return "black", center_score
    return "unknown", center_score


# ---------------------------------------------------------------------------
# kNN-based classifier
# ---------------------------------------------------------------------------

_model_cache = None


def _get_model():
    global _model_cache
    if _model_cache is None:
        from charm.vision.piece_color_knn import load_color_model

        _model_cache = load_color_model()
    return _model_cache


def reload_model() -> None:
    """Force reload of the kNN model from disk (call after retraining)."""
    global _model_cache
    from charm.vision.piece_color_knn import load_color_model

    _model_cache = load_color_model()


# ---------------------------------------------------------------------------
# Unified entry point (used by pipeline.py — defaults to threshold)
# ---------------------------------------------------------------------------


def detect_piece_colors(
    cells: list[SquareCell],
    occupancy_results: list[OccupancyResult],
    white_threshold: float = 125.0,
    black_threshold: float = 110.0,
    color_mode: str = "threshold",
    model=None,
) -> list[PieceColorResult]:
    """
    Classify color of occupied cells.

    color_mode="threshold": original brightness-threshold logic (default, always available).
    color_mode="knn": kNN classifier (requires trained model on disk).
    """
    occupancy_map = {(r.row, r.col): r for r in occupancy_results}
    results: list[PieceColorResult] = []

    if color_mode == "knn":
        from charm.vision.piece_color_knn import classify_piece_colors, compute_image_median_L

        if model is None:
            model = _get_model()

        crops = [c.image for c in cells]
        occupancy_mask = [occupancy_map[(c.row, c.col)].occupied for c in cells]

        if model is not None:
            median_L = compute_image_median_L(crops)
            labels = classify_piece_colors(crops, occupancy_mask, model, {"median_L": median_L})
        else:
            labels = ["empty" if not occ else "unknown" for occ in occupancy_mask]

        for i, cell in enumerate(cells):
            occ = occupancy_map[(cell.row, cell.col)]
            raw = labels[i]
            color: PieceColorLabel = raw if raw in ("white", "black") else "unknown"
            results.append(
                PieceColorResult(row=cell.row, col=cell.col, occupied=occ.occupied, color=color, brightness_score=0.0)
            )
    else:
        for cell in cells:
            occ = occupancy_map[(cell.row, cell.col)]
            if not occ.occupied:
                results.append(
                    PieceColorResult(row=cell.row, col=cell.col, occupied=False, color="unknown", brightness_score=0.0)
                )
            else:
                label, score = classify_piece_color_threshold(cell.image, white_threshold, black_threshold)
                results.append(
                    PieceColorResult(row=cell.row, col=cell.col, occupied=True, color=label, brightness_score=score)
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
            color = (0, 0, 255)
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
                color = (0, 255, 255)
                label = f"U:{result.brightness_score:.0f}"
            thickness = 3

        cv2.rectangle(debug_image, (cell.x1, cell.y1), (cell.x2, cell.y2), color, thickness)
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
