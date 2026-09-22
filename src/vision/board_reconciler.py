"""Reconcile the logical Xiangqi board with a fresh physical-board snapshot.

The camera layout model answers *which* piece is on a square; YOLO supplies
the sub-cell location used by the gripper.  Keeping those responsibilities
separate prevents a nearby, but wrong, physical piece from being picked.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator


Cell = Tuple[int, int]


@dataclass(frozen=True)
class PieceObservation:
    """Comparison for one logical piece that the robot must pick."""

    expected_piece: str
    observed_piece: str
    target: Optional[GridTarget]
    reason: Optional[str] = None

    @property
    def verified(self) -> bool:
        return self.reason is None and self.target is not None


@dataclass(frozen=True)
class BoardSyncReport:
    """Result of comparing a CChess layout with the in-memory FEN board."""

    available: bool
    mismatches: Tuple[Cell, ...]
    unknown_cells: Tuple[Cell, ...]
    picks: Dict[str, PieceObservation]
    error: Optional[str] = None

    @property
    def board_matches(self) -> bool:
        """Unknown model classifications are reported, not mistaken for matches."""
        return self.available and not self.mismatches and not self.unknown_cells

    @property
    def picks_verified(self) -> bool:
        return self.available and all(observation.verified for observation in self.picks.values())

    @property
    def safe_to_execute(self) -> bool:
        return self.board_matches and self.picks_verified


class BoardReconciler:
    """Validate physical piece identity and locate its real pick position."""

    def __init__(self, pick_estimator: VisualPickEstimator):
        self.pick_estimator = pick_estimator

    @staticmethod
    def _valid_board(board: object) -> bool:
        return (
            isinstance(board, list)
            and len(board) == 10
            and all(isinstance(row, list) and len(row) == 9 for row in board)
        )

    def reconcile(
        self,
        expected_board: List[List[str]],
        expected_cells: Dict[str, Cell],
        cchess_result: Optional[dict],
        detections: Iterable[tuple],
    ) -> BoardSyncReport:
        """Return board drift plus verified camera-corrected pick targets.

        ``x`` is the layout model's unknown class.  It is kept visible in the
        report but does not get silently converted to an empty square.
        """
        if not self._valid_board(expected_board):
            return BoardSyncReport(False, (), (), {}, "invalid expected board shape")
        if not cchess_result or not cchess_result.get("success"):
            error = (cchess_result or {}).get("error", "CChess board recognition unavailable")
            return BoardSyncReport(False, (), (), {}, str(error))

        actual_board = cchess_result.get("board")
        if not self._valid_board(actual_board):
            return BoardSyncReport(False, (), (), {}, "invalid CChess board shape")

        mismatches = []
        unknown_cells = []
        for row in range(10):
            for col in range(9):
                expected = expected_board[row][col]
                actual = actual_board[row][col]
                if actual == "x":
                    unknown_cells.append((col, row))
                elif actual != expected:
                    mismatches.append((col, row))

        picks: Dict[str, PieceObservation] = {}
        for name, (col, row) in expected_cells.items():
            if not (0 <= col < 9 and 0 <= row < 10):
                picks[name] = PieceObservation("?", "?", None, "expected cell is outside the board")
                continue
            expected = expected_board[row][col]
            actual = actual_board[row][col]
            if expected in (".", "x"):
                picks[name] = PieceObservation(expected, actual, None, "logical source has no known piece")
            elif actual != expected:
                picks[name] = PieceObservation(expected, actual, None, "physical piece identity does not match FEN")
            else:
                target = self.pick_estimator.estimate_pick_target(detections, col, row)
                if target is None:
                    picks[name] = PieceObservation(expected, actual, None, "no stable physical pick point")
                else:
                    picks[name] = PieceObservation(expected, actual, target)

        return BoardSyncReport(True, tuple(mismatches), tuple(unknown_cells), picks)
