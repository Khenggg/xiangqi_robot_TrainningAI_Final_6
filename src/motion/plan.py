"""
Motion Plan, Motion Step, and Task Intent Contracts.

Implements a two-layer motion architecture:
1. Semantic Task Intent (board-space coordinates, game logic, piece identities)
2. Resolved Motion Plan (Cartesian waypoints, gripper steps, placement versions)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.motion.contracts import GripperCommand, MotionType, MotionWaypoint
from src.motion.result import PayloadState
from src.motion.stages import MotionStage


# ==============================================================================
# Layer 1: Semantic Task Intents (Operate on Row, Col — NEVER Robot XYZ)
# ==============================================================================

@dataclass(frozen=True)
class BoardPickIntent:
    """
    Semantic intent to pick a piece from a board square.
    
    Coordinates are board-local (row, col). Robot XYZ is NOT authoritative here
    and must be resolved through an authoritative BoardPoseProvider.
    """
    row: float
    col: float
    piece_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoardPlaceIntent:
    """
    Semantic intent to place a held piece onto a board square.
    """
    row: float
    col: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PieceMoveIntent:
    """
    Semantic intent to move a piece between board squares without capture.
    """
    src_row: float
    src_col: float
    dst_row: float
    dst_col: float
    piece_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureIntent:
    """
    Semantic intent to execute a capture move:
    1. Remove opponent piece at (dst_row, dst_col) to capture bin.
    2. Move attacking piece from (src_row, src_col) to (dst_row, dst_col).
    """
    src_row: float
    src_col: float
    dst_row: float
    dst_col: float
    bin_cell: Optional[Tuple[float, float]] = (-1.0, -1.0)
    bin_pose_mm_deg: Optional[Tuple[float, float, float, float, float, float]] = None
    attacker_piece_id: Optional[str] = None
    captured_piece_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


# ==============================================================================
# Layer 2: Resolved Motion Steps & Motion Plan
# ==============================================================================

@dataclass(frozen=True)
class MotionStep:
    """
    A single discrete action within an executable MotionPlan.
    
    May represent a Cartesian move, gripper action, wait/dwell, or verification check.
    """
    step_id: int
    stage: MotionStage
    motion_type: MotionType
    waypoint: Optional[MotionWaypoint] = None
    gripper_command: Optional[GripperCommand] = None
    wait_duration_s: Optional[float] = None
    expected_payload_state: Optional[PayloadState] = None
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.motion_type in (MotionType.CARTESIAN_LINEAR, MotionType.CARTESIAN_POINT, MotionType.JOINT):
            if self.waypoint is None:
                raise ValueError(f"MotionStep of type {self.motion_type} requires a valid waypoint")
        elif self.motion_type == MotionType.GRIPPER:
            if self.gripper_command is None:
                raise ValueError("MotionStep of type GRIPPER requires a gripper_command")
        elif self.motion_type == MotionType.WAIT:
            if self.wait_duration_s is None or self.wait_duration_s < 0.0:
                raise ValueError("MotionStep of type WAIT requires a non-negative wait_duration_s")


@dataclass(frozen=True)
class MotionPlan:
    """
    Immutable specification of an end-to-end motion choreography.
    
    Carries full execution metadata including placement version consistency tracking,
    stage sequence, and payload intent.
    """
    task_id: str
    plan_type: str
    steps: Tuple[MotionStep, ...]
    source: Optional[Tuple[float, float]] = None
    destination: Optional[Tuple[float, float]] = None
    payload_intent: PayloadState = PayloadState.NONE
    placement_version: Optional[int] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.steps:
            raise ValueError("MotionPlan must contain at least one MotionStep")
        # Ensure steps is an immutable tuple
        if not isinstance(self.steps, tuple):
            object.__setattr__(self, "steps", tuple(self.steps))

    @property
    def total_steps(self) -> int:
        """Total number of discrete steps in this plan."""
        return len(self.steps)

    def stages(self) -> Tuple[MotionStage, ...]:
        """Return the sequence of functional stages across all steps."""
        return tuple(step.stage for step in self.steps)

    def get_step(self, step_id: int) -> Optional[MotionStep]:
        """Find a step by its integer ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def is_valid_for_placement_version(self, current_version: int) -> bool:
        """
        Check if this plan matches the current authoritative board placement version.
        
        If placement_version is None, plan is version-agnostic (e.g. pure joint moves).
        If placement_version is set, it MUST match current_version.
        """
        if self.placement_version is None:
            return True
        return self.placement_version == current_version
