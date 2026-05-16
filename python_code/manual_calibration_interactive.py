#!/usr/bin/env python3

from pathlib import Path
import sys
import json
import argparse

# Setup paths FIRST before any charm imports
PYTHON_CODE_ROOT = Path(__file__).resolve().parent
SRC_PATH = PYTHON_CODE_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

import cv2
import numpy as np

from charm.vision.four_point_calibration import (
    save_four_point_calibration,
    save_inner_warp_calibration,
    FourPointCalibration,
    InnerWarpCalibration,
)


def calibrate_board_corners_interactive(image_path: str | Path) -> FourPointCalibration:
    """
    Interactive board corner calibration using mouse clicks.
    Click in order: top-left, top-right, bottom-right, bottom-left.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Could not load image: {image_path}")

    h, w = image.shape[:2]
    display = image.copy()
    corners = []

    print("Click 4 board corners in order: top-left, top-right, bottom-right, bottom-left")
    print("Close the window when done.")

    def mouse_callback(event, x, y, flags, param):
        nonlocal display, corners
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(corners) < 4:
                corners.append([x, y])
                display = image.copy()
                for i, (cx, cy) in enumerate(corners):
                    cv2.circle(display, (cx, cy), 8, (0, 255, 0), -1)
                    cv2.putText(
                        display, str(i + 1), (cx + 15, cy - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
                    )
                cv2.imshow("Calibrate Board Corners", display)
                print(f"  Corner {len(corners)}: ({x}, {y})")

    cv2.namedWindow("Calibrate Board Corners")
    cv2.setMouseCallback("Calibrate Board Corners", mouse_callback)
    cv2.imshow("Calibrate Board Corners", display)

    while len(corners) < 4:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break

    cv2.destroyAllWindows()

    if len(corners) != 4:
        raise RuntimeError(f"Expected 4 corners, got {len(corners)}")

    corners_array = np.array(corners, dtype=np.float32)
    return FourPointCalibration(corners=corners_array.tolist())


def calibrate_inner_warp_interactive(image_path: str | Path) -> InnerWarpCalibration:
    """
    Interactive inner warp refinement calibration.
    Click 4 corners for refinement.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Could not load image: {image_path}")

    h, w = image.shape[:2]
    display = image.copy()
    corners = []

    print("Click 4 inner warp refinement corners: top-left, top-right, bottom-right, bottom-left")
    print("Close the window when done.")

    def mouse_callback(event, x, y, flags, param):
        nonlocal display, corners
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(corners) < 4:
                corners.append([x, y])
                display = image.copy()
                for i, (cx, cy) in enumerate(corners):
                    cv2.circle(display, (cx, cy), 8, (0, 0, 255), -1)
                    cv2.putText(
                        display, str(i + 1), (cx + 15, cy - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2
                    )
                cv2.imshow("Calibrate Inner Warp", display)
                print(f"  Corner {len(corners)}: ({x}, {y})")

    cv2.namedWindow("Calibrate Inner Warp")
    cv2.setMouseCallback("Calibrate Inner Warp", mouse_callback)
    cv2.imshow("Calibrate Inner Warp", display)

    while len(corners) < 4:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break

    cv2.destroyAllWindows()

    if len(corners) != 4:
        raise RuntimeError(f"Expected 4 corners, got {len(corners)}")

    corners_array = np.array(corners, dtype=np.float32)
    return InnerWarpCalibration(corners=corners_array.tolist())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive 2-step calibration with mouse clicks."
    )

    parser.add_argument(
        "--image",
        type=Path,
        required=True,
        help="Raw image to calibrate.",
    )

    parser.add_argument(
        "--output-board",
        type=Path,
        default=None,
        help="Save board calibration JSON here. Default: python_code/board_calibration.json",
    )

    parser.add_argument(
        "--output-inner",
        type=Path,
        default=None,
        help="Save inner warp calibration JSON here. Default: python_code/inner_warp_calibration.json",
    )

    args = parser.parse_args()

    image_path = args.image.resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    output_board = Path(args.output_board) if args.output_board else PYTHON_CODE_ROOT / "board_calibration.json"
    output_inner = Path(args.output_inner) if args.output_inner else PYTHON_CODE_ROOT / "inner_warp_calibration.json"

    print("=" * 80)
    print("Step 1: Board corner calibration")
    print("=" * 80)
    board_cal = calibrate_board_corners_interactive(image_path)

    print()
    print("=" * 80)
    print("Step 2: Inner warp refinement calibration")
    print("=" * 80)
    inner_cal = calibrate_inner_warp_interactive(image_path)

    output_board.parent.mkdir(parents=True, exist_ok=True)
    output_inner.parent.mkdir(parents=True, exist_ok=True)

    save_four_point_calibration(output_board, board_cal)
    save_inner_warp_calibration(output_inner, inner_cal)

    print()
    print("=" * 80)
    print("Done!")
    print(f"Board calibration: {output_board}")
    print(f"Inner warp calibration: {output_inner}")
    print("=" * 80)


if __name__ == "__main__":
    main()
