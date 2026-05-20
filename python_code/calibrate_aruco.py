"""Standalone ArUco calibration script (headless use only).

The webapp normally drives this through the ArucoCalibration component +
existing /api/calibration endpoints. Use this script when no browser is
available.

Step 1: ArUco outer-corner detection (auto)
Step 2: Visually confirm warp
Step 3: Click 4 inner corners on the warp for the refinement calibration

Saves to:
    - board_calibration.json  (outer corners on the raw image)
    - inner_warp_calibration.json  (inner corners on the first warp)
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.vision.aruco_calibration import (  # noqa: E402
    compute_board_corners_from_markers,
    detect_aruco_markers,
    draw_aruco_overlay,
)
from charm.vision.calibration_config import (  # noqa: E402
    DEFAULT_BOARD_CALIBRATION_JSON,
    DEFAULT_INNER_WARP_CALIBRATION_JSON,
)
from charm.vision.four_point_calibration import (  # noqa: E402
    InnerWarpCalibration,
    save_four_point_calibration,
    save_inner_warp_calibration,
    warp_from_calibration,
)
from charm.vision.transferphoto import fetch_raw_image  # noqa: E402


WARP_SIZE = 800


def _confirm(prompt: str) -> bool:
    ans = input(f"{prompt} [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def _collect_clicks(window: str, image: np.ndarray, count: int) -> list[tuple[int, int]]:
    """Block until the operator clicks `count` points; ESC aborts."""
    clicks: list[tuple[int, int]] = []
    canvas = image.copy()

    def _on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if len(clicks) >= count:
            return
        clicks.append((int(x), int(y)))
        cv2.circle(canvas, (x, y), 6, (0, 255, 0), -1)
        cv2.putText(
            canvas, str(len(clicks)), (x + 8, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA,
        )
        cv2.imshow(window, canvas)

    cv2.imshow(window, canvas)
    cv2.setMouseCallback(window, _on_mouse)
    while len(clicks) < count:
        key = cv2.waitKey(30) & 0xFF
        if key == 27:  # ESC
            raise KeyboardInterrupt("aborted by operator")
    return clicks


def main() -> int:
    print(f"Fetching frame from ESP32-CAM ...")
    raw_path = fetch_raw_image()
    raw = cv2.imread(raw_path)
    if raw is None:
        print(f"Could not read raw image: {raw_path}", file=sys.stderr)
        return 1

    print("Detecting ArUco markers ...")
    detections = detect_aruco_markers(raw)
    detected_ids = sorted({d.marker_id for d in detections})
    print(f"  detected ids: {detected_ids}")
    if len(detections) < 4:
        missing = sorted(set(range(4)) - set(detected_ids))
        print(f"ERROR: Need 4 markers (ids 0-3). Missing: {missing}", file=sys.stderr)
        return 2

    result = compute_board_corners_from_markers(detections)
    overlay = draw_aruco_overlay(raw, result)
    cv2.imshow("ArUco overlay (any key to continue)", overlay)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    cal = result.calibration
    first_warp = warp_from_calibration(raw, cal, output_size=WARP_SIZE)

    cv2.imshow("First warp — visually verify (any key to continue)", first_warp)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if not _confirm("Save board_calibration.json?"):
        print("Skipping save.")
        return 3

    save_four_point_calibration(cal, DEFAULT_BOARD_CALIBRATION_JSON)
    print(f"  wrote {DEFAULT_BOARD_CALIBRATION_JSON}")

    # ----- inner warp click step -----
    print("Click the 4 inner playing-area corners on the warp, in order:")
    print("  1) top-left  2) top-right  3) bottom-right  4) bottom-left")
    window = "Inner warp — click 4 corners (ESC = abort)"
    try:
        pts = _collect_clicks(window, first_warp, count=4)
    except KeyboardInterrupt:
        print("Inner warp click step aborted; board_calibration.json was still saved.")
        cv2.destroyAllWindows()
        return 4
    cv2.destroyAllWindows()

    inner_cal = InnerWarpCalibration(
        top_left=pts[0],
        top_right=pts[1],
        bottom_right=pts[2],
        bottom_left=pts[3],
    )
    save_inner_warp_calibration(inner_cal, DEFAULT_INNER_WARP_CALIBRATION_JSON)
    print(f"  wrote {DEFAULT_INNER_WARP_CALIBRATION_JSON}")
    print("Calibration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
