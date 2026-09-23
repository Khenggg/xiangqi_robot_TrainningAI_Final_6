"""Match a fully recognized board against legal Red successors."""
from __future__ import annotations

from typing import Dict, Iterable

from src.core import xiangqi
from src.vision.player_turn_types import Board, MatchKind, MatchResult, Move


def freeze_board(board: Iterable[Iterable[str]]) -> Board:
    result = tuple(tuple(row) for row in board)
    if len(result) != 10 or any(len(row) != 9 for row in result):
        raise ValueError("board layout must be 10x9")
    return result


class LegalSuccessorMatcher:
    """Exact full-board matcher; it deliberately never guesses from occupancy."""

    def __init__(self, committed_board):
        self.committed_board = freeze_board(committed_board)
        self.successors: Dict[Move, Board] = {}
        for move in xiangqi.find_all_valid_moves("r", [list(row) for row in self.committed_board]):
            successor, _ = xiangqi.make_temp_move([list(row) for row in self.committed_board], move)
            self.successors[move] = freeze_board(successor)

    def match(self, layout) -> MatchResult:
        if layout is None:
            return MatchResult(MatchKind.UNAVAILABLE, reason="no complete layout")
        try:
            observed = freeze_board(layout)
        except (TypeError, ValueError):
            return MatchResult(MatchKind.UNAVAILABLE, reason="malformed layout")
        if observed == self.committed_board:
            return MatchResult(MatchKind.BASELINE_EQUAL)
        candidates = [move for move, board in self.successors.items() if board == observed]
        if len(candidates) == 1:
            return MatchResult(MatchKind.UNIQUE, candidates[0])
        if len(candidates) > 1:
            return MatchResult(MatchKind.AMBIGUOUS, reason="multiple legal successors")
        return MatchResult(MatchKind.INVALID, reason="layout is not a legal Red successor")
