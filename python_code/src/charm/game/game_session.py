from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

import chess

from charm.chess_engine.best_move import get_best_move
from charm.game.state_tracker import BoardStateTracker, compare_board_to_bitmaps
from charm.game.vision_integration import update_tracker_from_image
from charm.vision.pipeline import PipelineOptions, run_board_pipeline

Bitmap = list[list[int]]


PlayerColor = Literal["white", "black"]


@dataclass
class SessionResult:
    success: bool
    message: str
    move_uci: Optional[str] = None
    motion_step: Optional[str] = None
    mismatch_count: Optional[int] = None
    error_code: Optional[str] = None


@dataclass
class SessionStep:
    step_index: int
    image_path: str
    success: bool
    message: str
    move_uci: Optional[str] = None
    motion_step: Optional[str] = None
    mismatch_count: Optional[int] = None
    error_code: Optional[str] = None


class GameSession:
    """
    GameSession manages the software chess state.

    It does NOT:
      - capture photos
      - run raw camera calibration
      - talk directly to the mechanical arm

    It DOES:
      - validate the initial board from a calibrated board image
      - maintain the internal chess.Board through BoardStateTracker
      - detect player moves from calibrated board images
      - compute robot moves using Stockfish
      - verify robot moves from calibrated board images

    Important:
      All image_path inputs here must be calibrated / refined board images,
      not raw ESP32-CAM photos.
    """

    def __init__(self) -> None:
        self.initialized = False
        self.game_started = False
        self.flip_180 = False
        self.pipeline_options: Optional[PipelineOptions] = None

        self.player_color: Optional[PlayerColor] = None
        self.robot_color: Optional[PlayerColor] = None

        self.tracker: Optional[BoardStateTracker] = None
        self.steps: list[SessionStep] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _record_step(self, image_path: str, result: SessionResult) -> None:
        self.steps.append(
            SessionStep(
                step_index=len(self.steps),
                image_path=image_path,
                success=result.success,
                message=result.message,
                move_uci=result.move_uci,
                motion_step=result.motion_step,
                mismatch_count=result.mismatch_count,
                error_code=result.error_code,
            )
        )

    def _move_to_motion_step(self, move_uci: str) -> str:
        return f"{move_uci[:2]} -> {move_uci[2:4]}"

    def _require_initialized(self) -> Optional[SessionResult]:
        if not self.initialized or self.tracker is None:
            return SessionResult(
                success=False,
                message="Session is not initialized. Please validate the initial board first.",
            )
        return None

    def _require_game_started(self) -> Optional[SessionResult]:
        if not self.game_started:
            return SessionResult(
                success=False,
                message="Game has not started. Please choose player color first.",
            )
        return None

    # ------------------------------------------------------------------
    # Step 1: wait for start is handled by E2E controller
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.initialized = False
        self.game_started = False
        self.flip_180 = False
        self.pipeline_options = None
        self.player_color = None
        self.robot_color = None
        self.tracker = None
        self.steps = []

    # ------------------------------------------------------------------
    # Step 2: validate initial board
    # ------------------------------------------------------------------
    def initialize_from_image(
        self,
        image_path: str,
        max_mismatches: int = 0,
        flip_180: bool = False,
        pipeline_options: Optional[PipelineOptions] = None,
    ) -> SessionResult:
        """
        Validate the standard initial chess position from a calibrated board image.

        This should be called after:
          raw photo
          -> calibration method 1
          -> calibration method 2
          -> refined board image

        If the board matches the standard initial position, this creates the
        BoardStateTracker and the session becomes initialized.

        Pass `pipeline_options` to match the tuned detector params and empty-board
        reference used by the webapp's debug pipeline; otherwise legacy defaults apply.
        """
        pipeline_result = run_board_pipeline(image_path, options=pipeline_options)

        white_bitmap = pipeline_result.white_bitmap
        black_bitmap = pipeline_result.black_bitmap
        if flip_180:
            white_bitmap = [list(reversed(row)) for row in reversed(white_bitmap)]
            black_bitmap = [list(reversed(row)) for row in reversed(black_bitmap)]

        expected_board = chess.Board()
        mismatch_count = compare_board_to_bitmaps(
            expected_board,
            white_bitmap,
            black_bitmap,
        )

        if mismatch_count > max_mismatches:
            result = SessionResult(
                success=False,
                message=(
                    "Initial board setup is invalid. "
                    "Please reset the pieces to the standard starting position."
                ),
                mismatch_count=mismatch_count,
            )
            self._record_step(image_path, result)
            return result

        self.tracker = BoardStateTracker(expected_board)
        self.initialized = True
        self.game_started = False
        self.flip_180 = flip_180
        self.pipeline_options = pipeline_options
        self.player_color = None
        self.robot_color = None

        result = SessionResult(
            success=True,
            message=(
                "Initial board validated. "
                "Tracking started from the standard starting position. "
                "Please choose player color next."
            ),
            mismatch_count=mismatch_count,
        )
        self._record_step(image_path, result)
        return result

    def initialize_from_bitmaps(
        self,
        white_bitmap: Bitmap,
        black_bitmap: Bitmap,
        max_mismatches: int = 0,
        flip_180: bool = False,
    ) -> SessionResult:
        """CNN path: validate the initial board from pre-computed bitmaps."""
        wb = white_bitmap
        bb = black_bitmap
        if flip_180:
            wb = [list(reversed(row)) for row in reversed(wb)]
            bb = [list(reversed(row)) for row in reversed(bb)]

        expected_board = chess.Board()
        mismatch_count = compare_board_to_bitmaps(expected_board, wb, bb)

        if mismatch_count > max_mismatches:
            result = SessionResult(
                success=False,
                message=(
                    "Initial board setup is invalid. "
                    "Please reset the pieces to the standard starting position."
                ),
                mismatch_count=mismatch_count,
            )
            self._record_step("cnn_scan", result)
            return result

        self.tracker = BoardStateTracker(expected_board)
        self.initialized = True
        self.game_started = False
        self.flip_180 = False
        self.pipeline_options = None
        self.player_color = None
        self.robot_color = None

        result = SessionResult(
            success=True,
            message=(
                "Initial board validated via CNN. "
                "Tracking started from the standard starting position. "
                "Please choose player color next."
            ),
            mismatch_count=mismatch_count,
        )
        self._record_step("cnn_scan", result)
        return result

    def process_bitmaps(
        self,
        white_bitmap: Bitmap,
        black_bitmap: Bitmap,
        max_mismatches: int = 0,
    ) -> SessionResult:
        """CNN path: update the game tracker from pre-computed bitmaps."""
        init_error = self._require_initialized()
        if init_error is not None:
            self._record_step("cnn_scan", init_error)
            return init_error

        assert self.tracker is not None
        inference_result = self.tracker.update_from_bitmaps(
            white_bitmap, black_bitmap, max_mismatches=max_mismatches
        )

        if inference_result.move is None:
            board = self.tracker.board
            status = inference_result.status

            if status == "unchanged_position":
                error_code = "unchanged"
                message = "Board unchanged — did you complete your move before pressing done?"
            elif status == "ambiguous_observation":
                error_code = "ambiguous"
                n = inference_result.matching_move_count
                message = (
                    f"Ambiguous: {n} legal moves match the observed position. "
                    "Reposition your piece precisely and try again."
                )
            else:
                if board.is_check():
                    legal_count = board.legal_moves.count()
                    error_code = "in_check"
                    message = (
                        f"You are in check ({legal_count} escaping move{'s' if legal_count != 1 else ''} available) "
                        "— your move must resolve the check."
                    )
                else:
                    error_code = "illegal_move"
                    message = "Illegal move: the piece position does not match any legal move from the current position."

            result = SessionResult(
                success=False,
                message=message,
                mismatch_count=inference_result.mismatch_count,
                error_code=error_code,
            )
            self._record_step("cnn_scan", result)
            return result

        move_uci = inference_result.move.uci()
        result = SessionResult(
            success=True,
            message="Move recognized and board updated.",
            move_uci=move_uci,
            motion_step=self._move_to_motion_step(move_uci),
            mismatch_count=inference_result.mismatch_count,
        )
        self._record_step("cnn_scan", result)
        return result

    # ------------------------------------------------------------------
    # Step 3: choose player color and start game
    # ------------------------------------------------------------------
    def start_game(self, player_color: PlayerColor) -> SessionResult:
        """
        Start the game after the initial board has been validated.

        Args:
            player_color: "white" or "black"

        If player chooses white:
            player moves first, robot is black.

        If player chooses black:
            robot is white and should move first.
        """
        init_error = self._require_initialized()
        if init_error is not None:
            return init_error

        if player_color not in {"white", "black"}:
            return SessionResult(
                success=False,
                message=f"Invalid player color: {player_color}. Use 'white' or 'black'.",
            )

        self.player_color = player_color
        self.robot_color = "black" if player_color == "white" else "white"
        self.game_started = True

        if self.robot_color == "white":
            message = (
                "Game started. Player is black, robot is white. "
                "Robot should make the first move."
            )
        else:
            message = (
                "Game started. Player is white, robot is black. "
                "Player should make the first move."
            )

        return SessionResult(
            success=True,
            message=message,
        )

    # ------------------------------------------------------------------
    # Step 4: process player move
    # ------------------------------------------------------------------
    def process_player_move_from_image(
        self,
        image_path: str,
        max_mismatches: int = 0,
        pipeline_options: Optional[PipelineOptions] = None,
    ) -> SessionResult:
        """
        Process a calibrated board image after the human player has moved.

        This:
          - recognizes the new physical board state
          - compares it with the internal board
          - infers the player's move
          - updates the internal board if successful
        """
        init_error = self._require_initialized()
        if init_error is not None:
            self._record_step(image_path, init_error)
            return init_error

        start_error = self._require_game_started()
        if start_error is not None:
            self._record_step(image_path, start_error)
            return start_error

        return self.process_next_image(
            image_path=image_path,
            max_mismatches=max_mismatches,
            pipeline_options=pipeline_options,
        )

    def process_next_image(
        self,
        image_path: str,
        max_mismatches: int = 0,
        pipeline_options: Optional[PipelineOptions] = None,
    ) -> SessionResult:
        """
        Low-level method for processing any next calibrated board image.

        This can be used for:
          - player move detection
          - robot move verification

        Important:
          If a valid move is inferred, this method updates the internal board.
        """
        init_error = self._require_initialized()
        if init_error is not None:
            self._record_step(image_path, init_error)
            return init_error

        assert self.tracker is not None

        effective_options = pipeline_options if pipeline_options is not None else self.pipeline_options
        update_result = update_tracker_from_image(
            tracker=self.tracker,
            image_path=image_path,
            max_mismatches=max_mismatches,
            flip_180=self.flip_180,
            pipeline_options=effective_options,
        )

        inference_result = update_result.inference_result

        if inference_result.move is None:
            assert self.tracker is not None
            board = self.tracker.board
            status = inference_result.status

            if status == "unchanged_position":
                error_code = "unchanged"
                message = "Board unchanged — did you complete your move before pressing done?"
            elif status == "ambiguous_observation":
                error_code = "ambiguous"
                n = inference_result.matching_move_count
                message = (
                    f"Ambiguous: {n} legal moves match the observed position. "
                    "Reposition your piece precisely and try again."
                )
            else:
                if board.is_check():
                    legal_count = board.legal_moves.count()
                    error_code = "in_check"
                    message = (
                        f"You are in check ({legal_count} escaping move{'s' if legal_count != 1 else ''} available) "
                        "— your move must resolve the check."
                    )
                else:
                    error_code = "illegal_move"
                    message = "Illegal move: the piece position does not match any legal move from the current position."

            result = SessionResult(
                success=False,
                message=message,
                mismatch_count=inference_result.mismatch_count,
                error_code=error_code,
            )
            self._record_step(image_path, result)
            return result

        move_uci = inference_result.move.uci()

        result = SessionResult(
            success=True,
            message="Move recognized and board updated.",
            move_uci=move_uci,
            motion_step=self._move_to_motion_step(move_uci),
            mismatch_count=inference_result.mismatch_count,
        )
        self._record_step(image_path, result)
        return result

    # ------------------------------------------------------------------
    # Step 5: compute robot move with Stockfish
    # ------------------------------------------------------------------
    def compute_robot_move(
        self,
        engine_path: str = "stockfish",
        think_time: float = 0.1,
        skill_level: int = 12,
    ) -> SessionResult:
        """
        Compute the robot's next move using Stockfish.

        Important:
          This method does NOT update the internal board.
          It only computes what the robot should do.

        The board should be updated only after:
          - robot physically moves
          - camera captures verification image
          - verify_expected_move_from_image(...) succeeds
        """
        init_error = self._require_initialized()
        if init_error is not None:
            return init_error

        start_error = self._require_game_started()
        if start_error is not None:
            return start_error

        assert self.tracker is not None
        board = self.tracker.board

        if board.is_game_over():
            return SessionResult(
                success=False,
                message=f"Game is already over: {board.result()}",
            )

        best_move = get_best_move(
            board,
            engine_path=engine_path,
            think_time=think_time,
            skill_level=skill_level,
        )

        if best_move is None:
            return SessionResult(
                success=False,
                message="Stockfish did not return a move.",
            )

        move_uci = best_move.uci()

        return SessionResult(
            success=True,
            message="Robot move computed by Stockfish.",
            move_uci=move_uci,
            motion_step=self._move_to_motion_step(move_uci),
        )

    # ------------------------------------------------------------------
    # Step 6: verify robot move
    # ------------------------------------------------------------------
    def verify_expected_move_from_image(
        self,
        image_path: str,
        expected_move_uci: str,
        max_mismatches: int = 0,
    ) -> SessionResult:
        """
        Verify that the physical robot move matches the expected Stockfish move.

        Flow:
          current internal board
          + calibrated image after robot move
          -> infer actual physical move
          -> compare actual move with expected_move_uci

        If detected move equals expected_move_uci:
          success, internal board has been updated.

        Warning:
          This version calls process_next_image(), which updates the internal board
          as soon as it detects a valid move. If the robot made a wrong but legal
          move, the internal board may be updated before this method returns failure.
        """
        init_error = self._require_initialized()
        if init_error is not None:
            self._record_step(image_path, init_error)
            return init_error

        start_error = self._require_game_started()
        if start_error is not None:
            self._record_step(image_path, start_error)
            return start_error

        result = self.process_next_image(
            image_path=image_path,
            max_mismatches=max_mismatches,
        )

        if not result.success:
            return SessionResult(
                success=False,
                message=f"Robot move verification failed: {result.message}",
                move_uci=result.move_uci,
                motion_step=result.motion_step,
                mismatch_count=result.mismatch_count,
            )

        if result.move_uci != expected_move_uci:
            return SessionResult(
                success=False,
                message=(
                    f"Robot move verification failed. "
                    f"Expected {expected_move_uci}, but detected {result.move_uci}."
                ),
                move_uci=result.move_uci,
                motion_step=result.motion_step,
                mismatch_count=result.mismatch_count,
            )

        return SessionResult(
            success=True,
            message=f"Robot move verified successfully: {expected_move_uci}",
            move_uci=result.move_uci,
            motion_step=result.motion_step,
            mismatch_count=result.mismatch_count,
        )

    # ------------------------------------------------------------------
    # Optional fallback: manually commit robot move without vision
    # ------------------------------------------------------------------
    def commit_robot_move(self, move_uci: str) -> SessionResult:
        """
        Manually update the internal board after a robot move.

        Use this only if:
          - hardware verification is unavailable, or
          - you are running a mock test and manually confirm the robot move.

        In the real E2E flow, prefer verify_expected_move_from_image().
        """
        init_error = self._require_initialized()
        if init_error is not None:
            return init_error

        start_error = self._require_game_started()
        if start_error is not None:
            return start_error

        assert self.tracker is not None

        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            return SessionResult(
                success=False,
                message=f"Invalid UCI move: {move_uci}",
                move_uci=move_uci,
            )

        board = self.tracker.board

        if move not in board.legal_moves:
            return SessionResult(
                success=False,
                message=f"Illegal robot move for current board: {move_uci}",
                move_uci=move_uci,
            )

        board.push(move)

        result = SessionResult(
            success=True,
            message="Robot move committed to internal board.",
            move_uci=move_uci,
            motion_step=self._move_to_motion_step(move_uci),
        )

        self._record_step("manual_robot_commit", result)
        return result

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def is_initialized(self) -> bool:
        return self.initialized

    def is_game_started(self) -> bool:
        return self.game_started

    def robot_moves_first(self) -> bool:
        return self.game_started and self.robot_color == "white"

    def get_player_color(self) -> Optional[PlayerColor]:
        return self.player_color

    def get_robot_color(self) -> Optional[PlayerColor]:
        return self.robot_color

    def get_move_history(self) -> list[str]:
        return [step.move_uci for step in self.steps if step.move_uci is not None]

    def get_current_board(self) -> Optional[chess.Board]:
        """
        Return the current internal chess.Board, mainly for debugging or arm metadata.

        Example use:
            board = session.get_current_board()
            is_capture = board.is_capture(move)
        """
        if self.tracker is None:
            return None
        return self.tracker.board

    def get_current_fen(self) -> Optional[str]:
        """
        Return the current board FEN for debugging.
        """
        board = self.get_current_board()
        if board is None:
            return None
        return board.fen()

    def print_steps(self) -> None:
        """
        Print all recorded session steps in a readable format.
        """
        print("Session steps:")
        for step in self.steps:
            print(
                f"[{step.step_index}] "
                f"success={step.success}, "
                f"error_code={step.error_code}, "
                f"image={step.image_path}, "
                f"move={step.move_uci}, "
                f"motion={step.motion_step}, "
                f"mismatch={step.mismatch_count}, "
                f"message={step.message}"
            )