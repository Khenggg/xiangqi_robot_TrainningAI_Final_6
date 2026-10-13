from types import SimpleNamespace
from unittest.mock import Mock
from urllib.request import urlopen
from urllib.error import HTTPError
import pytest

from src.core.launch_options import parse_options, configure_runtime, ViewerServer
from src.core.game_state import GameState
from src.core.ai_execution import execute_ai_move
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
from src.hardware.hardware_manager import HardwareManager
from src.core.self_play_controller import SelfPlayController


@pytest.mark.parametrize("argv,backend,dry,game_only", [
    ([], "VIRTUAL", True, False),
    (["--virtual"], "VIRTUAL", True, True),
    (["--physical"], "PHYSICAL", False, False),
])
def test_launch_modes(argv, backend, dry, game_only):
    cfg = SimpleNamespace()
    configure_runtime(cfg, parse_options(argv))
    assert (cfg.ROBOT_BACKEND, cfg.DRY_RUN, cfg.GAME_ONLY) == (backend, dry, game_only)


def test_invalid_cli_modes():
    for argv in (["--virtual", "--physical"], ["--viewer-port", "0"],
                 ["--viewer-port", "8765"]):
        with pytest.raises(SystemExit):
            parse_options(argv)


def test_game_only_ai_never_uses_motion_or_camera():
    state = GameState()
    state.turn = "b"
    cfg = SimpleNamespace(GAME_ONLY=True, ROBOT_BACKEND="VIRTUAL")
    hw = SimpleNamespace(config=cfg, is_robot_ready=True,
                         execute_piece_move=Mock(), verify_physical_board=Mock())
    assert execute_ai_move(state, hw, ((0, 3), (0, 4)), dry_run=True)
    assert state.board[4][0] == "b_P" and state.turn == "r"
    hw.execute_piece_move.assert_not_called()
    hw.verify_physical_board.assert_not_called()


@pytest.mark.parametrize("operation", ["reset", "rollback", "undo"])
@pytest.mark.parametrize("game_only", [True, False])
def test_game_only_history_controls_do_not_require_physical_reconciliation(operation, game_only):
    state = GameState()
    state.api_client.send_move_update_board = Mock()
    hw = SimpleNamespace(config=SimpleNamespace(GAME_ONLY=game_only, ROBOT_BACKEND="VIRTUAL" if game_only else "PHYSICAL"),
                         dry_run=game_only, simulation_runtime=None,
                         capture_baseline_if_needed=Mock(), restore_yolo_baseline=Mock())
    if not game_only:
        state.set_board_observer(Mock(return_value=True))
    state.save_rollback_state()
    assert state.process_human_move((4, 6), (4, 5), "r_P")
    if operation == "reset":
        state.reset_game(hw)
    elif operation == "rollback":
        state.handle_rollback(hw)
    else:
        assert state.undo_round(hw)
    assert state.board[6][4] == "r_P" and state.turn == "r"
    assert state.physical_sync_fault is (not game_only and operation != "undo")
    assert bool(state.move_sync_error) is (not game_only)
    if game_only:
        assert state.process_human_move((4, 6), (4, 5), "r_P")



def test_game_only_initialization_skips_both_devices():
    hw = SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True), _init_ai=Mock(),
                         _init_robot=Mock(), _init_camera=Mock())
    assert HardwareManager.initialize_all(hw) is hw
    hw._init_ai.assert_called_once()
    hw._init_robot.assert_not_called()
    hw._init_camera.assert_not_called()


def test_new_game_discards_previous_space_rollback():
    state = GameState()
    state.api_client.send_move_update_board = Mock()
    hw = SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True, ROBOT_BACKEND="VIRTUAL"),
                         dry_run=True, simulation_runtime=None)
    assert state.process_human_move((4, 6), (4, 5), "r_P")
    state.save_rollback_state()
    state.reset_game(hw)
    initial = state.current_fen
    state.handle_rollback(hw)
    assert state.current_fen == initial
    assert state._pre_space_state is None


def test_game_only_self_play_motion_adapter_never_uses_robot():
    hw = SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True, ROBOT_BACKEND="VIRTUAL"),
                         dry_run=True, robot=SimpleNamespace(move_piece=Mock()))
    assert HardwareManager.execute_piece_move(hw).success
    hw.robot.move_piece.assert_not_called()
    hw.config.ROBOT_BACKEND = "PHYSICAL"
    assert not HardwareManager.execute_piece_move(hw).success
    hw.robot.move_piece.assert_not_called()


def test_game_only_self_play_commits_without_a_simulator():
    state = GameState()
    state.api_client.send_move_update_board = Mock()
    hw = SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True, ROBOT_BACKEND="VIRTUAL"),
                         dry_run=True, is_robot_ready=True, simulation_runtime=None,
                         difficulty_availability=lambda: {"easy": True},
                         ai_ctrl=SimpleNamespace(pick_move=lambda board, **kw: ((0, 6), (0, 5))))
    hw.execute_piece_move = lambda **kwargs: HardwareManager.execute_piece_move(hw, **kwargs)
    controller = SelfPlayController(state, hw)
    assert controller.start("easy", "easy", run_mode="step")
    assert controller.request_next_move()
    controller._thread.join(2)
    controller.tick()
    controller._thread.join(2)
    controller.tick()
    assert state.board[5][0] == "r_P" and state.turn == "b"
    assert not state.physical_sync_fault and not state.move_sync_error


def test_human_sync_failure_is_not_reported_as_accepted():
    state = GameState()
    state.api_client.send_move_update_board = Mock()
    state.set_board_observer(lambda cells: False)
    request = SimpleNamespace(turn_token=(0, 0), move=((4, 6), (4, 5)))
    coordinator = HumanMoveCommitCoordinator(state)
    assert coordinator.try_commit(request) == "REJECTED"
    assert state.physical_sync_fault and state.move_sync_error
    assert state.snapshot_continue_required
    # The already observed move remains coherent in FEN and identities.
    assert state.board[5][4] == "r_P" and state.turn == "b"
    assert state.current_fen.split()[1] == "b"
    assert coordinator.try_commit(request) == "STALE"
    state.api_client.send_move_update_board.assert_not_called()


def test_enable_requires_operator_camera_and_idle_twin():
    state = GameState()
    robot = SimpleNamespace(connected=True, activate_physical_control=Mock(return_value=True))
    twin = SimpleNamespace(_board_observation_ready=Mock(return_value=True))
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL"), dry_run=False,
                         robot=robot, twin_bridge=twin, board_pose_provider=object(),
                         _piece_move_lock=SimpleNamespace(locked=lambda: False),
                         verify_physical_board=Mock(return_value=False))
    with pytest.raises(RuntimeError):
        HardwareManager.activate_physical_game(hw, state)
    with pytest.raises(RuntimeError):
        HardwareManager.activate_physical_game(hw, state, commissioned=True)
    robot.activate_physical_control.assert_not_called()
    hw.verify_physical_board.return_value = True
    twin._board_observation_ready.return_value = False
    with pytest.raises(RuntimeError):
        HardwareManager.activate_physical_game(hw, state, commissioned=True)
    robot.activate_physical_control.assert_not_called()
    twin._board_observation_ready.return_value = True
    assert HardwareManager.activate_physical_game(hw, state, commissioned=True)
    robot.activate_physical_control.assert_called_once_with(commissioned=True)
    robot.activate_physical_control.reset_mock()
    state.physical_sync_fault = True
    with pytest.raises(RuntimeError):
        HardwareManager.activate_physical_game(hw, state, commissioned=True)
    robot.activate_physical_control.assert_not_called()


def test_viewer_server_serves_assets_but_not_repo_secrets(tmp_path, monkeypatch):
    (tmp_path / "robot-3d-viewer").mkdir()
    (tmp_path / "robot-3d-viewer" / "index.html").write_text("viewer")
    (tmp_path / "secret.txt").write_text("private")
    monkeypatch.setattr("src.core.launch_options.webbrowser.open", Mock())
    server = ViewerServer(tmp_path, 0)
    server.start(8765)
    try:
        assert urlopen(server.url).read() == b"viewer"
        with pytest.raises(HTTPError) as error:
            urlopen(server.url + "../secret.txt")
        assert error.value.code == 403
    finally:
        server.close()


def test_viewer_serves_local_three_without_exposing_package_or_traversal(tmp_path, monkeypatch):
    three = tmp_path / 'node_modules' / 'three'
    for relative in ('build/three.module.js', 'examples/jsm/controls/OrbitControls.js'):
        target = three / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('export {};', encoding='utf-8')
    (three / 'package.json').write_text('{}')
    (tmp_path / 'secret.js').write_text('private')
    monkeypatch.setattr('src.core.launch_options.webbrowser.open', Mock())
    server = ViewerServer(tmp_path, 0)
    server.start(8765)
    origin = server.url.removesuffix('robot-3d-viewer/')
    try:
        for relative in ('build/three.module.js', 'examples/jsm/controls/OrbitControls.js'):
            with urlopen(origin + 'vendor/three/' + relative) as response:
                assert response.read() == b'export {};'
                assert 'javascript' in response.headers['Content-Type']
        for relative in ('package.json', 'build/%2e%2e/%2e%2e/%2e%2e/secret.js'):
            with pytest.raises(HTTPError) as error:
                urlopen(origin + 'vendor/three/' + relative)
            assert error.value.code == 403
    finally:
        server.close()
