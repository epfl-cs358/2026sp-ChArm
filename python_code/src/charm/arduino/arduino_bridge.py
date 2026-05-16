from __future__ import annotations

import os

import serial
import chess

manual_serial = None


def _get_serial():
    global manual_serial
    if manual_serial is None or not manual_serial.is_open:
        port = os.getenv("CHARM_SERIAL_PORT", "/dev/ttyUSB0")
        baud = int(os.getenv("CHARM_SERIAL_BAUD", "9600"))
        manual_serial = serial.Serial(port, baud, timeout=2)
    return manual_serial

def execute_move(uci_move: str, board: chess.Board):
    move = chess.Move.from_uci(uci_move)
    from_square = chess.square_name(move.from_square)
    to_square = chess.square_name(move.to_square)
    
    # Get the piece being moved
    piece = board.piece_at(move.from_square)
    piece_name = chess.piece_name(piece.piece_type).lower()
    
    # Check for capture
    is_capture = board.is_capture(move)
    captured_piece = None
    captured_square = None
    if is_capture:
        if board.is_en_passant(move):
            # Captured pawn is on the same file as to_square but on from_square's rank
            ep_sq = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
            captured_piece_obj = board.piece_at(ep_sq)
            captured_square = chess.square_name(ep_sq)
        else:
            captured_piece_obj = board.piece_at(move.to_square)
            captured_square = to_square
        if captured_piece_obj is not None:
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

    if is_capture and captured_piece and captured_square:
        # Pick up captured piece from its actual square and put it in trash
        send_command(f"pick {captured_piece} {captured_square}")
        send_command(f"put {captured_piece} trash")

    # For promotion the robot places the promoted piece, not the pawn
    placed_piece = chess.piece_name(move.promotion).lower() if move.promotion else piece_name

    # Move the main piece
    send_command(f"pick {piece_name} {from_square}")
    send_command(f"put {placed_piece} {to_square}")
    
    # If castling, also move the rook
    if is_castling and rook_from and rook_to:
        send_command(f"pick rook {rook_from}")
        send_command(f"put rook {rook_to}")

    send_command("home")


def send_command(command):
    ser = _get_serial()
    ser.write(f"{command}\n".encode())
    response = ser.readline().decode().strip()
    return response
