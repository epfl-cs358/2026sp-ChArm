from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.arduino.arduino_bridge import ArduinoBridge

print("Sending test move: e2 -> e4")
with ArduinoBridge() as bridge:
    bridge.execute_move("e2e4", is_capture=False, is_castling=False, is_promotion=False)
print("Done.")
