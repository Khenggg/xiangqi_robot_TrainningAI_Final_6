"""Bounded HOMECHESS recovery using the owned driver and measured robot-base TCP.

This module never enables/resets a controller, clears a stop latch, commands the
gripper, or repeats a failed game command. The operator removes any held piece
and restores the board after HOME is verified. Physical clearance is unverified.
"""
from dataclasses import dataclass
import math
import time

import config
from src.hardware.rpc_transport import RpcOutcomeUnknown
from src.hardware.simulation_adapter import BorrowedPhysicalStateSource


# Acceptance thresholds in robot_base_frame (mm/degrees), not calibration data.
HOME_POSITION_TOLERANCE_MM = 1.0
HOME_ORIENTATION_TOLERANCE_DEG = 1.0
HOME_JOINT_TOLERANCE_DEG = 1.0
MEASUREMENT_MAX_AGE_S = 0.5
MEASUREMENT_TIMEOUT_S = 1.0
MEASUREMENT_POLL_INTERVAL_S = 0.025


@dataclass(frozen=True)
class HomeChessRecoveryResult:
    at_home: bool
    reason: str
    commanded: bool = False


def _unknown_outcome(failure, robot):
    seen = set()
    current = failure
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (RpcOutcomeUnknown, OSError)):
            return True
        current = current.__cause__ or current.__context__
    metadata = getattr(getattr(robot, "last_motion_result", None), "metadata", {})
    return metadata.get("rpc_outcome_unknown", False) is True


@dataclass(frozen=True)
class _HomePoint:
    pose: tuple
    joints: tuple
    tool: int
    user: int


@dataclass(frozen=True)
class _MeasuredPose:
    pose: tuple
    joints: tuple


def _finite_joints(values):
    joints = tuple(float(value) for value in values)
    if len(joints) != 6 or not all(math.isfinite(value) for value in joints):
        raise RuntimeError("Six finite measured joints are required")
    return joints


def _frame_id(value):
    # The bundled SDK packet exposes c_int fields as Python ints. Reject bools,
    # strings and fractional IDs rather than guessing a telemetry frame.
    if type(value) is not int or value < 0:
        raise RuntimeError("Missing or malformed measured tool/user frame")
    return value


def _guard(robot, is_current=None, home=None):
    if is_current is not None and is_current() is not True:
        raise RuntimeError("Recovery no longer owns the pending move")
    if getattr(robot, "dry", True) is not False:
        raise RuntimeError("HOME recovery requires a measured physical driver")
    if getattr(robot, "connected", False) is not True:
        raise RuntimeError("Robot disconnected; HOME was not dispatched")
    if getattr(robot, "physical_motion_authorized", False) is not True:
        raise RuntimeError("Physical control is not authorized")
    if getattr(robot, "_disable_outcome_unknown", False) is True:
        raise RuntimeError("Controller disable outcome is unknown")
    if getattr(robot, "_gripper_pulse_active", False) is True:
        raise RuntimeError("Gripper pulse has not finished")
    if getattr(robot, "_gripper_hold_active", False) is True:
        raise RuntimeError("Gripper close output is still active")
    if isinstance(getattr(robot, '_gripper_stop_failure', None), BaseException):
        raise RuntimeError(f'Controller stop unresolved: {robot._gripper_stop_failure}')
    tool, user = _frame_id(robot.tool_num), _frame_id(robot.user_num)
    if user != 0:
        raise RuntimeError("HOME recovery TCP requires robot-base user frame 0")
    if home is not None and (tool, user) != (home.tool, home.user):
        raise RuntimeError("Driver tool/user frame changed during HOME recovery")
    robot._require_actuation()  # Includes stop latch and existing driver gates.
    validity = getattr(robot, 'dispatch_validity', None)
    if validity is not None:
        validity()


def _home_point(robot):
    code, point = robot.read_teaching_point("HOMECHESS")
    if isinstance(code, bool) or code != 0:
        raise RuntimeError("Validated HOMECHESS teaching point unavailable")
    robot._verify_waypoint_frame(point, "HOMECHESS")
    pose = tuple(robot._validate_pose(point[:6]))
    if len(point) < 14 or not all(math.isfinite(float(v)) for v in point[6:12]):
        raise RuntimeError("HOMECHESS joints/frame metadata are invalid")
    return _HomePoint(pose, tuple(float(v) for v in point[6:12]),
                      _frame_id(robot.tool_num), _frame_id(robot.user_num))


def _verify_measured_frame(robot, source, snapshot, home):
    """Use the exact immutable SDK packet pinned by the physical reader.

    Looking at robot.robot.robot_state_pkg independently could pair a new
    packet's frame with an old snapshot's TCP. PhysicalFR3Backend pins the
    packet and measurement timestamp together; fail closed if that provenance
    is unavailable (including the legacy independent-query fallback).
    """
    reader = getattr(source, "_reader", None)
    packet = getattr(reader, "_last_stream_packet", None)
    if (reader is None or packet is None or isinstance(packet, type)
            or getattr(reader, "_rpc", None) is not robot.robot
            or getattr(reader, "_measurement_timestamp", None) != snapshot.measurement_timestamp):
        raise RuntimeError("Measured TCP has no pinned packet/frame provenance")
    tool = _frame_id(getattr(packet, "tool", None))
    user = _frame_id(getattr(packet, "user", None))
    if (tool, user) != (home.tool, home.user):
        raise RuntimeError("Measured packet tool/user differs from HOME command frame")
    packet_tcp = robot._validate_pose(getattr(packet, "tl_cur_pos", ()))
    if tuple(packet_tcp) != tuple(snapshot.tcp_pose_mm_deg):
        raise RuntimeError("Measured TCP does not match the pinned frame packet")
    packet_joints = _finite_joints(getattr(packet, "jt_cur_pos", ()))
    if packet_joints != _finite_joints(snapshot.joints_deg):
        raise RuntimeError("Measured joints do not match the pinned frame packet")


def _measured_idle(robot, source, since, home, is_current, *, allow_settle=False):
    """Two distinct idle packets produced after this recovery stage started."""
    deadline = time.monotonic() + MEASUREMENT_TIMEOUT_S
    last_stamp, samples = None, 0
    while time.monotonic() < deadline:
        _guard(robot, is_current, home)
        snapshot = source.get_state_snapshot()
        if (snapshot.connected is not True or snapshot.joints_valid is not True
                or snapshot.tcp_valid is not True):
            raise RuntimeError("Robot measurements are unavailable/invalid")
        settling = allow_settle and snapshot.motion_state == "MOVING"
        if (snapshot.motion_state not in {"IDLE", "READY"} and not settling) or snapshot.last_error:
            raise RuntimeError(f"Robot is not idle: {snapshot.motion_state}; {snapshot.last_error or ''}")
        stamp = snapshot.measurement_timestamp
        if stamp is not None and math.isfinite(float(stamp)):
            age = time.time() - stamp
            if stamp > since and 0 <= age <= MEASUREMENT_MAX_AGE_S:
                _verify_measured_frame(robot, source, snapshot, home)
                if settling:
                    last_stamp, samples = None, 0
                elif last_stamp is None or stamp > last_stamp:
                    samples += 1
                    last_stamp = stamp
                    if samples >= 2:
                        return _MeasuredPose(tuple(robot._validate_pose(snapshot.tcp_pose_mm_deg)),
                                             _finite_joints(snapshot.joints_deg))
            else:
                last_stamp, samples = None, 0
        else:
            last_stamp, samples = None, 0
        time.sleep(MEASUREMENT_POLL_INTERVAL_S)
    raise RuntimeError("No two distinct fresh idle TCP measurements; HOME not verified")


def _pose_matches(actual, expected):
    position_error = math.dist(actual[:3], expected[:3])
    angle_errors = [abs((a - b + 180.0) % 360.0 - 180.0)
                    for a, b in zip(actual[3:], expected[3:])]
    return (position_error <= HOME_POSITION_TOLERANCE_MM
            and max(angle_errors) <= HOME_ORIENTATION_TOLERANCE_DEG)


def _home_matches(measured, home):
    # HOME is a taught joint configuration, not merely an equivalent TCP pose.
    # Absolute differences deliberately do not treat winding angles as equal.
    return (_pose_matches(measured.pose, home.pose)
            and all(abs(actual - expected) <= HOME_JOINT_TOLERANCE_DEG
                    for actual, expected in zip(measured.joints, home.joints)))


def _accepted(code, operation):
    if isinstance(code, bool) or code != 0:
        raise RuntimeError(f"{operation} failed: {code!r}")


def check_home_chess(robot, *, is_current=None):
    """Read-only HOME proof immediately before operator-approved retry."""
    try:
        since = time.time()
        _guard(robot, is_current)
        home = _home_point(robot)
        source = BorrowedPhysicalStateSource(robot)
        measured = _measured_idle(robot, source, since, home, is_current)
        if not _home_matches(measured, home):
            return HomeChessRecoveryResult(False, "Measured pose/joints are not at HOMECHESS")
        return HomeChessRecoveryResult(True, "HOMECHESS verified from fresh idle TCP")
    except Exception as exc:
        return HomeChessRecoveryResult(False, f"HOME verification blocked: {type(exc).__name__}: {exc}")


def return_to_home_chess(robot, *, failure=None, is_current=None):
    """Lift at measured XY/orientation, then issue one taught HOME command.

    An unknown failed-command outcome blocks automatic dispatch. A deliberate
    later invocation without ``failure`` may recheck the fixed controller, but
    never clears any existing driver stop/authorization gate.
    """
    commanded = False
    try:
        if failure is not None and _unknown_outcome(failure, robot):
            return HomeChessRecoveryResult(False, "Previous command outcome unknown; deliberate HOME recheck required")
        since = time.time()
        _guard(robot, is_current)
        home = _home_point(robot)
        safe_z = float(config.SAFE_Z)
        if not math.isfinite(safe_z) or home.pose[2] < safe_z:
            raise RuntimeError("HOMECHESS must be at or above configured SAFE_Z")
        source = BorrowedPhysicalStateSource(robot)
        measured = _measured_idle(robot, source, since, home, is_current)
        if _home_matches(measured, home):
            return HomeChessRecoveryResult(True, "Already at measured HOMECHESS")
        lift_pose = list(measured.pose)
        lift_pose[2] = max(measured.pose[2], safe_z)
        if measured.pose[2] < lift_pose[2]:
            _guard(robot, is_current, home)
            commanded = True
            _accepted(robot.movel_pose(lift_pose, label="Recovery vertical lift"), "Recovery lift")
            measured = _measured_idle(robot, source, time.time(), home, is_current, allow_settle=True)
            if not _pose_matches(measured.pose, lift_pose):
                raise RuntimeError("Recovery lift was not confirmed at measured XY/clearance")
        _guard(robot, is_current, home)
        commanded = True
        # Dispatch the one frozen, frame-validated teaching point. Calling the
        # convenience go_to_home_chess() here would re-read a possibly edited
        # controller waypoint after the lift had already started.
        _accepted(robot.movej_joint(list(home.joints), list(home.pose), label="Recovery HOMECHESS"), "HOMECHESS")
        measured = _measured_idle(robot, source, time.time(), home, is_current, allow_settle=True)
        if not _home_matches(measured, home):
            raise RuntimeError("HOME command ended but measured pose/joints are not at HOMECHESS")
        return HomeChessRecoveryResult(True, "HOMECHESS verified; remove payload and restore board", commanded)
    except Exception as exc:
        return HomeChessRecoveryResult(False, f"HOME recovery blocked: {type(exc).__name__}: {exc}", commanded)
