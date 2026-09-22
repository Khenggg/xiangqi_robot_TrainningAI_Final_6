"""
Motion Coordinator layer for Xiangqi Robot pick-and-place choreography.

Decouples high-level motion planning and multi-stage pick/place sequences
from backend hardware execution (VirtualFR3Backend vs PhysicalFR3Backend).
"""

from typing import Any, Optional, Sequence, Tuple
import logging
import time

from src.domain.board_pose import BoardPlacementState
from src.domain.board_pose_provider import BoardPoseProvider, FixedBoardPoseProvider
from src.hardware.backends.base import RobotBackend

logger = logging.getLogger(__name__)


class MotionCoordinator:
    """
    Coordinates multi-phase pick, place, and capture sequences using an authoritative
    BoardPoseProvider and an abstract RobotBackend.
    """

    def __init__(
        self,
        backend: RobotBackend,
        board_pose_provider: Optional[BoardPoseProvider] = None,
        tool_rotation_deg: Sequence[float] = (180.0, 0.0, 90.0),
        safe_clearance_z_mm: float = 40.0,
        pick_depth_offset_mm: float = 0.0,
    ):
        self.backend = backend
        self.board_pose_provider = board_pose_provider or FixedBoardPoseProvider()
        self.tool_rotation_deg = list(tool_rotation_deg)
        self.safe_clearance_z_mm = float(safe_clearance_z_mm)
        self.pick_depth_offset_mm = float(pick_depth_offset_mm)

    @property
    def board_placement(self) -> BoardPlacementState:
        return self.board_pose_provider.get_board_placement_state()

    def _get_cartesian_pose_mm_deg(
        self,
        row: float,
        col: float,
        z_rel_m: float = 0.0,
    ) -> Sequence[float]:
        """Convert continuous (row, col) on board to full 6-DOF Cartesian pose [X, Y, Z (mm), Rx, Ry, Rz (deg)]."""
        state = self.board_placement
        p_xyz_m = state.cell_to_robot_xyz(row, col, z_rel_m=z_rel_m)
        # Convert meters to mm for FAIRINO / Backend Cartesian interface
        x_mm = float(p_xyz_m[0]) * 1000.0
        y_mm = float(p_xyz_m[1]) * 1000.0
        z_mm = float(p_xyz_m[2]) * 1000.0
        return [round(x_mm, 2), round(y_mm, 2), round(z_mm, 2)] + list(self.tool_rotation_deg)

    def pick(self, row: float, col: float, visual_target: Optional[Any] = None) -> bool:
        """
        Execute pick choreography at cell (row, col):
        1. Open gripper
        2. Move to approach pose (safe height above piece)
        3. Descend to pick surface
        4. Close gripper
        5. Lift back to approach pose
        """
        target_row = getattr(visual_target, "row", row) if visual_target is not None else row
        target_col = getattr(visual_target, "col", col) if visual_target is not None else col

        clearance_m = self.safe_clearance_z_mm / 1000.0
        pick_z_m = self.pick_depth_offset_mm / 1000.0

        approach_pose = self._get_cartesian_pose_mm_deg(target_row, target_col, z_rel_m=clearance_m)
        pick_pose = self._get_cartesian_pose_mm_deg(target_row, target_col, z_rel_m=pick_z_m)

        logger.info(f"[MotionCoordinator] Pick at (row={target_row:.2f}, col={target_col:.2f}) -> {pick_pose[:3]}")

        # 1. Open gripper
        if not self.backend.set_gripper(closed=False):
            return False

        # 2. Move to approach pose
        if not self.backend.move_cartesian(approach_pose):
            return False

        # 3. Descend to pick
        if not self.backend.move_cartesian(pick_pose):
            return False

        # 4. Close gripper
        if not self.backend.set_gripper(closed=True):
            return False

        # 5. Lift to safe clearance
        if not self.backend.move_cartesian(approach_pose):
            return False

        return True

    def place(self, row: float, col: float) -> bool:
        """
        Execute place choreography at cell (row, col):
        1. Move to approach pose
        2. Descend to place surface
        3. Open gripper
        4. Lift back to approach pose
        """
        clearance_m = self.safe_clearance_z_mm / 1000.0
        place_z_m = self.pick_depth_offset_mm / 1000.0

        approach_pose = self._get_cartesian_pose_mm_deg(row, col, z_rel_m=clearance_m)
        place_pose = self._get_cartesian_pose_mm_deg(row, col, z_rel_m=place_z_m)

        logger.info(f"[MotionCoordinator] Place at (row={row:.2f}, col={col:.2f}) -> {place_pose[:3]}")

        # 1. Move to approach pose
        if not self.backend.move_cartesian(approach_pose):
            return False

        # 2. Descend to place
        if not self.backend.move_cartesian(place_pose):
            return False

        # 3. Open gripper
        if not self.backend.set_gripper(closed=False):
            return False

        # 4. Lift to safe clearance
        if not self.backend.move_cartesian(approach_pose):
            return False

        return True

    def place_pose(self, pose_mm_deg: Sequence[float]) -> bool:
        """
        Execute place choreography directly at a Cartesian pose [X, Y, Z, Rx, Ry, Rz]:
        Used for off-board locations such as capture bin.
        """
        pose = list(pose_mm_deg)
        approach_pose = pose.copy()
        approach_pose[2] += self.safe_clearance_z_mm

        logger.info(f"[MotionCoordinator] Place at custom pose -> {pose[:3]}")

        # 1. Move to approach pose
        if not self.backend.move_cartesian(approach_pose):
            return False

        # 2. Descend to place pose
        if not self.backend.move_cartesian(pose):
            return False

        # 3. Open gripper
        if not self.backend.set_gripper(closed=False):
            return False

        # 4. Lift back to approach pose
        if not self.backend.move_cartesian(approach_pose):
            return False

        return True

    def execute_move(
        self,
        src_row: float,
        src_col: float,
        dst_row: float,
        dst_col: float,
        is_capture: bool = False,
        capture_bin_cell: Optional[Tuple[float, float]] = None,
        capture_bin_pose_mm: Optional[Sequence[float]] = None,
        moving_visual_target: Optional[Any] = None,
        captured_visual_target: Optional[Any] = None,
    ) -> bool:
        """
        Execute full move sequence:
        If capture: pick piece at dst (with optional visual target) and place into capture bin.
        Pick piece at src (with optional visual target) and place at dst.
        """
        if is_capture:
            # Capture destination piece first
            logger.info(f"[MotionCoordinator] Capturing piece at ({dst_row},{dst_col})")
            if not self.pick(dst_row, dst_col, visual_target=captured_visual_target):
                return False

            if capture_bin_pose_mm is not None:
                if not self.place_pose(capture_bin_pose_mm):
                    return False
            else:
                bin_r, bin_c = capture_bin_cell if capture_bin_cell is not None else (-1.0, -1.0)
                if not self.place(bin_r, bin_c):
                    return False

        # Move attacker to dst
        if not self.pick(src_row, src_col, visual_target=moving_visual_target):
            return False
        if not self.place(dst_row, dst_col):
            return False

        return True
