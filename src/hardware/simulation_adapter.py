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
        if not robot.connected or robot.robot is None or robot.dry:
            raise ValueError("Physical telemetry requires an existing real connection")
        self.robot = robot
        self.ip = robot.ip
        self._reader = PhysicalFR3Backend(ip=robot.ip, dry_run=False)
        self._reader._rpc = robot.robot
        self._reader._connected = True

    def get_state_snapshot(self):
        self._reader._connected = bool(self.robot.connected)
        return self._reader.get_state_snapshot()


def physical_board_provider(robot, config):
    """Fit verified contact observations; reject unknown frame/offset or XY drift."""
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
    # A rigid canonical board must represent the actual visual motion mapping.
    # This is a consistency check, not a physical clearance acceptance threshold.
    state = provider.get_board_placement_state()
    for row in range(10):
        for col in range(9):
            physical = robot.board_to_pose_bilinear(col, row, state.board_surface_z_m * 1000.0)
            simulated = state.cell_to_robot_xyz(row, col) * 1000.0
            if np.linalg.norm(np.asarray(physical[:2]) - simulated[:2]) > 1e-3:
                raise ValueError("Physical bilinear grid and rigid simulation board disagree; mirror blocked")
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
    from src.domain.board_pose import BoardCell
    try:
        BoardCell(s_row, s_col)
        BoardCell(d_row, d_col)
        if (s_row, s_col) == (d_row, d_col):
            raise ValueError("Source and destination must differ")
    except (TypeError, ValueError) as exc:
        return rejected(str(exc), MotionFailureCategory.TARGET_INVALID)
    if is_capture:
        return rejected("Simulation capture needs a validated disposal route; no piece is teleported",
                        MotionFailureCategory.SAFETY_INTERLOCK)
    world = runtime.world
    if piece_id is None:
        matches = [pid for pid, piece in world.pieces.items()
                   if runtime.find_nearest_cell(piece.get_position_robot()) == (s_row, s_col)
                   and runtime.placement_state.is_in_bounds_robot(piece.get_position_robot())]
        if len(matches) != 1:
            return rejected("Source must contain exactly one simulated piece", MotionFailureCategory.TARGET_INVALID)
        piece_id = matches[0]
    if piece_id not in world.pieces or runtime.find_nearest_cell(world.pieces[piece_id].get_position_robot()) != (s_row, s_col):
        return rejected("Piece identity disagrees with source cell", MotionFailureCategory.TARGET_INVALID)
    target = runtime.placement_state.cell_to_robot_xyz(d_row, d_col)
    if any(pid != piece_id and np.linalg.norm(piece.get_position_robot()[:2] - target[:2]) < 0.015
           for pid, piece in world.pieces.items()):
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
                                    metadata={"piece_id": piece_id, "physical_grasp_verified": False})
