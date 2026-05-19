from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from charm.game.state_tracker import BoardStateTracker, MoveInferenceResult
from charm.vision.pipeline import BoardPipelineResult, PipelineOptions, run_board_pipeline


@dataclass
class VisionStateUpdateResult:
    pipeline_result: BoardPipelineResult
    inference_result: MoveInferenceResult


def infer_move_from_image(
    tracker: BoardStateTracker,
    image_path: str,
    pipeline_options: Optional[PipelineOptions] = None,
) -> VisionStateUpdateResult:
    pipeline_result = run_board_pipeline(image_path, options=pipeline_options)
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
    pipeline_options: Optional[PipelineOptions] = None,
) -> VisionStateUpdateResult:
    pipeline_result = run_board_pipeline(image_path, options=pipeline_options)
    white_bitmap = pipeline_result.white_bitmap
    black_bitmap = pipeline_result.black_bitmap
    if flip_180:
        white_bitmap = [list(reversed(row)) for row in reversed(white_bitmap)]
        black_bitmap = [list(reversed(row)) for row in reversed(black_bitmap)]
    inference_result = tracker.update_from_bitmaps(
        white_bitmap,
        black_bitmap,
        max_mismatches=max_mismatches,
    )
    return VisionStateUpdateResult(
        pipeline_result=pipeline_result,
        inference_result=inference_result,
    )
