"""
Motion Execution Results, Failure Taxonomy, and Payload Semantics.

Defines structured diagnostics and payload tracking to enable robust
error recovery in both physical and virtual robot execution pipelines.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional

from src.motion.stages import MotionStage


class PayloadState(Enum):
    """
    Semantic belief state regarding piece attachment to the end-effector.
    
    Distinguishes operational phases to inform recovery strategies:
        - Before grasp: piece remains undisturbed on source square.
        - While carrying: piece is in flight; aborting requires safe retreat or park.
        - After release: piece is placed; game state has advanced.
    """
    NONE = auto()
    """No piece is held or expected to be held."""

    EXPECTED_ATTACHED = auto()
    """Gripper close command sent; waiting for confirmation/lift."""

    ATTACHED = auto()
    """Piece is confirmed attached to gripper (payload in transit)."""

    EXPECTED_RELEASED = auto()
    """Gripper open command sent; waiting for release settle confirmation."""

    RELEASED = auto()
    """Piece has been released and confirmed resting on target surface."""

    UNKNOWN = auto()
    """Payload state cannot be determined with certainty."""


class MotionFailureCategory(Enum):
    """
    Standard taxonomy of motion execution failures.
    
    Enables upper-level task managers to differentiate recoverable mechanical
    retries from fatal safety or configuration errors.
    """
    NONE = auto()
    """No failure; operation succeeded."""

    BACKEND_NOT_READY = auto()
    """Robot controller or simulation backend is uninitialized, disconnected, or busy."""

    TARGET_INVALID = auto()
    """Target coordinates, cell indices, or pose parameters are out of bounds."""

    PLANNING_FAILED = auto()
    """Trajectory interpolation, corridor generation, or choreography planning failed."""

    IK_FAILED = auto()
    """Inverse kinematics failed to find a valid joint solution for a waypoint."""

    COLLISION_BLOCKED = auto()
    """Path or destination obstructed by self-collision, board collision, or obstacles."""

    MOTION_COMMAND_FAILED = auto()
    """Low-level controller or simulation step rejected or failed the motion execution."""

    GRIPPER_FAILED = auto()
    """Gripper actuation (open/close) failed or pneumatic pressure was lost."""

    PAYLOAD_NOT_CONFIRMED = auto()
    """Grasp verification predicate failed (expected piece was not acquired)."""

    RELEASE_FAILED = auto()
    """Release verification predicate failed (piece remained stuck to gripper)."""

    STALE_PLACEMENT_VERSION = auto()
    """Plan was constructed against an older BoardPlacement version and must be replanned."""

    RECOVERY_FAILED = auto()
    """Automated recovery procedure failed to return the robot to a safe state."""

    ABORTED = auto()
    """Operation was explicitly aborted by user, emergency stop, or safety guard."""


@dataclass
class MotionExecutionResult:
    """
    Structured outcome of a motion sequence or stage execution.
    
    Replaces binary True/False returns with actionable context for error recovery.
    """
    success: bool
    last_completed_stage: Optional[MotionStage] = None
    failed_stage: Optional[MotionStage] = None
    failure_category: MotionFailureCategory = MotionFailureCategory.NONE
    recoverable: bool = True
    payload_state: PayloadState = PayloadState.UNKNOWN
    error_code: Optional[str] = None
    backend_code: Optional[int] = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        last_stage: MotionStage = MotionStage.COMPLETE,
        payload_state: PayloadState = PayloadState.NONE,
        message: str = "Execution succeeded",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "MotionExecutionResult":
        """Convenience factory for successful execution."""
        return cls(
            success=True,
            last_completed_stage=last_stage,
            failed_stage=None,
            failure_category=MotionFailureCategory.NONE,
            recoverable=True,
            payload_state=payload_state,
            message=message,
            metadata=metadata or {},
        )

    @classmethod
    def fail(
        cls,
        failed_stage: MotionStage,
        category: MotionFailureCategory,
        message: str,
        last_completed_stage: Optional[MotionStage] = None,
        payload_state: PayloadState = PayloadState.UNKNOWN,
        recoverable: bool = True,
        error_code: Optional[str] = None,
        backend_code: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "MotionExecutionResult":
        """Convenience factory for failed execution."""
        return cls(
            success=False,
            last_completed_stage=last_completed_stage,
            failed_stage=failed_stage,
            failure_category=category,
            recoverable=recoverable,
            payload_state=payload_state,
            error_code=error_code,
            backend_code=backend_code,
            message=message,
            metadata=metadata or {},
        )

    @property
    def failed_before_grasp(self) -> bool:
        """
        True if the failure occurred before the piece was seized.
        
        Implies the source piece remains untouched on its starting board cell.
        """
        if self.success:
            return False
        
        # If payload state is explicitly NONE or failure was in pre-grasp stages
        pre_grasp_stages = {
            MotionStage.PREPOSITION,
            MotionStage.APPROACH,
            MotionStage.LAND,
        }
        if self.failed_stage in pre_grasp_stages:
            return True
        if self.failed_stage == MotionStage.GRIP and self.payload_state in (
            PayloadState.NONE,
            PayloadState.UNKNOWN,
        ):
            return True
        return False

    @property
    def failed_while_carrying(self) -> bool:
        """
        True if the failure occurred while carrying the piece in flight.
        
        Implies the robot arm may still hold the piece; requires safe park or recovery.
        """
        if self.success:
            return False
        if self.payload_state in (PayloadState.ATTACHED, PayloadState.EXPECTED_RELEASED):
            return True
        carrying_stages = {
            MotionStage.LIFT,
            MotionStage.PAYLOAD_CLEAR,
            MotionStage.TRANSIT,
            MotionStage.PLACE_APPROACH,
            MotionStage.PLACE_LAND,
        }
        return self.failed_stage in carrying_stages and self.payload_state != PayloadState.NONE

    @property
    def failed_after_release(self) -> bool:
        """
        True if the piece was successfully released onto the destination before failure.
        
        Implies the board state modification has already taken effect physically.
        """
        if self.success:
            return False
        if self.payload_state == PayloadState.RELEASED:
            return True
        post_release_stages = {
            MotionStage.SETTLE,
            MotionStage.POST_RELEASE_LIFT,
            MotionStage.CLEAR_BOARD,
            MotionStage.SERVICE_RETREAT,
            MotionStage.SERVICE_SAFE,
        }
        return self.failed_stage in post_release_stages
