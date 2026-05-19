"""Shared helper: (row, col) for every chessboard square in warped-image space."""

SQUARES_RC: list[tuple[int, int]] = [(r, c) for r in range(8) for c in range(8)]
