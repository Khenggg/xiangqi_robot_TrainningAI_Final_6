"""Mode boundaries and repeated turns; all devices/HTTP mocked unless noted."""
import atexit
from copy import deepcopy
import inspect
from pathlib import Path
import os
import runpy
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.core import xiangqi
from src.core.game_state import GameState
from src.core.ai_execution import execute_ai_move
from src.motion.result import MotionExecutionResult
from src.ui.input_handler import InputHandler
from src.vision.player_turn_types import InteractionCapability


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',lambda *a:Mock(room_id=None))
    return GameState()


def unified(state,monkeypatch,mode):
    monkeypatch.setattr(config,'GAME_MODE',mode)
    clock=[100.0]
    result=[None]
    monkeypatch.setattr('src.ui.input_handler.time.monotonic',lambda:clock[0])
    detector=SimpleNamespace(_baseline_time=1.,_baseline_occ=[[False]*9 for _ in range(10)],
        has_baseline=lambda:True,has_new_human_move=Mock(return_value=False),
        detect_move=Mock(side_effect=AssertionError('UNIFIED fell back to YOLO')))
    hw=SimpleNamespace(config=SimpleNamespace(PLAYER_TURN_MODE='UNIFIED',ROBOT_BACKEND='PHYSICAL'),
        dry_run=False,interaction_capability=InteractionCapability.AVAILABLE,
        is_board_occluded=lambda:False,yolo_detector=detector,
        cam_monitor=SimpleNamespace(get_latest_observation=lambda:(clock[0],object(),[],result[0])))
    handler=InputHandler(state,hw)
    handler._observed_baseline_time=1.
    return handler,clock,result


def observe_move(handler,clock,result,move,**metadata):
    expected,_=xiangqi.make_temp_move(handler.state.board,move)
    result[0]={'success':True,'board':expected,'confidence':[[.99]*9 for _ in range(10)],**metadata}
    confirmed=[]
    for _ in range(6):
        clock[0]+=1.
        confirmed.append(handler.poll_board_stability())
    return any(confirmed)


def test_unified_human_vs_robot_rearms_for_second_red_turn(state,monkeypatch):
    handler,clock,result=unified(state,monkeypatch,'HUMAN_VS_ROBOT')
    assert observe_move(handler,clock,result,((0,6),(0,5)))
    hw=SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True,ROBOT_BACKEND='VIRTUAL'),is_robot_ready=True)
    assert execute_ai_move(state,hw,((0,3),(0,4)),dry_run=True)
    assert observe_move(handler,clock,result,((2,6),(2,5)))
    assert len(state.move_history)==3 and state.human_commit_generation==2


def test_missing_camera_sample_breaks_unified_continuous_settle_window(state,monkeypatch):
    handler,clock,result=unified(state,monkeypatch,'HUMAN_VS_ROBOT')
    expected,_=xiangqi.make_temp_move(state.board,((0,6),(0,5)))
    result[0]={'success':True,'board':expected,'confidence':[[.99]*9 for _ in range(10)]}
    for _ in range(4):
        clock[0]+=.8;assert not handler.poll_board_stability()
    getter=handler.hw.cam_monitor.get_latest_observation
    handler.hw.cam_monitor.get_latest_observation=lambda:None
    clock[0]+=1.;assert not handler.poll_board_stability()
    handler.hw.cam_monitor.get_latest_observation=getter
    clock[0]+=1.;assert not handler.poll_board_stability()
    confirmed=[]
    for _ in range(6):
        clock[0]+=1.;confirmed.append(handler.poll_board_stability())
    assert any(confirmed) and len(state.move_history)==1


def test_unified_rearms_after_repaired_mirror_without_new_game_epoch(state,monkeypatch):
    handler,clock,result=unified(state,monkeypatch,'HUMAN_VS_ROBOT')
    state.set_board_observer(Mock(return_value=False))
    assert observe_move(handler,clock,result,((0,6),(0,5)))
    assert state.turn=='b' and not state.physical_sync_fault and state.projection_error
    epoch=state.game_epoch
    state.set_board_observer(Mock(return_value=True))
    handler.hw.verify_physical_board=Mock(return_value=True)
    handler.hw.capture_baseline_if_needed=Mock(return_value=True)
    assert state.sync_current_board()
    assert state.game_epoch==epoch and not state.physical_sync_fault and not state.move_sync_error
    ai_hw=SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True,ROBOT_BACKEND='VIRTUAL'),is_robot_ready=True)
    assert execute_ai_move(state,ai_hw,((0,3),(0,4)),dry_run=True)
    assert observe_move(handler,clock,result,((2,6),(2,5)))
    assert len(state.move_history)==3


@pytest.mark.parametrize('kind',['low','missing','explicit_false','bad_shape','nan','changed_cell_low'])
def test_unified_rejects_untrusted_recognition_even_when_layout_is_legal(state,monkeypatch,kind):
    handler,clock,result=unified(state,monkeypatch,'HUMAN_VS_ROBOT')
    expected,_=xiangqi.make_temp_move(state.board,((0,6),(0,5)))
    data={'success':True,'board':expected}
    if kind=='low':data['confidence']=[[.05]*9 for _ in range(10)]
    if kind=='bad_shape':data['confidence']=[[.99]]
    if kind=='explicit_false':data.update(confidence=[[.99]*9 for _ in range(10)],quality_ok=False)
    if kind in ('nan','changed_cell_low'):
        data['confidence']=[[.99]*9 for _ in range(10)]
        data['confidence'][5][0]=float('nan') if kind=='nan' else .1
    result[0]=data
    for _ in range(6):
        clock[0]+=1.;assert not handler.poll_board_stability()
    assert not state.move_history and not state.api_client.method_calls


@pytest.mark.parametrize('flag',['game_over','turn_confirmation_required'])
def test_ai_entrypoint_cannot_dispatch_on_finished_or_unconfirmed_game(state,flag):
    state.turn='b';setattr(state,flag,True)
    before=deepcopy(state.board)
    hw=SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='VIRTUAL'),simulation_runtime=object(),
                       is_robot_ready=True,execute_piece_move=Mock(return_value=MotionExecutionResult.ok()))
    assert not execute_ai_move(state,hw,((0,3),(0,4)),dry_run=True)
    hw.execute_piece_move.assert_not_called()
    assert state.board==before and state.pending_move is None and state.pending_ai_move is None


def test_ten_plies_two_captures_surrender_and_new_game_match_pybullet_scene(state,monkeypatch):
    mode='HUMAN_VS_ROBOT'
    # Real PyBullet board/piece reconciliation, mocked arm execution (not a trajectory test).
    from src.digital_twin.live_twin_bridge import LiveTwinBridge
    from src.domain.board_pose_provider import FixedBoardPoseProvider
    from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
    from src.hardware.telemetry_publisher import TelemetryPublisher
    from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
    from src.domain.game_move import MoveActor
    monkeypatch.setattr(config,'GAME_MODE',mode)
    monkeypatch.setattr(config,'DRY_RUN',True)
    backend=PhysicalFR3Backend(dry_run=True)
    backend.connect()
    telemetry=TelemetryPublisher(port=0)
    bridge=LiveTwinBridge(backend,FixedBoardPoseProvider.from_forward_shift(0),telemetry)
    state.set_move_observer(bridge.reconcile_human_move)
    state.set_board_observer(bridge.reconcile_to_board_cells)
    motion=Mock(return_value=MotionExecutionResult.ok())
    opening=[((4,6),(4,5)),((4,3),(4,4)),((4,5),(4,4)),((0,3),(0,4)),((0,6),(0,5)),
             ((0,4),(0,5)),((1,7),(4,7)),((1,2),(4,2)),((7,9),(6,7)),((7,0),(6,2))]
    policy=iter(opening)
    hw=SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='VIRTUAL',GAME_ONLY=False,GAME_MODE=mode),dry_run=True,
        simulation_runtime=object(),is_robot_ready=True,cam_monitor=None,capture_baseline_if_needed=Mock(return_value=True),
        execute_piece_move=motion,ai_ctrl=SimpleNamespace(pick_move=lambda *a,**kw:next(policy)))
    human=HumanMoveCommitCoordinator(state)
    try:
        for move in opening:
            expected,_=xiangqi.make_temp_move(state.board,move)
            if state.turn=='r':
                assert state.is_human_turn
                req=SimpleNamespace(turn_token=(state.game_epoch,state.human_commit_generation),move=move)
                assert human.try_commit(req)=='ACCEPTED'
                assert human.try_commit(req)=='DUPLICATE'
            else:
                assert state.can_start_ai_turn()
                state.mark_ai_turn_started()
                assert execute_ai_move(state,hw,move,dry_run=True)
                assert not state.can_start_ai_turn()
            assert state.board==expected and not state.physical_sync_fault and not state.move_sync_error
            active=set(bridge.world.pieces)
            assert active==set(state.piece_ids.values())
            emitted=telemetry._latest_world_state['pieces']
            assert {p['id'] for p in emitted}==set(state.piece_ids.values())
            expected_cells={pid:(r,c) for (r,c),pid in state.piece_ids.items()}
            assert {p['id']:(p['nearest_row'],p['nearest_col']) for p in emitted}==expected_cells
            captured=telemetry._latest_world_state.get('captured_pieces',[])
            assert all(p['captured'] is True and p['physical_state']=='OUT_OF_BOUNDS' for p in captured)
        assert len(state.move_history)==10 and len(bridge.world.pieces)==30
        assert len(telemetry._latest_world_state.get('captured_pieces',[]))==2
        assert len(state.r_captured)==len(state.b_captured)==1
        assert motion.call_count==5
        for call in motion.call_args_list:
            assert call.kwargs['move_context'].actor is MoveActor.ROBOT
        from src.ui.board_renderer import BTN_SURRENDER_RECT
        InputHandler(state,hw).handle_mouse_down(*BTN_SURRENDER_RECT.center)
        assert state.game_over and state.winner=='b'
        state.api_client.end_match.assert_called_once_with(winner='BLACK',reason='RESIGN')
        state.reset_game(hw)
        assert state.board==xiangqi.get_board() and not state.game_over and not state.move_history
        assert len(bridge.world.pieces)==32 and set(bridge.world.pieces)==set(state.piece_ids.values())
    finally:
        bridge.close()

