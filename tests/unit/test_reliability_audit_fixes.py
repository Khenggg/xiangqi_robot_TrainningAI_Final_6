"""Regression probes at failure boundaries; no physical SDK construction."""
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.ai.moonfish_engine import MoonfishEngine
from src.core.game_state import GameState
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.hardware.rpc_transport import BoundedRPCProxy, RpcOutcomeUnknown, wait_for_reconnect
from src.vision.snapshot_detector import SnapshotDetector
from src.core import xiangqi


def test_silent_engine_handshake_has_actual_deadline(tmp_path):
    script = tmp_path / 'silent.py'
    script.write_text('import time\ntime.sleep(60)\n')
    engine = MoonfishEngine(str(script))
    engine.start_timeout_s = .1
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        engine.start()
    assert time.monotonic() - start < 5
    assert engine.process is None and not engine._ready


def test_silent_bestmove_releases_engine(tmp_path):
    script = tmp_path / 'silent_search.py'
    script.write_text("import sys,time\nfor line in sys.stdin:\n if line.strip()=='ucci': print('ucciok',flush=True)\n elif line.startswith('go '): time.sleep(60)\n")
    engine = MoonfishEngine(str(script))
    engine.start()
    engine.request_timeout_s = .1
    with pytest.raises(TimeoutError):
        engine.pick_best_move(xiangqi.get_board(), 'b')
    assert engine.process is None
    assert engine._lock.acquire(blocking=False)
    engine._lock.release()


def test_lost_rpc_reply_never_resends_motion():
    sdk = SimpleNamespace(MoveCart=Mock(side_effect=socket.timeout('lost reply')))
    proxy = BoundedRPCProxy('http://unused', proxy=sdk)
    with pytest.raises(RpcOutcomeUnknown, match='do not resend'):
        proxy.MoveCart([1,2,3,4,5,6])
    assert sdk.MoveCart.call_count == 1


def test_actual_http_transport_and_vendor_motion_never_replay_lost_reply():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from src.hardware.robot_sdk_core import RPC
    received = []
    class LostReply(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),LostReply)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    rpc = RPC.__new__(RPC)  # No controller/receiver constructor.
    rpc.is_conect = True
    rpc.reconnect_flag = False
    rpc.GetSafetyCode = lambda:0
    rpc.robot = BoundedRPCProxy(f'http://127.0.0.1:{server.server_port}',timeout_s=.5)
    try:
        with pytest.raises(RpcOutcomeUnknown):
            rpc.MoveCart([0,0,220,180,0,0],0,0)
        assert len(received)==1 and b'MoveCart' in received[0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


def test_stuck_reconnect_bounded_without_command():
    start = time.monotonic()
    with pytest.raises(RpcOutcomeUnknown):
        wait_for_reconnect(SimpleNamespace(reconnect_flag=True), timeout_s=.05)
    assert time.monotonic() - start < .3


def test_commit_preserves_truth_when_viewer_fails(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    state = GameState()
    state.turn = 'b'
    move = ((0,3),(0,4))
    from src.domain.game_move import MoveActor
    state.mark_move_pending(state.create_move_context(*move, MoveActor.ROBOT))
    after, _ = xiangqi.make_temp_move(state.board, move)
    state.set_pending_physical_move(move, after, '.', 'b')
    state.set_board_observer(Mock(return_value=False))
    assert state.commit_pending_physical_move()
    assert state.turn == 'r' and state.board[4][0] == 'b_P'
    assert state.physical_sync_fault and state.move_sync_error
    assert len(state.move_history) == 1 and state.last_committed_move is not None
    assert not state.commit_pending_physical_move()


def test_rescan_invalidates_old_ai_job_without_stranding_retry(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    state = GameState()
    state.turn = 'b'
    state.ai_thread = Mock()
    state.ai_thinking = True
    assert state.apply_confirmed_board([row[:] for row in state.board])
    state.ai_retry_requested = True
    assert state.can_start_ai_turn()


def test_rescan_reaps_live_ai_job_before_new_engine_request(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    state = GameState()
    state.turn = 'b'
    released = threading.Event()
    state.ai_thread = threading.Thread(target=lambda:released.wait(2))
    worker = state.ai_thread
    worker.start()
    try:
        assert state.apply_confirmed_board([row[:] for row in state.board])
        state.ai_retry_requested = True
        assert not state.can_start_ai_turn()
        released.set(); worker.join(1)
        assert state.can_start_ai_turn()
    finally:
        released.set(); worker.join(1)


def test_recovery_does_not_allow_moves_until_sync_complete(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    state = GameState()
    controller = SelfPlayController(state, SimpleNamespace())
    controller.status = SelfPlayStatus.FAULTED
    state.physical_sync_fault = True
    assert controller.recovery_input_allowed
    assert not controller.finish_recovery()
    state.physical_sync_fault = False
    assert controller.finish_recovery()
    assert controller.status == SelfPlayStatus.IDLE


def test_auto_detector_rejects_low_confidence_legal_move(tmp_path):
    detector = SnapshotDetector(tmp_path / 'unused.npy', {})
    before = xiangqi.get_board()
    after, _ = xiangqi.make_temp_move(before, ((4,6),(4,5)))
    confidence = [[.99]*9 for _ in range(10)]
    confidence[5][4] = .1
    result = detector.detect_move(None, [], before,
        cchess_result={'success':True,'board':after,'confidence':confidence})
    assert result == (None,None,None)


def test_spectator_latency_does_not_block_game_or_mix_rooms(monkeypatch):
    from src.api.simulation_client import TuongKyDaiSuClient
    arrived, released = threading.Event(), threading.Event()
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs.get('json')))
        if url.endswith('/matches'):
            arrived.set()
            assert released.wait(2)
            return SimpleNamespace(status_code=200,json=lambda:{'success':True,'data':{'roomId':7}})
        return SimpleNamespace(status_code=200,json=lambda:{'success':True,'data':{}})
    monkeypatch.setattr('src.api.simulation_client.requests.post',post)
    api = TuongKyDaiSuClient('http://unused','test')
    try:
        start = time.monotonic()
        api.create_match()
        assert arrived.wait(1)
        api.send_move_update_board('fen-1')
        api.end_match()
        assert time.monotonic() - start < .5
        released.set()
        api._jobs.join()
        assert calls[1][0].endswith('/7/fen') and calls[2][0].endswith('/7/end')
    finally:
        released.set()
        api.close(1)


def test_websocket_start_failure_rolls_back_entire_session(monkeypatch):
    from src.core import session_startup
    state = GameState()
    manager = Mock()
    manager.initialize_all.return_value = manager
    manager.setup_digital_twin.return_value = SimpleNamespace(board_sync_available=True)
    manager.sync_committed_board.return_value = True
    telemetry = Mock()
    telemetry.start.side_effect = RuntimeError('port occupied')
    monkeypatch.setattr(session_startup, 'HardwareManager', Mock(return_value=manager))
    monkeypatch.setattr(session_startup, 'TelemetryPublisher', Mock(return_value=telemetry))
    config = SimpleNamespace(TELEMETRY_HOST='127.0.0.1', TELEMETRY_PORT=8765, GAME_ONLY=False)
    with pytest.raises(RuntimeError, match='port occupied'):
        session_startup.build_session(config, SimpleNamespace(no_viewer=True), '.', state)
    manager.cleanup.assert_called_once()
    telemetry.stop.assert_called_once()
    assert state._board_observer is None and not state.physical_sync_fault


def test_unknown_board_does_not_prevent_readonly_arm_telemetry():
    from src.digital_twin.physical_state_relay import PhysicalStateRelay
    snapshot = object()
    backend = SimpleNamespace(ip='fake', get_state_snapshot=lambda:snapshot)
    telemetry = Mock()
    relay = PhysicalStateRelay(backend, telemetry, 'contact offset not measured')
    assert relay.poll_once() is snapshot
    telemetry.update_from_snapshot.assert_called_once_with(snapshot)
    assert telemetry.source == 'PHYSICAL' and not relay.board_sync_available


def test_wrong_home_frame_rejects_before_motion():
    from src.hardware.robot_VIP import FR5Robot
    arm = FR5Robot()
    arm.dry = False
    arm.connected = arm.physical_motion_authorized = True
    arm.robot = Mock()
    arm.robot.GetRobotTeachingPoint.return_value = (0,[0.0]*12+[arm.tool_num,arm.user_num+1])
    arm.teaching_points = {name:dict(pose=[x,y,10,180,0,0],joints=[0]*6)
        for name,x,y in [('R1',-200,500),('R2',-200,180),('R3',160,180),('R4',160,500)]}
    result = arm.move_piece(0,0,0,1,False)
    assert not result.success and 'frame' in result.message
    arm.robot.MoveCart.assert_not_called()
    arm.robot.MoveJ.assert_not_called()


def test_physical_stage_rejects_stale_telemetry_without_rpc():
    from src.hardware.robot_VIP import FR5Robot, RobotCommandError
    arm = FR5Robot()
    arm.dry = False
    arm.connected = arm.physical_motion_authorized = True
    arm.telemetry_readiness = lambda:False
    arm.robot = Mock()
    with pytest.raises(RobotCommandError, match='stale'):
        arm.move_safe_pose([0,0,200,180,0,0])
    arm.robot.MoveCart.assert_not_called()
