"""
Motion Contracts for Xiangqi Robot motion planning and execution.

Defines immutable Cartesian and Joint waypoints, motion types, and gripper commands
decoupled from specific robot backend implementations (FAIRINO vs PyBullet).
"""

from dataclasses import dataclass, field
from enum import Enum, auto
import math
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from src.motion.stages import MotionStage


class MotionType(Enum):
    """
    Desired mechanical behavior for a motion step.
    
    Translates later into backend-specific primitives (e.g. MoveL vs MoveJ in FAIRINO,
    or Cartesian vs joint trajectory planning in PyBullet).
    """
    CARTESIAN_LINEAR = auto()
    """Linear Cartesian interpolation (MoveL) maintaining constant tool orientation."""

    CARTESIAN_POINT = auto()
    """Point-to-point Cartesian move where intermediate path geometry is unconstrained."""

    JOINT = auto()
    """Direct joint-space motion interpolation."""

    GRIPPER = auto()
    """End-effector actuation without arm movement."""

    WAIT = auto()
    """Temporal dwell (e.g., settling after piece placement)."""

    VERIFY = auto()
    """Non-actuating predicate evaluation (e.g., payload clearance verification)."""


class GripperCommand(Enum):
    """
    Backend-neutral semantic command for end-effector actuation.
    
    Contains NO knowledge of Tool Digital Outputs (DO0, DO1), relays,
    pulse widths, or low-level pneumatic valve timings.
    """
    OPEN = auto()
    """Open gripper fingers to release payload or prepare for grasp."""

    CLOSE = auto()
    """Close gripper fingers to grasp payload."""

    SAFE_IDLE = auto()
    """De-energize or set gripper to safe unpowered resting state."""


@dataclass(frozen=True)
class MotionWaypoint:
    """
    Immutable value object representing a 6-DOF Cartesian waypoint.
    
    Attributes:
        position_mm: 3D coordinates (X, Y, Z) in millimeters relative to robot base.
        orientation_deg: 3D Euler angles (Rx, Ry, Rz) in degrees relative to robot base.
        stage: The functional lifecycle stage associated with this waypoint.
        motion_type: Desired motion interpolation type (default CARTESIAN_LINEAR).
        speed_factor: Relative execution speed factor (1.0 = nominal, > 0.0).
        tolerance_mm: Optional spatial arrival tolerance corridor in millimeters.
        label: Human-readable diagnostic description of this waypoint.
        metadata: Read-only mapping of auxiliary domain context.
    """
    position_mm: Tuple[float, float, float]
    orientation_deg: Tuple[float, float, float]
    stage: MotionStage
    motion_type: MotionType = MotionType.CARTESIAN_LINEAR
    speed_factor: float = 1.0
    tolerance_mm: Optional[float] = None
    label: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Disallow ambiguous Cartesian waypoint with JOINT motion type
        if self.motion_type == MotionType.JOINT:
            raise ValueError(
                "MotionWaypoint represents Cartesian targets (X, Y, Z, Rx, Ry, Rz) and cannot "
                "use MotionType.JOINT. Use JointWaypoint for explicit joint-space targets."
            )

        # Validate coordinate dimensionality
        if len(self.position_mm) != 3:
            raise ValueError(f"position_mm must be a 3-tuple (X, Y, Z), got {self.position_mm}")
        if len(self.orientation_deg) != 3:
            raise ValueError(f"orientation_deg must be a 3-tuple (Rx, Ry, Rz), got {self.orientation_deg}")
        if self.speed_factor <= 0.0:
            raise ValueError(f"speed_factor must be positive, got {self.speed_factor}")

        # Ensure elements are floats
        object.__setattr__(
            self,
            "position_mm",
            tuple(float(v) for v in self.position_mm),
        )
        object.__setattr__(
            self,
            "orientation_deg",
            tuple(float(v) for v in self.orientation_deg),
        )
        # Deep defensive copy and freeze metadata with MappingProxyType
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))

    @property
    def pose_mm_deg(self) -> Tuple[float, float, float, float, float, float]:
        """Return canonical 6-tuple [X, Y, Z (mm), Rx, Ry, Rz (deg)]."""
        return (
            self.position_mm[0],
            self.position_mm[1],
            self.position_mm[2],
            self.orientation_deg[0],
            self.orientation_deg[1],
            self.orientation_deg[2],
        )

    @classmethod
    def from_pose_sequence(
        cls,
        pose_6d: Sequence[float],
        stage: MotionStage,
        motion_type: MotionType = MotionType.CARTESIAN_LINEAR,
        speed_factor: float = 1.0,
        tolerance_mm: Optional[float] = None,
        label: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "MotionWaypoint":
        """Convenience constructor from a 6-element sequence [X, Y, Z, Rx, Ry, Rz]."""
        if len(pose_6d) != 6:
            raise ValueError(f"pose_6d must contain exactly 6 elements, got {len(pose_6d)}")
        return cls(
            position_mm=(float(pose_6d[0]), float(pose_6d[1]), float(pose_6d[2])),
            orientation_deg=(float(pose_6d[3]), float(pose_6d[4]), float(pose_6d[5])),
            stage=stage,
            motion_type=motion_type,
            speed_factor=speed_factor,
            tolerance_mm=tolerance_mm,
            label=label,
            metadata=metadata or {},
        )


# Canonical alias for Cartesian waypoints
CartesianWaypoint = MotionWaypoint


@dataclass(frozen=True)
class JointWaypoint:
    """
    Immutable value object representing an explicit 6-DOF joint-space waypoint.
    
    Attributes:
        joints_deg: 6 joint angles (J1..J6) in degrees.
        stage: The functional lifecycle stage associated with this waypoint.
        motion_type: Desired motion interpolation type (default JOINT).
        speed_factor: Relative execution speed factor (1.0 = nominal, > 0.0).
        tolerance_deg: Optional joint arrival tolerance in degrees.
        label: Human-readable diagnostic description of this waypoint.
        metadata: Read-only mapping of auxiliary domain context.
    """
    joints_deg: Tuple[float, float, float, float, float, float]
    stage: MotionStage
    motion_type: MotionType = MotionType.JOINT
    speed_factor: float = 1.0
    tolerance_deg: Optional[float] = None
    label: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate motion type
        if self.motion_type != MotionType.JOINT:
            raise ValueError(
                f"JointWaypoint must use MotionType.JOINT, got {self.motion_type}"
            )

        # Validate joint count (FR3 has exactly 6 joints)
        if len(self.joints_deg) != 6:
            raise ValueError(
                f"JointWaypoint requires exactly 6 joint values (J1..J6), got {len(self.joints_deg)}: {self.joints_deg}"
            )
        if self.speed_factor <= 0.0:
            raise ValueError(f"speed_factor must be positive, got {self.speed_factor}")

        # Ensure elements are floats
        object.__setattr__(
            self,
            "joints_deg",
            tuple(float(v) for v in self.joints_deg),
        )
        # Deep defensive copy and freeze metadata with MappingProxyType
        meta_dict = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta_dict))

    @property
    def joints_rad(self) -> Tuple[float, float, float, float, float, float]:
        """Return 6 joint angles converted to radians."""
        return tuple(math.radians(v) for v in self.joints_deg)

    @classmethod
    def from_sequence(
        cls,
        joints_6d: Sequence[float],
        stage: MotionStage,
        speed_factor: float = 1.0,
        tolerance_deg: Optional[float] = None,
        label: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "JointWaypoint":
        """Convenience constructor from a 6-element joint sequence in degrees."""
        if len(joints_6d) != 6:
            raise ValueError(f"joints_6d must contain exactly 6 elements, got {len(joints_6d)}")
        return cls(
            joints_deg=tuple(float(v) for v in joints_6d),  # type: ignore
            stage=stage,
            speed_factor=speed_factor,
            tolerance_deg=tolerance_deg,
            label=label,
            metadata=metadata or {},
        )
