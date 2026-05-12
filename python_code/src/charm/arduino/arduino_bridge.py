from __future__ import annotations

import serial
manual_serial = serial.Serial('/dev/cu.usbmodem1401', 9600, timeout=2)

from charm.arduino.coordinate_map import get_square_position, T_X, T_Y, T_Z, Z_HOVER, Z_DOWN, H_X, H_Y, H_Z

def execute_move(uci_move: str, is_capture: bool, is_castling: bool, is_promotion: bool):
    from_square = uci_move[:2]
    to_square   = uci_move[2:4]

    (x_f, y_f) = get_square_position(from_square)
    (x_t, y_t) = get_square_position(to_square)

    if is_capture:
        send_command(f"moveXYZ {x_t} {y_t} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("CG")
        send_command(f"moveXYZ {T_X} {T_Y} {Z_HOVER}")
        send_command(f"moveZ {T_Z}")
        send_command("OG")
        send_command(f"moveXYZ {x_f} {y_f} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("CG")
        send_command(f"moveXYZ {x_t} {y_t} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("OG")
        send_command(f"moveXYZ {H_X} {H_Y} {H_Z}")
        
    elif is_castling:
        from_rook = ""
        to_rook = ""

        if from_square == "e1":
            if to_square == "g1":
                from_rook = "h1"
                to_rook = "f1"
            else:
                from_rook = "a1"
                to_rook = "d1"
        else:
            if to_square == "g8":
                from_rook = "h8"
                to_rook = "f8"
            else:
                from_rook = "a8"
                to_rook = "d8"
        
        (x_fR, y_fR) = get_square_position(from_rook)
        (x_tR, y_tR) = get_square_position(to_rook)

        send_command(f"moveXYZ {x_f} {y_f} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("CG")
        send_command(f"moveXYZ {x_t} {y_t} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("OG")
        
        send_command(f"moveXYZ {x_fR} {y_fR} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("CG")
        send_command(f"moveXYZ {x_tR} {y_tR} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("OG")
        send_command(f"moveXYZ {H_X} {H_Y} {H_Z}")

    else:

        send_command(f"moveXYZ {x_f} {y_f} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("CG")
        send_command(f"moveXYZ {x_t} {y_t} {Z_HOVER}")
        send_command(f"moveZ {Z_DOWN}")
        send_command("OG")
        send_command(f"moveXYZ {H_X} {H_Y} {H_Z}")


def send_command(command):
    manual_serial.write(f"{command}\n".encode())
    response = manual_serial.readline().decode().strip()
    return response