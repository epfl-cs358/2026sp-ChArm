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


class GameSession:
    def __init__(self) -> None:
        self.initialized = False
        self.tracker: Optional[BoardStateTracker] = None

    def initialize_from_image(self, image_path: str, max_mismatches: int = 0) -> SessionResult:
        """
        Mode A:
        Validate that the first image matches the standard chess starting position.
        """
        pipeline_result = run_board_pipeline(image_path)

        expected_board = chess.Board()
        expected_white_bitmap, expected_black_bitmap = board_to_bitmaps(expected_board)

        mismatch_count = compare_board_to_bitmaps(
            expected_board,
            pipeline_result.white_bitmap,
            pipeline_result.black_bitmap,
        )

        if mismatch_count > max_mismatches:
            return SessionResult(
                success=False,
                message="Initial board setup is invalid. Please reset the board to the standard starting position.",
                mismatch_count=mismatch_count,
            )

        self.tracker = BoardStateTracker(expected_board)
        self.initialized = True

        return SessionResult(
            success=True,
            message="Initial board validated. Tracking started from the standard starting position.",
            mismatch_count=mismatch_count,
        )

    def process_next_image(self, image_path: str, max_mismatches: int = 0) -> SessionResult:
        """
        Mode B:
        Infer one move from a new image and update the tracker.
        """
        if not self.initialized or self.tracker is None:
            return SessionResult(
                success=False,
                message="Session is not initialized. Please validate the initial board first.",
            )

        update_result = update_tracker_from_image(
            tracker=self.tracker,
            image_path=image_path,
            max_mismatches=max_mismatches,
        )

        inference_result = update_result.inference_result

        if inference_result.move is None:
            return SessionResult(
                success=False,
                message="No valid move could be inferred from the current image.",
                mismatch_count=inference_result.mismatch_count,
            )

        move_uci = inference_result.move.uci()

        return SessionResult(
            success=True,
            message="Move recognized and board updated.",
            move_uci=move_uci,
            motion_step=f"{move_uci[:2]} -> {move_uci[2:4]}",
            mismatch_count=inference_result.mismatch_count,
        )
    