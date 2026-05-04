from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # python_code

DEFAULT_BOARD_CALIBRATION_JSON = ROOT / "board_calibration.json"
DEFAULT_INNER_WARP_CALIBRATION_JSON = ROOT / "inner_warp_calibration.json"