"""
Virtual physical simulation package for Xiangqi Robot.
"""

from src.simulation.physics.state import (
    GraspResult,
    GraspStatus,
    DropEvent,
    PiecePhysicalState,
    PieceSnapshot,
    WorldStateSnapshot,
)
from src.simulation.physics.transforms import (
    continuous_board_coord,
    nearest_intersection_metrics,
    quat_to_rot_matrix,
    rot_matrix_to_quat,
    tilt_angle_deg,
    transform_point_robot_to_world,
    transform_quat_robot_to_world,
)
from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.gripper import VirtualGripper
from src.simulation.physics.world import VirtualPhysicalWorld

__all__ = [
    "VirtualPhysicalWorld",
    "XiangqiPieceBody",
    "VirtualGripper",
    "PiecePhysicalState",
    "GraspStatus",
    "GraspResult",
    "DropEvent",
    "PieceSnapshot",
    "WorldStateSnapshot",
    "continuous_board_coord",
    "nearest_intersection_metrics",
    "quat_to_rot_matrix",
    "rot_matrix_to_quat",
    "tilt_angle_deg",
    "transform_point_robot_to_world",
    "transform_quat_robot_to_world",
]
