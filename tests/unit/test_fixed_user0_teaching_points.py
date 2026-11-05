"""Fixed physical command coordinates never query controller teaching/WObj data."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.hardware import robot_VIP
from src.hardware.hardware_manager import HardwareManager
from src.hardware.simulation_adapter import physical_board_provider


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'calibration/physical_teaching_points_user0.json'
READS = ('GetRobotTeachingPoint', 'GetActualWObjNum', 'GetCurWObjCoord', 'GetWObjCoordWithID')


def fixed_robot(monkeypatch, path=PROFILE):
    sdk = SimpleNamespace(SDK_state=True)
    for name in READS:
        setattr(sdk, name, Mock(side_effect=AssertionError('Unexpected controller coordinate read: '+name)))
    for name in ('Mode', 'RobotEnable', 'MoveCart', 'MoveJ', 'SetToolDO'):
        setattr(sdk, name, Mock(return_value=0))
    monkeypatch.setattr(robot_VIP, 'robot_sdk_core', SimpleNamespace(RPC=Mock(return_value=sdk)))
    return robot_VIP.FR5Robot(dry_run=False, teaching_points_path=path), sdk


def assert_no_coordinate_reads(sdk):
    for name in READS:
        getattr(sdk, name).assert_not_called()


def test_fixed_profile_preserves_recorded_values_and_normalizes_only_user_metadata():
    frozen = json.loads(PROFILE.read_text(encoding='utf-8'))
    recorded = json.loads((ROOT / frozen['provenance']['source']).read_text(encoding='utf-8-sig'))
    assert set(frozen['points']) == {'R1', 'R2', 'R3', 'R4', 'HOMECHESS', 'R_Trash'}
    for name, point in frozen['points'].items():
        assert point['pose'] == recorded['points'][name]['pose_mm_deg']
        assert point['joints'] == recorded['points'][name]['joints_deg']
        assert point['tool'] == recorded['points'][name]['tool_frame'] == 0
        assert point['user'] == 0


def test_fixed_connection_and_mirror_use_same_points_without_controller_reads(monkeypatch, tmp_path):
    from src.domain.board_pose_provider import CANONICAL_WIDTH_MM, CANONICAL_LENGTH_MM
    # Synthetic dimensions for the optional mirror contract. No claim that the
    # recorded physical setup has a measured board surface or matching mesh.
    payload = json.loads(PROFILE.read_text(encoding='utf-8'))
    for name, x, y in [('R1', -200., 100.), ('R2', -200.+CANONICAL_WIDTH_MM, 100.),
                       ('R3', -200.+CANONICAL_WIDTH_MM, 100.+CANONICAL_LENGTH_MM),
                       ('R4', -200., 100.+CANONICAL_LENGTH_MM)]:
        payload['points'][name]['pose'][:2] = [x, y]
    profile = tmp_path / 'synthetic-user0.json'
    profile.write_text(json.dumps(payload), encoding='utf-8')
    robot, sdk = fixed_robot(monkeypatch, profile)
    assert robot.connect() and robot.teaching_points_error is None
    assert robot.tool_num == robot.user_num == 0
    assert not robot.physical_motion_authorized
    sdk.RobotEnable.assert_not_called()
    sdk.SetToolDO.assert_not_called()
    cfg = SimpleNamespace(BOARD_CALIBRATION_MODEL='XY_SE2',
        BOARD_CALIBRATION_GRID_DIMENSIONS_MM=[CANONICAL_WIDTH_MM, CANONICAL_LENGTH_MM],
        BOARD_CALIBRATION_PROVENANCE='SYNTHETIC_TEST_ONLY', BOARD_SURFACE_Z_SOURCE='MEASURED',
        BOARD_CALIBRATION_SURFACE_Z_MM=0., ROBOT_USER_FRAME=0, ROBOT_TOOL_FRAME=0)
    provider = physical_board_provider(robot, cfg)
    assert provider.is_calibrated
    assert_no_coordinate_reads(sdk)


def test_real_manager_selects_fixed_profile_relative_to_project(monkeypatch):
    _, sdk = fixed_robot(monkeypatch)
    cfg = SimpleNamespace(**{name: getattr(config, name) for name in dir(config) if name.isupper()})
    cfg.ROBOT_BACKEND, cfg.DRY_RUN, cfg.GAME_MODE = 'PHYSICAL', False, 'HUMAN_VS_ROBOT'
    cfg.SESSION_PROFILE = None
    manager = HardwareManager(cfg, ROOT)
    manager._init_robot()
    assert manager.robot.uses_fixed_teaching_points
    assert Path(manager.robot.fixed_teaching_points_path) == PROFILE
    assert manager.robot.teaching_points_error is None
    assert manager.backend is not None  # Optional mirror still needs its independent geometry/Z setup.
    assert_no_coordinate_reads(sdk)
    sdk.RobotEnable.assert_not_called()


def test_move_and_capture_get_home_and_bin_from_fixed_profile(monkeypatch):
    robot, sdk = fixed_robot(monkeypatch)
    assert robot.connect()
    for name in ('GRIPPER_OPEN_MAX_PULSE_SEC', 'GRIPPER_CLOSE_PULSE_SEC',
                 'GRIPPER_SAFE_GAP_CLOSE_PULSE_SEC', 'GRIPPER_OPEN_SETTLE_SEC',
                 'GRIPPER_CLOSE_SETTLE_SEC', 'GRIPPER_DIRECTION_DEADTIME_SEC'):
        monkeypatch.setattr(config, name, 0.)
    assert robot.activate_physical_control(commissioned=True)
    assert robot.move_piece(0, 3, 0, 4, False).success
    assert robot.move_piece(0, 4, 0, 5, True, verify_capture_cleared=lambda: True).success
    assert_no_coordinate_reads(sdk)
    home = robot.teaching_points['HOMECHESS']
    trash = robot.teaching_points['R_Trash']
    joint_targets = [call.kwargs['joint_pos'] for call in sdk.MoveJ.call_args_list]
    assert home['joints'] in joint_targets and trash['joints'] in joint_targets
    for call in sdk.MoveCart.call_args_list + sdk.MoveJ.call_args_list:
        assert call.kwargs['tool'] == call.kwargs['user'] == 0


@pytest.mark.parametrize('fault', ['missing_home', 'foreign_user', 'units', 'nan_joints', 'degenerate_corners'])
def test_invalid_fixed_profile_blocks_enable_without_live_fallback(monkeypatch, tmp_path, fault):
    payload = copy.deepcopy(json.loads(PROFILE.read_text(encoding='utf-8')))
    if fault == 'missing_home':
        del payload['points']['HOMECHESS']
    elif fault == 'foreign_user':
        payload['points']['R1']['user'] = 1
    elif fault == 'units':
        payload['position_unit'] = 'm'
    elif fault == 'nan_joints':
        payload['points']['HOMECHESS']['joints'][0] = float('nan')
    else:
        payload['points']['R2'] = copy.deepcopy(payload['points']['R1'])
    path = tmp_path / 'fixed.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    robot, sdk = fixed_robot(monkeypatch, path)
    assert robot.connect() and robot.teaching_points_error
    assert not robot.teaching_points
    with pytest.raises(robot_VIP.RobotCommandError):
        robot.activate_physical_control(commissioned=True)
    assert_no_coordinate_reads(sdk)
    sdk.RobotEnable.assert_not_called()


def test_missing_fixed_profile_never_falls_back_to_controller(monkeypatch, tmp_path):
    robot, sdk = fixed_robot(monkeypatch, tmp_path / 'missing.json')
    assert robot.connect() and robot.teaching_points_error
    with pytest.raises(robot_VIP.RobotCommandError):
        robot.activate_physical_control(commissioned=True)
    assert_no_coordinate_reads(sdk)
    sdk.RobotEnable.assert_not_called()
