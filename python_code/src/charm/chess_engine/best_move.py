from __future__ import annotations

from pathlib import Path
from typing import Optional

import chess
import chess.engine


def get_best_move(
    board: chess.Board,
    engine_path: str = "stockfish",
    think_time: float = 0.1,
    skill_level: int = 20,
    uci_elo: Optional[int] = None,
    use_limit_strength: bool = False,
) -> Optional[chess.Move]:
    """Find the best move using Stockfish engine at a given strength.

    Stockfish offers two orthogonal strength levers:
      - ``Skill Level`` (0-20): introduces intentional suboptimal moves.
      - ``UCI_LimitStrength`` + ``UCI_Elo`` (1320-3190): targets a precise Elo
        and *ignores* Skill Level while active.

    A fresh engine process is opened per call, so the relevant UCI options must
    be (re)applied every time — they do not persist between moves.

    Args:
        board: Current chess board state
        engine_path: Path to Stockfish executable
        think_time: Time limit for engine analysis (seconds)
        skill_level: Stockfish skill level (0-20, where 0 is weakest)
        uci_elo: Target Elo (1320-3190), only used when ``use_limit_strength``
        use_limit_strength: When True, target ``uci_elo`` instead of skill level
    """
    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        if use_limit_strength and uci_elo is not None:
            engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": max(1320, min(3190, uci_elo)),
            })
        else:
            # Always disable limit-strength explicitly — it may be left on by a
            # previous configuration, which would make Stockfish ignore Skill.
            engine.configure({
                "UCI_LimitStrength": False,
                "Skill Level": max(0, min(20, skill_level)),
            })

        result = engine.play(board, chess.engine.Limit(time=think_time))
        return result.move
    finally:
        engine.quit()