from __future__ import annotations

from pathlib import Path
import sys
import argparse


# ---------------------------------------------------------------------
# Project path setup
# This file is located at:
#   python_code/tests/test_calibrated_pipeline.py
#
# Therefore:
#   parents[1] = python_code/
# ---------------------------------------------------------------------
PYTHON_CODE_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PYTHON_CODE_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.calibrated_pipeline import run_calibrated_board_pipeline


def print_matrix(title: str, matrix: list[list[int]]) -> None:
    print()
    print(title)
    print("-" * len(title))
    for row in matrix:
        print(" ".join(str(value) for value in row))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Test raw image -> calibration method 1 -> calibration method 2 "
            "-> board pipeline."
        )
    )

    parser.add_argument(
        "--raw-image",
        type=Path,
        default=PYTHON_CODE_ROOT / "latest_raw.jpg",
        help="Raw camera image before calibration.",
    )

    parser.add_argument(
        "--board-calibration-json",
        type=Path,
        default=PYTHON_CODE_ROOT / "board_calibration.json",
        help="Calibration method 1 JSON file.",
    )

    parser.add_argument(
        "--inner-warp-json",
        type=Path,
        default=PYTHON_CODE_ROOT / "inner_warp_calibration.json",
        help="Calibration method 2 JSON file.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PYTHON_CODE_ROOT / "e2e_debug" / "calibrated_pipeline_test",
        help="Output directory for debug images. Files are overwritten on each run.",
    )

    parser.add_argument(
        "--name-prefix",
        type=str,
        default="test",
        help="Prefix for generated debug files.",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Calibrated Pipeline Test")
    print("=" * 80)
    print("PYTHON_CODE_ROOT        =", PYTHON_CODE_ROOT)
    print("SRC_PATH                =", SRC_PATH)
    print("raw_image               =", args.raw_image)
    print("board_calibration_json  =", args.board_calibration_json)
    print("inner_warp_json         =", args.inner_warp_json)
    print("output_dir              =", args.output_dir)
    print()

    if not args.raw_image.exists():
        raise FileNotFoundError(
            f"Raw image not found: {args.raw_image}\n"
            "Expected default path:\n"
            f"  {PYTHON_CODE_ROOT / 'latest_raw.jpg'}\n\n"
            "You can pass another image with:\n"
            "  --raw-image path/to/image.jpg"
        )

    if not args.board_calibration_json.exists():
        raise FileNotFoundError(
            f"Board calibration JSON not found: {args.board_calibration_json}\n"
            "Expected default path:\n"
            f"  {PYTHON_CODE_ROOT / 'board_calibration.json'}"
        )

    if not args.inner_warp_json.exists():
        raise FileNotFoundError(
            f"Inner warp calibration JSON not found: {args.inner_warp_json}\n"
            "Expected default path:\n"
            f"  {PYTHON_CODE_ROOT / 'inner_warp_calibration.json'}"
        )

    result = run_calibrated_board_pipeline(
        raw_image_path=args.raw_image,
        four_point_calibration_path=args.board_calibration_json,
        inner_warp_calibration_path=args.inner_warp_json,
        output_dir=args.output_dir,
        name_prefix=args.name_prefix,
    )

    print("=" * 80)
    print("Generated files")
    print("=" * 80)
    print("first_warp_path          =", result.first_warp_path)
    print("refined_warp_path        =", result.refined_warp_path)
    print("calibration_1_debug_path =", result.calibration_1_debug_path)
    print("calibration_2_debug_path =", result.calibration_2_debug_path)
    print("grid_debug_path          =", result.grid_debug_path)
    print("occupancy_debug_path     =", result.occupancy_debug_path)
    print("piece_color_debug_path   =", result.piece_color_debug_path)

    print_matrix("Occupancy matrix", result.pipeline_result.occupancy_matrix)
    print_matrix("White bitmap", result.pipeline_result.white_bitmap)
    print_matrix("Black bitmap", result.pipeline_result.black_bitmap)

    print()
    print("=" * 80)
    print("Done")
    print("=" * 80)
    print("Open these debug images and check:")
    print("1. calibration_1_debug_path: four outer board corners are correct.")
    print("2. first_warp_path: board is roughly square.")
    print("3. calibration_2_debug_path: refinement corners are correct.")
    print("4. refined_warp_path: clean 8x8 chessboard.")
    print("5. grid_debug_path: grid lines align with board squares.")
    print("6. occupancy_debug_path: occupied squares are correct.")
    print("7. piece_color_debug_path: white/black piece classification is correct.")


if __name__ == "__main__":
    main()