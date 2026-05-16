#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime
import sys
import os

from src.charm.vision.transferphoto import fetch_raw_image

PYTHON_CODE_ROOT = Path(__file__).resolve().parent
SRC_PATH = PYTHON_CODE_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))


def capture_game_session(game_name: str = "game_1", esp32_url: str | None = None) -> None:
    session_dir = PYTHON_CODE_ROOT / game_name
    session_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"Game Session: {game_name}")
    print(f"Output directory: {session_dir}")
    print("=" * 80)
    print()
    print("Press ENTER to capture photos. Type 'quit' or 'q' to exit.")
    print()

    photo_count = 0

    while True:
        user_input = input("> ").strip().lower()

        if user_input in ("quit", "q", "exit"):
            print()
            print(f"Session ended. {photo_count} photos captured.")
            print(f"Saved to: {session_dir}")
            break

        if user_input == "":
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                photo_count += 1
                output_path = session_dir / f"photo_{photo_count:03d}_{timestamp}.jpg"

                print(f"[{photo_count}] Capturing...", end=" ", flush=True)

                fetch_raw_image(url=esp32_url, output_path=str(output_path))

                print(f"✓ Saved: {output_path.name}")
                print()

            except Exception as e:
                print(f"❌ Error: {e}")
                print()
        else:
            print("Invalid input. Press ENTER to capture, or 'q' to quit.")
            print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Capture raw ESP32-CAM photos into a game session folder."
    )
    parser.add_argument(
        "--game",
        type=str,
        default="game_1",
        help="Game session name/folder (default: game_1)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="ESP32-CAM URL (default: env CHARM_ESP32_URL or http://172.21.73.228/capture)",
    )

    args = parser.parse_args()

    capture_game_session(game_name=args.game, esp32_url=args.url)
