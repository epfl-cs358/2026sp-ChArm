A1_X = TODO
A1_Y = TODO
STEP = 37.5

Z_HOVER = TODO
Z_DOWN = TODO

H_X = TODO
H_Y = TODO
H_Z = TODO

T_X = TODO
T_Y = TODO
T_Z = TODO

def get_square_position(move):
    col = ord(move[0]) - ord('a')
    row = int(move[1]) - 1

    x = A1_X + col * STEP
    y = A1_Y + row * STEP

    return (x, y)

