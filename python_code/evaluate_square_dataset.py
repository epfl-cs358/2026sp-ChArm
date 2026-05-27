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

from charm.vision.calibrated_pipeline import run_calibrated_board_pipeline
from charm.vision.grid_splitter import extract_8x8_cells
from charm.vision.occupancy_detector import compute_occupancy_score
from charm.vision.piece_color_detector import compute_piece_brightness_score


LABELS = ("black", "empty", "white")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate full-board photos organized as root/{black,empty,white}/{a1..h8}/images. "
            "Only the square named by the folder is scored."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Dataset root containing black/, empty/, and white/ folders.",
    )
    parser.add_argument(
        "--board-calibration-json",
        type=Path,
        default=ROOT / "board_calibration.json",
        help="Board corner calibration JSON.",
    )
    parser.add_argument(
        "--inner-warp-json",
        type=Path,
        default=ROOT / "inner_warp_calibration.json",
        help="Inner warp calibration JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "e2e_debug" / "square_dataset_eval",
        help="Output folder for debug files and report.json.",
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
    return parser.parse_args()


def square_to_row_col(square: str) -> tuple[int, int]:
    if len(square) != 2:
        raise ValueError(f"Invalid square name: {square}")

    file_char = square[0].lower()
    rank_char = square[1]

    if file_char < "a" or file_char > "h" or rank_char < "1" or rank_char > "8":
        raise ValueError(f"Invalid square name: {square}")

    col = ord(file_char) - ord("a")
    row = 8 - int(rank_char)
    return row, col


def iter_examples(dataset_dir: Path):
    for expected_label in LABELS:
        label_dir = dataset_dir / expected_label
        if not label_dir.exists():
            continue

        if expected_label == "empty":
            for image_path in sorted(label_dir.rglob("*")):
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES:
                    yield expected_label, None, image_path
            continue

        for square_dir in sorted(p for p in label_dir.iterdir() if p.is_dir()):
            square = square_dir.name.lower()
            for image_path in sorted(square_dir.rglob("*")):
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES:
                    yield expected_label, square, image_path


def classify_cell(
    cell_image,
    occupancy_threshold: float,
    white_threshold: float,
    black_threshold: float,
) -> tuple[str, float, float]:
    occupancy_score = compute_occupancy_score(cell_image)
    if occupancy_score <= occupancy_threshold:
        return "empty", occupancy_score, 0.0

    color_score = compute_piece_brightness_score(cell_image)
    if color_score >= white_threshold:
        return "white", occupancy_score, color_score
    if color_score <= black_threshold:
        return "black", occupancy_score, color_score
    return "unknown", occupancy_score, color_score


def cell_map(refined_warp_path: Path) -> dict[tuple[int, int], Any]:
    image = cv2.imread(str(refined_warp_path))
    if image is None:
        raise FileNotFoundError(f"Could not read refined warp: {refined_warp_path}")
    return {(cell.row, cell.col): cell for cell in extract_8x8_cells(image)}


def expected_label_for_square(target_label: str, target_square: str | None, row: int, col: int) -> str:
    if target_label == "empty":
        return "empty"

    if target_square is None:
        return "empty"

    target_row, target_col = square_to_row_col(target_square)
    if (row, col) == (target_row, target_col):
        return target_label
    return "empty"


def main() -> None:
    args = parse_args()
    examples = list(iter_examples(args.dataset_dir))
    if not examples:
        raise FileNotFoundError(
            f"No images found under {args.dataset_dir}/{{black,empty,white}}/{{a1..h8}}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    confusion = {
        expected: {predicted: 0 for predicted in LABELS}
        for expected in LABELS
    }
    rows: list[dict[str, Any]] = []
    correct = 0
    occupancy_correct = 0

    for index, (target_label, target_square, image_path) in enumerate(examples, start=1):
        square_part = target_square if target_square is not None else "all_empty"
        run_dir = args.output_dir / f"{index:03d}_{target_label}_{square_part}_{image_path.stem}"

        calibrated = run_calibrated_board_pipeline(
            raw_image_path=image_path,
            four_point_calibration_path=args.board_calibration_json,
            inner_warp_calibration_path=args.inner_warp_json,
            output_dir=run_dir,
            name_prefix=f"{expected}_{square}_{image_path.stem}",
        )

        cells = cell_map(calibrated.refined_warp_path)
        scored_squares = (
            [square_to_row_col(target_square)]
            if target_square is not None
            else [(row, col) for row in range(8) for col in range(8)]
        )

        image_correct = True
        image_rows = []

        for row, col in scored_squares:
            expected = expected_label_for_square(target_label, target_square, row, col)
            predicted, occupancy_score, color_score = classify_cell(
                cells[(row, col)].image,
                args.occupancy_threshold,
                args.white_threshold,
                args.black_threshold,
            )

            is_correct = predicted == expected
            image_correct = image_correct and is_correct
            correct += int(is_correct)
            confusion[expected][predicted] += 1

            expected_occupied = expected != "empty"
            predicted_occupied = predicted != "empty"
            occupancy_match = expected_occupied == predicted_occupied
            occupancy_correct += int(occupancy_match)

            image_rows.append(
                {
                    "square": f"{chr(ord('a') + col)}{8 - row}",
                    "row": row,
                    "col": col,
                    "expected": expected,
                    "predicted": predicted,
                    "correct": is_correct,
                    "occupancy_correct": occupancy_match,
                    "occupancy_score": round(occupancy_score, 4),
                    "color_score": round(color_score, 4),
                }
            )

        rows.append(
            {
                "image": str(image_path),
                "target_label": target_label,
                "target_square": target_square,
                "correct": image_correct,
                "run_dir": str(run_dir),
                "occupancy_debug": str(calibrated.occupancy_debug_path),
                "piece_color_debug": str(calibrated.piece_color_debug_path),
                "squares": image_rows,
            }
        )

        status = "OK" if image_correct else "WRONG"
        print(f"[{index:03d}/{len(examples):03d}] {target_label}/{square_part}/{image_path.name}: {status}")

    total = sum(len(row["squares"]) for row in rows)
    summary = {
        "dataset_dir": str(args.dataset_dir),
        "total": total,
        "accuracy": correct / total if total else None,
        "occupancy_accuracy": occupancy_correct / total if total else None,
        "occupancy_threshold": args.occupancy_threshold,
        "white_threshold": args.white_threshold,
        "black_threshold": args.black_threshold,
        "confusion": confusion,
    }
    report = {
        "summary": summary,
        "rows": rows,
    }

    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(json.dumps(summary, indent=2))
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
