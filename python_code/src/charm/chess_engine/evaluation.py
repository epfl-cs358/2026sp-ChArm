"""Stockfish position-evaluation helpers used by the webapp game endpoints.

`evaluate_position` returns a centipawn score from White's point of view (so
positive = White winning, negative = Black winning) plus the engine's best
move and a forced-mate distance when applicable. `classify_move_rating`
buckets the player's centipawn loss into the rating tier shown on the
dashboard's Game Evaluation panel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

import chess
import chess.engine


MoveRating = Literal["Excellent", "Good", "Inaccuracy", "Mistake", "Blunder"]


# Centipawn-loss thresholds borrowed from the implementation plan; tweak in
# one place if we want to retune them later.
_RATING_THRESHOLDS: list[tuple[int, MoveRating]] = [
    (20, "Excellent"),
    (50, "Good"),
    (100, "Inaccuracy"),
    (200, "Mistake"),
]


@dataclass
class Evaluation:
    """Result of one Stockfish probe of a position."""

    # Centipawn score from White's POV. ``None`` only if score and mate are
    # both unavailable (e.g. engine error).
    score_cp: Optional[int]
    # Positive = White mates in N, negative = Black mates in N, 0/None if not
    # a forced mate.
    mate: Optional[int]
    # Best move at this position (UCI). None on game end.
    best_move_uci: Optional[str]
    best_move_san: Optional[str]


def evaluate_position(
    board: chess.Board,
    engine_path: str = "stockfish",
    think_time: float = 0.1,
    skill_level: int = 20,
) -> Evaluation:
    """Run Stockfish on ``board`` and return its score + best move."""
    if board.is_game_over():
        # Map terminal positions to a fixed-sign mate value so the caller's
        # win-percentage math still works without special-casing.
        outcome = board.outcome()
        if outcome is not None and outcome.winner is not None:
            mate = 0 if outcome.winner == chess.WHITE else 0
            score_cp = 100_000 if outcome.winner == chess.WHITE else -100_000
        else:
            mate = None
            score_cp = 0
        return Evaluation(score_cp=score_cp, mate=mate, best_move_uci=None, best_move_san=None)

    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        skill = max(0, min(20, skill_level))
        try:
            engine.configure({"Skill Level": skill})
        except chess.engine.EngineError:
            # Some forks don't expose Skill Level — proceed with defaults.
            pass

        info = engine.analyse(board, chess.engine.Limit(time=think_time))
        pov_score = info["score"].white()
        score_cp = pov_score.score(mate_score=100_000)
        mate = pov_score.mate()
        pv = info.get("pv") or []
        best_move = pv[0] if pv else None
        best_move_uci = best_move.uci() if best_move is not None else None
        best_move_san: Optional[str] = None
        if best_move is not None:
            try:
                best_move_san = board.san(best_move)
            except Exception:
                best_move_san = best_move_uci
    finally:
        engine.quit()

    return Evaluation(
        score_cp=score_cp,
        mate=mate,
        best_move_uci=best_move_uci,
        best_move_san=best_move_san,
    )


def win_percentage_from_cp(score_cp: Optional[int], mate: Optional[int]) -> float:
    """Convert a White-POV centipawn (or mate) score into a 0-100 win %."""
    if mate is not None and mate != 0:
        return 100.0 if mate > 0 else 0.0
    if score_cp is None:
        return 50.0
    # Lichess-style sigmoid; coefficient 0.00368208 maps roughly to the
    # win-probability curve used by chess.com / Lichess.
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * score_cp)) - 1.0)


def format_score(score_cp: Optional[int], mate: Optional[int]) -> str:
    """Render a score for the UI: ``"+1.2"``, ``"-0.5"`` or ``"M7"`` / ``"-M3"``."""
    if mate is not None and mate != 0:
        return f"M{mate}" if mate > 0 else f"-M{abs(mate)}"
    if score_cp is None:
        return "0.0"
    pawns = score_cp / 100.0
    return f"{pawns:+.1f}"


def winning_color(score_cp: Optional[int], mate: Optional[int]) -> str:
    """Return "white", "black" or "even" based on the score."""
    if mate is not None and mate != 0:
        return "white" if mate > 0 else "black"
    if score_cp is None:
        return "even"
    if score_cp > 30:
        return "white"
    if score_cp < -30:
        return "black"
    return "even"


def classify_move_rating(
    cp_before_player: int,
    cp_after_player: int,
    mate_before: Optional[int],
    mate_after: Optional[int],
) -> tuple[MoveRating, int]:
    """Bucket a player's move into a quality tier.

    Both centipawn values must be expressed from the *moving player's*
    perspective (so a higher number is better for that player). Returns
    ``(rating, cp_loss)`` where ``cp_loss`` is the drop in eval caused by
    the move (always ≥ 0; ``inf`` for a conceded forced mate).
    """
    # Conceding a forced mate where there was none before is the worst case.
    if (mate_before is None or mate_before >= 0) and mate_after is not None and mate_after < 0:
        return "Blunder", 10_000

    cp_loss = max(0, cp_before_player - cp_after_player)
    for threshold, rating in _RATING_THRESHOLDS:
        if cp_loss < threshold:
            return rating, cp_loss
    return "Blunder", cp_loss
