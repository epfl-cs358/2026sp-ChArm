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
) -> Optional[chess.Move]:
    """Find the best move using Stockfish engine at a given skill level.
    
    Args:
        board: Current chess board state
        engine_path: Path to Stockfish executable
        think_time: Time limit for engine analysis (seconds)
        skill_level: Stockfish skill level (0-20, where 0 is weakest, 20 is strongest)
    """
    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        # Clamp skill_level to valid range [0, 20]
        skill = max(0, min(20, skill_level))
        engine.configure({"Skill Level": skill})
        
        result = engine.play(board, chess.engine.Limit(time=think_time))
        return result.move
    finally:
        engine.quit()