from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.utils.bitmap import build_white_black_bitmaps
from charm.vision.calibration_config import DEFAULT_INNER_WARP_CALIBRATION_JSON
from charm.vision.board_detector import find_largest_quadrilateral
from charm.vision.four_point_calibration import (
    load_four_point_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)
from charm.vision.grid_splitter import (
    detect_8x8_grid_lines,
    draw_8x8_grid,
    extract_8x8_cells,
)
from charm.vision.occupancy_detector import (
    detect_occupancy,
    draw_occupancy_debug,
    occupancy_to_matrix,
)
from charm.vision.piece_color_detector import (
    detect_piece_colors,
    draw_piece_color_debug,
)
from charm.vision.preprocessing import enhance_board_contrast


def print_matrix(title: str, matrix: list[list[int]]) -> None:
    print(title)
    for row in matrix:
        print(row)
    print()


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
    parser.add_argument(
        "--output-size",
        type=int,
        default=800,
        help="Output size of warped board image.",
    )
    parser.add_argument(
        "--occupancy-threshold",
        type=float,
        default=2.0,
        help="Threshold for occupancy detection.",
    )
    parser.add_argument(
        "--angle",
        type=float,
        default=0.0,
        help="Rotate the input image by this many degrees to test robustness.",
    )
    parser.add_argument(
        "--already-refined",
        action="store_true",
        help="Treat --image as an already refined board warp and skip auto-detection/calibration.",
    )
    parser.add_argument(
        "--white-threshold",
        type=float,
        default=128.0,
        help="White piece brightness threshold.",
    )
    parser.add_argument(
        "--black-threshold",
        type=float,
        default=128.0,
        help="Black piece brightness threshold.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    image_path = Path(args.image)
    calibration_path = Path(args.calibration)

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image from path: {image_path}")

    if args.angle != 0.0:
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, args.angle, 1.0)
        image = cv2.warpAffine(image, rotation_matrix, (w, h))
        print(f"Applied rotation of {args.angle} degrees to the input image.")

    if args.already_refined:
        print("Using input as already refined board warp.")
        refined_warped = cv2.resize(image, (args.output_size, args.output_size), interpolation=cv2.INTER_CUBIC)
        calibration_warped = refined_warped.copy()
    else:
        auto_quad = find_largest_quadrilateral(image)
        if auto_quad is not None:
            print("Board corners successfully auto-detected!")
            calibration = load_four_point_calibration(calibration_path)
            calibration.top_left = tuple(map(int, auto_quad[0]))
            calibration.top_right = tuple(map(int, auto_quad[1]))
            calibration.bottom_right = tuple(map(int, auto_quad[2]))
            calibration.bottom_left = tuple(map(int, auto_quad[3]))
        else:
            print("Auto-detect failed. Falling back to saved board calibration.")
            calibration = load_four_point_calibration(calibration_path)

        # Step 1: first warp from saved manual calibration
        calibration_warped = warp_from_calibration(
            image,
            calibration,
            output_size=args.output_size,
        )

        # Step 2: second refinement
        inner_calibration = load_four_point_calibration(DEFAULT_INNER_WARP_CALIBRATION_JSON)
        refined_warped = refine_board_with_inner_corners(
            calibration_warped,
            inner_calibration,
            output_size=args.output_size,
        )

    # Step 3: enhance low-contrast board, then draw grid and split into cells
    enhanced_warped = enhance_board_contrast(refined_warped)
    x_lines, y_lines = detect_8x8_grid_lines(enhanced_warped)
    grid_debug = draw_8x8_grid(enhanced_warped, x_lines, y_lines)
    occupancy_cells = extract_8x8_cells(enhanced_warped, x_lines, y_lines)
    color_cells = extract_8x8_cells(refined_warped, x_lines, y_lines)

    # Step 4: occupancy detection
    occupancy_results = detect_occupancy(
        occupancy_cells,
        threshold=args.occupancy_threshold,
    )
    occupancy_matrix = occupancy_to_matrix(occupancy_results)
    occupancy_debug = draw_occupancy_debug(
        enhanced_warped,
        occupancy_cells,
        occupancy_results,
    )

    # Step 5: piece color detection
    color_results = detect_piece_colors(
        color_cells,
        occupancy_results,
        white_threshold=args.white_threshold,
        black_threshold=args.black_threshold,
    )
    piece_color_debug = draw_piece_color_debug(
        refined_warped,
        color_cells,
        color_results,
    )

    # Step 6: bitmaps
    white_bitmap, black_bitmap = build_white_black_bitmaps(color_results)

    # Save outputs
    cv2.imwrite(str(ROOT / "output_test_calibration_warped.jpg"), calibration_warped)
    cv2.imwrite(str(ROOT / "output_test_refined_warped.jpg"), refined_warped)
    cv2.imwrite(str(ROOT / "output_test_grid_debug.jpg"), grid_debug)
    cv2.imwrite(str(ROOT / "output_test_occupancy_debug.jpg"), occupancy_debug)
    cv2.imwrite(str(ROOT / "output_test_piece_color_debug.jpg"), piece_color_debug)

    print(f"Input image: {image_path}")
    print(f"Calibration file: {calibration_path}")
    print()

    print_matrix("Occupancy matrix:", occupancy_matrix)
    print_matrix("White bitmap:", white_bitmap)
    print_matrix("Black bitmap:", black_bitmap)

    print("Saved:")
    print("- output_test_calibration_warped.jpg")
    print("- output_test_refined_warped.jpg")
    print("- output_test_grid_debug.jpg")
    print("- output_test_occupancy_debug.jpg")
    print("- output_test_piece_color_debug.jpg")


if __name__ == "__main__":
    main()
