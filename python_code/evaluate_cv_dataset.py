from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.calibrated_pipeline import run_calibrated_board_pipeline


LabelGrid = list[list[str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run current CV pipeline over a dataset and report accuracy when labels exist."
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        required=True,
        help="Folder containing raw board photos.",
    )
    parser.add_argument(
        "--glob",
        default="*.jpg",
        help="Image glob inside --images-dir. Example: '*.jpg' or 'photo_*.jpg'.",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=ROOT.parent / "color_annotations.json",
        help="Optional webapp color_annotations.json.",
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
        default=ROOT / "e2e_debug" / "dataset_eval",
        help="Output folder for per-image debug files and report.json.",
    )
    parser.add_argument("--thumb-size", type=int, default=300)
    parser.add_argument("--cols", type=int, default=4)
    return parser.parse_args()


def flat_to_grid(labels: list[str]) -> LabelGrid:
    if len(labels) != 64:
        raise ValueError("Expected exactly 64 labels.")
    return [labels[row * 8:(row + 1) * 8] for row in range(8)]


def load_annotations(path: Path) -> dict[str, LabelGrid]:
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    annotations: dict[str, LabelGrid] = {}

    for entry in raw:
        labels = flat_to_grid(entry["board_64"])
        keys = {
            str(entry.get("image_id", "")),
            str(entry.get("image_path", "")),
            Path(str(entry.get("image_path", ""))).name,
            Path(str(entry.get("image_id", ""))).name,
        }
        for key in keys:
            if key:
                annotations[key] = labels

    return annotations


def result_to_label_grid(white_bitmap: list[list[int]], black_bitmap: list[list[int]]) -> LabelGrid:
    labels = [["empty" for _ in range(8)] for _ in range(8)]

    for row in range(8):
        for col in range(8):
            if white_bitmap[row][col]:
                labels[row][col] = "white"
            elif black_bitmap[row][col]:
                labels[row][col] = "black"

    return labels


def occupancy_label(label: str) -> str:
    return "occupied" if label in {"white", "black"} else "empty"


def score_labels(predicted: LabelGrid, expected: LabelGrid) -> dict[str, Any]:
    total = 64
    color_correct = 0
    occupancy_correct = 0
    mismatches: list[dict[str, Any]] = []

    for row in range(8):
        for col in range(8):
            pred = predicted[row][col]
            exp = expected[row][col]

            if pred == exp:
                color_correct += 1
            else:
                mismatches.append(
                    {
                        "row": row,
                        "col": col,
                        "expected": exp,
                        "predicted": pred,
                    }
                )

            if occupancy_label(pred) == occupancy_label(exp):
                occupancy_correct += 1

    return {
        "color_accuracy": color_correct / total,
        "occupancy_accuracy": occupancy_correct / total,
        "color_correct": color_correct,
        "occupancy_correct": occupancy_correct,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def write_contact_sheet(image_paths: list[Path], output_path: Path, thumb_size: int, cols: int) -> None:
    if not image_paths:
        return

    label_h = 32
    rows = (len(image_paths) + cols - 1) // cols
    canvas = np.full((rows * (thumb_size + label_h), cols * thumb_size, 3), 28, dtype=np.uint8)

    for index, path in enumerate(image_paths):
        image = cv2.imread(str(path))
        if image is None:
            continue

        image = cv2.resize(image, (thumb_size, thumb_size), interpolation=cv2.INTER_AREA)
        row, col = divmod(index, cols)
        x = col * thumb_size
        y = row * (thumb_size + label_h)
        canvas[y:y + thumb_size, x:x + thumb_size] = image

        cv2.putText(
            canvas,
            path.stem[:42],
            (x + 6, y + thumb_size + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )

    cv2.imwrite(str(output_path), canvas)


def find_expected_labels(annotations: dict[str, LabelGrid], image_path: Path) -> LabelGrid | None:
    candidates = [
        str(image_path),
        image_path.name,
        image_path.stem,
    ]

    for key in candidates:
        if key in annotations:
            return annotations[key]

    return None


def main() -> None:
    args = parse_args()
    images = sorted(args.images_dir.glob(args.glob))
    if not images:
        raise FileNotFoundError(f"No images found: {args.images_dir / args.glob}")

    annotations = load_annotations(args.annotations)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "images_dir": str(args.images_dir),
        "glob": args.glob,
        "annotations": str(args.annotations),
        "board_calibration_json": str(args.board_calibration_json),
        "inner_warp_json": str(args.inner_warp_json),
        "images": [],
    }

    contact_images: list[Path] = []
    scored_images = 0
    color_correct = 0
    occupancy_correct = 0

    for index, image_path in enumerate(images, start=1):
        run_dir = args.output_dir / image_path.stem
        result = run_calibrated_board_pipeline(
            raw_image_path=image_path,
            four_point_calibration_path=args.board_calibration_json,
            inner_warp_calibration_path=args.inner_warp_json,
            output_dir=run_dir,
            name_prefix=image_path.stem,
        )

        collected_debug = args.output_dir / f"{index:03d}_{image_path.stem}_piece_color_debug.png"
        shutil.copy2(result.piece_color_debug_path, collected_debug)
        contact_images.append(collected_debug)

        pipeline_result = result.pipeline_result
        predicted = result_to_label_grid(
            pipeline_result.white_bitmap,
            pipeline_result.black_bitmap,
        )
        expected = find_expected_labels(annotations, image_path)
        score = score_labels(predicted, expected) if expected is not None else None

        if score is not None:
            scored_images += 1
            color_correct += score["color_correct"]
            occupancy_correct += score["occupancy_correct"]

        entry = {
            "image": str(image_path),
            "run_dir": str(run_dir),
            "refined_warp": str(result.refined_warp_path),
            "occupancy_debug": str(result.occupancy_debug_path),
            "piece_color_debug": str(result.piece_color_debug_path),
            "predicted_labels": predicted,
            "occupancy_matrix": pipeline_result.occupancy_matrix,
            "white_bitmap": pipeline_result.white_bitmap,
            "black_bitmap": pipeline_result.black_bitmap,
            "score": score,
        }
        report["images"].append(entry)

        if score is None:
            score_text = "no labels"
        else:
            score_text = (
                f"color={score['color_accuracy']:.1%} "
                f"occupancy={score['occupancy_accuracy']:.1%} "
                f"mismatches={score['mismatch_count']}"
            )

        print(f"[{index:03d}/{len(images):03d}] {image_path.name}: {score_text}")

    if scored_images:
        total_cells = scored_images * 64
        report["summary"] = {
            "scored_images": scored_images,
            "total_images": len(images),
            "color_accuracy": color_correct / total_cells,
            "occupancy_accuracy": occupancy_correct / total_cells,
        }
    else:
        report["summary"] = {
            "scored_images": 0,
            "total_images": len(images),
            "color_accuracy": None,
            "occupancy_accuracy": None,
        }

    contact_sheet = args.output_dir / "contact_sheet.png"
    write_contact_sheet(contact_images, contact_sheet, args.thumb_size, args.cols)

    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"Contact sheet: {contact_sheet}")
    print(f"Report: {report_path}")
    print(f"Summary: {report['summary']}")


if __name__ == "__main__":
    main()
