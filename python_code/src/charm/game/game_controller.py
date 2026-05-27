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
from charm.chess_engine import (
    Evaluation,
    classify_move_rating,
    evaluate_position,
    format_score,
    win_percentage_from_cp,
    winning_color,
)
from charm.game.cv_scan import build_router, persist_validated_capture
from charm.game.game_session import GameSession, SessionResult
from charm.vision.cv_router import AttemptDecision


# Move-quality term flashed on the LCD (mirrors api_server._RATING_LCD_LABEL).
_RATING_LCD_LABEL = {
    "Blunder": "BLUNDER!",
    "Mistake": "MISTAKE!",
    "Inaccuracy": "INACCURACY",
    "Good": "GOOD",
    "Excellent": "EXCELLENT!",
}


# Shared with webapp_backend/api_server.py — both must resolve to the same
# absolute path (python_code/controller_game_state.json) so the webapp can
# poll the LCD-driven game state.
_CONTROLLER_STATE_FILE = (
    Path(__file__).resolve().parents[3] / "controller_game_state.json"
)


BoardImageProvider = Callable[[], str]
MoveExecutor = Callable[[], None]
DifficultyHandler = Callable[[int], None]
PhaseListener = Callable[[str, Optional[str], Optional[str]], None]
ScanListener = Callable[[dict], None]
EvaluationListener = Callable[[dict], None]


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
    # Called on every phase transition. Receives (phase, error_message, bot_move).
    # Used by the in-process api_server to surface phase to the webapp.
    on_phase_change: Optional[PhaseListener] = None
    # Called when a CV scan validates. Receives the pipeline debug payload
    # (refined_warp / occupancy_debug / cnn_overlay / bitmaps …) so the webapp
    # can render the same pipeline visualization it shows for webapp-driven play.
    on_scan_complete: Optional[ScanListener] = None
    # Called when a Stockfish evaluation is ready. Receives a GameEvaluation
    # dict matching the dashboard's Game Evaluation panel.
    on_evaluation_complete: Optional[EvaluationListener] = None
    # When True, also persist phase to controller_game_state.json (legacy file-based path).
    write_state_file: bool = False
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
        # Optional Direct-Elo strength levers (set via set_difficulty_params).
        # When use_limit_strength is True, Stockfish targets current_uci_elo and
        # ignores current_skill_level.
        self.current_uci_elo: Optional[int] = None
        self.current_use_limit_strength: bool = False
        self.current_phase: str = "idle"
        self.last_error: Optional[str] = None
        self.last_bot_move: Optional[str] = None
        # Most recent player-move evaluation, retained so the post-robot-move
        # panel can show "you played a Blunder; best was Nf3" alongside the
        # final position score.
        self.last_player_move_rating: Optional[str] = None
        self.last_player_cp_loss: Optional[int] = None
        self._last_player_best_move_san: Optional[str] = None
        self._last_player_best_move_uci: Optional[str] = None
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

        # Sync current game state to the ESP32 UI box if a game is already in
        # progress (e.g. the user started a session on the webapp, then booted
        # the LCD controller mid-game). Otherwise sit in the main menu.
        board = self.session.get_current_board() if self.session else None
        if self.session and self.session.initialized and self.session.game_started and board is not None:
            self.config.player_color = self.session.get_player_color() or "white"
            self.config.flip_180 = (self.config.player_color == "black")
            try:
                self.ui_link.set_difficulty(self.current_difficulty)
            except Exception as e:
                print(f"[GAME] Sync difficulty failed: {e}", flush=True)

            try:
                self.ui_link.set_mode(6)  # 6 = GAME mode
            except Exception as e:
                print(f"[GAME] Sync mode failed: {e}", flush=True)

            try:
                if board.is_game_over():
                    self.ui_link.game_over(self._game_over_reason(board))
                    self._write_state("game_over")
                else:
                    if board.turn == chess.WHITE:
                        self.ui_link.player_turn_white()
                    else:
                        self.ui_link.player_turn_black()
                    self._write_state("player_turn")
            except Exception as e:
                print(f"[GAME] Sync turn failed: {e}", flush=True)
        else:
            self._write_state("waiting")

    def stop(self) -> None:
        self.ui_link.close()

    def restart(self) -> None:
        """Fully reset the game session and return the LCD to its menu.

        Clears the shared session and the retained move-evaluation state, then
        sends the box back to MENU (mode 1) so the next game starts clean. A
        dead/offline ESP32 socket must not abort the reset, so the LCD write is
        best-effort.
        """
        self.session.reset()
        self.last_player_move_rating = None
        self.last_player_cp_loss = None
        self._last_player_best_move_san = None
        self._last_player_best_move_uci = None
        self.config.player_color = "white"
        self.config.flip_180 = False
        if self.ui_link:
            try:
                self.ui_link.set_mode(1)  # 1 = MENU mode
            except Exception as exc:
                print(f"[GAME] Restart: failed to reset LCD mode: {exc!r}", flush=True)
        self._write_state("waiting")

    def _write_state(self, phase: str, error_message: str = None, bot_move: str = None) -> None:
        """Publish a phase transition.

        In-process callers (webapp) receive the update via the
        ``on_phase_change`` callback; the file write is only kept for
        legacy callers that opt in via ``config.write_state_file``.
        """
        self.current_phase = phase
        self.last_error = error_message
        self.last_bot_move = bot_move

        if self.config.on_phase_change is not None:
            try:
                self.config.on_phase_change(phase, error_message, bot_move)
            except Exception as exc:
                print(f"[GAME] on_phase_change raised: {exc!r}", flush=True)

        if not self.config.write_state_file:
            return

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
            last_capture = [None]

            def _on_init_attempt(mode, idx, capture) -> AttemptDecision:
                print(f"[DEBUG] init attempt mode={mode} idx={idx}", flush=True)
                last_capture[0] = capture
                result = self.session.initialize_from_bitmaps(
                    capture.white_bitmap,
                    capture.black_bitmap,
                    max_mismatches=0,  # setup validation is strict — no noise tolerance
                    flip_180=self.config.flip_180,
                )
                last_initial["result"] = result
                # Emit only on success so the webapp overlay doesn't flicker
                # through intermediate failed frames during the retry loop.
                if result.success:
                    persist_validated_capture(capture, cfg, mode_used=mode, move_uci=None)
                    self._emit_scan(capture)
                return AttemptDecision(
                    success=result.success,
                    error=None if result.success else result.message,
                )

            router_result = router.scan(fns, _on_init_attempt)
            print(f"[DEBUG] router result: success={router_result.success} mode_used={router_result.mode_used} attempts={router_result.attempts_by_mode()}", flush=True)

            if not router_result.success or last_initial["result"] is None or not last_initial["result"].success:
                print("[DEBUG] RETURN FALSE: no attempt validated the initial board", flush=True)
                print("=======================================================\n", flush=True)
                # Emit the last captured frame once so the user can inspect what
                # the CV saw on failure (without flickering through every retry).
                if last_capture[0] is not None:
                    self._emit_scan(last_capture[0])
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
                # Player chose black — bot (white) moves first.
                # Start the robot move in a background thread so BOARD_OK is
                # sent back to the ESP32 immediately (before the 10-second
                # BOARD_TIMEOUT fires while the arm is still moving).
                threading.Thread(target=self._do_robot_move, daemon=True).start()
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

        # Snapshot the position the player faced *before* their move so we can
        # score the move quality once the scan commits it.
        board_before = self.session.get_current_board()
        board_before_copy = board_before.copy(stack=True) if board_before is not None else None
        player_turn_white = board_before.turn == chess.WHITE if board_before is not None else True

        router, fns, cfg = build_router()
        last_move: dict = {"result": None}
        last_capture = [None]

        def _on_move_attempt(mode, idx, capture) -> AttemptDecision:
            print(f"[DEBUG] move attempt mode={mode} idx={idx}", flush=True)
            last_capture[0] = capture
            result = self.session.process_bitmaps(
                capture.white_bitmap,
                capture.black_bitmap,
                max_mismatches=0,
            )
            last_move["result"] = result
            # Emit only on success so the webapp overlay doesn't flicker through
            # intermediate failed frames during the retry loop.
            if result.success:
                persist_validated_capture(capture, cfg, mode_used=mode, move_uci=result.move_uci)
                self._emit_scan(capture)
            return AttemptDecision(
                success=result.success,
                error=None if result.success else result.message,
            )

        router_result = router.scan(fns, _on_move_attempt)
        move_result: Optional[SessionResult] = last_move["result"]

        if not router_result.success or move_result is None or not move_result.success:
            msg = (move_result.message if move_result is not None else None) or "Illegal move"
            # Emit the last captured frame once so the user can inspect the
            # failed scan without flickering through every retry.
            if last_capture[0] is not None:
                self._emit_scan(last_capture[0])
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

        # Score the human move, flash the rating on the LCD, and surface the
        # interim (post-player) evaluation to the webapp.
        self._evaluate_player_move(board_before_copy, player_turn_white)

        # Check if the player's move ended the game.
        board = self.session.get_current_board()
        if board is not None and board.is_game_over():
            self.ui_link.game_over(self._game_over_reason(board))
            self._write_state("game_over")
            return

        if board is not None and board.is_check():
            self.ui_link.send_check()

        # Run the robot move in a background thread to prevent blocking the main loop.
        threading.Thread(target=self._do_robot_move, daemon=True).start()

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
            uci_elo=self.current_uci_elo,
            use_limit_strength=self.current_use_limit_strength,
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

        # Drive the arm off the session's flip (set at init for both colors and
        # already trusted by the camera read) rather than the config copy, so the
        # arm and detection can never disagree about board orientation.
        execute_move(robot_result.move_uci, board, self.config.arm_ser, self.config.arm_lock, flip_180=self.session.flip_180)

        # Commit the robot's move into the session's internal board.
        self.session.commit_robot_move(robot_result.move_uci)

        # Update the LCD with whose turn it is next, or show game over.
        updated_board = self.session.get_current_board()

        # Evaluate the final position and push the merged panel to the webapp:
        # final-position score + the retained player-move rating.
        self._emit_final_evaluation(updated_board)

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

    # ── Evaluation / scan plumbing ─────────────────────────────────────────

    def _emit_scan(self, capture) -> None:
        """Forward a validated scan's pipeline payload to the webapp."""
        if self.config.on_scan_complete is None:
            return
        try:
            self.config.on_scan_complete(capture.payload)
        except Exception as exc:
            print(f"[GAME] on_scan_complete raised: {exc!r}", flush=True)

    def _evaluate_safe(self, board: Optional[chess.Board]) -> Optional[Evaluation]:
        """Full-strength Stockfish probe; never raises into the game flow."""
        if board is None:
            return None
        try:
            return evaluate_position(
                board,
                engine_path=self.config.engine_path,
                think_time=self.config.think_time,
            )
        except FileNotFoundError:
            return None
        except Exception as exc:
            print(f"[GAME] evaluate_position failed: {exc!r}", flush=True)
            return None

    def _evaluation_panel(self, eval_for_panel: Evaluation) -> dict:
        """Shape an Evaluation + retained player rating for the dashboard panel."""
        return {
            "score": format_score(eval_for_panel.score_cp, eval_for_panel.mate),
            "score_cp": eval_for_panel.score_cp,
            "mate": eval_for_panel.mate,
            "winning_color": winning_color(eval_for_panel.score_cp, eval_for_panel.mate),
            "win_percentage": round(
                win_percentage_from_cp(eval_for_panel.score_cp, eval_for_panel.mate), 1
            ),
            "player_move_rating": self.last_player_move_rating,
            "player_cp_loss": self.last_player_cp_loss,
            # best_move_* = what Stockfish wanted *before* the player moved,
            # so the UI can say "try X instead".
            "best_move_suggestion": self._last_player_best_move_san
            or eval_for_panel.best_move_san,
            "best_move_uci": self._last_player_best_move_uci
            or eval_for_panel.best_move_uci,
        }

    def _emit_evaluation(self, eval_for_panel: Optional[Evaluation]) -> None:
        if eval_for_panel is None or self.config.on_evaluation_complete is None:
            return
        try:
            self.config.on_evaluation_complete(self._evaluation_panel(eval_for_panel))
        except Exception as exc:
            print(f"[GAME] on_evaluation_complete raised: {exc!r}", flush=True)

    def _evaluate_player_move(
        self, board_before: Optional[chess.Board], player_turn_white: bool
    ) -> None:
        """Score the just-committed human move, flash the LCD, emit the eval."""
        board_after = self.session.get_current_board()
        eval_before = self._evaluate_safe(board_before)
        eval_after = self._evaluate_safe(board_after)
        if eval_before is None or eval_after is None:
            self._emit_evaluation(eval_after or eval_before)
            return

        # Convert White-POV scores to the moving player's POV so a "loss" is
        # always a drop in the moving side's eval.
        sign = 1 if player_turn_white else -1
        cp_before = (eval_before.score_cp or 0) * sign
        cp_after = (eval_after.score_cp or 0) * sign
        mate_before = eval_before.mate
        mate_after = eval_after.mate
        if not player_turn_white:
            mate_before = -mate_before if mate_before is not None else None
            mate_after = -mate_after if mate_after is not None else None

        rating, cp_loss = classify_move_rating(cp_before, cp_after, mate_before, mate_after)
        self.last_player_move_rating = rating
        self.last_player_cp_loss = cp_loss
        self._last_player_best_move_san = eval_before.best_move_san
        self._last_player_best_move_uci = eval_before.best_move_uci

        label = _RATING_LCD_LABEL.get(rating)
        if label is not None:
            try:
                self.ui_link.error_msg(label)
                time.sleep(2.0)
                # error_msg puts the LCD in ERROR mode (line 1 = "Illegal move !").
                # The move was legal, so restore GAME mode (6) to resume normal
                # turn-status display instead of leaving the box stuck on ERROR.
                self.ui_link.set_mode(6)
            except Exception as exc:
                print(f"[GAME] LCD rating flash failed: {exc!r}", flush=True)

        # Interim panel uses the post-player position.
        self._emit_evaluation(eval_after)

    def _emit_final_evaluation(self, final_board: Optional[chess.Board]) -> None:
        """Push the final-position panel (merged with retained player rating)."""
        self._emit_evaluation(self._evaluate_safe(final_board))

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
        # The vision scan already applies a 180° correction for the camera
        # mount, so a White setup is already in standard coordinates → no flip.
        # A Black setup is physically rotated 180° relative to standard
        # coordinates (White on ranks 7–8), so it must be flipped.
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

    def set_difficulty_params(
        self,
        skill_level: Optional[int] = None,
        think_time: Optional[float] = None,
        uci_elo: Optional[int] = None,
        use_limit_strength: bool = False,
    ) -> None:
        """Apply extended Stockfish strength levers mid-game.

        Used by the webapp's advanced difficulty modal. Bypasses the legacy
        1–20 ``difficulty`` → skill mapping so LCD-driven robot moves use the
        same skill level / think time / Direct-Elo settings as the dashboard.
        """
        if skill_level is not None:
            self.current_skill_level = max(0, min(20, int(skill_level)))
        if think_time is not None:
            self.config.think_time = float(think_time)
        self.current_uci_elo = uci_elo
        self.current_use_limit_strength = bool(use_limit_strength)

    def _on_promotion_choice(self, piece: str) -> None:
        """Called by the bridge when ESP32 sends PROMOTION_CHOICE <piece>."""
        self._promotion_piece = piece.lower()
        self._promotion_event.set()

    def handle_manual_control(self, cmd: str) -> None:
        """Relay a manual jog command from the ESP32 to the Mega."""
        _CMD_MAP = {
            "MANUAL_JOINT1_FWD":    "jogJ1 0.5",
            "MANUAL_JOINT1_BWD":    "jogJ1 -0.5",
            "MANUAL_JOINT2_FWD":    "jogJ2 0.5",
            "MANUAL_JOINT2_BWD":    "jogJ2 -0.5",
            "MANUAL_Z_FWD":         "jogZ 2",
            "MANUAL_Z_BWD":         "jogZ -2",
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
