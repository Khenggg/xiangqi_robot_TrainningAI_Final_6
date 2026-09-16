"""
Physical simulation state enums, results, and immutable snapshot models.
"""

from dataclasses import asdict, dataclass
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class PiecePhysicalState(str, Enum):
    """Physical state of a rigid body Xiangqi piece."""
    ON_BOARD = "ON_BOARD"
    ATTACHED_TO_GRIPPER = "ATTACHED_TO_GRIPPER"
    FALLING = "FALLING"
    SETTLING = "SETTLING"
    RESTING = "RESTING"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"


class GraspStatus(str, Enum):
    """Result status for deterministic geometric grasp attempt."""
    SUCCESS = "SUCCESS"
    NO_CANDIDATE = "NO_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"
    ALREADY_ATTACHED = "ALREADY_ATTACHED"
    INVALID_GRIPPER_STATE = "INVALID_GRIPPER_STATE"


@dataclass(frozen=True)
class GraspResult:
    """Structured result of a grasp attempt."""
    success: bool
    status: GraspStatus
    piece_id: Optional[str] = None
    distance_m: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class PieceSnapshot:
    """Immutable snapshot of a single piece's physical state."""
    id: str
    side: str
    type: str

    # Robot base coordinates (physics authority)
    position_robot_base_m: List[float]
    orientation_quaternion_robot_base: List[float]  # [x, y, z, w]

    # Three.js 3D world coordinates (visualization mapping)
    position_3d_world_m: List[float]
    orientation_quaternion_3d_world: List[float]    # [x, y, z, w]

    # Velocities
    linear_velocity_m_s: List[float]
    angular_velocity_rad_s: List[float]

    # Simulation metrics
    physical_state: str
    attached: bool
    tilt_deg: float
    col_float: float
    row_float: float
    nearest_col: int
    nearest_row: int
    distance_to_nearest_intersection_m: float

    @property
    def is_grasped(self) -> bool:
        return self.attached

    @property
    def status(self) -> str:
        return self.physical_state

    @property
    def pose_world(self) -> List[float]:
        return self.position_3d_world_m

    @property
    def orientation_quat_world(self) -> List[float]:
        return self.orientation_quaternion_3d_world

    @property
    def pose_robot(self) -> List[float]:
        return self.position_robot_base_m

    @property
    def orientation_quat_robot(self) -> List[float]:
        return self.orientation_quaternion_robot_base

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pose_world"] = list(self.position_3d_world_m)
        d["orientation_quat_world"] = list(self.orientation_quaternion_3d_world)
        d["pose_robot"] = list(self.position_robot_base_m)
        d["orientation_quat_robot"] = list(self.orientation_quaternion_robot_base)
        d["is_grasped"] = self.attached
        d["status"] = self.physical_state
        return d


@dataclass(frozen=True)
class WorldStateSnapshot:
    """
    Authoritative snapshot of the entire virtual physical environment.
    """
    timestamp: float
    simulation_time: float
    gripper: Dict[str, Any]
    pieces: List[PieceSnapshot]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "world_state",
            "timestamp": self.timestamp,
            "simulation_time": round(self.simulation_time, 4),
            "gripper": self.gripper,
            "pieces": [p.to_dict() for p in self.pieces],
        }


@dataclass(frozen=True)
class DropEvent:
    """
    Evidence record for a force-drop event during simulation.
    Captures exact robot motion state, release position, release velocity, and progress.
    """
    triggered: bool
    timestamp: float
    sim_time: float
    robot_motion_state: str
    release_position: List[float]
    release_linear_velocity: List[float]
    release_angular_velocity: List[float]
    attached_piece_id: Optional[str]
    trajectory_progress: float
    release_speed: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
