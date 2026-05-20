from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

import chess


_serial = None
_serial_key: Optional[tuple[str, int]] = None
_serial_lock = threading.RLock()


def default_calibration() -> dict:
    return {
        "a1": {"x": 0.0, "y": 0.0},
        "file_vector": {"x": 37.5, "y": 0.0},
        "rank_vector": {"x": 0.0, "y": 37.5},
        "z_hover": 60.0,
        "z_down": 5.0,
        "home": {"x": 0.0, "y": 0.0, "z": 60.0},
        "capture_bin": {"x": 0.0, "y": 0.0, "z": 5.0},
        "pick_z": {
            "pawn": 3.0,
            "knight": 0.0,
            "bishop": 11.0,
            "rook": 11.0,
            "queen": 17.0,
            "king": 19.0,
        },
        "place_z": {
            "pawn": 30.0,
            "knight": 30.0,
            "bishop": 32.0,
            "rook": 35.0,
            "queen": 38.0,
            "king": 40.0,
        },
    }


def load_calibration(path: Path) -> dict:
    if not path.exists():
        return default_calibration()
    try:
        data = json.loads(path.read_text())
    except Exception:
        return default_calibration()
    defaults = default_calibration()
    return {
        **defaults,
        **data,
        "pick_z": {**defaults["pick_z"], **data.get("pick_z", data.get("piece_heights", {}))},
        "place_z": {**defaults["place_z"], **data.get("place_z", {})},
    }


def save_calibration(path: Path, payload: dict) -> None:
    a1 = {"x": float(payload["a1"]["x"]), "y": float(payload["a1"]["y"])}
    h1 = {"x": float(payload["h1"]["x"]), "y": float(payload["h1"]["y"])}
    h8 = {"x": float(payload["h8"]["x"]), "y": float(payload["h8"]["y"])}
    calibration = {
        "a1": a1,
        "file_vector": {
            "x": (h1["x"] - a1["x"]) / 7.0,
            "y": (h1["y"] - a1["y"]) / 7.0,
        },
        "rank_vector": {
            "x": (h8["x"] - h1["x"]) / 7.0,
            "y": (h8["y"] - h1["y"]) / 7.0,
        },
        "z_hover": float(payload["z_hover"]),
        "z_down": float(payload["z_down"]),
        "home": payload["home"],
        "capture_bin": payload["capture_bin"],
        "pick_z": payload["pick_z"],
        "place_z": payload["place_z"],
    }
    path.write_text(json.dumps(calibration, indent=2))


def square_center(calibration: dict, square: str) -> list[float]:
    file_idx = ord(square[0].lower()) - ord("a")
    rank_idx = int(square[1]) - 1
    a1 = calibration["a1"]
    fv = calibration["file_vector"]
    rv = calibration["rank_vector"]
    return [
        a1["x"] + file_idx * fv["x"] + rank_idx * rv["x"],
        a1["y"] + file_idx * fv["y"] + rank_idx * rv["y"],
    ]


def list_ports() -> list[dict]:
    try:
        import serial.tools.list_ports

        return [
            {"device": p.device, "description": p.description, "manufacturer": p.manufacturer}
            for p in serial.tools.list_ports.comports()
        ]
    except Exception:
        return []


def find_port() -> Optional[str]:
    by_id_dir = Path("/dev/serial/by-id")
    if by_id_dir.exists():
        for path in sorted(by_id_dir.iterdir()):
            if path.is_symlink():
                return str(path.resolve())

    try:
        import serial.tools.list_ports

        ports = list(serial.tools.list_ports.comports())
    except Exception:
        return None

    preferred = ("arduino", "usb serial", "usb-serial", "wch", "ch340", "teensy")
    for port in ports:
        haystack = " ".join(
            str(value or "") for value in (port.device, port.description, port.manufacturer)
        ).lower()
        if any(marker in haystack for marker in preferred):
            return port.device
    return None


def connected_port() -> Optional[str]:
    with _serial_lock:
        if _serial is not None and getattr(_serial, "is_open", False) and _serial_key is not None:
            return _serial_key[0]
    return None


def close() -> None:
    global _serial, _serial_key
    with _serial_lock:
        if _serial is not None and getattr(_serial, "is_open", False):
            _serial.close()
        _serial = None
        _serial_key = None


def _get_serial(port: Optional[str], baud: int):
    global _serial, _serial_key
    import serial

    resolved_port = port or find_port() or os.getenv("CHARM_SERIAL_PORT", "/dev/cu.usbmodem1401")
    key = (resolved_port, baud)
    with _serial_lock:
        if _serial is None or not getattr(_serial, "is_open", False) or _serial_key != key:
            close()
            _serial = serial.Serial(resolved_port, baud, timeout=2)
            _serial_key = key
            # Opening the Arduino USB serial port resets the Mega. Let setup()
            # finish and discard the boot/menu output before sending commands.
            time.sleep(2.5)
            try:
                _serial.reset_input_buffer()
            except Exception:
                pass
        return _serial


def _read_lines(ser, idle_timeout: float = 0.25, max_wait: float = 8.0, stop_on_marker: Optional[str] = None) -> list[str]:
    deadline = time.monotonic() + max_wait
    idle_deadline = time.monotonic() + idle_timeout
    lines: list[str] = []
    while time.monotonic() < deadline:
        raw = ser.readline()
        if raw:
            line = raw.decode(errors="ignore").strip()
            if line:
                lines.append(line)
                if stop_on_marker and stop_on_marker in line:
                    break
            idle_deadline = time.monotonic() + idle_timeout
            continue
        # When a stop marker is set, the caller is committed to waiting for it
        # — don't let idle-silence cut us off mid-motion. A blocking Arduino
        # command (`home`, `pick`, `put`, ...) prints its header, then runs
        # the stepper silently for seconds, then prints a trailing line. Only
        # `max_wait` should bound the wait in that case.
        if stop_on_marker is None and time.monotonic() >= idle_deadline:
            break
    return lines


def _looks_like_garbage(line: str) -> bool:
    if not line:
        return False
    non_printable = sum(1 for c in line if ord(c) < 32 and c not in ('\t', '\n', '\r'))
    return non_printable > len(line) * 0.3


def send_commands(commands: list[str], port: Optional[str], baud: int, max_wait: float = 8.0, idle_timeout: float = 0.25, stop_on: Optional[str] = None) -> list[str]:
    with _serial_lock:
        ser = _get_serial(port, baud)
        responses: list[str] = []
        for command in commands:
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            ser.write(f"{command}\n".encode())
            responses.append(f"> {command}")
            lines = _read_lines(ser, idle_timeout=idle_timeout, max_wait=max_wait, stop_on_marker=stop_on)
            # If only garbage came back (Arduino was in bootloader), reopen and retry once
            if lines and all(_looks_like_garbage(l) for l in lines):
                global _serial, _serial_key
                close()
                import serial as _serial_mod
                resolved = port or find_port() or os.getenv("CHARM_SERIAL_PORT", "/dev/cu.usbmodem1401")
                _serial = _serial_mod.Serial(resolved, baud, timeout=2)
                _serial_key = (resolved, baud)
                ser = _serial
                time.sleep(3.0)
                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass
                ser.write(f"{command}\n".encode())
                responses[-1] = f"> {command} [retried after garbage]"
                lines = _read_lines(ser, idle_timeout=idle_timeout, max_wait=max_wait, stop_on_marker=stop_on)
            responses.extend(lines)
        return responses


def parse_position(responses: list[str]) -> Optional[dict]:
    for line in reversed(responses):
        match = re.search(r"Position:\s*\(([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)", line)
        if match:
            return {"x": float(match.group(1)), "y": float(match.group(2)), "z": float(match.group(3))}
        match = re.search(r"\bpos=\(([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)", line)
        if match:
            return {"x": float(match.group(1)), "y": float(match.group(2)), "z": float(match.group(3))}
    return None


def parse_board_info(responses: list[str], calibration_path: Path) -> Optional[dict]:
    points: dict[str, dict[str, float]] = {}
    current_z: Optional[float] = None
    for line in responses:
        point_match = re.match(r"^(A1|H1|H8|Trash):\s*\(([-\d.]+),\s*([-\d.]+)\)", line)
        if point_match:
            key = point_match.group(1).lower()
            points[key] = {"x": float(point_match.group(2)), "y": float(point_match.group(3))}
            continue
        z_match = re.match(r"^current Z=([-\d.]+)\s*mm", line)
        if z_match:
            current_z = float(z_match.group(1))

    if not any(key in points for key in ("a1", "h1", "h8", "trash")):
        return None

    complete = all(key in points for key in ("a1", "h1", "h8"))
    calibration = None
    if complete:
        a1 = points["a1"]
        h1 = points["h1"]
        h8 = points["h8"]
        existing = load_calibration(calibration_path)
        calibration = {
            **existing,
            "a1": a1,
            "file_vector": {
                "x": (h1["x"] - a1["x"]) / 7.0,
                "y": (h1["y"] - a1["y"]) / 7.0,
            },
            "rank_vector": {
                "x": (h8["x"] - h1["x"]) / 7.0,
                "y": (h8["y"] - h1["y"]) / 7.0,
            },
        }
        if "trash" in points:
            calibration["capture_bin"] = {
                "x": points["trash"]["x"],
                "y": points["trash"]["y"],
                "z": existing["capture_bin"]["z"],
            }

    return {
        "points": points,
        "current_z": current_z,
        "complete": complete,
        "calibration": calibration,
    }


def move_commands(
    uci: str,
    piece_type: Optional[str],
    capture: bool,
    castling: bool,
    captured_piece_type: Optional[str] = None,
) -> list[str]:
    move = chess.Move.from_uci(uci)
    from_square = chess.square_name(move.from_square)
    to_square = chess.square_name(move.to_square)
    piece = piece_type or "pawn"
    commands: list[str] = []
    if capture:
        captured_piece = captured_piece_type or piece
        commands.extend([f"pick {captured_piece} {to_square}", f"put {captured_piece} trash"])
    commands.extend([f"pick {piece} {from_square}", f"put {piece} {to_square}"])
    if castling:
        if to_square == "g1":
            commands.extend(["pick rook h1", "put rook f1"])
        elif to_square == "c1":
            commands.extend(["pick rook a1", "put rook d1"])
        elif to_square == "g8":
            commands.extend(["pick rook h8", "put rook f8"])
        elif to_square == "c8":
            commands.extend(["pick rook a8", "put rook d8"])
    commands.append("home")
    return commands


def commands_for_request(payload: dict) -> list[str]:
    command = payload.get("command")
    if command == "pos":
        return ["pos"]
    if command == "arm-calibrate":
        return ["calibrate"]
    if command == "board-info":
        return ["boardInfo"]
    if command == "board-calibrate":
        return ["cal"]
    if command == "board-cal-key":
        raw = payload.get("raw")
        if raw is None:
            raise ValueError("raw calibration key is required")
        return [raw.lower()]
    if command == "board-cal-clear":
        return ["calClear"]
    if command == "capture-corner":
        corner = payload.get("corner")
        if corner is None:
            raise ValueError("corner is required")
        corner_commands = {"h1": "setH1", "a1": "setA1", "h8": "setH8"}
        return [corner_commands[corner], "pos"]
    if command == "goto":
        x = payload.get("x")
        y = payload.get("y")
        z = payload.get("z")
        if x is None or y is None or z is None:
            raise ValueError("x, y, z are required")
        return [f"moveXYZ {x} {y} {z}", "pos"]
    if command == "jog":
        raw = payload.get("raw")
        if raw is None:
            raise ValueError("raw jog key is required")
        return [raw.lower(), "pos"]
    if command == "move-square":
        square = payload.get("square")
        if square is None:
            raise ValueError("square is required")
        return [f"goto {square.lower()}", "pos"]
    if command == "move":
        uci = payload.get("uci")
        if uci is None:
            raise ValueError("uci is required")
        return move_commands(
            uci,
            payload.get("piece_type"),
            bool(payload.get("capture")),
            bool(payload.get("castling")),
            payload.get("captured_piece_type"),
        )
    if command == "raw":
        raw = payload.get("raw")
        if raw is None:
            raise ValueError("raw is required")
        return [raw]
    if command == "photo":
        return ["photo"]
    if command == "inject-cal":
        h1 = payload["h1"]
        a1 = payload["a1"]
        h8 = payload["h8"]
        trash = payload["trash"]
        return [
            f"injectCal {h1['x']} {h1['y']} {a1['x']} {a1['y']} {h8['x']} {h8['y']} {trash['x']} {trash['y']}"
        ]
    raise ValueError(f"Unknown robot command: {command}")


def parse_esp32_url(responses: list[str]) -> Optional[str]:
    for line in responses:
        if line.startswith("PHOTO_URL "):
            return line.split(" ", 1)[1].strip()
    return None


def inject_board_cal(
    h1: tuple[float, float],
    a1: tuple[float, float],
    h8: tuple[float, float],
    trash: tuple[float, float],
    port: Optional[str] = None,
    baud: int = 9600,
) -> list[str]:
    cmd = f"injectCal {h1[0]} {h1[1]} {a1[0]} {a1[1]} {h8[0]} {h8[1]} {trash[0]} {trash[1]}"
    return send_commands([cmd], port, baud)


def response(responses: list[str], calibration_path: Path) -> dict:
    return {
        "status": "ok",
        "responses": responses,
        "position": parse_position(responses),
        "board_info": parse_board_info(responses, calibration_path),
        "timestamp": time.time(),
    }
