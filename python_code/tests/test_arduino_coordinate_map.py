from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.arduino.arduino_bridge import MoveFlags, build_move_commands
from charm.arduino.coordinate_map import BoardCalibration


def test_three_square_calibration_uses_37_5mm_grid() -> None:
    calibration = BoardCalibration.from_three_squares(
        a1=(100.0, 200.0),
        h1=(362.5, 200.0),
        a8=(100.0, 462.5),
    )

    assert calibration.square_center("a1") == (100.0, 200.0)
    assert calibration.square_center("b1") == (137.5, 200.0)
    assert calibration.square_center("a2") == (100.0, 237.5)
    assert calibration.square_center("h8") == (362.5, 462.5)


def test_three_square_calibration_supports_rotated_board() -> None:
    calibration = BoardCalibration.from_three_squares(
        a1=(100.0, 100.0),
        h1=(100.0, 362.5),
        a8=(-162.5, 100.0),
    )

    assert calibration.square_center("b1") == (100.0, 137.5)
    assert calibration.square_center("a2") == (62.5, 100.0)


def test_move_commands_do_not_require_serial() -> None:
    calibration = BoardCalibration.from_three_squares(
        a1=(0.0, 0.0),
        h1=(262.5, 0.0),
        a8=(0.0, 262.5),
        z_hover=40.0,
        z_down=8.0,
        home=(10.0, 20.0, 40.0),
    )

    commands = build_move_commands("e2e4", calibration, MoveFlags())

    assert commands[:6] == [
        "moveXYZ 150.000 37.500 40.000",
        "moveZ 8.000",
        "CG",
        "moveXYZ 150.000 112.500 40.000",
        "moveZ 8.000",
        "OG",
    ]
    assert commands[-1] == "moveXYZ 10.000 20.000 40.000"


def test_move_commands_use_piece_specific_pickup_height() -> None:
    calibration = BoardCalibration.from_three_squares(
        a1=(0.0, 0.0),
        h1=(262.5, 0.0),
        a8=(0.0, 262.5),
        z_hover=40.0,
        z_down=8.0,
        piece_heights={"pawn": 6.0, "queen": 12.0},
    )

    commands = build_move_commands("d1h5", calibration, MoveFlags(), piece_type="queen")

    assert commands[1] == "moveZ 12.000"
    assert commands[4] == "moveZ 12.000"
