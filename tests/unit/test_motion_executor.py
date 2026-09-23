"""
Unit Tests for MotionExecutor (Phase 3B).

Tests execution lifecycle, fail-fast behavior, backend readiness enforcement,
stale placement version rejection, and zero-command safety invariant.
"""

from typing import List, Sequence
import unittest
from unittest.mock import MagicMock, call

from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.motion.contracts import CartesianWaypoint, GripperCommand, JointWaypoint, MotionType, MotionWaypoint
from src.motion.executor import MotionExecutor
from src.motion.plan import MotionPlan, MotionStep
from src.motion.result import MotionFailureCategory, PayloadState
from src.motion.stages import MotionStage


class FakeRobotBackend(RobotBackend):
    """Deterministic in-memory Fake RobotBackend for zero-hardware unit testing."""

    def __init__(self, connected: bool = True, motion_state: str = "IDLE"):
        self._connected = connected
        self._motion_state = motion_state
        self._gripper_closed = False
        self._current_joints = [0.0] * 6
        self._current_tcp = [-300.0, 0.0, 150.0, 180.0, 0.0, 90.0]
        self._last_error = None
        # Call recorders
        self.move_cartesian_calls: List[Sequence[float]] = []
        self.move_joint_calls: List[Sequence[float]] = []
        self.set_gripper_calls: List[bool] = []

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def is_connected(self) -> bool:
        return self._connected

    def get_state_snapshot(self) -> RobotStateSnapshot:
        return RobotStateSnapshot(
            robot_model="FR3",
            connected=self._connected,
            motion_state=self._motion_state,
            joints_deg=list(self._current_joints),
            flange_pose_mm_deg=list(self._current_tcp),
            tcp_pose_mm_deg=list(self._current_tcp),
            gripper_closed=self._gripper_closed,
            timestamp=1000.0,
            last_error=self._last_error,
        )

    def move_joint(self, target_joints_deg: Sequence[float], speed_factor=None) -> bool:
        self.move_joint_calls.append(list(target_joints_deg))
        self._current_joints = list(target_joints_deg)
        return True

    def move_cartesian(self, target_pose_mm_deg: Sequence[float], speed_factor=None, samples=20) -> bool:
        self.move_cartesian_calls.append(list(target_pose_mm_deg))
        self._current_tcp = list(target_pose_mm_deg)
        return True

    def set_gripper(self, closed: bool) -> bool:
        self.set_gripper_calls.append(closed)
        self._gripper_closed = closed
        return True

    def stop(self) -> bool:
        self._motion_state = "IDLE"
        return True


class MotionExecutorTests(unittest.TestCase):
    """Test suite for shared MotionExecutor."""

    def setUp(self):
        self.backend = FakeRobotBackend(connected=True, motion_state="IDLE")
        self.provider = FixedBoardPoseProvider.from_forward_shift(forward_shift_mm=15.0)
        self.sleep_mock = MagicMock()
        self.executor = MotionExecutor(
            backend=self.backend,
            board_pose_provider=self.provider,
            sleep_fn=self.sleep_mock,
        )

    def _create_sample_pick_plan(self, placement_version: int = 1) -> MotionPlan:
        app_wp = CartesianWaypoint((-250.0, 100.0, 40.0), (180.0, 0.0, 90.0), MotionStage.APPROACH)
        land_wp = CartesianWaypoint((-250.0, 100.0, 5.0), (180.0, 0.0, 90.0), MotionStage.LAND)
        lift_wp = CartesianWaypoint((-250.0, 100.0, 40.0), (180.0, 0.0, 90.0), MotionStage.LIFT)

        steps = (
            MotionStep(1, MotionStage.APPROACH, MotionType.CARTESIAN_LINEAR, waypoint=app_wp),
            MotionStep(2, MotionStage.LAND, MotionType.CARTESIAN_LINEAR, waypoint=land_wp),
            MotionStep(3, MotionStage.GRIP, MotionType.GRIPPER, gripper_command=GripperCommand.CLOSE),
            MotionStep(4, MotionStage.LIFT, MotionType.CARTESIAN_LINEAR, waypoint=lift_wp),
        )
        return MotionPlan(
            task_id="pick-test-1",
            plan_type="PICK",
            steps=steps,
            placement_version=placement_version,
        )

    def test_executor_success_clean_lifecycle(self):
        """Verify successful plan execution dispatches ordered moves, commands gripper, and updates state."""
        plan = self._create_sample_pick_plan(placement_version=1)
        res = self.executor.execute_plan(plan)

        self.assertTrue(res.success)
        self.assertEqual(res.last_completed_stage, MotionStage.LIFT)
        self.assertIsNone(res.failed_stage)
        self.assertEqual(res.failure_category, MotionFailureCategory.NONE)
        self.assertEqual(res.payload_state, PayloadState.ATTACHED)

        # Verify dispatched backend calls
        self.assertEqual(len(self.backend.move_cartesian_calls), 3)  # approach, land, lift
        self.assertEqual(len(self.backend.set_gripper_calls), 1)     # close
        self.assertEqual(self.backend.set_gripper_calls[0], True)

    def test_backend_not_ready_sends_zero_commands(self):
        """Verify unready backend aborts immediately with BACKEND_NOT_READY and zero commands sent."""
        # Case A: Disconnected
        self.backend._connected = False
        plan = self._create_sample_pick_plan()
        res = self.executor.execute_plan(plan)

        self.assertFalse(res.success)
        self.assertEqual(res.failure_category, MotionFailureCategory.BACKEND_NOT_READY)
        self.assertEqual(len(self.backend.move_cartesian_calls), 0)
        self.assertEqual(len(self.backend.set_gripper_calls), 0)

        # Case B: In ERROR state
        self.backend._connected = True
        self.backend._motion_state = "ERROR"
        res_err = self.executor.execute_plan(plan)

        self.assertFalse(res_err.success)
        self.assertEqual(res_err.failure_category, MotionFailureCategory.BACKEND_NOT_READY)
        self.assertEqual(len(self.backend.move_cartesian_calls), 0)
        self.assertEqual(len(self.backend.set_gripper_calls), 0)

    def test_stale_placement_version_rejected_with_zero_commands(self):
        """Verify plan generated against stale placement version is rejected before issuing any motion."""
        # Plan has version 99, but provider is version 1
        plan_stale = self._create_sample_pick_plan(placement_version=99)
        res = self.executor.execute_plan(plan_stale)

        self.assertFalse(res.success)
        self.assertEqual(res.failure_category, MotionFailureCategory.STALE_PLACEMENT_VERSION)
        self.assertIn("placement_version=99", res.message)
        # Zero motion commands issued!
        self.assertEqual(len(self.backend.move_cartesian_calls), 0)
        self.assertEqual(len(self.backend.set_gripper_calls), 0)

    def test_joint_waypoint_execution(self):
        """Verify JointWaypoint steps are dispatched to backend.move_joint."""
        jw = JointWaypoint(
            joints_deg=(0.0, -25.0, 95.0, -70.0, -90.0, 0.0),
            stage=MotionStage.SERVICE_RETREAT,
            speed_factor=1.2,
        )
        plan = MotionPlan(
            task_id="joint-retreat-1",
            plan_type="RETREAT",
            steps=(
                MotionStep(1, MotionStage.SERVICE_RETREAT, MotionType.JOINT, joint_waypoint=jw),
            ),
        )
        res = self.executor.execute_plan(plan)
        self.assertTrue(res.success)
        self.assertEqual(len(self.backend.move_joint_calls), 1)
        self.assertEqual(self.backend.move_joint_calls[0], [0.0, -25.0, 95.0, -70.0, -90.0, 0.0])

    def test_wait_step_calls_sleep(self):
        """Verify WAIT step executes dwell through supplied sleep function."""
        step = MotionStep(1, MotionStage.SETTLE, MotionType.WAIT, wait_duration_s=0.75)
        plan = MotionPlan(task_id="wait-1", plan_type="WAIT", steps=(step,))
        res = self.executor.execute_plan(plan)

        self.assertTrue(res.success)
        self.sleep_mock.assert_called_once_with(0.75)


if __name__ == "__main__":
    unittest.main()
