"""Fault injection at the real integration boundary; never opens a physical SDK."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.core.game_state import GameState
from src.core.ai_execution import execute_ai_move
from src.core.visual_move_coordinator import retry_is_current
from src.core.motion_worker import MotionWorker
from src.motion.result import MotionExecutionResult, MotionFailureCategory
from src.motion.stages import MotionStage
from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator
from src.vision.pick_consensus import PickTargetUnavailable


def fixture(monkeypatch, capture=False):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    state = GameState()
    if capture:
        state.board[5][4] = 'b_P'
        state.piece_ids[(5,4)] = 'black_pawn_test'
        state.update_fen_from_board()
    hw = SimpleNamespace(config=SimpleNamespace(VISUAL_PICK_ENABLED=True, GAME_ONLY=False, ROBOT_BACKEND='PHYSICAL'),
        simulation_runtime=None, dry_run=False, is_robot_ready=True,
        verify_physical_board=Mock(return_value=True), is_cell_visually_clear=Mock(return_value=True),
        get_robot_center_pick_targets=Mock(side_effect=lambda cells: {k:GridTarget(*v,.9,0) for k,v in cells.items()}),
        execute_piece_move=Mock(return_value=MotionExecutionResult.ok()))
    return state, hw


@pytest.mark.parametrize('color,move', [('r',((4,6),(4,5))), ('b',((4,3),(4,4)))])
@pytest.mark.parametrize('mode',['center','ring'])
def test_acquisition_retry_same_identity_and_actor(monkeypatch, color, move, mode):
    state, hw = fixture(monkeypatch)
    if mode=='ring':
        hw.config.VISUAL_PICK_ENABLED=False
        hw.config.VISUAL_RING_PICK_ENABLED=True
    state.turn = color
    state.update_fen_from_board()
    before = state.current_fen
    hw.get_robot_center_pick_targets.side_effect = PickTargetUnavailable('not stable')
    assert not execute_ai_move(state, hw, move, visual_pick_enabled=True)
    identity = state.pending_move.move_id
    assert retry_is_current(state)
    assert state.current_fen == before and not state.physical_sync_fault
    hw.execute_piece_move.assert_not_called()
    hw.get_robot_center_pick_targets.side_effect = lambda cells:{k:GridTarget(*v,.9,0) for k,v in cells.items()}
    assert execute_ai_move(state, hw, move, visual_pick_enabled=True)
    assert state.last_committed_move.move_id == identity
    assert state.visual_pick_retry is None and len(state.move_history)==1


@pytest.mark.parametrize('mode',['center','ring'])
def test_capture_retry_never_replays_victim_pick(monkeypatch,mode):
    state, hw = fixture(monkeypatch, capture=True)
    if mode=='ring':
        hw.config.VISUAL_PICK_ENABLED=False
        hw.config.VISUAL_RING_PICK_ENABLED=True
    move=((4,6),(4,5))
    def targets(cells):
        if 'moving' in cells:
            raise PickTargetUnavailable('source not stable')
        return {k:GridTarget(*v,.9,0) for k,v in cells.items()}
    hw.get_robot_center_pick_targets.side_effect = targets
    def first_motion(**kw):
        assert kw['is_capture']
        assert kw['verify_capture_cleared']()
        with pytest.raises(PickTargetUnavailable) as failed:
            kw['refresh_moving_visual_target']()
        return MotionExecutionResult.fail(MotionStage.SETTLE, MotionFailureCategory.PRECONDITION_FAILED,
            str(failed.value), metadata={'visual_retry_stage':failed.value.stage})
    hw.execute_piece_move.side_effect=first_motion
    before=state.current_fen
    assert not execute_ai_move(state, hw, move, visual_pick_enabled=True)
    assert state.current_fen==before and state.visual_pick_retry['stage']=='capture_removed'
    assert not state.physical_sync_fault
    hw.get_robot_center_pick_targets.side_effect=lambda cells:{k:GridTarget(*v,.9,0) for k,v in cells.items()}
    def resumed(**kw):
        assert not kw['is_capture'] and kw['refresh_moving_visual_target'] is None
        return MotionExecutionResult.ok()
    hw.execute_piece_move.side_effect=resumed
    assert execute_ai_move(state, hw, move, visual_pick_enabled=True)
    assert [call.kwargs['is_capture'] for call in hw.execute_piece_move.call_args_list] == [True,False]
    assert len(state.move_history)==1


def test_stale_retry_cannot_acquire_or_send_motion(monkeypatch):
    state, hw=fixture(monkeypatch)
    move=((4,6),(4,5))
    hw.get_robot_center_pick_targets.side_effect=PickTargetUnavailable('missing')
    assert not execute_ai_move(state,hw,move,visual_pick_enabled=True)
    state.game_epoch+=1
    hw.get_robot_center_pick_targets.reset_mock()
    assert not retry_is_current(state)
    assert not execute_ai_move(state,hw,move,visual_pick_enabled=True)
    hw.execute_piece_move.assert_not_called()
    hw.get_robot_center_pick_targets.assert_not_called()


def test_sdk_failure_is_fault_not_sampling_retry(monkeypatch):
    state,hw=fixture(monkeypatch)
    hw.execute_piece_move.return_value=MotionExecutionResult.fail(MotionStage.APPROACH,
        MotionFailureCategory.MOTION_COMMAND_FAILED,'SDK 112',backend_code=112)
    before=state.current_fen
    assert not execute_ai_move(state,hw,((4,6),(4,5)),visual_pick_enabled=True)
    assert state.physical_sync_fault and state.visual_pick_retry is None and state.current_fen==before


def test_full_board_verify_failure_never_commits(monkeypatch):
    state,hw=fixture(monkeypatch)
    hw.verify_physical_board.side_effect=[True,False]
    before=state.current_fen
    assert not execute_ai_move(state,hw,((4,6),(4,5)),visual_pick_enabled=True)
    assert state.physical_sync_fault and state.current_fen==before and not state.visual_pick_retry


def test_worker_single_owner_and_close_keeps_resources_live():
    worker=MotionWorker()
    released=threading.Event()
    completed=[]
    assert worker.start(lambda:released.wait(3), lambda value,error:completed.append((value,error)))
    try:
        assert worker.busy and not worker.start(lambda:None,lambda *a:None)
        with pytest.raises(RuntimeError,match='kept open'):
            worker.close(timeout=.01)
        assert worker.busy and not completed
    finally:
        released.set()
        worker.close()
        assert worker.poll()
    assert completed==[(True,None)] and not worker.busy


def test_outside_grid_remains_disabled_by_default(tmp_path):
    import numpy as np
    path=tmp_path/'perspective.npy'
    np.save(path,np.eye(3))
    est=VisualPickEstimator(path,point_mode='center')
    assert est.estimate_pick_target([(0,.95,(-.2,-.1,0,.1))],0,0) is None


def test_reset_clears_retry_requests_and_checkpoint(monkeypatch):
    state,hw=fixture(monkeypatch)
    state.visual_pick_retry={'old':'request'}
    state.visual_capture_checkpoint={'old':'capture'}
    state.test_pick_retry={'old':'test'}
    state.reset_game()
    assert state.visual_pick_retry is None and state.visual_capture_checkpoint is None and state.test_pick_retry is None


def test_confirmed_board_recovery_clears_old_retry_gating(monkeypatch):
    state,hw=fixture(monkeypatch)
    state.visual_pick_retry={'old':'request'}
    state.visual_capture_checkpoint={'old':'capture'}
    state.test_pick_retry={'old':'test'}
    assert state.apply_confirmed_board([row[:] for row in state.board])
    assert state.visual_pick_retry is None and state.visual_capture_checkpoint is None and state.test_pick_retry is None


@pytest.mark.parametrize('color,move',[('r',((4,6),(4,5))),('b',((4,3),(4,4)))])
def test_self_play_camera_retry_preserves_actor(monkeypatch,color,move):
    from src.core.self_play_controller import SelfPlayController,SelfPlayStatus
    state,hw=fixture(monkeypatch)
    state.turn=color
    hw.cam_monitor=object()
    hw.capture_baseline_if_needed=Mock(return_value=True)
    hw.ai_ctrl=SimpleNamespace(pick_move=lambda *a,**kw:move)
    controller=SelfPlayController(state,hw)
    assert controller.start('easy','easy')
    hw.get_robot_center_pick_targets.side_effect=PickTargetUnavailable('missing center')
    assert controller.request_next_move()
    controller._thread.join(3)
    controller.tick()
    controller._thread.join(3)
    controller.tick()
    assert controller.status is SelfPlayStatus.PICK_PAUSED and retry_is_current(state)
    identity=state.pending_move.move_id
    hw.execute_piece_move.assert_not_called()
    hw.get_robot_center_pick_targets.side_effect=lambda cells:{k:GridTarget(*v,.9,0) for k,v in cells.items()}
    assert controller.retry_visual_pick()
    controller._thread.join(3)
    controller.tick()
    assert controller.status is SelfPlayStatus.READY
    assert len(state.move_history)==1 and state.last_committed_move.move_id==identity


def test_real_robot_stops_before_grip_when_first_sdk_motion_fails(monkeypatch):
    from src.hardware.robot_VIP import FR5Robot
    import config
    robot=FR5Robot()
    robot.dry=False
    robot.connected=True
    robot.physical_motion_authorized=True
    robot.robot=Mock()
    robot.robot.MoveCart.return_value=112
    robot.robot.GetRobotTeachingPoint.return_value=(0,[0.0]*12+[robot.tool_num,robot.user_num])
    robot.board_to_pose=Mock(return_value=[-300,0,config.SAFE_Z,180,0,0])
    robot.gripper_ctrl=Mock()
    result=robot.move_piece(4,6,4,5,False)
    assert not result.success and result.backend_code==112
    assert robot.robot.MoveCart.call_count==1
    robot.gripper_ctrl.assert_not_called()


@pytest.mark.parametrize('target',[None,GridTarget(float('nan'),6,.9,0)])
def test_physical_manager_rejects_missing_or_nonfinite_measurement(target):
    from src.hardware.hardware_manager import HardwareManager
    manager=HardwareManager.__new__(HardwareManager)
    manager.config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL',VISUAL_RING_PICK_ENABLED=True)
    manager.dry_run=False
    manager.simulation_runtime=None
    manager.board_pose_provider=object()
    manager._piece_move_lock=threading.Lock()
    manager.robot=SimpleNamespace(connected=True,physical_motion_authorized=True,move_piece=Mock())
    result=manager.execute_piece_move(4,6,4,5,False,moving_visual_target=target)
    assert not result.success
    manager.robot.move_piece.assert_not_called()


def test_physical_manager_capture_requires_fresh_source_and_clear_checkpoint():
    from src.hardware.hardware_manager import HardwareManager
    manager=HardwareManager.__new__(HardwareManager)
    manager.config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL',VISUAL_PICK_ENABLED=True)
    manager.dry_run=False
    manager.simulation_runtime=None
    manager.board_pose_provider=object()
    manager._piece_move_lock=threading.Lock()
    manager.robot=SimpleNamespace(connected=True,physical_motion_authorized=True,move_piece=Mock())
    result=manager.execute_piece_move(4,6,4,5,True,captured_visual_target=GridTarget(4,5,.9,0))
    assert not result.success
    manager.robot.move_piece.assert_not_called()
