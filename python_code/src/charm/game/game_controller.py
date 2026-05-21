from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional

import chess
import serial

from charm.arduino.uiController_bridge import ArduinoUIControllerLink
from charm.arduino.arduino_bridge import execute_move, send_command
from charm.game.cv_scan import build_router, persist_validated_capture
from charm.game.game_session import GameSession, SessionResult
from charm.vision.cv_router import AttemptDecision


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
    arm_ser: serial.Serial = None        # USB serial to Mega, for arm commands
    arm_lock: threading.Lock = None      # protects arm_ser writes
    # "white" or "black" — set by the app layer before the game starts.
    player_color: str = "white"
    # Set to True when the camera sees white on top / black on bottom
    # (180° rotated from the chess.Board standard orientation).
    flip_180: bool = False
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
            on_calibration=self.run_calibration,
        )

    def start(self) -> None:
        self.ui_link.start()

    def stop(self) -> None:
        self.ui_link.close()

    def check_board(self) -> bool:
        """Called by the bridge when Arduino sends CHECK_BOARD.

        Uses the same CV router config as the webapp (cv_router_config.json):
        tries the configured primary mode (CNN if active, else vision) and
        falls back to the other after attempts_each tries each. Validated
        captures are appended to the shared dataset.

        Returns True/False — the bridge sends BOARD_OK or BOARD_FAIL.
        """
        print("\n========== GAME CONTROLLER CHECK_BOARD DEBUG ==========", flush=True)

        try:
            self.session.reset()

            router, fns, cfg = build_router()
            print(f"[DEBUG] router: primary={cfg.primary} attempts_each={cfg.attempts_each} modes={list(fns.keys())}", flush=True)

            last_initial: dict = {"result": None}

            def _on_init_attempt(mode, idx, capture) -> AttemptDecision:
                print(f"[DEBUG] init attempt mode={mode} idx={idx}", flush=True)
                result = self.session.initialize_from_bitmaps(
                    capture.white_bitmap,
                    capture.black_bitmap,
                    max_mismatches=0,
                )
                last_initial["result"] = result
                if result.success:
                    persist_validated_capture(capture, cfg, mode_used=mode, move_uci=None)
                return AttemptDecision(
                    success=result.success,
                    error=None if result.success else result.message,
                )

            router_result = router.scan(fns, _on_init_attempt)
            print(f"[DEBUG] router result: success={router_result.success} mode_used={router_result.mode_used} attempts={router_result.attempts_by_mode()}", flush=True)

            if not router_result.success or last_initial["result"] is None or not last_initial["result"].success:
                print("[DEBUG] RETURN FALSE: no attempt validated the initial board", flush=True)
                print("=======================================================\n", flush=True)
                return False

            print("[DEBUG] Step 3: start_game()", flush=True)
            print("[DEBUG] config.player_color =", self.config.player_color, flush=True)
            start_result = self.session.start_game(self.config.player_color)
            print("[DEBUG] start_result.success =", start_result.success, flush=True)
            print("[DEBUG] start_result.message =", start_result.message, flush=True)

            if not start_result.success:
                print("[DEBUG] RETURN FALSE: start_game failed", flush=True)
                print("=======================================================\n", flush=True)
                return False

            print("[DEBUG] RETURN TRUE: check_board success", flush=True)
            print("=======================================================\n", flush=True)
            return True

        except Exception as e:
            print("[DEBUG] EXCEPTION in check_board:", repr(e), flush=True)
            import traceback
            traceback.print_exc()
            print("[DEBUG] RETURN FALSE because exception occurred", flush=True)
            print("=======================================================\n", flush=True)
            return False


    def player_done(self) -> None:
        """Called by the bridge when Arduino sends PLAYER_DONE (button press).

        Same router-driven flow as check_board: CNN-primary if active, vision
        fallback, retries per cv_router_config.json.
        """
        if self.config.on_player_done is not None:
            self.config.on_player_done()

        router, fns, cfg = build_router()
        last_move: dict = {"result": None}

        def _on_move_attempt(mode, idx, capture) -> AttemptDecision:
            print(f"[DEBUG] move attempt mode={mode} idx={idx}", flush=True)
            result = self.session.process_bitmaps(
                capture.white_bitmap,
                capture.black_bitmap,
                max_mismatches=0,
            )
            last_move["result"] = result
            if result.success:
                persist_validated_capture(capture, cfg, mode_used=mode, move_uci=result.move_uci)
            return AttemptDecision(
                success=result.success,
                error=None if result.success else result.message,
            )

        router_result = router.scan(fns, _on_move_attempt)
        move_result: Optional[SessionResult] = last_move["result"]

        if not router_result.success or move_result is None or not move_result.success:
            # Vision could not detect a valid move (illegal or ambiguous move).
            # Put the Arduino in ERROR mode so the LCD shows "ERR: check board".
            self.ui_link.set_mode(7)  # UIMode::ERROR = 7 in uiState.h
            return

        # Check if the player's move ended the game.
        board = self.session.get_current_board()
        if board is not None and board.is_game_over():
            self.ui_link.game_over(self._game_over_reason(board))
            return

        if board is not None:
            if board.turn == chess.WHITE:
                self.ui_link.player_turn_white()
            else:
                self.ui_link.player_turn_black()

        self.ui_link.bot_thinking()
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

        execute_move(robot_result.move_uci, board, self.config.arm_ser, self.config.arm_lock)

        # Commit the robot's move into the session's internal board.
        self.session.commit_robot_move(robot_result.move_uci)

        # Update the LCD with whose turn it is next, or show game over.
        updated_board = self.session.get_current_board()
        if updated_board is not None and updated_board.is_game_over():
            self.ui_link.game_over(self._game_over_reason(updated_board))
            return

        if updated_board is not None:
            if updated_board.turn == chess.WHITE:
                self.ui_link.player_turn_white()
            else:
                self.ui_link.player_turn_black()

        self.ui_link.move_done()

    def run_calibration(self) -> None:
        """Called by the bridge when the ESP32 sends CALIBRATION. Forwards the
        calibrate command to the Mega so the arm runs its homing routine."""
        print("[GAME] CALIBRATION received — sending 'calibrate' to Mega", flush=True)
        if self.config.arm_ser is None or self.config.arm_lock is None:
            print("[GAME] No arm serial configured, skipping calibration", flush=True)
            return

        send_command("calibrate", self.config.arm_ser, self.config.arm_lock)
        print("[GAME] Calibration complete", flush=True)
        self.ui_link.set_mode(1)

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

    def _game_over_reason(self, board: chess.Board) -> str:
        outcome = board.outcome()
        if outcome is None:
            return "DRAW"
        if outcome.termination == chess.Termination.CHECKMATE:
            return "WHITE_WIN" if outcome.winner == chess.WHITE else "BLACK_WIN"
        if outcome.termination == chess.Termination.STALEMATE:
            return "STALEMATE"
        return "DRAW"

    def notify_turn_white(self) -> None:
        self.ui_link.player_turn_white()

    def notify_turn_black(self) -> None:
        self.ui_link.player_turn_black()
