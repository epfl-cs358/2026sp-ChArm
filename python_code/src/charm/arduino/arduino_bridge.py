from __future__ import annotations

from dataclasses import dataclass
import os
import re
import time
from typing import Iterable

from charm.arduino.coordinate_map import BoardCalibration, load_calibration, normalize_piece_type


DEFAULT_BAUD = 9600
PORT_ENV = "CHARM_ARDUINO_PORT"


def find_arduino_port() -> str:
    import serial.tools.list_ports

    env_port = os.environ.get(PORT_ENV)
    if env_port:
        return env_port

    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        description = f"{port.device} {port.description} {port.manufacturer or ''}".lower()
        if any(token in description for token in ("arduino", "usbmodem", "usbserial", "ch340", "wchusbserial")):
            return port.device

    available = ", ".join(f"{p.device} ({p.description})" for p in ports) or "none"
    raise RuntimeError(
        f"No Arduino serial port found. Set {PORT_ENV} manually. Available ports: {available}"
    )


@dataclass(frozen=True)
class MoveFlags:
    is_capture: bool = False
    is_castling: bool = False
    is_promotion: bool = False


class ArduinoBridge:
    def __init__(
        self,
        port: str | None = None,
        baud: int = DEFAULT_BAUD,
        timeout: float = 2.0,
        calibration: BoardCalibration | None = None,
        reset_delay: float = 2.0,
    ) -> None:
        import serial

        self.port = port or find_arduino_port()
        self.baud = baud
        self.timeout = timeout
        self.calibration = calibration or load_calibration(require_exists=True)
        self.serial = serial.Serial(self.port, self.baud, timeout=self.timeout)
        time.sleep(reset_delay)
        self.serial.reset_input_buffer()

    def close(self) -> None:
        self.serial.close()

    def __enter__(self) -> "ArduinoBridge":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send_command(self, command: str, read_timeout: float | None = None) -> list[str]:
        previous_timeout = self.serial.timeout
        if read_timeout is not None:
            self.serial.timeout = read_timeout
        try:
            self.serial.write(f"{command}\n".encode())
            return self._read_response()
        finally:
            self.serial.timeout = previous_timeout

    def jog(self, key: str) -> list[str]:
        if key not in {"w", "a", "s", "d", "u", "j", "c", "v", "q"}:
            raise ValueError(f"Invalid jog key: {key!r}")
        return self.send_command(key, read_timeout=0.18)

    def calibrate_arm(self) -> list[str]:
        return self.send_command("calibrate")

    def board_info(self) -> list[str]:
        return self.send_command("boardInfo", read_timeout=0.4)

    def start_board_calibration(self) -> list[str]:
        return self.send_command("cal", read_timeout=0.5)

    def board_calibration_key(self, key: str) -> list[str]:
        if key not in {"w", "a", "s", "d", "u", "j", "v", "n", "p", "q"}:
            raise ValueError(f"Invalid calibration key: {key!r}")
        return self.send_command(key, read_timeout=0.5)

    def clear_board_calibration(self) -> list[str]:
        return self.send_command("calClear", read_timeout=0.4)

    def capture_board_corner(self, square: str) -> list[str]:
        normalized = square.lower().strip()
        if normalized not in ("a1", "h1", "h8"):
            raise ValueError(f"Invalid calibration corner: {square!r}")
        # Allan firmware stores corners via the interactive `cal` wizard (EEPROM).
        # There is no serial command to set a corner programmatically, so we
        # just read the current arm position. The caller should jog the arm to
        # the corner first, then call this to record the XY.
        return self.position()

    def position(self) -> list[str]:
        return self.send_command("pos", read_timeout=0.08)

    def position_xyz(self) -> dict[str, float] | None:
        return parse_position_response(self.position())

    def open_gripper(self) -> list[str]:
        return self.send_command("OG")

    def close_gripper(self) -> list[str]:
        return self.send_command("CG")

    def move_xyz(self, x: float, y: float, z: float) -> list[str]:
        return self.send_command(f"moveXYZ {x:.3f} {y:.3f} {z:.3f}")

    def move_z(self, z: float) -> list[str]:
        return self.send_command(f"moveZ {z:.3f}")

    def move_to_square(self, square: str, z: float | None = None) -> list[str]:
        responses = self.send_command(f"goto {square.lower().strip()}", read_timeout=0.4)
        if z is not None:
            responses.extend(self.move_z(z))
        return responses

    def execute_move(
        self,
        uci_move: str,
        is_capture: bool = False,
        is_castling: bool = False,
        is_promotion: bool = False,
        piece_type: str | None = None,
    ) -> None:
        flags = MoveFlags(is_capture, is_castling, is_promotion)
        for command in build_move_commands(uci_move, self.calibration, flags, piece_type=piece_type):
            self.send_command(command)

    def _read_response(self) -> list[str]:
        lines: list[str] = []
        while True:
            raw = self.serial.readline()
            if not raw:
                break
            line = raw.decode(errors="replace").strip()
            if line:
                lines.append(line)
                if _is_complete_response(line):
                    break
        return lines


def _move_piece_commands(
    from_square: str,
    to_square: str,
    calibration: BoardCalibration,
    piece_type: str | None = None,
) -> list[str]:
    z_down = calibration.z_for_piece(piece_type)
    return [
        f"moveZ {calibration.z_hover:.3f}",
        f"goto {from_square}",
        f"moveZ {z_down:.3f}",
        "CG",
        f"moveZ {calibration.z_hover:.3f}",
        f"goto {to_square}",
        f"moveZ {z_down:.3f}",
        "OG",
    ]


def _home_command(calibration: BoardCalibration) -> str:
    return f"moveXYZ {calibration.home.x:.3f} {calibration.home.y:.3f} {calibration.home.z:.3f}"


def _capture_commands(to_square: str, calibration: BoardCalibration, piece_type: str | None = None) -> list[str]:
    z_down = calibration.z_for_piece(piece_type)
    return [
        f"moveZ {calibration.z_hover:.3f}",
        f"goto {to_square}",
        f"moveZ {z_down:.3f}",
        "CG",
        f"moveXYZ {calibration.capture_bin.x:.3f} {calibration.capture_bin.y:.3f} {calibration.z_hover:.3f}",
        f"moveZ {calibration.capture_bin.z:.3f}",
        "OG",
    ]


def _castling_rook_move(from_square: str, to_square: str) -> tuple[str, str]:
    if from_square == "e1" and to_square == "g1":
        return ("h1", "f1")
    if from_square == "e1" and to_square == "c1":
        return ("a1", "d1")
    if from_square == "e8" and to_square == "g8":
        return ("h8", "f8")
    if from_square == "e8" and to_square == "c8":
        return ("a8", "d8")
    raise ValueError(f"Invalid castling move: {from_square}{to_square}")


def build_move_commands(
    uci_move: str,
    calibration: BoardCalibration | None = None,
    flags: MoveFlags | None = None,
    piece_type: str | None = None,
) -> list[str]:
    if len(uci_move) < 4:
        raise ValueError(f"Invalid UCI move: {uci_move!r}")

    calibration = calibration or load_calibration()
    flags = flags or MoveFlags()
    piece_type = normalize_piece_type(piece_type) if piece_type else None
    from_square = uci_move[:2]
    to_square = uci_move[2:4]

    commands: list[str] = []
    if flags.is_capture:
        commands.extend(_capture_commands(to_square, calibration, piece_type))

    commands.extend(_move_piece_commands(from_square, to_square, calibration, piece_type))

    if flags.is_castling:
        rook_from, rook_to = _castling_rook_move(from_square, to_square)
        commands.extend(_move_piece_commands(rook_from, rook_to, calibration, "rook"))

    if flags.is_promotion:
        # Physical promotion piece handling is hardware/table specific. The move
        # is still executed as a normal pawn move so the board state progresses.
        pass

    commands.append(_home_command(calibration))
    return commands


_default_bridge: ArduinoBridge | None = None


def get_default_bridge() -> ArduinoBridge:
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = ArduinoBridge()
    return _default_bridge


def close_default_bridge() -> None:
    global _default_bridge
    if _default_bridge is not None:
        _default_bridge.close()
        _default_bridge = None


def send_command(command: str) -> list[str]:
    return get_default_bridge().send_command(command)


def parse_position_response(responses: Iterable[str]) -> dict[str, float] | None:
    pattern = re.compile(r"Position:\s*\(([-+\d.]+),\s*([-+\d.]+),\s*([-+\d.]+)\)")
    for line in responses:
        match = pattern.search(line)
        if match:
            return {
                "x": float(match.group(1)),
                "y": float(match.group(2)),
                "z": float(match.group(3)),
            }
    return None


def _is_complete_response(line: str) -> bool:
    return (
        line.startswith("Position:")
        or line.startswith("Controller mode")
        or line.startswith("Gripper:")
        or line.startswith("EEPROM calibration cleared.")
        or line.startswith("[cal] All 3 corners set.")
        or line.startswith("[cal] Incomplete")
        or line.startswith("[cal] Cancelled.")
        or line.startswith("[cal] already")
        or line.startswith("[cal ")
        or line == "===================================="
        or "CAPTURED" in line
        or line.startswith("current Z=")
        or line.startswith("  arrived at")
        or line.startswith("  FAILED:")
        or line.startswith("Board not fully calibrated")
        or line == "Calibration done"
    )


def execute_move(
    uci_move: str,
    is_capture: bool,
    is_castling: bool,
    is_promotion: bool,
    piece_type: str | None = None,
) -> None:
    get_default_bridge().execute_move(
        uci_move,
        is_capture=is_capture,
        is_castling=is_castling,
        is_promotion=is_promotion,
        piece_type=piece_type,
    )


def print_responses(responses: Iterable[str]) -> None:
    for line in responses:
        print(line)
