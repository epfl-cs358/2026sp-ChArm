"""Arm-driven labeled-data capture for the per-square exemplar classifier.

Storage layout under ``python_code/labeled_datasets/<name>/``:

    metadata.json            — name, created/updated, settings, progress
    empty/frame_0.jpg ...    — N frames of the empty board (warped)
    white/<sq>/frame_0.jpg   — N frames of a white piece at <sq>
    black/<sq>/frame_0.jpg   — N frames of a black piece at <sq>
    exemplar_config.json     — produced by compute_stats (per-square features)
    accuracy.json            — produced by compute_stats (per-square LOO accuracy)
"""

from __future__ import annotations

import json
import re
import shutil
import time
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

    def write_empty_frames(self, name: str, frames: list[np.ndarray]) -> int:
        """Overwrite empty frames with a fresh batch and return count saved."""
        d = self.empty_dir(name)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frames):
            cv2.imwrite(str(d / f"frame_{i}.jpg"), frame)
        meta = self.load(name)
        meta.empty_frames = len(frames)
        self.save(meta)
        return len(frames)

    def write_square_frames(
        self,
        name: str,
        color: str,
        square: str,
        frames: list[np.ndarray],
    ) -> int:
        """Overwrite frames for a (color, square) cell. Used for first capture and retake."""
        d = self.square_dir(name, color, square)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frames):
            cv2.imwrite(str(d / f"frame_{i}.jpg"), frame)
        meta = self.load(name)
        bucket = meta.white if color == "white" else meta.black
        bucket[square.lower()] = len(frames)
        # invalidate downstream artifacts since data changed
        meta.has_exemplar_config = False
        meta.has_accuracy = False
        self.save(meta)
        return len(frames)

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


def _check_square(square: str) -> str:
    sq = square.lower().strip()
    if sq not in SQUARES:
        raise ValueError(f"Invalid square: {square}")
    return sq
