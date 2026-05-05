from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[3]  # python_code
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.calibration_config import (
    DEFAULT_BOARD_CALIBRATION_JSON,
    DEFAULT_INNER_WARP_CALIBRATION_JSON,
)
from charm.vision.four_point_calibration import (
    InnerWarpCalibration,
    draw_calibration_points,
    load_four_point_calibration,
    save_inner_warp_calibration,
    warp_from_calibration,
)

clicked_points: list[tuple[int, int]] = []


def mouse_callback(event, x, y, flags, param) -> None:
    global clicked_points
    if event == cv2.EVENT_LBUTTONDOWN and len(clicked_points) < 4:
        clicked_points.append((x, y))
        print(f"Point {len(clicked_points)}: ({x}, {y})")


def draw_points(image, points: list[tuple[int, int]]):
    debug = image.copy()
    labels = ["TL", "TR", "BR", "BL"]

    for i, (x, y) in enumerate(points):
        cv2.circle(debug, (x, y), 6, (0, 255, 255), -1)
        cv2.putText(
            debug,
            f"{labels[i]} ({x},{y})",
            (x + 8, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    if len(points) == 4:
        for i in range(4):
            cv2.line(debug, points[i], points[(i + 1) % 4], (0, 255, 255), 2)

    return debug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        default=str(ROOT.parent / "latest_raw.jpg"),
        help="Path to the raw image.",
    )
    parser.add_argument(
        "--board-calibration",
        default=str(DEFAULT_BOARD_CALIBRATION_JSON),
        help="Path to saved first-stage calibration json.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_INNER_WARP_CALIBRATION_JSON),
        help="Path to save inner-warp calibration json.",
    )
    parser.add_argument(
        "--warp-size",
        type=int,
        default=800,
        help="Output size for first warp.",
    )
    return parser.parse_args()


def main() -> None:
    global clicked_points

    args = parse_args()
    image_path = Path(args.image)
    board_calibration_path = Path(args.board_calibration)
    output_path = Path(args.output)

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    if not board_calibration_path.exists():
        raise FileNotFoundError(
            f"Could not find board calibration file: {board_calibration_path}"
        )

    board_calibration = load_four_point_calibration(board_calibration_path)
    first_warp = warp_from_calibration(
        image,
        board_calibration,
        output_size=args.warp_size,
    )

    window_name = "Inner Warp Calibration - Click TL, TR, BR, BL"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, mouse_callback)

    print("Click 4 INNER points in this order:")
    print("1. top_left")
    print("2. top_right")
    print("3. bottom_right")
    print("4. bottom_left")
    print("Use the already-warped board.")
    print("Press 'r' to reset, 's' to save, 'q' to quit.")

    while True:
        display = draw_points(first_warp, clicked_points)
        cv2.imshow(window_name, display)

        key = cv2.waitKey(20) & 0xFF

        if key == ord("r"):
            clicked_points = []
            print("Points reset.")

        elif key == ord("s"):
            if len(clicked_points) != 4:
                print("You must select exactly 4 points before saving.")
                continue

            calibration = InnerWarpCalibration(
                top_left=clicked_points[0],
                top_right=clicked_points[1],
                bottom_right=clicked_points[2],
                bottom_left=clicked_points[3],
            )
            save_inner_warp_calibration(calibration, output_path)
            print(f"Inner warp calibration saved to: {output_path}")
            break

        elif key == ord("q"):
            print("Calibration cancelled.")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()