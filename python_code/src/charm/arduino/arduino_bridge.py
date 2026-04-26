from __future__ import annotations

import serial
arduino = serial.Serial('/dev/cu.usbmodem1401', 9600, timeout=2)

from charm.arduino.coordinate_map import get_square_position, TRASH, Z_HOVER, Z_DOWN, H_X, H_Y, H_Z

def execute_move(uci_move: str):
    from_square = uci_move[:2]
    to_square   = uci_move[2:4]

    (x_f, y_f) = get_square_position(from_square)
    (x_t, y_t) = get_square_position(to_square)

    send_command(f"moveXYZ {x_f} {y_f} {Z_HOVER}")
    send_command(f"moveZ {Z_DOWN}")
    send_command("CG")
    send_command(f"moveXYZ {x_t} {y_t} {Z_HOVER}")
    send_command(f"moveZ {Z_DOWN}")
    send_command("OG")
    send_command(f"moveXYZ {H_X} {H_Y} {H_Z}")

    """
    I still need to do the castling move, the capture move and the promotion move,
    but for that I need to be clear first how the moves are send to me to differentaite them 
    from the ordinary moves.
    """


def send_command(command):
    arduino.write(f"{command}\n".encode())
    response = arduino.readline().decode().strip()
    return response