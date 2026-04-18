from __future__ import annotations

from charm.vision.piece_color_detector import PieceColorResult


def build_white_black_bitmaps(
    color_results: list[PieceColorResult],
) -> tuple[list[list[int]], list[list[int]]]:
    white_bitmap = [[0 for _ in range(8)] for _ in range(8)]
    black_bitmap = [[0 for _ in range(8)] for _ in range(8)]

    for result in color_results:
        if not result.occupied:
            continue

        if result.color == "white":
            white_bitmap[result.row][result.col] = 1
        elif result.color == "black":
            black_bitmap[result.row][result.col] = 1

    return white_bitmap, black_bitmap