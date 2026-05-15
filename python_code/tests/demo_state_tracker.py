from __future__ import annotations

import argparse
from pathlib import Path
import sys

import chess

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.game import BoardStateTracker, board_to_bitmaps


def print_matrix(title: str, matrix: list[list[int]]) -> None:
    print(title)
    for row in matrix:
        print(row)
    print()


def build_board_from_moves(moves: list[str]) -> chess.Board:
    board = chess.Board()

    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move for current board state: {uci}")
        board.push(move)

    return board


def clone_bitmap(bitmap: list[list[int]]) -> list[list[int]]:
    return [row.copy() for row in bitmap]


def inject_noise(
    white_bitmap: list[list[int]],
    black_bitmap: list[list[int]],
    row: int,
    col: int,
    color: str,
) -> tuple[list[list[int]], list[list[int]]]:
    noisy_white = clone_bitmap(white_bitmap)
    noisy_black = clone_bitmap(black_bitmap)

    if color == "white":
        noisy_white[row][col] = 1 - noisy_white[row][col]
    else:
        noisy_black[row][col] = 1 - noisy_black[row][col]

    return noisy_white, noisy_black


def build_invalid_observation(
    white_bitmap: list[list[int]],
    black_bitmap: list[list[int]],
) -> tuple[list[list[int]], list[list[int]]]:
    invalid_white = clone_bitmap(white_bitmap)
    invalid_black = clone_bitmap(black_bitmap)

    # Impossible example from the initial move tests: add an extra white piece
    # without removing a consistent one from the board state.
    invalid_white[4][3] = 1

    return invalid_white, invalid_black


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demo the #36 state tracker from a sequence of known moves."
    )
    parser.add_argument(
        "--moves",
        nargs="+",
        required=True,
        help="Full move sequence in UCI format. The demo will infer the last move.",
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=0,
        help="Maximum mismatch count allowed when accepting the inferred move.",
    )
    parser.add_argument(
        "--inject-noise",
        action="store_true",
        help="Flip one bitmap square to demonstrate a noisy observation.",
    )
    parser.add_argument(
        "--noise-row",
        type=int,
        default=3,
        help="Row index (0-7) used with --inject-noise.",
    )
    parser.add_argument(
        "--noise-col",
        type=int,
        default=3,
        help="Column index (0-7) used with --inject-noise.",
    )
    parser.add_argument(
        "--noise-color",
        choices=("white", "black"),
        default="white",
        help="Bitmap color to modify when using --inject-noise.",
    )
    parser.add_argument(
        "--show-invalid-example",
        action="store_true",
        help="Replace the observed bitmap with an obviously invalid board observation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if len(args.moves) < 1:
        raise ValueError("At least one move is required.")

    before_moves = args.moves[:-1]
    target_move = args.moves[-1]

    previous_board = build_board_from_moves(before_moves)
    observed_board = build_board_from_moves(args.moves)

    white_bitmap, black_bitmap = board_to_bitmaps(observed_board)

    if args.show_invalid_example:
        white_bitmap, black_bitmap = build_invalid_observation(white_bitmap, black_bitmap)
    elif args.inject_noise:
        white_bitmap, black_bitmap = inject_noise(
            white_bitmap,
            black_bitmap,
            row=args.noise_row,
            col=args.noise_col,
            color=args.noise_color,
        )

    tracker = BoardStateTracker(previous_board)
    result = tracker.update_from_bitmaps(
        white_bitmap,
        black_bitmap,
        max_mismatches=args.max_mismatches,
    )

    print(f"Known previous moves: {' '.join(before_moves) if before_moves else '(initial position)'}")
    print(f"Expected last move: {target_move}")
    if args.show_invalid_example:
        print("Demo mode: invalid observation")
    elif args.inject_noise:
        print(
            "Demo mode: noisy observation "
            f"(flipped {args.noise_color} bitmap at row={args.noise_row}, col={args.noise_col})"
        )
    print()
    print_matrix("Observed white bitmap:", white_bitmap)
    print_matrix("Observed black bitmap:", black_bitmap)

    if result.move is None:
        print(
            "No accepted move inferred. "
            f"status={result.status}, mismatch_count={result.mismatch_count}"
        )
        return

    print(f"Inferred last move: {result.move.uci()}")
    print(f"Status: {result.status}")
    print(f"Mismatch count: {result.mismatch_count}")
    print()
    print("Updated board FEN:")
    print(tracker.board.fen())


if __name__ == "__main__":
    main()
