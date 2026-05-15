from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from charm.vision.four_point_calibration import (
    draw_calibration_points,
    draw_inner_warp_points,
    load_four_point_calibration,
    load_inner_warp_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)
from charm.vision.pipeline import BoardPipelineResult, run_board_pipeline


# calibrated_pipeline.py is located at:
#   python_code/src/charm/vision/calibrated_pipeline.py
#
# parents[3] points to:
#   python_code/
PYTHON_CODE_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_BOARD_CALIBRATION_PATH = PYTHON_CODE_ROOT / "board_calibration.json"
DEFAULT_INNER_WARP_CALIBRATION_PATH = PYTHON_CODE_ROOT / "inner_warp_calibration.json"


@dataclass
class CalibratedBoardResult:
    raw_image_path: Path
    first_warp_path: Path
    refined_warp_path: Path
    calibration_1_debug_path: Path
    calibration_2_debug_path: Path
    grid_debug_path: Path
    occupancy_debug_path: Path
    piece_color_debug_path: Path
    pipeline_result: BoardPipelineResult


def calibrate_raw_image_to_board_image(
    raw_image_path: str | Path,
    four_point_calibration_path: str | Path | None = None,
    inner_warp_calibration_path: str | Path | None = None,
    output_dir: str | Path = PYTHON_CODE_ROOT / "e2e_debug" / "calibrated_pipeline",
    name_prefix: str = "board",
    output_size: int = 800,
) -> Path:
    """
    Convert one raw camera image into one calibrated board image.

    Default calibration JSON locations:
      python_code/board_calibration.json
      python_code/inner_warp_calibration.json

    Pipeline:
      raw camera image
      -> calibration method 1: four-point perspective warp
      -> calibration method 2: inner-corner refinement warp
      -> refined 800x800 board image

    Returns:
      Path to the refined calibrated board image.
    """
    raw_image_path = Path(raw_image_path)

    four_point_calibration_path = (
        Path(four_point_calibration_path)
        if four_point_calibration_path is not None
        else DEFAULT_BOARD_CALIBRATION_PATH
    )

    inner_warp_calibration_path = (
        Path(inner_warp_calibration_path)
        if inner_warp_calibration_path is not None
        else DEFAULT_INNER_WARP_CALIBRATION_PATH
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not raw_image_path.exists():
        raise FileNotFoundError(f"Raw image not found: {raw_image_path}")

    if not four_point_calibration_path.exists():
        raise FileNotFoundError(
            f"Four-point calibration JSON not found: {four_point_calibration_path}"
        )

    if not inner_warp_calibration_path.exists():
        raise FileNotFoundError(
            f"Inner-warp calibration JSON not found: {inner_warp_calibration_path}"
        )

    image = cv2.imread(str(raw_image_path))

    if image is None:
        raise FileNotFoundError(f"Could not read raw image: {raw_image_path}")

    four_point_calibration = load_four_point_calibration(four_point_calibration_path)
    inner_warp_calibration = load_inner_warp_calibration(inner_warp_calibration_path)

    calibration_1_debug = draw_calibration_points(
        image=image,
        calibration=four_point_calibration,
    )
    calibration_1_debug_path = output_dir / f"{name_prefix}_calibration_1_points.png"
    cv2.imwrite(str(calibration_1_debug_path), calibration_1_debug)

    first_warp = warp_from_calibration(
        image=image,
        calibration=four_point_calibration,
        output_size=output_size,
    )
    first_warp_path = output_dir / f"{name_prefix}_first_warp.png"
    cv2.imwrite(str(first_warp_path), first_warp)

    calibration_2_debug = draw_inner_warp_points(
        image=first_warp,
        calibration=inner_warp_calibration,
    )
    calibration_2_debug_path = output_dir / f"{name_prefix}_calibration_2_points.png"
    cv2.imwrite(str(calibration_2_debug_path), calibration_2_debug)

    refined_warp = refine_board_with_inner_corners(
        warped_board=first_warp,
        calibration=inner_warp_calibration,
        output_size=output_size,
    )
    refined_warp_path = output_dir / f"{name_prefix}_refined_warp.png"
    cv2.imwrite(str(refined_warp_path), refined_warp)

    return refined_warp_path


def run_calibrated_board_pipeline(
    raw_image_path: str | Path,
    four_point_calibration_path: str | Path | None = None,
    inner_warp_calibration_path: str | Path | None = None,
    output_dir: str | Path = PYTHON_CODE_ROOT / "e2e_debug" / "calibrated_pipeline",
    name_prefix: str = "board",
    output_size: int = 800,
) -> CalibratedBoardResult:
    """
    Full raw-photo vision wrapper.

    Default calibration JSON locations:
      python_code/board_calibration.json
      python_code/inner_warp_calibration.json

    Pipeline:
      raw camera image
      -> calibration method 1
      -> calibration method 2
      -> run_board_pipeline(refined_warp)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    four_point_calibration_path = (
        Path(four_point_calibration_path)
        if four_point_calibration_path is not None
        else DEFAULT_BOARD_CALIBRATION_PATH
    )

    inner_warp_calibration_path = (
        Path(inner_warp_calibration_path)
        if inner_warp_calibration_path is not None
        else DEFAULT_INNER_WARP_CALIBRATION_PATH
    )

    refined_warp_path = calibrate_raw_image_to_board_image(
        raw_image_path=raw_image_path,
        four_point_calibration_path=four_point_calibration_path,
        inner_warp_calibration_path=inner_warp_calibration_path,
        output_dir=output_dir,
        name_prefix=name_prefix,
        output_size=output_size,
    )

    pipeline_result = run_board_pipeline(str(refined_warp_path))

    grid_debug_path = output_dir / f"{name_prefix}_grid_debug.png"
    occupancy_debug_path = output_dir / f"{name_prefix}_occupancy_debug.png"
    piece_color_debug_path = output_dir / f"{name_prefix}_piece_color_debug.png"

    cv2.imwrite(str(grid_debug_path), pipeline_result.grid_debug_image)
    cv2.imwrite(str(occupancy_debug_path), pipeline_result.occupancy_debug_image)
    cv2.imwrite(str(piece_color_debug_path), pipeline_result.piece_color_debug_image)

    return CalibratedBoardResult(
        raw_image_path=Path(raw_image_path),
        first_warp_path=output_dir / f"{name_prefix}_first_warp.png",
        refined_warp_path=refined_warp_path,
        calibration_1_debug_path=output_dir / f"{name_prefix}_calibration_1_points.png",
        calibration_2_debug_path=output_dir / f"{name_prefix}_calibration_2_points.png",
        grid_debug_path=grid_debug_path,
        occupancy_debug_path=occupancy_debug_path,
        piece_color_debug_path=piece_color_debug_path,
        pipeline_result=pipeline_result,
    )