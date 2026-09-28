"""Stable game identities and semantic moves; cells use (row, col)."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple
import json
from uuid import uuid4


class MoveActor(str, Enum):
    HUMAN = "HUMAN"
    ROBOT = "ROBOT"


@dataclass(frozen=True)
class MoveContext:
    piece_id: str
    src: Tuple[int, int]
    dst: Tuple[int, int]
    actor: MoveActor
    captured_piece_id: Optional[str] = None
    move_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self):
        object.__setattr__(self, "actor", MoveActor(self.actor))
        for name in ("src", "dst"):
            cell = tuple(getattr(self, name))
            if len(cell) != 2 or any(isinstance(v, bool) or not isinstance(v, int) for v in cell):
                raise ValueError(f"{name} must contain integer (row, col)")
            if not (0 <= cell[0] < 10 and 0 <= cell[1] < 9):
                raise ValueError(f"{name} outside board: {cell}")
            object.__setattr__(self, name, cell)
        if not self.piece_id or self.piece_id == self.captured_piece_id:
            raise ValueError("Move requires distinct moving and captured piece identities")
        if self.src == self.dst:
            raise ValueError("Move source and destination must differ")


def initial_piece_identities() -> Dict[Tuple[int, int], str]:
    """Load the same stable IDs used to spawn PyBullet pieces, without physics."""
    path = Path(__file__).resolve().parents[2] / "shared" / "xiangqi_start_layout.json"
    with path.open(encoding="utf-8-sig") as handle:
        pieces = json.load(handle)["pieces"]
    identities = {(int(piece["row"]), int(piece["col"])): str(piece["id"]) for piece in pieces}
    if len(identities) != len(pieces) or len(set(identities.values())) != len(pieces):
        raise ValueError("Initial layout contains duplicate cells or piece IDs")
    return identities


def piece_symbol_for_identity(piece_id: str) -> str:
    """Convert canonical layout IDs to GameState's existing r_P/b_R symbols."""
    side, kind, _index = piece_id.split("_")
    codes = {"rook": "R", "knight": "N", "elephant": "E", "advisor": "A",
             "king": "K", "cannon": "C", "pawn": "P"}
    return {"red": "r", "black": "b"}[side] + "_" + codes[kind]
