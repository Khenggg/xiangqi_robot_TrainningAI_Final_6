"""
Canonical Robot Backend Protocol and State Abstraction.

Defines the interface for all robot execution backends (physical RPC, virtual simulation, mock).
Provides thread-safe state snapshots and motion contracts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


@dataclass(frozen=True)
class RobotStateSnapshot:
    """
    Immutable thread-safe snapshot of robot state at a given timestamp.
    """
    robot_model: str                    # "FR3", "FR5", etc.
    connected: bool
    motion_state: str                   # "IDLE", "MOVING", "ERROR", "DISCONNECTED"
    joints_deg: List[float]             # 6 joint angles in degrees
    flange_pose_mm_deg: List[float]     # [X, Y, Z (mm), Rx, Ry, Rz (deg)]
    tcp_pose_mm_deg: List[float]        # [X, Y, Z (mm), Rx, Ry, Rz (deg)]
    gripper_closed: bool
    timestamp: float                    # Unix timestamp
    last_error: Optional[str] = None
    trajectory_stage: Optional[str] = None  # "PREPOSITION", "LIFT", "TRANSIT", "LAND", "COMPLETE", etc.
    placement_version: int = 1


class RobotBackend(ABC):
    """
    Abstract Base Class / Protocol for Robot Backends.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Connect to robot controller (virtual or physical)."""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from robot controller."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if currently connected."""
        pass

    @abstractmethod
    def get_state_snapshot(self) -> RobotStateSnapshot:
        """Return immutable, thread-safe snapshot of current authoritative state."""
        pass

    @abstractmethod
    def move_joint(
        self,
        target_joints_deg: Sequence[float],
        speed_factor: Optional[float] = None,
    ) -> bool:
        """
        Execute joint-space motion (MoveJ) to target angles.
        Interpolates smoothly in joint space.
        """
        pass

    @abstractmethod
    def move_cartesian(
        self,
        target_pose_mm_deg: Sequence[float],
        speed_factor: Optional[float] = None,
        samples: int = 20,
    ) -> bool:
        """
        Execute Cartesian-space linear motion (MoveL) to target end-effector pose.
        Samples the Cartesian path and verifies IK at every intermediate waypoint.
        """
        pass

    @abstractmethod
    def set_gripper(self, closed: bool) -> bool:
        """Command gripper state (True=closed/grip, False=open/release)."""
        pass

    @abstractmethod
    def stop(self) -> bool:
        """Emergency stop / halt current motion."""
        pass
