"""
Coordinate transformation and spatial rotation utilities for simulation physics.

Supports conversions between robot_base (authoritative physics frame)
and 3d_world (Three.js visualization frame) using the canonical extrinsics:
    R_robot_to_world = [[0, -1, 0], [0, 0, 1], [-1, 0, 0]]
    translation = [0, 0, 0]

All quaternions follow the PyBullet / Three.js convention: [x, y, z, w].
"""

import math
from typing import Optional, Sequence, Tuple
import numpy as np

# Canonical rotation matrix from shared/virtual_fr3_scene.json
DEFAULT_R_ROBOT_TO_WORLD = np.array([
    [0.0, -1.0, 0.0],
    [0.0, 0.0, 1.0],
    [-1.0, 0.0, 0.0],
], dtype=float)

DEFAULT_TRANSLATION_ROBOT_TO_WORLD = np.array([0.0, 0.0, 0.0], dtype=float)


def quat_to_rot_matrix(q: Sequence[float]) -> np.ndarray:
    """
    Convert quaternion [x, y, z, w] to a 3x3 orthonormal rotation matrix.
    """
    x, y, z, w = q
    norm_sq = x * x + y * y + z * z + w * w
    if norm_sq < 1e-12:
        return np.eye(3, dtype=float)
    s = 2.0 / norm_sq

    return np.array([
        [1.0 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1.0 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1.0 - s * (x * x + y * y)],
    ], dtype=float)


def rot_matrix_to_quat(R: np.ndarray) -> np.ndarray:
    """
    Convert a 3x3 orthonormal rotation matrix to quaternion [x, y, z, w].
    Uses a numerically stable branch selection based on trace and diagonals.
    """
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    q = np.array([x, y, z, w], dtype=float)
    norm = np.linalg.norm(q)
    if norm > 1e-12:
        q /= norm
    return q


def transform_point_robot_to_world(
    p_robot: Sequence[float],
    R: Optional[np.ndarray] = None,
    t: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """
    Transform 3D position from robot_base to 3d_world.
    P_world = R * P_robot + t
    """
    rot = DEFAULT_R_ROBOT_TO_WORLD if R is None else np.asarray(R, dtype=float)
    trans = DEFAULT_TRANSLATION_ROBOT_TO_WORLD if t is None else np.asarray(t, dtype=float)
    return rot @ np.asarray(p_robot, dtype=float) + trans


def transform_quat_robot_to_world(
    q_robot: Sequence[float],
    R: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Transform orientation quaternion [x, y, z, w] from robot_base to 3d_world.
    R_world = R * R_robot
    """
    rot = DEFAULT_R_ROBOT_TO_WORLD if R is None else np.asarray(R, dtype=float)
    M_robot = quat_to_rot_matrix(q_robot)
    M_world = rot @ M_robot
    return rot_matrix_to_quat(M_world)


def tilt_angle_deg(q_robot: Sequence[float]) -> float:
    """
    Calculate tilt angle in degrees between local cylinder axis (local +Z)
    and authoritative world vertical (+Z in robot_base).
    
    Upright piece -> 0.0 deg
    Lying on side -> ~90.0 deg
    Upside down   -> 180.0 deg
    """
    M = quat_to_rot_matrix(q_robot)
    # Local Z vector in robot base is M[:, 2]
    cos_angle = float(np.clip(M[2, 2], -1.0, 1.0))
    return math.degrees(math.acos(cos_angle))


def continuous_board_coord(
    p_robot: Sequence[float],
    grid_origin_robot: Sequence[float],
    col_spacing_m: float = 0.040,
    row_spacing_m: float = 0.040,
) -> Tuple[float, float]:
    """
    Derive continuous floating-point (col, row) on the board from a robot_base point.
    In robot_base:
        x0 is row 0, row increases along -X -> row = (x0 - x) / row_spacing
        y0 is col 0, col increases along +Y -> col = (y - y0) / col_spacing
    """
    x0, y0, _ = grid_origin_robot
    x, y, _ = p_robot
    col_float = (float(y) - float(y0)) / float(col_spacing_m)
    row_float = (float(x0) - float(x)) / float(row_spacing_m)
    return col_float, row_float


def nearest_intersection_metrics(
    col_float: float,
    row_float: float,
    p_robot: Sequence[float],
    grid_origin_robot: Sequence[float],
    col_spacing_m: float = 0.040,
    row_spacing_m: float = 0.040,
    max_cols: int = 9,
    max_rows: int = 10,
) -> Tuple[int, int, float]:
    """
    Calculate nearest intersection (nearest_col, nearest_row) and distance in meters.
    Clamps nearest index to [0, max-1] only for nearest target calculation.
    """
    nearest_c = max(0, min(max_cols - 1, int(round(col_float))))
    nearest_r = max(0, min(max_rows - 1, int(round(row_float))))

    x0, y0, z0 = grid_origin_robot
    target_x = x0 - nearest_r * row_spacing_m
    target_y = y0 + nearest_c * col_spacing_m

    # Horizontal distance in board XY plane
    dx = float(p_robot[0]) - target_x
    dy = float(p_robot[1]) - target_y
    dist_m = math.hypot(dx, dy)

    return nearest_c, nearest_r, dist_m
