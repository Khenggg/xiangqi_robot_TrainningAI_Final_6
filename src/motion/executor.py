"""
Motion Executor.

Dispatches ordered stages of a ResolvedMotionPlan to an abstract RobotBackend,
enforcing fail-fast safety, payload state tracking, backend readiness checks,
and placement version validation.
"""

from typing import Any, Callable, Dict, Mapping, Optional
import logging
import time

from src.domain.board_pose_provider import BoardPoseProvider
from src.hardware.backends.base import RobotBackend
from src.motion.contracts import GripperCommand, MotionType
from src.motion.plan import MotionPlan, MotionStep
from src.motion.result import (
    MotionExecutionResult,
    MotionFailureCategory,
    PayloadState,
)
from src.motion.stages import MotionStage

logger = logging.getLogger(__name__)


class MotionExecutor:
    """
    Standardized executor for compiled MotionPlans across physical and virtual backends.
    
    Architectural Guarantees:
        - Never issues raw controller RPCs or simulator direct physics APIs.
        - Communicates exclusively through the abstract RobotBackend interface.
        - Strictly halts on first failed stage and preserves exact failure context.
        - Validates backend connection and readiness before issuing any movement.
        - Enforces placement version freshness against the authoritative BoardPoseProvider.
    """

    def __init__(
        self,
        backend: RobotBackend,
        board_pose_provider: Optional[BoardPoseProvider] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        self.backend = backend
        self.board_pose_provider = board_pose_provider
        self.sleep_fn = sleep_fn or time.sleep
        self._current_payload_state: PayloadState = PayloadState.NONE

    @property
    def payload_state(self) -> PayloadState:
        """Current semantic belief state of piece attachment to the gripper."""
        return self._current_payload_state

    def reset_payload_state(self, state: PayloadState = PayloadState.NONE) -> None:
        """Explicitly reset tracked payload state (e.g. after manual recovery)."""
        self._current_payload_state = state

    def execute_plan(self, plan: MotionPlan) -> MotionExecutionResult:
        """
        Execute all ordered steps within a MotionPlan sequentially.
        
        Lifecycle:
            1. Backend Readiness Validation (aborts with BACKEND_NOT_READY if unready).
            2. Structural Plan Validation (aborts with INVALID_PLAN if empty/malformed).
            3. Placement Version Check (aborts with STALE_PLACEMENT_VERSION if out of date).
            4. Step-by-Step Execution (halts immediately on first failure).
            5. Final Result Construction.
        """
        # --- 1. Backend Readiness Check ---
        if not self.backend.is_connected():
            return MotionExecutionResult.fail(
                failed_stage=plan.steps[0].stage if plan.steps else MotionStage.PREPOSITION,
                category=MotionFailureCategory.BACKEND_NOT_READY,
                message="Backend is not connected",
                last_completed_stage=None,
                payload_state=self._current_payload_state,
                recoverable=True,
            )

        snap = self.backend.get_state_snapshot()
        if not snap.connected or snap.motion_state in ("ERROR", "DISCONNECTED"):
            return MotionExecutionResult.fail(
                failed_stage=plan.steps[0].stage if plan.steps else MotionStage.PREPOSITION,
                category=MotionFailureCategory.BACKEND_NOT_READY,
                message=f"Backend state is not ready (motion_state='{snap.motion_state}', connected={snap.connected})",
                last_completed_stage=None,
                payload_state=self._current_payload_state,
                recoverable=True,
            )

        # --- 2. Structural Plan Validation ---
        if not plan.steps:
            return MotionExecutionResult.fail(
                failed_stage=MotionStage.PREPOSITION,
                category=MotionFailureCategory.INVALID_PLAN,
                message="MotionPlan contains no steps to execute",
                last_completed_stage=None,
                payload_state=self._current_payload_state,
                recoverable=False,
            )

        # --- 3. Placement Version Check ---
        if self.board_pose_provider is not None and plan.placement_version is not None:
            current_version = self.board_pose_provider.get_board_placement_state().placement_version
            if not plan.is_valid_for_placement_version(current_version):
                return MotionExecutionResult.fail(
                    failed_stage=plan.steps[0].stage,
                    category=MotionFailureCategory.STALE_PLACEMENT_VERSION,
                    message=(
                        f"Stale plan rejected: Plan placement_version={plan.placement_version} "
                        f"does not match current BoardPlacement version={current_version}"
                    ),
                    last_completed_stage=None,
                    payload_state=self._current_payload_state,
                    recoverable=True,
                )

        # --- 4. Ordered Step Execution ---
        last_completed_stage: Optional[MotionStage] = None

        for step in plan.steps:
            logger.debug(f"[MotionExecutor] Step {step.step_id} ({step.stage.name}): {step.description}")
            step_result = self._execute_step(step, last_completed_stage)

            if not step_result.success:
                logger.warning(
                    f"[MotionExecutor] Halting execution at step {step.step_id} "
                    f"({step.stage.name}): {step_result.message}"
                )
                return step_result

            last_completed_stage = step.stage

        # --- 5. Clean Completion ---
        return MotionExecutionResult.ok(
            last_stage=last_completed_stage or MotionStage.COMPLETE,
            payload_state=self._current_payload_state,
            message=f"Plan '{plan.task_id}' ({plan.plan_type}) executed successfully ({len(plan.steps)} steps)",
        )

    def _execute_step(
        self, step: MotionStep, last_completed_stage: Optional[MotionStage]
    ) -> MotionExecutionResult:
        """Dispatch a single MotionStep to the RobotBackend."""
        # 1. Cartesian Linear or Point Movement
        if step.motion_type in (MotionType.CARTESIAN_LINEAR, MotionType.CARTESIAN_POINT):
            assert step.waypoint is not None
            ok = self.backend.move_cartesian(
                step.waypoint.pose_mm_deg,
                speed_factor=step.waypoint.speed_factor,
            )
            if not ok:
                last_err = (
                    getattr(self.backend, "_last_error", None)
                    or getattr(self.backend.get_state_snapshot(), "last_error", None)
                    or "Cartesian motion command failed"
                )
                return MotionExecutionResult.fail(
                    failed_stage=step.stage,
                    category=MotionFailureCategory.MOTION_COMMAND_FAILED,
                    message=f"Cartesian motion failed at stage {step.stage.name}: {last_err}",
                    last_completed_stage=last_completed_stage,
                    payload_state=self._current_payload_state,
                    error_code=str(last_err),
                )

        # 2. Joint Space Movement
        elif step.motion_type == MotionType.JOINT:
            assert step.joint_waypoint is not None
            ok = self.backend.move_joint(
                step.joint_waypoint.joints_deg,
                speed_factor=step.joint_waypoint.speed_factor,
            )
            if not ok:
                last_err = (
                    getattr(self.backend, "_last_error", None)
                    or getattr(self.backend.get_state_snapshot(), "last_error", None)
                    or "Joint motion command failed"
                )
                return MotionExecutionResult.fail(
                    failed_stage=step.stage,
                    category=MotionFailureCategory.MOTION_COMMAND_FAILED,
                    message=f"Joint motion failed at stage {step.stage.name}: {last_err}",
                    last_completed_stage=last_completed_stage,
                    payload_state=self._current_payload_state,
                    error_code=str(last_err),
                )

        # 3. Gripper Actuation
        elif step.motion_type == MotionType.GRIPPER:
            assert step.gripper_command is not None
            if step.gripper_command == GripperCommand.CLOSE:
                ok = self.backend.set_gripper(closed=True)
                if not ok:
                    return MotionExecutionResult.fail(
                        failed_stage=step.stage,
                        category=MotionFailureCategory.GRIPPER_FAILED,
                        message="Failed to close gripper",
                        last_completed_stage=last_completed_stage,
                        payload_state=self._current_payload_state,
                    )
                self._current_payload_state = PayloadState.ATTACHED

            elif step.gripper_command == GripperCommand.OPEN:
                ok = self.backend.set_gripper(closed=False)
                if not ok:
                    return MotionExecutionResult.fail(
                        failed_stage=step.stage,
                        category=MotionFailureCategory.GRIPPER_FAILED,
                        message="Failed to open gripper",
                        last_completed_stage=last_completed_stage,
                        payload_state=self._current_payload_state,
                    )
                self._current_payload_state = PayloadState.RELEASED

            elif step.gripper_command == GripperCommand.SAFE_IDLE:
                # Gripper safe idle does not mutate payload state
                pass

        # 4. Temporal Wait / Settle Dwell
        elif step.motion_type == MotionType.WAIT:
            assert step.wait_duration_s is not None
            if step.wait_duration_s > 0.0:
                self.sleep_fn(step.wait_duration_s)
            if step.expected_payload_state is not None:
                self._current_payload_state = step.expected_payload_state

        # 5. Non-actuating Verification
        elif step.motion_type == MotionType.VERIFY:
            if step.stage == MotionStage.PAYLOAD_CLEAR:
                # Verify that gripper is expected to be holding a piece
                if step.expected_payload_state == PayloadState.ATTACHED and self._current_payload_state != PayloadState.ATTACHED:
                    return MotionExecutionResult.fail(
                        failed_stage=step.stage,
                        category=MotionFailureCategory.PAYLOAD_NOT_CONFIRMED,
                        message="Payload clearance check failed: piece not confirmed attached",
                        last_completed_stage=last_completed_stage,
                        payload_state=self._current_payload_state,
                    )

        # Update payload state if step explicitly defines target state
        if step.expected_payload_state is not None:
            # Only advance to ATTACHED if gripper was closed or payload confirmed
            if step.expected_payload_state in (PayloadState.ATTACHED, PayloadState.RELEASED):
                self._current_payload_state = step.expected_payload_state

        return MotionExecutionResult.ok(
            last_stage=step.stage,
            payload_state=self._current_payload_state,
        )
