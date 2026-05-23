from __future__ import annotations

import threading
import serial
import chess


def _mirror_sq(sq: str) -> str:
    """Mirror a square's RANK only, preserving the file: a1↔a8, e2↔e7.

    Used for arm coordinates when the player is Black. The board is never
    physically rotated: the player's pieces always sit on the near side
    (calibration a1/h1, ranks 1-2) and the robot's on the far side (a8/h8,
    ranks 7-8) with the SAME files. So the engine's White squares (internal
    ranks 1-2) map to the physical far side at the same file — a rank flip,
    not a full 180° rotation (which would also swap a-file ↔ h-file)."""
    return sq[0] + str(9 - int(sq[1]))


def execute_move(uci_move: str, board: chess.Board, ser: serial.Serial, lock: threading.Lock, flip_180: bool = False):
    print(f"[ARM] execute_move called: {uci_move} flip={flip_180}", flush=True)
    move = chess.Move.from_uci(uci_move)

    def sq(square_name: str) -> str:
        return _mirror_sq(square_name) if flip_180 else square_name

    from_square = sq(chess.square_name(move.from_square))
    to_square   = sq(chess.square_name(move.to_square))

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
            rook_from = sq("h1")
            rook_to   = sq("f1")
        elif move.to_square == chess.C1:  # White queenside
            rook_from = sq("a1")
            rook_to   = sq("d1")
        elif move.to_square == chess.G8:  # Black kingside
            rook_from = sq("h8")
            rook_to   = sq("f8")
        elif move.to_square == chess.C8:  # Black queenside
            rook_from = sq("a8")
            rook_to   = sq("d8")

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
_TERMINATION_PREFIXES = ("invalid", "usage", "bad ", "board not", "trash not")
_COMMAND_TIMEOUT_S = 120.0  # max seconds to wait for the Mega to finish a command


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
