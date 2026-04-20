from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess

Bitmap = list[list[int]]


def empty_bitmap() -> Bitmap:
    return [[0 for _ in range(8)] for _ in range(8)]


def board_to_bitmaps(board: chess.Board) -> tuple[Bitmap, Bitmap]:
    """
    Convert a python-chess board to the same 8x8 bitmap format produced by vision.

    Assumed orientation:
    - bitmap row 0 is rank 8
    - bitmap col 0 is file a
    """
    white_bitmap = empty_bitmap()
    black_bitmap = empty_bitmap()

    for square, piece in board.piece_map().items():
        row = 7 - chess.square_rank(square)
        col = chess.square_file(square)

        if piece.color == chess.WHITE:
            white_bitmap[row][col] = 1
        else:
            black_bitmap[row][col] = 1

    return white_bitmap, black_bitmap


def count_bitmap_mismatches(left: Bitmap, right: Bitmap) -> int:
    mismatches = 0

    for row in range(8):
        for col in range(8):
            if left[row][col] != right[row][col]:
                mismatches += 1

    return mismatches


def compare_board_to_bitmaps(
    board: chess.Board,
    observed_white_bitmap: Bitmap,
    observed_black_bitmap: Bitmap,
) -> int:
    candidate_white_bitmap, candidate_black_bitmap = board_to_bitmaps(board)

    return count_bitmap_mismatches(candidate_white_bitmap, observed_white_bitmap) + count_bitmap_mismatches(
        candidate_black_bitmap,
        observed_black_bitmap,
    )


@dataclass
class MoveInferenceResult:
    move: Optional[chess.Move]
    mismatch_count: int


def infer_move_from_bitmaps(
    board: chess.Board,
    observed_white_bitmap: Bitmap,
    observed_black_bitmap: Bitmap,
) -> MoveInferenceResult:
    """
    Infer the move that best explains the observed bitmaps.

    If the current board already matches exactly, return move=None.
    """
    current_mismatch_count = compare_board_to_bitmaps(
        board,
        observed_white_bitmap,
        observed_black_bitmap,
    )

    best_result = MoveInferenceResult(
        move=None,
        mismatch_count=current_mismatch_count,
    )

    for move in board.legal_moves:
        candidate_board = board.copy(stack=False)
        candidate_board.push(move)

        mismatch_count = compare_board_to_bitmaps(
            candidate_board,
            observed_white_bitmap,
            observed_black_bitmap,
        )

        if mismatch_count < best_result.mismatch_count:
            best_result = MoveInferenceResult(
                move=move,
                mismatch_count=mismatch_count,
            )

    return best_result


class BoardStateTracker:
    def __init__(self, board: Optional[chess.Board] = None) -> None:
        self.board = board.copy(stack=True) if board is not None else chess.Board()

    def current_bitmaps(self) -> tuple[Bitmap, Bitmap]:
        return board_to_bitmaps(self.board)

    def infer_move(
        self,
        observed_white_bitmap: Bitmap,
        observed_black_bitmap: Bitmap,
    ) -> MoveInferenceResult:
        return infer_move_from_bitmaps(
            self.board,
            observed_white_bitmap,
            observed_black_bitmap,
        )

    def update_from_bitmaps(
        self,
        observed_white_bitmap: Bitmap,
        observed_black_bitmap: Bitmap,
        max_mismatches: int = 0,
    ) -> MoveInferenceResult:
        result = self.infer_move(
            observed_white_bitmap,
            observed_black_bitmap,
        )

        if result.move is None:
            return result

        if result.mismatch_count > max_mismatches:
            return MoveInferenceResult(
                move=None,
                mismatch_count=result.mismatch_count,
            )

        self.board.push(result.move)
        return result
