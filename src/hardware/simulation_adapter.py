"""Small adapters joining the visual application to the retained simulator.

Physical telemetry borrows the application's SDK connection and exposes reads
only. It never opens another controller connection or owns its shutdown.
"""
import numpy as np

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


def physical_board_provider(robot, config):
    """Optional measured board mirror; visual commands keep their own taught mapping."""
    from src.domain.board_pose_provider import (
        BoardCalibrationProfile, PhysicalTeachingPointBoardPoseProvider,
    )
    offset = getattr(config, "BOARD_CALIBRATION_OFFSET_MM", None)
    provenance = getattr(config, "BOARD_CALIBRATION_PROVENANCE", "")
    frame = getattr(config, "BOARD_CALIBRATION_OFFSET_FRAME", "")
    if offset is None or np.asarray(offset).shape != (3,) or not np.all(np.isfinite(offset)):
        raise ValueError("Physical board surface contact offset has not been calibrated")
    if not provenance or frame not in ("ROBOT_BASE", "TOOL"):
        raise ValueError("Physical board contact calibration requires frame and provenance")
    observations = {}
    for name in ("R1", "R2", "R3", "R4"):
        code, value = robot.robot.GetRobotTeachingPoint(name)
        if code != 0 or len(value) < 14:
            raise ValueError(f"{name}: missing verified teaching point/frame metadata")
        observations[name] = value
    provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(
        observations, calibration_profile=BoardCalibrationProfile(
            tcp_to_board_contact_offset_mm=list(offset), offset_frame=frame,
            provenance=provenance,
        ),
    )
    if not provider.is_calibrated:
        raise ValueError(provider.calibration_result.error_message)
    # Command coordinates and the mirror must use the SAME verified controller
    # frames. The visual donor used user=1 while canonical calibration requires
    # robot base (user=0); retaining that default would offset every motion.
    # Visual correction deliberately offsets measured pick centres. A rigid
    # board mirror is a display estimate, not a motion authority. Report the
    # difference instead of blocking physical visual commands on sub-micron fit.
    state = provider.get_board_placement_state()
    discrepancies = []
    for row in range(10):
        for col in range(9):
            physical = robot.board_to_pose_bilinear(col, row, state.board_surface_z_m * 1000.0)
            simulated = state.cell_to_robot_xyz(row, col) * 1000.0
            discrepancies.append(float(np.linalg.norm(np.asarray(physical[:2]) - simulated[:2])))
    provider.visual_command_xy_difference_mm = max(discrepancies)
    robot.tool_num = int(float(observations["R1"][12]))
    robot.user_num = int(float(observations["R1"][13]))
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
                         piece_id=None, captured_piece_id=None, move_context=None, **kwargs):
    from contextlib import nullcontext
    from src.simulation.runtime import RuntimeOperationState, RuntimeOperationBusy
    operation = getattr(runtime, "acquire_operation_state", None)
    try:
        with operation(RuntimeOperationState.GAME_MOVE) if callable(operation) else nullcontext():
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
        if (world.get_attached_piece() is not None
                or np.linalg.norm(world.pieces[captured_piece_id].get_position_robot()[:2] - target[:2]) < 0.015):
            return rejected("Capture square not physically cleared", MotionFailureCategory.SAFETY_INTERLOCK)
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
    for row, col in area.get("slots_in_board_grid", []):
        if not np.all(np.isfinite([row, col])):
            raise ValueError("Capture slot grid coordinates must be finite")
        slot = runtime.placement_state.cell_to_robot_xyz(row, col)
        slot[2] = 0.0
        if runtime.placement_state.is_in_bounds_robot(slot, xy_margin_m=runtime.geom.piece_diameter_mm / 2000.0 + 0.005):
            raise ValueError("Capture slot is inside the board")
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
