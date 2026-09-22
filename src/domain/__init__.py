"""Domain package for Xiangqi Robot core entities and value objects."""

from src.domain.geometry import (
    BoardGeometry,
    PieceGeometry,
    BoardConvention,
    PhysicalGeometry,
    get_physical_geometry,
)
from src.domain.board_pose import (
    BoardCell,
    BoardPlacementState,
    compute_rotation_matrix,
    rot_matrix_to_quat,
    canonical_cell_to_robot_xyz_m,
    find_nearest_cell,
    DEFAULT_BOARD_YAW_DEG,
)
from src.domain.board_pose_provider import (
    BoardPoseProvider,
    FixedBoardPoseProvider,
    PhysicalTeachingPointBoardPoseProvider,
    BoardCalibrationResult,
    calibrate_board_from_teaching_points,
)

__all__ = [
    "BoardGeometry",
    "PieceGeometry",
    "BoardConvention",
    "PhysicalGeometry",
    "get_physical_geometry",
    "BoardCell",
    "BoardPlacementState",
    "compute_rotation_matrix",
    "rot_matrix_to_quat",
    "canonical_cell_to_robot_xyz_m",
    "find_nearest_cell",
    "DEFAULT_BOARD_YAW_DEG",
    "BoardPoseProvider",
    "FixedBoardPoseProvider",
    "PhysicalTeachingPointBoardPoseProvider",
    "BoardCalibrationResult",
    "calibrate_board_from_teaching_points",
]
