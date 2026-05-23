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


def compare_board_to_bitmaps(
    board: chess.Board,
    observed_white_bitmap: Bitmap,
    observed_black_bitmap: Bitmap,
    print_mismatches: bool = True,
) -> int:
    # Per-square loop only for diagnostic [MISMATCH] prints. The returned count
    # uses the per-channel sum (webapp's original convention) so that callers
    # passing a non-zero max_mismatches see the same threshold semantics as
    # before the prints were restored.
    if print_mismatches:
        for row in range(8):
            for col in range(8):
                rank = 7 - row
                file = col
                square = chess.square(file, rank)

                piece = board.piece_at(square)
                expected_white = piece is not None and piece.color == chess.WHITE
                expected_black = piece is not None and piece.color == chess.BLACK

                detected_white = bool(observed_white_bitmap[row][col])
                detected_black = bool(observed_black_bitmap[row][col])

                if expected_white != detected_white or expected_black != detected_black:
                    print(
                        f"[MISMATCH] {chess.square_name(square)} "
                        f"expected_white={expected_white}, "
                        f"expected_black={expected_black}, "
                        f"detected_white={detected_white}, "
                        f"detected_black={detected_black}"
                    )

    candidate_white_bitmap, candidate_black_bitmap = board_to_bitmaps(board)
    mismatch_count = count_bitmap_mismatches(
        candidate_white_bitmap, observed_white_bitmap
    ) + count_bitmap_mismatches(
        candidate_black_bitmap, observed_black_bitmap
    )

    if print_mismatches:
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
        print_mismatches=True,
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
        # Bitmaps are occupancy-only (no piece type), so all promotion variants
        # produce identical bitmaps.  Keep only queen promotions to avoid a
        # spurious ambiguous_observation when a human promotes.
        if move.promotion and move.promotion != chess.QUEEN:
            continue

        candidate_board = board.copy(stack=False)
        candidate_board.push(move)

        mismatch_count = compare_board_to_bitmaps(
            candidate_board,
            observed_white_bitmap,
            observed_black_bitmap,
            print_mismatches=False,
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

    # Print summary diagnostics for the best match found
    if best_result.move is not None:
        if best_result.matching_move_count > 1:
            print(f"[DEBUG] Ambiguous result: {best_result.matching_move_count} moves found matching the minimal mismatch count of {best_result.mismatch_count}", flush=True)
        else:
            print(f"[DEBUG] Best inferred move: {best_result.move.uci()} (mismatch count: {best_result.mismatch_count})", flush=True)
    else:
        print(f"[DEBUG] No legal move found to improve mismatch count of {best_result.mismatch_count}", flush=True)

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
