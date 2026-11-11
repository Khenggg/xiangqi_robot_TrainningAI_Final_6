"""Recovery commands are tested with fake measured states, never a controller."""
from types import SimpleNamespace
import threading
import time
from unittest.mock import Mock

import pytest

from src.hardware import home_chess_recovery as recovery
from src.hardware.robot_VIP import FR5Robot, RobotCommandError
from src.hardware.rpc_transport import RpcOutcomeUnknown


@pytest.fixture
def arm(monkeypatch):
    home = [100., 150., 350., 180., 0., 90.]
    robot = SimpleNamespace(
        dry=False, connected=True, physical_motion_authorized=True, user_num=0, tool_num=0,
        _disable_outcome_unknown=False, _gripper_pulse_active=False,
        _motion_stop=threading.Event(), last_motion_result=None,
        pose=[200., 250., 100., 180., 0., 90.], joints=[20.] * 6, home=home,
        gripper_ctrl=Mock(), activate_physical_control=Mock(),
        send_controlled_stop=Mock(), _validate_pose=FR5Robot._validate_pose,
        _verify_waypoint_frame=Mock(),
        read_teaching_point=Mock(return_value=(0, home + [0.] * 6 + [0, 0])),
    )
    def require_actuation():
        if robot._motion_stop.is_set():
            raise RobotCommandError('Stop latched')
    robot._require_actuation = Mock(side_effect=require_actuation)
    def lift(pose, **kwargs):
        robot.pose = list(pose)
        return 0
    def go_home(joints, pose, **kwargs):
        robot.pose = list(pose)
        robot.joints = list(joints)
        return 0
    robot.robot = SimpleNamespace()
    robot.movel_pose = Mock(side_effect=lift)
    robot.movej_joint = Mock(side_effect=go_home)
    robot.go_to_home_chess = Mock()
    robot.measurement_factory = lambda: SimpleNamespace(
        connected=True, joints_valid=True, tcp_valid=True, motion_state='IDLE',
        last_error=None, measurement_timestamp=time.time(), tcp_pose_mm_deg=list(robot.pose),
        joints_deg=list(robot.joints))
    source = SimpleNamespace(_reader=SimpleNamespace(_rpc=robot.robot))
    robot.packet_tool, robot.packet_user = 0, 0
    def take_snapshot():
        snapshot = robot.measurement_factory()
        source._reader._measurement_timestamp = snapshot.measurement_timestamp
        source._reader._last_stream_packet = SimpleNamespace(
            tool=robot.packet_tool, user=robot.packet_user,
            tl_cur_pos=list(snapshot.tcp_pose_mm_deg), jt_cur_pos=list(snapshot.joints_deg))
        return snapshot
    source.get_state_snapshot = Mock(side_effect=take_snapshot)
    robot.source = source
    monkeypatch.setattr(recovery, 'BorrowedPhysicalStateSource', Mock(return_value=source))
    monkeypatch.setattr(recovery.config, 'SAFE_Z', 220.)
    # Windows wall-clock packet stamps can repeat for a scheduler tick; leave
    # enough time for two distinct stamps even when another suite is running.
    monkeypatch.setattr(recovery, 'MEASUREMENT_TIMEOUT_S', .2)
    monkeypatch.setattr(recovery, 'MEASUREMENT_POLL_INTERVAL_S', .001)
    return robot


def assert_no_commands(robot):
    robot.movel_pose.assert_not_called()
    robot.movej_joint.assert_not_called()
    robot.go_to_home_chess.assert_not_called()
    robot.gripper_ctrl.assert_not_called()
    robot.activate_physical_control.assert_not_called()
    robot.send_controlled_stop.assert_not_called()


def test_lift_keeps_measured_xy_and_orientation_then_home_once(arm):
    result = recovery.return_to_home_chess(arm, failure=RobotCommandError('Known command rejection', 9))
    assert result.at_home and result.commanded
    arm.movel_pose.assert_called_once_with([200., 250., 220., 180., 0., 90.], label='Recovery vertical lift')
    arm.movej_joint.assert_called_once_with([0.] * 6, arm.home, label='Recovery HOMECHESS')
    arm.go_to_home_chess.assert_not_called()
    arm.gripper_ctrl.assert_not_called()
    arm.activate_physical_control.assert_not_called()
    arm.send_controlled_stop.assert_not_called()
    assert not arm._motion_stop.is_set()
    assert arm.source.get_state_snapshot.call_count >= 6


def test_above_clearance_goes_home_without_lowering(arm):
    arm.pose[2] = 300.
    result = recovery.return_to_home_chess(arm)
    assert result.at_home
    arm.movel_pose.assert_not_called()
    arm.movej_joint.assert_called_once()


def test_existing_driver_dispatch_binding_cannot_be_bypassed(arm):
    arm.dispatch_validity = Mock(side_effect=RuntimeError('Stale driver binding'))
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'Stale driver binding' in result.reason
    assert_no_commands(arm)


def test_driver_binding_is_rechecked_between_lift_and_home(arm):
    arm.dispatch_validity = Mock()
    def lift(pose, **kwargs):
        arm.pose = list(pose)
        arm.dispatch_validity.side_effect = RuntimeError('Driver binding changed')
        return 0
    arm.movel_pose.side_effect = lift
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'Driver binding changed' in result.reason
    arm.movel_pose.assert_called_once()
    arm.movej_joint.assert_not_called()
    arm.gripper_ctrl.assert_not_called()


def test_already_home_is_read_only_and_accepts_wrapped_angles(arm):
    arm.pose = list(arm.home)
    arm.joints = [0.] * 6
    arm.pose[3] -= 360.
    result = recovery.return_to_home_chess(arm)
    assert result.at_home and not result.commanded
    assert_no_commands(arm)


@pytest.mark.parametrize('guard', ['disconnected', 'unauthorized', 'stop', 'pulse', 'disable_unknown', 'frame', 'dry'])
def test_driver_guards_reject_before_any_motion(arm, guard):
    if guard == 'disconnected': arm.connected = False
    elif guard == 'unauthorized': arm.physical_motion_authorized = False
    elif guard == 'stop': arm._motion_stop.set()
    elif guard == 'pulse': arm._gripper_pulse_active = True
    elif guard == 'disable_unknown': arm._disable_outcome_unknown = True
    elif guard == 'frame': arm.user_num = 1
    elif guard == 'dry': arm.dry = True
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and not result.commanded
    assert_no_commands(arm)


@pytest.mark.parametrize('kind', ['direct', 'wrapped', 'metadata', 'oserror'])
def test_unknown_outcome_never_automatically_dispatches_home(arm, kind):
    failure = RpcOutcomeUnknown('No reply')
    if kind == 'wrapped':
        wrapper = RobotCommandError('Wrapped error')
        wrapper.__cause__ = failure
        failure = wrapper
    elif kind == 'metadata':
        arm.last_motion_result = SimpleNamespace(metadata={'rpc_outcome_unknown': True})
        failure = RobotCommandError('Donor wrapper loses exception type')
    elif kind == 'oserror': failure = TimeoutError('Lost connection')
    result = recovery.return_to_home_chess(arm, failure=failure)
    assert not result.at_home and 'unknown' in result.reason
    assert_no_commands(arm)


def test_deliberate_recheck_after_unknown_failure_still_requires_measured_idle(arm):
    arm.last_motion_result = SimpleNamespace(metadata={'rpc_outcome_unknown': True})
    result = recovery.return_to_home_chess(arm)
    assert result.at_home
    arm.movej_joint.assert_called_once()


@pytest.mark.parametrize('invalid', ['moving', 'fault', 'tcp_invalid', 'joints_invalid', 'disconnected', 'stale', 'duplicate', 'nonfinite'])
def test_invalid_or_unsettled_measurements_do_not_dispatch_motion(arm, invalid):
    stamp = time.time()
    def snapshot():
        return SimpleNamespace(
            connected=invalid != 'disconnected', joints_valid=invalid != 'joints_invalid',
            tcp_valid=invalid != 'tcp_invalid', motion_state='MOVING' if invalid == 'moving' else 'IDLE',
            last_error='Controller fault' if invalid == 'fault' else None,
            measurement_timestamp=stamp - 2 if invalid == 'stale' else stamp if invalid == 'duplicate' else time.time(),
            tcp_pose_mm_deg=[float('nan')] * 6 if invalid == 'nonfinite' else list(arm.pose),
            joints_deg=list(arm.joints))
    arm.measurement_factory = snapshot
    assert not recovery.return_to_home_chess(arm).at_home
    assert_no_commands(arm)


@pytest.mark.parametrize('bad_home', ['missing', 'frame', 'joints', 'below_clearance'])
def test_home_is_validated_before_lift(arm, bad_home):
    if bad_home == 'missing': arm.read_teaching_point.return_value = (1, [])
    elif bad_home == 'frame': arm._verify_waypoint_frame.side_effect = RobotCommandError('Wrong tool/user')
    elif bad_home == 'joints':
        point = list(arm.read_teaching_point.return_value[1]); point[6] = float('nan')
        arm.read_teaching_point.return_value = (0, point)
    elif bad_home == 'below_clearance':
        point = list(arm.read_teaching_point.return_value[1]); point[2] = 100.
        arm.read_teaching_point.return_value = (0, point)
    assert not recovery.return_to_home_chess(arm).at_home
    assert_no_commands(arm)


@pytest.mark.parametrize('code', [6, False])
def test_failed_lift_does_not_dispatch_home(arm, code):
    arm.movel_pose.side_effect = None
    arm.movel_pose.return_value = code
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and result.commanded
    arm.movel_pose.assert_called_once()
    arm.movej_joint.assert_not_called()


def test_lift_success_without_measured_clearance_does_not_dispatch_home(arm):
    arm.movel_pose.side_effect = None
    arm.movel_pose.return_value = 0
    assert not recovery.return_to_home_chess(arm).at_home
    arm.movej_joint.assert_not_called()


def test_home_unknown_result_has_no_second_dispatch(arm):
    arm.movej_joint.side_effect = RpcOutcomeUnknown('HOME reply lost')
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home
    arm.movej_joint.assert_called_once()
    arm.gripper_ctrl.assert_not_called()


def test_lift_unknown_result_does_not_dispatch_home_or_replay_lift(arm):
    arm.movel_pose.side_effect = RpcOutcomeUnknown('Lift reply lost')
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home
    arm.movel_pose.assert_called_once()
    arm.movej_joint.assert_not_called()


def test_home_accepted_with_stale_post_motion_telemetry_is_not_success(arm):
    def home_without_new_packet(joints, pose, **kwargs):
        arm.pose = list(arm.home)
        stamp = time.time() - 2
        arm.measurement_factory = lambda: SimpleNamespace(
            connected=True, joints_valid=True, tcp_valid=True, motion_state='IDLE',
            last_error=None, measurement_timestamp=stamp, tcp_pose_mm_deg=list(arm.pose),
            joints_deg=list(arm.joints))
        return 0
    arm.movej_joint.side_effect = home_without_new_packet
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home
    arm.movej_joint.assert_called_once()


def test_home_must_be_measured_not_assumed_from_command_acceptance(arm):
    arm.movej_joint.side_effect = None
    arm.movej_joint.return_value = 0
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'not at HOMECHESS' in result.reason
    arm.movej_joint.assert_called_once()


def test_stop_arriving_after_lift_prevents_home_and_is_preserved(arm):
    def lift(pose, **kwargs):
        arm.pose = pose
        arm._motion_stop.set()
        return 0
    arm.movel_pose.side_effect = lift
    assert not recovery.return_to_home_chess(arm).at_home
    arm.movej_joint.assert_not_called()
    assert arm._motion_stop.is_set()


@pytest.mark.parametrize('at_home', [True, False])
def test_check_home_is_read_only(arm, at_home):
    if at_home:
        arm.pose = list(arm.home)
        arm.joints = [0.] * 6
    result = recovery.check_home_chess(arm)
    assert result.at_home is at_home
    assert_no_commands(arm)


@pytest.mark.parametrize('operation', [recovery.return_to_home_chess, recovery.check_home_chess])
@pytest.mark.parametrize('field,value', [
    ('packet_tool', 1), ('packet_user', 1), ('packet_tool', None),
    ('packet_user', None), ('packet_tool', True), ('packet_user', 0.5),
    ('packet_tool', '0'), ('packet_user', -1),
])
def test_measured_packet_frame_must_match_command_frame(arm, operation, field, value):
    setattr(arm, field, value)
    result = operation(arm)
    assert not result.at_home and ('frame' in result.reason or 'tool/user' in result.reason)
    assert_no_commands(arm)


@pytest.mark.parametrize('provenance', ['missing_packet', 'wrong_sdk', 'different_stamp', 'different_tcp'])
def test_snapshot_and_frame_must_come_from_the_same_pinned_packet(arm, provenance):
    original = arm.source.get_state_snapshot.side_effect
    def changed_snapshot():
        snapshot = original()
        reader = arm.source._reader
        if provenance == 'missing_packet': reader._last_stream_packet = None
        elif provenance == 'wrong_sdk': reader._rpc = object()
        elif provenance == 'different_stamp': reader._measurement_timestamp -= .01
        elif provenance == 'different_tcp': reader._last_stream_packet.tl_cur_pos[0] += 1.
        return snapshot
    arm.source.get_state_snapshot.side_effect = changed_snapshot
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and ('provenance' in result.reason or 'packet' in result.reason)
    assert_no_commands(arm)


def test_home_dispatch_uses_frozen_validated_point_even_if_teaching_data_changes(arm):
    point = arm.read_teaching_point.return_value[1]
    def lift_and_change_teaching(pose, **kwargs):
        arm.pose = list(pose)
        point[0], point[6] = 800., 120.
        return 0
    arm.movel_pose.side_effect = lift_and_change_teaching
    assert recovery.return_to_home_chess(arm).at_home
    arm.read_teaching_point.assert_called_once_with('HOMECHESS')
    arm.movej_joint.assert_called_once_with([0.] * 6, arm.home, label='Recovery HOMECHESS')
    arm.go_to_home_chess.assert_not_called()


def test_changed_driver_frame_after_lift_prevents_home(arm):
    def lift_and_change_tool(pose, **kwargs):
        arm.pose = list(pose)
        arm.tool_num = 1
        return 0
    arm.movel_pose.side_effect = lift_and_change_tool
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'frame changed' in result.reason
    arm.movej_joint.assert_not_called()


def test_changed_measured_frame_after_lift_prevents_home(arm):
    def lift_and_change_packet_tool(pose, **kwargs):
        arm.pose = list(pose)
        arm.packet_tool = 1
        return 0
    arm.movel_pose.side_effect = lift_and_change_packet_tool
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'tool/user' in result.reason
    arm.movej_joint.assert_not_called()


@pytest.mark.parametrize('operation', [recovery.return_to_home_chess, recovery.check_home_chess])
def test_stale_pending_move_blocks_before_any_command(arm, operation):
    result = operation(arm, is_current=lambda: False)
    assert not result.at_home and 'pending move' in result.reason
    assert_no_commands(arm)


def test_pending_move_changed_after_lift_blocks_home(arm):
    current = True
    def lift_and_retire_pending(pose, **kwargs):
        nonlocal current
        arm.pose = list(pose)
        current = False
        return 0
    arm.movel_pose.side_effect = lift_and_retire_pending
    result = recovery.return_to_home_chess(arm, is_current=lambda: current)
    assert not result.at_home and 'pending move' in result.reason
    arm.movej_joint.assert_not_called()


@pytest.mark.parametrize('stage', ['lift', 'home'])
def test_own_accepted_motion_may_settle_from_fresh_moving_to_idle_without_resend(arm, stage):
    method = arm.movel_pose if stage == 'lift' else arm.movej_joint
    original_command = method.side_effect
    original_measurement = arm.measurement_factory
    remaining_moving = 3
    def accepted_with_lag(*args, **kwargs):
        nonlocal remaining_moving
        code = original_command(*args, **kwargs)
        def lagging_measurement():
            nonlocal remaining_moving
            snapshot = original_measurement()
            if remaining_moving:
                remaining_moving -= 1
                snapshot.motion_state = 'MOVING'
            return snapshot
        arm.measurement_factory = lagging_measurement
        return code
    method.side_effect = accepted_with_lag
    result = recovery.return_to_home_chess(arm)
    assert result.at_home
    arm.movel_pose.assert_called_once()
    arm.movej_joint.assert_called_once()


@pytest.mark.parametrize('state', ['MOVING', 'ERROR'])
def test_unsettled_own_home_stays_failed_without_resend(arm, state):
    original_measurement = arm.measurement_factory
    def accepted_home(joints, pose, **kwargs):
        arm.pose = list(pose)
        def unsettled_measurement():
            snapshot = original_measurement()
            snapshot.motion_state = state
            return snapshot
        arm.measurement_factory = unsettled_measurement
        return 0
    arm.movej_joint.side_effect = accepted_home
    assert not recovery.return_to_home_chess(arm).at_home
    arm.movej_joint.assert_called_once()


@pytest.mark.parametrize('packet_tool,replace_current_packet,accepted', [
    (0, False, True), (1, False, False), (0, True, True),
])
def test_frame_provenance_with_actual_borrowed_physical_reader(
        arm, monkeypatch, packet_tool, replace_current_packet, accepted):
    from src.hardware.simulation_adapter import BorrowedPhysicalStateSource
    arm.ip = 'offline-test'
    source = BorrowedPhysicalStateSource(arm)
    read = source.get_state_snapshot
    def next_packet():
        arm.robot.robot_state_pkg = SimpleNamespace(
            jt_cur_pos=list(arm.joints), tl_cur_pos=list(arm.pose), flange_cur_pos=[0.] * 6,
            EmergencyStop=0, main_code=0, sub_code=0, motion_done=1,
            tool=packet_tool, user=0)
        snapshot = read()
        if replace_current_packet:
            # A later SDK receive must not supply frame metadata for the
            # already returned snapshot. The reader retains its exact packet.
            arm.robot.robot_state_pkg = SimpleNamespace(tool=99, user=99)
        return snapshot
    source.get_state_snapshot = next_packet
    monkeypatch.setattr(recovery, 'BorrowedPhysicalStateSource', lambda robot: source)
    result = recovery.return_to_home_chess(arm)
    assert result.at_home is accepted
    if not accepted:
        assert_no_commands(arm)


def test_same_tcp_on_different_ik_branch_dispatches_taught_home_joints(arm):
    arm.pose = list(arm.home)
    arm.joints = [20.] * 6
    result = recovery.return_to_home_chess(arm)
    assert result.at_home and result.commanded
    arm.movel_pose.assert_not_called()
    arm.movej_joint.assert_called_once_with([0.] * 6, arm.home, label='Recovery HOMECHESS')


@pytest.mark.parametrize('joint_error,accepted', [(.5, True), (1.1, False), (360., False)])
def test_read_only_home_requires_taught_joints_without_winding_equivalence(arm, joint_error, accepted):
    arm.pose = list(arm.home)
    arm.joints = [joint_error] + [0.] * 5
    assert recovery.check_home_chess(arm).at_home is accepted
    assert_no_commands(arm)


def test_home_tcp_arrival_with_wrong_joint_branch_remains_failed(arm):
    def wrong_branch(joints, pose, **kwargs):
        arm.pose = list(pose)
        arm.joints = [20.] * 6
        return 0
    arm.movej_joint.side_effect = wrong_branch
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'joints' in result.reason
    arm.movej_joint.assert_called_once()


@pytest.mark.parametrize('joints', [[float('nan')] * 6, [float('inf')] * 6, [0.] * 5, []])
def test_unknown_nonfinite_or_incomplete_joints_deny_recovery(arm, joints):
    arm.joints = joints
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'joints' in result.reason
    assert_no_commands(arm)


def test_joint_measurement_must_match_pinned_packet(arm):
    original = arm.source.get_state_snapshot.side_effect
    def mismatched_joints():
        snapshot = original()
        arm.source._reader._last_stream_packet.jt_cur_pos[0] += 10.
        return snapshot
    arm.source.get_state_snapshot.side_effect = mismatched_joints
    result = recovery.return_to_home_chess(arm)
    assert not result.at_home and 'pinned' in result.reason
    assert_no_commands(arm)


@pytest.mark.parametrize('wrapped', [False, True])
def test_move_result_preserves_unknown_rpc_outcome_through_donor_wrapper(arm, wrapped):
    arm._gripper_hold_active = False
    arm._stop_hold_after_failure = lambda exc: FR5Robot._stop_hold_after_failure(arm, exc)
    failure = RpcOutcomeUnknown('MoveCart outcome unknown')
    if wrapped:
        outer = RuntimeError('Wrapped operation failure')
        outer.__cause__ = failure
        failure = outer
    arm._move_piece_sequence = Mock(side_effect=failure)
    result = FR5Robot.move_piece(arm, 0, 3, 0, 4, False)
    assert not result.success and result.metadata['rpc_outcome_unknown'] is True
