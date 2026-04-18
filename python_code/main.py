from __future__ import annotations

from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.pipeline import run_board_pipeline


def main() -> None:
    image_path = ROOT / "test_images" / "chessboard2.jpeg"
    print(f"Reading image from: {image_path}")

    result = run_board_pipeline(str(image_path))

    cv2.imwrite(str(ROOT / "output_corners_debug.jpg"), result.corners_debug_image)
    cv2.imwrite(str(ROOT / "output_warped_board.jpg"), result.warped_board)
    cv2.imwrite(str(ROOT / "output_grid_debug.jpg"), result.grid_debug_image)

    print("Saved:")
    print("- output_corners_debug.jpg")
    print("- output_warped_board.jpg")
    print("- output_grid_debug.jpg")


if __name__ == "__main__":
    main()