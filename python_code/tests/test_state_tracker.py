from __future__ import annotations

from pathlib import Path
import sys
import unittest

import chess

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.game.state_tracker import BoardStateTracker, board_to_bitmaps, infer_move_from_bitmaps


def clone_bitmap(bitmap: list[list[int]]) -> list[list[int]]:
    return [row.copy() for row in bitmap]


class StateTrackerTests(unittest.TestCase):
    def test_board_to_bitmaps_matches_start_position_counts(self) -> None:
        white_bitmap, black_bitmap = board_to_bitmaps(chess.Board())

        self.assertEqual(sum(sum(row) for row in white_bitmap), 16)
        self.assertEqual(sum(sum(row) for row in black_bitmap), 16)
        self.assertEqual(white_bitmap[6][4], 1)  # e2
        self.assertEqual(black_bitmap[1][4], 1)  # e7

    def test_infers_simple_pawn_move(self) -> None:
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(chess.Board(), white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e2e4")
        self.assertEqual(result.mismatch_count, 0)

    def test_infers_capture(self) -> None:
        board = chess.Board()
        for uci in ("e2e4", "d7d5", "e4d5"):
            board.push(chess.Move.from_uci(uci))

        before_capture = chess.Board()
        for uci in ("e2e4", "d7d5"):
            before_capture.push(chess.Move.from_uci(uci))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_capture, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e4d5")
        self.assertEqual(result.mismatch_count, 0)

    def test_infers_castling(self) -> None:
        board = chess.Board()
        for uci in ("g1f3", "g8f6", "e2e4", "e7e5", "f1e2", "b8c6", "e1g1"):
            board.push(chess.Move.from_uci(uci))

        before_castle = chess.Board()
        for uci in ("g1f3", "g8f6", "e2e4", "e7e5", "f1e2", "b8c6"):
            before_castle.push(chess.Move.from_uci(uci))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_castle, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e1g1")
        self.assertEqual(result.mismatch_count, 0)

    def test_infers_en_passant(self) -> None:
        board = chess.Board()
        for uci in ("e2e4", "a7a6", "e4e5", "d7d5", "e5d6"):
            board.push(chess.Move.from_uci(uci))

        before_en_passant = chess.Board()
        for uci in ("e2e4", "a7a6", "e4e5", "d7d5"):
            before_en_passant.push(chess.Move.from_uci(uci))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_en_passant, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e5d6")
        self.assertEqual(result.mismatch_count, 0)

    def test_returns_none_when_position_is_unchanged(self) -> None:
        board = chess.Board()
        white_bitmap, black_bitmap = board_to_bitmaps(board)

        tracker = BoardStateTracker(board)
        result = tracker.update_from_bitmaps(white_bitmap, black_bitmap)

        self.assertIsNone(result.move)
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(tracker.board.fen(), board.fen())

    def test_tracker_updates_across_multiple_moves(self) -> None:
        tracker = BoardStateTracker()

        board_after_e4 = chess.Board()
        board_after_e4.push(chess.Move.from_uci("e2e4"))
        white_bitmap, black_bitmap = board_to_bitmaps(board_after_e4)
        result = tracker.update_from_bitmaps(white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e2e4")
        self.assertEqual(result.mismatch_count, 0)

        board_after_e4_e5 = chess.Board()
        for uci in ("e2e4", "e7e5"):
            board_after_e4_e5.push(chess.Move.from_uci(uci))
        white_bitmap, black_bitmap = board_to_bitmaps(board_after_e4_e5)
        result = tracker.update_from_bitmaps(white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e7e5")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(tracker.board.fen(), board_after_e4_e5.fen())

    def test_rejects_inconsistent_bitmaps_when_mismatch_limit_is_zero(self) -> None:
        tracker = BoardStateTracker()
        white_bitmap, black_bitmap = board_to_bitmaps(chess.Board())

        bad_white_bitmap = clone_bitmap(white_bitmap)
        bad_black_bitmap = clone_bitmap(black_bitmap)

        # Impossible observation: e2 is empty, e4 has a white piece, and an extra
        # white piece appears on d4 at the same time.
        bad_white_bitmap[6][4] = 0
        bad_white_bitmap[4][4] = 1
        bad_white_bitmap[4][3] = 1

        result = tracker.update_from_bitmaps(
            bad_white_bitmap,
            bad_black_bitmap,
            max_mismatches=0,
        )

        self.assertIsNone(result.move)
        self.assertGreater(result.mismatch_count, 0)
        self.assertEqual(tracker.board.fen(), chess.Board().fen())

    def test_allows_noisy_match_when_mismatch_limit_is_relaxed(self) -> None:
        tracker = BoardStateTracker()

        board_after_e4 = chess.Board()
        board_after_e4.push(chess.Move.from_uci("e2e4"))
        white_bitmap, black_bitmap = board_to_bitmaps(board_after_e4)

        noisy_white_bitmap = clone_bitmap(white_bitmap)
        noisy_black_bitmap = clone_bitmap(black_bitmap)

        # Add one wrong occupied white square while keeping the true e2e4 pattern.
        noisy_white_bitmap[3][3] = 1

        result = tracker.update_from_bitmaps(
            noisy_white_bitmap,
            noisy_black_bitmap,
            max_mismatches=1,
        )

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e2e4")
        self.assertEqual(result.mismatch_count, 1)
        self.assertEqual(tracker.board.fen(), board_after_e4.fen())


if __name__ == "__main__":
    unittest.main()
