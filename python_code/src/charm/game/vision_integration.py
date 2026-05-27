from __future__ import annotations

from dataclasses import dataclass

from charm.game.state_tracker import BoardStateTracker, MoveInferenceResult
from charm.vision.pipeline import BoardPipelineResult, run_board_pipeline


@dataclass
class VisionStateUpdateResult:
    pipeline_result: BoardPipelineResult
    inference_result: MoveInferenceResult


def infer_move_from_image(
    tracker: BoardStateTracker,
    image_path: str,
) -> VisionStateUpdateResult:
    pipeline_result = run_board_pipeline(image_path)
    inference_result = tracker.infer_move(
        pipeline_result.white_bitmap,
        pipeline_result.black_bitmap,
    )
    return VisionStateUpdateResult(
        pipeline_result=pipeline_result,
        inference_result=inference_result,
    )


def update_tracker_from_image(
    tracker: BoardStateTracker,
    image_path: str,
    max_mismatches: int = 0,
    flip_180: bool = False,
    use_occupancy_fallback: bool = True,
    max_occupancy_mismatches: int = 2,
) -> VisionStateUpdateResult:
    pipeline_result = run_board_pipeline(image_path)
    white_bitmap = pipeline_result.white_bitmap
    black_bitmap = pipeline_result.black_bitmap
    occupancy_matrix = pipeline_result.occupancy_matrix
    if flip_180:
        white_bitmap = [list(reversed(row)) for row in reversed(white_bitmap)]
        black_bitmap = [list(reversed(row)) for row in reversed(black_bitmap)]
        occupancy_matrix = [list(reversed(row)) for row in reversed(occupancy_matrix)]
    inference_result = tracker.update_from_bitmaps(
        white_bitmap,
        black_bitmap,
        max_mismatches=max_mismatches,
    )
    if (
        use_occupancy_fallback
        and inference_result.status == "invalid_observation"
    ):
        inference_result = tracker.update_from_occupancy(
            occupancy_matrix,
            max_mismatches=max_occupancy_mismatches,
        )
    return VisionStateUpdateResult(
        pipeline_result=pipeline_result,
        inference_result=inference_result,
    )
