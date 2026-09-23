"""Small, dependency-free contracts for human-turn confirmation.

The camera is allowed to report uncertainty.  Only a complete clear layout can
become a move candidate; this is what makes a lifted piece or a hand over the
board a non-terminal observation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

Board = Tuple[Tuple[str, ...], ...]
Move = Tuple[Tuple[int, int], Tuple[int, int]]


class PlayerTurnMode(str, Enum):
    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
    UNIFIED = "UNIFIED"


class InteractionCapability(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class Visibility(str, Enum):
    CLEAR = "CLEAR"
    OCCLUDED = "OCCLUDED"
    INSUFFICIENT = "INSUFFICIENT"
    UNAVAILABLE = "UNAVAILABLE"


class PlayerTurnState(str, Enum):
    INACTIVE = "INACTIVE"
    PLAYER_IDLE = "PLAYER_IDLE"
    INTERACTING_OR_OCCLUDED = "INTERACTING_OR_OCCLUDED"
    WAITING_FOR_CLEAR = "WAITING_FOR_CLEAR"
    VALIDATING_FINAL_BOARD = "VALIDATING_FINAL_BOARD"
    UNSETTLED_PLACEMENT = "UNSETTLED_PLACEMENT"
    AMBIGUOUS_BOARD = "AMBIGUOUS_BOARD"
    WAITING_FOR_CORRECTION = "WAITING_FOR_CORRECTION"
    MOVE_CONFIRMED = "MOVE_CONFIRMED"


class MatchKind(str, Enum):
    BASELINE_EQUAL = "BASELINE_EQUAL"
    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class BoardObservation:
    observed_at: float
    layout: Optional[Board]
    visibility: Visibility
    coverage_ratio: float = 1.0
    aggregate_confidence: float = 1.0
    motion_active: bool = False
    hand_or_object_present: bool = False


@dataclass(frozen=True)
class MatchResult:
    kind: MatchKind
    move: Optional[Move] = None
    reason: str = ""


@dataclass(frozen=True)
class CommitRequest:
    turn_token: int
    move: Move
    source: str = "AUTO"
