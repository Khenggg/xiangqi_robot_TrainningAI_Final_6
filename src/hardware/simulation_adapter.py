"""Small adapters joining the visual application to the retained simulator.

Physical telemetry borrows the application's SDK connection and exposes reads
only. It never opens another controller connection or owns its shutdown.
"""
import logging

import numpy as np

from src.core.project_logging import event
from src.motion.result import MotionExecutionResult, MotionFailureCategory, PayloadState
from src.motion.stages import MotionStage


class SimulationMotionResult(MotionExecutionResult):
    def __bool__(self):
        return self.success


def rejected(message, category=MotionFailureCategory.PRECONDITION_FAILED, stage=MotionStage.APPROACH):
    return SimulationMotionResult.fail(stage, category, message)


class BorrowedPhysicalStateSource:
    """Read snapshots using the visual robot's existing FAIRINO SDK handle."""
    dry_run = False

    def __init__(self, robot):
        from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
        if robot.robot is None or robot.dry:
            raise ValueError("Physical telemetry requires an existing real SDK handle")
        self.robot = robot
        self.ip = robot.ip
        self._reader = PhysicalFR3Backend(ip=robot.ip, dry_run=False)
        self._reader._rpc = robot.robot
        self._reader._connected = bool(robot.connected)

    def get_state_snapshot(self):
        sdk = self.robot.robot
        self._reader._rpc = sdk
        # Raw telemetry follows the retained SDK, independently of startup's
        # command/calibration latch. A recovered socket still needs a fresh
        # measured packet: the backend retains its freshness/validity checks.
        sdk_connected = getattr(sdk, 'SDK_state', None)
        self._reader._connected = sdk is not None and (
            sdk_connected if isinstance(sdk_connected, bool) else bool(self.robot.connected))
        self._reader._gripper_closed = bool(getattr(self.robot, 'gripper_closed_estimate', False))
        return self._reader.get_state_snapshot()


def _resolve_xy_surface_z(parsed, config):
    """Resolve the XY mirror surface Z from an independent measurement or R1-R4."""
    source = str(getattr(config, "BOARD_SURFACE_Z_SOURCE", "MEASURED")).upper()
    if source == "MEASURED":
        value = getattr(config, "BOARD_CALIBRATION_SURFACE_Z_MM", None)
        if value is None:
            raise ValueError(
                "XY board mirror needs BOARD_CALIBRATION_SURFACE_Z_MM "
                "or BOARD_SURFACE_Z_SOURCE='R1_R4'")
        value = float(value)
        if not np.isfinite(value):
            raise ValueError("BOARD_CALIBRATION_SURFACE_Z_MM must be finite")
        return value, dict(source="MEASURED", value_mm=value)
    if source != "R1_R4":
        raise ValueError("BOARD_SURFACE_Z_SOURCE must be MEASURED or R1_R4")
    if not bool(getattr(config, "R1_R4_TAUGHT_AT_BOARD_SURFACE", False)):
        raise ValueError(
            "BOARD_SURFACE_Z_SOURCE='R1_R4' requires R1_R4_TAUGHT_AT_BOARD_SURFACE=True "
            "after operator confirmation that all four points were taught at the board surface")
    zs = [float(point.xyz_mm[2]) for point in parsed.values()]
    if not np.isfinite(zs).all():
        raise ValueError("R1-R4 contain nonfinite Z")
    spread = float(max(zs) - min(zs))
    tolerance = float(getattr(config, "BOARD_CALIBRATION_Z_TOLERANCE_MM", 1.0))
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("BOARD_CALIBRATION_Z_TOLERANCE_MM must be positive")
    if spread > tolerance:
        raise ValueError(
            f"R1-R4 Z spread {spread:.2f} mm exceeds {tolerance:.2f} mm; "
            "the four points do not describe one flat board surface")
    value = float(np.median(zs))
    warnings = []
    safe_z = getattr(config, "SAFE_Z", None)
    pick_z = getattr(config, "PICK_Z", None)
    if safe_z is not None and abs(value - float(safe_z)) <= 5.0:
        warnings.append("R1-R4 Z is within 5 mm of SAFE_Z; points may have been taught at hover height")
    if pick_z is not None and abs(value - float(pick_z)) > 30.0:
        warnings.append("R1-R4 Z differs from PICK_Z by more than 30 mm")
    if warnings:
        event("board.surface_z_suspicious", "R1-R4 Z may not be the board surface",
              level=logging.WARNING, value_mm=value, warnings=warnings)
    return value, dict(source="R1_R4", value_mm=value, z_mm=zs,
                       spread_mm=spread, tolerance_mm=tolerance, warnings=warnings)


def physical_board_provider(robot, config):
    """Optional measured board mirror; visual commands keep their own taught mapping."""
    from src.domain.board_pose_provider import (
        BoardCalibrationProfile, PhysicalTeachingPointBoardPoseProvider, parse_teaching_point_observation,
    )
    model = getattr(config, "BOARD_CALIBRATION_MODEL", "XY_SE2")
    offset = getattr(config, "BOARD_CALIBRATION_OFFSET_MM", None)
    provenance = getattr(config, "BOARD_CALIBRATION_PROVENANCE", "")
    frame = getattr(config, "BOARD_CALIBRATION_OFFSET_FRAME", "")
    if model == "XY_SE2":
        dimensions = getattr(config, "BOARD_CALIBRATION_GRID_DIMENSIONS_MM", None)
        if dimensions is None or not provenance:
            raise ValueError(
                "XY board mirror needs measured grid width/length, provenance and a surface Z source")
    elif model == "SE3_LEGACY":
        if offset is None or np.asarray(offset).shape != (3,) or not np.all(np.isfinite(offset)):
            raise ValueError("Physical board surface contact offset has not been calibrated")
        if not provenance or frame not in ("ROBOT_BASE", "TOOL"):
            raise ValueError("Physical board contact calibration requires frame and provenance")
    else:
        raise ValueError("Board calibration model must be XY_SE2 or SE3_LEGACY")
    observations = {}
    for name in ("R1", "R2", "R3", "R4"):
        if getattr(robot, "uses_fixed_teaching_points", False) is True:
            code, value = robot.read_teaching_point(name)
        else:
            code, value = robot.robot.GetRobotTeachingPoint(name)
        if code != 0 or len(value) < 14:
            raise ValueError(f"{name}: missing verified teaching point/frame metadata")
        observations[name] = value
    parsed = {name: parse_teaching_point_observation(value) for name, value in observations.items()}
    normalize = getattr(robot, "normalize_board_observations", None)
    if callable(normalize):
        parsed = normalize(parsed)
    frames = {(point.tool_id, point.user_or_wobj_id) for point in parsed.values()}
    if len(frames) != 1 or any(value is None for value in next(iter(frames))):
        raise ValueError("All four mirror observations require the same explicit tool/user frame")
    tool_id, user_id = next(iter(frames))
    expected_user = int(getattr(config, "ROBOT_USER_FRAME", 0))
    require_base = bool(getattr(config, "BOARD_CALIBRATION_REQUIRE_BASE_FRAME", True))
    if require_base and user_id != 0:
        raise ValueError(
            f"Board mirror requires robot-base teaching points (user 0); found user {user_id}. "
            "Re-teach R1–R4 in robot base (user 0).")
    if user_id != expected_user:
        raise ValueError(
            f"Board mirror requires user {expected_user}; found user {user_id}.")
    expected_tool = getattr(config, "ROBOT_TOOL_FRAME", None)
    if expected_tool is not None and tool_id != int(expected_tool):
        raise ValueError(
            f"Board mirror requires tool {int(expected_tool)}; found tool {tool_id}.")
    if (tool_id, user_id) != (robot.tool_num, robot.user_num):
        raise ValueError("Controller points changed after command mapping loaded; reload R1–R4 before calibrating")
    for name, point in parsed.items():
        cached = robot.teaching_points.get(name, {}).get("pose")
        observed = list(point.xyz_mm) + list(point.rpy_deg)
        if (cached is None or len(cached) != 6
                or not np.allclose(cached, observed, atol=1e-9, rtol=0)):
            raise ValueError(f"{name} changed between controller reads; reload the command mapping")
    base_xy = np.eye(3)
    if model == "XY_SE2":
        from src.domain.board_xy_calibration import calibrate_board_xy
        surface_z, surface_meta = _resolve_xy_surface_z(parsed, config)
        event("board.surface_z_resolved", "Đã xác định Z mặt bàn cho mirror",
              source=surface_meta["source"], value_mm=surface_z, details=surface_meta)
        conversion = getattr(config, "BOARD_CALIBRATION_USER_TO_BASE_XY", None)
        result = calibrate_board_xy(
            parsed, grid_dimensions_mm=dimensions, surface_z_mm=surface_z,
            safe_transit_height_mm=getattr(config, "SAFE_TRANSIT_HEIGHT_MM", 40.0),
            previous_version=max(0, int(getattr(robot, "teaching_points_version", 0))),
            require_controller_metadata=True, robot_base_from_user_xy=conversion,
            frame_provenance=getattr(config, "BOARD_CALIBRATION_FRAME_PROVENANCE", ""),
        )
        provider = PhysicalTeachingPointBoardPoseProvider(result)
        if user_id != 0:
            base_xy = np.asarray(conversion, dtype=float)
    else:
        if user_id != 0:
            raise ValueError("Legacy SE3 mirror requires robot-base observations; no user-frame identity assumed")
        provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(
            observations, calibration_profile=BoardCalibrationProfile(
                tcp_to_board_contact_offset_mm=list(offset), offset_frame=frame, provenance=provenance))
    if not provider.is_calibrated:
        raise ValueError(provider.calibration_result.error_message)
    # Convert command XY to robot base before comparing the optional mirror.
    # Loading a mirror must not alter the command mapping's chosen frame.
    # Visual correction deliberately offsets measured pick centres. A rigid
    # board mirror is a display estimate, not a motion authority. Report the
    # difference instead of blocking physical visual commands on sub-micron fit.
    state = provider.get_board_placement_state()
    discrepancies = []
    for row in range(10):
        for col in range(9):
            physical = robot.board_to_pose_bilinear(col, row, state.board_surface_z_m * 1000.0)
            physical_xy = base_xy[:2, :2] @ np.asarray(physical[:2]) + base_xy[:2, 2]
            simulated = state.cell_to_robot_xyz(row, col) * 1000.0
            discrepancies.append(float(np.linalg.norm(physical_xy - simulated[:2])))
    provider.visual_command_xy_difference_mm = max(discrepancies)
    # Building an optional display provider must not rewrite command tool/user IDs.
    return provider


class VirtualVisualRobot:
    """Visual application's robot facade; all virtual motion stays in runtime."""
    dry = True
    robot = None
    teaching_points = {}
    physical_motion_authorized = False

    def __init__(self, manager):
        self.manager = manager
        self.perspective_matrix = None

    @property
    def connected(self):
        return self.manager.backend.is_connected()

    def set_perspective_matrix(self, matrix):
        self.perspective_matrix = matrix

    def get_planned_command(self):
        return None

    def move_piece(self, *args, **kwargs):
        return execute_virtual_move(self.manager.simulation_runtime, *args, **kwargs)

    execute_piece_move = move_piece

    def board_to_pose(self, col, row, z_height, rotation=None):
        state = self.manager.simulation_runtime.placement_state
        xyz = state.cell_to_robot_xyz(row, col) * 1000.0
        xyz[2] = z_height
        return list(xyz) + list(rotation or [180.0, 0.0, 0.0])


def execute_virtual_move(runtime, s_col, s_row, d_col, d_row, is_capture,
                         moving_visual_target=None, captured_visual_target=None,
                         piece_id=None, captured_piece_id=None, move_context=None, validity_guard=None, **kwargs):
    from contextlib import nullcontext
    from src.simulation.runtime import RuntimeOperationState, RuntimeOperationBusy
    operation = getattr(runtime, "acquire_operation_state", None)
    try:
        with operation(RuntimeOperationState.GAME_MOVE) if callable(operation) else nullcontext():
            if validity_guard is not None:
                validity_guard()
            return _execute_virtual_move(runtime, s_col, s_row, d_col, d_row, is_capture,
                                         piece_id=piece_id, captured_piece_id=captured_piece_id)
    except (RuntimeOperationBusy, ValueError, TypeError) as exc:
        return rejected(str(exc))


def _execute_virtual_move(runtime, s_col, s_row, d_col, d_row, is_capture,
                          piece_id=None, captured_piece_id=None):
    from src.domain.board_pose import BoardCell
    try:
        BoardCell(s_row, s_col)
        BoardCell(d_row, d_col)
        if (s_row, s_col) == (d_row, d_col):
            raise ValueError("Source and destination must differ")
    except (TypeError, ValueError) as exc:
        return rejected(str(exc), MotionFailureCategory.TARGET_INVALID)
    world = runtime.world
    if piece_id is None:
        matches = [pid for pid, piece in world.pieces.items()
                   if runtime.find_nearest_cell(piece.get_position_robot()) == (s_row, s_col)
                   and runtime.placement_state.is_in_bounds_robot(piece.get_position_robot())]
        if len(matches) != 1:
            return rejected("Source must contain exactly one simulated piece", MotionFailureCategory.TARGET_INVALID)
        piece_id = matches[0]
    if (piece_id not in world.pieces
            or not runtime.placement_state.is_in_bounds_robot(world.pieces[piece_id].get_position_robot())
            or runtime.find_nearest_cell(world.pieces[piece_id].get_position_robot()) != (s_row, s_col)):
        return rejected("Piece identity disagrees with source cell", MotionFailureCategory.TARGET_INVALID)
    target = runtime.placement_state.cell_to_robot_xyz(d_row, d_col)
    victims = [pid for pid, piece in world.pieces.items() if pid != piece_id
               and np.linalg.norm(piece.get_position_robot()[:2] - target[:2]) < 0.015]
    if is_capture:
        if (len(victims) != 1 or (captured_piece_id is not None and victims != [captured_piece_id])
                or victims[0].split("_", 1)[0] == piece_id.split("_", 1)[0]):
            return rejected("Captured identity must match one opponent at destination", MotionFailureCategory.TARGET_INVALID)
        captured_piece_id = victims[0]
        slot = select_capture_slot(runtime)
        if slot is None:
            return rejected("No free reachable simulated capture slot; configure capture_area in the scene",
                            MotionFailureCategory.SAFETY_INTERLOCK)
        removed = runtime.pick_piece(captured_piece_id)
        if not removed.get("success", False):
            return rejected(removed.get("error") or removed.get("status"), MotionFailureCategory.PAYLOAD_NOT_CONFIRMED)
        disposed = runtime.place_piece(capture_slot_robot_m=slot)
        if not disposed.get("success", False):
            return rejected(disposed.get("error") or disposed.get("status"),
                            MotionFailureCategory.MOTION_COMMAND_FAILED, MotionStage.RELEASE)
        captured_body = world.pieces.get(captured_piece_id)
        if (world.get_attached_piece() is not None
                or (captured_body is not None
                    and np.linalg.norm(captured_body.get_position_robot()[:2] - target[:2]) < 0.015)):
            return rejected("Capture square not physically cleared", MotionFailureCategory.SAFETY_INTERLOCK)
        # Hybrid policy: keep an immutable tray snapshot for telemetry/viewer,
        # but remove the captured rigid body from the physics world.
        if world.capture_piece(captured_piece_id) is None:
            return rejected("Captured piece snapshot unavailable", MotionFailureCategory.PAYLOAD_NOT_CONFIRMED)
    elif victims:
        return rejected("Destination is occupied", MotionFailureCategory.TARGET_INVALID)
    picked = runtime.pick_piece(piece_id)
    if not picked.get("success", False):
        return rejected(picked.get("error") or picked.get("status", "Virtual pick failed"),
                        MotionFailureCategory.PAYLOAD_NOT_CONFIRMED, MotionStage.GRIP)
    placed = runtime.place_piece(target_cell=(d_row, d_col))
    if not placed.get("success", False):
        return rejected(placed.get("error") or placed.get("status", "Virtual place failed"),
                        MotionFailureCategory.MOTION_COMMAND_FAILED, MotionStage.PLACE_LAND)
    return SimulationMotionResult.ok(payload_state=PayloadState.RELEASED,
                                    metadata={"piece_id": piece_id, "captured_piece_id": captured_piece_id,
                                              "physical_grasp_verified": False})


def select_capture_slot(runtime):
    """Scene-defined board-relative slots; no physical teaching-point fallback."""
    area = getattr(runtime, "capture_area", {})
    if area.get("support") != "SIMULATED_FLOOR":
        return None
    from src.domain.capture_layout import capture_slots
    for slot in capture_slots(area, runtime.placement_state, runtime.geom):
        spacing = runtime.geom.piece_diameter_mm / 1000.0 + 0.005
        if any(np.linalg.norm(piece.get_position_robot()[:2] - slot[:2]) < spacing
               for piece in runtime.world.pieces.values()):
            continue
        pose = list(slot * 1000.0) + list(runtime.target_tool_euler_deg)
        pose[2] += runtime.geom.piece_height_mm / 2.0 + runtime.PLACE_RELEASE_CLEARANCE_M * 1000.0
        ik = runtime.backend.solve_tcp_ik(pose, allow_multi_seed=True)
        if ik.success:
            return slot
    return None
