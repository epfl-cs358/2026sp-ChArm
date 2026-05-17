from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import chess

Bitmap = list[list[int]]
TrackerStatus = Literal[
    "accepted_legal_move",
    "unchanged_position",
    "invalid_observation",
    "ambiguous_observation",
]


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


def compare_board_to_bitmaps(expected_board, white_bitmap, black_bitmap) -> int:
    """
    Compare a python-chess board with detected 8x8 white/black bitmaps.

    Bitmap convention:
      row 0 = rank 8
      row 7 = rank 1
      col 0 = file a
      col 7 = file h
    """
    mismatch_count = 0

    for row in range(8):
        for col in range(8):
            rank = 7 - row
            file = col
            square = chess.square(file, rank)

            piece = expected_board.piece_at(square)

            expected_white = piece is not None and piece.color == chess.WHITE
            expected_black = piece is not None and piece.color == chess.BLACK

            detected_white = bool(white_bitmap[row][col])
            detected_black = bool(black_bitmap[row][col])

            if expected_white != detected_white or expected_black != detected_black:
                mismatch_count += 1
                print(
                    f"[MISMATCH] {chess.square_name(square)} "
                    f"expected_white={expected_white}, "
                    f"expected_black={expected_black}, "
                    f"detected_white={detected_white}, "
                    f"detected_black={detected_black}"
                )

    print("[DEBUG] total mismatch_count =", mismatch_count)
    return mismatch_count


@dataclass
class MoveInferenceResult:
    move: Optional[chess.Move]
    mismatch_count: int
    status: TrackerStatus
    matching_move_count: int = 0


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

    if current_mismatch_count == 0:
        return MoveInferenceResult(
            move=None,
            mismatch_count=0,
            status="unchanged_position",
            matching_move_count=0,
        )

    best_result = MoveInferenceResult(
        move=None,
        mismatch_count=current_mismatch_count,
        status="invalid_observation",
        matching_move_count=0,
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
                status="accepted_legal_move",
                matching_move_count=1,
            )
        elif mismatch_count == best_result.mismatch_count and best_result.move is not None:
            best_result.matching_move_count += 1

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

        if result.status == "unchanged_position":
            return result

        if result.move is None or result.mismatch_count > max_mismatches:
            return MoveInferenceResult(
                move=None,
                mismatch_count=result.mismatch_count,
                status="invalid_observation",
                matching_move_count=result.matching_move_count,
            )

        if result.matching_move_count > 1:
            return MoveInferenceResult(
                move=None,
                mismatch_count=result.mismatch_count,
                status="ambiguous_observation",
                matching_move_count=result.matching_move_count,
            )

        self.board.push(result.move)
        return MoveInferenceResult(
            move=result.move,
            mismatch_count=result.mismatch_count,
            status="accepted_legal_move",
            matching_move_count=result.matching_move_count,
        )
