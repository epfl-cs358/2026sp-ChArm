from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.occupancy_detector import compute_occupancy_score
from charm.vision.piece_color_detector import compute_piece_brightness_score


LABELS = ("black", "empty", "white")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate current CV scoring on a cell dataset organized as "
            "root/black, root/empty, root/white."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Dataset root containing black/, empty/, and white/ folders.",
    )
    parser.add_argument(
        "--occupancy-threshold",
        type=float,
        default=9.0,
        help="Threshold for occupied vs empty.",
    )
    parser.add_argument(
        "--white-threshold",
        type=float,
        default=80.0,
        help="Piece color threshold for white.",
    )
    parser.add_argument(
        "--black-threshold",
        type=float,
        default=80.0,
        help="Piece color threshold for black.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "e2e_debug" / "cell_dataset_eval.json",
        help="Path to write detailed JSON report.",
    )
    return parser.parse_args()


def iter_images(dataset_dir: Path):
    for label in LABELS:
        label_dir = dataset_dir / label
        if not label_dir.exists():
            continue
        for path in sorted(label_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                yield label, path


def classify_cell(
    image,
    occupancy_threshold: float,
    white_threshold: float,
    black_threshold: float,
) -> tuple[str, float, float]:
    occupancy_score = compute_occupancy_score(image)
    if occupancy_score <= occupancy_threshold:
        return "empty", occupancy_score, 0.0

    color_score = compute_piece_brightness_score(image)
    if color_score >= white_threshold:
        return "white", occupancy_score, color_score
    if color_score <= black_threshold:
        return "black", occupancy_score, color_score
    return "unknown", occupancy_score, color_score


def main() -> None:
    args = parse_args()

    rows: list[dict[str, Any]] = []
    confusion = {
        expected: {predicted: 0 for predicted in (*LABELS, "unknown")}
        for expected in LABELS
    }

    total = 0
    correct = 0
    occupancy_total = 0
    occupancy_correct = 0

    for expected, path in iter_images(args.dataset_dir):
        image = cv2.imread(str(path))
        if image is None:
            rows.append(
                {
                    "path": str(path),
                    "expected": expected,
                    "error": "could not read image",
                }
            )
            continue

        predicted, occupancy_score, color_score = classify_cell(
            image,
            args.occupancy_threshold,
            args.white_threshold,
            args.black_threshold,
        )

        total += 1
        is_correct = predicted == expected
        correct += int(is_correct)
        confusion[expected][predicted] += 1

        expected_occupied = expected != "empty"
        predicted_occupied = predicted != "empty"
        occupancy_total += 1
        occupancy_correct += int(expected_occupied == predicted_occupied)

        rows.append(
            {
                "path": str(path),
                "expected": expected,
                "predicted": predicted,
                "correct": is_correct,
                "occupancy_score": round(occupancy_score, 4),
                "color_score": round(color_score, 4),
            }
        )

    summary = {
        "dataset_dir": str(args.dataset_dir),
        "total": total,
        "accuracy": correct / total if total else None,
        "occupancy_accuracy": occupancy_correct / occupancy_total
        if occupancy_total
        else None,
        "occupancy_threshold": args.occupancy_threshold,
        "white_threshold": args.white_threshold,
        "black_threshold": args.black_threshold,
        "confusion": confusion,
    }

    report = {
        "summary": summary,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
