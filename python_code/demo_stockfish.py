from __future__ import annotations

from pathlib import Path
import sys

import chess

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.chess_engine import get_best_move


def main() -> None:
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("e7e5")
    board.push_uci("g1f3")

    move = get_best_move(board, engine_path="stockfish", think_time=0.1)

    print("Position after e2e4 e7e5 g1f3")
    print(board)
    print()

    if move is None:
        print("No best move returned.")
    else:
        print("Best move:", move.uci())


if __name__ == "__main__":
    main()