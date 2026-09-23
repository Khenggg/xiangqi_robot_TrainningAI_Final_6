"""
Motion Stage vocabulary for Xiangqi Robot motion planning and execution.

Provides backend-neutral lifecycle and trajectory stage identifiers
normalizing simulation runtime and physical coordinator semantics.
"""

from enum import Enum, auto


class MotionStage(Enum):
    """
    Standard lifecycle stages for Xiangqi Robot pick-and-place motions.
    
    Architecture Flow:
        Intent -> MotionPlan -> MotionStage[] -> MotionExecutor -> RobotBackend
        
    These stages are purely semantic and backend-neutral. Neither PyBullet
    joint angles nor FAIRINO RPC methods are coupled to these definitions.
    """

    # --- Pre-Trajectory & Setup ---
    PREPOSITION = auto()
    """Arm is repositioning to a preparation pose or initial clearance area."""

    # --- Pick Choreography ---
    APPROACH = auto()
    """Motion to a safe clearance altitude directly aligned over the target cell."""

    LAND = auto()
    """Controlled vertical descent from approach altitude down to grasp surface."""

    GRIP = auto()
    """Gripper closure to grasp piece payload."""

    LIFT = auto()
    """Vertical ascent back to safe transit altitude while carrying payload."""

    PAYLOAD_CLEAR = auto()
    """Verification that payload is securely held and clear of board obstacles."""

    # --- Transit Choreography ---
    TRANSIT = auto()
    """Horizontal or corridor transit across safe altitude plane between cells."""

    # --- Place Choreography ---
    PLACE_APPROACH = auto()
    """Alignment at destination approach pose prior to descent."""

    PLACE_LAND = auto()
    """Controlled vertical descent from transit altitude down to release surface."""

    RELEASE = auto()
    """Gripper opening to deposit piece payload onto board or capture bin."""

    SETTLE = auto()
    """Post-release dwell allowing piece physics / mechanical settling."""

    POST_RELEASE_LIFT = auto()
    """Vertical lift from placement surface back to safe clearance altitude."""

    # --- Retreat & Safe Parking ---
    CLEAR_BOARD = auto()
    """Elevation to full board-clearance altitude above all pieces."""

    SERVICE_RETREAT = auto()
    """Retreat motion toward designated safe service / resting configuration."""

    SERVICE_SAFE = auto()
    """Known collision-free holding pose for recovery, intervention, or idle."""

    # --- Completion & Exceptional Stages ---
    COMPLETE = auto()
    """Motion plan execution concluded successfully."""

    RECOVERY = auto()
    """Recovery or corrective motion following an execution fault."""
