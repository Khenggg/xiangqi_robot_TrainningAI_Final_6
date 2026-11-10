"""Adversarial scheduling and retry probes; all hardware/HTTP mocked."""
import atexit
import inspect
import os
from pathlib import Path
import runpy
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.core import xiangqi
from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.motion.result import MotionExecutionResult
from src.ui.input_handler import InputHandler
from src.vision.pick_consensus import PickTargetUnavailable
from src.vision.visual_pick_estimator import GridTarget


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    return GameState()


def hardware(physical=False):
    return SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL' if physical else 'VIRTUAL',
        VISUAL_PICK_ENABLED=physical, GAME_ONLY=False, GAME_MODE='HUMAN_VS_ROBOT'), dry_run=not physical,
        simulation_runtime=None if physical else object(), is_robot_ready=True,
        cam_monitor=object(), yolo_detector=None,
        ai_ctrl=SimpleNamespace(pick_move=Mock(return_value=((4,6),(4,5)))),
        verify_physical_board=Mock(return_value=True), is_cell_visually_clear=Mock(return_value=True),
        execute_piece_move=Mock(return_value=MotionExecutionResult.ok()),
        get_robot_center_pick_targets=Mock(side_effect=lambda cells: {k: GridTarget(*v,.99,0) for k,v in cells.items()}),
        capture_baseline_if_needed=Mock(return_value=True))


def paused_retry(state,hw,move):
    hw.get_robot_center_pick_targets.side_effect=PickTargetUnavailable('unstable center')
    assert not execute_ai_move(state,hw,move,visual_pick_enabled=True)
    assert state.visual_pick_retry and not state.physical_sync_fault
    hw.get_robot_center_pick_targets.side_effect=lambda cells:{k:GridTarget(*v,.99,0) for k,v in cells.items()}
    return InputHandler(state,hw)


def test_v_preserves_pending_on_transient_fen_failure_then_retries_once(state):
    import pygame
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    pending, context = state.pending_ai_move, state.pending_move
    handler._motion_busy=lambda:False
    hw.verify_physical_board.return_value=False
    handler.handle_keyboard(pygame.K_v)
    assert state.pending_ai_move is pending and state.pending_move is context
    assert state.visual_pick_retry['resolution']['reason']=='BOARD_VERIFICATION_FAILED'
    assert not state.physical_sync_fault and not state.move_sync_error
    hw.execute_piece_move.assert_not_called()
    hw.capture_baseline_if_needed.assert_not_called()
    hw.verify_physical_board.return_value=True
    handler.handle_keyboard(pygame.K_v)
    hw.execute_piece_move.assert_called_once()
    assert state.pending_ai_move is None and state.visual_pick_retry is None
    assert len(state.move_history)==1


def test_v_fen_match_without_valid_pick_target_stays_paused(state):
    import pygame
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    handler._motion_busy=lambda:False
    hw.get_robot_center_pick_targets.side_effect=PickTargetUnavailable('offset 7mm > 6mm')
    handler.handle_keyboard(pygame.K_v)
    assert state.visual_pick_retry and not state.physical_sync_fault
    assert not state.move_history
    hw.execute_piece_move.assert_not_called()


def test_post_motion_fen_failure_still_requires_recovery_not_replay(state):
    import pygame
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    handler._motion_busy=lambda:False
    hw.verify_physical_board.side_effect=[True,False]
    handler.handle_keyboard(pygame.K_v)
    hw.execute_piece_move.assert_called_once()
    assert state.physical_sync_fault and state.move_sync_error
    assert not state.move_history


@pytest.mark.parametrize('failure',['false','exception'])
def test_retry_baseline_failure_pauses_game_after_preserving_commit(state,failure):
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    if failure=='false': hw.capture_baseline_if_needed.return_value=False
    else: hw.capture_baseline_if_needed.side_effect=RuntimeError('camera disconnected')
    handler._retry_visual_pick()
    assert len(state.move_history)==1 and state.turn=='r' and state.pending_ai_move is None
    assert state.manual_override_active and state.snapshot_continue_required
    assert not state.snapshot_continue_can_commit_pending
    assert not state.physical_sync_fault, 'A confirmed move is retained; pause for baseline repair'
    hw.execute_piece_move.assert_called_once()
    hw.capture_baseline_if_needed.assert_called_once()
    assert not InputHandler(state,hw).poll_board_stability()


def test_retry_mirror_failure_does_not_refresh_baseline_or_replay_motion(state):
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    state.set_board_observer(lambda *a:False)
    handler._retry_visual_pick()
    assert len(state.move_history)==1 and state.projection_error
    assert not state.physical_sync_fault and not state.move_sync_error
    hw.capture_baseline_if_needed.assert_called_once()
    handler._retry_visual_pick()
    hw.execute_piece_move.assert_called_once()


@pytest.mark.parametrize('color',['r','b'])
def test_terminal_retry_publishes_fen_then_end_once(state,color):
    board=[['.']*9 for _ in range(10)]
    board[0][4]='b_K';board[9][4]='r_K';board[6][4]='r_P'
    board[2][0]='r_R';board[1][3]='r_R';board[2][6]='r_N'
    if color=='b':
        board=[[p.replace('r_','x_').replace('b_','r_').replace('x_','b_') for p in row] for row in reversed(board)]
    from src.domain.game_move import piece_symbol_for_identity
    pools={}
    for identity in state.piece_ids.values(): pools.setdefault(piece_symbol_for_identity(identity),[]).append(identity)
    state.board=board;state.turn=color
    state.piece_ids={(r,c):pools[p].pop() for r,row in enumerate(board) for c,p in enumerate(row) if p!='.'}
    state.update_fen_from_board()
    move=((0,2),(4,2)) if color=='r' else ((0,7),(4,7))
    hw=hardware(True);handler=paused_retry(state,hw,move)
    handler._retry_visual_pick()
    assert state.game_over and state.winner==color and state.game_over_reason=='CHECKMATE'
    assert [c[0] for c in state.api_client.method_calls]==['send_move_update_board','end_match']
    state.api_client.end_match.assert_called_once_with(winner='RED' if color=='r' else 'BLACK',reason='CHECKMATE')
    handler._retry_visual_pick()
    hw.execute_piece_move.assert_called_once()
    hw.capture_baseline_if_needed.assert_not_called()

