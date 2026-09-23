"""
Deterministic Motion Plan Builders.

Constructs standardized multi-stage MotionPlans for pick, place, normal move,
and capture choreographies without triggering hardware or simulation actuation.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import uuid

from src.motion.contracts import GripperCommand, MotionType, MotionWaypoint
from src.motion.plan import MotionPlan, MotionStep
from src.motion.result import PayloadState
from src.motion.stages import MotionStage


def _generate_task_id(prefix: str) -> str:
    """Generate a unique short task ID."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _to_waypoint(
    pose_6d: Sequence[float],
    stage: MotionStage,
    label: str,
    speed_factor: float = 1.0,
    motion_type: MotionType = MotionType.CARTESIAN_LINEAR,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MotionWaypoint:
    """Helper to convert a 6-element pose into an immutable MotionWaypoint."""
    return MotionWaypoint.from_pose_sequence(
        pose_6d=pose_6d,
        stage=stage,
        motion_type=motion_type,
        speed_factor=speed_factor,
        label=label,
        metadata=metadata,
    )


def build_pick_plan(
    approach_pose_mm_deg: Sequence[float],
    pick_pose_mm_deg: Sequence[float],
    source_cell: Optional[Tuple[float, float]] = None,
    speed_factor: float = 1.0,
    placement_version: Optional[int] = None,
    task_id: Optional[str] = None,
    include_preposition: bool = False,
    preposition_pose_mm_deg: Optional[Sequence[float]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MotionPlan:
    """
    Construct a deterministic pick motion plan:
    1. [Optional] PREPOSITION: Move to preparation/staging pose
    2. APPROACH: Move to safe clearance directly above source piece
    3. LAND: Descend vertically to grasp height
    4. GRIP: Close gripper fingers
    5. LIFT: Ascend vertically back to safe clearance altitude
    6. PAYLOAD_CLEAR: Verify payload is securely held
    """
    task_id = task_id or _generate_task_id("pick")
    steps: List[MotionStep] = []
    step_id = 1

    if include_preposition and preposition_pose_mm_deg is not None:
        wp_prep = _to_waypoint(
            preposition_pose_mm_deg,
            MotionStage.PREPOSITION,
            "Preposition to staging area",
            speed_factor,
        )
        steps.append(MotionStep(
            step_id=step_id,
            stage=MotionStage.PREPOSITION,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=wp_prep,
            expected_payload_state=PayloadState.NONE,
            description="Preposition arm toward target sector",
        ))
        step_id += 1

    # Stage: APPROACH
    wp_app = _to_waypoint(
        approach_pose_mm_deg,
        MotionStage.APPROACH,
        "Approach clearance pose above piece",
        speed_factor,
    )
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.APPROACH,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=wp_app,
        expected_payload_state=PayloadState.NONE,
        description="Align arm above source piece at safe clearance altitude",
    ))
    step_id += 1

    # Stage: LAND
    wp_land = _to_waypoint(
        pick_pose_mm_deg,
        MotionStage.LAND,
        "Descend to grasp surface",
        speed_factor,
    )
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=wp_land,
        expected_payload_state=PayloadState.NONE,
        description="Descend vertically to piece grasp height",
    ))
    step_id += 1

    # Stage: GRIP
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.GRIP,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.CLOSE,
        expected_payload_state=PayloadState.EXPECTED_ATTACHED,
        description="Close gripper fingers to seize piece",
    ))
    step_id += 1

    # Stage: LIFT
    wp_lift = _to_waypoint(
        approach_pose_mm_deg,
        MotionStage.LIFT,
        "Lift back to safe clearance altitude",
        speed_factor,
    )
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=wp_lift,
        expected_payload_state=PayloadState.ATTACHED,
        description="Lift piece vertically back to safe clearance altitude",
    ))
    step_id += 1

    # Stage: PAYLOAD_CLEAR
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PAYLOAD_CLEAR,
        motion_type=MotionType.VERIFY,
        expected_payload_state=PayloadState.ATTACHED,
        description="Verify piece is confirmed attached and clear of board",
    ))

    return MotionPlan(
        task_id=task_id,
        plan_type="PICK",
        steps=tuple(steps),
        source=source_cell,
        destination=None,
        payload_intent=PayloadState.ATTACHED,
        placement_version=placement_version,
        metadata=metadata or {},
    )


def build_place_plan(
    approach_pose_mm_deg: Sequence[float],
    place_pose_mm_deg: Sequence[float],
    destination_cell: Optional[Tuple[float, float]] = None,
    speed_factor: float = 1.0,
    placement_version: Optional[int] = None,
    task_id: Optional[str] = None,
    settle_time_s: float = 0.5,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MotionPlan:
    """
    Construct a deterministic place motion plan:
    1. PLACE_APPROACH: Align arm above destination square at safe clearance
    2. PLACE_LAND: Descend vertically to piece placement height
    3. RELEASE: Open gripper fingers to deposit piece
    4. SETTLE: Dwell allowing piece to physically stabilize
    5. POST_RELEASE_LIFT: Ascend vertically clear of placed piece
    """
    task_id = task_id or _generate_task_id("place")
    steps: List[MotionStep] = []
    step_id = 1

    # Stage: PLACE_APPROACH
    wp_app = _to_waypoint(
        approach_pose_mm_deg,
        MotionStage.PLACE_APPROACH,
        "Destination approach pose",
        speed_factor,
    )
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PLACE_APPROACH,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=wp_app,
        expected_payload_state=PayloadState.ATTACHED,
        description="Align held piece above destination at safe clearance",
    ))
    step_id += 1

    # Stage: PLACE_LAND
    wp_land = _to_waypoint(
        place_pose_mm_deg,
        MotionStage.PLACE_LAND,
        "Descend to placement surface",
        speed_factor,
    )
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PLACE_LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=wp_land,
        expected_payload_state=PayloadState.ATTACHED,
        description="Descend vertically to deposit piece onto surface",
    ))
    step_id += 1

    # Stage: RELEASE
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.RELEASE,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.OPEN,
        expected_payload_state=PayloadState.EXPECTED_RELEASED,
        description="Open gripper fingers to release piece",
    ))
    step_id += 1

    # Stage: SETTLE
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.SETTLE,
        motion_type=MotionType.WAIT,
        wait_duration_s=settle_time_s,
        expected_payload_state=PayloadState.RELEASED,
        description="Dwell to allow piece physical settling",
    ))
    step_id += 1

    # Stage: POST_RELEASE_LIFT
    wp_lift = _to_waypoint(
        approach_pose_mm_deg,
        MotionStage.POST_RELEASE_LIFT,
        "Post-release vertical lift",
        speed_factor,
    )
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.POST_RELEASE_LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=wp_lift,
        expected_payload_state=PayloadState.RELEASED,
        description="Lift clear of released piece back to clearance altitude",
    ))

    return MotionPlan(
        task_id=task_id,
        plan_type="PLACE",
        steps=tuple(steps),
        source=None,
        destination=destination_cell,
        payload_intent=PayloadState.RELEASED,
        placement_version=placement_version,
        metadata=metadata or {},
    )


def build_move_plan(
    src_approach_pose_mm_deg: Sequence[float],
    src_pick_pose_mm_deg: Sequence[float],
    dst_approach_pose_mm_deg: Sequence[float],
    dst_place_pose_mm_deg: Sequence[float],
    src_cell: Optional[Tuple[float, float]] = None,
    dst_cell: Optional[Tuple[float, float]] = None,
    speed_factor: float = 1.0,
    placement_version: Optional[int] = None,
    task_id: Optional[str] = None,
    settle_time_s: float = 0.5,
    clear_board_pose_mm_deg: Optional[Sequence[float]] = None,
    service_safe_pose_mm_deg: Optional[Sequence[float]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MotionPlan:
    """
    Construct a full non-capture move plan:
    Pick(src) -> TRANSIT(dst) -> Place(dst) -> [Optional CLEAR_BOARD -> SERVICE_RETREAT].
    """
    task_id = task_id or _generate_task_id("move")
    steps: List[MotionStep] = []
    step_id = 1

    # 1. Pick at source
    # Stage: APPROACH
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.APPROACH,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(src_approach_pose_mm_deg, MotionStage.APPROACH, "Source approach", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Approach source piece at safe clearance altitude",
    ))
    step_id += 1

    # Stage: LAND
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(src_pick_pose_mm_deg, MotionStage.LAND, "Source land", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Descend vertically to grasp height at source",
    ))
    step_id += 1

    # Stage: GRIP
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.GRIP,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.CLOSE,
        expected_payload_state=PayloadState.EXPECTED_ATTACHED,
        description="Close gripper fingers around piece",
    ))
    step_id += 1

    # Stage: LIFT
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(src_approach_pose_mm_deg, MotionStage.LIFT, "Source lift", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Lift piece vertically to safe clearance altitude",
    ))
    step_id += 1

    # Stage: PAYLOAD_CLEAR
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PAYLOAD_CLEAR,
        motion_type=MotionType.VERIFY,
        expected_payload_state=PayloadState.ATTACHED,
        description="Verify piece is confirmed attached before transit",
    ))
    step_id += 1

    # 2. TRANSIT across safe plane
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.TRANSIT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_approach_pose_mm_deg, MotionStage.TRANSIT, "Transit to destination approach", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Horizontal transit across safe plane to destination approach",
    ))
    step_id += 1

    # 3. Place at destination
    # Stage: PLACE_APPROACH
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PLACE_APPROACH,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_approach_pose_mm_deg, MotionStage.PLACE_APPROACH, "Destination approach", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Align at destination approach prior to placement descent",
    ))
    step_id += 1

    # Stage: PLACE_LAND
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PLACE_LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_place_pose_mm_deg, MotionStage.PLACE_LAND, "Destination land", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Descend vertically to destination placement surface",
    ))
    step_id += 1

    # Stage: RELEASE
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.RELEASE,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.OPEN,
        expected_payload_state=PayloadState.EXPECTED_RELEASED,
        description="Open gripper fingers to release piece onto destination",
    ))
    step_id += 1

    # Stage: SETTLE
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.SETTLE,
        motion_type=MotionType.WAIT,
        wait_duration_s=settle_time_s,
        expected_payload_state=PayloadState.RELEASED,
        description="Dwell to allow piece physical settling",
    ))
    step_id += 1

    # Stage: POST_RELEASE_LIFT
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.POST_RELEASE_LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_approach_pose_mm_deg, MotionStage.POST_RELEASE_LIFT, "Post-release lift", speed_factor),
        expected_payload_state=PayloadState.RELEASED,
        description="Lift vertically back to safe clearance altitude",
    ))
    step_id += 1

    # 4. Optional Safe Retreat
    if clear_board_pose_mm_deg is not None:
        steps.append(MotionStep(
            step_id=step_id,
            stage=MotionStage.CLEAR_BOARD,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=_to_waypoint(clear_board_pose_mm_deg, MotionStage.CLEAR_BOARD, "Clear board altitude", speed_factor),
            expected_payload_state=PayloadState.RELEASED,
            description="Elevate to full board clearance transit altitude",
        ))
        step_id += 1

    if service_safe_pose_mm_deg is not None:
        steps.append(MotionStep(
            step_id=step_id,
            stage=MotionStage.SERVICE_RETREAT,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=_to_waypoint(service_safe_pose_mm_deg, MotionStage.SERVICE_RETREAT, "Service retreat", speed_factor),
            expected_payload_state=PayloadState.RELEASED,
            description="Retreat to designated SERVICE_SAFE position",
        ))

    return MotionPlan(
        task_id=task_id,
        plan_type="MOVE",
        steps=tuple(steps),
        source=src_cell,
        destination=dst_cell,
        payload_intent=PayloadState.RELEASED,
        placement_version=placement_version,
        metadata=metadata or {},
    )


def build_capture_plan(
    captured_approach_pose_mm_deg: Sequence[float],
    captured_pick_pose_mm_deg: Sequence[float],
    bin_approach_pose_mm_deg: Sequence[float],
    bin_place_pose_mm_deg: Sequence[float],
    attacker_approach_pose_mm_deg: Sequence[float],
    attacker_pick_pose_mm_deg: Sequence[float],
    dst_approach_pose_mm_deg: Sequence[float],
    dst_place_pose_mm_deg: Sequence[float],
    src_cell: Optional[Tuple[float, float]] = None,
    dst_cell: Optional[Tuple[float, float]] = None,
    bin_cell: Optional[Tuple[float, float]] = None,
    speed_factor: float = 1.0,
    placement_version: Optional[int] = None,
    task_id: Optional[str] = None,
    settle_time_s: float = 0.5,
    clear_board_pose_mm_deg: Optional[Sequence[float]] = None,
    service_safe_pose_mm_deg: Optional[Sequence[float]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MotionPlan:
    """
    Construct a capture move plan:
    1. Pick opponent piece at destination (captured)
    2. TRANSIT to capture bin
    3. Place captured piece in bin (RELEASE -> SETTLE -> POST_RELEASE_LIFT)
    4. TRANSIT to source piece (attacker)
    5. Pick attacking piece at source
    6. TRANSIT to destination
    7. Place attacking piece at destination
    8. [Optional CLEAR_BOARD -> SERVICE_RETREAT]
    
    Guarantees that the captured piece is cleared before the attacking piece moves.
    """
    task_id = task_id or _generate_task_id("capture")
    steps: List[MotionStep] = []
    step_id = 1

    # Part A: Remove captured piece from destination to bin
    # 1. Approach captured piece
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.APPROACH,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(captured_approach_pose_mm_deg, MotionStage.APPROACH, "Captured approach", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Approach captured piece at destination",
    ))
    step_id += 1

    # 2. Land on captured piece
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(captured_pick_pose_mm_deg, MotionStage.LAND, "Captured land", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Descend to grasp captured piece at destination",
    ))
    step_id += 1

    # 3. Grip captured piece
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.GRIP,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.CLOSE,
        expected_payload_state=PayloadState.EXPECTED_ATTACHED,
        description="Close gripper around captured piece",
    ))
    step_id += 1

    # 4. Lift captured piece
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(captured_approach_pose_mm_deg, MotionStage.LIFT, "Captured lift", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Lift captured piece clear of board",
    ))
    step_id += 1

    # 5. Verify payload clear
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PAYLOAD_CLEAR,
        motion_type=MotionType.VERIFY,
        expected_payload_state=PayloadState.ATTACHED,
        description="Verify captured piece is securely held",
    ))
    step_id += 1

    # 6. Transit to bin approach
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.TRANSIT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(bin_approach_pose_mm_deg, MotionStage.TRANSIT, "Transit to bin", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Transit captured piece to capture bin approach",
    ))
    step_id += 1

    # 7. Descend to bin place
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PLACE_LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(bin_place_pose_mm_deg, MotionStage.PLACE_LAND, "Bin land", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Descend into capture bin",
    ))
    step_id += 1

    # 8. Release in bin
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.RELEASE,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.OPEN,
        expected_payload_state=PayloadState.EXPECTED_RELEASED,
        description="Release captured piece in bin",
    ))
    step_id += 1

    # 9. Settle in bin
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.SETTLE,
        motion_type=MotionType.WAIT,
        wait_duration_s=settle_time_s,
        expected_payload_state=PayloadState.RELEASED,
        description="Settle captured piece in bin",
    ))
    step_id += 1

    # 10. Lift from bin
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.POST_RELEASE_LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(bin_approach_pose_mm_deg, MotionStage.POST_RELEASE_LIFT, "Bin lift", speed_factor),
        expected_payload_state=PayloadState.RELEASED,
        description="Lift clear of capture bin",
    ))
    step_id += 1

    # Part B: Move attacking piece from source to destination
    # 11. Transit to attacker source approach
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.TRANSIT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(attacker_approach_pose_mm_deg, MotionStage.TRANSIT, "Transit to attacker", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Transit arm from bin to attacking piece approach",
    ))
    step_id += 1

    # 12. Land on attacker
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(attacker_pick_pose_mm_deg, MotionStage.LAND, "Attacker land", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Descend to grasp attacking piece",
    ))
    step_id += 1

    # 13. Grip attacker
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.GRIP,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.CLOSE,
        expected_payload_state=PayloadState.EXPECTED_ATTACHED,
        description="Close gripper around attacking piece",
    ))
    step_id += 1

    # 14. Lift attacker
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(attacker_approach_pose_mm_deg, MotionStage.LIFT, "Attacker lift", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Lift attacking piece clear of board",
    ))
    step_id += 1

    # 15. Verify attacker clear
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PAYLOAD_CLEAR,
        motion_type=MotionType.VERIFY,
        expected_payload_state=PayloadState.ATTACHED,
        description="Verify attacking piece is securely held",
    ))
    step_id += 1

    # 16. Transit attacker to destination approach
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.TRANSIT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_approach_pose_mm_deg, MotionStage.TRANSIT, "Transit attacker to dst", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Transit attacking piece to destination approach",
    ))
    step_id += 1

    # 17. Land attacker at destination
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.PLACE_LAND,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_place_pose_mm_deg, MotionStage.PLACE_LAND, "Attacker dst land", speed_factor),
        expected_payload_state=PayloadState.ATTACHED,
        description="Descend to place attacking piece at destination",
    ))
    step_id += 1

    # 18. Release attacker
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.RELEASE,
        motion_type=MotionType.GRIPPER,
        gripper_command=GripperCommand.OPEN,
        expected_payload_state=PayloadState.EXPECTED_RELEASED,
        description="Release attacking piece at destination",
    ))
    step_id += 1

    # 19. Settle attacker
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.SETTLE,
        motion_type=MotionType.WAIT,
        wait_duration_s=settle_time_s,
        expected_payload_state=PayloadState.RELEASED,
        description="Settle attacking piece on board",
    ))
    step_id += 1

    # 20. Post-release lift
    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.POST_RELEASE_LIFT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(dst_approach_pose_mm_deg, MotionStage.POST_RELEASE_LIFT, "Attacker post-release lift", speed_factor),
        expected_payload_state=PayloadState.RELEASED,
        description="Lift clear of placed attacking piece",
    ))
    step_id += 1

    # Optional Safe Retreat
    if clear_board_pose_mm_deg is not None:
        steps.append(MotionStep(
            step_id=step_id,
            stage=MotionStage.CLEAR_BOARD,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=_to_waypoint(clear_board_pose_mm_deg, MotionStage.CLEAR_BOARD, "Clear board altitude", speed_factor),
            expected_payload_state=PayloadState.RELEASED,
            description="Elevate to full board clearance transit altitude",
        ))
        step_id += 1

    if service_safe_pose_mm_deg is not None:
        steps.append(MotionStep(
            step_id=step_id,
            stage=MotionStage.SERVICE_RETREAT,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=_to_waypoint(service_safe_pose_mm_deg, MotionStage.SERVICE_RETREAT, "Service retreat", speed_factor),
            expected_payload_state=PayloadState.RELEASED,
            description="Retreat to designated SERVICE_SAFE position",
        ))

    return MotionPlan(
        task_id=task_id,
        plan_type="CAPTURE",
        steps=tuple(steps),
        source=src_cell,
        destination=dst_cell,
        payload_intent=PayloadState.RELEASED,
        placement_version=placement_version,
        metadata=metadata or {},
    )


def build_service_retreat_plan(
    service_safe_pose_mm_deg: Sequence[float],
    clear_board_pose_mm_deg: Optional[Sequence[float]] = None,
    speed_factor: float = 1.0,
    placement_version: Optional[int] = None,
    task_id: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> MotionPlan:
    """
    Construct a standalone retreat-to-safe plan:
    [Optional CLEAR_BOARD] -> SERVICE_RETREAT -> SERVICE_SAFE.
    """
    task_id = task_id or _generate_task_id("retreat")
    steps: List[MotionStep] = []
    step_id = 1

    if clear_board_pose_mm_deg is not None:
        steps.append(MotionStep(
            step_id=step_id,
            stage=MotionStage.CLEAR_BOARD,
            motion_type=MotionType.CARTESIAN_LINEAR,
            waypoint=_to_waypoint(clear_board_pose_mm_deg, MotionStage.CLEAR_BOARD, "Clear board", speed_factor),
            expected_payload_state=PayloadState.NONE,
            description="Elevate to clear all board obstacles",
        ))
        step_id += 1

    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.SERVICE_RETREAT,
        motion_type=MotionType.CARTESIAN_LINEAR,
        waypoint=_to_waypoint(service_safe_pose_mm_deg, MotionStage.SERVICE_RETREAT, "Service retreat", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Retreat arm toward SERVICE_SAFE pose",
    ))
    step_id += 1

    steps.append(MotionStep(
        step_id=step_id,
        stage=MotionStage.SERVICE_SAFE,
        motion_type=MotionType.CARTESIAN_POINT,
        waypoint=_to_waypoint(service_safe_pose_mm_deg, MotionStage.SERVICE_SAFE, "Holding in SERVICE_SAFE", speed_factor),
        expected_payload_state=PayloadState.NONE,
        description="Holding in known collision-free SERVICE_SAFE state",
    ))

    return MotionPlan(
        task_id=task_id,
        plan_type="SERVICE_RETREAT",
        steps=tuple(steps),
        source=None,
        destination=None,
        payload_intent=PayloadState.NONE,
        placement_version=placement_version,
        metadata=metadata or {},
    )
