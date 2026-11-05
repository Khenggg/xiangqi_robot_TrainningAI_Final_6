"""Rigid R1–R4 XY calibration; height and physical motion authority are separate."""
import math
import numpy as np

from src.domain.board_pose import BoardPlacementState, compute_rotation_matrix, load_nominal_scene_placement
from src.domain.board_pose_provider import (
    BoardCalibrationResult, BoardCalibrationTolerancePolicy, parse_teaching_point_observation,
    CANONICAL_WIDTH_MM, CANONICAL_LENGTH_MM, CANONICAL_THICKNESS_MM,
)


def calibrate_board_xy(points, *, grid_dimensions_mm, surface_z_mm,
                       safe_transit_height_mm, previous_version,
                       require_controller_metadata=False,
                       robot_base_from_user_xy=None, frame_provenance="",
                       tolerance_policy=None):
    """Fit SE(2) from four outer grid intersections, never a scaled/warped board.

    R1=(row 0,col 0), R2=(0,8), R3=(9,8), R4=(9,0). Z/RPY observations
    do not enter the fit. Surface Z is supplied through an independent contract.
    Geometry dimensions must match the shared mesh/cell geometry; another board
    size requires updating that geometry explicitly rather than silently scaling.
    Controller inputs require one tool and user frame; a nonzero user frame needs
    an explicitly proven rigid XY conversion to robot base.
    """
    names = ("R1", "R2", "R3", "R4")
    if not isinstance(points, dict) or set(points) != set(names):
        raise ValueError("XY calibration requires exactly R1, R2, R3, R4")
    dimensions = np.asarray(grid_dimensions_mm, dtype=float)
    if dimensions.shape != (2,) or not np.isfinite(dimensions).all() or np.any(dimensions <= 0):
        raise ValueError("Grid width/length must be explicit positive millimetres")
    if not np.allclose(dimensions, [CANONICAL_WIDTH_MM, CANONICAL_LENGTH_MM], atol=1e-6, rtol=0):
        raise ValueError("Measured grid dimensions differ from shared geometry; update geometry before calibration")
    if (isinstance(surface_z_mm, bool) or isinstance(safe_transit_height_mm, bool)
            or not math.isfinite(float(surface_z_mm)) or not math.isfinite(float(safe_transit_height_mm))
            or safe_transit_height_mm <= 0 or type(previous_version) is not int or previous_version < 0):
        raise ValueError("Independent surface Z, transit height and previous version are required")
    observations = {name: parse_teaching_point_observation(points[name]) for name in names}
    measured = np.asarray([observations[name].xyz_mm[:2] for name in names], dtype=float)
    if measured.shape != (4, 2) or not np.isfinite(measured).all():
        raise ValueError("R1–R4 require finite XY in millimetres")
    if require_controller_metadata:
        tools = [observations[name].tool_id for name in names]
        users = [observations[name].user_or_wobj_id for name in names]
        if (any(type(value) is not int or value < 0 for value in tools + users)
                or len(set(tools)) != 1 or len(set(users)) != 1):
            raise ValueError("R1–R4 require the same explicit tool/user frame")
        if users[0] != 0:
            if robot_base_from_user_xy is None or not frame_provenance.strip():
                raise ValueError("Non-base teaching frame requires a proven robot-base XY transform")
            transform = np.asarray(robot_base_from_user_xy, dtype=float)
            if (transform.shape != (3, 3) or not np.isfinite(transform).all()
                    or not np.allclose(transform[2], [0, 0, 1], atol=1e-9, rtol=0)
                    or not np.allclose(transform[:2, :2].T @ transform[:2, :2], np.eye(2), atol=1e-9, rtol=0)
                    or not math.isclose(float(np.linalg.det(transform[:2, :2])), 1, abs_tol=1e-9)):
                raise ValueError("User-to-base conversion must be rigid SE(2), without scale/reflection")
            measured = measured @ transform[:2, :2].T + transform[:2, 2]

    width, length = map(float, dimensions)
    local = np.array([[-width/2, -length/2], [width/2, -length/2],
                      [width/2, length/2], [-width/2, length/2]])
    center = measured.mean(axis=0)
    left, singular, right_t = np.linalg.svd(local.T @ (measured-center))
    if singular[-1] <= 1e-9:
        raise ValueError("Degenerate/collinear R1–R4 XY observations")
    correction = np.diag([1.0, 1.0 if np.linalg.det(right_t.T @ left.T) > 0 else -1.0])
    rotation_xy = right_t.T @ correction @ left.T
    errors = np.linalg.norm(local @ rotation_xy.T + center - measured, axis=1)
    rms = float(np.sqrt(np.mean(errors**2)))
    policy = tolerance_policy or BoardCalibrationTolerancePolicy()
    limits = (policy.max_corner_residual_hard_fail_mm, policy.max_rms_residual_hard_fail_mm,
              policy.max_dimension_error_hard_fail_mm)
    if any(not math.isfinite(float(value)) or value < 0 for value in limits):
        raise ValueError("XY fit tolerances must be finite nonnegative millimetres")
    max_error = float(np.max(errors))
    error = None
    if max_error > policy.max_corner_residual_hard_fail_mm or rms > policy.max_rms_residual_hard_fail_mm:
        error = f"R1–R4 do not fit a rigid XY grid: max={max_error:.3f} mm, RMS={rms:.3f} mm"
    measured_width = float((np.linalg.norm(measured[1]-measured[0])+np.linalg.norm(measured[2]-measured[3]))/2)
    measured_length = float((np.linalg.norm(measured[3]-measured[0])+np.linalg.norm(measured[2]-measured[1]))/2)
    if max(abs(measured_width-width), abs(measured_length-length)) > policy.max_dimension_error_hard_fail_mm:
        error = "R1–R4 dimensions differ from configured grid; no scale/warp correction applied"
    state = None
    retained_points = {name: [float(xy[0]), float(xy[1]), float(surface_z_mm)]
                       for name, xy in zip(names, measured)}
    if error is None:
        rotation = np.eye(3)
        rotation[:2, :2] = rotation_xy
        yaw_rotation = rotation @ compute_rotation_matrix(0).T
        z = float(surface_z_mm)/1000
        box_z = z-CANONICAL_THICKNESS_MM/2000
        x, y = center/1000
        nominal = load_nominal_scene_placement()["board_center_in_robot_base_m"]
        nominal_xy_mm = np.asarray(nominal[:2], dtype=float)*1000
        shift_mm = float(np.dot(center-nominal_xy_mm, rotation_xy[:, 0]))
        state = BoardPlacementState(
            forward_shift_mm=shift_mm, safe_transit_height_mm=float(safe_transit_height_mm),
            board_height_offset_mm=float(surface_z_mm)-CANONICAL_THICKNESS_MM,
            board_yaw_deg=math.degrees(math.atan2(yaw_rotation[1, 0], yaw_rotation[0, 0])),
            board_center_robot_m=[float(x), float(y), box_z], board_surface_z_robot_m=z,
            physical_board_center_robot_m=[float(x), float(y), box_z],
            physical_board_center_world_m=[float(-y), box_z, float(-x)],
            board_visual_root_world_m=[float(-y), z, float(-x)],
            board_center_world_m=[float(-y), z, float(-x)], rotation_matrix=rotation.tolist(),
            teaching_points=retained_points, placement_version=previous_version+1,
            calibration_space="XY_SE2",
        )
        state.grid_origin_robot_m = state.cell_to_robot_xyz(0, 0).tolist()
        mapped = np.asarray([state.cell_to_robot_xyz(row, col)[:2]*1000
                             for row, col in ((0, 0), (0, 8), (9, 8), (9, 0))])
        if not np.allclose(mapped, local @ rotation_xy.T + center, atol=1e-6, rtol=0):
            raise ValueError("Shared cell mapping disagrees with XY calibration; no placement published")
    return BoardCalibrationResult(
        success=error is None, state=state,
        error_r1_mm=float(errors[0]), error_r2_mm=float(errors[1]),
        error_r3_mm=float(errors[2]), error_r4_mm=float(errors[3]),
        rms_error_mm=rms, max_error_mm=max_error, measured_width_mm=measured_width,
        measured_length_mm=measured_length, error_message=error, teaching_points=retained_points,
        tolerance_policy=policy, calibration_log="XY_SE2; Z independent; no scale/warp",
    )
