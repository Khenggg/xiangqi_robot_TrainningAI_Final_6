"""Scene orientation, semantic IDs and real PyBullet target-coordinate parity."""
import json
from pathlib import Path

import numpy as np
import pytest
from src.domain.board_pose import (
    BoardPlacementState, canonical_cell_to_robot_xyz_m, find_nearest_cell,
    compute_rotation_matrix,
)
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.simulation.runtime import VirtualXiangqiSimulation

ROOT = Path(__file__).resolve().parents[2]


def test_scene_black_side_negative_x_red_side_positive_x():
    scene = json.loads((ROOT/'shared/virtual_fr3_scene.json').read_text(encoding='utf-8'))
    board = scene['virtual_board_placement']
    state = BoardPlacementState.compute(0)
    assert state.board_yaw_deg == board['board_yaw_deg'] == 180
    center = np.asarray(board['board_center_in_robot_base_m'])
    np.testing.assert_allclose(state.board_center_robot_m[:2], center[:2], atol=1e-9)
    assert state.board_surface_z_robot_m == pytest.approx(center[2])
    assert np.mean([state.cell_to_robot_xyz(0,c)[0] for c in range(9)]) < center[0]
    assert np.mean([state.cell_to_robot_xyz(9,c)[0] for c in range(9)]) > center[0]
    assert np.linalg.det(state.R_robot_from_board) == pytest.approx(1)
    np.testing.assert_allclose(board['T_robot_from_board'], state.T_robot_from_board, atol=1e-9)
    for name,cell in [('R1',(0,0)),('R2',(0,8)),('R3',(9,8)),('R4',(9,0))]:
        np.testing.assert_allclose(board['teaching_points'][name],state.cell_to_robot_xyz(*cell)*1000,atol=1e-6)


@pytest.mark.parametrize('yaw',[180.,37.])
def test_every_default_provider_and_math_helper_follows_scene(monkeypatch,tmp_path,yaw):
    scene = json.loads((ROOT/'shared/virtual_fr3_scene.json').read_text(encoding='utf-8'))
    scene['virtual_board_placement']['board_yaw_deg'] = yaw
    path=tmp_path/'scene.json';path.write_text(json.dumps(scene),encoding='utf-8')
    monkeypatch.setenv('XIANGQI_SCENE_CONFIG',str(path))
    state=BoardPlacementState.compute(0)
    assert state.board_yaw_deg==yaw
    assert FixedBoardPoseProvider().get_board_placement_state().board_yaw_deg==yaw
    assert FixedBoardPoseProvider.from_forward_shift().get_board_placement_state().board_yaw_deg==yaw
    for row in range(10):
        for col in range(9):
            xyz=state.cell_to_robot_xyz(row,col)
            np.testing.assert_allclose(canonical_cell_to_robot_xyz_m(row,col),xyz,atol=1e-6)
            assert find_nearest_cell(xyz)==(row,col)
            assert find_nearest_cell(xyz,state.grid_origin_robot_m)==(row,col)
    explicit=BoardPlacementState.compute(0,board_yaw_deg=0.)
    assert explicit.board_yaw_deg==0
    np.testing.assert_allclose(explicit.R_robot_from_board,compute_rotation_matrix(0),atol=1e-12)


def test_real_world_and_runtime_targets_follow_scene_without_swapping_ids():
    layout=json.loads((ROOT/'shared/xiangqi_start_layout.json').read_text(encoding='utf-8'))['pieces']
    sim=VirtualXiangqiSimulation(auto_sync_telemetry=False)
    try:
        assert sim.placement_state.board_yaw_deg==180
        assert set(sim.world.pieces)=={p['id'] for p in layout}
        for item in layout:
            xyz=sim.world.pieces[item['id']].get_position_robot()
            expected=sim.placement_state.cell_to_robot_xyz(item['row'],item['col'])
            # PyBullet settling causes small lateral drift; cell identity and
            # planner coordinates below remain exact, with a 0.5mm fixture cap.
            assert np.linalg.norm(xyz[:2]-expected[:2]) < .0005
            assert sim.find_nearest_cell(xyz)==(item['row'],item['col'])
        for row in range(10):
            for col in range(9):
                target=sim.cell_to_robot_xyz(row,col)
                np.testing.assert_allclose(target[:2],sim.placement_state.cell_to_robot_xyz(row,col)[:2],atol=1e-9)
    finally:
        sim.stop()
