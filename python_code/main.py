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
from charm.vision.pipeline import run_board_pipeline
from charm.vision.transferphoto import fetch_raw_image
from charm.vision.calibration_config import (
    DEFAULT_BOARD_CALIBRATION_JSON,
    DEFAULT_INNER_WARP_CALIBRATION_JSON,
)
from charm.vision.four_point_calibration import (
    load_four_point_calibration,
    load_inner_warp_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)


def print_matrix(title: str, matrix: list[list[int]]) -> None:
    print(title)
    for row in matrix:
        print(row)
    print()


def save_debug_images(result) -> None:
    cv2.imwrite(str(ROOT / "output_warped_board.jpg"), result.warped_board)
    cv2.imwrite(str(ROOT / "output_grid_debug.jpg"), result.grid_debug_image)
    cv2.imwrite(str(ROOT / "output_occupancy_debug.jpg"), result.occupancy_debug_image)
    cv2.imwrite(str(ROOT / "output_piece_color_debug.jpg"), result.piece_color_debug_image)


def print_saved_outputs() -> None:
    print("Saved:")
    print("- output_first_warp.jpg")
    print("- output_refined_warp.jpg")
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
        default=str(ROOT.parent / "latest_raw.jpg"),
        help="Path to the input image.",
    )
    parser.add_argument(
        "--camera",
        action="store_true",
        help="Capture image from ESP32-CAM instead of --image.",
    )
    parser.add_argument(
        "--board-calibration",
        default=str(DEFAULT_BOARD_CALIBRATION_JSON),
        help="Path to saved board calibration json.",
    )
    parser.add_argument(
        "--inner-calibration",
        default=str(DEFAULT_INNER_WARP_CALIBRATION_JSON),
        help="Path to saved second-stage inner warp calibration json.",
    )
    parser.add_argument(
        "--warp-size",
        type=int,
        default=800,
        help="Output size for calibrated board image.",
    )
    parser.add_argument(
        "--before-moves",
        nargs="*",
        default=[],
        help="UCI moves already played before the observed image.",
    )
    parser.add_argument(
        "--infer-move",
        action="store_true",
        help="Infer a legal move from the observed image using the software board state.",
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=0,
        help="Maximum mismatch count allowed before rejecting the inferred move.",
    )
    parser.add_argument(
        "--max-occupancy-mismatches",
        type=int,
        default=2,
        help="Maximum occupancy-only mismatch count allowed in the legal-move fallback.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.camera:
        original_image_path = Path(fetch_raw_image())
    else:
        original_image_path = Path(args.image)

    board_calibration_path = Path(args.board_calibration)
    inner_calibration_path = Path(args.inner_calibration)

    print(f"Reading image from: {original_image_path}")

    original_image = cv2.imread(str(original_image_path))
    if original_image is None:
        raise FileNotFoundError(f"Could not read image from path: {original_image_path}")

    if not board_calibration_path.exists():
        raise FileNotFoundError(
            f"Could not find board calibration file: {board_calibration_path}\n"
            "Run calibrate_board_corners.py first."
        )

    if not inner_calibration_path.exists():
        raise FileNotFoundError(
            f"Could not find inner warp calibration file: {inner_calibration_path}\n"
            "Run calibrate_inner_warp_corners.py first."
        )

    board_calibration = load_four_point_calibration(board_calibration_path)
    inner_calibration = load_inner_warp_calibration(inner_calibration_path)

    first_warp = warp_from_calibration(
        original_image,
        board_calibration,
        output_size=args.warp_size,
    )
    cv2.imwrite(str(ROOT / "output_first_warp.jpg"), first_warp)

    refined_warp = refine_board_with_inner_corners(
        first_warp,
        inner_calibration,
        output_size=args.warp_size,
    )
    cv2.imwrite(str(ROOT / "output_refined_warp.jpg"), refined_warp)

    calibrated_input_path = ROOT / "output_latest_calibrated_input.jpg"
    cv2.imwrite(str(calibrated_input_path), refined_warp)

    if args.infer_move:
        tracker = BoardStateTracker(build_board_from_moves(args.before_moves))
        update_result = update_tracker_from_image(
            tracker=tracker,
            image_path=str(calibrated_input_path),
            max_mismatches=args.max_mismatches,
            max_occupancy_mismatches=args.max_occupancy_mismatches,
        )
        result = update_result.pipeline_result
        inference_result = update_result.inference_result
    else:
        result = run_board_pipeline(str(calibrated_input_path))
        inference_result = None

    save_debug_images(result)

    print_matrix("Occupancy matrix:", result.occupancy_matrix)
    print_matrix("White bitmap:", result.white_bitmap)
    print_matrix("Black bitmap:", result.black_bitmap)

    if inference_result is None:
        print("Move inference skipped.")
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
