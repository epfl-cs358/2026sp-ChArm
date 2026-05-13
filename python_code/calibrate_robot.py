from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.arduino.arduino_bridge import ArduinoBridge, print_responses
from charm.arduino.coordinate_map import (
    DEFAULT_CONFIG_PATH,
    BoardCalibration,
    PIECE_TYPES,
    load_calibration,
    save_calibration,
)


def parse_xy(value: str) -> tuple[float, float]:
    try:
        x_raw, y_raw = value.split(",", maxsplit=1)
        return (float(x_raw), float(y_raw))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected format x,y in millimeters") from exc


def parse_xyz(value: str) -> tuple[float, float, float]:
    try:
        x_raw, y_raw, z_raw = value.split(",", maxsplit=2)
        return (float(x_raw), float(y_raw), float(z_raw))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected format x,y,z in millimeters") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibrate and test ChArm robot square coordinates over PySerial."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Calibration JSON path.")
    parser.add_argument("--port", default=None, help="Serial port. Defaults to CHARM_ARDUINO_PORT or auto-detect.")
    parser.add_argument("--baud", type=int, default=9600, help="Arduino baud rate.")

    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="Print the current calibration and sample squares.")
    show.add_argument("--squares", nargs="*", default=["a1", "b1", "a2", "h8"])

    write = sub.add_parser("write", help="Write calibration from measured square centers.")
    write.add_argument("--a1", type=parse_xy, required=True, help="Center of a1 as x,y in mm.")
    write.add_argument("--h1", type=parse_xy, required=True, help="Center of h1 as x,y in mm.")
    write.add_argument("--a8", type=parse_xy, required=True, help="Center of a8 as x,y in mm.")
    write.add_argument("--z-hover", type=float, required=True, help="Safe travel Z in mm.")
    write.add_argument("--z-down", type=float, required=True, help="Pickup/drop Z in mm.")
    write.add_argument("--home", type=parse_xyz, required=True, help="Home position as x,y,z in mm.")
    write.add_argument("--capture-bin", type=parse_xyz, required=True, help="Captured-piece drop position as x,y,z in mm.")
    for piece in PIECE_TYPES:
        write.add_argument(
            f"--{piece}-z",
            type=float,
            default=None,
            help=f"Pickup/drop Z for a {piece}. Defaults to --z-down.",
        )

    move_square = sub.add_parser("move-square", help="Move above one square center.")
    move_square.add_argument("square", help="Chess square, e.g. e4.")
    move_square.add_argument("--down", action="store_true", help="Move to z_down instead of z_hover.")

    move = sub.add_parser("move", help="Execute a UCI move.")
    move.add_argument("uci", help="UCI move, e.g. e2e4.")
    move.add_argument("--capture", action="store_true")
    move.add_argument("--castling", action="store_true")
    move.add_argument("--promotion", action="store_true")
    move.add_argument("--piece-type", choices=PIECE_TYPES, default=None)

    goto = sub.add_parser("goto", help="Move directly to an XYZ coordinate.")
    goto.add_argument("xyz", type=parse_xyz, help="Target as x,y,z in mm.")

    sub.add_parser("arm-calibrate", help="Run Arduino homing/calibrate command.")
    sub.add_parser("pos", help="Print Arduino current position.")

    raw = sub.add_parser("raw", help="Send one raw Arduino command.")
    raw.add_argument("arduino_command", help="Command understood by arduino_code/src/main.cpp, e.g. cm, pos, w, OG.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)

    if args.command == "write":
        piece_heights = {
            piece: getattr(args, f"{piece}_z") if getattr(args, f"{piece}_z") is not None else args.z_down
            for piece in PIECE_TYPES
        }
        calibration = BoardCalibration.from_three_squares(
            args.a1,
            args.h1,
            args.a8,
            z_hover=args.z_hover,
            z_down=args.z_down,
            home=args.home,
            capture_bin=args.capture_bin,
            piece_heights=piece_heights,
        )
        saved_path = save_calibration(calibration, config_path)
        print(f"Saved calibration to {saved_path}")
        return

    calibration = load_calibration(config_path, require_exists=args.command in {"move-square", "move"})

    if args.command == "show":
        print(f"Calibration: {config_path}")
        print(calibration.to_dict())
        for square in args.squares:
            print(f"{square}: {calibration.square_center(square)}")
        return

    with ArduinoBridge(port=args.port, baud=args.baud, calibration=calibration) as bridge:
        if args.command == "move-square":
            z = calibration.z_down if args.down else calibration.z_hover
            print_responses(bridge.move_to_square(args.square, z=z))
        elif args.command == "move":
            bridge.execute_move(
                args.uci,
                is_capture=args.capture,
                is_castling=args.castling,
                is_promotion=args.promotion,
                piece_type=args.piece_type,
            )
        elif args.command == "arm-calibrate":
            print_responses(bridge.calibrate_arm())
        elif args.command == "pos":
            print_responses(bridge.position())
        elif args.command == "goto":
            print_responses(bridge.move_xyz(*args.xyz))
        elif args.command == "raw":
            print_responses(bridge.send_command(args.arduino_command))


if __name__ == "__main__":
    main()
