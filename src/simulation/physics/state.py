"""
Physical simulation state enums, results, and immutable snapshot models.
"""

from dataclasses import asdict, dataclass
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Tuple


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
    PARTIAL = "PARTIAL"
    LIFT_FAILED_AFTER_GRASP = "LIFT_FAILED_AFTER_GRASP"


@dataclass(frozen=True)
class GraspResult:
    """Structured result of a grasp attempt."""
    success: bool
    status: GraspStatus
    piece_id: Optional[str] = None
    distance_m: float = 0.0
    reason: str = ""


class PickResult(dict):
    """Structured result for pick_piece operation with backwards-compatible dictionary and boolean behavior."""
    def __init__(
        self,
        success: bool,
        status: str,
        reason: Optional[str] = None,
        error: Optional[str] = None,
        piece_id: Optional[str] = None,
    ):
        err = error or reason
        super().__init__(success=success, status=str(status), reason=err, error=err, piece_id=piece_id)

    def __bool__(self) -> bool:
        return bool(self.get("success", False))

    @property
    def success(self) -> bool:
        return bool(self.get("success", False))

    @property
    def status(self) -> str:
        return str(self.get("status", ""))

    @property
    def reason(self) -> Optional[str]:
        return self.get("reason") or self.get("error")

    @property
    def error(self) -> Optional[str]:
        return self.get("error") or self.get("reason")

    @property
    def piece_id(self) -> Optional[str]:
        return self.get("piece_id")


class PlaceResult(dict):
    """Structured result for place_piece operation with backwards-compatible boolean behavior."""
    def __init__(
        self,
        success: bool,
        status: str,
        reason: Optional[str] = None,
        error: Optional[str] = None,
        piece_id: Optional[str] = None,
        target_cell: Optional[Tuple[int, int]] = None,
    ):
        err = error or reason
        super().__init__(success=success, status=str(status), reason=err, error=err, piece_id=piece_id, target_cell=target_cell)

    def __bool__(self) -> bool:
        return bool(self.get("success", False))

    @property
    def success(self) -> bool:
        return bool(self.get("success", False))

    @property
    def status(self) -> str:
        return str(self.get("status", ""))

    @property
    def reason(self) -> Optional[str]:
        return self.get("reason") or self.get("error")

    @property
    def error(self) -> Optional[str]:
        return self.get("error") or self.get("reason")

    @property
    def piece_id(self) -> Optional[str]:
        return self.get("piece_id")

    @property
    def target_cell(self) -> Optional[Tuple[int, int]]:
        return self.get("target_cell")


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
    release_gripper_position: Optional[List[float]] = None
    release_gripper_orientation: Optional[List[float]] = None
    release_piece_orientation: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ServiceSafetyReport:
    """
    Authoritative physical safety report for SERVICE_SAFE and Board Adjustment Readiness.
    Evaluates articulated link clearances, gripper state, attachments, and robot conditioning.
    """
    service_safe: bool
    robot_connected: bool
    robot_idle: bool
    trajectory_idle: bool
    gripper_open: bool
    piece_attached: bool
    links_clear: bool
    gripper_clear: bool
    min_board_clearance_mm: float
    closest_link_or_proxy: str
    min_joint_margin_deg: float
    condition_number: float
    service_pose_match: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_safe": self.service_safe,
            "robot_connected": self.robot_connected,
            "robot_idle": self.robot_idle,
            "trajectory_idle": self.trajectory_idle,
            "gripper_open": self.gripper_open,
            "piece_attached": self.piece_attached,
            "links_clear": self.links_clear,
            "gripper_clear": self.gripper_clear,
            "min_board_clearance_mm": round(self.min_board_clearance_mm, 2),
            "closest_link_or_proxy": self.closest_link_or_proxy,
            "min_joint_margin_deg": round(self.min_joint_margin_deg, 2),
            "condition_number": round(self.condition_number, 2),
            "service_pose_match": self.service_pose_match,
            "reasons": list(self.reasons),
        }

