"""
Unit Tests for MotionResolver (Phase 3B).

Verifies translation of Semantic Task Intents into ResolvedMotionPlans
using BoardPoseProvider authority, correct stage sequencing, and
placement_version propagation.
"""

import unittest
from unittest.mock import MagicMock

from src.domain.board_pose import BoardPlacementState
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.motion.coordinator import MotionProfile
from src.motion.plan import (
    BoardPickIntent,
    BoardPlaceIntent,
    CaptureIntent,
    PieceMoveIntent,
)
from src.motion.resolver import MotionResolver
from src.motion.stages import MotionStage


class MotionResolverTests(unittest.TestCase):
    """Test suite for MotionResolver compilation of semantic intents."""

    def setUp(self):
        self.provider = FixedBoardPoseProvider.from_forward_shift(forward_shift_mm=15.0)
        self.profile = MotionProfile(
            pick_tcp_height_above_board_mm=5.0,
            place_tcp_height_above_board_mm=5.0,
            safe_clearance_above_board_mm=45.0,
        )
        self.resolver = MotionResolver(
            board_pose_provider=self.provider,
            motion_profile=self.profile,
            tool_rotation_deg=(180.0, 0.0, 90.0),
            default_speed_factor=1.0,
        )

    def test_resolve_piece_move_intent_ordered_stages(self):
        """Verify normal PieceMoveIntent resolves to full canonical 3-stage pick-transit-place sequence."""
        intent = PieceMoveIntent(src_row=6.0, src_col=4.0, dst_row=5.0, dst_col=4.0, piece_id="r_soldier_3")
        plan = self.resolver.resolve_move(intent)

        self.assertEqual(plan.plan_type, "MOVE")
        self.assertEqual(plan.source, (6.0, 4.0))
        self.assertEqual(plan.destination, (5.0, 4.0))
        self.assertEqual(plan.placement_version, self.provider.get_board_placement_state().placement_version)

        stages = plan.stages()
        expected = (
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
        )
        self.assertEqual(stages, expected)

    def test_resolve_uses_board_pose_authority(self):
        """Verify robot waypoints are computed via BoardPlacementState, reflecting shifts."""
        intent = BoardPickIntent(row=0.0, col=0.0)

        # Baseline plan at d=15mm
        plan_15 = self.resolver.resolve_pick(intent)
        wp_app_15 = plan_15.steps[0].waypoint
        self.assertIsNotNone(wp_app_15)

        # Shifted provider at d=30mm
        provider_30 = FixedBoardPoseProvider.from_forward_shift(forward_shift_mm=30.0)
        resolver_30 = MotionResolver(board_pose_provider=provider_30, motion_profile=self.profile)
        plan_30 = resolver_30.resolve_pick(intent)
        wp_app_30 = plan_30.steps[0].waypoint
        self.assertIsNotNone(wp_app_30)

        # Board forward shift is in -X for yaw=90. Waypoints MUST reflect this difference!
        self.assertNotEqual(wp_app_15.position_mm, wp_app_30.position_mm)

    def test_resolve_capture_intent_removes_captured_piece_first(self):
        """
        Verify CaptureIntent choreography:
        Captured piece at dst is picked and placed in bin BEFORE attacker at src is moved.
        """
        intent = CaptureIntent(
            src_row=7.0,
            src_col=1.0,
            dst_row=9.0,
            dst_col=1.0,
            bin_cell=(-1.0, -1.0),
            attacker_piece_id="r_cannon_1",
            captured_piece_id="b_horse_1",
        )
        plan = self.resolver.resolve_capture(intent)

        self.assertEqual(plan.plan_type, "CAPTURE")
        stages = plan.stages()

        # There are two GRIP stages and two RELEASE stages
        grip_indices = [i for i, st in enumerate(stages) if st == MotionStage.GRIP]
        release_indices = [i for i, st in enumerate(stages) if st == MotionStage.RELEASE]

        self.assertEqual(len(grip_indices), 2)
        self.assertEqual(len(release_indices), 2)

        # First GRIP is captured piece at dst
        # First RELEASE is captured piece into bin
        # Second GRIP is attacker at src
        # Second RELEASE is attacker at dst
        self.assertLess(
            release_indices[0],
            grip_indices[1],
            "Captured piece must be released into bin before attacker is gripped",
        )

    def test_placement_version_propagation(self):
        """Verify the resolved plan faithfully stamps placement_version from current provider."""
        state = self.provider.get_board_placement_state()
        state.placement_version = 42

        intent = BoardPickIntent(row=4.0, col=4.0)
        plan = self.resolver.resolve_pick(intent)
        self.assertEqual(plan.placement_version, 42)

    def test_generic_resolve_dispatch(self):
        """Verify resolver.resolve() automatically routes all intent subclasses."""
        move = PieceMoveIntent(src_row=0.0, src_col=0.0, dst_row=1.0, dst_col=0.0)
        capture = CaptureIntent(src_row=0.0, src_col=0.0, dst_row=1.0, dst_col=0.0)
        pick = BoardPickIntent(row=2.0, col=2.0)
        place = BoardPlaceIntent(row=3.0, col=3.0)

        self.assertEqual(self.resolver.resolve(move).plan_type, "MOVE")
        self.assertEqual(self.resolver.resolve(capture).plan_type, "CAPTURE")
        self.assertEqual(self.resolver.resolve(pick).plan_type, "PICK")
        self.assertEqual(self.resolver.resolve(place).plan_type, "PLACE")


if __name__ == "__main__":
    unittest.main()
