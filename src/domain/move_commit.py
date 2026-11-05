"""Business commit evidence, independent of optional display projections."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MoveCommitResult:
    committed: bool
    move_id: Optional[str]
    board_revision: int
    projection_pending: bool = False
    projection_error: Optional[str] = None

    def __bool__(self):
        return self.committed
