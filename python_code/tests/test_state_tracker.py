from __future__ import annotations

from pathlib import Path
import sys
import unittest

import chess

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from charm.game.state_tracker import (
    BoardStateTracker,
    board_to_bitmaps,
    board_to_occupancy_bitmap,
    infer_move_from_bitmaps,
    infer_move_from_occupancy,
)


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
        self.assertEqual(result.status, "accepted_legal_move")
        self.assertEqual(result.matching_move_count, 1)

    def test_infers_knight_move(self) -> None:
        board = chess.Board()
        board.push(chess.Move.from_uci("g1f3"))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(chess.Board(), white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "g1f3")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")

    def test_infers_bishop_move(self) -> None:
        board = chess.Board()
        for uci in ("e2e4", "a7a6", "f1c4"):
            board.push(chess.Move.from_uci(uci))

        before_bishop_move = chess.Board()
        for uci in ("e2e4", "a7a6"):
            before_bishop_move.push(chess.Move.from_uci(uci))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_bishop_move, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "f1c4")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")

    def test_infers_rook_move(self) -> None:
        before_rook_move = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQK2R w KQkq - 0 1")
        board = before_rook_move.copy(stack=False)
        board.push(chess.Move.from_uci("h1g1"))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_rook_move, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "h1g1")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")

    def test_infers_queen_move(self) -> None:
        board = chess.Board()
        for uci in ("d2d4", "a7a6", "d1d3"):
            board.push(chess.Move.from_uci(uci))

        before_queen_move = chess.Board()
        for uci in ("d2d4", "a7a6"):
            before_queen_move.push(chess.Move.from_uci(uci))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_queen_move, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "d1d3")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")

    def test_infers_king_move(self) -> None:
        before_king_move = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQ1KNR w kq - 0 1")
        board = before_king_move.copy(stack=False)
        board.push(chess.Move.from_uci("f1e1"))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_king_move, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "f1e1")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")

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
        self.assertEqual(result.status, "accepted_legal_move")

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
        self.assertEqual(result.status, "accepted_legal_move")

    def test_infers_black_castling(self) -> None:
        board = chess.Board()
        for uci in ("e2e4", "e7e5", "g1f3", "g8f6", "f1e2", "f8e7", "e1g1", "e8g8"):
            board.push(chess.Move.from_uci(uci))

        before_black_castle = chess.Board()
        for uci in ("e2e4", "e7e5", "g1f3", "g8f6", "f1e2", "f8e7", "e1g1"):
            before_black_castle.push(chess.Move.from_uci(uci))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_black_castle, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e8g8")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")

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
        self.assertEqual(result.status, "accepted_legal_move")

    def test_infers_promotion(self) -> None:
        before_promotion = chess.Board("7k/4P3/8/8/8/8/8/4K3 w - - 0 1")
        board = before_promotion.copy(stack=False)
        board.push(chess.Move.from_uci("e7e8q"))

        white_bitmap, black_bitmap = board_to_bitmaps(board)
        result = infer_move_from_bitmaps(before_promotion, white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertIn(result.move.uci(), {"e7e8q", "e7e8r", "e7e8b", "e7e8n"})
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")
        self.assertGreater(result.matching_move_count, 1)

    def test_returns_none_when_position_is_unchanged(self) -> None:
        board = chess.Board()
        white_bitmap, black_bitmap = board_to_bitmaps(board)

        tracker = BoardStateTracker(board)
        result = tracker.update_from_bitmaps(white_bitmap, black_bitmap)

        self.assertIsNone(result.move)
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "unchanged_position")
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
        self.assertEqual(result.status, "accepted_legal_move")

        board_after_e4_e5 = chess.Board()
        for uci in ("e2e4", "e7e5"):
            board_after_e4_e5.push(chess.Move.from_uci(uci))
        white_bitmap, black_bitmap = board_to_bitmaps(board_after_e4_e5)
        result = tracker.update_from_bitmaps(white_bitmap, black_bitmap)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e7e5")
        self.assertEqual(result.mismatch_count, 0)
        self.assertEqual(result.status, "accepted_legal_move")
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
        self.assertEqual(result.status, "invalid_observation")
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
        self.assertEqual(result.status, "accepted_legal_move")
        self.assertEqual(tracker.board.fen(), board_after_e4.fen())

    def test_occupancy_fallback_accepts_legal_move_with_extra_noise(self) -> None:
        board_after_e4 = chess.Board()
        board_after_e4.push(chess.Move.from_uci("e2e4"))
        occupancy = board_to_occupancy_bitmap(board_after_e4)

        # Random false positive: d4 suddenly looks occupied.
        occupancy[4][3] = 1

        result = infer_move_from_occupancy(chess.Board(), occupancy)

        self.assertIsNotNone(result.move)
        self.assertEqual(result.move.uci(), "e2e4")
        self.assertEqual(result.mismatch_count, 1)
        self.assertEqual(result.status, "accepted_legal_move")

    def test_occupancy_fallback_rejects_noise_without_legal_move(self) -> None:
        occupancy = board_to_occupancy_bitmap(chess.Board())

        # Only an impossible extra piece appears; no source square changed.
        occupancy[4][3] = 1

        tracker = BoardStateTracker()
        result = tracker.update_from_occupancy(
            occupancy,
            max_mismatches=0,
        )

        self.assertIsNone(result.move)
        self.assertEqual(result.status, "invalid_observation")
        self.assertEqual(tracker.board.fen(), chess.Board().fen())


if __name__ == "__main__":
    unittest.main()
