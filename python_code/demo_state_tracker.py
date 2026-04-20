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

    tracker = BoardStateTracker(previous_board)
    result = tracker.update_from_bitmaps(
        white_bitmap,
        black_bitmap,
        max_mismatches=args.max_mismatches,
    )

    print(f"Known previous moves: {' '.join(before_moves) if before_moves else '(initial position)'}")
    print(f"Expected last move: {target_move}")
    print()
    print_matrix("Observed white bitmap:", white_bitmap)
    print_matrix("Observed black bitmap:", black_bitmap)

    if result.move is None:
        print(f"No accepted move inferred. mismatch_count={result.mismatch_count}")
        return

    print(f"Inferred last move: {result.move.uci()}")
    print(f"Mismatch count: {result.mismatch_count}")
    print()
    print("Updated board FEN:")
    print(tracker.board.fen())


if __name__ == "__main__":
    main()
