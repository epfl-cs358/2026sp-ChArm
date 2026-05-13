from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import chess

from charm.arduino.uiController_bridge import ArduinoUIControllerLink
from charm.arduino.arduino_bridge import execute_move
from charm.chess_engine.best_move import get_best_move
from charm.game.game_session import GameSession


BoardImageProvider = Callable[[], str]
MoveExecutor = Callable[[], None]
DifficultyHandler = Callable[[int], None]


@dataclass
class GameControllerConfig:
    """Wires the game/session layer to the Arduino UI protocol.

    The controller does not decide chess moves itself. It only coordinates:
    - UI state events coming from the Arduino UIController
    - session/vision checks
    - external move planning/execution callbacks supplied by the app layer
    """

    board_image_provider: BoardImageProvider
    on_player_done: Optional[MoveExecutor] = None
    on_set_difficulty: Optional[DifficultyHandler] = None
    engine_path: str = "stockfish"
    think_time: float = 0.1


class GameController:
    # Map Arduino difficulty (0-2) to Stockfish skill level (0-20)
    DIFFICULTY_MAP = {
        0: 5,   # EASY: beginner level
        1: 12,  # MEDIUM: intermediate level
        2: 20,  # HARD: maximum strength
    }

    def __init__(
        self,
        ui_link: ArduinoUIControllerLink,
        session: Optional[GameSession],
        config: GameControllerConfig,
    ) -> None:
        self.ui_link = ui_link
        self.session = session if session is not None else GameSession()
        self.config = config
        self.current_difficulty = 1  # Default to MEDIUM (Arduino difficulty 1)
        self.current_skill_level = self.DIFFICULTY_MAP[1]  # Stockfish skill level
        self.ui_link.set_handlers(
            on_check_board=self.check_board,
            on_player_done=self.player_done,
            on_set_difficulty=self.set_difficulty,
        )

    def start(self) -> None:
        self.ui_link.start()

    def stop(self) -> None:
        self.ui_link.close()

    def check_board(self) -> bool:
        image_path = self.config.board_image_provider()
        result = self.session.initialize_from_image(image_path)

        if result.success:
            self.ui_link.board_ok()
            return True

        self.ui_link.board_fail()
        return False

    def player_done(self) -> None:
        # Tell the Arduino UI that the robot side is thinking/moving.
        self.ui_link.bot_thinking()

        if self.config.on_player_done is not None:
            # Optional app-level hook (logging, camera capture orchestration, etc.)
            self.config.on_player_done()

        if self.session.tracker is None:
            return

        board = self.session.tracker.board
        best_move = get_best_move(
            board,
            engine_path=self.config.engine_path,
            think_time=self.config.think_time,
            skill_level=self.current_skill_level,
        )

        if best_move is None:
            return

        is_capture = board.is_capture(best_move)
        is_castling = board.is_castling(best_move)
        is_promotion = best_move.promotion is not None
        piece = board.piece_at(best_move.from_square)
        piece_type = chess.piece_name(piece.piece_type) if piece is not None else None

        self.ui_link.bot_moving()
        execute_move(
            best_move.uci(),
            is_capture=is_capture,
            is_castling=is_castling,
            is_promotion=is_promotion,
            piece_type=piece_type,
        )

        # Keep session board state in sync with physical execution.
        board.push(best_move)

        # After robot move, it is the human turn again.
        self.ui_link.player_turn_white() if board.turn == chess.WHITE else self.ui_link.player_turn_black()

        self.ui_link.move_done()

    def set_difficulty(self, difficulty: int) -> None:
        """Update Stockfish skill level based on Arduino difficulty setting.
        
        Args:
            difficulty: Arduino difficulty value (0=EASY, 1=MEDIUM, 2=HARD)
        """
        self.current_difficulty = difficulty
        self.current_skill_level = self.DIFFICULTY_MAP.get(difficulty, 12)
        
        if self.config.on_set_difficulty is not None:
            self.config.on_set_difficulty(difficulty)

    def notify_turn_white(self) -> None:
        self.ui_link.player_turn_white()

    def notify_turn_black(self) -> None:
        self.ui_link.player_turn_black()
