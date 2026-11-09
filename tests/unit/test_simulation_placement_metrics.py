"""Pure analytical placement checks: no simulator, hardware, IK or datasets."""
import json
import math
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from src.domain.board_pose import BoardPlacementState, load_nominal_scene_placement
from src.simulation.placement import BoardPlacementAnalyzer


@pytest.fixture
def analyzer():
    return BoardPlacementAnalyzer(kinematics=SimpleNamespace(MAX_REACH_RADIUS_M=0.65))


def measured_points(state, analyzer, height_mm):
    cells = np.array([state.cell_to_robot_xyz(row, col) for row in range(10) for col in range(9)])
    approach = cells.copy()
    approach[:, 2] += height_mm / 1000 + analyzer.tool_length_m
    grasp = cells.copy()
    grasp[:, 2] += analyzer.geom.piece_height_mm / 2000 + analyzer.tool_length_m
    return cells, approach, grasp


def test_default_analysis_follows_current_scene_instead_of_yaw90(analyzer):
    scene = load_nominal_scene_placement()
    result = analyzer.compute_geometric_precheck(0)
    assert result["board_yaw_deg"] == scene["board_yaw_deg"]
    assert result["is_geometric_pass"] is True
    assert result["near_grid_depth_mm"] == pytest.approx(3.8, abs=.01)
    assert result["far_grid_depth_mm"] == pytest.approx(203.8, abs=.01)
    assert result["near_board_edge_distance_mm"] == 0
    assert result["far_approach_distance_mm"] == pytest.approx(625.9431923, abs=.01)


@pytest.mark.parametrize("yaw", [0, 90, 180, 37])
@pytest.mark.parametrize("shift", [-10, 0, 15])
def test_all90_extrema_follow_authoritative_transform(analyzer, yaw, shift):
    state = BoardPlacementState.compute(shift, board_yaw_deg=yaw, board_height_offset_mm=7,
                                        safe_transit_height_mm=50)
    original = state.T_robot_from_board.copy()
    result = analyzer.compute_geometric_precheck(shift, 50, placement_state=state)
    cells, approach, grasp = measured_points(state, analyzer, 50)
    assert result["near_grid_depth_mm"] == pytest.approx(np.abs(cells[:, 0]).min()*1000, abs=.01)
    assert result["far_grid_depth_mm"] == pytest.approx(np.abs(cells[:, 0]).max()*1000, abs=.01)
    assert result["far_approach_distance_mm"] == pytest.approx(np.linalg.norm(approach, axis=1).max()*1000, abs=.01)
    assert result["far_grasp_distance_mm"] == pytest.approx(np.linalg.norm(grasp, axis=1).max()*1000, abs=.01)
    assert result["board_yaw_deg"] == yaw
    np.testing.assert_array_equal(state.T_robot_from_board, original)
    assert not np.allclose(state.cell_to_robot_xyz(2, 7), state.cell_to_robot_xyz(7, 2))


@pytest.mark.parametrize("yaw", [0, 90, 180, 37])
def test_reported_limits_are_conservative_and_cover_every_cell(analyzer, yaw):
    result = analyzer.compute_geometric_precheck(15, 50, board_yaw_deg=yaw)
    d_max = result["d_max_for_current_h_mm"]
    state = BoardPlacementState.compute(d_max, board_yaw_deg=yaw)
    _, approach, grasp = measured_points(state, analyzer, 50)
    assert max(np.linalg.norm(approach, axis=1).max(), np.linalg.norm(grasp, axis=1).max())*1000 <= 650 + .001
    beyond = BoardPlacementState.compute(d_max + .02, board_yaw_deg=yaw)
    assert np.linalg.norm(measured_points(beyond, analyzer, 50)[1], axis=1).max()*1000 > 650
    H_max = result["h_max_for_current_d_mm"]
    current = BoardPlacementState.compute(15, board_yaw_deg=yaw)
    if H_max is None:
        # Changing transit height cannot repair an already unreachable grasp.
        assert np.linalg.norm(measured_points(current, analyzer, 0)[2], axis=1).max()*1000 > 650
    else:
        assert np.linalg.norm(measured_points(current, analyzer, H_max)[1], axis=1).max()*1000 <= 650
        assert np.linalg.norm(measured_points(current, analyzer, H_max+.02)[1], axis=1).max()*1000 > 650


def test_explicit_surface_changes_computed_targets_not_only_report(analyzer):
    result = analyzer.compute_geometric_precheck(0, 50, board_surface_mm=31.5, board_yaw_deg=180)
    state = BoardPlacementState.compute(0, board_yaw_deg=180, nominal_board_surface_z_m=.0315)
    assert result["board_surface_z_mm"] == 31.5
    assert result["far_approach_distance_mm"] == pytest.approx(
        np.linalg.norm(measured_points(state, analyzer, 50)[1], axis=1).max()*1000, abs=.01)


def test_supplied_translated_pose_is_used_without_nominal_scene_fallback(analyzer):
    state = BoardPlacementState.compute(0, board_yaw_deg=180,
                                        nominal_board_center_robot_m=[.111, .250, .01])
    result = analyzer.compute_geometric_precheck(0, 70, placement_state=state)
    assert result["board_center_distance_mm"] == 111
    assert result["far_approach_distance_mm"] == pytest.approx(
        np.linalg.norm(measured_points(state, analyzer, 70)[1], axis=1).max()*1000, abs=.01)


@pytest.mark.parametrize("invalid", [math.nan, math.inf])
def test_invalid_analysis_is_unknown_and_json_safe(analyzer, invalid):
    result = analyzer.compute_geometric_precheck(invalid)
    assert result["status"] == "GEOMETRIC UNKNOWN"
    assert result["is_geometric_pass"] is False
    assert result["far_approach_distance_mm"] is None
    json.dumps(result, allow_nan=False)


def test_backend_and_viewer_analysis_have_numeric_parity(analyzer):
    node = shutil.which("node")
    assert node, "Node is required for the backend/viewer geometry contract"
    root = Path(__file__).resolve().parents[2]
    cases = []
    for yaw in [0, 90, 180, 37]:
        state = BoardPlacementState.compute(15, board_yaw_deg=yaw, board_height_offset_mm=7,
                                            safe_transit_height_mm=50)
        cases.append({"placement": state.to_dict(), "analysis": analyzer.compute_geometric_precheck(
            15, 50, placement_state=state)})
    javascript = """
import fs from 'node:fs';
import {parsePhysicalGeometry} from './robot-3d-viewer/geometry.mjs';
import {computePlacementMetrics} from './robot-3d-viewer/placement_metrics.mjs';
const payload=JSON.parse(fs.readFileSync(0,'utf8'));
const geo=parsePhysicalGeometry(JSON.parse(fs.readFileSync('shared/physical_geometry.json','utf8')));
console.log(JSON.stringify(payload.cases.map(item=>computePlacementMetrics(item.placement,geo,payload.tool))));
"""
    completed = subprocess.run([node, "--input-type=module", "-e", javascript], cwd=root,
                               input=json.dumps({"cases": cases, "tool": analyzer.tool_length_m}),
                               text=True, capture_output=True, timeout=15, check=True)
    viewer = json.loads(completed.stdout)
    mapping = {"near_grid_depth_mm": "near_grid_depth_mm", "far_grid_depth_mm": "far_grid_depth_mm",
               "near_board_edge_distance_mm": "near_board_edge_distance_mm",
               "far_board_edge_distance_mm": "far_board_edge_distance_mm",
               "board_center_distance_mm": "board_center_distance_mm",
               "far_approach_distance_mm": "D_far_app", "far_grasp_distance_mm": "D_far_grasp",
               "d_max_for_current_h_mm": "d_max", "h_max_for_current_d_mm": "H_max"}
    for case, observed in zip(cases, viewer, strict=True):
        for backend_name, viewer_name in mapping.items():
            assert case["analysis"][backend_name] == pytest.approx(observed[viewer_name], abs=.02)
