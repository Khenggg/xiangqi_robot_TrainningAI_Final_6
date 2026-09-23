"""
Unit Tests for Motion Failure Semantics and Error Recovery Context (Phase 3B).

Validates strict fail-fast stage halting, exact payload state preservation,
and diagnostic metadata for upper-level recovery decisions.
"""

from typing import List, Sequence
import unittest

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.motion.contracts import CartesianWaypoint, GripperCommand, MotionType
from src.motion.executor import MotionExecutor
from src.motion.plan import MotionPlan, MotionStep
from src.motion.result import MotionFailureCategory, PayloadState
from src.motion.stages import MotionStage


class FaultInjectingBackend(RobotBackend):
    """Fake backend capable of simulating failure at designated stages or commands."""

    def __init__(self):
        self._connected = True
        self._motion_state = "IDLE"
        self._fail_cartesian_at_index = None  # 0-indexed call count
        self._fail_gripper_close = False
        self._fail_gripper_open = False
        self._cartesian_call_count = 0
        self.move_cartesian_calls: List[Sequence[float]] = []
        self.set_gripper_calls: List[bool] = []

    def connect(self) -> bool:
        return True

    def disconnect(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return self._connected

    def get_state_snapshot(self) -> RobotStateSnapshot:
        return RobotStateSnapshot(
            robot_model="FR3",
            connected=self._connected,
            motion_state=self._motion_state,
            joints_deg=[0.0] * 6,
            flange_pose_mm_deg=[-300.0, 0.0, 150.0, 180.0, 0.0, 90.0],
            tcp_pose_mm_deg=[-300.0, 0.0, 150.0, 180.0, 0.0, 90.0],
            gripper_closed=False,
            timestamp=1000.0,
            last_error="Simulated hardware fault" if self._fail_cartesian_at_index == self._cartesian_call_count else None,
        )

    def move_joint(self, target_joints_deg: Sequence[float], speed_factor=None) -> bool:
        return True

    def move_cartesian(self, target_pose_mm_deg: Sequence[float], speed_factor=None, samples=20) -> bool:
        idx = self._cartesian_call_count
        self._cartesian_call_count += 1
        self.move_cartesian_calls.append(list(target_pose_mm_deg))

        if self._fail_cartesian_at_index == idx:
            return False
        return True

    def set_gripper(self, closed: bool) -> bool:
        self.set_gripper_calls.append(closed)
        if closed and self._fail_gripper_close:
            return False
        if not closed and self._fail_gripper_open:
            return False
        return True

    def stop(self) -> bool:
        return True


class MotionFailureSemanticsTests(unittest.TestCase):
    """Test suite for failure semantics, stage halting, and payload tracking."""

    def setUp(self):
        self.backend = FaultInjectingBackend()
        self.executor = MotionExecutor(backend=self.backend)

    def _build_test_move_plan(self) -> MotionPlan:
        app_src = CartesianWaypoint((-300.0, 50.0, 40.0), (180.0, 0.0, 90.0), MotionStage.APPROACH)
        land_src = CartesianWaypoint((-300.0, 50.0, 5.0), (180.0, 0.0, 90.0), MotionStage.LAND)
        lift_src = CartesianWaypoint((-300.0, 50.0, 40.0), (180.0, 0.0, 90.0), MotionStage.LIFT)
        transit_dst = CartesianWaypoint((-200.0, -50.0, 40.0), (180.0, 0.0, 90.0), MotionStage.TRANSIT)
        land_dst = CartesianWaypoint((-200.0, -50.0, 5.0), (180.0, 0.0, 90.0), MotionStage.PLACE_LAND)
        lift_dst = CartesianWaypoint((-200.0, -50.0, 40.0), (180.0, 0.0, 90.0), MotionStage.POST_RELEASE_LIFT)

        steps = (
            MotionStep(1, MotionStage.APPROACH, MotionType.CARTESIAN_LINEAR, waypoint=app_src),
            MotionStep(2, MotionStage.LAND, MotionType.CARTESIAN_LINEAR, waypoint=land_src),
            MotionStep(3, MotionStage.GRIP, MotionType.GRIPPER, gripper_command=GripperCommand.CLOSE),
            MotionStep(4, MotionStage.LIFT, MotionType.CARTESIAN_LINEAR, waypoint=lift_src),
            MotionStep(5, MotionStage.PAYLOAD_CLEAR, MotionType.VERIFY, expected_payload_state=PayloadState.ATTACHED),
            MotionStep(6, MotionStage.TRANSIT, MotionType.CARTESIAN_LINEAR, waypoint=transit_dst),
            MotionStep(7, MotionStage.PLACE_LAND, MotionType.CARTESIAN_LINEAR, waypoint=land_dst),
            MotionStep(8, MotionStage.RELEASE, MotionType.GRIPPER, gripper_command=GripperCommand.OPEN),
            MotionStep(9, MotionStage.SETTLE, MotionType.WAIT, wait_duration_s=0.1, expected_payload_state=PayloadState.RELEASED),
            MotionStep(10, MotionStage.POST_RELEASE_LIFT, MotionType.CARTESIAN_LINEAR, waypoint=lift_dst),
        )
        return MotionPlan(task_id="move-fault-test", plan_type="MOVE", steps=steps)

    def test_land_failure_halts_immediately_before_grip(self):
        """
        Verify failure at LAND:
        - Execution stops immediately.
        - ZERO gripper calls issued.
        - failed_stage == LAND, last_completed == APPROACH.
        - failed_before_grasp == True, payload_state == NONE.
        """
        self.backend._fail_cartesian_at_index = 1  # 0=APPROACH, 1=LAND
        plan = self._build_test_move_plan()

        res = self.executor.execute_plan(plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failed_stage, MotionStage.LAND)
        self.assertEqual(res.last_completed_stage, MotionStage.APPROACH)
        self.assertEqual(res.failure_category, MotionFailureCategory.MOTION_COMMAND_FAILED)
        self.assertTrue(res.failed_before_grasp)
        self.assertFalse(res.failed_while_carrying)
        self.assertEqual(res.payload_state, PayloadState.NONE)

        # Invariant: NO gripper call ever reached!
        self.assertEqual(len(self.backend.set_gripper_calls), 0)

    def test_grip_failure_halts_before_lift_or_transit(self):
        """
        Verify failure at GRIP:
        - Execution stops.
        - No subsequent LIFT or TRANSIT motion calls issued.
        - failed_stage == GRIP, category == GRIPPER_FAILED.
        - failed_before_grasp == True.
        """
        self.backend._fail_gripper_close = True
        plan = self._build_test_move_plan()

        res = self.executor.execute_plan(plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failed_stage, MotionStage.GRIP)
        self.assertEqual(res.last_completed_stage, MotionStage.LAND)
        self.assertEqual(res.failure_category, MotionFailureCategory.GRIPPER_FAILED)
        self.assertTrue(res.failed_before_grasp)

        # Only 2 Cartesian moves (APPROACH, LAND) were executed; LIFT was NOT called!
        self.assertEqual(len(self.backend.move_cartesian_calls), 2)

    def test_transit_failure_tracks_payload_attached(self):
        """
        Verify failure during TRANSIT:
        - Piece was already grasped at step 3.
        - Failure occurs during transit (call index 3: 0=app, 1=land, 2=lift, 3=transit).
        - failed_while_carrying == True, payload_state reflects EXPECTED_ATTACHED or ATTACHED.
        """
        self.backend._fail_cartesian_at_index = 3  # TRANSIT call
        plan = self._build_test_move_plan()

        res = self.executor.execute_plan(plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failed_stage, MotionStage.TRANSIT)
        self.assertEqual(res.last_completed_stage, MotionStage.PAYLOAD_CLEAR)
        self.assertTrue(res.failed_while_carrying)
        self.assertFalse(res.failed_before_grasp)
        self.assertFalse(res.failed_after_release)
        # Without external verifier, payload state remains EXPECTED_ATTACHED
        self.assertEqual(res.payload_state, PayloadState.EXPECTED_ATTACHED)

        # With external verifier, payload state advances to ATTACHED
        executor_with_ver = MotionExecutor(backend=self.backend, payload_verifier=lambda st: True)
        self.backend._cartesian_call_count = 0
        res_ver = executor_with_ver.execute_plan(plan)
        self.assertFalse(res_ver.success)
        self.assertTrue(res_ver.failed_while_carrying)
        self.assertEqual(res_ver.payload_state, PayloadState.ATTACHED)

    def test_release_failure_does_not_claim_released(self):
        """
        Verify failure during RELEASE:
        - Gripper open fails.
        - Executor does not falsely claim payload was released.
        - failed_stage == RELEASE, category == GRIPPER_FAILED.
        """
        self.backend._fail_gripper_open = True
        plan = self._build_test_move_plan()

        res = self.executor.execute_plan(plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failed_stage, MotionStage.RELEASE)
        self.assertEqual(res.failure_category, MotionFailureCategory.GRIPPER_FAILED)
        self.assertNotEqual(res.payload_state, PayloadState.RELEASED)

    def test_post_release_lift_failure_marks_failed_after_release(self):
        """
        Verify failure during POST_RELEASE_LIFT:
        - Piece was already deposited onto destination.
        - Lift away from destination fails (call index 5: 0=app, 1=land, 2=lift, 3=transit, 4=place_land, 5=post_release_lift).
        - failed_after_release == True, payload_state == RELEASED.
        """
        self.backend._fail_cartesian_at_index = 5  # POST_RELEASE_LIFT
        plan = self._build_test_move_plan()

        res = self.executor.execute_plan(plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failed_stage, MotionStage.POST_RELEASE_LIFT)
        self.assertTrue(res.failed_after_release)
        self.assertIn(res.payload_state, (PayloadState.RELEASED, PayloadState.EXPECTED_RELEASED))


if __name__ == "__main__":
    unittest.main()
