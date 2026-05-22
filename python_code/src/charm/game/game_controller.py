from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import chess
import serial

from charm.arduino.uiController_bridge import ArduinoUIControllerLink
from charm.arduino.arduino_bridge import execute_move, send_command
from charm.game.cv_scan import build_router, persist_validated_capture
from charm.game.game_session import GameSession, SessionResult
from charm.vision.cv_router import AttemptDecision


# Shared with webapp_backend/api_server.py — both must resolve to the same
# absolute path (python_code/controller_game_state.json) so the webapp can
# poll the LCD-driven game state.
_CONTROLLER_STATE_FILE = (
    Path(__file__).resolve().parents[3] / "controller_game_state.json"
)


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
    def __init__(
        self,
        ui_link: ArduinoUIControllerLink,
        session: Optional[GameSession],
        config: GameControllerConfig,
    ) -> None:
        self.ui_link = ui_link
        self.session = session if session is not None else GameSession()
        self.config = config
        self.current_difficulty = 10  # Default level 10 out of 20
        self.current_skill_level = 9  # Stockfish skill = difficulty - 1
        self._promotion_event = threading.Event()
        self._promotion_piece: str = "q"
        self.ui_link.set_handlers(
            on_check_board=self.check_board,
            on_player_done=self.player_done,
            on_set_difficulty=self.set_difficulty,
            on_set_color=self.set_player_color,
            on_calibration=self.run_calibration,
            on_manual_control=self.handle_manual_control,
            on_promotion_choice=self._on_promotion_choice,
        )

    def start(self) -> None:
        self.ui_link.start()
        self._write_state("waiting")

    def stop(self) -> None:
        self.ui_link.close()

    def _write_state(self, phase: str, error_message: str = None, bot_move: str = None) -> None:
        """Atomically publish current game state for the webapp to poll."""
        board = self.session.get_current_board()
        state = {
            "phase": phase,
            "fen": board.fen() if board is not None else None,
            "moves": self.session.get_move_history(),
            "player_color": self.session.get_player_color(),
            "robot_color": self.session.get_robot_color(),
            "difficulty": self.current_difficulty,
            "error_message": error_message,
            "bot_move": bot_move,
            "updated_at": time.time(),
        }
        try:
            tmp = _CONTROLLER_STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state))
            tmp.replace(_CONTROLLER_STATE_FILE)  # atomic on POSIX
        except Exception as exc:
            print(f"[GAME] failed to write state file: {exc!r}", flush=True)

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
            self._write_state("checking_board")

            router, fns, cfg = build_router()
            print(f"[DEBUG] router: primary={cfg.primary} attempts_each={cfg.attempts_each} modes={list(fns.keys())}", flush=True)

            last_initial: dict = {"result": None}

            def _on_init_attempt(mode, idx, capture) -> AttemptDecision:
                print(f"[DEBUG] init attempt mode={mode} idx={idx}", flush=True)
                result = self.session.initialize_from_bitmaps(
                    capture.white_bitmap,
                    capture.black_bitmap,
                    max_mismatches=0,
                    flip_180=self.config.flip_180,
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
                self._write_state("error")
                return False

            print("[DEBUG] Step 3: start_game()", flush=True)
            print("[DEBUG] config.player_color =", self.config.player_color, flush=True)
            start_result = self.session.start_game(self.config.player_color)
            print("[DEBUG] start_result.success =", start_result.success, flush=True)
            print("[DEBUG] start_result.message =", start_result.message, flush=True)

            if not start_result.success:
                print("[DEBUG] RETURN FALSE: start_game failed", flush=True)
                print("=======================================================\n", flush=True)
                self._write_state("error")
                return False

            print("[DEBUG] RETURN TRUE: check_board success", flush=True)
            print("=======================================================\n", flush=True)
            if self.session.robot_moves_first():
                # Player chose black — bot (white) moves first; _do_robot_move
                # sends player_turn_white + bot_thinking internally.
                self._do_robot_move()
            else:
                self.ui_link.player_turn_white()
                self._write_state("player_turn")
            return True

        except Exception as e:
            print("[DEBUG] EXCEPTION in check_board:", repr(e), flush=True)
            import traceback
            traceback.print_exc()
            print("[DEBUG] RETURN FALSE because exception occurred", flush=True)
            print("=======================================================\n", flush=True)
            self._write_state("error")
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
            msg = (move_result.message if move_result is not None else None) or "Illegal move"
            self.ui_link.error_msg(msg)
            self._write_state("error", error_message=msg)
            return

        # If the player promoted a pawn, ask which piece they want.
        if move_result.move_uci and len(move_result.move_uci) == 5:
            self._promotion_event.clear()
            self.ui_link.promotion_needed()
            self._promotion_event.wait(timeout=60.0)
            chosen = self._promotion_piece
            if chosen != "q":
                self.session.fix_last_promotion(chosen)

        # Check if the player's move ended the game.
        board = self.session.get_current_board()
        if board is not None and board.is_game_over():
            self.ui_link.game_over(self._game_over_reason(board))
            self._write_state("game_over")
            return

        if board is not None and board.is_check():
            self.ui_link.send_check()

        self._do_robot_move()

    def _do_robot_move(self) -> None:
        """Compute, physically execute, and commit the robot's next move."""
        # Tell the LCD whose turn it is (the bot's colour) and that it's thinking.
        # Doing this here makes the method self-contained so it works whether
        # called from player_done() or directly from check_board().
        init_board = self.session.get_current_board()
        if init_board is not None:
            if init_board.turn == chess.WHITE:
                self.ui_link.player_turn_white()
            else:
                self.ui_link.player_turn_black()
        self.ui_link.bot_thinking()
        self._write_state("bot_thinking")

        robot_result = self.session.compute_robot_move(
            engine_path=self.config.engine_path,
            think_time=self.config.think_time,
            skill_level=self.current_skill_level,
        )

        if not robot_result.success:
            self.ui_link.move_done()
            self._write_state("error")
            return

        # board must be read BEFORE committing so execute_move and _format_bot_move
        # can inspect piece types and capture info from the pre-move board state.
        board = self.session.get_current_board()
        if board is None:
            return

        move_label = self._format_bot_move(robot_result.move_uci, board)
        self.ui_link.bot_move(move_label)
        self.ui_link.bot_moving()
        if len(robot_result.move_uci) == 5:
            self.ui_link.bot_promoting(robot_result.move_uci[4])
        self._write_state("bot_moving", bot_move=move_label)

        execute_move(robot_result.move_uci, board, self.config.arm_ser, self.config.arm_lock, flip_180=self.config.flip_180)

        # Commit the robot's move into the session's internal board.
        self.session.commit_robot_move(robot_result.move_uci)

        # Update the LCD with whose turn it is next, or show game over.
        updated_board = self.session.get_current_board()
        if updated_board is not None and updated_board.is_game_over():
            self.ui_link.game_over(self._game_over_reason(updated_board))
            self._write_state("game_over")
            return

        if updated_board is not None:
            if updated_board.turn == chess.WHITE:
                self.ui_link.player_turn_white()
            else:
                self.ui_link.player_turn_black()
            if updated_board.is_check():
                self.ui_link.send_check()

        self.ui_link.move_done()
        self._write_state("player_turn")

    def run_calibration(self) -> None:
        """Called by the bridge when the ESP32 sends CALIBRATION. Forwards the
        calibrate command to the Mega so the arm runs its homing routine."""
        print("[GAME] CALIBRATION received — sending 'calibrate' to Mega", flush=True)
        if self.config.arm_ser is None or self.config.arm_lock is None:
            print("[GAME] No arm serial configured, skipping calibration", flush=True)
            return

        self._write_state("arm_calibrating")
        send_command("calibrate", self.config.arm_ser, self.config.arm_lock)
        print("[GAME] Calibration complete", flush=True)
        self.ui_link.set_mode(1)
        self._write_state("waiting")

    def set_player_color(self, color: str) -> None:
        """Called by the bridge when Arduino sends SET_COLOR (color selection screen)."""
        self.config.player_color = color
        self.config.flip_180 = (color == "black")
        self._write_state("waiting")

    def set_difficulty(self, difficulty: int) -> None:
        """Update Stockfish skill level based on Arduino difficulty setting.

        Args:
            difficulty: Numeric level 1–20 from the ESP32 slider.
                        Maps to Stockfish skill 0–19 (level 1 → skill 0).
        """
        self.current_difficulty = difficulty
        self.current_skill_level = max(0, min(19, difficulty - 1))

        if self.config.on_set_difficulty is not None:
            self.config.on_set_difficulty(difficulty)
        self._write_state("waiting")

    def _on_promotion_choice(self, piece: str) -> None:
        """Called by the bridge when ESP32 sends PROMOTION_CHOICE <piece>."""
        self._promotion_piece = piece.lower()
        self._promotion_event.set()

    def handle_manual_control(self, cmd: str) -> None:
        """Relay a manual jog command from the ESP32 to the Mega."""
        _CMD_MAP = {
            "MANUAL_JOINT1_FWD":    "jogJ1 2.0",
            "MANUAL_JOINT1_BWD":    "jogJ1 -2.0",
            "MANUAL_JOINT2_FWD":    "jogJ2 2.0",
            "MANUAL_JOINT2_BWD":    "jogJ2 -2.0",
            "MANUAL_Z_FWD":         "jogZ 0.5",
            "MANUAL_Z_BWD":         "jogZ -0.5",
            "MANUAL_GRIPPER_OPEN":  "OG",
            "MANUAL_GRIPPER_CLOSE": "CG",
        }
        mega_cmd = _CMD_MAP.get(cmd)
        if mega_cmd is None:
            print(f"[GAME] Unknown manual control command: {cmd}", flush=True)
            return
        if self.config.arm_ser is None or self.config.arm_lock is None:
            print(f"[GAME] No arm serial configured, ignoring {cmd}", flush=True)
            return
        print(f"[GAME] Manual control: {cmd} -> {mega_cmd}", flush=True)
        send_command(mega_cmd, self.config.arm_ser, self.config.arm_lock)

    def _format_bot_move(self, uci: str, board: chess.Board) -> str:
        try:
            move = chess.Move.from_uci(uci)
            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)
            if board.is_castling(move):
                return "O-O-O" if board.is_queenside_castling(move) else "O-O"
            promo = ("=" + chess.piece_symbol(move.promotion).upper()) if move.promotion else ""
            if board.is_en_passant(move):
                return f"{from_sq}x{to_sq} ep{promo}"
            if board.is_capture(move):
                return f"{from_sq}x{to_sq}{promo}"
            return f"{from_sq}->{to_sq}{promo}"
        except Exception:
            return uci

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
