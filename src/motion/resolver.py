"""
Motion Plan Resolver.

Translates high-level semantic task intents (PieceMoveIntent, CaptureIntent,
BoardPickIntent, BoardPlaceIntent) into fully resolved, robot-space MotionPlans
using authoritative BoardPoseProvider transformations and MotionProfiles.
"""

from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from src.domain.board_pose import BoardPlacementState
from src.domain.board_pose_provider import BoardPoseProvider, FixedBoardPoseProvider
from src.motion.builder import (
    build_capture_plan,
    build_move_plan,
    build_pick_plan,
    build_place_plan,
)
from src.motion.coordinator import MotionProfile
from src.motion.plan import (
    BoardPickIntent,
    BoardPlaceIntent,
    CaptureIntent,
    MotionPlan,
    PieceMoveIntent,
    ResolvedMotionPlan,
)


class MotionResolver:
    """
    Backend-neutral resolver that compiles Semantic Task Intents into ResolvedMotionPlans.
    
    Architectural Guarantee:
        Strictly preserves the transform hierarchy:
        (row, col) -> BoardPoseProvider / BoardPlacementState -> robot base XYZ.
        Never duplicates coordinate arithmetic or hardcodes cell coordinates.
    """

    def __init__(
        self,
        board_pose_provider: BoardPoseProvider,
        motion_profile: Optional[MotionProfile] = None,
        tool_rotation_deg: Sequence[float] = (180.0, 0.0, 90.0),
        default_speed_factor: float = 1.0,
    ):
        if board_pose_provider is None:
            raise ValueError("board_pose_provider must be explicitly provided to MotionResolver")
        self.board_pose_provider = board_pose_provider
        self.motion_profile = motion_profile or MotionProfile()
        self.tool_rotation_deg = list(tool_rotation_deg)
        self.default_speed_factor = float(default_speed_factor)

    def _get_placement_state(
        self, override_state: Optional[BoardPlacementState] = None
    ) -> BoardPlacementState:
        """Obtain authoritative BoardPlacementState."""
        if override_state is not None:
            return override_state
        return self.board_pose_provider.get_board_placement_state()

    def _cell_to_pose_mm_deg(
        self,
        state: BoardPlacementState,
        row: float,
        col: float,
        z_rel_m: float,
        rotation_deg: Optional[Sequence[float]] = None,
    ) -> Sequence[float]:
        """Convert continuous (row, col) on board to 6-DOF Cartesian pose [X, Y, Z (mm), Rx, Ry, Rz (deg)]."""
        rot = list(rotation_deg) if rotation_deg is not None else self.tool_rotation_deg
        p_xyz_m = state.cell_to_robot_xyz(row, col, z_rel_m=z_rel_m)
        x_mm = round(float(p_xyz_m[0]) * 1000.0, 3)
        y_mm = round(float(p_xyz_m[1]) * 1000.0, 3)
        z_mm = round(float(p_xyz_m[2]) * 1000.0, 3)
        return [x_mm, y_mm, z_mm] + rot

    def resolve_pick(
        self,
        intent: BoardPickIntent,
        board_placement: Optional[BoardPlacementState] = None,
        motion_profile: Optional[MotionProfile] = None,
        tool_rotation_deg: Optional[Sequence[float]] = None,
        speed_factor: Optional[float] = None,
        task_id: Optional[str] = None,
    ) -> ResolvedMotionPlan:
        """Resolve a BoardPickIntent into a fully qualified pick plan."""
        state = self._get_placement_state(board_placement)
        prof = motion_profile or self.motion_profile
        rot = tool_rotation_deg or self.tool_rotation_deg
        speed = speed_factor if speed_factor is not None else self.default_speed_factor

        clearance_m = prof.safe_clearance_above_board_mm / 1000.0
        pick_z_m = prof.pick_tcp_height_above_board_mm / 1000.0

        app_pose = self._cell_to_pose_mm_deg(state, intent.row, intent.col, clearance_m, rot)
        pick_pose = self._cell_to_pose_mm_deg(state, intent.row, intent.col, pick_z_m, rot)

        meta = dict(intent.metadata)
        if intent.piece_id:
            meta["piece_id"] = intent.piece_id

        return build_pick_plan(
            approach_pose_mm_deg=app_pose,
            pick_pose_mm_deg=pick_pose,
            source_cell=(intent.row, intent.col),
            speed_factor=speed,
            placement_version=state.placement_version,
            task_id=task_id,
            metadata=meta,
        )

    def resolve_place(
        self,
        intent: BoardPlaceIntent,
        board_placement: Optional[BoardPlacementState] = None,
        motion_profile: Optional[MotionProfile] = None,
        tool_rotation_deg: Optional[Sequence[float]] = None,
        speed_factor: Optional[float] = None,
        settle_time_s: float = 0.5,
        task_id: Optional[str] = None,
    ) -> ResolvedMotionPlan:
        """Resolve a BoardPlaceIntent into a fully qualified place plan."""
        state = self._get_placement_state(board_placement)
        prof = motion_profile or self.motion_profile
        rot = tool_rotation_deg or self.tool_rotation_deg
        speed = speed_factor if speed_factor is not None else self.default_speed_factor

        clearance_m = prof.safe_clearance_above_board_mm / 1000.0
        place_z_m = prof.place_tcp_height_above_board_mm / 1000.0

        app_pose = self._cell_to_pose_mm_deg(state, intent.row, intent.col, clearance_m, rot)
        place_pose = self._cell_to_pose_mm_deg(state, intent.row, intent.col, place_z_m, rot)

        return build_place_plan(
            approach_pose_mm_deg=app_pose,
            place_pose_mm_deg=place_pose,
            destination_cell=(intent.row, intent.col),
            speed_factor=speed,
            placement_version=state.placement_version,
            task_id=task_id,
            settle_time_s=settle_time_s,
            metadata=intent.metadata,
        )

    def resolve_move(
        self,
        intent: PieceMoveIntent,
        board_placement: Optional[BoardPlacementState] = None,
        motion_profile: Optional[MotionProfile] = None,
        tool_rotation_deg: Optional[Sequence[float]] = None,
        speed_factor: Optional[float] = None,
        settle_time_s: float = 0.5,
        clear_board_pose_mm_deg: Optional[Sequence[float]] = None,
        service_safe_pose_mm_deg: Optional[Sequence[float]] = None,
        task_id: Optional[str] = None,
        moving_visual_target: Optional[Any] = None,
    ) -> ResolvedMotionPlan:
        """
        Resolve a standard PieceMoveIntent into an end-to-end motion plan:
        Pick(src) -> TRANSIT -> Place(dst) -> [Optional CLEAR_BOARD -> SERVICE_RETREAT].

        If moving_visual_target is provided, continuous (row, col) refines the pick
        approach and grasp poses without corrupting the exact logical destination place poses.
        """
        state = self._get_placement_state(board_placement)
        prof = motion_profile or self.motion_profile
        rot = tool_rotation_deg or self.tool_rotation_deg
        speed = speed_factor if speed_factor is not None else self.default_speed_factor

        clearance_m = prof.safe_clearance_above_board_mm / 1000.0
        pick_z_m = prof.pick_tcp_height_above_board_mm / 1000.0
        place_z_m = prof.place_tcp_height_above_board_mm / 1000.0

        src_row = intent.src_row
        src_col = intent.src_col
        if moving_visual_target is not None:
            if hasattr(moving_visual_target, "row") and hasattr(moving_visual_target, "col"):
                src_row = float(moving_visual_target.row)
                src_col = float(moving_visual_target.col)
            elif isinstance(moving_visual_target, (tuple, list)) and len(moving_visual_target) >= 2:
                src_row = float(moving_visual_target[0])
                src_col = float(moving_visual_target[1])

        src_app = self._cell_to_pose_mm_deg(state, src_row, src_col, clearance_m, rot)
        src_pick = self._cell_to_pose_mm_deg(state, src_row, src_col, pick_z_m, rot)
        dst_app = self._cell_to_pose_mm_deg(state, intent.dst_row, intent.dst_col, clearance_m, rot)
        dst_place = self._cell_to_pose_mm_deg(state, intent.dst_row, intent.dst_col, place_z_m, rot)

        meta = dict(intent.metadata)
        if intent.piece_id:
            meta["piece_id"] = intent.piece_id

        return build_move_plan(
            src_approach_pose_mm_deg=src_app,
            src_pick_pose_mm_deg=src_pick,
            dst_approach_pose_mm_deg=dst_app,
            dst_place_pose_mm_deg=dst_place,
            src_cell=(intent.src_row, intent.src_col),
            dst_cell=(intent.dst_row, intent.dst_col),
            speed_factor=speed,
            placement_version=state.placement_version,
            task_id=task_id,
            settle_time_s=settle_time_s,
            clear_board_pose_mm_deg=clear_board_pose_mm_deg,
            service_safe_pose_mm_deg=service_safe_pose_mm_deg,
            metadata=meta,
        )

    def resolve_capture(
        self,
        intent: CaptureIntent,
        board_placement: Optional[BoardPlacementState] = None,
        motion_profile: Optional[MotionProfile] = None,
        tool_rotation_deg: Optional[Sequence[float]] = None,
        speed_factor: Optional[float] = None,
        settle_time_s: float = 0.5,
        clear_board_pose_mm_deg: Optional[Sequence[float]] = None,
        service_safe_pose_mm_deg: Optional[Sequence[float]] = None,
        task_id: Optional[str] = None,
        moving_visual_target: Optional[Any] = None,
        captured_visual_target: Optional[Any] = None,
    ) -> ResolvedMotionPlan:
        """
        Resolve a CaptureIntent:
        1. Pick opponent piece at destination square (optionally refined by captured_visual_target)
        2. Transit to capture bin and release
        3. Pick attacking piece at source square (optionally refined by moving_visual_target)
        4. Transit to destination square and place (strictly at logical destination)
        5. [Optional retreat]

        Guarantees that the captured piece is evicted before the attacking piece moves.
        """
        state = self._get_placement_state(board_placement)
        prof = motion_profile or self.motion_profile
        rot = tool_rotation_deg or self.tool_rotation_deg
        speed = speed_factor if speed_factor is not None else self.default_speed_factor

        clearance_m = prof.safe_clearance_above_board_mm / 1000.0
        pick_z_m = prof.pick_tcp_height_above_board_mm / 1000.0
        place_z_m = prof.place_tcp_height_above_board_mm / 1000.0

        # Poses for captured piece at destination
        cap_row = intent.dst_row
        cap_col = intent.dst_col
        if captured_visual_target is not None:
            if hasattr(captured_visual_target, "row") and hasattr(captured_visual_target, "col"):
                cap_row = float(captured_visual_target.row)
                cap_col = float(captured_visual_target.col)
            elif isinstance(captured_visual_target, (tuple, list)) and len(captured_visual_target) >= 2:
                cap_row = float(captured_visual_target[0])
                cap_col = float(captured_visual_target[1])

        c_app = self._cell_to_pose_mm_deg(state, cap_row, cap_col, clearance_m, rot)
        c_pick = self._cell_to_pose_mm_deg(state, cap_row, cap_col, pick_z_m, rot)

        # Poses for capture bin
        if intent.bin_pose_mm_deg is not None:
            bin_place = list(intent.bin_pose_mm_deg)
            bin_app = list(bin_place)
            bin_app[2] += prof.safe_clearance_above_board_mm
        elif intent.bin_cell is not None:
            bin_r, bin_c = intent.bin_cell
            bin_app = self._cell_to_pose_mm_deg(state, bin_r, bin_c, clearance_m, rot)
            bin_place = self._cell_to_pose_mm_deg(state, bin_r, bin_c, place_z_m, rot)
        else:
            raise ValueError(
                "Capture requires explicit bin_pose_mm_deg or bin_cell; none provided"
            )

        # Poses for attacking piece at source
        atk_row = intent.src_row
        atk_col = intent.src_col
        if moving_visual_target is not None:
            if hasattr(moving_visual_target, "row") and hasattr(moving_visual_target, "col"):
                atk_row = float(moving_visual_target.row)
                atk_col = float(moving_visual_target.col)
            elif isinstance(moving_visual_target, (tuple, list)) and len(moving_visual_target) >= 2:
                atk_row = float(moving_visual_target[0])
                atk_col = float(moving_visual_target[1])

        a_app = self._cell_to_pose_mm_deg(state, atk_row, atk_col, clearance_m, rot)
        a_pick = self._cell_to_pose_mm_deg(state, atk_row, atk_col, pick_z_m, rot)

        # Destination placement poses (strictly logical destination)
        d_app = self._cell_to_pose_mm_deg(state, intent.dst_row, intent.dst_col, clearance_m, rot)
        d_place = self._cell_to_pose_mm_deg(state, intent.dst_row, intent.dst_col, place_z_m, rot)

        meta = dict(intent.metadata)
        if intent.attacker_piece_id:
            meta["attacker_piece_id"] = intent.attacker_piece_id
        if intent.captured_piece_id:
            meta["captured_piece_id"] = intent.captured_piece_id

        return build_capture_plan(
            captured_approach_pose_mm_deg=c_app,
            captured_pick_pose_mm_deg=c_pick,
            bin_approach_pose_mm_deg=bin_app,
            bin_place_pose_mm_deg=bin_place,
            attacker_approach_pose_mm_deg=a_app,
            attacker_pick_pose_mm_deg=a_pick,
            dst_approach_pose_mm_deg=d_app,
            dst_place_pose_mm_deg=d_place,
            src_cell=(intent.src_row, intent.src_col),
            dst_cell=(intent.dst_row, intent.dst_col),
            bin_cell=intent.bin_cell,
            speed_factor=speed,
            placement_version=state.placement_version,
            task_id=task_id,
            settle_time_s=settle_time_s,
            clear_board_pose_mm_deg=clear_board_pose_mm_deg,
            service_safe_pose_mm_deg=service_safe_pose_mm_deg,
            metadata=meta,
        )

    def resolve(
        self,
        intent: Union[PieceMoveIntent, CaptureIntent, BoardPickIntent, BoardPlaceIntent],
        **kwargs: Any,
    ) -> ResolvedMotionPlan:
        """Generic entry point dispatching to specialized resolver based on intent type."""
        if isinstance(intent, PieceMoveIntent):
            return self.resolve_move(intent, **kwargs)
        elif isinstance(intent, CaptureIntent):
            return self.resolve_capture(intent, **kwargs)
        elif isinstance(intent, BoardPickIntent):
            return self.resolve_pick(intent, **kwargs)
        elif isinstance(intent, BoardPlaceIntent):
            return self.resolve_place(intent, **kwargs)
        raise ValueError(f"Unsupported intent type: {type(intent)}")
