from __future__ import annotations

from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.pipeline import run_board_pipeline


def print_matrix(title: str, matrix: list[list[int]]) -> None:
    print(title)
    for row in matrix:
        print(row)
    print()


def main() -> None:
    image_path = ROOT / "test_images" / "chessboard2.jpeg"
    print(f"Reading image from: {image_path}")

    result = run_board_pipeline(str(image_path))

    cv2.imwrite(str(ROOT / "output_black_mask_debug.jpg"), result.black_mask_debug_image)
    cv2.imwrite(str(ROOT / "output_color_mask_debug.jpg"), result.color_mask_debug_image)
    cv2.imwrite(str(ROOT / "output_corners_debug.jpg"), result.corners_debug_image)
    cv2.imwrite(str(ROOT / "output_warped_board.jpg"), result.warped_board)
    cv2.imwrite(str(ROOT / "output_grid_debug.jpg"), result.grid_debug_image)
    cv2.imwrite(str(ROOT / "output_occupancy_debug.jpg"), result.occupancy_debug_image)
    cv2.imwrite(str(ROOT / "output_piece_color_debug.jpg"), result.piece_color_debug_image)

    print_matrix("Occupancy matrix:", result.occupancy_matrix)
    print_matrix("White bitmap:", result.white_bitmap)
    print_matrix("Black bitmap:", result.black_bitmap)

    print("Saved:")
    print("- output_black_mask_debug.jpg")
    print("- output_color_mask_debug.jpg")
    print("- output_corners_debug.jpg")
    print("- output_warped_board.jpg")
    print("- output_grid_debug.jpg")
    print("- output_occupancy_debug.jpg")
    print("- output_piece_color_debug.jpg")


if __name__ == "__main__":
    main()