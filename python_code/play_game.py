"""
play_game.py — full game entry point

Wires together:
  - ArduinoUIControllerLink  (TCP socket to ESP32 UI box: buttons + LCD)
  - arduino_bridge.execute_move  (USB serial to Arduino Mega: arm commands)
  - GameSession              (chess state + vision)
  - GameController           (coordinates everything)

Usage:
    python play_game.py --esp32-host 192.168.1.42
    python play_game.py --esp32-host 192.168.1.42 --player-color black
    python play_game.py --esp32-host 192.168.1.42 --arm-port /dev/cu.usbserial-120

Ctrl-C to stop.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

import cv2
import serial

from charm.arduino.uiController_bridge import ArduinoUIControllerLink
from charm.game.game_controller import GameController, GameControllerConfig
from charm.game.game_session import GameSession
from charm.vision.calibration_config import (
    DEFAULT_BOARD_CALIBRATION_JSON,
    DEFAULT_INNER_WARP_CALIBRATION_JSON,
)
from charm.vision.four_point_calibration import (
    load_four_point_calibration,
    load_inner_warp_calibration,
    refine_board_with_inner_corners,
    warp_from_calibration,
)
from charm.vision.transferphoto import fetch_raw_image


CALIBRATED_IMAGE_PATH = ROOT / "latest_calibrated.jpg"
WARP_SIZE = 800
DEFAULT_MEGA_PORTS = (
    "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0",
    "/dev/ttyUSB2",
    "/dev/ttyUSB1",
    "/dev/ttyUSB0",
    "/dev/cu.usbserial-120",
)


def make_board_image_provider(
    board_calibration_path: Path,
    inner_calibration_path: Path,
) -> callable:
    """Returns a callable that captures a photo and returns a calibrated image path."""
    board_cal = load_four_point_calibration(board_calibration_path)
    inner_cal = load_inner_warp_calibration(inner_calibration_path)

    def capture_and_calibrate() -> str:
        raw_path = fetch_raw_image()
        raw_image = cv2.imread(raw_path)
        if raw_image is None:
            raise RuntimeError(f"Could not read raw image: {raw_path}")

        first_warp = warp_from_calibration(raw_image, board_cal, output_size=WARP_SIZE)
        refined = refine_board_with_inner_corners(first_warp, inner_cal, output_size=WARP_SIZE)
        cv2.imwrite(str(CALIBRATED_IMAGE_PATH), refined)
        return str(CALIBRATED_IMAGE_PATH)

    return capture_and_calibrate


def find_default_arm_port() -> str:
    for port in DEFAULT_MEGA_PORTS:
        if Path(port).exists():
            return port
    return DEFAULT_MEGA_PORTS[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChArm chess game")
    parser.add_argument(
        "--esp32-host",
        default="172.21.71.52",
        help="IP address of the ESP32 UI box.",
    )
    parser.add_argument(
        "--esp32-port",
        type=int,
        default=8765,
        help="TCP port on the ESP32 UI box.",
    )
    parser.add_argument(
        "--arm-port",
        default=None,
        help="USB serial port for the Arduino Mega (arm commands).",
    )
    parser.add_argument(
        "--player-color",
        choices=["white", "black"],
        default="white",
        help="Fallback color if the ESP32 color screen is skipped (default: white). "
             "The on-device color selection overrides this at game start.",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        choices=[0, 1, 2],
        default=1,
        help="Starting difficulty: 0=Easy, 1=Medium, 2=Hard.",
    )
    parser.add_argument(
        "--flip-180",
        action="store_true",
        help="Set if the camera sees white on top / black on bottom "
             "(board is 180° rotated from the chess.Board standard orientation).",
    )
    parser.add_argument(
        "--board-calibration",
        default=str(DEFAULT_BOARD_CALIBRATION_JSON),
        help="Path to board calibration JSON.",
    )
    parser.add_argument(
        "--inner-calibration",
        default=str(DEFAULT_INNER_WARP_CALIBRATION_JSON),
        help="Path to inner warp calibration JSON.",
    )
    parser.add_argument(
        "--engine-path",
        default="stockfish",
        help="Path to the Stockfish binary.",
    )
    parser.add_argument(
        "--think-time",
        type=float,
        default=0.5,
        help="Seconds Stockfish spends thinking per move.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    board_cal_path = Path(args.board_calibration)
    inner_cal_path = Path(args.inner_calibration)

    if not board_cal_path.exists():
        print(f"ERROR: board calibration not found: {board_cal_path}")
        print("Run calibrate_board_corners.py first.")
        sys.exit(1)

    if not inner_cal_path.exists():
        print(f"ERROR: inner warp calibration not found: {inner_cal_path}")
        print("Run calibrate_inner_warp_corners.py first.")
        sys.exit(1)

    arm_port = args.arm_port or find_default_arm_port()
    print(f"Connecting to Arduino Mega on {arm_port} @ 115200 baud...")
    arm_ser = serial.Serial(arm_port, 115200, timeout=2)
    arm_lock = threading.Lock()

    print(f"Connecting to ESP32 UI box at {args.esp32_host}:{args.esp32_port}...")
    ui_link = ArduinoUIControllerLink(
        host=args.esp32_host,
        port=args.esp32_port,
        on_line=lambda line: print(f"[ESP32] {line}", flush=True),
    )

    session = GameSession()

    config = GameControllerConfig(
        board_image_provider=make_board_image_provider(board_cal_path, inner_cal_path),
        arm_ser=arm_ser,
        arm_lock=arm_lock,
        player_color=args.player_color,
        flip_180=args.flip_180,
        engine_path=args.engine_path,
        think_time=args.think_time,
    )

    controller = GameController(ui_link=ui_link, session=session, config=config)

    # Apply starting difficulty from CLI args.
    controller.set_difficulty(args.difficulty)

    controller.start()

    difficulty_label = {0: "Easy", 1: "Medium", 2: "Hard"}
    print(f"Game ready. Player: {args.player_color}, difficulty: {difficulty_label[args.difficulty]}")
    print("Use the buttons on the ESP32 box to start a game.")
    print("Ctrl-C to quit.\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        controller.stop()
        arm_ser.close()
        print("Done.")


if __name__ == "__main__":
    main()
