"""Mode-local donor logic; physical commands are mocked throughout."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import config as shared_config
from src.modes.vsc_v3 import config as scoped_config
from src.modes.vsc_v3.adapter_config import configure
from src.modes.vsc_v3.hardware.hardware_manager import HardwareManager
from src.modes.vsc_v3.hardware.robot_VIP import FR5Robot
from src.hardware.robot_VIP import FR5Robot as CurrentRobot, RobotCommandError


def test_donor_modules_and_config_are_distinct_from_other_modes(tmp_path):
    from src.modes.vsc_v3.core.game_state import GameState as DonorState
    from src.core.game_state import GameState as SharedState
    from src.modes.vsc_v3.vision.player_turn_types import PlayerTurnMode as DonorTurn
    from src.vision.player_turn_types import PlayerTurnMode as SharedTurn
    before = vars(shared_config).copy()
    configure(shared_config, 'BOARD_ONLY', tmp_path)
    assert scoped_config is not shared_config
    assert DonorState is not SharedState and DonorTurn is not SharedTurn
    assert scoped_config.DRY_RUN
    assert scoped_config.VISUAL_PVP_PICK_ENABLED
    assert not scoped_config.VISUAL_RING_PICK_ENABLED
    assert not scoped_config.VISUAL_TOP_FACE_ENABLED
    assert vars(shared_config).keys() == before.keys()
    assert all(vars(shared_config)[key] is value for key, value in before.items())


def test_current_hardware_profile_and_wiring_override_donor_values(tmp_path):
    configure(shared_config, 'PHYSICAL', tmp_path)
    assert not scoped_config.DRY_RUN
    for name in ('GRIPPER_OPEN_DO_ID','GRIPPER_CLOSE_DO_ID','PHYSICAL_TEACHING_POINTS_FILE',
                 'ROBOT_FRAME_POLICY','SAFE_Z','PICK_Z','PLACE_Z','ROTATION','MOVE_SPEED'):
        assert getattr(scoped_config, name) == getattr(shared_config, name)
    assert scoped_config.GRIPPER_OPEN_DO_ID == 1
    assert scoped_config.GRIPPER_CLOSE_DO_ID == 0
    assert issubclass(FR5Robot, CurrentRobot)


def test_real_manager_constructor_selects_fixed_profile_without_sdk_calls(tmp_path):
    from pathlib import Path
    import shutil
    cfg = SimpleNamespace(DRY_RUN=False, ROBOT_IP='192.168.58.2',
                          PHYSICAL_TEACHING_POINTS_FILE='calibration/physical_teaching_points_user0.json')
    manager = HardwareManager(cfg, tmp_path)
    assert manager.robot.uses_fixed_teaching_points
    assert manager.robot.fixed_teaching_points_path == str(tmp_path / cfg.PHYSICAL_TEACHING_POINTS_FILE)
    assert manager.robot.ip == cfg.ROBOT_IP
    assert not manager.robot.dry
    assert manager.robot.robot is None  # Constructor never opens SDK or actuates.
    profile = tmp_path / cfg.PHYSICAL_TEACHING_POINTS_FILE
    profile.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[2] / cfg.PHYSICAL_TEACHING_POINTS_FILE, profile)
    manager.robot.connected = True
    manager.robot.robot = Mock()
    manager.robot._load_teaching_points()
    manager.robot.robot.GetRobotTeachingPoint.assert_not_called()
    manager.robot.robot.GetActualWObjNum.assert_not_called()
    manager.robot.robot.GetWObjCoordWithID.assert_not_called()
    assert manager.robot.teaching_points_error is None
    assert all(point['user'] == 0 for point in manager.robot.teaching_points.values())


def test_robot_initialization_uses_loaded_fixed_profile_without_home_or_gripper():
    manager = HardwareManager.__new__(HardwareManager)
    manager.config = SimpleNamespace()
    manager.dry_run = False
    manager.robot = Mock(connected=True, teaching_points_error=None,
                         teaching_points={'R1': {'pose': [12., 34., 50., 180., 0., 0.]}})
    manager._init_robot()
    manager.robot.connect.assert_called_once()
    manager.robot.activate_physical_control.assert_called_once_with(commissioned=True)
    manager.robot.go_to_home_chess.assert_not_called()
    manager.robot.gripper_ctrl.assert_not_called()
    manager.robot.robot.GetRobotTeachingPoint.assert_not_called()
    assert manager.config.BOARD_ORIGIN_X == 12.
    assert manager.config.BOARD_ORIGIN_Y == 34.


def test_failed_current_hardware_result_cannot_become_donor_success(monkeypatch):
    monkeypatch.setattr(CurrentRobot, 'move_piece', lambda *a, **k: SimpleNamespace(
        success=False, message='controller rejected', backend_code=112))
    robot = FR5Robot.__new__(FR5Robot)
    with pytest.raises(RobotCommandError, match='controller rejected'):
        robot.move_piece(0, 0, 0, 1, False, require_visual_target=False)


def test_mode_dry_run_never_connects_hardware():
    manager = HardwareManager.__new__(HardwareManager)
    manager.dry_run = True
    manager.robot = Mock()
    manager._init_robot()
    manager.robot.connect.assert_not_called()
    assert not manager.robot.connected


@pytest.mark.parametrize('requested,available', [(True, True), (True, False), (False, True)])
def test_scoped_onnx_prefers_gpu_but_respects_cpu_and_missing_driver(monkeypatch, requested, available):
    import sys
    import src.modes.vsc_v3.vision.cchess_recognizer as recognizer
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: available)))
    monkeypatch.setattr(recognizer.ort, 'get_available_providers', lambda: ['CUDAExecutionProvider', 'CPUExecutionProvider'])
    session = Mock()
    session.get_inputs.return_value = [SimpleNamespace(name='input')]
    factory = Mock(return_value=session)
    monkeypatch.setattr(recognizer.ort, 'InferenceSession', factory)
    recognizer.CChessRecognizer('pose.onnx', 'layout.onnx', use_gpu=requested)
    assert factory.call_count == 2
    for call in factory.call_args_list:
        providers = call.kwargs['providers']
        if requested and available:
            assert providers[0][0] == 'CUDAExecutionProvider'
        else:
            assert providers == ['CPUExecutionProvider']


@pytest.mark.parametrize('capture', [False, True])
def test_donor_sequence_preserves_logical_fallback_using_current_primitives(capture):
    robot = FR5Robot.__new__(FR5Robot)
    robot._require_actuation = Mock()
    robot.dry = True
    robot.board_to_pose = Mock()
    robot._validate_pose = Mock()
    robot.tool_num = robot.user_num = 0
    robot.teaching_points = {'R_Trash': {'pose': [0] * 6, 'joints': [0] * 6, 'tool': 0, 'user': 0}}
    robot.pick_at = Mock()
    robot.move_to_extra_safe = Mock()
    robot.place_at = Mock()
    robot.place_in_capture_bin = Mock()
    robot.go_to_home_chess = Mock()
    refreshed = Mock(return_value=None)
    verified = Mock(return_value=True)
    robot._move_piece_sequence(0, 0, 0, 1, capture, moving_visual_target=None,
        captured_visual_target=None, refresh_moving_visual_target=refreshed,
        verify_capture_cleared=verified, require_visual_target=False)
    robot._require_actuation.assert_called_once()
    refreshed.assert_called_once()
    assert robot.pick_at.call_args_list[-1].args == (0, 0)
    assert robot.pick_at.call_args_list[-1].kwargs['visual_target'] is None
    assert robot.pick_at.call_count == (2 if capture else 1)
    robot.place_at.assert_called_once_with(0, 1)
    if capture:
        verified.assert_called_once()
        robot.place_in_capture_bin.assert_called_once()
    else:
        robot.place_in_capture_bin.assert_not_called()
    assert FR5Robot.pick_at is CurrentRobot.pick_at
    assert FR5Robot.gripper_ctrl is CurrentRobot.gripper_ctrl


def test_donor_board_stability_logic_not_replaced_by_shared_hardware_overlay(tmp_path):
    source = SimpleNamespace(**vars(shared_config))
    source.BOARD_STABILITY_MIN_IDENTICAL_FRAMES = 999
    configure(source, 'PHYSICAL', tmp_path)
    assert scoped_config.ROBOT_BACKEND == 'PHYSICAL'
    assert getattr(scoped_config, 'BOARD_STABILITY_MIN_IDENTICAL_FRAMES', None) != 999
