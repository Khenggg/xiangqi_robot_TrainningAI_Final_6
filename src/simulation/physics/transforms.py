"""
Coordinate transformation and spatial rotation utilities for simulation physics.

Supports conversions between robot_base (authoritative physics frame)
and 3d_world (Three.js visualization frame) loaded dynamically from
the canonical source:
    shared/virtual_fr3_scene.json

All quaternions follow the PyBullet / Three.js convention: [x, y, z, w].
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union
import numpy as np


@dataclass(frozen=True)
class SceneTransform:
    """Canonical spatial transformation between robot_base and 3d_world."""
    rotation_matrix: np.ndarray  # 3x3 float
    translation_m: np.ndarray    # (3,) float

    def __post_init__(self):
        R = np.asarray(self.rotation_matrix, dtype=float)
        t = np.asarray(self.translation_m, dtype=float)
        if R.shape != (3, 3) or not np.all(np.isfinite(R)):
            raise ValueError(f"Invalid rotation_matrix shape {R.shape} or non-finite values")
        if t.shape != (3,) or not np.all(np.isfinite(t)):
            raise ValueError(f"Invalid translation_m shape {t.shape} or non-finite values")
        identity_error = float(np.max(np.abs(R.T @ R - np.eye(3))))
        if identity_error > 1e-4:
            raise ValueError(f"Rotation matrix is not orthonormal: max |R^T R - I| = {identity_error:.4e}")
        det = float(np.linalg.det(R))
        if abs(det - 1.0) > 1e-3:
            raise ValueError(f"Rotation matrix determinant {det:.4f} != +1.0 (chirality violation)")
        object.__setattr__(self, "rotation_matrix", R)
        object.__setattr__(self, "translation_m", t)


DEFAULT_SCENE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "shared"
    / "virtual_fr3_scene.json"
)

_CACHED_SCENE_TRANSFORM: Optional[SceneTransform] = None


def get_canonical_scene_transform(
    scene_config_path: Optional[Union[str, Path]] = None,
    force_reload: bool = False,
) -> SceneTransform:
    """
    Load and strictly validate the canonical robot_base -> 3d_world transformation
    from shared/virtual_fr3_scene.json. Fails fast if file is missing or malformed.
    Caches the canonical transform for performance; custom paths do not poison the cache.
    """
    global _CACHED_SCENE_TRANSFORM
    use_default_path = scene_config_path is None
    if use_default_path and _CACHED_SCENE_TRANSFORM is not None and not force_reload:
        return _CACHED_SCENE_TRANSFORM

    target_path = DEFAULT_SCENE_PATH if use_default_path else Path(scene_config_path)
    if not target_path.is_file():
        raise FileNotFoundError(f"Canonical scene configuration not found at {target_path}")

    with open(target_path, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    if "robot_base_to_3d_world" not in cfg:
        raise ValueError(f"Missing 'robot_base_to_3d_world' block in {target_path}")

    trans_cfg = cfg["robot_base_to_3d_world"]
    if "rotation_matrix" not in trans_cfg:
        raise ValueError(f"Missing 'rotation_matrix' in robot_base_to_3d_world from {target_path}")
    if "translation_m" not in trans_cfg:
        raise ValueError(f"Missing 'translation_m' in robot_base_to_3d_world from {target_path}")

    R = np.array(trans_cfg["rotation_matrix"], dtype=float)
    t = np.array(trans_cfg["translation_m"], dtype=float)

    transform = SceneTransform(rotation_matrix=R, translation_m=t)
    if use_default_path:
        _CACHED_SCENE_TRANSFORM = transform

    return transform


# Explicit loader alias
load_scene_transform = get_canonical_scene_transform

# Canonical dynamic aliases populated from canonical scene configuration
DEFAULT_R_ROBOT_TO_WORLD = get_canonical_scene_transform().rotation_matrix
DEFAULT_TRANSLATION_ROBOT_TO_WORLD = get_canonical_scene_transform().translation_m


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


def rpy_to_rot_matrix(rpy_rad: Sequence[float]) -> np.ndarray:
    """Convert extrinsic Euler angles [roll, pitch, yaw] in radians to 3x3 rotation matrix."""
    r, p, y = float(rpy_rad[0]), float(rpy_rad[1]), float(rpy_rad[2])
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)

    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]], dtype=float)
    Ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]], dtype=float)
    Rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    return Rz @ Ry @ Rx


def rpy_deg_to_quat(rpy_deg: Sequence[float]) -> np.ndarray:
    """Convert extrinsic Euler angles [rx, ry, rz] in degrees to quaternion [x, y, z, w]."""
    rpy_rad = [math.radians(float(v)) for v in rpy_deg]
    R = rpy_to_rot_matrix(rpy_rad)
    return rot_matrix_to_quat(R)


def transform_point_robot_to_world(
    p_robot: Sequence[float],
    R: Optional[np.ndarray] = None,
    t: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """
    Transform 3D position from robot_base to 3d_world.
    P_world = R * P_robot + t
    """
    if R is None or t is None:
        trans_cfg = get_canonical_scene_transform()
        rot = trans_cfg.rotation_matrix if R is None else np.asarray(R, dtype=float)
        trans = trans_cfg.translation_m if t is None else np.asarray(t, dtype=float)
    else:
        rot = np.asarray(R, dtype=float)
        trans = np.asarray(t, dtype=float)
    return rot @ np.asarray(p_robot, dtype=float) + trans


def transform_quat_robot_to_world(
    q_robot: Sequence[float],
    R: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Transform orientation quaternion [x, y, z, w] from robot_base to 3d_world.
    R_world = R * R_robot
    """
    rot = get_canonical_scene_transform().rotation_matrix if R is None else np.asarray(R, dtype=float)
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
