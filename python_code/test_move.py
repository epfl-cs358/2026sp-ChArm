from charm.arduino.arduino_bridge import execute_move, send_command

print("Sending test move: e2 -> e4")
execute_move("e2e4", is_capture=False, is_castling=False, is_promotion=False)
print("Done.")
