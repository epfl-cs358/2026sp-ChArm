from __future__ import annotations

import threading
import serial
import chess


def execute_move(uci_move: str, board: chess.Board, ser: serial.Serial, lock: threading.Lock):
    print(f"[ARM] execute_move called: {uci_move}", flush=True)
    move = chess.Move.from_uci(uci_move)
    from_square = chess.square_name(move.from_square)
    to_square = chess.square_name(move.to_square)

    # Get the piece being moved
    piece = board.piece_at(move.from_square)
    piece_name = chess.piece_name(piece.piece_type).lower()

    # Check for capture
    is_capture = board.is_capture(move)
    captured_piece = None
    if is_capture:
        captured_piece_obj = board.piece_at(move.to_square)
        captured_piece = chess.piece_name(captured_piece_obj.piece_type).lower()

    # Check for castling
    is_castling = board.is_castling(move)
    rook_from = None
    rook_to = None
    if is_castling:
        if move.to_square == chess.G1:  # White kingside
            rook_from = "h1"
            rook_to = "f1"
        elif move.to_square == chess.C1:  # White queenside
            rook_from = "a1"
            rook_to = "d1"
        elif move.to_square == chess.G8:  # Black kingside
            rook_from = "h8"
            rook_to = "f8"
        elif move.to_square == chess.C8:  # Black queenside
            rook_from = "a8"
            rook_to = "d8"

    if is_capture and captured_piece:
        # Pick up captured piece and put it in trash
        send_command(f"pick {captured_piece} {to_square}", ser, lock)
        send_command(f"put {captured_piece} trash", ser, lock)

    # Move the main piece
    send_command(f"pick {piece_name} {from_square}", ser, lock)
    send_command(f"put {piece_name} {to_square}", ser, lock)

    # If castling, also move the rook
    if is_castling and rook_from and rook_to:
        send_command(f"pick rook {rook_from}", ser, lock)
        send_command(f"put rook {rook_to}", ser, lock)

    send_command("home", ser, lock)


_TERMINATION_SUFFIXES = ("done", "failed")
_TERMINATION_PREFIXES = ("invalid", "usage", "bad ", "going home", "board not", "trash not")
_COMMAND_TIMEOUT_S = 60.0   # max seconds to wait for the Mega to finish a command


def send_command(command: str, ser: serial.Serial, lock: threading.Lock) -> str:
    import time
    with lock:
        ser.write(f"{command}\n".encode())
        ser.flush()
        response = ""
        deadline = time.monotonic() + _COMMAND_TIMEOUT_S
        while time.monotonic() < deadline:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                # readline timed out (serial port timeout) — keep waiting
                continue
            response = line
            lower = line.lower()
            if any(lower.endswith(s) for s in _TERMINATION_SUFFIXES) or \
               any(lower.startswith(p) for p in _TERMINATION_PREFIXES):
                break
        else:
            print(f"[ARM] WARNING: '{command}' timed out after {_COMMAND_TIMEOUT_S}s, last response: {response!r}", flush=True)
    print(f"[ARM] {command!r} -> {response!r}", flush=True)
    return response
