"""Recorded taught grid display, no SDK/controller/network construction."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.digital_twin.physical_board_display import PhysicalBoardDisplay
from src.digital_twin.physical_state_relay import PhysicalStateRelay

ROOT = Path(__file__).resolve().parents[2]


def display_setup(z=None):
    points = json.loads((ROOT/'calibration/physical_teaching_points_user0.json').read_text())['points']
    xyz = np.array([points[n]['pose'][:3] for n in ('R1', 'R2', 'R3', 'R4')])
    robot = SimpleNamespace(_validated_corners=lambda: xyz.copy(), user_num=0,
                            teaching_points_version=7)
    display = PhysicalBoardDisplay(robot, SimpleNamespace(BOARD_CALIBRATION_SURFACE_Z_MM=z), .0105)
    return display, xyz


def test_recorded_corners_keep_column_direction_and_independent_z():
    display, xyz = display_setup()
    for i, (row, col) in enumerate(((0,0),(0,8),(9,8),(9,0))):
        np.testing.assert_allclose(np.array(display.cell_robot(row, col))[:2]*1000, xyz[i,:2])
    assert display.cell_robot(0,8)[1] > display.cell_robot(0,0)[1]
    packet = display.packet()
    assert packet['motion_authority'] is False and packet['surface_z_verified'] is False
    assert packet['T_robot_from_board'] is None
    assert packet['board_surface_z_m'] == .0105  # Never use approach Z=220mm as surface.


def test_all_90_cells_match_recorded_bilinear_xy():
    display, xyz = display_setup(153.2)
    for row in range(10):
        for col in range(9):
            u, v = col/8, row/9
            expected = (1-v)*((1-u)*xyz[0]+u*xyz[1])+v*((1-u)*xyz[3]+u*xyz[2])
            np.testing.assert_allclose(display.cell_robot(row,col)[:2], expected[:2]/1000, atol=1e-12)
    assert display.packet()['surface_z_verified'] is True
    assert display.cell_robot(2,7)[2] == pytest.approx(.1532)


def test_semantic_projection_keeps_attached_and_captured_positions():
    display, _ = display_setup()
    packet = {'pieces': [dict(id='p', pose_world=[9,9,9]),
                         dict(id='held', is_grasped=True, pose_world=[1,2,3]),
                         dict(id='released', pose_world=[4,5,6]),
                         dict(id='captured', captured=True, pose_world=[7,8,9])]}
    world = SimpleNamespace(pieces={'p': SimpleNamespace(height_m=.01)})
    cells = {(2,7):'p',(0,0):'held',(1,1):'released',(3,3):'captured'}
    display.project_pieces(packet,cells,world,excluded=['released'])
    p = packet['pieces'][0]
    pos = display.cell_robot(2,7,.005)
    assert p['pose_robot'] == pos
    assert p['pose_world'] == [-pos[1],pos[2],-pos[0]]
    assert [p['pose_world'] for p in packet['pieces'][1:]] == [[1,2,3],[4,5,6],[7,8,9]]


def test_relay_broadcasts_taught_display_and_projects_snapshot_without_hardware():
    display, _ = display_setup()
    world = SimpleNamespace(layout_cfg={'pieces':[dict(id='p',row=0,col=8)]},
                            pieces={'p':SimpleNamespace(height_m=.01)},
                            get_snapshot=lambda:SimpleNamespace(to_dict=lambda:{'pieces':[dict(id='p')]}))
    telemetry = Mock()
    relay = PhysicalStateRelay(SimpleNamespace(ip='unused'),telemetry,'surface unknown',
                               world=world,owns_world=False,display_mapping=display)
    placement = telemetry.broadcast_custom.call_args.args[0]
    assert placement['placement_source'] == 'R1_R4_PHYSICAL_DISPLAY'
    piece = telemetry.update_world_state.call_args.args[0]['pieces'][0]
    assert piece['pose_robot'][:2] == pytest.approx([-.202,.547])
    assert relay.uncalibrated_board  # This does not grant calibrated motion authority.


@pytest.mark.parametrize('z',[True,float('nan'),float('inf')])
def test_invalid_surface_height_rejected(z):
    with pytest.raises(ValueError): display_setup(z)


def test_relay_attach_lift_release_uses_gripper_frame_not_nominal_cell():
    from src.domain.game_move import MoveContext, MoveActor
    from src.simulation.physics.world import VirtualPhysicalWorld
    import config
    display, _ = display_setup()
    world = VirtualPhysicalWorld(enable_gui=False)
    relay = PhysicalStateRelay(SimpleNamespace(ip='unused'),None,'surface unknown',
                               world=world,display_mapping=display)
    # Attach at the taught (0,8) location, ~330mm away from its nominal cell.
    context = MoveContext('black_rook_1',(0,8),(1,8),MoveActor.ROBOT)
    try:
        assert relay._cells[(0,8)] == context.piece_id
        relay.begin_command_animation(context)
        grasp = np.array(display.cell_robot(0,8,.005))
        gripper = world.gripper
        tcp = grasp - gripper.tcp_to_grasp_center  # identity tool quaternion
        gripper.set_tcp_pose(tcp,[0,0,0,1])
        relay.animate_command_gripper('gripper',True,config.GRIPPER_ACTION_CLOSE)
        piece = world.get_attached_piece()
        assert piece is not None
        np.testing.assert_allclose(piece.get_pose_robot_base()[0],grasp,atol=1e-7)
        np.testing.assert_allclose(gripper.T_gripper_piece[:3,3],0,atol=1e-7)
        gripper.set_tcp_pose(tcp+[0,0,.04],[0,0,0,1])
        np.testing.assert_allclose(piece.get_pose_robot_base()[0],grasp+[0,0,.04],atol=1e-7)
        relay.animate_command_gripper('gripper',False,config.GRIPPER_ACTION_RELEASE)
        assert world.get_attached_piece() is None
        np.testing.assert_allclose(piece.get_pose_robot_base()[0],grasp+[0,0,.04],atol=1e-7)
        relay.telemetry=Mock()
        relay.finish_command_animation()
        relay._publish_world()
        snap = relay.telemetry.update_world_state.call_args.args[0]
        released = next(p for p in snap['pieces'] if p['id']==context.piece_id)
        np.testing.assert_allclose(released['pose_robot'],grasp+[0,0,.04],atol=1e-7)
        # Only an actual board reconciliation establishes the destination cell.
        cells=dict(relay._cells);del cells[context.src];cells[context.dst]=context.piece_id
        assert relay.reconcile_to_board_cells(cells)
        assert not relay._released
        snap = relay.telemetry.update_world_state.call_args.args[0]
        placed=next(p for p in snap['pieces'] if p['id']==context.piece_id)
        np.testing.assert_allclose(placed['pose_robot'][:2],display.cell_robot(1,8)[:2],atol=1e-7)
    finally:
        relay.close()
