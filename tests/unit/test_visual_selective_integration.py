"""Fault injection across UI -> manager -> executor, with no physical RPC."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import time
import pytest
from src.core.game_state import GameState
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer
from src.hardware.hardware_manager import HardwareManager
from src.domain.game_move import MoveActor, MoveContext
from src.motion.result import MotionExecutionResult
from src.motion.stages import MotionStage
from src.motion.result import MotionFailureCategory

def fixture():
    state = GameState(allow_mouse_move=True)
    hw = Mock(config=SimpleNamespace())
    hw.execute_pick_place_test.return_value = MotionExecutionResult.ok()
    hw.sync_committed_board.return_value = True
    handler = InputHandler(state, hw)
    handler._toggle_pick_test()
    return state, hw, handler

def click(handler, cell):
    with patch.object(BoardRenderer, 'pixel_to_grid', return_value=cell):
        handler._handle_pick_test_click(0, 0)

def test_manual_move_updates_separate_identity_and_scene_not_game_fen():
    state, hw, handler = fixture()
    fen, board = state.current_fen, [r[:] for r in state.board]
    identity = state.piece_ids[(6, 4)]
    click(handler, (4, 6)); click(handler, (4, 5))
    assert state.current_fen == fen and state.board == board
    assert state.pick_test_piece_ids[(5, 4)] == identity
    assert (6, 4) not in state.pick_test_piece_ids
    hw.sync_committed_board.assert_called_once_with(state.pick_test_piece_ids)
    context = hw.execute_pick_place_test.call_args.kwargs['move_context']
    assert context.piece_id == identity and context.src == (6, 4) and context.dst == (5, 4)
    assert not state.can_start_ai_turn()

@pytest.mark.parametrize('failure', ['motion', 'verify', 'scene'])
def test_test_fault_latches_and_blocks_second_motion_even_after_toggle(failure):
    state, hw, handler = fixture()
    if failure == 'scene': hw.sync_committed_board.return_value = False
    else: hw.execute_pick_place_test.side_effect = RuntimeError(f'{failure} failed')
    click(handler, (4, 6)); click(handler, (4, 5))
    assert state.pick_test_fault
    click(handler, (2, 6)); click(handler, (2, 5))
    handler._toggle_pick_test(); handler._toggle_pick_test()
    assert not state.pick_test_mode
    assert hw.execute_pick_place_test.call_count == 1
    assert state.pick_test_board == state.board

def test_manager_rejects_sdk_failure_instead_of_reporting_success_or_verifying():
    manager = HardwareManager.__new__(HardwareManager)
    manager.simulation_runtime = None
    manager.is_cell_visually_clear = Mock(return_value=True)
    manager.get_robot_center_pick_targets = Mock(return_value={'moving': Mock()})
    manager.execute_piece_move = Mock(return_value=MotionExecutionResult.fail(
        MotionStage.APPROACH, MotionFailureCategory.MOTION_COMMAND_FAILED, 'SDK 112', backend_code=112))
    manager.verify_visual_move = Mock(return_value=True)
    context = MoveContext('red_pawn_3', (6,4), (5,4), MoveActor.ROBOT)
    with pytest.raises(RuntimeError, match='112'):
        manager.execute_pick_place_test((4,6), (4,5), move_context=context)
    manager.verify_visual_move.assert_not_called()

def test_manual_mode_blocks_direct_game_and_selfplay_entry_points():
    from src.core.ai_execution import execute_ai_move
    from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
    state, hw, _ = fixture()
    fen = state.current_fen
    assert not state.process_human_move((4,6),(4,5),'r_P')
    assert not state.process_emergency_move((4,6),(4,5),'r_P')
    assert not execute_ai_move(state,hw,((4,6),(4,5)))
    controller = SelfPlayController(state,hw)
    controller.status = SelfPlayStatus.READY
    assert not controller.request_next_move()
    assert state.current_fen == fen and state.pending_move is None
    hw.execute_piece_move.assert_not_called()

@pytest.mark.parametrize('condition', ['stale','low','moving','invalid'])
def test_measurement_observed_state_blocks_before_enable(condition, tmp_path):
    from src.ui import measurement_client as client
    robot = Mock(connected=True, tool_num=0, user_num=0, teaching_points={})
    robot.board_to_pose_bilinear.return_value = [10,20,client.config.SAFE_Z,180,0,0]
    snap = SimpleNamespace(connected=True,tcp_valid=condition!='invalid',motion_state='MOVING' if condition=='moving' else 'IDLE',
        measurement_timestamp=time.time()-10 if condition=='stale' else time.time(),
        tcp_pose_mm_deg=[0,0,0 if condition=='low' else client.config.SAFE_Z+20,180,0,0])
    reader=Mock(); reader.get_state_snapshot.return_value=snap
    with patch.object(client,'new_report',return_value=tmp_path), patch('src.hardware.simulation_adapter.physical_board_provider',return_value=Mock()):
        session=client.RobotMeasurement(robot,state_source=reader)
        with pytest.raises(RuntimeError): session.move([0,0,client.config.SAFE_Z+20])
    robot.activate_physical_control.assert_not_called()
    robot.move_safe_pose.assert_not_called()

def test_manual_gui_move_after_taught_pose_uses_actual_pybullet_and_preserves_fen(monkeypatch):
    import config
    import pygame
    import numpy as np
    from pathlib import Path
    monkeypatch.setattr(config, 'ROBOT_BACKEND', 'VIRTUAL')
    monkeypatch.setattr(config, 'DRY_RUN', True)
    monkeypatch.setattr(config, 'GAME_ONLY', False, raising=False)
    manager = HardwareManager(config, Path(__file__).resolve().parents[2])
    manager._init_robot()
    runtime = manager.simulation_runtime
    bridge = manager.setup_digital_twin(start=False)
    state = GameState(allow_mouse_move=True)
    state.api_client.create_match = Mock()
    state.set_board_observer(bridge.reconcile_to_board_cells)
    try:
        assert state.sync_current_board()
        assert runtime.runtime_go_service_safe()['success']
        assert runtime.prepare_board_adjustment()['success']
        points = runtime.get_board_teaching_points()['points']
        center = np.mean(list(points.values()), axis=0)
        angle = np.deg2rad(3)
        rotation = np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        points = {k:(center + rotation @ (np.array(v)-center) + [10,0,0]).tolist() for k,v in points.items()}
        applied = runtime.apply_board_teaching_points(points)
        assert applied['success'], applied
        placement = runtime.placement_state
        identity = state.piece_ids[(6,4)]
        fen = state.current_fen
        # Measure physical settle BEFORE reconciliation can snap a body to its cell.
        actual_motion = manager.execute_piece_move
        evidence = []
        def observed_execution(*args, **kwargs):
            result = actual_motion(*args, **kwargs)
            if result.success:
                body = runtime.world.pieces[identity]
                actual = body.get_position_robot().copy()
                evidence.append(float(np.linalg.norm((actual-placement.cell_to_robot_xyz(5,4))[:2])*1000))
                assert runtime.find_nearest_cell(actual) == (5,4)
                assert runtime.world.get_attached_piece() is None
            return result
        manager.execute_piece_move = observed_execution
        handler = InputHandler(state, manager)
        handler.handle_keyboard(pygame.K_t)
        assert state.pick_test_mode
        handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(4,6))
        handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(4,5))
        assert not state.pick_test_fault, state.pick_test_fault
        assert len(evidence) == 1 and evidence[0] < 1, evidence
        piece = runtime.world.pieces[identity]
        assert runtime.find_nearest_cell(piece.get_position_robot()) == (5,4)
        error = np.linalg.norm((piece.get_position_robot()-placement.cell_to_robot_xyz(5,4))[:2])*1000
        assert error < 1, error
        assert runtime.world.get_attached_piece() is None
        assert runtime.backend.collision_guard_enabled
        assert state.current_fen == fen
        assert bridge._cells == state.pick_test_piece_ids
        assert not state.can_start_ai_turn()
        state.reset_game(manager)
        assert runtime.placement_state is placement
        assert len(runtime.world.pieces) == 32
        assert bridge._cells == state.piece_ids
        assert not state.pick_test_mode and not state.pick_test_resume_required
        print(f'SYSTEM manual GUI/PyBullet, yaw3 +10mm, XY error BEFORE sync {evidence[0]:.4f} mm, after sync {error:.4f} mm, reset32: PASS')
    finally:
        bridge.close()
        runtime.disconnect()
        runtime.world.close()

@pytest.mark.parametrize('activated,disable_code', [(False,0),(True,0),(True,112)])
def test_measurement_cleanup_disables_only_owned_activation_and_surfaces_failure(activated, disable_code):
    from src.ui.measurement_client import RobotMeasurement
    session = RobotMeasurement.__new__(RobotMeasurement)
    session.robot = Mock()
    session.robot.robot.RobotEnable.return_value = disable_code
    session.activation_attempted = activated
    if activated and disable_code:
        with pytest.raises(RuntimeError, match='112'): session.close()
    else:
        session.close()
    assert session.robot.physical_motion_authorized is False
    if activated: session.robot.robot.RobotEnable.assert_called_once_with(0)
    else: session.robot.robot.RobotEnable.assert_not_called()
    session.robot.robot.CloseRPC.assert_called_once()
    session.robot.gripper_ctrl.assert_not_called()
    session.robot.go_to_home_chess.assert_not_called()

@pytest.mark.parametrize('authorized,disable_code', [(False,0),(True,0),(True,112)])
def test_manual_fault_revocation_disables_only_previously_authorized_controller(authorized,disable_code):
    from src.hardware.robot_VIP import FR5Robot, RobotCommandError
    robot=FR5Robot.__new__(FR5Robot)
    robot.dry=False; robot.connected=True; robot.physical_motion_authorized=authorized
    robot.robot=Mock(); robot.robot.RobotEnable.return_value=disable_code
    if authorized and disable_code:
        with pytest.raises(RobotCommandError, match='112'): robot.deactivate_physical_control()
    else: assert robot.deactivate_physical_control()
    assert not robot.physical_motion_authorized
    if authorized: robot.robot.RobotEnable.assert_called_once_with(0)
    else: robot.robot.RobotEnable.assert_not_called()
    robot.robot.SetToolDO.assert_not_called()

@pytest.mark.parametrize('fault,expected', [('SDK 112','Test bị khóa'),(None,'Khôi phục bàn')])
def test_render_keeps_manual_fault_or_resume_gate_visible_after_status_timeout(fault,expected):
    import pygame
    renderer=BoardRenderer.__new__(BoardRenderer)
    renderer.screen=Mock(); renderer.log_font=Mock()
    renderer.log_font.size.return_value=(100,20)
    renderer._draw_panel=Mock()
    state={'pick_test_fault':fault,'pick_test_mode':False,'pick_test_resume_required':True,
           'status_message':'old status','status_expiry':0}
    with patch.object(pygame.draw,'circle'):
        renderer._draw_ai_status(state)
    assert any(expected in call.args[0] for call in renderer.log_font.render.call_args_list)
