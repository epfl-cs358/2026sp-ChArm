"""Per-square exemplar classifier.

Given a labeled dataset captured by the arm-driven wizard, build per-square
feature exemplars for {empty, white, black} and classify new frames by
1-NN with a confidence margin.

The classifier interface is intentionally a drop-in replacement for the
threshold path in ``piece_color_detector.detect_piece_colors`` / occupancy
detection: it consumes the same per-cell warped image and returns occupancy
+ color labels.

Design rationale (recap of the cv_reliability_pitch.md proposal):
  * Per-square exemplars avoid global thresholds — green vs cream squares
    no longer fight a single ``white_threshold``.
  * 1-NN gives a confidence *margin* (distance to 2nd-nearest class),
    surfaceable to the UI for low-confidence cells.
  * Cross-validation accuracy gives an empirical health check per square
    so the wizard can prompt the user to retake the worst ones.

Feature vector (per cell ROI = center 30%..70% box):
  [mean_L, mean_a, mean_b, p25_L, p75_L, edge_density]

LAB is used so brightness (L) and chroma (a,b) are decorrelated — this is
why the threshold path's dark_delta signal is robust, and keeping the same
basis here means we inherit that robustness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import cv2
import numpy as np


LabelStr = Literal["empty", "white", "black"]
ColorOnly = Literal["white", "black", "unknown"]


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_cell_features(cell_image: np.ndarray) -> np.ndarray:
    """Compute a 6-D feature vector for a single cell.

    ROI is the center 30%..70% of the cell so we ignore square-edge artifacts.
    """
    h, w = cell_image.shape[:2]
    x1, x2 = int(w * 0.30), int(w * 0.70)
    y1, y2 = int(h * 0.30), int(h * 0.70)
    roi = cell_image[y1:y2, x1:x2]
    if roi.size == 0:
        return np.zeros(6, dtype=np.float32)

    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]
    A = lab[:, :, 1]
    B = lab[:, :, 2]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.mean(edges > 0))

    return np.array(
        [
            float(np.mean(L)),
            float(np.mean(A)),
            float(np.mean(B)),
            float(np.percentile(L, 25)),
            float(np.percentile(L, 75)),
            edge_density,
        ],
        dtype=np.float32,
    )


def _normalize(features: np.ndarray, scale: np.ndarray) -> np.ndarray:
    safe = np.where(scale > 1e-6, scale, 1.0)
    return features / safe


# ---------------------------------------------------------------------------
# Exemplar bank (per-square per-label storage of feature vectors)
# ---------------------------------------------------------------------------


@dataclass
class SquareExemplars:
    row: int
    col: int
    empty: list[list[float]] = field(default_factory=list)
    white: list[list[float]] = field(default_factory=list)
    black: list[list[float]] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "empty": self.empty,
            "white": self.white,
            "black": self.black,
        }


@dataclass
class ExemplarConfig:
    """All exemplars + the feature-scaling vector used to normalize distances."""

    feature_scale: list[float]
    squares: dict[str, SquareExemplars]  # key: "{row},{col}"
    created_at: float
    dataset_name: str

    def to_json(self) -> dict:
        return {
            "version": 1,
            "created_at": self.created_at,
            "dataset_name": self.dataset_name,
            "feature_scale": self.feature_scale,
            "squares": {k: v.to_json() for k, v in self.squares.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> "ExemplarConfig":
        squares: dict[str, SquareExemplars] = {}
        for k, v in data.get("squares", {}).items():
            squares[k] = SquareExemplars(
                row=int(v["row"]),
                col=int(v["col"]),
                empty=[list(map(float, x)) for x in v.get("empty", [])],
                white=[list(map(float, x)) for x in v.get("white", [])],
                black=[list(map(float, x)) for x in v.get("black", [])],
            )
        return cls(
            feature_scale=[float(x) for x in data.get("feature_scale", [])],
            squares=squares,
            created_at=float(data.get("created_at", 0.0)),
            dataset_name=str(data.get("dataset_name", "")),
        )

    @classmethod
    def load(cls, path: Path) -> "ExemplarConfig":
        return cls.from_json(json.loads(Path(path).read_text()))

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=2))


# ---------------------------------------------------------------------------
# Building the config from a dataset on disk
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    row: int
    col: int
    label: LabelStr
    confidence_margin: float  # (2nd-nearest distance) - (nearest distance)
    nearest_distance: float
    distances: dict[str, float]  # label -> min distance


def _nearest_distance(query: np.ndarray, exemplars: list[list[float]]) -> Optional[float]:
    if not exemplars:
        return None
    bank = np.asarray(exemplars, dtype=np.float32)
    diffs = bank - query
    return float(np.min(np.linalg.norm(diffs, axis=1)))


def classify_cell(
    cell_image: np.ndarray,
    row: int,
    col: int,
    config: ExemplarConfig,
) -> ClassificationResult:
    feats = extract_cell_features(cell_image)
    scale = np.asarray(config.feature_scale, dtype=np.float32)
    query = _normalize(feats, scale)

    key = f"{row},{col}"
    sq = config.squares.get(key)
    distances: dict[str, float] = {}

    if sq is None:
        return ClassificationResult(
            row=row, col=col, label="empty",
            confidence_margin=0.0, nearest_distance=float("inf"), distances=distances,
        )

    for label, bank in (("empty", sq.empty), ("white", sq.white), ("black", sq.black)):
        bank_norm = [(_normalize(np.asarray(v, dtype=np.float32), scale)).tolist() for v in bank]
        d = _nearest_distance(query, bank_norm)
        if d is not None:
            distances[label] = d

    if not distances:
        return ClassificationResult(
            row=row, col=col, label="empty",
            confidence_margin=0.0, nearest_distance=float("inf"), distances=distances,
        )

    ordered = sorted(distances.items(), key=lambda kv: kv[1])
    best_label, best_d = ordered[0]
    second_d = ordered[1][1] if len(ordered) > 1 else best_d + 1.0
    return ClassificationResult(
        row=row, col=col,
        label=best_label,  # type: ignore[arg-type]
        confidence_margin=float(second_d - best_d),
        nearest_distance=float(best_d),
        distances=distances,
    )


# ---------------------------------------------------------------------------
# Cross-validation accuracy report (leave-one-frame-out per square)
# ---------------------------------------------------------------------------


@dataclass
class SquareAccuracy:
    row: int
    col: int
    total: int
    correct: int
    confusion: dict[str, dict[str, int]]  # true_label -> predicted_label -> count

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def to_json(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "total": self.total,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "confusion": self.confusion,
        }


def leave_one_out_accuracy(config: ExemplarConfig) -> dict[str, SquareAccuracy]:
    """For every (square, label, frame) recompute nearest-class with that
    frame held out of its own class. Returns per-square accuracy.
    """
    scale = np.asarray(config.feature_scale, dtype=np.float32)
    out: dict[str, SquareAccuracy] = {}

    for key, sq in config.squares.items():
        banks: dict[str, list[np.ndarray]] = {
            "empty": [np.asarray(v, dtype=np.float32) for v in sq.empty],
            "white": [np.asarray(v, dtype=np.float32) for v in sq.white],
            "black": [np.asarray(v, dtype=np.float32) for v in sq.black],
        }
        confusion: dict[str, dict[str, int]] = {
            true: {pred: 0 for pred in ("empty", "white", "black")}
            for true in ("empty", "white", "black")
        }
        total = 0
        correct = 0
        for true_label, frames in banks.items():
            for i, query_raw in enumerate(frames):
                query = _normalize(query_raw, scale)
                distances: dict[str, float] = {}
                for cand_label, cand_frames in banks.items():
                    candidates = (
                        cand_frames[:i] + cand_frames[i + 1 :]
                        if cand_label == true_label
                        else cand_frames
                    )
                    if not candidates:
                        continue
                    bank = np.stack([_normalize(v, scale) for v in candidates])
                    distances[cand_label] = float(np.min(np.linalg.norm(bank - query, axis=1)))
                if not distances:
                    continue
                pred = min(distances.items(), key=lambda kv: kv[1])[0]
                confusion[true_label][pred] += 1
                total += 1
                if pred == true_label:
                    correct += 1
        out[key] = SquareAccuracy(
            row=sq.row,
            col=sq.col,
            total=total,
            correct=correct,
            confusion=confusion,
        )
    return out


# ---------------------------------------------------------------------------
# Building config from a dataset (used by /api/labeling/compute-stats)
# ---------------------------------------------------------------------------


def build_exemplar_config(
    dataset_name: str,
    extract_cells_fn,
    iter_empty_frames,
    iter_square_frames,
) -> ExemplarConfig:
    """Walk dataset frames and assemble an ExemplarConfig.

    Parameters
    ----------
    extract_cells_fn : Callable[[np.ndarray], list[SquareCell]]
        Wraps the same grid-extraction the pipeline uses so the cell crops
        match. Callers pass a closure that runs detect_8x8_grid_lines +
        extract_8x8_cells on a warped image.
    iter_empty_frames : iterable of warped 8x8-grid images.
    iter_square_frames : Callable[[color, square], iterable[warped image]].
    """
    from charm.vision.labeling_squares import SQUARES_RC  # local import to avoid cycle

    squares: dict[str, SquareExemplars] = {}
    for row, col in SQUARES_RC:
        squares[f"{row},{col}"] = SquareExemplars(row=row, col=col)

    # Empty frames apply to every square (cell taken from the same row/col
    # of every empty-board capture).
    for frame in iter_empty_frames():
        for cell in extract_cells_fn(frame):
            feats = extract_cell_features(cell.image)
            key = f"{cell.row},{cell.col}"
            if key in squares:
                squares[key].empty.append(feats.tolist())

    for color in ("white", "black"):
        for sq_name in _all_square_names():
            row, col = _square_to_rc(sq_name)
            key = f"{row},{col}"
            for frame in iter_square_frames(color, sq_name):
                cells = extract_cells_fn(frame)
                cell = next((c for c in cells if c.row == row and c.col == col), None)
                if cell is None:
                    continue
                feats = extract_cell_features(cell.image)
                if color == "white":
                    squares[key].white.append(feats.tolist())
                else:
                    squares[key].black.append(feats.tolist())

    # Compute per-feature scale across all collected exemplars so distances
    # are comparable across L (range ~0..255) and edge_density (range ~0..1).
    all_features: list[list[float]] = []
    for sq in squares.values():
        all_features.extend(sq.empty)
        all_features.extend(sq.white)
        all_features.extend(sq.black)

    if all_features:
        arr = np.asarray(all_features, dtype=np.float32)
        std = arr.std(axis=0)
        # avoid zero-std collapsing
        scale = np.where(std > 1e-3, std, 1.0)
    else:
        scale = np.ones(6, dtype=np.float32)

    import time

    return ExemplarConfig(
        feature_scale=[float(x) for x in scale],
        squares=squares,
        created_at=time.time(),
        dataset_name=dataset_name,
    )


def _all_square_names() -> list[str]:
    return [f"{c}{r}" for r in range(1, 9) for c in "abcdefgh"]


def _square_to_rc(square: str) -> tuple[int, int]:
    sq = square.lower()
    col = ord(sq[0]) - ord("a")
    row = 8 - int(sq[1])
    return row, col
