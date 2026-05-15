from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.calibration_config import DEFAULT_INNER_WARP_CALIBRATION
from charm.vision.four_point_calibration import (
    draw_calibration_points,
    draw_inner_warp_points,
    load_four_point_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        default=str(ROOT.parent / "latest_raw.jpg"),
        help="Path to the input image.",
    )
    parser.add_argument(
        "--calibration",
        default=str(ROOT / "board_calibration.json"),
        help="Path to saved calibration json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    calibration_path = Path(args.calibration)

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    calibration = load_four_point_calibration(calibration_path)

    calibration_debug = draw_calibration_points(image, calibration)
    warped = warp_from_calibration(image, calibration, output_size=800)

    inner_debug = draw_inner_warp_points(warped, DEFAULT_INNER_WARP_CALIBRATION)
    refined = refine_board_with_inner_corners(
        warped,
        DEFAULT_INNER_WARP_CALIBRATION,
        output_size=800,
    )

    cv2.imwrite(str(ROOT / "output_calibration_debug.jpg"), calibration_debug)
    cv2.imwrite(str(ROOT / "output_calibration_warped.jpg"), warped)
    cv2.imwrite(str(ROOT / "output_inner_warp_debug.jpg"), inner_debug)
    cv2.imwrite(str(ROOT / "output_refined_warped.jpg"), refined)

    print(f"Input image: {image_path}")
    print(f"Calibration file: {calibration_path}")
    print("Saved:")
    print("- output_calibration_debug.jpg")
    print("- output_calibration_warped.jpg")
    print("- output_inner_warp_debug.jpg")
    print("- output_refined_warped.jpg")


if __name__ == "__main__":
    main()