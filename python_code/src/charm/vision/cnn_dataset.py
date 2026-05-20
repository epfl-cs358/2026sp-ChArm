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

from charm.vision.grid_splitter import extract_8x8_cells

WARP_SIZE = 800
LABELED_DATASETS_ROOT = Path(__file__).resolve().parents[3] / "labeled_datasets"

CLASSES = ("empty", "white", "black")
# Sampling defaults. The empty class is still gated by class_weight at train
# time, so we keep more of it now — earlier 0.10 was throwing away most of
# the light-square diversity, which made white false-positives common. 0.30
# is a good balance: a 5-frame empty session contributes ~96 empty cells
# (5×64×0.30) which is plenty without drowning out the piece classes.
DEFAULT_EMPTY_FRAME_SAMPLE_RATE = 0.30
DEFAULT_EMPTY_SAMPLES_WITH_PIECE = 3


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
    # The warped board image is 180° rotated from the white-at-bottom
    # convention: rank 1 appears at the top of the image, file h appears at
    # the left. Verified empirically against labeled captures (a1/a8/h8 all
    # show their pieces in the opposite corner from the standard mapping).
    sq = square.lower().strip()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise ValueError(f"Invalid square name: {square}")
    col = 7 - (ord(sq[0]) - ord("a"))
    row = int(sq[1]) - 1
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


def _iter_bulk_cells(source_root: Path) -> Iterable[tuple[Path, str]]:
    """Yield (cell_path, class_label) for every bulk-painted per-cell crop.

    Bulk-paint sessions save single-cell crops (already 100x100) under
    bulk/<class>/<sq>/cell_*.jpg, so we copy them straight into the CNN
    train/val split without re-cropping.
    """
    bulk_root = source_root / "bulk"
    if not bulk_root.exists():
        return
    for cls in CLASSES:
        cls_dir = bulk_root / cls
        if not cls_dir.exists():
            continue
        for sq_dir in sorted(cls_dir.iterdir()):
            if not sq_dir.is_dir():
                continue
            for f in sorted(sq_dir.glob("*.jpg")):
                yield f, cls


def _count_source_frames(source_root: Path) -> int:
    return sum(1 for _ in _iter_source_frames(source_root)) + sum(
        1 for _ in _iter_bulk_cells(source_root)
    )


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
    empty_frame_sample_rate: float = DEFAULT_EMPTY_FRAME_SAMPLE_RATE,
    empty_samples_with_piece: int = DEFAULT_EMPTY_SAMPLES_WITH_PIECE,
    progress_cb: Optional[Callable[[CnnBuildProgress], None]] = None,
) -> CnnBuildReport:
    """Iterate every source frame, split into 64 cells, label, and write PNGs.

    The labeling pipeline already saves 800x800 warped board frames, so this
    function skips the warp stage and goes straight to grid splitting.

    `empty_frame_sample_rate` is the fraction of empty squares saved from
    frames that contain no pieces.
    `empty_samples_with_piece` limits how many empty squares we save from a
    frame that contains a piece (the piece square is always saved).
    """
    if not (0.0 <= val_split <= 1.0):
        raise ValueError(f"val_split must be in [0, 1], got {val_split}")
    if not (0.0 <= empty_frame_sample_rate <= 1.0):
        raise ValueError(
            f"empty_frame_sample_rate must be in [0, 1], got {empty_frame_sample_rate}"
        )
    if empty_samples_with_piece < 0:
        raise ValueError(
            f"empty_samples_with_piece must be >= 0, got {empty_samples_with_piece}"
        )

    source_root = LABELED_DATASETS_ROOT / source_dataset_name
    if not source_root.exists():
        raise FileNotFoundError(f"Source dataset not found: {source_root}")

    output_name = output_dataset_name
    if not output_name.startswith("cnn_"):
        output_name = f"cnn_{output_name}"
    output_root = LABELED_DATASETS_ROOT / output_name
    _ensure_output_layout(output_root)

    # Remember which labeling dataset this CNN dataset was built from so
    # feedback ("actually empty") can append a bulk cell back to the source.
    import json
    (output_root / "source.json").write_text(
        json.dumps({"source_dataset": source_dataset_name}) + "\n"
    )

    frames_total = _count_source_frames(source_root)
    counts_train: dict[str, int] = {c: 0 for c in CLASSES}
    counts_val: dict[str, int] = {c: 0 for c in CLASSES}

    rng = random.Random(0xC4A2)  # deterministic split + empty sampling

    frames_done = 0
    for frame_path, kind, target_square in _iter_source_frames(source_root):
        warped = cv2.imread(str(frame_path))
        if warped is None:
            frames_done += 1
            continue

        cells = extract_8x8_cells(warped)
        piece_cells: list = []
        empty_cells: list = []
        for cell in cells:
            label = _label_for_cell(cell.row, cell.col, kind, target_square)
            if label == "empty":
                empty_cells.append(cell)
            else:
                piece_cells.append((cell, label))

        rng.shuffle(empty_cells)
        if kind == "empty":
            target = int(round(len(empty_cells) * empty_frame_sample_rate))
            target = max(0, min(len(empty_cells), target))
            chosen_empties = empty_cells[:target]
        else:
            target = min(len(empty_cells), empty_samples_with_piece)
            chosen_empties = empty_cells[:target]

        to_write: list[tuple[object, str]] = [(c, lbl) for c, lbl in piece_cells]
        to_write.extend((c, "empty") for c in chosen_empties)

        for cell, label in to_write:
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

    # Bulk-paint sessions contribute single-cell crops directly; no grid
    # splitting needed — just copy each cell into the chosen split.
    for cell_path, cls in _iter_bulk_cells(source_root):
        cell_img = cv2.imread(str(cell_path))
        if cell_img is None:
            frames_done += 1
            continue
        split = "val" if rng.random() < val_split else "train"
        out_dir = output_root / split / cls
        out_path = out_dir / f"{uuid.uuid4().hex}.png"
        cv2.imwrite(str(out_path), cell_img)
        if split == "train":
            counts_train[cls] += 1
        else:
            counts_val[cls] += 1
        frames_done += 1
        if progress_cb is not None:
            progress_cb(CnnBuildProgress(
                frames_done=frames_done,
                frames_total=frames_total,
                current_file=str(cell_path.relative_to(source_root)),
                cells_written_by_class={
                    c: counts_train[c] + counts_val[c] for c in CLASSES
                },
            ))

    return CnnBuildReport(
        output_dir=output_root,
        counts_train=counts_train,
        counts_val=counts_val,
    )
