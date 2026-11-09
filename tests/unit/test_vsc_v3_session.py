from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from src.modes.vsc_v3_session import VscV3Session, VscV3Showcase, committed_piece_cells
from src.domain.game_move import initial_piece_identities


def initial_board():
    from src.modes.vsc_v3.core import xiangqi
    return xiangqi.get_board()


def test_identity_projection_tracks_move_capture_and_reset():
    board = initial_board()
    canonical = initial_piece_identities()
    history = [{'src':(0,6), 'dst':(0,5), 'turn':'r'}]
    board[5][0], board[6][0] = board[6][0], '.'
    moved = committed_piece_cells(board, history)
    assert moved[5,0] == canonical[6,0]
    # Reset/rollback is derived from committed state, not a missed FEN hook.
    assert committed_piece_cells(initial_board(), []) == canonical
    history.append({'src':(0,3), 'dst':(0,5), 'turn':'b'})
    board[5][0], board[3][0] = board[3][0], '.'
    captured = committed_piece_cells(board, history)
    assert captured[5,0] == canonical[3,0]
    assert canonical[6,0] not in captured.values()


def test_scanned_position_projection_never_modifies_input_board():
    board = initial_board()
    board[5][0], board[6][0] = board[6][0], '.'
    before = deepcopy(board)
    cells = committed_piece_cells(board, [])
    assert cells[5,0].startswith('red_pawn')
    assert board == before


@pytest.fixture
def donor_session(monkeypatch):
    import src.modes.vsc_v3.core.game_state as donor
    monkeypatch.setattr(donor, 'TuongKyDaiSuClient', lambda *args: Mock())
    session = VscV3Session.__new__(VscV3Session)
    session.state = donor.GameState(allow_mouse_move=True)
    session.config = SimpleNamespace(DRY_RUN=True)
    session.hw = SimpleNamespace(robot=SimpleNamespace(connected=False), ai_ctrl=Mock(), clear_yolo_baseline=Mock())
    session.input = Mock()
    return session


def test_real_donor_red_commit_black_ai_and_single_fen_commit(donor_session):
    session = donor_session
    state = session.state
    state.process_human_move((0,6),(0,5),'r_P')
    session.hw.ai_ctrl.pick_move.return_value = ((0,3),(0,4))
    session._tick_ai()
    state.ai_thread.join(2)
    session._tick_ai()
    assert state.turn == 'r'
    assert state.board[4][0] == 'b_P' and state.board[3][0] == '.'
    assert len(state.move_history) == 2
    session._tick_ai()
    session.hw.ai_ctrl.pick_move.assert_called_once()
    assert len(state.move_history) == 2


def test_stale_ai_result_cannot_commit(donor_session):
    session = donor_session
    session.state.process_human_move((0,6),(0,5),'r_P')
    session.hw.ai_ctrl.pick_move.return_value = ((0,3),(0,4))
    session._tick_ai()
    session.state.ai_thread.join(2)
    session.state.game_epoch += 1
    before = deepcopy(session.state.board)
    session._tick_ai()
    assert session.state.board == before
    assert len(session.state.move_history) == 1


def test_physical_failure_retains_pending_fen(donor_session):
    session = donor_session
    session.config = SimpleNamespace(DRY_RUN=False, VISUAL_MOTION_ASYNC_ENABLED=True)
    session.hw.robot.connected = True
    session.state.process_human_move((0,6),(0,5),'r_P')
    session.hw.ai_ctrl.pick_move.return_value = ((0,3),(0,4))
    session.input.start_pending_ai_motion.side_effect = RuntimeError('motion failed')
    session._tick_ai()
    session.state.ai_thread.join(2)
    session._tick_ai()
    assert session.state.turn == 'b'
    assert session.state.pending_ai_move is not None
    assert session.state.board[3][0] == 'b_P'
    assert session.state.physical_sync_fault


def test_disconnected_physical_robot_cannot_be_treated_as_dry_run(donor_session):
    session = donor_session
    session.config.DRY_RUN = False
    session.state.process_human_move((0,6),(0,5),'r_P')
    session.hw.ai_ctrl.pick_move.return_value = ((0,3),(0,4))
    session._tick_ai()
    session.state.ai_thread.join(2)
    session._tick_ai()
    assert session.state.turn == 'b'
    assert session.state.board[3][0] == 'b_P'
    assert session.state.pending_ai_move is not None


def test_headless_facade_initialize_render_and_return_home(monkeypatch):
    import config
    import pygame
    from pathlib import Path
    import src.modes.vsc_v3.hardware.hardware_manager as hardware
    import src.modes.vsc_v3.core.game_state as donor
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    monkeypatch.setattr(donor, 'TuongKyDaiSuClient', lambda *args: Mock())
    class Hardware:
        def __init__(self, cfg, root):
            self.config, self.dry_run = cfg, cfg.DRY_RUN
            self.robot = SimpleNamespace(connected=False)
            self.cam_monitor = None
            self.cleanup = Mock()
        def initialize_all(self): return self
        def difficulty_availability(self): return {'easy':True,'medium':True,'hard':True,'impossible':True}
    monkeypatch.setattr(hardware, 'HardwareManager', Hardware)
    session = VscV3Session(config, SimpleNamespace(no_viewer=True), Path(__file__).parents[2], 'BOARD_ONLY')
    try:
        session.initialize()
        pygame.init()
        screen = pygame.display.set_mode((1440,1080))
        session.activate(screen)
        session.draw(screen)
        session.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        assert session.wants_home
    finally:
        session.close()
        pygame.quit()
    session.hw.cleanup.assert_called_once()


def test_observational_showcase_cannot_change_robot_result_or_exception():
    robot = SimpleNamespace(move_piece=Mock(return_value='verified result'), motion_listener=None)
    state = SimpleNamespace(board=initial_board(), move_history=[])
    showcase = VscV3Showcase(SimpleNamespace(hw=SimpleNamespace(robot=robot), state=state))
    showcase.relay = Mock()
    showcase.relay.begin_command_animation.side_effect = RuntimeError('viewer unavailable')
    showcase.relay.finish_command_animation.side_effect = RuntimeError('viewer closed')
    original = robot.move_piece
    showcase._observe_physical_commands()
    assert robot.move_piece(0,3,0,4,False) == 'verified result'
    original.assert_called_once_with(0,3,0,4,False)
    original.side_effect = ValueError('controller failure')
    with pytest.raises(ValueError, match='controller failure'):
        robot.move_piece(0,3,0,4,False)


def test_showcase_ignores_pending_physical_motion():
    state = SimpleNamespace(physical_motion_busy=True, ai_thinking=False, board=initial_board(),move_history=[])
    showcase = VscV3Showcase(SimpleNamespace(state=state))
    showcase.relay = Mock()
    showcase.tick()
    assert showcase._updates.empty()


def test_close_retains_resources_under_running_donor_worker():
    session = VscV3Session.__new__(VscV3Session)
    session._closed = False
    session.input = SimpleNamespace(_motion_thread=Mock(is_alive=Mock(return_value=True)))
    session.state = SimpleNamespace(ai_thread=None)
    session.showcase = Mock()
    session.hw = Mock()
    with pytest.raises(RuntimeError, match='worker still owns'):
        session.close()
    session.hw.cleanup.assert_not_called()
    session.showcase.close.assert_not_called()


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_failed_startup_retains_owner_if_cleanup_fails(monkeypatch, cleanup_fails):
    import config
    from pathlib import Path
    import src.modes.vsc_v3.hardware.hardware_manager as hardware
    import src.modes.vsc_v3.core.game_state as donor
    from src.modes.vsc_v3_session import VscV3StartupError
    monkeypatch.setattr(donor, 'TuongKyDaiSuClient', lambda *args: Mock())
    class Hardware:
        def __init__(self, cfg, root):
            self.cleanup = Mock(side_effect=RuntimeError('worker retained') if cleanup_fails else None)
        def initialize_all(self): raise ValueError('camera failed')
    monkeypatch.setattr(hardware, 'HardwareManager', Hardware)
    session = VscV3Session(config, SimpleNamespace(no_viewer=True), Path(__file__).parents[2], 'BOARD_ONLY')
    if cleanup_fails:
        with pytest.raises(VscV3StartupError) as caught:
            session.initialize()
        assert caught.value.session is session
        assert str(caught.value.cause) == 'camera failed'
        assert str(caught.value.cleanup_error) == 'worker retained'
        assert not session._closed
    else:
        with pytest.raises(ValueError, match='camera failed'):
            session.initialize()
        assert session._closed


def test_real_virtual_showcase_projects_committed_board_without_game_mutation(monkeypatch):
    import time
    from pathlib import Path
    import src.core.launch_options as launch
    import src.hardware.telemetry_publisher as telemetry
    monkeypatch.setattr(launch, 'check_viewer_assets', lambda root: None)
    monkeypatch.setattr(launch, 'ViewerServer', lambda *args: Mock())
    monkeypatch.setattr(telemetry, 'TelemetryPublisher', lambda **kwargs: Mock())
    state = SimpleNamespace(board=initial_board(), move_history=[], ai_thinking=False, physical_motion_busy=False)
    session = SimpleNamespace(selected_mode='SIMULATION', options=SimpleNamespace(no_viewer=False,viewer_port=0),
                              root=Path(__file__).parents[2], config=SimpleNamespace(DRY_RUN=True,TELEMETRY_PORT=0), state=state)
    showcase = VscV3Showcase(session)
    try:
        showcase.start()
        state.board[5][0], state.board[6][0] = state.board[6][0], '.'
        state.move_history = [{'turn':'r','src':(0,6),'dst':(0,5)}]
        before = deepcopy(state.board)
        showcase.tick()
        deadline = time.monotonic() + 5
        expected_id = initial_piece_identities()[6,0]
        while showcase.relay._cells.get((5,0)) != expected_id and time.monotonic() < deadline:
            time.sleep(.02)
        assert showcase.relay._cells[5,0] == expected_id
        assert state.board == before
        assert state.move_history == [{'turn':'r','src':(0,6),'dst':(0,5)}]
    finally:
        showcase.close()
