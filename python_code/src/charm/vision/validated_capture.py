"""Save 64-cell crops of a *validated* board scan into a fixed dataset.

Triggered after the CV router confirms a scan corresponds to a legal move (or
a valid initial position). Each per-square crop is written to::

    labeled_datasets/<dataset_name>/bulk/<class>/<square>/cell_<uuid>.jpg

…which is the same on-disk schema the rest of the codebase (``cnn_dataset``,
``webapp_backend/labeling.py``) already reads, so the data can be fed straight
into ``train_standalone.py`` later.

A chronological ``metadata.json`` is appended to so the user can audit recent
captures without scanning every subdirectory.

The capture is best-effort: any I/O failure is logged and swallowed — a save
problem must never block a game.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np


LABELED_DATASETS_ROOT = Path(__file__).resolve().parents[3] / "labeled_datasets"

logger = logging.getLogger(__name__)


@dataclass
class CaptureSummary:
    dataset_path: Path
    saved: bool
    counts: dict[str, int]   # {"empty": n, "white": n, "black": n}
    error: Optional[str] = None


def _rc_to_square(row: int, col: int) -> str:
    """Inverse of charm.vision.cnn_dataset._square_to_rc.

    The lab camera is mounted 180° rotated from the white-at-bottom chess view:
    rank 1 appears at the top of the image and file h appears at the left.
    The previous convention (row 0 = rank 8, col 0 = file a) wrote cells into
    folders named for the diagonally-opposite square, so a cell that physically
    held a white pawn at h2 was saved under bulk/white/a7/. cnn_dataset already
    encodes the correct mapping; this helper now mirrors it so the training set
    folder names match the physical squares.
    """
    file_ch = chr(ord("a") + (7 - col))
    rank_ch = str(row + 1)
    return file_ch + rank_ch


def _label_at(row: int, col: int, white_bitmap, black_bitmap) -> str:
    if white_bitmap[row][col]:
        return "white"
    if black_bitmap[row][col]:
        return "black"
    return "empty"


def _load_meta(meta_path: Path, name: str) -> dict[str, Any]:
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception as exc:
            logger.warning("Could not parse %s — starting fresh: %s", meta_path, exc)
    now = time.time()
    return {
        "name": name,
        "created_at": now,
        "updated_at": now,
        "schema": "bulk_per_square_v1",
        "source": "cv_router.validated_capture",
        "captures": [],
        "bulk_empty": {},
        "bulk_white": {},
        "bulk_black": {},
    }


def _bump_bucket(meta: dict, label: str, square: str) -> None:
    key = {"empty": "bulk_empty", "white": "bulk_white", "black": "bulk_black"}.get(label)
    if key is None:
        return
    bucket = meta.setdefault(key, {})
    bucket[square] = bucket.get(square, 0) + 1


def save_validated_capture(
    refined_image: np.ndarray,
    white_bitmap_image_orient: list[list[int]],
    black_bitmap_image_orient: list[list[int]],
    move_uci: Optional[str],
    mode_used: str,
    session_id: Optional[str] = None,
    dataset_name: str = "validated_live",
    datasets_root: Path = LABELED_DATASETS_ROOT,
) -> CaptureSummary:
    """Slice ``refined_image`` into 64 cells and save each into the right class folder.

    The two bitmaps are expected in **image orientation** (row 0 = top of image
    = rank 8 from white's POV). Callers that hold bitmaps in chess-orientation
    after a 180° flip must un-flip before calling this — see api_server's
    integration for an example.
    """
    dataset_dir = datasets_root / dataset_name
    bulk_dir = dataset_dir / "bulk"
    meta_path = dataset_dir / "metadata.json"

    counts = {"empty": 0, "white": 0, "black": 0}
    try:
        h, w = refined_image.shape[:2]
        if h < 8 or w < 8:
            raise ValueError(f"refined_image too small: {h}x{w}")
        cell_h, cell_w = h // 8, w // 8

        bulk_dir.mkdir(parents=True, exist_ok=True)
        meta = _load_meta(meta_path, dataset_name)
        capture_id = uuid.uuid4().hex

        for row in range(8):
            for col in range(8):
                label = _label_at(row, col, white_bitmap_image_orient, black_bitmap_image_orient)
                square = _rc_to_square(row, col)
                y1, x1 = row * cell_h, col * cell_w
                y2, x2 = y1 + cell_h, x1 + cell_w
                cell_img = refined_image[y1:y2, x1:x2]
                # Normalize to 100x100 to match existing dataset
                if cell_img.shape[0] != 100 or cell_img.shape[1] != 100:
                    cell_img = cv2.resize(cell_img, (100, 100), interpolation=cv2.INTER_AREA)

                target_dir = bulk_dir / label / square
                target_dir.mkdir(parents=True, exist_ok=True)
                fname = target_dir / f"cell_{capture_id}_{square}.jpg"
                ok = cv2.imwrite(str(fname), cell_img)
                if not ok:
                    logger.warning("cv2.imwrite returned false for %s", fname)
                    continue
                counts[label] += 1
                _bump_bucket(meta, label, square)

        meta["updated_at"] = time.time()
        meta.setdefault("captures", []).append(
            {
                "ts": time.time(),
                "iso": datetime.now(timezone.utc).isoformat(),
                "capture_id": capture_id,
                "mode_used": mode_used,
                "session_id": session_id,
                "move_uci": move_uci,
                "counts": dict(counts),
            }
        )
        # Atomic write: write to a tmp sibling then rename. Protects against a
        # racing writer corrupting the file if both the webapp and play_game.py
        # are saving into the same dataset.
        tmp_path = meta_path.with_suffix(meta_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(meta, indent=2))
        tmp_path.replace(meta_path)

        return CaptureSummary(dataset_path=dataset_dir, saved=True, counts=counts)
    except Exception as exc:
        logger.exception("validated_capture failed for dataset %s", dataset_name)
        return CaptureSummary(dataset_path=dataset_dir, saved=False, counts=counts, error=str(exc))


def unflip_bitmap_180(b: list[list[int]]) -> list[list[int]]:
    """Reverse a 180° flip applied to an 8x8 bitmap.

    Useful when the caller has bitmaps in chess-orientation (post-flip) and
    needs to align them back to image-orientation for cell extraction.
    """
    return [list(reversed(row)) for row in reversed(b)]
