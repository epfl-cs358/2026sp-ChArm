"""Convert a labeling-wizard dataset into a CNN training dataset.

Source layout (produced by the existing labeling wizard at
webapp_backend/labeling.py):

    labeled_datasets/<source>/
        empty/frame_*.jpg
        white/<sq>/frame_*.jpg     # one piece on <sq>, rest empty
        black/<sq>/frame_*.jpg

Output layout consumed by tf.keras.utils.image_dataset_from_directory:

    labeled_datasets/cnn_<output>/
        train/{empty,white,black}/<uuid>.png   (~85%)
        val/  /{empty,white,black}/<uuid>.png  (~15%)

Each captured frame is warped through the two-stage calibration, split into
64 cells (100x100 each at warp_size=800), and labelled per-cell from the
source folder's ground truth.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

import cv2

from charm.vision.calibration_config import (
    DEFAULT_BOARD_CALIBRATION_JSON,
    DEFAULT_INNER_WARP_CALIBRATION_JSON,
)
from charm.vision.four_point_calibration import (
    load_four_point_calibration,
    load_inner_warp_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)
from charm.vision.grid_splitter import extract_8x8_cells

WARP_SIZE = 800
LABELED_DATASETS_ROOT = Path(__file__).resolve().parents[3] / "labeled_datasets"

CLASSES = ("empty", "white", "black")


@dataclass
class CnnBuildProgress:
    frames_done: int
    frames_total: int
    current_file: str
    cells_written_by_class: dict[str, int] = field(default_factory=dict)


@dataclass
class CnnBuildReport:
    output_dir: Path
    counts_train: dict[str, int]
    counts_val: dict[str, int]


def _square_to_rc(square: str) -> tuple[int, int]:
    sq = square.lower().strip()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise ValueError(f"Invalid square name: {square}")
    col = ord(sq[0]) - ord("a")
    row = 8 - int(sq[1])
    return row, col


def _iter_source_frames(source_root: Path) -> Iterable[tuple[Path, str, Optional[str]]]:
    """Yield (frame_path, kind, square) for every capture in the source folder.

    kind ∈ {"empty", "white", "black"}; square is None when kind == "empty".
    """
    empty_dir = source_root / "empty"
    if empty_dir.exists():
        for f in sorted(empty_dir.glob("*.jpg")):
            yield f, "empty", None

    for piece_kind in ("white", "black"):
        piece_dir = source_root / piece_kind
        if not piece_dir.exists():
            continue
        for square_dir in sorted(piece_dir.iterdir()):
            if not square_dir.is_dir():
                continue
            for f in sorted(square_dir.glob("*.jpg")):
                yield f, piece_kind, square_dir.name


def _count_source_frames(source_root: Path) -> int:
    return sum(1 for _ in _iter_source_frames(source_root))


def _ensure_output_layout(output_root: Path) -> None:
    for split in ("train", "val"):
        for cls in CLASSES:
            (output_root / split / cls).mkdir(parents=True, exist_ok=True)


def _label_for_cell(
    row: int, col: int, kind: str, target_square: Optional[str]
) -> str:
    """Return the class label for one cell of one frame."""
    if kind == "empty":
        return "empty"
    if target_square is None:
        # Should never happen for kind in {white, black}, but be safe.
        return "empty"
    target_row, target_col = _square_to_rc(target_square)
    if row == target_row and col == target_col:
        return kind
    return "empty"


def build_cnn_dataset(
    source_dataset_name: str,
    output_dataset_name: str,
    val_split: float = 0.15,
    progress_cb: Optional[Callable[[CnnBuildProgress], None]] = None,
) -> CnnBuildReport:
    """Iterate every source frame, warp, split, label, and write per-cell PNGs."""
    if not (0.0 <= val_split <= 1.0):
        raise ValueError(f"val_split must be in [0, 1], got {val_split}")

    source_root = LABELED_DATASETS_ROOT / source_dataset_name
    if not source_root.exists():
        raise FileNotFoundError(f"Source dataset not found: {source_root}")

    output_name = output_dataset_name
    if not output_name.startswith("cnn_"):
        output_name = f"cnn_{output_name}"
    output_root = LABELED_DATASETS_ROOT / output_name
    _ensure_output_layout(output_root)

    board_cal = load_four_point_calibration(DEFAULT_BOARD_CALIBRATION_JSON)
    inner_cal = load_inner_warp_calibration(DEFAULT_INNER_WARP_CALIBRATION_JSON)

    frames_total = _count_source_frames(source_root)
    counts_train: dict[str, int] = {c: 0 for c in CLASSES}
    counts_val: dict[str, int] = {c: 0 for c in CLASSES}

    rng = random.Random(0xC4A2)  # deterministic split

    frames_done = 0
    for frame_path, kind, target_square in _iter_source_frames(source_root):
        raw = cv2.imread(str(frame_path))
        if raw is None:
            frames_done += 1
            continue

        first = warp_from_calibration(raw, board_cal, output_size=WARP_SIZE)
        refined = refine_board_with_inner_corners(first, inner_cal, output_size=WARP_SIZE)
        cells = extract_8x8_cells(refined)

        for cell in cells:
            label = _label_for_cell(cell.row, cell.col, kind, target_square)
            split = "val" if rng.random() < val_split else "train"
            out_dir = output_root / split / label
            out_path = out_dir / f"{uuid.uuid4().hex}.png"
            cv2.imwrite(str(out_path), cell.image)
            if split == "train":
                counts_train[label] += 1
            else:
                counts_val[label] += 1

        frames_done += 1
        if progress_cb is not None:
            progress_cb(CnnBuildProgress(
                frames_done=frames_done,
                frames_total=frames_total,
                current_file=str(frame_path.relative_to(source_root)),
                cells_written_by_class={
                    c: counts_train[c] + counts_val[c] for c in CLASSES
                },
            ))

    return CnnBuildReport(
        output_dir=output_root,
        counts_train=counts_train,
        counts_val=counts_val,
    )
