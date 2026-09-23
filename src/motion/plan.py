"""
Motion Plan, Motion Step, and Task Intent Contracts.

Implements a two-layer motion architecture:
1. Semantic Task Intent (board-space coordinates, game logic, piece identities)
2. Resolved Motion Plan (Cartesian waypoints, gripper steps, placement versions)
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.motion.contracts import GripperCommand, JointWaypoint, MotionType, MotionWaypoint
from src.motion.result import PayloadState
from src.motion.stages import MotionStage


def _validate_board_coord(row: float, col: float, name: str = "cell", tol: float = 0.5) -> None:
    """Validate continuous board coordinates within 0..9 rows and 0..8 cols with continuous tolerance."""
    if not (-tol <= row <= 9.0 + tol and -tol <= col <= 8.0 + tol):
        raise ValueError(
            f"Semantic board coordinates {name}=({row:.3f}, {col:.3f}) out of bounds "
            f"[0..9, 0..8] with tolerance {tol:.2f}"
        )


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

    def __post_init__(self):
        _validate_board_coord(self.row, self.col, "pick")
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))


@dataclass(frozen=True)
class BoardPlaceIntent:
    """
    Semantic intent to place a held piece onto a board square.
    """
    row: float
    col: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _validate_board_coord(self.row, self.col, "place")
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))


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

    def __post_init__(self):
        _validate_board_coord(self.src_row, self.src_col, "src")
        _validate_board_coord(self.dst_row, self.dst_col, "dst")
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))


@dataclass(frozen=True)
class CaptureIntent:
    """
    Semantic intent to execute a capture move:
    1. Remove opponent piece at (dst_row, dst_col) to capture bin.
    2. Move attacking piece from (src_row, src_col) to (dst_row, dst_col).

    Requires explicit bin target: either bin_pose_mm_deg or bin_cell must be provided.
    """
    src_row: float
    src_col: float
    dst_row: float
    dst_col: float
    bin_cell: Optional[Tuple[float, float]] = None
    bin_pose_mm_deg: Optional[Tuple[float, float, float, float, float, float]] = None
    attacker_piece_id: Optional[str] = None
    captured_piece_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _validate_board_coord(self.src_row, self.src_col, "src")
        _validate_board_coord(self.dst_row, self.dst_col, "dst")
        if self.bin_cell is None and self.bin_pose_mm_deg is None:
            raise ValueError(
                "CaptureIntent requires explicit bin_cell or bin_pose_mm_deg; cannot be empty"
            )
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))


# ==============================================================================
# Layer 2: Resolved Motion Steps & Motion Plan
# ==============================================================================

@dataclass(frozen=True)
class MotionStep:
    """
    A single discrete action within an executable MotionPlan.
    
    May represent a Cartesian move, joint move, gripper action, wait/dwell,
    or verification check.
    """
    step_id: int
    stage: MotionStage
    motion_type: MotionType
    waypoint: Optional[MotionWaypoint] = None
    joint_waypoint: Optional[JointWaypoint] = None
    gripper_command: Optional[GripperCommand] = None
    wait_duration_s: Optional[float] = None
    expected_payload_state: Optional[PayloadState] = None
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Enforce strict, unambiguous target correspondence
        if self.motion_type in (MotionType.CARTESIAN_LINEAR, MotionType.CARTESIAN_POINT):
            if self.waypoint is None:
                raise ValueError(f"MotionStep of Cartesian type {self.motion_type} requires a valid Cartesian waypoint")
            if self.joint_waypoint is not None:
                raise ValueError("MotionStep of Cartesian type cannot accept a joint_waypoint")
        elif self.motion_type == MotionType.JOINT:
            if self.joint_waypoint is None:
                raise ValueError("MotionStep of type JOINT requires an explicit joint_waypoint")
            if self.waypoint is not None:
                raise ValueError("MotionStep of type JOINT cannot accept a Cartesian waypoint (ambiguous target)")
            if len(self.joint_waypoint.joints_deg) != 6:
                raise ValueError(f"MotionStep of type JOINT requires 6 joint angles, got {len(self.joint_waypoint.joints_deg)}")
        elif self.motion_type == MotionType.GRIPPER:
            if self.gripper_command is None:
                raise ValueError("MotionStep of type GRIPPER requires a gripper_command")
            if self.waypoint is not None or self.joint_waypoint is not None:
                raise ValueError("MotionStep of type GRIPPER cannot accept movement waypoints")
        elif self.motion_type == MotionType.WAIT:
            if self.wait_duration_s is None or self.wait_duration_s < 0.0:
                raise ValueError("MotionStep of type WAIT requires a non-negative wait_duration_s")
            if self.waypoint is not None or self.joint_waypoint is not None:
                raise ValueError("MotionStep of type WAIT cannot accept movement waypoints")

        # Freeze metadata
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))

    @property
    def target(self) -> Optional[Any]:
        """Convenience property returning the active target waypoint (Cartesian or Joint)."""
        return self.waypoint if self.waypoint is not None else self.joint_waypoint


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
        # Freeze metadata
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))

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


# Canonical alias for resolved motion plans
ResolvedMotionPlan = MotionPlan
