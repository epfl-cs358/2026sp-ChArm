from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2
import chess

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.game import BoardStateTracker, update_tracker_from_image
from charm.vision.pipeline import BoardPipelineResult, run_board_pipeline


def print_matrix(title: str, matrix: list[list[int]]) -> None:
    print(title)
    for row in matrix:
        print(row)
    print()


def save_debug_images(result: BoardPipelineResult) -> None:
    cv2.imwrite(str(ROOT / "output_black_mask_debug.jpg"), result.black_mask_debug_image)
    cv2.imwrite(str(ROOT / "output_color_mask_debug.jpg"), result.color_mask_debug_image)
    cv2.imwrite(str(ROOT / "output_corners_debug.jpg"), result.corners_debug_image)
    cv2.imwrite(str(ROOT / "output_warped_board.jpg"), result.warped_board)
    cv2.imwrite(str(ROOT / "output_grid_debug.jpg"), result.grid_debug_image)
    cv2.imwrite(str(ROOT / "output_occupancy_debug.jpg"), result.occupancy_debug_image)
    cv2.imwrite(str(ROOT / "output_piece_color_debug.jpg"), result.piece_color_debug_image)


def print_saved_outputs() -> None:
    print("Saved:")
    print("- output_black_mask_debug.jpg")
    print("- output_color_mask_debug.jpg")
    print("- output_corners_debug.jpg")
    print("- output_warped_board.jpg")
    print("- output_grid_debug.jpg")
    print("- output_occupancy_debug.jpg")
    print("- output_piece_color_debug.jpg")


def build_board_from_moves(moves: list[str]) -> chess.Board:
    board = chess.Board()

    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move for current board state: {uci}")
        board.push(move)

    return board


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        default=str(ROOT / "test_images" / "chessboard2.jpeg"),
        help="Path to the input image.",
    )
    parser.add_argument(
        "--before-moves",
        nargs="*",
        default=[],
        help="UCI moves already played before the observed image.",
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=0,
        help="Maximum mismatch count allowed before rejecting the inferred move.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    print(f"Reading image from: {image_path}")

    if args.before_moves:
        tracker = BoardStateTracker(build_board_from_moves(args.before_moves))
        update_result = update_tracker_from_image(
            tracker=tracker,
            image_path=str(image_path),
            max_mismatches=args.max_mismatches,
        )
        result = update_result.pipeline_result
        inference_result = update_result.inference_result
    else:
        result = run_board_pipeline(str(image_path))
        inference_result = None

    save_debug_images(result)

    print_matrix("Occupancy matrix:", result.occupancy_matrix)
    print_matrix("White bitmap:", result.white_bitmap)
    print_matrix("Black bitmap:", result.black_bitmap)

    if inference_result is None:
        print("Move inference skipped.")
        print("Pass --before-moves with the known board history to infer the next move.")
    elif inference_result.move is None:
        print(f"No accepted move inferred. mismatch_count={inference_result.mismatch_count}")
    else:
        print(
            f"Inferred move: {inference_result.move.uci()} "
            f"(mismatch_count={inference_result.mismatch_count})"
        )

    print_saved_outputs()


if __name__ == "__main__":
    main()
