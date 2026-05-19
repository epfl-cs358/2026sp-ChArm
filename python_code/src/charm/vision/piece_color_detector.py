from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

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
    brightness_delta: Optional[float] = None
    dark_score: Optional[float] = None
    dark_delta: Optional[float] = None


def _center_lab_l(cell_image: np.ndarray) -> np.ndarray:
    h, w = cell_image.shape[:2]
    x1 = int(w * 0.35)
    x2 = int(w * 0.65)
    y1 = int(h * 0.30)
    y2 = int(h * 0.65)
    roi = cell_image[y1:y2, x1:x2]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    return lab[:, :, 0].astype(np.float32)


def compute_piece_brightness_score(cell_image: np.ndarray) -> float:
    """75th percentile of LAB L over the center ROI — picks up white highlights."""
    return float(np.percentile(_center_lab_l(cell_image), 75))


def compute_piece_dark_score(cell_image: np.ndarray) -> float:
    """25th percentile of LAB L over the center ROI — picks up black shadows."""
    return float(np.percentile(_center_lab_l(cell_image), 25))


def detect_piece_colors(
    cells: list[SquareCell],
    occupancy_results: list[OccupancyResult],
    white_threshold: float = 128.0,
    black_threshold: float = 128.0,
    reference_cells: Optional[list[SquareCell]] = None,
    white_delta_threshold: float = 5.0,
    black_delta_threshold: float = -30.0,
) -> list[PieceColorResult]:
    """Classify occupied cells as white/black/unknown.

    Without a reference:
      - p75(LAB L) >= white_threshold -> white
      - p75(LAB L) <= black_threshold -> black
      - otherwise -> unknown

    With `reference_cells` (cells from an empty-board reference) the LAB L
    channel is sampled twice per cell:
      - bright_delta = p75(cell L) - p75(ref L) — kept for debugging.
      - dark_delta   = p25(cell L) - p25(ref L) — primary discriminator.

    Once occupancy has flagged a cell as occupied, the two classes separate
    cleanly on `dark_delta` alone: a black piece body drops p25(L) by ~100+
    units vs the empty reference, while a white piece only moves it by ~±20
    (bright_delta is unreliable for white-on-light-square, where the empty
    square is already near-saturated at p75).

    Classification (with reference):
      - dark_delta <= black_delta_threshold -> black
      - otherwise -> white
    `white_delta_threshold` is retained on the signature for API stability
    but is no longer consulted on the reference path.
    """
    occupancy_map = {(r.row, r.col): r for r in occupancy_results}
    ref_map = {(c.row, c.col): c for c in reference_cells} if reference_cells else {}
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
                    brightness_delta=None,
                )
            )
            continue

        bright_score = compute_piece_brightness_score(cell.image)
        dark_score = compute_piece_dark_score(cell.image)
        ref_cell = ref_map.get((cell.row, cell.col))
        bright_delta: Optional[float] = None
        dark_delta: Optional[float] = None

        if ref_cell is not None:
            ref_bright = compute_piece_brightness_score(ref_cell.image)
            ref_dark = compute_piece_dark_score(ref_cell.image)
            bright_delta = bright_score - ref_bright
            dark_delta = dark_score - ref_dark

            # Once occupancy has already said the cell is occupied, dark_delta
            # alone cleanly splits the two classes: a black piece body drops
            # p25(L) by ~100+ units vs the empty reference, while a white piece
            # moves it by at most ~20 either way (even on light squares where
            # bright_delta is uninformative).
            label: PieceColorLabel = "black" if dark_delta <= black_delta_threshold else "white"
        else:
            if bright_score >= white_threshold:
                label = "white"
            elif bright_score <= black_threshold:
                label = "black"
            else:
                label = "unknown"

        results.append(
            PieceColorResult(
                row=cell.row,
                col=cell.col,
                occupied=True,
                color=label,
                brightness_score=bright_score,
                brightness_delta=bright_delta,
                dark_score=dark_score,
                dark_delta=dark_delta,
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
            tag = {"white": "W", "black": "B"}.get(result.color, "U")
            if result.color == "white":
                color = (255, 255, 255)
            elif result.color == "black":
                color = (0, 255, 0)
            else:
                color = (0, 255, 255)  # yellow

            if result.brightness_delta is not None and result.dark_delta is not None:
                label = f"{tag}:{result.brightness_delta:+.0f}/{result.dark_delta:+.0f}"
            elif result.brightness_delta is not None:
                label = f"{tag}:{result.brightness_delta:+.0f}"
            else:
                label = f"{tag}:{result.brightness_score:.0f}"
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