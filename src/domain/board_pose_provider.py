"""
Domain module for Board Pose Providers.

Decouples board localization and calibration from motion execution.
Allows switching between fixed nominal pose, calibrated physical teaching points,
and future vision-based dynamic board tracking.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import logging
import math
import numpy as np

from src.domain.board_pose import BoardPlacementState, compute_rotation_matrix
from src.domain.geometry import (
    CANONICAL_GRID_WIDTH_MM,
    CANONICAL_GRID_LENGTH_MM,
    CANONICAL_BOARD_THICKNESS_MM,
    CANONICAL_GRID_DIAGONAL_MM,
    CANONICAL_CELL_SPACING_MM,
    get_physical_geometry,
)

logger = logging.getLogger(__name__)

# Canonical single source of truth dimensions derived from shared/physical_geometry.json
CANONICAL_WIDTH_MM: float = CANONICAL_GRID_WIDTH_MM       # col 0 to col 8 (8 * 40mm = 320.0 mm)
CANONICAL_LENGTH_MM: float = CANONICAL_GRID_LENGTH_MM     # row 0 to row 9 (9 * 40mm = 360.0 mm)
CANONICAL_THICKNESS_MM: float = CANONICAL_BOARD_THICKNESS_MM  # 10.5 mm
CANONICAL_DIAGONAL_MM: float = CANONICAL_GRID_DIAGONAL_MM     # ~481.66 mm
CANONICAL_CELL_SPACING_MM: float = CANONICAL_CELL_SPACING_MM  # 40.0 mm


@dataclass(frozen=True)
class TeachingPointObservation:
    """
    Standardized observation of a robotic calibration teaching point.
    Preserves frame metadata (tool_id, user/work-object frame) from FAIRINO SDK.
    """
    xyz_mm: List[float]
    rpy_deg: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    tool_id: Optional[int] = None
    user_or_wobj_id: Optional[int] = None
    raw: Any = None


def parse_teaching_point_observation(val: Any) -> TeachingPointObservation:
    """
    Parse arbitrary teaching point data structures into TeachingPointObservation with frame metadata.

    FAIRINO SDK representation (robot_sdk_core.py:3947):
      data = [x, y, z, rx, ry, rz, j1, j2, j3, j4, j5, j6, tool, wobj, speed, acc, e1, e2, e3, e4]
      data[12]: tool ID (int)
      data[13]: user/wobj ID (int, 0 = robot base coordinate system)
    """
    if isinstance(val, TeachingPointObservation):
        return val

    tool_id: Optional[int] = None
    user_or_wobj_id: Optional[int] = None
    rpy_deg: List[float] = [0.0, 0.0, 0.0]
    raw_val = val

    if isinstance(val, dict):
        if "tool" in val or "tool_id" in val:
            raw_t = val.get("tool", val.get("tool_id"))
            tool_id = int(float(str(raw_t).strip())) if raw_t is not None else None
        if "wobj" in val or "user" in val or "user_or_wobj_id" in val or "user_frame_id" in val:
            raw_u = val.get("wobj", val.get("user", val.get("user_or_wobj_id", val.get("user_frame_id"))))
            user_or_wobj_id = int(float(str(raw_u).strip())) if raw_u is not None else None
        if "pose" in val:
            val = val["pose"]
        elif "xyz" in val:
            val = val["xyz"]

    if hasattr(val, "pose"):
        val = getattr(val, "pose")

    if hasattr(val, "x") and hasattr(val, "y") and hasattr(val, "z"):
        val = [getattr(val, "x"), getattr(val, "y"), getattr(val, "z")]

    if not isinstance(val, (list, tuple, np.ndarray)) or len(val) < 3:
        raise ValueError(f"Teaching point data must contain at least 3 coordinates, got {val}")

    x, y, z = float(val[0]), float(val[1]), float(val[2])
    if math.isnan(x) or math.isnan(y) or math.isnan(z) or math.isinf(x) or math.isinf(y) or math.isinf(z):
        raise ValueError(f"Teaching point contains NaN or Inf coordinates: {[x, y, z]}")

    if len(val) >= 6:
        rpy_deg = [float(val[3]), float(val[4]), float(val[5])]

    # Extract tool & wobj if 20-element or >=14 element SDK list
    if len(val) >= 14:
        try:
            if tool_id is None:
                tool_id = int(float(str(val[12]).strip()))
            if user_or_wobj_id is None:
                user_or_wobj_id = int(float(str(val[13]).strip()))
        except (ValueError, TypeError):
            pass

    return TeachingPointObservation(
        xyz_mm=[x, y, z],
        rpy_deg=rpy_deg,
        tool_id=tool_id,
        user_or_wobj_id=user_or_wobj_id,
        raw=raw_val,
    )


def extract_xyz_mm(val: Any) -> List[float]:
    """Extract [x, y, z] in mm from teaching point data structures."""
    obs = parse_teaching_point_observation(val)
    return list(obs.xyz_mm)


def rpy_deg_to_rot_matrix(rpy_deg: Sequence[float]) -> np.ndarray:
    """Convert extrinsic Euler angles [rx, ry, rz] in degrees to 3x3 rotation matrix (Rz @ Ry @ Rx)."""
    rx = math.radians(float(rpy_deg[0]))
    ry = math.radians(float(rpy_deg[1]))
    rz = math.radians(float(rpy_deg[2]))
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, math.cos(rx), -math.sin(rx)], [0.0, math.sin(rx), math.cos(rx)]], dtype=float)
    Ry = np.array([[math.cos(ry), 0.0, math.sin(ry)], [0.0, 1.0, 0.0], [-math.sin(ry), 0.0, math.cos(ry)]], dtype=float)
    Rz = np.array([[math.cos(rz), -math.sin(rz), 0.0], [math.sin(rz), math.cos(rz), 0.0], [0.0, 0.0, 1.0]], dtype=float)
    return Rz @ Ry @ Rx


@dataclass(frozen=True)
class BoardCalibrationProfile:
    """
    Semantic model defining the relationship between taught TCP and true board contact point.

    Mode A: tcp_to_board_contact_offset_mm = [0, 0, 0]
      Pointer contact tip is directly at the grid intersection on the board surface.
      provenance: 'CALIBRATED_POINTER_CONTACT'

    Mode B: known offset in tool frame or robot base frame.
      For tool frame: offset_robot = R_robot_from_tcp @ offset_tool
      p_board_ref_robot = p_tcp_robot + offset_robot

    CRITICAL: The canonical gripper length (150 mm) is NOT automatically a calibration contact offset.
    Calibration contact geometry is completely independent of runtime piece grasp TCP.
    """
    tcp_to_board_contact_offset_mm: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    offset_frame: str = "TOOL"  # "TOOL" or "ROBOT_BASE"
    provenance: str = "CALIBRATED_POINTER_CONTACT"
    description: str = "TCP contact point on board grid intersection"


@dataclass(frozen=True)
class BoardCalibrationTolerancePolicy:
    """
    Authoritative quality and safety tolerances for Xiangqi board calibration.
    Tightened specifically for Xiangqi geometry (cell spacing 40mm, piece diameter 22.5mm).
    """
    name: str = "INITIAL_PHYSICAL_CALIBRATION_TOLERANCE"
    max_dimension_error_warning_mm: float = 3.0
    max_dimension_error_hard_fail_mm: float = 5.0
    max_corner_residual_hard_fail_mm: float = 5.0
    max_rms_residual_warning_mm: float = 2.0
    max_rms_residual_hard_fail_mm: float = 3.0
    max_plane_residual_hard_fail_mm: float = 3.0
    max_edge_length_diff_mm: float = 5.0
    max_diagonal_diff_mm: float = 8.0
    min_normal_z: float = 0.707  # Max 45 deg tilt from upward +Z


@dataclass(frozen=True)
class BoardCalibrationResult:
    """Diagnostic and quality metrics from physical board pose calibration."""
    success: bool
    state: Optional[BoardPlacementState]
    error_r1_mm: float
    error_r2_mm: float
    error_r3_mm: float
    error_r4_mm: float
    rms_error_mm: float
    max_error_mm: float
    measured_width_mm: float
    measured_length_mm: float
    error_message: Optional[str] = None
    teaching_points: Optional[Dict[str, List[float]]] = None
    max_plane_residual_mm: float = 0.0
    calibration_profile: Optional[BoardCalibrationProfile] = None
    tolerance_policy: Optional[BoardCalibrationTolerancePolicy] = None
    warnings: List[str] = field(default_factory=list)
    calibration_log: Optional[str] = None

    @property
    def residuals(self) -> Dict[str, float]:
        return {
            "R1": self.error_r1_mm,
            "R2": self.error_r2_mm,
            "R3": self.error_r3_mm,
            "R4": self.error_r4_mm,
            "RMS": self.rms_error_mm,
            "Max": self.max_error_mm,
        }

    @property
    def residuals_mm(self) -> Dict[str, float]:
        return self.residuals


def calibrate_board_from_teaching_points(
    teaching_points: Dict[str, Any],
    safe_transit_height_mm: float = 40.0,
    max_residual_mm: Optional[float] = None,
    max_rms_mm: Optional[float] = None,
    width_tolerance_mm: Optional[float] = None,
    length_tolerance_mm: Optional[float] = None,
    max_coplanar_z_diff_mm: Optional[float] = None,
    calibration_profile: Optional[BoardCalibrationProfile] = None,
    tolerance_policy: Optional[BoardCalibrationTolerancePolicy] = None,
) -> BoardCalibrationResult:
    """
    Perform rigid 3D calibration of the physical Xiangqi board from R1-R4 teaching points.

    R1: (row=0, col=0)
    R2: (row=0, col=8)
    R3: (row=9, col=8)
    R4: (row=9, col=0)

    Canonical Board-Local Geometry (meters, surface origin at grid center):
      u = (col - 4.0) * 0.040 m
      v = (row - 4.5) * 0.040 m
      R1: u=-0.160, v=-0.180, w=0.0
      R2: u=+0.160, v=-0.180, w=0.0
      R3: u=+0.160, v=+0.180, w=0.0
      R4: u=-0.160, v=+0.180, w=0.0
    """
    profile = calibration_profile or BoardCalibrationProfile()
    policy = tolerance_policy or BoardCalibrationTolerancePolicy()

    # Dynamic overrides for backward compatibility if explicitly provided
    dim_hard_fail_w = width_tolerance_mm if width_tolerance_mm is not None else policy.max_dimension_error_hard_fail_mm
    dim_hard_fail_l = length_tolerance_mm if length_tolerance_mm is not None else policy.max_dimension_error_hard_fail_mm
    rms_hard_fail = max_rms_mm if max_rms_mm is not None else policy.max_rms_residual_hard_fail_mm
    corner_hard_fail = max_residual_mm if max_residual_mm is not None else policy.max_corner_residual_hard_fail_mm
    plane_hard_fail = max_coplanar_z_diff_mm if max_coplanar_z_diff_mm is not None else policy.max_plane_residual_hard_fail_mm

    required_points = ["R1", "R2", "R3", "R4"]
    for pt in required_points:
        if pt not in teaching_points:
            return BoardCalibrationResult(
                success=False,
                state=None,
                error_r1_mm=float("inf"),
                error_r2_mm=float("inf"),
                error_r3_mm=float("inf"),
                error_r4_mm=float("inf"),
                rms_error_mm=float("inf"),
                max_error_mm=float("inf"),
                measured_width_mm=0.0,
                measured_length_mm=0.0,
                error_message=f"Missing required teaching point '{pt}' in observation dictionary",
                calibration_profile=profile,
                tolerance_policy=policy,
            )

    # 1. Parse observations into standardized TeachingPointObservation with frame metadata
    try:
        observations = {pt: parse_teaching_point_observation(teaching_points[pt]) for pt in required_points}
    except Exception as exc:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=0.0,
            measured_length_mm=0.0,
            error_message=f"Failed to parse teaching point coordinates: {exc}",
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # 2. Validate frame metadata consistency across R1-R4
    tools = {pt: observations[pt].tool_id for pt in required_points if observations[pt].tool_id is not None}
    if len(tools) > 1 and len(set(tools.values())) > 1:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=0.0,
            measured_length_mm=0.0,
            error_message=(
                f"Teaching point frame mismatch: "
                f"R1 tool={observations['R1'].tool_id}, R2 tool={observations['R2'].tool_id}, "
                f"R3 tool={observations['R3'].tool_id}, R4 tool={observations['R4'].tool_id}"
            ),
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    wobjs = {pt: observations[pt].user_or_wobj_id for pt in required_points if observations[pt].user_or_wobj_id is not None}
    if len(wobjs) > 1 and len(set(wobjs.values())) > 1:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=0.0,
            measured_length_mm=0.0,
            error_message=(
                f"Teaching point frame mismatch: "
                f"R1 wobj={observations['R1'].user_or_wobj_id}, R2 wobj={observations['R2'].user_or_wobj_id}, "
                f"R3 wobj={observations['R3'].user_or_wobj_id}, R4 wobj={observations['R4'].user_or_wobj_id}"
            ),
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # Validate that user frame is robot base frame (wobj 0 in FAIRINO)
    if any(w is not None and w != 0 for w in wobjs.values()):
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=0.0,
            measured_length_mm=0.0,
            error_message=(
                f"Teaching points are in user frame {list(wobjs.values())[0]} != 0 (robot base). "
                "FAIRINO base coordinate system (user frame 0) required for canonical board pose."
            ),
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # 3. Apply calibration contact profile offset (Mode A vs Mode B)
    contact_pts_mm = {}
    contact_offset = np.array(profile.tcp_to_board_contact_offset_mm, dtype=float)
    has_offset = bool(np.any(contact_offset != 0.0))

    for pt in required_points:
        p_tcp = np.array(observations[pt].xyz_mm, dtype=float)
        if has_offset:
            if profile.offset_frame.upper() == "TOOL":
                R_tcp = rpy_deg_to_rot_matrix(observations[pt].rpy_deg)
                offset_robot = R_tcp @ contact_offset
                p_contact = p_tcp + offset_robot
            else:  # ROBOT_BASE
                p_contact = p_tcp + contact_offset
            contact_pts_mm[pt] = p_contact
        else:
            contact_pts_mm[pt] = p_tcp

    p1_mm = contact_pts_mm["R1"]
    p2_mm = contact_pts_mm["R2"]
    p3_mm = contact_pts_mm["R3"]
    p4_mm = contact_pts_mm["R4"]

    pts_mm_dict = {pt: list(contact_pts_mm[pt]) for pt in required_points}

    # 4. Geometry and quadrilateral plausibility checks
    w_top = float(np.linalg.norm(p2_mm - p1_mm))
    w_bot = float(np.linalg.norm(p3_mm - p4_mm))
    measured_width = (w_top + w_bot) / 2.0

    l_left = float(np.linalg.norm(p4_mm - p1_mm))
    l_right = float(np.linalg.norm(p3_mm - p2_mm))
    measured_length = (l_left + l_right) / 2.0

    d1 = float(np.linalg.norm(p3_mm - p1_mm))
    d2 = float(np.linalg.norm(p4_mm - p2_mm))

    # Width edge symmetry
    diff_w = abs(w_top - w_bot)
    if diff_w > policy.max_edge_length_diff_mm:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            error_message=(
                f"Board width edge asymmetry too large: top={w_top:.1f} mm, bot={w_bot:.1f} mm "
                f"(diff={diff_w:.1f} mm > limit {policy.max_edge_length_diff_mm:.1f} mm)"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # Length edge symmetry
    diff_l = abs(l_left - l_right)
    if diff_l > policy.max_edge_length_diff_mm:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            error_message=(
                f"Board length edge asymmetry too large: left={l_left:.1f} mm, right={l_right:.1f} mm "
                f"(diff={diff_l:.1f} mm > limit {policy.max_edge_length_diff_mm:.1f} mm)"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # Diagonal symmetry
    diff_d = abs(d1 - d2)
    if diff_d > policy.max_diagonal_diff_mm:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            error_message=(
                f"Board diagonal asymmetry too large: R1-R3={d1:.1f} mm, R2-R4={d2:.1f} mm "
                f"(diff={diff_d:.1f} mm > limit {policy.max_diagonal_diff_mm:.1f} mm)"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # Width check
    width_error = abs(measured_width - CANONICAL_WIDTH_MM)
    if width_error > dim_hard_fail_w:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            error_message=(
                f"Board width mismatch: measured {measured_width:.1f} mm, "
                f"expected {CANONICAL_WIDTH_MM:.1f} mm (+/- {dim_hard_fail_w:.1f} mm)"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # Length check
    length_error = abs(measured_length - CANONICAL_LENGTH_MM)
    if length_error > dim_hard_fail_l:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            error_message=(
                f"Board length mismatch: measured {measured_length:.1f} mm, "
                f"expected {CANONICAL_LENGTH_MM:.1f} mm (+/- {dim_hard_fail_l:.1f} mm)"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # 5. True coplanarity check via point-to-plane orthogonal residuals (SVD plane fit & corner protrusion)
    P_meas_mm = np.array([p1_mm, p2_mm, p3_mm, p4_mm], dtype=float)
    p_center_mm = np.mean(P_meas_mm, axis=0)
    A_centered = P_meas_mm - p_center_mm

    _, _, Vt_plane = np.linalg.svd(A_centered)
    plane_normal = Vt_plane[-1]
    plane_normal_norm = np.linalg.norm(plane_normal)
    if plane_normal_norm > 1e-12:
        plane_normal /= plane_normal_norm

    plane_residuals_mm = np.abs(A_centered @ plane_normal)
    max_svd_residual = float(np.max(plane_residuals_mm))

    # Corner out-of-plane deviation (distance of each corner to the plane defined by other corners)
    n124 = np.cross(p2_mm - p1_mm, p4_mm - p1_mm)
    norm124 = np.linalg.norm(n124)
    dev_3 = float(abs(np.dot(p3_mm - p1_mm, n124)) / norm124) if norm124 > 1e-12 else 0.0

    n123 = np.cross(p2_mm - p1_mm, p3_mm - p2_mm)
    norm123 = np.linalg.norm(n123)
    dev_4 = float(abs(np.dot(p4_mm - p1_mm, n123)) / norm123) if norm123 > 1e-12 else 0.0

    n234 = np.cross(p3_mm - p2_mm, p4_mm - p3_mm)
    norm234 = np.linalg.norm(n234)
    dev_1 = float(abs(np.dot(p1_mm - p2_mm, n234)) / norm234) if norm234 > 1e-12 else 0.0

    n143 = np.cross(p4_mm - p1_mm, p3_mm - p4_mm)
    norm143 = np.linalg.norm(n143)
    dev_2 = float(abs(np.dot(p2_mm - p1_mm, n143)) / norm143) if norm143 > 1e-12 else 0.0

    max_corner_plane_dev = max(dev_1, dev_2, dev_3, dev_4)
    max_plane_residual = max(max_svd_residual, max_corner_plane_dev)

    if max_plane_residual > plane_hard_fail:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            max_plane_residual_mm=round(max_plane_residual, 3),
            error_message=(
                f"Board points non-coplanar: max point-to-plane residual {max_plane_residual:.2f} mm "
                f"> limit {plane_hard_fail:.1f} mm"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # 6. Convert contact points to meters for rigid SE(3) Kabsch estimation
    P_meas = P_meas_mm / 1000.0
    p_center_m = p_center_mm / 1000.0

    # Canonical corner coordinates in board-local frame (meters) centered at (0, 0, 0)
    P_can = np.array([
        [-0.160, -0.180, 0.0],  # R1 (row 0, col 0)
        [+0.160, -0.180, 0.0],  # R2 (row 0, col 8)
        [+0.160, +0.180, 0.0],  # R3 (row 9, col 8)
        [-0.160, +0.180, 0.0],  # R4 (row 9, col 0)
    ], dtype=float)

    P_meas_centered = P_meas - p_center_m
    H = P_can.T @ P_meas_centered

    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T

    # Enforce right-handed rotation SO(3)
    if np.linalg.det(R) < 0.0:
        Vt[-1, :] *= -1.0
        R = Vt.T @ U.T

    # Check that normal vector points upward (board surface facing +Z robot)
    normal_z = R[2, 2]
    if normal_z < policy.min_normal_z:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=float("inf"),
            error_r2_mm=float("inf"),
            error_r3_mm=float("inf"),
            error_r4_mm=float("inf"),
            rms_error_mm=float("inf"),
            max_error_mm=float("inf"),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            max_plane_residual_mm=round(max_plane_residual, 3),
            error_message=(
                f"Inverted or excessive tilt for board normal: z-component={normal_z:.3f} < {policy.min_normal_z:.3f}. "
                "Check whether R1-R4 teaching point order is swapped or inverted."
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # 7. Compute corner residuals against measured contact points
    P_pred_m = p_center_m + (R @ P_can.T).T
    residuals_mm = np.linalg.norm((P_pred_m - P_meas) * 1000.0, axis=1)

    e1 = float(residuals_mm[0])
    e2 = float(residuals_mm[1])
    e3 = float(residuals_mm[2])
    e4 = float(residuals_mm[3])
    rms_error = float(np.sqrt(np.mean(residuals_mm ** 2)))
    max_error = float(np.max(residuals_mm))

    if max_error > corner_hard_fail or rms_error > rms_hard_fail:
        return BoardCalibrationResult(
            success=False,
            state=None,
            error_r1_mm=round(e1, 2),
            error_r2_mm=round(e2, 2),
            error_r3_mm=round(e3, 2),
            error_r4_mm=round(e4, 2),
            rms_error_mm=round(rms_error, 2),
            max_error_mm=round(max_error, 2),
            measured_width_mm=round(measured_width, 2),
            measured_length_mm=round(measured_length, 2),
            max_plane_residual_mm=round(max_plane_residual, 3),
            error_message=(
                f"Calibration residual error too large: max={max_error:.2f} mm "
                f"(limit {corner_hard_fail:.1f} mm), RMS={rms_error:.2f} mm (limit {rms_hard_fail:.1f} mm)"
            ),
            teaching_points=pts_mm_dict,
            calibration_profile=profile,
            tolerance_policy=policy,
        )

    # 8. Record warnings if any parameter is between warning and hard fail
    warnings = []
    if rms_error > policy.max_rms_residual_warning_mm:
        warnings.append(
            f"RMS residual {rms_error:.2f} mm exceeds recommended warning threshold "
            f"({policy.max_rms_residual_warning_mm:.1f} mm)."
        )
    if width_error > policy.max_dimension_error_warning_mm:
        warnings.append(
            f"Width error {width_error:.2f} mm exceeds recommended warning threshold "
            f"({policy.max_dimension_error_warning_mm:.1f} mm)."
        )
    if length_error > policy.max_dimension_error_warning_mm:
        warnings.append(
            f"Length error {length_error:.2f} mm exceeds recommended warning threshold "
            f"({policy.max_dimension_error_warning_mm:.1f} mm)."
        )

    # 9. Build authoritative BoardPlacementState using canonical physical geometry
    surface_z_m = float(p_center_m[2])
    thickness_m = CANONICAL_THICKNESS_MM / 1000.0  # 0.0105 m canonical thickness
    box_center_z = surface_z_m - thickness_m / 2.0

    board_center_robot_m = [
        round(float(p_center_m[0]), 6),
        round(float(p_center_m[1]), 6),
        round(float(box_center_z), 6),
    ]

    # Compute effective board yaw for telemetry / backward compatibility
    R_0 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    R_z = R @ R_0.T
    effective_yaw_deg = math.degrees(math.atan2(R_z[1, 0], R_z[0, 0]))

    inferred_shift_mm = (-0.360 - float(p_center_m[0])) * 1000.0

    state = BoardPlacementState(
        forward_shift_mm=round(inferred_shift_mm, 2),
        safe_transit_height_mm=float(safe_transit_height_mm),
        board_height_offset_mm=round((surface_z_m - thickness_m) * 1000.0, 2),
        board_yaw_deg=round(effective_yaw_deg, 2),
        board_center_robot_m=board_center_robot_m,
        board_surface_z_robot_m=round(surface_z_m, 6),
        physical_board_center_robot_m=board_center_robot_m,
        physical_board_center_world_m=[
            round(-p_center_m[1], 6),
            round(box_center_z, 6),
            round(-p_center_m[0], 6),
        ],
        board_visual_root_world_m=[
            round(-p_center_m[1], 6),
            round(surface_z_m, 6),
            round(-p_center_m[0], 6),
        ],
        board_center_world_m=[
            round(-p_center_m[1], 6),
            round(surface_z_m, 6),
            round(-p_center_m[0], 6),
        ],
        rotation_matrix=[[round(float(v), 6) for v in row] for row in R.tolist()],
        placement_version=1,
    )

    # Set grid origin (cell 0, 0)
    p_c00 = state.cell_to_robot_xyz(0, 0, z_rel_m=0.0)
    state.grid_origin_robot_m = [round(float(v), 6) for v in p_c00]

    # 10. Generate full calibration log report (Section 14)
    tool_repr = observations["R1"].tool_id if observations["R1"].tool_id is not None else "0 (default)"
    wobj_repr = observations["R1"].user_or_wobj_id if observations["R1"].user_or_wobj_id is not None else "0 (base)"
    cal_log = (
        f"Teaching frame:\n"
        f"  tool = {tool_repr}\n"
        f"  user/wobj = {wobj_repr}\n"
        f"Calibration contact profile:\n"
        f"  offset = {profile.tcp_to_board_contact_offset_mm}\n"
        f"  offset frame = {profile.offset_frame}\n"
        f"  provenance = {profile.provenance}\n"
        f"R1-R4 transformed observations:\n"
        f"  R1: {contact_pts_mm['R1'].tolist()}\n"
        f"  R2: {contact_pts_mm['R2'].tolist()}\n"
        f"  R3: {contact_pts_mm['R3'].tolist()}\n"
        f"  R4: {contact_pts_mm['R4'].tolist()}\n"
        f"Measured width: {measured_width:.2f} mm\n"
        f"Measured length: {measured_length:.2f} mm\n"
        f"RMS residual: {rms_error:.3f} mm\n"
        f"Max residual: {max_error:.3f} mm\n"
        f"Plane residual: {max_plane_residual:.3f} mm\n"
        f"Board surface pose: center={board_center_robot_m}, surface_z={surface_z_m:.4f} m\n"
        f"T_robot_from_board R matrix:\n{R}"
    )

    return BoardCalibrationResult(
        success=True,
        state=state,
        error_r1_mm=e1,
        error_r2_mm=e2,
        error_r3_mm=e3,
        error_r4_mm=e4,
        rms_error_mm=rms_error,
        max_error_mm=max_error,
        measured_width_mm=measured_width,
        measured_length_mm=measured_length,
        max_plane_residual_mm=max_plane_residual,
        error_message=None,
        teaching_points=pts_mm_dict,
        calibration_profile=profile,
        tolerance_policy=policy,
        warnings=warnings,
        calibration_log=cal_log,
    )


class BoardPoseProvider(ABC):
    """Abstract interface for providing authoritative BoardPlacementState."""

    @abstractmethod
    def get_board_placement_state(self) -> BoardPlacementState:
        """Return the authoritative BoardPlacementState."""
        pass


class FixedBoardPoseProvider(BoardPoseProvider):
    """
    Fixed/static board placement provider.
    Used for simulation nominal placement and statically calibrated physical setups.
    """

    def __init__(self, placement_state: Optional[BoardPlacementState] = None):
        self._state = placement_state or BoardPlacementState.compute(forward_shift_mm=0.0)

    def get_board_placement_state(self) -> BoardPlacementState:
        return self._state

    def set_board_placement_state(self, state: BoardPlacementState) -> None:
        self._state = state

    @classmethod
    def from_forward_shift(
        cls,
        forward_shift_mm: float = 0.0,
        board_yaw_deg: float = 90.0,
        safe_transit_height_mm: float = 40.0,
    ) -> "FixedBoardPoseProvider":
        state = BoardPlacementState.compute(
            forward_shift_mm=forward_shift_mm,
            board_yaw_deg=board_yaw_deg,
            safe_transit_height_mm=safe_transit_height_mm,
        )
        return cls(state)

    @classmethod
    def from_teaching_points(
        cls,
        teaching_points: Dict[str, Any],
        board_yaw_deg: float = 90.0,
        safe_transit_height_mm: float = 40.0,
        calibration_profile: Optional[BoardCalibrationProfile] = None,
        tolerance_policy: Optional[BoardCalibrationTolerancePolicy] = None,
    ) -> "FixedBoardPoseProvider":
        """
        Bootstrap BoardPlacementState from R1-R4 teaching points using canonical rigid calibration.
        """
        result = calibrate_board_from_teaching_points(
            teaching_points=teaching_points,
            safe_transit_height_mm=safe_transit_height_mm,
            calibration_profile=calibration_profile,
            tolerance_policy=tolerance_policy,
        )
        if not result.success or result.state is None:
            raise ValueError(f"Failed to calibrate board from teaching points: {result.error_message}")
        return cls(result.state)


class PhysicalTeachingPointBoardPoseProvider(BoardPoseProvider):
    """
    Authoritative BoardPoseProvider calibrated from physical FAIRINO FR3 teaching points R1-R4.
    Does NOT fall back to simulation defaults if calibration fails or observations are invalid.
    """

    def __init__(
        self,
        calibration_result: BoardCalibrationResult,
        safe_transit_height_mm: float = 40.0,
    ):
        self._calibration_result = calibration_result
        self._safe_transit_height_mm = float(safe_transit_height_mm)

    @property
    def calibration_result(self) -> BoardCalibrationResult:
        return self._calibration_result

    @property
    def is_calibrated(self) -> bool:
        return self._calibration_result.success and self._calibration_result.state is not None

    def get_board_placement_state(self) -> BoardPlacementState:
        if not self.is_calibrated or self._calibration_result.state is None:
            err = self._calibration_result.error_message or "Physical board calibration is not available"
            raise RuntimeError(f"[PhysicalBoardPoseProvider] Cannot get BoardPlacementState: {err}")
        return self._calibration_result.state

    @classmethod
    def from_teaching_points(
        cls,
        teaching_points: Dict[str, Any],
        safe_transit_height_mm: float = 40.0,
        max_residual_mm: Optional[float] = None,
        max_rms_mm: Optional[float] = None,
        width_tolerance_mm: Optional[float] = None,
        length_tolerance_mm: Optional[float] = None,
        max_coplanar_z_diff_mm: Optional[float] = None,
        calibration_profile: Optional[BoardCalibrationProfile] = None,
        tolerance_policy: Optional[BoardCalibrationTolerancePolicy] = None,
    ) -> "PhysicalTeachingPointBoardPoseProvider":
        """Calibrate physical board pose from a dictionary containing R1-R4 teaching points."""
        result = calibrate_board_from_teaching_points(
            teaching_points=teaching_points,
            safe_transit_height_mm=safe_transit_height_mm,
            max_residual_mm=max_residual_mm,
            max_rms_mm=max_rms_mm,
            width_tolerance_mm=width_tolerance_mm,
            length_tolerance_mm=length_tolerance_mm,
            max_coplanar_z_diff_mm=max_coplanar_z_diff_mm,
            calibration_profile=calibration_profile,
            tolerance_policy=tolerance_policy,
        )
        return cls(result, safe_transit_height_mm=safe_transit_height_mm)

    @classmethod
    def from_controller(
        cls,
        controller_or_backend: Any,
        point_names: Sequence[str] = ("R1", "R2", "R3", "R4"),
        safe_transit_height_mm: float = 40.0,
        max_residual_mm: Optional[float] = None,
        max_rms_mm: Optional[float] = None,
        width_tolerance_mm: Optional[float] = None,
        length_tolerance_mm: Optional[float] = None,
        max_coplanar_z_diff_mm: Optional[float] = None,
        calibration_profile: Optional[BoardCalibrationProfile] = None,
        tolerance_policy: Optional[BoardCalibrationTolerancePolicy] = None,
    ) -> "PhysicalTeachingPointBoardPoseProvider":
        """
        Query R1-R4 teaching points directly from FAIRINO FR3 controller RPC / backend.
        """
        profile = calibration_profile or BoardCalibrationProfile()
        policy = tolerance_policy or BoardCalibrationTolerancePolicy()

        teaching_points: Dict[str, Any] = {}
        for name in point_names:
            err = -1
            data = None
            if hasattr(controller_or_backend, "get_teaching_point"):
                err, data = controller_or_backend.get_teaching_point(name)
            elif hasattr(controller_or_backend, "GetRobotTeachingPoint"):
                err, data = controller_or_backend.GetRobotTeachingPoint(name)
            elif hasattr(controller_or_backend, "robot") and hasattr(controller_or_backend.robot, "GetRobotTeachingPoint"):
                err, data = controller_or_backend.robot.GetRobotTeachingPoint(name)
            elif hasattr(controller_or_backend, "_rpc") and hasattr(controller_or_backend._rpc, "GetRobotTeachingPoint"):
                err, data = controller_or_backend._rpc.GetRobotTeachingPoint(name)

            if err != 0 or data is None or len(data) < 3:
                fail_result = BoardCalibrationResult(
                    success=False,
                    state=None,
                    error_r1_mm=float("inf"),
                    error_r2_mm=float("inf"),
                    error_r3_mm=float("inf"),
                    error_r4_mm=float("inf"),
                    rms_error_mm=float("inf"),
                    max_error_mm=float("inf"),
                    measured_width_mm=0.0,
                    measured_length_mm=0.0,
                    error_message=f"Controller failed to read teaching point '{name}' (err={err})",
                    calibration_profile=profile,
                    tolerance_policy=policy,
                )
                return cls(fail_result, safe_transit_height_mm=safe_transit_height_mm)

            teaching_points[name] = data

        return cls.from_teaching_points(
            teaching_points=teaching_points,
            safe_transit_height_mm=safe_transit_height_mm,
            max_residual_mm=max_residual_mm,
            max_rms_mm=max_rms_mm,
            width_tolerance_mm=width_tolerance_mm,
            length_tolerance_mm=length_tolerance_mm,
            max_coplanar_z_diff_mm=max_coplanar_z_diff_mm,
            calibration_profile=profile,
            tolerance_policy=policy,
        )
