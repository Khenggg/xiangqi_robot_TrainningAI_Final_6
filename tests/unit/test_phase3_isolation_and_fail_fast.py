"""
Unit tests for Phase 3 Corrective Pass — Runtime / Validation Isolation & Fail-Fast.

Covers Sections 27 to 37:
1. test_validation_rejected_during_motion
2. test_dry_run_gripper_history_and_attached_piece_isolation
3. test_movej_prevalidation_attached_piece_invariance
4. test_pick_piece_uses_current_placement_not_nominal_dataset
5. test_pick_piece_fail_fast_cleanup
6. test_place_piece_land_failure_does_not_release
7. test_dynamic_recovery_safe_z
8. test_board_relocation_rejected_when_piece_falling_or_settling
9. test_calibration_non_nominal_origin
10. test_board_center_and_surface_semantics
11. test_nearest_cell_consistency_after_shift
"""

import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import get_physical_geometry
from src.simulation.placement import (
    BoardPlacementState,
    BoardPlacementAnalyzer,
    canonical_cell_to_robot_xyz_m,
    find_nearest_cell,
    load_nominal_scene_placement,
)
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.state import PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation, PlaceResult
from src.simulation.virtual_fr3_backend import VirtualFR3Backend, PlannedTrajectory
import pybullet as p_bullet


class Phase3IsolationAndFailFastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geom = get_physical_geometry()
        cls.kinematics = FR3Kinematics()

    def setUp(self):
        self.world = VirtualPhysicalWorld(enable_gui=False)
        self.backend = VirtualFR3Backend(kinematics=self.kinematics)
        self.backend.connect()
        self.guard = FR3CollisionGuard(world=self.world)
        self.backend.set_collision_guard(self.guard)
        self.sim = VirtualXiangqiSimulation(world=self.world, backend=self.backend)

    def tearDown(self):
        try:
            self.backend.disconnect()
        except Exception:
            pass
        try:
            self.world.disconnect()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Test 1 (Section 27): Validation rejected during motion
    # -------------------------------------------------------------------------
    def test_validation_rejected_during_motion(self):
        """Verify busy rejection (VALIDATION_REJECTED_BUSY) when robot is moving or active."""
        # 1. Simulate robot in MOVING state
        self.backend._motion_state = "MOVING"
        res_bp = self.sim.validate_board_placement()
        self.assertFalse(res_bp.get("success", True))
        self.assertEqual(res_bp.get("status"), "VALIDATION_REJECTED_BUSY")
        self.assertIn("moving", res_bp.get("reason", "").lower())

        res_fb = self.sim.validate_full_board_routes()
        self.assertFalse(res_fb.get("success", True))
        self.assertEqual(res_fb.get("status"), "VALIDATION_REJECTED_BUSY")

        # 2. Simulate trajectory stage active
        self.backend._motion_state = "IDLE"
        self.backend.set_trajectory_stage("TRANSIT")
        res_bp_traj = self.sim.validate_board_placement()
        self.assertEqual(res_bp_traj.get("status"), "VALIDATION_REJECTED_BUSY")

        self.backend.set_trajectory_stage("IDLE")

        # 3. Conversely, execute_3stage_trajectory rejected when validation is running
        self.sim._validation_in_progress = True
        traj_res = self.sim.execute_3stage_trajectory((0, 4), (2, 4))
        self.assertFalse(traj_res.get("success"))
        self.assertIn("progress", traj_res.get("error", "").lower())
        self.sim._validation_in_progress = False

    # -------------------------------------------------------------------------
    # Test 2 (Section 28): Side-effect-free dry-run (gripper history & attached piece isolation)
    # -------------------------------------------------------------------------
    def test_dry_run_gripper_history_and_attached_piece_isolation(self):
        """Dry-run IK and collision checks must not mutate gripper history, TCP or attached pieces."""
        gripper = self.world.gripper
        init_history_len = len(gripper._history)
        init_tcp_pos = np.array(gripper.tcp_pos, copy=True)
        init_tcp_quat = np.array(gripper.tcp_quat, copy=True)

        # Attach a dummy piece
        piece = self.world.get_piece("red_king_0")
        self.assertIsNotNone(piece)
        gripper.attached_piece = piece
        piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER
        init_piece_pos = np.array(piece.get_position_robot(), copy=True)

        # Call candidate collision configuration sync
        candidate_q = [0.1, -0.5, 1.2, -0.7, -1.5, 0.2]
        self.world.sync_robot_collision_configuration(candidate_q)

        # Verify zero side effects on authoritative runtime state
        self.assertEqual(len(gripper._history), init_history_len, "Dry-run appended to gripper history!")
        self.assertTrue(np.allclose(gripper.tcp_pos, init_tcp_pos), "Dry-run mutated gripper.tcp_pos!")
        self.assertTrue(np.allclose(gripper.tcp_quat, init_tcp_quat), "Dry-run mutated gripper.tcp_quat!")
        self.assertTrue(
            np.allclose(piece.get_position_robot(), init_piece_pos, atol=1e-5),
            "Dry-run moved attached piece!",
        )

        # Reset attached piece
        gripper.attached_piece = None
        piece.physical_state = PiecePhysicalState.ON_BOARD

    # -------------------------------------------------------------------------
    # Test 3 (Section 29): MoveJ pre-validation attached piece invariance
    # -------------------------------------------------------------------------
    def test_movej_prevalidation_attached_piece_invariance(self):
        """Attached piece pose must remain completely invariant during MoveJ prevalidation."""
        gripper = self.world.gripper
        piece = self.world.get_piece("red_king_0")
        gripper.attached_piece = piece
        piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER
        init_piece_pos = np.array(piece.get_position_robot(), copy=True)

        # Plan / pre-validate a trajectory through collision guard
        test_waypoints = [
            [0.0, -0.785, 1.57, -0.785, -1.57, 0.0],
            [0.05, -0.75, 1.50, -0.75, -1.57, 0.0],
            [0.10, -0.70, 1.45, -0.70, -1.57, 0.0],
        ]
        col_res = self.guard.validate_trajectory(
            test_waypoints,
            allowed_grasp_piece_id="red_king_0",
            restore_state=True,
        )

        # Verify piece remained in exact initial position
        curr_piece_pos = piece.get_position_robot()
        self.assertTrue(
            np.allclose(curr_piece_pos, init_piece_pos, atol=1e-5),
            f"Pre-validation shifted attached piece! Init: {init_piece_pos}, Curr: {curr_piece_pos}",
        )
        gripper.attached_piece = None
        piece.physical_state = PiecePhysicalState.ON_BOARD

    # -------------------------------------------------------------------------
    # Test 4 (Section 30): Pick piece uses current placement, not nominal dataset
    # -------------------------------------------------------------------------
    def test_pick_piece_uses_current_placement_not_nominal_dataset(self):
        """Pick piece must compute fresh IK for shifted position; dataset q is strictly an IK seed."""
        # Shift board forward by 30mm
        self.sim.prepare_board_adjustment()
        self.sim.set_board_placement(forward_shift_mm=30.0)
        piece = self.world.get_piece("red_king_0")
        self.assertIsNotNone(piece)

        # Position piece at (0, 4) shifted: X should be -0.210m
        shifted_xyz = self.sim.cell_to_robot_xyz_m(0, 4, 0.0105 + self.geom.piece_height_mm / 2000.0)
        p_bullet.resetBasePositionAndOrientation(
            piece.body_id,
            shifted_xyz,
            [0, 0, 0, 1],
            physicsClientId=self.world.client_id,
        )

        with patch.object(self.backend, "solve_tcp_ik", wraps=self.backend.solve_tcp_ik) as mock_ik:
            # We don't need full motion execution, mock move_joint_with_lift_recovery to succeed
            with patch.object(self.backend, "move_joint_with_lift_recovery", return_value=True):
                with patch.object(self.backend, "move_cartesian", return_value=True):
                    with patch.object(self.world, "try_grasp", return_value=True):
                        self.sim.pick_piece("red_king_0")

            # Check that IK was called with the shifted X coordinate (-390 mm), NOT nominal (-360 mm)
            ik_calls = mock_ik.call_args_list
            self.assertGreater(len(ik_calls), 0)
            hover_target = ik_calls[0][0][0]  # target_tcp_pose_mm_deg
            self.assertAlmostEqual(hover_target[0], -390.0, delta=2.0)

    # -------------------------------------------------------------------------
    # Test 5 (Section 31): Pick piece fail-fast cleanup
    # -------------------------------------------------------------------------
    def test_pick_piece_fail_fast_cleanup(self):
        """Fail-fast: if approach/hover fails, gripper does NOT close and allowed_grasp_piece_id cleans up."""
        with patch.object(self.backend, "move_joint_with_lift_recovery", return_value=False):
            res = self.sim.pick_piece("red_king_0")
            self.assertFalse(res.success)
            self.assertIn("rejected", res.reason.lower())
            self.assertFalse(self.backend.get_state_snapshot().gripper_closed)
            self.assertIsNone(self.backend._allowed_grasp_piece_id, "allowed_grasp_piece_id was not cleaned up!")

        # Also test descent failure where allowed_grasp_piece_id was set
        with patch.object(self.backend, "move_joint_with_lift_recovery", return_value=True):
            with patch.object(self.backend, "move_cartesian", side_effect=[True, False]):
                res2 = self.sim.pick_piece("red_king_0")
                self.assertFalse(res2.success)
                self.assertFalse(self.backend.get_state_snapshot().gripper_closed)
                self.assertIsNone(self.backend._allowed_grasp_piece_id, "allowed_grasp_piece_id was not cleaned up after descent failure!")

    # -------------------------------------------------------------------------
    # Test 6 (Section 32): Place piece land failure does NOT release piece
    # -------------------------------------------------------------------------
    def test_place_piece_land_failure_does_not_release(self):
        """CRITICAL FAIL-FAST: If LAND fails, gripper must NOT open and piece must NOT be released."""
        piece = self.world.get_piece("red_king_0")
        self.world.gripper.attached_piece = piece
        piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER
        self.backend.set_gripper(True)

        # Simulate landing failure (e.g. collision or unreachability)
        with patch.object(self.backend, "move_joint_with_lift_recovery", return_value=True):
            with patch.object(self.backend, "move_cartesian", return_value=False):
                res = self.sim.place_piece("red_king_0", target_cell=(0, 4))

        self.assertFalse(res.success)
        self.assertEqual(res.status, "LAND_FAILED")
        # Gripper must remain closed
        self.assertTrue(self.backend.get_state_snapshot().gripper_closed, "Gripper opened after LAND failure!")
        # Piece must still be attached
        self.assertIsNotNone(self.world.get_attached_piece(), "Piece was released after LAND failure!")
        self.assertEqual(self.world.get_attached_piece().piece_id, "red_king_0")

        # Cleanup
        self.world.gripper.attached_piece = None
        piece.physical_state = PiecePhysicalState.ON_BOARD

    # -------------------------------------------------------------------------
    # Test 7 (Section 33): Dynamic recovery safe-Z
    # -------------------------------------------------------------------------
    def test_dynamic_recovery_safe_z(self):
        """Dynamic recovery must respect provided safe_plane_z_m rather than hardcoded 0.0805m."""
        dynamic_safe_z = 0.055  # 55mm safe transit plane
        with patch.object(self.backend, "move_joint", return_value=False):
            self.backend._motion_state = "COLLISION_REJECTED"
            with patch.object(self.backend, "move_cartesian", return_value=True) as mock_cart:
                self.backend.move_joint_with_lift_recovery(
                    target_joints_deg=[0, -45, 90, -45, -90, 0],
                    safe_plane_z_m=dynamic_safe_z,
                )
                self.assertGreater(mock_cart.call_count, 0)
                lift_target_mm = mock_cart.call_args_list[0][0][0]
                lift_z_m = lift_target_mm[2] / 1000.0
                self.assertGreaterEqual(lift_z_m, dynamic_safe_z)

    # -------------------------------------------------------------------------
    # Test 8 (Section 34): Board relocation rejected when pieces falling or settling
    # -------------------------------------------------------------------------
    def test_board_relocation_rejected_when_piece_falling_or_settling(self):
        """Board relocation rejected with BOARD_RELOCATION_REJECTED_WORLD_NOT_SETTLED if transient."""
        piece = self.world.get_piece("red_king_0")

        # 1. FALLING
        piece.physical_state = PiecePhysicalState.FALLING
        res_falling = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertFalse(res_falling.get("success"))
        self.assertEqual(res_falling.get("status"), "BOARD_RELOCATION_REJECTED_WORLD_NOT_SETTLED")

        # 2. SETTLING
        piece.physical_state = PiecePhysicalState.SETTLING
        res_settling = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertFalse(res_settling.get("success"))
        self.assertEqual(res_settling.get("status"), "BOARD_RELOCATION_REJECTED_WORLD_NOT_SETTLED")

        # 3. ATTACHED_TO_GRIPPER
        piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER
        self.world.gripper.attached_piece = piece
        res_attached = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertFalse(res_attached.get("success"))
        self.assertEqual(res_attached.get("status"), "BOARD_RELOCATION_REJECTED_WORLD_NOT_SETTLED")

        # Reset
        self.world.gripper.attached_piece = None
        piece.physical_state = PiecePhysicalState.ON_BOARD

    # -------------------------------------------------------------------------
    # Test 9 (Section 35): Calibration non-nominal origin
    # -------------------------------------------------------------------------
    def test_calibration_non_nominal_origin(self):
        """BoardPlacementState preserves non-nominal calibrated origin."""
        calibrated_origin = [-0.195, -0.155, 0.0120]
        state = BoardPlacementState.compute(
            forward_shift_mm=15.0,
            safe_transit_height_mm=50.0,
            board_height_offset_mm=2.0,
            nominal_grid_origin_m=calibrated_origin,
            nominal_board_surface_z_m=0.0120,
        )
        # Shifted x0 = -0.360 - 0.015 + 0.160 = -0.215
        # Shifted y0 = 0.0 - (-0.180) = 0.180
        # Shifted z0 = 0.0120 + 0.002 = 0.0140
        self.assertAlmostEqual(state.grid_origin_robot_m[0], -0.215, places=4)
        self.assertAlmostEqual(state.grid_origin_robot_m[2], 0.0140, places=4)
        self.assertAlmostEqual(state.board_surface_z_robot_m, 0.0140, places=4)

    # -------------------------------------------------------------------------
    # Test 10 (Section 36): Board center and surface semantics
    # -------------------------------------------------------------------------
    def test_board_center_and_surface_semantics(self):
        """Disambiguate physical center (half thickness) vs surface Z vs visual root."""
        state = BoardPlacementState.compute(
            forward_shift_mm=0.0,
            board_height_offset_mm=0.0,
            nominal_grid_origin_m=[-0.200, 0.180, 0.0105],
            nominal_board_center_robot_m=[-0.360, 0.0, 0.00525],
            nominal_board_surface_z_m=0.0105,
        )
        # Physical box center has z at 0.00525m
        self.assertAlmostEqual(state.physical_board_center_robot_m[2], 0.00525, places=4)
        # Playing surface is at 0.0105m
        self.assertAlmostEqual(state.board_surface_z_robot_m, 0.0105, places=4)
        # Three.js visual root has Y at 0.0105m, Z at 0.360m
        self.assertAlmostEqual(state.board_visual_root_world_m[1], 0.0105, places=4)
        self.assertAlmostEqual(state.board_visual_root_world_m[2], 0.360, places=4)

        d_dict = state.to_dict()
        self.assertIn("physical_board_center_robot_m", d_dict)
        self.assertIn("board_surface_z_robot_m", d_dict)
        self.assertIn("board_visual_root_world_m", d_dict)

    # -------------------------------------------------------------------------
    # Test 11 (Section 37): Nearest cell consistency after shift
    # -------------------------------------------------------------------------
    def test_nearest_cell_consistency_after_shift(self):
        """find_nearest_cell must round-trip accurately under forward shift."""
        self.sim.prepare_board_adjustment()
        self.sim.set_board_placement(forward_shift_mm=30.0)

        test_cells = [(0, 0), (0, 4), (4, 4), (9, 0), (9, 8)]
        for r, c in test_cells:
            xyz = self.sim.cell_to_robot_xyz_m(r, c)
            mapped_r, mapped_c = self.sim.find_nearest_cell(xyz)
            self.assertEqual((mapped_r, mapped_c), (r, c), f"Failed for cell ({r}, {c})")

        # Test standalone find_nearest_cell function from placement.py
        shifted_origin = self.sim.placement_state.grid_origin_robot_m
        for r, c in test_cells:
            xyz = self.sim.cell_to_robot_xyz_m(r, c)
            mapped_r, mapped_c = find_nearest_cell(xyz, grid_origin_robot_m=shifted_origin)
            self.assertEqual((mapped_r, mapped_c), (r, c))

    # -------------------------------------------------------------------------
    # Test 12: Full backend data reset (RESET_ALL_BACKEND_DATA)
    # -------------------------------------------------------------------------
    def test_reset_all_backend_data(self):
        """Verify full reset restores robot HOME, canonical piece positions, and nominal board placement."""
        # 1. Mutate state: shift board, move robot, attach piece
        self.sim.prepare_board_adjustment()
        self.sim.set_board_placement(forward_shift_mm=30.0)
        piece = self.world.get_piece("red_king_0")
        self.world.gripper.attached_piece = piece
        piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER
        self.backend.set_gripper(True)
        self.backend._joints_deg = [10.0, -30.0, 80.0, -50.0, -85.0, 5.0]

        # 2. Invoke full reset via client command handler
        self.sim._handle_client_command({"command": "RESET_ALL_BACKEND_DATA"})

        # 3. Assertions
        # Board placement restored to nominal (d=0)
        self.assertAlmostEqual(self.sim.placement_state.forward_shift_mm, 0.0)
        self.assertAlmostEqual(self.sim.placement_state.grid_origin_robot_m[0], -0.200, places=4)
        # Gripper open and piece detached
        self.assertFalse(self.backend.get_state_snapshot().gripper_closed)
        self.assertIsNone(self.world.get_attached_piece())
        # Robot returned to HOME pose
        self.assertTrue(np.allclose(self.backend.get_state_snapshot().joints_deg, [0.0, -45.0, 90.0, -45.0, -90.0, 0.0], atol=1e-2))
        # Piece position restored to canonical grid (red_king_0 is at row 9, col 4: x = -0.360, y = -0.180)
        pos, _ = piece.get_pose_robot_base()
        self.assertAlmostEqual(pos[0], -0.360, delta=0.01)
        self.assertAlmostEqual(pos[1], -0.180, delta=0.01)
        self.assertIn(piece.physical_state, (PiecePhysicalState.ON_BOARD, PiecePhysicalState.RESTING))


if __name__ == "__main__":
    unittest.main()

