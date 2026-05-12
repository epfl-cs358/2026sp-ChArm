from __future__ import annotations

import serial
import chess

manual_serial = serial.Serial('/dev/cu.usbmodem1401', 9600, timeout=2)

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
        send_command(f"pick {captured_piece} {to_square}")
        send_command(f"put {captured_piece} trash")
    
    # Move the main piece
    send_command(f"pick {piece_name} {from_square}")
    send_command(f"put {piece_name} {to_square}")
    
    # If castling, also move the rook
    if is_castling and rook_from and rook_to:
        send_command(f"pick rook {rook_from}")
        send_command(f"put rook {rook_to}")


def send_command(command):
    manual_serial.write(f"{command}\n".encode())
    response = manual_serial.readline().decode().strip()
    return response