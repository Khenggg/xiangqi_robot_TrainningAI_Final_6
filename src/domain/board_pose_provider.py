"""
Domain module for Board Pose Providers.

Decouples board localization and calibration from motion execution.
Allows switching between fixed nominal pose, calibrated physical teaching points,
and future vision-based dynamic board tracking.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import math
import numpy as np

from src.domain.board_pose import BoardPlacementState, compute_rotation_matrix


CANONICAL_WIDTH_MM: float = 320.0   # col 0 to col 8 (8 * 40mm)
CANONICAL_LENGTH_MM: float = 360.0  # row 0 to row 9 (9 * 40mm)
CANONICAL_DIAGONAL_MM: float = math.hypot(CANONICAL_WIDTH_MM, CANONICAL_LENGTH_MM)  # ~481.66 mm


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


def extract_xyz_mm(val: Any) -> List[float]:
    """Extract [x, y, z] in mm from teaching point data structures."""
    if isinstance(val, dict):
        if "pose" in val:
            val = val["pose"]
        elif "xyz" in val:
            val = val["xyz"]
    elif hasattr(val, "pose"):
        val = getattr(val, "pose")
    elif hasattr(val, "x") and hasattr(val, "y") and hasattr(val, "z"):
        val = [getattr(val, "x"), getattr(val, "y"), getattr(val, "z")]

    if not isinstance(val, (list, tuple, np.ndarray)) or len(val) < 3:
        raise ValueError(f"Teaching point data must contain at least 3 coordinates, got {val}")

    x, y, z = float(val[0]), float(val[1]), float(val[2])
    if math.isnan(x) or math.isnan(y) or math.isnan(z) or math.isinf(x) or math.isinf(y) or math.isinf(z):
        raise ValueError(f"Teaching point contains NaN or Inf coordinates: {[x, y, z]}")

    return [x, y, z]


def calibrate_board_from_teaching_points(
    teaching_points: Dict[str, Any],
    safe_transit_height_mm: float = 40.0,
    max_residual_mm: float = 20.0,
    max_rms_mm: float = 15.0,
    width_tolerance_mm: float = 30.0,
    length_tolerance_mm: float = 30.0,
    max_coplanar_z_diff_mm: float = 25.0,
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
            )

    try:
        pts_mm = {pt: extract_xyz_mm(teaching_points[pt]) for pt in required_points}
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
        )

    p1_mm = np.array(pts_mm["R1"], dtype=float)
    p2_mm = np.array(pts_mm["R2"], dtype=float)
    p3_mm = np.array(pts_mm["R3"], dtype=float)
    p4_mm = np.array(pts_mm["R4"], dtype=float)

    # 1. Geometry and quadrilateral plausibility checks
    w_top = float(np.linalg.norm(p2_mm - p1_mm))
    w_bot = float(np.linalg.norm(p3_mm - p4_mm))
    measured_width = (w_top + w_bot) / 2.0

    l_left = float(np.linalg.norm(p4_mm - p1_mm))
    l_right = float(np.linalg.norm(p3_mm - p2_mm))
    measured_length = (l_left + l_right) / 2.0

    # Width check
    if abs(measured_width - CANONICAL_WIDTH_MM) > width_tolerance_mm:
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
                f"expected {CANONICAL_WIDTH_MM:.1f} mm (+/- {width_tolerance_mm} mm)"
            ),
            teaching_points=pts_mm,
        )

    # Length check
    if abs(measured_length - CANONICAL_LENGTH_MM) > length_tolerance_mm:
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
                f"expected {CANONICAL_LENGTH_MM:.1f} mm (+/- {length_tolerance_mm} mm)"
            ),
            teaching_points=pts_mm,
        )

    # Coplanar Z check
    z_vals = [p1_mm[2], p2_mm[2], p3_mm[2], p4_mm[2]]
    z_diff = max(z_vals) - min(z_vals)
    if z_diff > max_coplanar_z_diff_mm:
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
                f"Board corner Z variation too large: {z_diff:.1f} mm > {max_coplanar_z_diff_mm:.1f} mm"
            ),
            teaching_points=pts_mm,
        )

    # 2. Convert measured points to meters for rigid estimation
    P_meas = np.array([p1_mm, p2_mm, p3_mm, p4_mm], dtype=float) / 1000.0

    # Board playing surface center in robot base {B}
    p_center_m = np.mean(P_meas, axis=0)

    # Canonical corner coordinates in board-local frame (meters)
    # Centered at (0, 0, 0) on the surface
    P_can = np.array([
        [-0.160, -0.180, 0.0],  # R1 (row 0, col 0)
        [+0.160, -0.180, 0.0],  # R2 (row 0, col 8)
        [+0.160, +0.180, 0.0],  # R3 (row 9, col 8)
        [-0.160, +0.180, 0.0],  # R4 (row 9, col 0)
    ], dtype=float)

    # 3. Optimal rigid transformation via Kabsch / SVD
    P_meas_centered = P_meas - p_center_m
    H = P_can.T @ P_meas_centered  # 3x3 covariance matrix

    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T

    # Enforce right-handed rotation SO(3)
    if np.linalg.det(R) < 0.0:
        Vt[-1, :] *= -1.0
        R = Vt.T @ U.T

    # Check that normal vector points upward (board surface facing +Z)
    normal_z = R[2, 2]
    if normal_z < 0.7:
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
                f"Inverted or non-horizontal board normal (z-component={normal_z:.3f} < 0.7). "
                "Check whether R1-R4 teaching point order is inverted."
            ),
            teaching_points=pts_mm,
        )

    # 4. Compute corner residuals against measured teaching points
    P_pred_m = p_center_m + (R @ P_can.T).T
    residuals_mm = np.linalg.norm((P_pred_m - P_meas) * 1000.0, axis=1)

    e1 = float(residuals_mm[0])
    e2 = float(residuals_mm[1])
    e3 = float(residuals_mm[2])
    e4 = float(residuals_mm[3])
    rms_error = float(np.sqrt(np.mean(residuals_mm ** 2)))
    max_error = float(np.max(residuals_mm))

    if max_error > max_residual_mm or rms_error > max_rms_mm:
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
            error_message=(
                f"Calibration residual error too large: max={max_error:.2f} mm "
                f"(limit {max_residual_mm:.1f} mm), RMS={rms_error:.2f} mm (limit {max_rms_mm:.1f} mm)"
            ),
            teaching_points=pts_mm,
        )

    # 5. Build authoritative BoardPlacementState
    surface_z_m = float(p_center_m[2])
    thickness_m = 0.0105  # canonical 10.5 mm
    box_center_z = surface_z_m - thickness_m / 2.0

    board_center_robot_m = [
        round(float(p_center_m[0]), 6),
        round(float(p_center_m[1]), 6),
        round(float(box_center_z), 6),
    ]

    # Compute effective board yaw for telemetry / backward compatibility
    # Convention: R = R_z(yaw) @ R_0 -> R_z = R @ R_0^T
    R_0 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    R_z = R @ R_0.T
    effective_yaw_deg = math.degrees(math.atan2(R_z[1, 0], R_z[0, 0]))

    # Inferred forward shift relative to nominal X=-0.360m: center_x = -0.360 - d_m -> d_m = -0.360 - center_x
    inferred_shift_mm = (-0.360 - float(p_center_m[0])) * 1000.0

    state = BoardPlacementState(
        forward_shift_mm=round(inferred_shift_mm, 2),
        safe_transit_height_mm=float(safe_transit_height_mm),
        board_height_offset_mm=round((surface_z_m - 0.0105) * 1000.0, 2),
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
        error_message=None,
        teaching_points=pts_mm,
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
    ) -> "FixedBoardPoseProvider":
        """
        Bootstrap BoardPlacementState from R1-R4 teaching points using canonical rigid calibration.
        """
        result = calibrate_board_from_teaching_points(
            teaching_points=teaching_points,
            safe_transit_height_mm=safe_transit_height_mm,
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
        max_residual_mm: float = 20.0,
        max_rms_mm: float = 15.0,
        width_tolerance_mm: float = 30.0,
        length_tolerance_mm: float = 30.0,
    ) -> "PhysicalTeachingPointBoardPoseProvider":
        """Calibrate physical board pose from a dictionary containing R1-R4 teaching points."""
        result = calibrate_board_from_teaching_points(
            teaching_points=teaching_points,
            safe_transit_height_mm=safe_transit_height_mm,
            max_residual_mm=max_residual_mm,
            max_rms_mm=max_rms_mm,
            width_tolerance_mm=width_tolerance_mm,
            length_tolerance_mm=length_tolerance_mm,
        )
        return cls(result, safe_transit_height_mm=safe_transit_height_mm)

    @classmethod
    def from_controller(
        cls,
        controller_or_backend: Any,
        point_names: Sequence[str] = ("R1", "R2", "R3", "R4"),
        safe_transit_height_mm: float = 40.0,
        max_residual_mm: float = 20.0,
        max_rms_mm: float = 15.0,
        width_tolerance_mm: float = 30.0,
        length_tolerance_mm: float = 30.0,
    ) -> "PhysicalTeachingPointBoardPoseProvider":
        """
        Query R1-R4 teaching points directly from FAIRINO FR3 controller RPC / backend.
        """
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
        )
