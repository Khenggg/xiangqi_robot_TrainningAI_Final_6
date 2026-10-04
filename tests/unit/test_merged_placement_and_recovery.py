import numpy as np
import pytest
from unittest.mock import patch

from src.domain.board_pose import BoardPlacementState, canonical_cell_to_robot_xyz_m, find_nearest_cell
from src.simulation.runtime import VirtualXiangqiSimulation


@pytest.mark.parametrize("yaw", [0., 37., 90., 180., -90.])
def test_non_nominal_grid_moves_and_round_trips(yaw):
    origin = [0.123, -0.456, 0.031]
    state = BoardPlacementState.compute(0., board_yaw_deg=yaw, nominal_grid_origin_m=origin,
                                        nominal_board_surface_z_m=origin[2])
    np.testing.assert_allclose(state.cell_to_robot_xyz(0, 0), origin, atol=1e-6)
    for row, col in [(0, 0), (2, 7), (7, 2), (9, 8)]:
        xyz = state.cell_to_robot_xyz(row, col)
        np.testing.assert_allclose(canonical_cell_to_robot_xyz_m(row, col, nominal_x0=origin[0],
                                  nominal_y0=origin[1], z_m=origin[2], board_yaw_deg=yaw), xyz, atol=1e-6)
        assert find_nearest_cell(xyz, origin, board_yaw_deg=yaw) == (row, col)
    shifted = BoardPlacementState.compute(17., board_yaw_deg=yaw, nominal_grid_origin_m=origin,
                                          nominal_board_surface_z_m=origin[2])
    np.testing.assert_allclose(shifted.cell_to_robot_xyz(2, 7) - state.cell_to_robot_xyz(2, 7),
                              state.R_robot_from_board[:, 0] * .017, atol=1e-6)


def test_reset_failure_preserves_error_and_does_not_reset_board():
    sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
    sim.start()
    try:
        sim.backend._last_error = "blocked home trajectory"
        before = sim.placement_state.to_dict()
        with patch.object(sim.backend, "set_gripper", return_value=True), \
             patch.object(sim.backend, "reset_to_home", return_value=False), \
             patch.object(sim, "reset_board_placement") as reset_board:
            result = sim.full_reset()
        assert not result["success"]
        assert result["status"] == "RESET_HOME_REJECTED"
        assert sim.backend._last_error == "blocked home trajectory"
        assert sim.placement_state.to_dict() == before
        reset_board.assert_not_called()
    finally:
        sim.stop()
