"""
Motion layer package for high-level robot choreography and movement coordination.

Architecture:
    Intent (Semantic row, col)
        ↓
    MotionPlan (Waypoint sequence, placement version, payload state)
        ↓
    MotionStage[] (Standardized lifecycle vocabulary)
        ↓
    MotionExecutor (Phase 3B integration)
        ↓
    RobotBackend (VirtualFR3Backend vs PhysicalFR3Backend)
"""

from src.motion.coordinator import MotionCoordinator, MotionProfile
from src.motion.stages import MotionStage
from src.motion.contracts import (
    MotionType,
    GripperCommand,
    MotionWaypoint,
)
from src.motion.result import (
    PayloadState,
    MotionFailureCategory,
    MotionExecutionResult,
)
from src.motion.plan import (
    MotionStep,
    MotionPlan,
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
    # Result & Payload Semantics
    "PayloadState",
    "MotionFailureCategory",
    "MotionExecutionResult",
    # Plan & Task Intents
    "MotionStep",
    "MotionPlan",
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
]
