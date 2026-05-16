from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.calibrated_pipeline import run_calibrated_board_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the calibrated CV pipeline on a folder of raw photos, collect all "
            "piece_color_debug images into one folder, and create a contact sheet."
        )
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=ROOT / "game_1",
        help="Folder containing raw board photos. Default: python_code/game_1",
    )
    parser.add_argument(
        "--glob",
        default="photo_*.jpg",
        help="Image glob inside --images-dir. Default: photo_*.jpg",
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
        "--work-dir",
        type=Path,
        default=ROOT / "e2e_debug" / "piece_color_debug_runs",
        help="Folder for full per-image pipeline outputs.",
    )
    parser.add_argument(
        "--collect-dir",
        type=Path,
        default=ROOT / "e2e_debug" / "piece_color_debug_all",
        help="Folder containing only collected piece_color_debug images.",
    )
    parser.add_argument("--thumb-size", type=int, default=320, help="Contact sheet thumbnail size.")
    parser.add_argument("--cols", type=int, default=4, help="Contact sheet columns.")
    return parser.parse_args()


def write_contact_sheet(image_paths: list[Path], output_path: Path, thumb_size: int, cols: int) -> None:
    if not image_paths:
        return

    label_h = 34
    rows = (len(image_paths) + cols - 1) // cols
    canvas = np.full((rows * (thumb_size + label_h), cols * thumb_size, 3), 28, dtype=np.uint8)

    for i, path in enumerate(image_paths):
        image = cv2.imread(str(path))
        if image is None:
            continue
        image = cv2.resize(image, (thumb_size, thumb_size), interpolation=cv2.INTER_AREA)
        row, col = divmod(i, cols)
        y = row * (thumb_size + label_h)
        x = col * thumb_size
        canvas[y:y + thumb_size, x:x + thumb_size] = image

        label = path.name.replace("_after_player_piece_color_debug.png", "")
        cv2.putText(
            canvas,
            label[:44],
            (x + 6, y + thumb_size + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )

    cv2.imwrite(str(output_path), canvas)


def main() -> None:
    args = parse_args()

    images = sorted(args.images_dir.glob(args.glob))
    if not images:
        raise FileNotFoundError(f"No images found: {args.images_dir / args.glob}")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.collect_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "mode": "main.py CV defaults via run_calibrated_board_pipeline",
        "images_dir": str(args.images_dir),
        "glob": args.glob,
        "board_calibration_json": str(args.board_calibration_json),
        "inner_warp_json": str(args.inner_warp_json),
        "work_dir": str(args.work_dir),
        "collect_dir": str(args.collect_dir),
        "images": [],
    }

    collected_paths: list[Path] = []

    for index, image_path in enumerate(images, start=1):
        stem = image_path.stem
        run_dir = args.work_dir / stem
        name_prefix = f"{stem}_after_player"

        result = run_calibrated_board_pipeline(
            raw_image_path=image_path,
            four_point_calibration_path=args.board_calibration_json,
            inner_warp_calibration_path=args.inner_warp_json,
            output_dir=run_dir,
            name_prefix=name_prefix,
        )

        collected_path = args.collect_dir / f"{index:02d}_{stem}_after_player_piece_color_debug.png"
        shutil.copy2(result.piece_color_debug_path, collected_path)
        collected_paths.append(collected_path)

        occupied = sum(sum(row) for row in result.pipeline_result.occupancy_matrix)
        white_pieces = sum(sum(row) for row in result.pipeline_result.white_bitmap)
        black_pieces = sum(sum(row) for row in result.pipeline_result.black_bitmap)

        report["images"].append(
            {
                "index": index,
                "raw_image": str(image_path),
                "run_dir": str(run_dir),
                "refined_warp": str(result.refined_warp_path),
                "piece_color_debug": str(result.piece_color_debug_path),
                "collected_piece_color_debug": str(collected_path),
                "occupied": occupied,
                "white_pieces": white_pieces,
                "black_pieces": black_pieces,
                "occupancy_matrix": result.pipeline_result.occupancy_matrix,
                "white_bitmap": result.pipeline_result.white_bitmap,
                "black_bitmap": result.pipeline_result.black_bitmap,
            }
        )

        print(
            f"[{index:02d}/{len(images):02d}] {image_path.name} "
            f"-> occupied={occupied} white={white_pieces} black={black_pieces}"
        )

    contact_sheet_path = args.collect_dir / "contact_sheet.png"
    write_contact_sheet(collected_paths, contact_sheet_path, args.thumb_size, args.cols)

    report_path = args.collect_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"Collected debug images: {args.collect_dir}")
    print(f"Contact sheet: {contact_sheet_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
