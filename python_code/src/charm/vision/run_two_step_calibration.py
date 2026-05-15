from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import os
import argparse


# This file is:
#   python_code/src/charm/vision/run_two_step_calibration.py
#
# parents[3] is:
#   python_code/
PYTHON_CODE_ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = PYTHON_CODE_ROOT / "src"

DEFAULT_RAW_IMAGE = PYTHON_CODE_ROOT / "latest_raw.jpg"

CALIBRATE_BOARD_SCRIPT = (
    PYTHON_CODE_ROOT / "src" / "charm" / "vision" / "calibrate_board_corners.py"
)

CALIBRATE_INNER_SCRIPT = (
    PYTHON_CODE_ROOT / "src" / "charm" / "vision" / "calibrate_inner_warp_corners.py"
)


def run_script(script_path: Path, image_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_PATH)

    command = [
        sys.executable,
        str(script_path),
        "--image",
        str(image_path),
    ]

    print()
    print("=" * 80)
    print("Running:")
    print(" ".join(command))
    print("=" * 80)

    subprocess.run(command, check=True, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run board corner calibration and inner warp calibration on one image."
    )

    parser.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_RAW_IMAGE,
        help="Image used for both calibration steps. Default: python_code/latest_raw.jpg",
    )

    args = parser.parse_args()
    raw_image = args.image

    if not raw_image.is_absolute():
        raw_image = Path.cwd() / raw_image

    raw_image = raw_image.resolve()

    if not raw_image.exists():
        raise FileNotFoundError(
            f"Raw image not found: {raw_image}\n"
            "Pass an existing image with --image."
        )

    print("=" * 80)
    print("Two-step calibration")
    print("=" * 80)
    print("Raw image:", raw_image)

    print()
    print("Step 1: board corner calibration")
    print("Click corners in order:")
    print("  top-left -> top-right -> bottom-right -> bottom-left")
    run_script(CALIBRATE_BOARD_SCRIPT, raw_image)

    print()
    print("Step 2: inner warp refinement calibration")
    print("Click refinement corners in order:")
    print("  top-left -> top-right -> bottom-right -> bottom-left")
    run_script(CALIBRATE_INNER_SCRIPT, raw_image)

    print()
    print("=" * 80)
    print("Done.")
    print("=" * 80)


if __name__ == "__main__":
    main()