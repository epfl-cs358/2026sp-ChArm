"""
demo_ui_bridge.py — end-to-end UI communication test

Tests the REAL serial link between Python (uiController_bridge) and the Arduino
(UIController). No camera, no chess engine, no robot movement — everything
game-related is stubbed.

Arduino side: flash with the 'ui_test' env (main_ui_test.cpp).

Usage:
    python demo_ui_bridge.py --port /dev/cu.usbmodem1401
    python demo_ui_bridge.py --port /dev/cu.usbmodem1401 --baud 115200

What it does automatically:
  CHECK_BOARD  -> always replies BOARD_OK  (no camera needed)
  PLAYER_DONE  -> BOT_THINKING (1 s) -> BOT_MOVING (2 s) -> PLAYER_TURN_WHITE (1 s)
  SET_DIFFICULTY <n> -> just prints it

Ctrl-C to quit.
"""

from __future__ import annotations

import argparse
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.arduino.uiController_bridge import ArduinoUIControllerLink


def log(tag: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {tag:12s} {msg}", flush=True)


def make_check_board_handler(link: ArduinoUIControllerLink):
    def check_board() -> bool:
        log("CHECK_BOARD", "received — replying BOARD_OK (stubbed)")
        # handler must return True/False; bridge already sends BOARD_OK/FAIL
        return True
    return check_board


def make_player_done_handler(link: ArduinoUIControllerLink):
    def player_done() -> None:
        log("PLAYER_DONE", "received — simulating bot turn")

        def run():
            time.sleep(1.0)
            link.bot_thinking()
            log("->Arduino", "BOT_THINKING")

            time.sleep(2.0)
            link.bot_moving()
            log("->Arduino", "BOT_MOVING")

            time.sleep(1.0)
            link.player_turn_white()
            log("->Arduino", "PLAYER_TURN_WHITE")

        threading.Thread(target=run, daemon=True).start()

    return player_done


def make_set_difficulty_handler():
    labels = {0: "EASY", 1: "MEDIUM", 2: "HARD"}

    def set_difficulty(n: int) -> None:
        label = labels.get(n, f"unknown({n})")
        log("SET_DIFFICULTY", f"{n} ({label})")

    return set_difficulty


def main() -> None:
    parser = argparse.ArgumentParser(description="UI bridge simulation test")
    parser.add_argument("--port", default="/dev/cu.usbmodem1401", help="Arduino serial port")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    args = parser.parse_args()

    print(f"Connecting to Arduino on {args.port} @ {args.baud} baud...")

    link = ArduinoUIControllerLink(
        port=args.port,
        baud=args.baud,
        on_line=lambda line: log("Arduino->", line),
    )

    link.set_handlers(
        on_check_board=make_check_board_handler(link),
        on_player_done=make_player_done_handler(link),
        on_set_difficulty=make_set_difficulty_handler(),
    )

    link.start()
    print("Bridge running. Use the knob + button on the Arduino.")
    print("Ctrl-C to quit.\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        link.close()
        print("Done.")


if __name__ == "__main__":
    main()
