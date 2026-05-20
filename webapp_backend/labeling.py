"""Arm-driven labeled-data capture for the per-square exemplar classifier.

Storage layout under ``python_code/labeled_datasets/<name>/``:

    metadata.json            — name, created/updated, settings, progress
    empty/frame_0.jpg ...    — N frames of the empty board (warped)
    white/<sq>/frame_0.jpg   — N frames of a white piece at <sq>
    black/<sq>/frame_0.jpg   — N frames of a black piece at <sq>
    bulk/<color>/<sq>/cell_*.jpg
                             — single-cell crops (100x100) from bulk-paint
                               sessions where many squares are labeled from
                               one capture. color ∈ {empty, white, black}.
    exemplar_config.json     — produced by compute_stats (per-square features)
    accuracy.json            — produced by compute_stats (per-square LOO accuracy)
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np


SQUARES: list[str] = [f"{c}{r}" for r in range(1, 9) for c in "abcdefgh"]
SAFE_NAME = re.compile(r"^[A-Za-z0-9_\- ]+$")


def square_to_rc(square: str) -> tuple[int, int]:
    """Map chess square (e.g. 'h8') to (row, col) in the warped image grid.

    Row 0 is the top of the image (rank 8); col 0 is the left of the image
    (file a). This matches the convention used by extract_8x8_cells in the
    existing pipeline.
    """
    sq = square.lower().strip()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise ValueError(f"Invalid square: {square}")
    col = ord(sq[0]) - ord("a")
    row = 8 - int(sq[1])
    return row, col


def _safe_name(name: str) -> str:
    name = name.strip()
    if not name or not SAFE_NAME.match(name):
        raise ValueError(
            "Dataset name must be 1-64 chars from [A-Za-z0-9 _-]"
        )
    return name


@dataclass
class DatasetSettings:
    """User-applied capture settings for a dataset session."""

    frames_per_square: int = 5
    settle_ms: int = 600
    source_square: str = "h8"
    piece_type: str = "pawn"
    lighting_note: str = ""

    def to_json(self) -> dict:
        return {
            "frames_per_square": int(self.frames_per_square),
            "settle_ms": int(self.settle_ms),
            "source_square": self.source_square,
            "piece_type": self.piece_type,
            "lighting_note": self.lighting_note,
        }

    @classmethod
    def from_json(cls, data: dict) -> "DatasetSettings":
        return cls(
            frames_per_square=int(data.get("frames_per_square", 5)),
            settle_ms=int(data.get("settle_ms", 600)),
            source_square=str(data.get("source_square", "h8")),
            piece_type=str(data.get("piece_type", "pawn")),
            lighting_note=str(data.get("lighting_note", "")),
        )


@dataclass
class DatasetMetadata:
    """On-disk metadata.json. Tracks progress per (color, square)."""

    name: str
    created_at: float
    updated_at: float
    settings: DatasetSettings
    empty_frames: int = 0
    white: dict[str, int] = field(default_factory=dict)
    black: dict[str, int] = field(default_factory=dict)
    # Per-square counts of single-cell crops captured via bulk paint.
    bulk_empty: dict[str, int] = field(default_factory=dict)
    bulk_white: dict[str, int] = field(default_factory=dict)
    bulk_black: dict[str, int] = field(default_factory=dict)
    has_exemplar_config: bool = False
    has_accuracy: bool = False

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "settings": self.settings.to_json(),
            "empty_frames": self.empty_frames,
            "white": self.white,
            "black": self.black,
            "bulk_empty": self.bulk_empty,
            "bulk_white": self.bulk_white,
            "bulk_black": self.bulk_black,
            "has_exemplar_config": self.has_exemplar_config,
            "has_accuracy": self.has_accuracy,
        }

    @classmethod
    def from_json(cls, data: dict) -> "DatasetMetadata":
        return cls(
            name=data["name"],
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            settings=DatasetSettings.from_json(data.get("settings", {})),
            empty_frames=int(data.get("empty_frames", 0)),
            white={k: int(v) for k, v in data.get("white", {}).items()},
            black={k: int(v) for k, v in data.get("black", {}).items()},
            bulk_empty={k: int(v) for k, v in data.get("bulk_empty", {}).items()},
            bulk_white={k: int(v) for k, v in data.get("bulk_white", {}).items()},
            bulk_black={k: int(v) for k, v in data.get("bulk_black", {}).items()},
            has_exemplar_config=bool(data.get("has_exemplar_config", False)),
            has_accuracy=bool(data.get("has_accuracy", False)),
        )


class DatasetStore:
    """Filesystem-backed dataset registry."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def dataset_dir(self, name: str) -> Path:
        return self.root / _safe_name(name)

    def metadata_path(self, name: str) -> Path:
        return self.dataset_dir(name) / "metadata.json"

    def exists(self, name: str) -> bool:
        return self.metadata_path(name).exists()

    def list(self) -> list[DatasetMetadata]:
        out: list[DatasetMetadata] = []
        for child in sorted(self.root.iterdir()):
            mp = child / "metadata.json"
            if not mp.exists():
                continue
            try:
                out.append(DatasetMetadata.from_json(json.loads(mp.read_text())))
            except Exception:
                continue
        return out

    def load(self, name: str) -> DatasetMetadata:
        mp = self.metadata_path(name)
        if not mp.exists():
            raise FileNotFoundError(f"Dataset not found: {name}")
        return DatasetMetadata.from_json(json.loads(mp.read_text()))

    def save(self, meta: DatasetMetadata) -> None:
        meta.updated_at = time.time()
        d = self.dataset_dir(meta.name)
        d.mkdir(parents=True, exist_ok=True)
        self.metadata_path(meta.name).write_text(json.dumps(meta.to_json(), indent=2))

    def create(self, name: str, settings: DatasetSettings) -> DatasetMetadata:
        name = _safe_name(name)
        if self.exists(name):
            raise FileExistsError(f"Dataset already exists: {name}")
        now = time.time()
        meta = DatasetMetadata(
            name=name,
            created_at=now,
            updated_at=now,
            settings=settings,
        )
        self.save(meta)
        return meta

    def delete(self, name: str) -> None:
        d = self.dataset_dir(name)
        if not d.exists():
            return
        shutil.rmtree(d, ignore_errors=True)

    # --------- frame storage ---------

    def empty_dir(self, name: str) -> Path:
        return self.dataset_dir(name) / "empty"

    def square_dir(self, name: str, color: str, square: str) -> Path:
        color = _check_color(color)
        sq = _check_square(square)
        return self.dataset_dir(name) / color / sq

    def _next_frame_index(self, d: Path) -> int:
        if not d.exists():
            return 0
        existing = [p for p in d.iterdir() if p.is_file() and p.suffix == ".jpg"]
        return len(existing)

    def write_empty_frames(
        self,
        name: str,
        frames: list[np.ndarray],
        mode: str = "overwrite",
    ) -> int:
        """Write empty frames; mode ∈ {"overwrite", "append"}.

        Returns the number of frames just written. The metadata count reflects
        the total frames on disk after the write.
        """
        d = self.empty_dir(name)
        if mode == "overwrite" and d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        start = self._next_frame_index(d) if mode == "append" else 0
        for i, frame in enumerate(frames):
            cv2.imwrite(str(d / f"frame_{start + i}.jpg"), frame)
        meta = self.load(name)
        meta.empty_frames = self._next_frame_index(d)
        self.save(meta)
        return len(frames)

    def write_square_frames(
        self,
        name: str,
        color: str,
        square: str,
        frames: list[np.ndarray],
        mode: str = "overwrite",
    ) -> int:
        """Write frames for a (color, square) cell.

        mode ∈ {"overwrite", "append"}. Retakes use "overwrite"; add-more-data
        flows use "append" so existing frames are preserved and new ones are
        suffixed with the next available index.
        """
        d = self.square_dir(name, color, square)
        if mode == "overwrite" and d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        start = self._next_frame_index(d) if mode == "append" else 0
        for i, frame in enumerate(frames):
            cv2.imwrite(str(d / f"frame_{start + i}.jpg"), frame)
        meta = self.load(name)
        bucket = meta.white if color == "white" else meta.black
        bucket[square.lower()] = self._next_frame_index(d)
        # invalidate downstream artifacts since data changed
        meta.has_exemplar_config = False
        meta.has_accuracy = False
        self.save(meta)
        return len(frames)

    # --------- bulk-paint cell storage ---------

    def bulk_dir(self, name: str, color: str, square: str) -> Path:
        color = _check_bulk_color(color)
        sq = _check_square(square)
        return self.dataset_dir(name) / "bulk" / color / sq

    def write_bulk_cells(
        self,
        name: str,
        labels: dict[str, str],
        cells_by_square: dict[str, np.ndarray],
    ) -> dict[str, int]:
        """Append single-cell crops to ``bulk/<color>/<sq>/`` for each label.

        ``labels`` maps square → "empty" | "white" | "black". ``cells_by_square``
        maps square → 100x100 BGR image (the warped board's per-cell crop).
        Squares missing from either dict are skipped silently. Returns a dict
        ``{"empty": n, "white": n, "black": n}`` of cells just written.
        """
        meta = self.load(name)
        written = {"empty": 0, "white": 0, "black": 0}
        for sq, label in labels.items():
            label = label.lower().strip()
            if label not in ("empty", "white", "black"):
                continue
            cell = cells_by_square.get(sq)
            if cell is None:
                continue
            d = self.bulk_dir(name, label, sq)
            d.mkdir(parents=True, exist_ok=True)
            fname = d / f"cell_{uuid.uuid4().hex}.jpg"
            cv2.imwrite(str(fname), cell)
            written[label] += 1
            bucket = (
                meta.bulk_empty
                if label == "empty"
                else meta.bulk_white
                if label == "white"
                else meta.bulk_black
            )
            bucket[sq] = bucket.get(sq, 0) + 1
        if any(written.values()):
            meta.has_exemplar_config = False
            meta.has_accuracy = False
            self.save(meta)
        return written

    def iter_bulk_cells(
        self, name: str, color: str
    ) -> Iterable[tuple[str, np.ndarray]]:
        """Yield (square, cell_image) for every bulk cell of the given color."""
        color = _check_bulk_color(color)
        base = self.dataset_dir(name) / "bulk" / color
        if not base.exists():
            return
        for sq_dir in sorted(base.iterdir()):
            if not sq_dir.is_dir():
                continue
            sq = sq_dir.name
            for p in sorted(sq_dir.iterdir()):
                if p.suffix != ".jpg":
                    continue
                img = cv2.imread(str(p))
                if img is not None:
                    yield sq, img

    def read_square_first_frame(
        self, name: str, color: str, square: str
    ) -> Optional[np.ndarray]:
        d = self.square_dir(name, color, square)
        if not d.exists():
            return None
        files = sorted(p for p in d.iterdir() if p.suffix == ".jpg")
        if not files:
            return None
        return cv2.imread(str(files[0]))

    def read_empty_first_frame(self, name: str) -> Optional[np.ndarray]:
        d = self.empty_dir(name)
        if not d.exists():
            return None
        files = sorted(p for p in d.iterdir() if p.suffix == ".jpg")
        if not files:
            return None
        return cv2.imread(str(files[0]))

    # --------- bulk frame iteration (used by stats) ---------

    def iter_empty_frames(self, name: str) -> Iterable[np.ndarray]:
        d = self.empty_dir(name)
        if not d.exists():
            return
        for p in sorted(d.iterdir()):
            if p.suffix != ".jpg":
                continue
            img = cv2.imread(str(p))
            if img is not None:
                yield img

    def iter_square_frames(
        self, name: str, color: str, square: str
    ) -> Iterable[np.ndarray]:
        d = self.square_dir(name, color, square)
        if not d.exists():
            return
        for p in sorted(d.iterdir()):
            if p.suffix != ".jpg":
                continue
            img = cv2.imread(str(p))
            if img is not None:
                yield img


def _check_color(color: str) -> str:
    c = color.lower().strip()
    if c not in ("white", "black"):
        raise ValueError(f"Invalid color: {color}")
    return c


def _check_bulk_color(color: str) -> str:
    c = color.lower().strip()
    if c not in ("empty", "white", "black"):
        raise ValueError(f"Invalid bulk color: {color}")
    return c


def _check_square(square: str) -> str:
    sq = square.lower().strip()
    if sq not in SQUARES:
        raise ValueError(f"Invalid square: {square}")
    return sq
