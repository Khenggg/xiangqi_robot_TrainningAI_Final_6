"""
Motion layer package for high-level robot choreography and movement coordination.

Architecture:
    Intent (Semantic row, col)
        ↓
    MotionResolver (BoardPose transformation, MotionProfile)
        ↓
    ResolvedMotionPlan (Waypoint sequence, placement version, payload state)
        ↓
    MotionStage[] (Standardized lifecycle vocabulary)
        ↓
    MotionExecutor (Dispatch & error recovery)
        ↓
    RobotBackend (VirtualFR3Backend vs PhysicalFR3Backend)
"""

from src.motion.coordinator import MotionCoordinator, MotionProfile
from src.motion.stages import MotionStage
from src.motion.contracts import (
    MotionType,
    GripperCommand,
    MotionWaypoint,
    CartesianWaypoint,
    JointWaypoint,
)
from src.motion.result import (
    PayloadState,
    MotionFailureCategory,
    MotionExecutionResult,
)
from src.motion.plan import (
    MotionStep,
    MotionPlan,
    ResolvedMotionPlan,
    BoardPickIntent,
    BoardPlaceIntent,
    PieceMoveIntent,
    CaptureIntent,
)
from src.motion.builder import (
    build_pick_plan,
    build_place_plan,
    build_move_plan,
    build_capture_plan,
    build_service_retreat_plan,
)
from src.motion.resolver import MotionResolver
from src.motion.executor import MotionExecutor

__all__ = [
    # Legacy / Existing Coordination (Unchanged)
    "MotionCoordinator",
    "MotionProfile",
    # Stage & Lifecycle Vocabulary
    "MotionStage",
    # Core Contracts & Waypoints
    "MotionType",
    "GripperCommand",
    "MotionWaypoint",
    "CartesianWaypoint",
    "JointWaypoint",
    # Result & Payload Semantics
    "PayloadState",
    "MotionFailureCategory",
    "MotionExecutionResult",
    # Plan & Task Intents
    "MotionStep",
    "MotionPlan",
    "ResolvedMotionPlan",
    "BoardPickIntent",
    "BoardPlaceIntent",
    "PieceMoveIntent",
    "CaptureIntent",
    # Deterministic Plan Builders
    "build_pick_plan",
    "build_place_plan",
    "build_move_plan",
    "build_capture_plan",
    "build_service_retreat_plan",
    # Shared Resolver & Executor (Phase 3B)
    "MotionResolver",
    "MotionExecutor",
]
