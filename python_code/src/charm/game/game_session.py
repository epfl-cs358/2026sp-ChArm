from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess

from charm.game.state_tracker import BoardStateTracker, board_to_bitmaps, compare_board_to_bitmaps
from charm.game.vision_integration import update_tracker_from_image
from charm.vision.pipeline import run_board_pipeline


@dataclass
class SessionResult:
    success: bool
    message: str
    move_uci: Optional[str] = None
    motion_step: Optional[str] = None
    mismatch_count: Optional[int] = None


@dataclass
class SessionStep:
    step_index: int
    image_path: str
    success: bool
    message: str
    move_uci: Optional[str] = None
    motion_step: Optional[str] = None
    mismatch_count: Optional[int] = None


class GameSession:
    def __init__(self) -> None:
        self.initialized = False
        self.tracker: Optional[BoardStateTracker] = None
        self.steps: list[SessionStep] = []

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
            )
        )

    def initialize_from_image(self, image_path: str, max_mismatches: int = 0) -> SessionResult:
        pipeline_result = run_board_pipeline(image_path)

        expected_board = chess.Board()
        mismatch_count = compare_board_to_bitmaps(
            expected_board,
            pipeline_result.white_bitmap,
            pipeline_result.black_bitmap,
        )

        if mismatch_count > max_mismatches:
            result = SessionResult(
                success=False,
                message="Initial board setup is invalid. Please reset the board to the standard starting position.",
                mismatch_count=mismatch_count,
            )
            self._record_step(image_path, result)
            return result

        self.tracker = BoardStateTracker(expected_board)
        self.initialized = True

        result = SessionResult(
            success=True,
            message="Initial board validated. Tracking started from the standard starting position.",
            mismatch_count=mismatch_count,
        )
        self._record_step(image_path, result)
        return result

    def process_next_image(self, image_path: str, max_mismatches: int = 0) -> SessionResult:
        if not self.initialized or self.tracker is None:
            result = SessionResult(
                success=False,
                message="Session is not initialized. Please validate the initial board first.",
            )
            self._record_step(image_path, result)
            return result

        update_result = update_tracker_from_image(
            tracker=self.tracker,
            image_path=image_path,
            max_mismatches=max_mismatches,
        )

        inference_result = update_result.inference_result

        if inference_result.move is None:
            result = SessionResult(
                success=False,
                message="No valid move could be inferred from the current image.",
                mismatch_count=inference_result.mismatch_count,
            )
            self._record_step(image_path, result)
            return result

        move_uci = inference_result.move.uci()

        result = SessionResult(
            success=True,
            message="Move recognized and board updated.",
            move_uci=move_uci,
            motion_step=f"{move_uci[:2]} -> {move_uci[2:4]}",
            mismatch_count=inference_result.mismatch_count,
        )
        self._record_step(image_path, result)
        return result

    # Additional helper methods for accessing session data
    def get_move_history(self) -> list[str]:
        return [step.move_uci for step in self.steps if step.move_uci is not None]

    # This method is for demonstration purposes to print the session steps in a readable format
    def print_steps(self) -> None:
        print("Session steps:")
        for step in self.steps:
            print(
                f"[{step.step_index}] "
                f"success={step.success}, "
                f"image={step.image_path}, "
                f"move={step.move_uci}, "
                f"motion={step.motion_step}, "
                f"mismatch={step.mismatch_count}, "
                f"message={step.message}"
            )