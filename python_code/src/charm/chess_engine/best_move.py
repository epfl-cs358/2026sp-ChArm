from __future__ import annotations

from pathlib import Path
from typing import Optional

import chess
import chess.engine


def get_best_move(
    board: chess.Board,
    engine_path: str = "stockfish",
    think_time: float = 0.1,
) -> Optional[chess.Move]:
    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        result = engine.play(board, chess.engine.Limit(time=think_time))
        return result.move
    finally:
        engine.quit()