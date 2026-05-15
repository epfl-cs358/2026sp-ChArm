from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import chess

from charm.arduino.uiController_bridge import ArduinoUIControllerLink
from charm.arduino.arduino_bridge import execute_move
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
    # "white" or "black" — set by the app layer before the game starts.
    player_color: str = "white"
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
        self.current_skill_level = self.DIFFICULTY_MAP[1]
        self.ui_link.set_handlers(
            on_check_board=self.check_board,
            on_player_done=self.player_done,
            on_set_difficulty=self.set_difficulty,
            on_set_color=self.set_player_color,
        )

    def start(self) -> None:
        self.ui_link.start()

    def stop(self) -> None:
        self.ui_link.close()

    def check_board(self) -> bool:
        """Called by the bridge when Arduino sends CHECK_BOARD.

        Returns True/False only — the bridge sends BOARD_OK or BOARD_FAIL
        based on this return value, so we must NOT call board_ok/board_fail here.
        """
        image_path = self.config.board_image_provider()
        result = self.session.initialize_from_image(image_path)

        if not result.success:
            return False

        start_result = self.session.start_game(self.config.player_color)
        if not start_result.success:
            return False

        # If the robot plays white it moves first.
        # BOARD_OK is sent by the bridge after this returns True, then we move.
        if self.session.robot_moves_first():
            self._do_robot_move()
        else:
            if self.config.player_color == "white":
                self.ui_link.player_turn_white()
            else:
                self.ui_link.player_turn_black()

        return True

    def player_done(self) -> None:
        """Called by the bridge when Arduino sends PLAYER_DONE (button press)."""
        self.ui_link.bot_thinking()

        if self.config.on_player_done is not None:
            self.config.on_player_done()

        # Capture the board and let the session detect + commit the player's move.
        image_path = self.config.board_image_provider()
        move_result = self.session.process_player_move_from_image(image_path)

        if not move_result.success:
            # Vision could not detect a valid move (illegal or ambiguous move).
            # Put the Arduino in ERROR mode so the LCD shows "ERR: check board".
            # Player presses button to dismiss the error, which returns to GAME
            # mode; they then press OK again to re-trigger PLAYER_DONE and retry.
            self.ui_link.set_mode(7)  # UIMode::ERROR = 7 in uiState.h
            return

        # Check if the player's move ended the game.
        board = self.session.get_current_board()
        if board is not None and board.is_game_over():
            self.ui_link.move_done()
            return

        self._do_robot_move()

    def _do_robot_move(self) -> None:
        """Compute, physically execute, and commit the robot's next move."""
        robot_result = self.session.compute_robot_move(
            engine_path=self.config.engine_path,
            think_time=self.config.think_time,
            skill_level=self.current_skill_level,
        )

        if not robot_result.success:
            self.ui_link.move_done()
            return

        self.ui_link.bot_moving()

        # board must be read BEFORE committing so execute_move can inspect
        # piece types and capture info from the pre-move board state.
        board = self.session.get_current_board()
        if board is None:
            return

        execute_move(robot_result.move_uci, board)

        # Commit the robot's move into the session's internal board.
        self.session.commit_robot_move(robot_result.move_uci)

        # Update the LCD with whose turn it is next.
        updated_board = self.session.get_current_board()
        if updated_board is not None and not updated_board.is_game_over():
            if updated_board.turn == chess.WHITE:
                self.ui_link.player_turn_white()
            else:
                self.ui_link.player_turn_black()

        self.ui_link.move_done()

    def set_player_color(self, color: str) -> None:
        """Called by the bridge when Arduino sends SET_COLOR (color selection screen)."""
        self.config.player_color = color

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
