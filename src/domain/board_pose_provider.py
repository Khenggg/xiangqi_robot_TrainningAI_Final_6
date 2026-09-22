"""
Domain module for Board Pose Providers.

Decouples board localization and calibration from motion execution.
Allows switching between fixed nominal pose, calibrated physical teaching points,
and future vision-based dynamic board tracking.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence, Tuple
import math
import numpy as np

from src.domain.board_pose import BoardPlacementState, compute_rotation_matrix


class BoardPoseProvider(ABC):
    """Abstract interface for providing authoritative BoardPlacementState."""

    @abstractmethod
    def get_board_placement_state(self) -> BoardPlacementState:
        """Return the authoritative BoardPlacementState."""
        pass


class FixedBoardPoseProvider(BoardPoseProvider):
    """
    Fixed/static board placement provider.
    Used for simulation nominal placement and statically calibrated physical setups.
    """

    def __init__(self, placement_state: Optional[BoardPlacementState] = None):
        self._state = placement_state or BoardPlacementState.compute(forward_shift_mm=0.0)

    def get_board_placement_state(self) -> BoardPlacementState:
        return self._state

    def set_board_placement_state(self, state: BoardPlacementState) -> None:
        self._state = state

    @classmethod
    def from_forward_shift(
        cls,
        forward_shift_mm: float = 0.0,
        board_yaw_deg: float = 90.0,
        safe_transit_height_mm: float = 40.0,
    ) -> "FixedBoardPoseProvider":
        state = BoardPlacementState.compute(
            forward_shift_mm=forward_shift_mm,
            board_yaw_deg=board_yaw_deg,
            safe_transit_height_mm=safe_transit_height_mm,
        )
        return cls(state)

    @classmethod
    def from_teaching_points(
        cls,
        teaching_points: Dict[str, Any],
        board_yaw_deg: float = 90.0,
        safe_transit_height_mm: float = 40.0,
    ) -> "FixedBoardPoseProvider":
        """
        Bootstrap BoardPlacementState from legacy R1-R4 teaching points.
        R1: (row=0, col=0)
        R2: (row=0, col=8)
        R3: (row=9, col=8)
        R4: (row=9, col=0)
        Calculates physical board center and surface height, then builds BoardPlacementState.
        """
        required = ["R1", "R2", "R3", "R4"]
        for pt in required:
            if pt not in teaching_points:
                raise ValueError(f"Teaching points dictionary missing required point '{pt}'")

        def extract_xyz(val):
            if isinstance(val, dict) and "pose" in val:
                val = val["pose"]
            return [float(val[0]), float(val[1]), float(val[2])]

        p_r1 = np.array(extract_xyz(teaching_points["R1"]))
        p_r2 = np.array(extract_xyz(teaching_points["R2"]))
        p_r3 = np.array(extract_xyz(teaching_points["R3"]))
        p_r4 = np.array(extract_xyz(teaching_points["R4"]))

        # Center is the mean of the 4 grid corners in robot base {B} (in meters)
        # Note: Teaching points are in mm, convert to meters
        center_m = np.mean([p_r1, p_r2, p_r3, p_r4], axis=0) / 1000.0
        surface_z_m = float(center_m[2])

        thickness_m = 0.0105
        box_center_z = surface_z_m - thickness_m / 2.0

        board_center_robot_m = [round(float(center_m[0]), 6), round(float(center_m[1]), 6), round(box_center_z, 6)]

        state = BoardPlacementState(
            forward_shift_mm=0.0,
            safe_transit_height_mm=float(safe_transit_height_mm),
            board_height_offset_mm=0.0,
            board_yaw_deg=float(board_yaw_deg),
            board_center_robot_m=board_center_robot_m,
            board_surface_z_robot_m=round(surface_z_m, 6),
            physical_board_center_robot_m=board_center_robot_m,
            physical_board_center_world_m=[round(-center_m[1], 6), round(box_center_z, 6), round(-center_m[0], 6)],
            board_visual_root_world_m=[round(-center_m[1], 6), round(surface_z_m, 6), round(-center_m[0], 6)],
            board_center_world_m=[round(-center_m[1], 6), round(surface_z_m, 6), round(-center_m[0], 6)],
            placement_version=1,
        )
        p_c00 = state.cell_to_robot_xyz(0, 0, z_rel_m=0.0)
        state.grid_origin_robot_m = [round(float(v), 6) for v in p_c00]
        return cls(state)
