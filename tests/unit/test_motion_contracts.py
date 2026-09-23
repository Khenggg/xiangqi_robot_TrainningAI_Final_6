"""
Unit Tests for Phase 3A Shared Motion Contracts & Choreography Foundation.

Tests exercise actual production contracts, stage vocabulary, failure taxonomy,
payload semantics, plan builders, and two-layer task intents without requiring
FAIRINO SDK, PyBullet, Camera, or real physical robot hardware.
"""

import math
from typing import List, Tuple
import unittest

from src.motion import (
    BoardPickIntent,
    BoardPlaceIntent,
    CaptureIntent,
    GripperCommand,
    MotionCoordinator,
    MotionExecutionResult,
    MotionFailureCategory,
    MotionPlan,
    MotionProfile,
    MotionStage,
    MotionStep,
    MotionType,
    MotionWaypoint,
    PayloadState,
    PieceMoveIntent,
    build_capture_plan,
    build_move_plan,
    build_pick_plan,
    build_place_plan,
    build_service_retreat_plan,
    CartesianWaypoint,
    JointWaypoint,
)


class MotionContractsTests(unittest.TestCase):
    """Test suite for Phase 3A shared motion domain contracts."""

    def test_motion_stage_vocabulary(self):
        """Verify MotionStage contains all standard lifecycle and retreat stages."""
        expected_stages = {
            MotionStage.PREPOSITION,
            MotionStage.APPROACH,
            MotionStage.LAND,
            MotionStage.GRIP,
            MotionStage.LIFT,
            MotionStage.PAYLOAD_CLEAR,
            MotionStage.TRANSIT,
            MotionStage.PLACE_APPROACH,
            MotionStage.PLACE_LAND,
            MotionStage.RELEASE,
            MotionStage.SETTLE,
            MotionStage.POST_RELEASE_LIFT,
            MotionStage.CLEAR_BOARD,
            MotionStage.SERVICE_RETREAT,
            MotionStage.SERVICE_SAFE,
            MotionStage.COMPLETE,
            MotionStage.RECOVERY,
        }
        for st in expected_stages:
            self.assertIsInstance(st, MotionStage)
            self.assertTrue(len(st.name) > 0)

    def test_motion_waypoint_contract_and_immutability(self):
        """Verify MotionWaypoint value object guarantees immutability and valid coordinates."""
        wp = MotionWaypoint(
            position_mm=(-250.5, 120.0, 45.0),
            orientation_deg=(180.0, 0.0, 90.0),
            stage=MotionStage.APPROACH,
            speed_factor=1.2,
            tolerance_mm=1.0,
            label="Safe approach pose",
            metadata={"cell": (4, 0)},
        )
        self.assertEqual(wp.position_mm, (-250.5, 120.0, 45.0))
        self.assertEqual(wp.orientation_deg, (180.0, 0.0, 90.0))
        self.assertEqual(wp.stage, MotionStage.APPROACH)
        self.assertEqual(wp.speed_factor, 1.2)
        self.assertEqual(wp.tolerance_mm, 1.0)
        self.assertEqual(wp.pose_mm_deg, (-250.5, 120.0, 45.0, 180.0, 0.0, 90.0))

        # Immutability check
        with self.assertRaises((TypeError, AttributeError)):
            wp.position_mm = (-300.0, 0.0, 50.0)  # type: ignore

        # Invalid speed factor check
        with self.assertRaises(ValueError):
            MotionWaypoint(
                position_mm=(0.0, 0.0, 0.0),
                orientation_deg=(0.0, 0.0, 0.0),
                stage=MotionStage.LAND,
                speed_factor=-0.5,
            )

        # Invalid coordinate length check
        with self.assertRaises(ValueError):
            MotionWaypoint(
                position_mm=(0.0, 0.0),  # type: ignore
                orientation_deg=(0.0, 0.0, 0.0),
                stage=MotionStage.LAND,
            )

    def test_motion_waypoint_from_pose_sequence(self):
        """Verify construction from a 6-element pose sequence."""
        pose = [-200.0, 100.0, 30.0, 175.0, 2.0, 88.0]
        wp = MotionWaypoint.from_pose_sequence(
            pose_6d=pose,
            stage=MotionStage.LAND,
            speed_factor=0.8,
            label="Descent waypoint",
        )
        self.assertEqual(wp.position_mm, (-200.0, 100.0, 30.0))
        self.assertEqual(wp.orientation_deg, (175.0, 2.0, 88.0))
        self.assertEqual(wp.stage, MotionStage.LAND)

        # Invalid pose sequence length
        with self.assertRaises(ValueError):
            MotionWaypoint.from_pose_sequence([0.0, 0.0, 0.0], stage=MotionStage.LAND)

    def test_metadata_immutability_and_defensive_copy(self):
        """Verify mutating caller metadata dictionary does not affect stored contract state."""
        meta = {"original_key": "original_val", "nested": {"counter": 1}}
        wp = MotionWaypoint(
            position_mm=(0.0, 0.0, 0.0),
            orientation_deg=(180.0, 0.0, 90.0),
            stage=MotionStage.APPROACH,
            metadata=meta,
        )

        # Mutate original caller dictionary
        meta["original_key"] = "mutated_val"
        meta["new_key"] = 999

        # Stored metadata must remain unchanged
        self.assertEqual(wp.metadata["original_key"], "original_val")
        self.assertNotIn("new_key", wp.metadata)

        # Attempting to mutate stored mappingproxy directly must raise TypeError
        with self.assertRaises(TypeError):
            wp.metadata["original_key"] = "hacked"  # type: ignore

    def test_joint_waypoint_contract(self):
        """Verify JointWaypoint validates exactly 6 joints and provides radiant conversion."""
        jw = JointWaypoint(
            joints_deg=(0.0, -20.0, 100.0, -80.0, -90.0, 15.0),
            stage=MotionStage.SERVICE_RETREAT,
            speed_factor=1.5,
            label="Service safe joint pose",
        )
        self.assertEqual(len(jw.joints_deg), 6)
        self.assertEqual(jw.joints_deg[0], 0.0)
        self.assertEqual(jw.motion_type, MotionType.JOINT)
        self.assertAlmostEqual(jw.joints_rad[4], -math.pi / 2.0, places=5)

        # Reject invalid joint count
        with self.assertRaises(ValueError):
            JointWaypoint(joints_deg=(0.0, 0.0, 0.0), stage=MotionStage.SERVICE_RETREAT)  # type: ignore

        # Reject Cartesian waypoint with JOINT type
        with self.assertRaises(ValueError):
            MotionWaypoint(
                position_mm=(0.0, 0.0, 0.0),
                orientation_deg=(0.0, 0.0, 0.0),
                stage=MotionStage.LAND,
                motion_type=MotionType.JOINT,
            )

    def test_motion_step_target_type_mutual_exclusion(self):
        """Verify MotionStep enforces unambiguous target types (Cartesian vs Joint)."""
        cart_wp = MotionWaypoint(
            position_mm=(0.0, 0.0, 0.0),
            orientation_deg=(180.0, 0.0, 90.0),
            stage=MotionStage.APPROACH,
        )
        joint_wp = JointWaypoint(
            joints_deg=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            stage=MotionStage.SERVICE_RETREAT,
        )

        # Valid Cartesian step
        s_cart = MotionStep(
            step_id=1,
            stage=MotionStage.APPROACH,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=cart_wp,
        )
        self.assertIsNotNone(s_cart.target)

        # Valid Joint step
        s_joint = MotionStep(
            step_id=2,
            stage=MotionStage.SERVICE_RETREAT,
            motion_type=MotionType.JOINT,
            joint_waypoint=joint_wp,
        )
        self.assertIsNotNone(s_joint.target)

        # Invalid: JOINT type with Cartesian waypoint
        with self.assertRaises(ValueError):
            MotionStep(
                step_id=3,
                stage=MotionStage.SERVICE_RETREAT,
                motion_type=MotionType.JOINT,
                waypoint=cart_wp,
            )

        # Invalid: CARTESIAN type with Joint waypoint
        with self.assertRaises(ValueError):
            MotionStep(
                step_id=4,
                stage=MotionStage.APPROACH,
                motion_type=MotionType.CARTESIAN_LINEAR,
                joint_waypoint=joint_wp,
            )

    def test_gripper_command_semantics(self):
        """Verify GripperCommand expresses OPEN, CLOSE, SAFE_IDLE without hardware pin coupling."""
        self.assertEqual(GripperCommand.OPEN.name, "OPEN")
        self.assertEqual(GripperCommand.CLOSE.name, "CLOSE")
        self.assertEqual(GripperCommand.SAFE_IDLE.name, "SAFE_IDLE")

    def test_payload_state_semantics(self):
        """Verify PayloadState covers the entire lifecycle of piece attachment."""
        states = [
            PayloadState.NONE,
            PayloadState.EXPECTED_ATTACHED,
            PayloadState.ATTACHED,
            PayloadState.EXPECTED_RELEASED,
            PayloadState.RELEASED,
            PayloadState.UNKNOWN,
        ]
        self.assertEqual(len(states), 6)

    def test_structured_motion_result_success(self):
        """Verify MotionExecutionResult factory for successful execution."""
        res = MotionExecutionResult.ok(
            last_stage=MotionStage.COMPLETE,
            payload_state=PayloadState.RELEASED,
            message="Move executed cleanly",
        )
        self.assertTrue(res.success)
        self.assertEqual(res.last_completed_stage, MotionStage.COMPLETE)
        self.assertIsNone(res.failed_stage)
        self.assertEqual(res.failure_category, MotionFailureCategory.NONE)
        self.assertEqual(res.payload_state, PayloadState.RELEASED)
        self.assertFalse(res.failed_before_grasp)
        self.assertFalse(res.failed_while_carrying)
        self.assertFalse(res.failed_after_release)

    def test_failure_taxonomy_and_recovery_classification(self):
        """Verify MotionExecutionResult helper predicates distinguish operational failure regimes."""
        # 1. Failure before grasp: collision during descent to pick
        res_before = MotionExecutionResult.fail(
            failed_stage=MotionStage.LAND,
            category=MotionFailureCategory.COLLISION_BLOCKED,
            message="Collision detected on descent",
            last_completed_stage=MotionStage.APPROACH,
            payload_state=PayloadState.NONE,
        )
        self.assertFalse(res_before.success)
        self.assertTrue(res_before.failed_before_grasp)
        self.assertFalse(res_before.failed_while_carrying)
        self.assertFalse(res_before.failed_after_release)

        # 2. Failure at grip: grasp predicate failed
        res_grip = MotionExecutionResult.fail(
            failed_stage=MotionStage.GRIP,
            category=MotionFailureCategory.PAYLOAD_NOT_CONFIRMED,
            message="Vacuum pressure not reached",
            last_completed_stage=MotionStage.LAND,
            payload_state=PayloadState.NONE,
        )
        self.assertTrue(res_grip.failed_before_grasp)
        self.assertFalse(res_grip.failed_while_carrying)

        # 3. Failure while carrying: obstacle during transit
        res_carrying = MotionExecutionResult.fail(
            failed_stage=MotionStage.TRANSIT,
            category=MotionFailureCategory.MOTION_COMMAND_FAILED,
            message="Joint torque limit exceeded during transit",
            last_completed_stage=MotionStage.LIFT,
            payload_state=PayloadState.ATTACHED,
        )
        self.assertFalse(res_carrying.failed_before_grasp)
        self.assertTrue(res_carrying.failed_while_carrying)
        self.assertFalse(res_carrying.failed_after_release)

        # 4. Failure after release: piece placed, but retreat failed
        res_after = MotionExecutionResult.fail(
            failed_stage=MotionStage.SERVICE_RETREAT,
            category=MotionFailureCategory.IK_FAILED,
            message="IK failed on retreat to service safe",
            last_completed_stage=MotionStage.POST_RELEASE_LIFT,
            payload_state=PayloadState.RELEASED,
        )
        self.assertFalse(res_after.failed_before_grasp)
        self.assertFalse(res_after.failed_while_carrying)
        self.assertTrue(res_after.failed_after_release)

    def test_semantic_task_intents(self):
        """Verify Layer 1 Semantic Task Intents operate strictly on row/col, not robot XYZ."""
        pick = BoardPickIntent(row=4.0, col=2.0, piece_id="r_soldier_1")
        self.assertEqual((pick.row, pick.col), (4.0, 2.0))
        self.assertEqual(pick.piece_id, "r_soldier_1")

        place = BoardPlaceIntent(row=5.0, col=2.0)
        self.assertEqual((place.row, place.col), (5.0, 2.0))

        move = PieceMoveIntent(src_row=6.0, src_col=4.0, dst_row=5.0, dst_col=4.0, piece_id="b_general")
        self.assertEqual((move.src_row, move.src_col), (6.0, 4.0))
        self.assertEqual((move.dst_row, move.dst_col), (5.0, 4.0))

        capture = CaptureIntent(
            src_row=9.0, src_col=1.0, dst_row=7.0, dst_col=1.0,
            bin_cell=(-1.0, -1.0), attacker_piece_id="r_cannon_1", captured_piece_id="b_horse_1"
        )
        self.assertEqual(capture.bin_cell, (-1.0, -1.0))
        self.assertEqual(capture.attacker_piece_id, "r_cannon_1")
        self.assertEqual(capture.captured_piece_id, "b_horse_1")

    def test_placement_version_tracking(self):
        """Verify MotionPlan carries placement_version and validates consistency."""
        wp = MotionWaypoint((-200.0, 0.0, 50.0), (180.0, 0.0, 90.0), MotionStage.APPROACH)
        step = MotionStep(
            step_id=1,
            stage=MotionStage.APPROACH,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=wp,
        )
        plan_v5 = MotionPlan(
            task_id="test-plan-1",
            plan_type="TEST",
            steps=(step,),
            placement_version=5,
        )
        self.assertTrue(plan_v5.is_valid_for_placement_version(5))
        self.assertFalse(plan_v5.is_valid_for_placement_version(6))

        # Version-agnostic plan (placement_version=None)
        plan_agnostic = MotionPlan(
            task_id="test-plan-2",
            plan_type="TEST",
            steps=(step,),
            placement_version=None,
        )
        self.assertTrue(plan_agnostic.is_valid_for_placement_version(5))
        self.assertTrue(plan_agnostic.is_valid_for_placement_version(99))

    def test_pick_plan_builder_stage_ordering(self):
        """Verify build_pick_plan generates canonical stage sequence: APPROACH -> LAND -> GRIP -> LIFT -> PAYLOAD_CLEAR."""
        app_pose = [-250.0, 100.0, 40.0, 180.0, 0.0, 90.0]
        pick_pose = [-250.0, 100.0, 4.7, 180.0, 0.0, 90.0]

        plan = build_pick_plan(
            approach_pose_mm_deg=app_pose,
            pick_pose_mm_deg=pick_pose,
            source_cell=(0, 0),
            placement_version=3,
        )
        self.assertEqual(plan.plan_type, "PICK")
        self.assertEqual(plan.source, (0, 0))
        self.assertEqual(plan.placement_version, 3)

        expected_stages = (
            MotionStage.APPROACH,
            MotionStage.LAND,
            MotionStage.GRIP,
            MotionStage.LIFT,
            MotionStage.PAYLOAD_CLEAR,
        )
        self.assertEqual(plan.stages(), expected_stages)

        # Verify step types
        self.assertEqual(plan.steps[0].motion_type, MotionType.CARTESIAN_LINEAR)
        self.assertEqual(plan.steps[1].motion_type, MotionType.CARTESIAN_LINEAR)
        self.assertEqual(plan.steps[2].motion_type, MotionType.GRIPPER)
        self.assertEqual(plan.steps[2].gripper_command, GripperCommand.CLOSE)
        self.assertEqual(plan.steps[3].motion_type, MotionType.CARTESIAN_LINEAR)
        self.assertEqual(plan.steps[4].motion_type, MotionType.VERIFY)

    def test_pick_plan_with_optional_preposition(self):
        """Verify pick plan with optional PREPOSITION stage."""
        prep_pose = [-300.0, 0.0, 150.0, 180.0, 0.0, 90.0]
        app_pose = [-250.0, 100.0, 40.0, 180.0, 0.0, 90.0]
        pick_pose = [-250.0, 100.0, 4.7, 180.0, 0.0, 90.0]

        plan = build_pick_plan(
            approach_pose_mm_deg=app_pose,
            pick_pose_mm_deg=pick_pose,
            include_preposition=True,
            preposition_pose_mm_deg=prep_pose,
        )
        self.assertEqual(plan.stages()[0], MotionStage.PREPOSITION)
        self.assertEqual(plan.steps[0].waypoint.pose_mm_deg, tuple(prep_pose))

    def test_place_plan_builder_stage_ordering(self):
        """Verify build_place_plan generates canonical stage sequence: PLACE_APPROACH -> PLACE_LAND -> RELEASE -> SETTLE -> POST_RELEASE_LIFT."""
        app_pose = [-220.0, -80.0, 40.0, 180.0, 0.0, 90.0]
        place_pose = [-220.0, -80.0, 4.7, 180.0, 0.0, 90.0]

        plan = build_place_plan(
            approach_pose_mm_deg=app_pose,
            place_pose_mm_deg=place_pose,
            destination_cell=(2, 3),
            settle_time_s=0.75,
        )
        self.assertEqual(plan.plan_type, "PLACE")
        self.assertEqual(plan.destination, (2, 3))

        expected_stages = (
            MotionStage.PLACE_APPROACH,
            MotionStage.PLACE_LAND,
            MotionStage.RELEASE,
            MotionStage.SETTLE,
            MotionStage.POST_RELEASE_LIFT,
        )
        self.assertEqual(plan.stages(), expected_stages)
        self.assertEqual(plan.steps[2].gripper_command, GripperCommand.OPEN)
        self.assertEqual(plan.steps[3].wait_duration_s, 0.75)

    def test_standard_move_plan_builder(self):
        """Verify build_move_plan combines Pick -> TRANSIT -> Place -> [CLEAR_BOARD -> SERVICE_RETREAT]."""
        src_app = [-300.0, 100.0, 40.0, 180.0, 0.0, 90.0]
        src_pick = [-300.0, 100.0, 4.7, 180.0, 0.0, 90.0]
        dst_app = [-200.0, -100.0, 40.0, 180.0, 0.0, 90.0]
        dst_place = [-200.0, -100.0, 4.7, 180.0, 0.0, 90.0]
        clear_pose = [-200.0, -100.0, 70.0, 180.0, 0.0, 90.0]
        retreat_pose = [-150.0, 0.0, 200.0, 180.0, 0.0, 90.0]

        plan = build_move_plan(
            src_approach_pose_mm_deg=src_app,
            src_pick_pose_mm_deg=src_pick,
            dst_approach_pose_mm_deg=dst_app,
            dst_place_pose_mm_deg=dst_place,
            src_cell=(0, 4),
            dst_cell=(9, 4),
            clear_board_pose_mm_deg=clear_pose,
            service_safe_pose_mm_deg=retreat_pose,
        )
        stages = plan.stages()

        # Check key sequence landmarks
        self.assertEqual(stages[0], MotionStage.APPROACH)
        self.assertEqual(stages[1], MotionStage.LAND)
        self.assertEqual(stages[2], MotionStage.GRIP)
        self.assertEqual(stages[3], MotionStage.LIFT)
        self.assertEqual(stages[4], MotionStage.PAYLOAD_CLEAR)
        self.assertEqual(stages[5], MotionStage.TRANSIT)
        self.assertEqual(stages[6], MotionStage.PLACE_APPROACH)
        self.assertEqual(stages[7], MotionStage.PLACE_LAND)
        self.assertEqual(stages[8], MotionStage.RELEASE)
        self.assertEqual(stages[9], MotionStage.SETTLE)
        self.assertEqual(stages[10], MotionStage.POST_RELEASE_LIFT)
        self.assertEqual(stages[11], MotionStage.CLEAR_BOARD)
        self.assertEqual(stages[12], MotionStage.SERVICE_RETREAT)

    def test_capture_plan_removes_captured_piece_first(self):
        """
        Verify build_capture_plan enforces critical invariant:
        Captured piece at destination is picked and placed in bin BEFORE attacker moves!
        """
        # Poses for captured piece (at destination)
        c_app = [-200.0, 50.0, 40.0, 180.0, 0.0, 90.0]
        c_pick = [-200.0, 50.0, 4.7, 180.0, 0.0, 90.0]
        # Poses for capture bin
        bin_app = [-100.0, 250.0, 50.0, 180.0, 0.0, 90.0]
        bin_place = [-100.0, 250.0, 15.0, 180.0, 0.0, 90.0]
        # Poses for attacker (at source)
        a_app = [-350.0, 50.0, 40.0, 180.0, 0.0, 90.0]
        a_pick = [-350.0, 50.0, 4.7, 180.0, 0.0, 90.0]

        plan = build_capture_plan(
            captured_approach_pose_mm_deg=c_app,
            captured_pick_pose_mm_deg=c_pick,
            bin_approach_pose_mm_deg=bin_app,
            bin_place_pose_mm_deg=bin_place,
            attacker_approach_pose_mm_deg=a_app,
            attacker_pick_pose_mm_deg=a_pick,
            dst_approach_pose_mm_deg=c_app,
            dst_place_pose_mm_deg=c_pick,
            src_cell=(7, 1),
            dst_cell=(9, 1),
            bin_cell=(-1, -1),
        )

        steps = plan.steps
        # Find index of first RELEASE (placing captured piece into bin)
        first_release_idx = next(i for i, s in enumerate(steps) if s.stage == MotionStage.RELEASE)
        # Find index of second GRIP (picking attacking piece)
        second_grip_idx = [i for i, s in enumerate(steps) if s.stage == MotionStage.GRIP][1]

        # The captured piece MUST be released in bin before the attacker is gripped!
        self.assertLess(
            first_release_idx,
            second_grip_idx,
            "Captured piece must be placed in bin BEFORE attacker is picked",
        )

    def test_service_retreat_plan(self):
        """Verify build_service_retreat_plan generates CLEAR_BOARD -> SERVICE_RETREAT -> SERVICE_SAFE."""
        clear_pose = [-250.0, 0.0, 80.0, 180.0, 0.0, 90.0]
        safe_pose = [-150.0, -100.0, 150.0, 180.0, 0.0, 90.0]

        plan = build_service_retreat_plan(
            service_safe_pose_mm_deg=safe_pose,
            clear_board_pose_mm_deg=clear_pose,
        )
        stages = plan.stages()
        self.assertEqual(stages, (MotionStage.CLEAR_BOARD, MotionStage.SERVICE_RETREAT, MotionStage.SERVICE_SAFE))

    def test_orientation_is_not_hardcoded(self):
        """Verify contracts allow arbitrary non-standard orientations without assuming [180, 0, 90]."""
        custom_orientation = (0.0, 180.0, 45.0)
        custom_app = [-200.0, 50.0, 40.0, *custom_orientation]
        custom_pick = [-200.0, 50.0, 5.0, *custom_orientation]

        plan = build_pick_plan(
            approach_pose_mm_deg=custom_app,
            pick_pose_mm_deg=custom_pick,
        )
        for step in plan.steps:
            if step.waypoint is not None:
                self.assertEqual(step.waypoint.orientation_deg, custom_orientation)

    def test_backward_compatibility_with_existing_motion_coordinator(self):
        """Verify existing MotionCoordinator and MotionProfile import and function unaffected."""
        profile = MotionProfile(
            pick_tcp_height_above_board_mm=4.715,
            place_tcp_height_above_board_mm=4.715,
            safe_clearance_above_board_mm=40.0,
            provenance="SIMULATION_GEOMETRIC_DEFAULT",
        )
        self.assertEqual(profile.pick_tcp_height_above_board_mm, 4.715)
        self.assertEqual(profile.safe_clearance_above_board_mm, 40.0)


if __name__ == "__main__":
    unittest.main()
