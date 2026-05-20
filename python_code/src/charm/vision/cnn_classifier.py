"""CNN-based per-cell classifier for the ChArm vision pipeline.

This module replaces step 4 of the classical pipeline (occupancy +
piece-color thresholds) with a single 3-class CNN trained by train_cnn.py.
It still consumes the SquareCell list produced by extract_8x8_cells and
still emits two 8x8 bitmaps consumed by infer_move_from_bitmaps.

This module is importable only. There is no main(), no cv2.imshow, no
keypress loop. The FastAPI server holds one CnnBoardClassifier instance
across requests.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from charm.vision.grid_splitter import SquareCell

PieceClass = Literal["empty", "white", "black"]
EXPECTED_CLASSES: tuple[str, ...] = ("empty", "white", "black")


@dataclass
class CnnCellPrediction:
    row: int
    col: int
    label: PieceClass
    confidence: float
    probs: dict[str, float]


@dataclass
class CnnClassificationResult:
    white_bitmap: list[list[int]]  # 8x8 0/1, row 0 = rank 8, col 0 = file a
    black_bitmap: list[list[int]]  # 8x8 0/1, same convention
    predictions: list[CnnCellPrediction]  # length 64, row-major
    inference_ms: float


def _empty_bitmap() -> list[list[int]]:
    return [[0 for _ in range(8)] for _ in range(8)]


def _resize_cell(cell_image: np.ndarray, side: int = 100) -> np.ndarray:
    """Make every cell exactly side x side; cv2.resize is a no-op when already correct."""
    h, w = cell_image.shape[:2]
    if h == side and w == side:
        return cell_image
    # Local import to keep cv2 out of the module hot-path when unused.
    import cv2
    return cv2.resize(cell_image, (side, side), interpolation=cv2.INTER_AREA)


class CnnBoardClassifier:
    """Wraps a trained Keras model and converts SquareCell lists to bitmaps."""

    def __init__(self, model_path: str, class_indices_path: str) -> None:
        # File-existence checks first so callers get clean errors even when
        # TensorFlow itself isn't installed (e.g. during a lint/test).
        self.model_path = Path(model_path)
        self.class_indices_path = Path(class_indices_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        if not self.class_indices_path.exists():
            raise FileNotFoundError(f"class_indices.json not found: {self.class_indices_path}")

        class_to_idx: dict[str, int] = json.loads(self.class_indices_path.read_text())
        missing = [c for c in EXPECTED_CLASSES if c not in class_to_idx]
        if missing:
            raise ValueError(
                f"class_indices.json is missing required classes: {missing}. "
                f"Got: {sorted(class_to_idx)}"
            )

        # idx -> name lookup for argmax.
        self._idx_to_class: dict[int, str] = {int(v): k for k, v in class_to_idx.items()}
        self._class_to_idx: dict[str, int] = {k: int(v) for k, v in class_to_idx.items()}

        # TensorFlow takes ~3 s to import; do it once here, after we've already
        # confirmed the on-disk artifacts exist.
        import tensorflow as tf
        self.model = tf.keras.models.load_model(self.model_path)

        # Warm up the graph so the first real inference isn't a 1-2s jit hit.
        dummy = np.zeros((1, 100, 100, 3), dtype=np.float32)
        self.model.predict(dummy, verbose=0)

    def classify_cells(self, cells: list[SquareCell]) -> CnnClassificationResult:
        """Run one forward pass over all 64 cells and produce bitmaps + per-cell probs."""
        if not cells:
            raise ValueError("classify_cells received an empty cell list")

        # Order is critical: bitmap[row][col] must align with predictions.
        ordered = sorted(cells, key=lambda c: (c.row, c.col))
        batch = np.stack([_resize_cell(c.image) for c in ordered], axis=0).astype(np.float32)
        # Rescaling layer in the model handles /255 — feed raw uint8 floats.

        t0 = time.perf_counter()
        probs = self.model.predict(batch, verbose=0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        white_bitmap = _empty_bitmap()
        black_bitmap = _empty_bitmap()
        predictions: list[CnnCellPrediction] = []

        for cell, prob_row in zip(ordered, probs):
            best_idx = int(np.argmax(prob_row))
            label = self._idx_to_class.get(best_idx, "empty")
            confidence = float(prob_row[best_idx])
            named_probs = {
                name: float(prob_row[self._class_to_idx[name]])
                for name in EXPECTED_CLASSES
                if name in self._class_to_idx
            }
            predictions.append(
                CnnCellPrediction(
                    row=cell.row,
                    col=cell.col,
                    label=label,  # type: ignore[arg-type]
                    confidence=confidence,
                    probs=named_probs,
                )
            )
            if label == "white":
                white_bitmap[cell.row][cell.col] = 1
            elif label == "black":
                black_bitmap[cell.row][cell.col] = 1

        return CnnClassificationResult(
            white_bitmap=white_bitmap,
            black_bitmap=black_bitmap,
            predictions=predictions,
            inference_ms=elapsed_ms,
        )


# ---------------------------------------------------------------------------
# Integration sketch for webapp_backend/api_server.py — already wired in this
# project. Keeping the skeleton here so the integration contract stays
# co-located with the classifier itself.
# ---------------------------------------------------------------------------
#
# from charm.vision.cnn_classifier import CnnBoardClassifier
# from charm.vision.transferphoto import fetch_raw_image
# from charm.vision.four_point_calibration import (
#     load_four_point_calibration,
#     load_inner_warp_calibration,
#     warp_from_calibration,
#     refine_board_with_inner_corners,
# )
# from charm.vision.grid_splitter import extract_8x8_cells
#
# classifier = CnnBoardClassifier(
#     model_path="python_code/models/<run_id>/chess_cnn.keras",
#     class_indices_path="python_code/models/<run_id>/class_indices.json",
# )
#
# @app.post("/api/cnn/scan")
# def cnn_scan():
#     raw = cv2.imread(fetch_raw_image())
#     warped = refine_board_with_inner_corners(
#         warp_from_calibration(raw, board_cal, output_size=800),
#         inner_cal, output_size=800,
#     )
#     cells = extract_8x8_cells(warped)
#     result = classifier.classify_cells(cells)
#     return {"white_bitmap": result.white_bitmap, "black_bitmap": result.black_bitmap}
