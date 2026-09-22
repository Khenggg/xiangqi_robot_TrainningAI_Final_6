"""
Authoritative Dynamic Board Placement State, Board Pose, and Analytical Geometry Analyzer.

Enforces:
- Robot Base frame {B} authority
- Authoritative Board Pose / board-frame transform architecture:
    p_robot = p_surface_center + R_robot_from_board @ [u, v, z_rel]
    [u, v, z_rel] = R_board_from_robot @ (p_robot - p_surface_center)
- Canonical board-local coordinates:
    u = (col - 4.0) * 0.040 m
    v = (row - 4.5) * 0.040 m
- Canonical 90° orientation (board_yaw_deg = +90.0):
    +column board axis (u) -> -X_robot
    +row board axis (v)    -> -Y_robot
    +Z_board               -> +Z_robot
- Dynamic board forward shift d (d > 0 means board center moves farther from robot along -X_robot)
- Exact geometry-independent reach prechecks and robustness quality scoring
"""

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics, IKResult


from src.domain.board_pose import (
    BoardCell,
    rot_matrix_to_quat,
    DEFAULT_BOARD_YAW_DEG,
    compute_rotation_matrix,
    load_nominal_scene_placement,
    BoardPlacementState,
    canonical_cell_to_robot_xyz_m,
    find_nearest_cell,
)



class BoardPlacementAnalyzer:
    """
    Analytical and empirical analyzer for Xiangqi board placement feasibility and optimization.
    Evaluates geometry-independent metrics derived strictly from authoritative BoardPlacementState.
    """

    def __init__(
        self,
        kinematics: Optional[FR3Kinematics] = None,
        tool_flange_to_tcp_m: Sequence[float] = (0.0, 0.0, 0.218),
        board_surface_nominal_m: float = 0.0105,
    ):
        self.kinematics = kinematics or FR3Kinematics()
        self.geom = get_physical_geometry()
        self.tool_length_m = float(tool_flange_to_tcp_m[2])
        self.tool_length_mm = self.tool_length_m * 1000.0
        self.board_surface_nominal_m = float(board_surface_nominal_m)
        self.board_surface_nominal_mm = self.board_surface_nominal_m * 1000.0
        self.piece_height_mm = float(self.geom.piece_height_mm)
        self.R_precheck_m = float(self.kinematics.MAX_REACH_RADIUS_M)
        self.R_precheck_mm = self.R_precheck_m * 1000.0

    def compute_geometric_precheck(
        self,
        forward_shift_mm: float,
        safe_transit_height_mm: float = 70.0,
        board_height_offset_mm: float = 0.0,
        board_surface_mm: Optional[float] = None,
        board_yaw_deg: float = 90.0,
        placement_version: int = 1,
    ) -> Dict[str, Any]:
        """
        Derive pure analytical geometric feasibility precheck using geometry-independent metrics.
        """
        d = float(forward_shift_mm)
        H = float(safe_transit_height_mm)
        h_off = float(board_height_offset_mm)
        z_board = board_surface_mm if board_surface_mm is not None else (self.board_surface_nominal_mm + h_off)
        piece_h_m = self.piece_height_mm / 1000.0

        state = BoardPlacementState.compute(
            forward_shift_mm=d,
            safe_transit_height_mm=H,
            board_height_offset_mm=h_off,
            board_yaw_deg=board_yaw_deg,
            placement_version=placement_version,
        )

        max_flange_approach_dist_mm = 0.0
        max_flange_grasp_dist_mm = 0.0
        max_tcp_reach_dist_mm = 0.0
        min_tcp_reach_dist_mm = float("inf")
        farthest_cell = (0, 0)
        nearest_cell = (0, 0)
        p_flange_ap_far = None
        min_grid_depth_mm = float("inf")
        max_grid_depth_mm = 0.0

        # Evaluate across all 90 cells
        for r in range(10):
            for c in range(9):
                p_gr = state.cell_to_robot_xyz(r, c, z_rel_m=piece_h_m / 2.0)
                p_ap = state.cell_to_robot_xyz(r, c, z_rel_m=H / 1000.0)

                p_flange_gr = p_gr + np.array([0.0, 0.0, self.tool_length_m])
                p_flange_ap = p_ap + np.array([0.0, 0.0, self.tool_length_m])

                d_flange_gr = float(np.linalg.norm(p_flange_gr)) * 1000.0
                d_flange_ap = float(np.linalg.norm(p_flange_ap)) * 1000.0
                d_tcp = float(np.linalg.norm(p_gr[:2])) * 1000.0
                grid_depth = abs(p_gr[0]) * 1000.0

                if grid_depth < min_grid_depth_mm:
                    min_grid_depth_mm = grid_depth
                if grid_depth > max_grid_depth_mm:
                    max_grid_depth_mm = grid_depth

                if d_flange_ap > max_flange_approach_dist_mm:
                    max_flange_approach_dist_mm = d_flange_ap
                    farthest_cell = (r, c)
                    p_flange_ap_far = p_flange_ap
                if d_flange_gr > max_flange_grasp_dist_mm:
                    max_flange_grasp_dist_mm = d_flange_gr
                if d_tcp > max_tcp_reach_dist_mm:
                    max_tcp_reach_dist_mm = d_tcp
                if d_tcp < min_tcp_reach_dist_mm:
                    min_tcp_reach_dist_mm = d_tcp
                    nearest_cell = (r, c)

        approach_margin_mm = self.R_precheck_mm - max_flange_approach_dist_mm
        grasp_margin_mm = self.R_precheck_mm - max_flange_grasp_dist_mm

        # Physical board edges from robot base:
        # Box has local half-widths: width (367mm) along u, length (410mm) along v
        hw = 0.367 / 2.0
        hl = 0.410 / 2.0
        corners_local = [(-hw, -hl), (-hw, hl), (hw, -hl), (hw, hl)]
        corners_robot = [state.board_local_to_robot(u, v, 0.0) for u, v in corners_local]
        x_corners = [c[0] for c in corners_robot]
        near_edge_x = max(x_corners)
        far_edge_x = min(x_corners)
        near_board_edge_dist = abs(near_edge_x) * 1000.0
        far_board_edge_dist = abs(far_edge_x) * 1000.0
        board_center_dist = abs(state.board_center_robot_m[0]) * 1000.0

        # Dynamic d_max and h_max derived from farthest transformed cell
        d_max_mm = None
        h_max_mm = None
        if p_flange_ap_far is not None:
            x_far_mm = p_flange_ap_far[0] * 1000.0
            y_far_mm = p_flange_ap_far[1] * 1000.0
            z_flange_app_mm = p_flange_ap_far[2] * 1000.0
            rad_d = self.R_precheck_mm**2 - y_far_mm**2 - z_flange_app_mm**2
            x_base_far_mm = abs(x_far_mm) - d
            d_max_mm = math.sqrt(rad_d) - x_base_far_mm if rad_d >= 0.0 else None

            rad_h = self.R_precheck_mm**2 - y_far_mm**2 - x_far_mm**2
            h_max_mm = math.sqrt(rad_h) - z_board - self.tool_length_mm if rad_h >= 0.0 else None

        is_geometric_pass = (approach_margin_mm >= 0.0) and (grasp_margin_mm >= 0.0) and (d >= -20.0)

        return {
            "type": "placement_analysis",
            "forward_shift_mm": round(d, 2),
            "board_surface_z_mm": round(z_board, 2),
            "safe_transit_height_mm": round(H, 2),
            "board_yaw_deg": round(board_yaw_deg, 2),
            "board_center_robot_xyz_m": [round(v, 5) for v in state.board_center_robot_m],
            "board_center_distance_mm": round(board_center_dist, 2),
            "near_board_edge_distance_mm": round(near_board_edge_dist, 2),
            "far_board_edge_distance_mm": round(far_board_edge_dist, 2),
            "near_grid_depth_mm": round(min_grid_depth_mm, 2),
            "far_grid_depth_mm": round(max_grid_depth_mm, 2),
            "nearest_grid_cell": list(nearest_cell),
            "nearest_grid_cell_distance_mm": round(min_tcp_reach_dist_mm, 2),
            "farthest_grid_cell": list(farthest_cell),
            "farthest_grid_cell_distance_mm": round(max_tcp_reach_dist_mm, 2),
            "far_grasp_distance_mm": round(max_flange_grasp_dist_mm, 2),
            "far_approach_distance_mm": round(max_flange_approach_dist_mm, 2),
            "r_precheck_mm": round(self.R_precheck_mm, 2),
            "grasp_reach_margin_mm": round(grasp_margin_mm, 2),
            "approach_reach_margin_mm": round(approach_margin_mm, 2),
            "d_max_for_current_h_mm": round(d_max_mm, 2) if d_max_mm is not None else None,
            "h_max_for_current_d_mm": round(h_max_mm, 2) if h_max_mm is not None else None,
            "status": "GEOMETRIC PASS" if is_geometric_pass else "GEOMETRIC FAIL",
            "is_geometric_pass": is_geometric_pass,
            "placement_version": int(placement_version),
        }

    def compute_quality_score(
        self,
        joint_limit_margin_deg: float,
        condition_number: float,
        manipulability: float,
        collision_clearance_mm: float,
        reach_margin_mm: float,
    ) -> float:
        """
        Define scalar quality score for feasible placement candidates:
        Prefers comfortably inside safe region with high manipulability and clearance.
        """
        c_clamped = max(1.0, min(100.0, condition_number)) if math.isfinite(condition_number) else 100.0
        cond_penalty = math.log(c_clamped)

        score = (
            15.0 * manipulability +
            0.15 * joint_limit_margin_deg +
            0.10 * collision_clearance_mm +
            0.05 * reach_margin_mm -
            1.5 * cond_penalty
        )
        return float(score)
