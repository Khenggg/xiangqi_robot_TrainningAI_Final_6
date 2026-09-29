"""PyBullet regression for changing the simulated board using four surface points."""

import unittest
import numpy as np

from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.motion.resolver import MotionResolver
from src.simulation.runtime import VirtualXiangqiSimulation


class SimBoardTeachingTests(unittest.TestCase):
    def setUp(self):
        self.sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        self.sim.start()
        self.provider = FixedBoardPoseProvider(self.sim.world.board_placement_state)
        self.sim.bind_board_pose_provider(self.provider)
        self.resolver = MotionResolver(self.provider)
        prepared = self.sim.prepare_board_adjustment()
        self.assertTrue(prepared["success"], prepared)

    def tearDown(self):
        self.sim.stop()

    def test_lateral_shift_updates_every_authority_and_existing_piece(self):
        before = self.sim.get_board_teaching_points()["points"]
        planned_before = self.resolver._cell_to_pose_mm_deg(self.provider.get_board_placement_state(), 0, 0, 0.0)
        piece = next(iter(self.sim.world.pieces.values()))
        piece_before = piece.get_pose_robot_base()[0]
        points = {name: [value + (10.0 if i == 0 else 0.0) for i, value in enumerate(xyz)]
                  for name, xyz in before.items()}
        result = self.sim.apply_board_teaching_points(points)
        self.assertTrue(result["success"], result)
        state = self.sim.placement_state
        self.assertIs(state, self.sim.world.board_placement_state)
        self.assertIs(state, self.provider.get_board_placement_state())
        self.assertEqual(self.sim.backend.get_state_snapshot().placement_version, state.placement_version)
        planned_after = self.resolver._cell_to_pose_mm_deg(self.provider.get_board_placement_state(), 0, 0, 0.0)
        np.testing.assert_allclose(np.asarray(planned_after[:3]) - planned_before[:3], [10, 0, 0], atol=0.01)
        np.testing.assert_allclose(self.sim.world.get_board_pose()[0],
                                   state.board_local_to_robot(0, 0, -self.sim.world._board_half_z), atol=1e-6)
        np.testing.assert_allclose(piece.get_pose_robot_base()[0] - piece_before, [0.01, 0, 0], atol=1e-5)
        for name, cell in {"R1": (0, 0), "R2": (0, 8), "R3": (9, 8), "R4": (9, 0)}.items():
            np.testing.assert_allclose(state.cell_to_robot_xyz(*cell) * 1000, points[name], atol=0.01)

    def test_invalid_rectangle_preserves_old_state_and_bodies(self):
        old = self.sim.placement_state
        body_before = self.sim.world.get_board_pose()[0]
        points = self.sim.get_board_teaching_points()["points"]
        points["R2"][0] += 30.0
        result = self.sim.apply_board_teaching_points(points)
        self.assertFalse(result["success"], result)
        self.assertIs(old, self.sim.placement_state)
        self.assertIs(old, self.sim.world.board_placement_state)
        self.assertIs(old, self.provider.get_board_placement_state())
        np.testing.assert_allclose(self.sim.world.get_board_pose()[0], body_before, atol=1e-8)

    def test_small_rotation_uses_full_transform_for_piece_and_board(self):
        points = self.sim.get_board_teaching_points()["points"]
        center = np.mean(list(points.values()), axis=0)
        theta = np.deg2rad(3.0)
        rotation = np.array([[np.cos(theta), -np.sin(theta), 0.0],
                             [np.sin(theta), np.cos(theta), 0.0], [0.0, 0.0, 1.0]])
        rotated = {name: (center + rotation @ (np.asarray(xyz) - center)).tolist()
                   for name, xyz in points.items()}
        piece = next(iter(self.sim.world.pieces.values()))
        local_before = self.sim.placement_state.robot_to_board_local(piece.get_position_robot())
        result = self.sim.apply_board_teaching_points(rotated)
        self.assertTrue(result["success"], result)
        np.testing.assert_allclose(self.sim.placement_state.robot_to_board_local(piece.get_position_robot()),
                                   local_before, atol=1e-5)
        np.testing.assert_allclose(self.sim.placement_state.cell_to_robot_xyz(0, 0) * 1000,
                                   rotated["R1"], atol=0.01)

    def test_quarter_turn_updates_target_without_old_axis_formula(self):
        points = self.sim.get_board_teaching_points()["points"]
        center = np.mean(list(points.values()), axis=0)
        quarter_turn = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        rotated = {name: (center + quarter_turn @ (np.asarray(xyz) - center)).tolist()
                   for name, xyz in points.items()}
        result = self.sim.apply_board_teaching_points(rotated)
        self.assertTrue(result["success"], result)
        state = self.provider.get_board_placement_state()
        np.testing.assert_allclose(state.cell_to_robot_xyz(0, 0) * 1000.0, rotated["R1"], atol=0.01)
        planned = self.resolver._cell_to_pose_mm_deg(state, 0, 0, 0.0)
        np.testing.assert_allclose(planned[:3], rotated["R1"], atol=0.01)
        local = self.sim.validate_board_placement(sample_limit=4)
        self.assertEqual(local["passed_cells_count"], 4, local)

    def test_board_sweep_into_robot_is_rejected_without_mutation(self):
        old = self.sim.placement_state
        points = self.sim.get_board_teaching_points()["points"]
        near_base = {name: [xyz[0], xyz[1] - 300.0, xyz[2]] for name, xyz in points.items()}
        result = self.sim.apply_board_teaching_points(near_base)
        self.assertFalse(result["success"], result)
        self.assertEqual(result["status"], "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR")
        self.assertIs(self.sim.placement_state, old)
        self.assertIs(self.provider.get_board_placement_state(), old)

    def test_virtual_twin_adopts_new_pose_without_recovery_error(self):
        bridge = LiveTwinBridge(self.sim.backend, self.provider, world=self.sim.world,
                                physical=False, owns_world=False)
        self.sim.bind_board_pose_provider(self.provider, bridge)
        points = self.sim.get_board_teaching_points()["points"]
        shifted = {name: [xyz[0] + 4, xyz[1], xyz[2]] for name, xyz in points.items()}
        result = self.sim.apply_board_teaching_points(shifted)
        self.assertTrue(result["success"], result)
        self.assertIs(bridge.placement, self.sim.placement_state)
        self.assertTrue(bridge.poll_once(), bridge.last_error)

    def test_board_below_floor_is_rejected_and_piece_pose_restored(self):
        old = self.sim.placement_state
        piece = next(iter(self.sim.world.pieces.values()))
        piece_before = piece.get_pose_robot_base()[0]
        points = self.sim.get_board_teaching_points()["points"]
        below_floor = {name: [xyz[0], xyz[1], xyz[2] - 8] for name, xyz in points.items()}
        result = self.sim.apply_board_teaching_points(below_floor)
        self.assertFalse(result["success"], result)
        self.assertEqual(result["status"], "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR")
        self.assertIs(self.sim.placement_state, old)
        np.testing.assert_allclose(piece.get_pose_robot_base()[0], piece_before, atol=1e-8)

    def test_stale_editor_version_cannot_replace_newer_board_pose(self):
        points = self.sim.get_board_teaching_points()["points"]
        old_version = self.sim.placement_state.placement_version
        first = self.sim.apply_board_teaching_points(points, expected_placement_version=old_version)
        self.assertTrue(first["success"], first)
        current = self.sim.placement_state
        stale = self.sim.apply_board_teaching_points(points, expected_placement_version=old_version)
        self.assertEqual(stale["status"], "BOARD_TEACHING_POINTS_STALE")
        self.assertIs(self.sim.placement_state, current)

    def test_four_point_apply_requires_fresh_service_preparation(self):
        points = self.sim.get_board_teaching_points()["points"]
        old = self.sim.placement_state
        self.sim._board_adjustment_ready = False
        result = self.sim.apply_board_teaching_points(points)
        self.assertEqual(result["status"], "BOARD_RELOCATION_REJECTED_NOT_READY")
        self.assertIs(self.sim.placement_state, old)

    def test_sampled_full_route_uses_feasible_local_ik_branch(self):
        points = self.sim.get_board_teaching_points()["points"]
        shifted = {name: [xyz[0] + 10, xyz[1], xyz[2]] for name, xyz in points.items()}
        applied = self.sim.apply_board_teaching_points(shifted)
        self.assertTrue(applied["success"], applied)
        route = self.sim.validate_full_board_routes(sample_limit=1)
        self.assertEqual(route["status"], "FULL_BOARD_ROUTES_SAMPLE_SAFE", route)
        self.assertEqual(route["passed_routes"], 1)


if __name__ == "__main__":
    unittest.main()
