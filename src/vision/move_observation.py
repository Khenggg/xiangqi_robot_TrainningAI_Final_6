"""
Move Observation Data Contract and Board Deduction.

Defines the semantic contract for vision observations of the Xiangqi board:
  - Strict board-space coordinates: (col: 0..8, row: 0..9)
  - Clear distinction between valid moves, captures, ambiguous changes, and errors
  - Fails safely if multiple pieces move or if moves violate rules
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from src.core import xiangqi


@dataclass(frozen=True)
class MoveObservation:
    """
    Immutable semantic observation of a board change / player move.
    """
    success: bool
    src: Optional[Tuple[int, int]] = None            # (col, row)
    dst: Optional[Tuple[int, int]] = None            # (col, row)
    piece: Optional[str] = None                      # e.g. "r_C", "r_P"
    is_capture: bool = False
    captured_piece: Optional[str] = None
    confidence: float = 1.0
    is_ambiguous: bool = False
    error: Optional[str] = None

    def as_tuple(self) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]], Optional[str]]:
        """Compatibility helper for legacy (src, dst, piece) tuple unpacking."""
        return self.src, self.dst, self.piece


def derive_move_observation(
    before_board: List[List[str]],
    after_board: List[List[str]],
    player_color: str = "r",
    min_confidence: float = 0.5,
    confidence_grid: Optional[List[List[float]]] = None,
) -> MoveObservation:
    """
    Derive semantic MoveObservation by comparing before and after board state grids (10x9).

    Args:
        before_board: 10x9 matrix of piece strings at T1 (baseline)
        after_board: 10x9 matrix of piece strings at T2 (fresh observation)
        player_color: "r" (Red / human) or "b" (Black / AI)
        min_confidence: minimum threshold for layout recognition
        confidence_grid: optional 10x9 confidence values

    Returns:
        MoveObservation indicating detected move or failure/ambiguity reason.
    """
    if not before_board or not after_board:
        return MoveObservation(success=False, error="Board matrix is empty or None")

    if len(before_board) != 10 or len(after_board) != 10:
        return MoveObservation(success=False, error="Invalid board height (expected 10 rows)")

    if any(len(row) != 9 for row in before_board) or any(len(row) != 9 for row in after_board):
        return MoveObservation(success=False, error="Invalid board width (expected 9 cols)")

    # 1. Check confidence if provided
    avg_conf = 1.0
    if confidence_grid is not None:
        confs = [c for row in confidence_grid for c in row]
        if confs:
            avg_conf = float(sum(confs) / len(confs))
            if min(confs) < min_confidence and avg_conf < min_confidence:
                return MoveObservation(
                    success=False,
                    confidence=avg_conf,
                    error=f"Low recognition confidence ({avg_conf:.2f} < {min_confidence:.2f})",
                )

    # 2. Find differences
    disappeared = []  # pieces of player_color that were present at T1 but changed at T2
    appeared = []     # cells where player_color pieces appeared at T2

    for r in range(10):
        for c in range(9):
            p1 = before_board[r][c]
            p2 = after_board[r][c]
            if p1 != p2:
                # Cell changed
                if p1.startswith(player_color) and not p2.startswith(player_color):
                    disappeared.append(((c, r), p1))
                elif p2.startswith(player_color) and not p1.startswith(player_color):
                    appeared.append(((c, r), p2))
                elif p1.startswith(player_color) and p2.startswith(player_color):
                    # Piece of same color changed type? E.g. recognition flicker or pawn promotion
                    # In Xiangqi, pawns do not change piece type. Treat as disappearance + appearance
                    disappeared.append(((c, r), p1))
                    appeared.append(((c, r), p2))

    # 3. Analyze change counts
    if len(disappeared) == 0 and len(appeared) == 0:
        return MoveObservation(success=False, error="No board change detected")

    if len(disappeared) > 1 or len(appeared) > 1:
        return MoveObservation(
            success=False,
            is_ambiguous=True,
            error=f"Multiple piece changes detected ({len(disappeared)} disappeared, {len(appeared)} appeared)",
        )

    if len(disappeared) == 1 and len(appeared) == 0:
        src, p = disappeared[0]
        return MoveObservation(
            success=False,
            src=src,
            piece=p,
            error=f"Piece {p} at {src} disappeared without arriving at destination",
        )

    if len(disappeared) == 0 and len(appeared) == 1:
        dst, p = appeared[0]
        return MoveObservation(
            success=False,
            dst=dst,
            piece=p,
            error=f"Piece {p} appeared at {dst} without origin source",
        )

    # Exactly 1 disappeared and 1 appeared
    (src_c, src_r), p_src = disappeared[0]
    (dst_c, dst_r), p_dst = appeared[0]

    src = (src_c, src_r)
    dst = (dst_c, dst_r)

    # 4. Validate piece identity consistency
    # Note: On noisy classification, p_dst might occasionally differ slightly from p_src,
    # but the canonical moved piece is the one from the authoritative before_board (p_src).
    piece = p_src

    # 5. Rule validation
    if not xiangqi.is_valid_move(src, dst, before_board, player_color):
        return MoveObservation(
            success=False,
            src=src,
            dst=dst,
            piece=piece,
            error=f"Illegal move {piece} {src}->{dst} according to Xiangqi rules",
        )

    # 6. Check capture
    orig_dest_piece = before_board[dst_r][dst_c]
    is_capture = (orig_dest_piece != ".")
    captured_piece = orig_dest_piece if is_capture else None

    return MoveObservation(
        success=True,
        src=src,
        dst=dst,
        piece=piece,
        is_capture=is_capture,
        captured_piece=captured_piece,
        confidence=avg_conf,
    )
