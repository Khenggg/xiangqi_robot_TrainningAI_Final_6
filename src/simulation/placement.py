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
- Dynamic board shift d follows the positive board column axis at the current yaw
- Exact geometry-independent reach prechecks and robustness quality scoring
"""

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from src.domain.geometry import get_physical_geometry, get_canonical_tool_geometry
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
        tool_flange_to_tcp_m: Optional[Sequence[float]] = None,
        board_surface_nominal_m: float = 0.0105,
    ):
        self.kinematics = kinematics or FR3Kinematics()
        self.geom = get_physical_geometry()
        canonical_tool = get_canonical_tool_geometry()
        if tool_flange_to_tcp_m is None:
            tool_flange_to_tcp_m = canonical_tool.canonical_tcp_offset_m
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
        board_yaw_deg: Optional[float] = None,
        placement_version: int = 1,
        placement_state: Optional[BoardPlacementState] = None,
    ) -> Dict[str, Any]:
        """Read-only analytical diagnostics from the exact board transform.

        X-depth fields retain their historical |X_robot| meaning, not radial
        distance. This reach sphere is not IK, collision or physical safety proof.
        ``placement_state`` avoids reconstructing a calibrated pose from nominal
        scene values; callers that omit it use the current nominal scene.
        """
        metric_fields = (
            "board_center_distance_mm", "near_board_edge_distance_mm",
            "far_board_edge_distance_mm", "near_grid_depth_mm", "far_grid_depth_mm",
            "nearest_grid_cell_distance_mm", "farthest_grid_cell_distance_mm",
            "far_grasp_distance_mm", "far_approach_distance_mm", "r_precheck_mm",
            "grasp_reach_margin_mm", "approach_reach_margin_mm",
            "d_max_for_current_h_mm", "h_max_for_current_d_mm",
        )

        def unknown(reason):
            return {"type": "placement_analysis", "status": "GEOMETRIC UNKNOWN",
                    "is_geometric_pass": False, "is_geometric_known": False,
                    "reason": reason, **{name: None for name in metric_fields}}

        try:
            d, H, h_off = map(float, (forward_shift_mm, safe_transit_height_mm, board_height_offset_mm))
            if not all(math.isfinite(value) for value in (d, H, h_off, self.tool_length_m, self.R_precheck_mm)):
                return unknown("Non-finite placement or tool geometry")
            if self.tool_length_m <= 0 or self.R_precheck_mm <= 0:
                return unknown("Invalid tool geometry or reach radius")
            state = placement_state if placement_state is not None else BoardPlacementState.compute(
                forward_shift_mm=d, safe_transit_height_mm=H,
                board_height_offset_mm=h_off, board_yaw_deg=board_yaw_deg,
                nominal_board_surface_z_m=self.board_surface_nominal_m,
                placement_version=placement_version,
            )
            T = np.array(state.T_robot_from_board, dtype=float, copy=True)
            z_board = float(board_surface_mm) if board_surface_mm is not None else T[2, 3] * 1000.0
            if T.shape != (4, 4) or not np.all(np.isfinite(T)) or not math.isfinite(z_board):
                return unknown("Non-finite board transform or surface")
            if (not np.allclose(T[3], [0, 0, 0, 1], atol=1e-6, rtol=0)
                    or not np.allclose(T[:3, :3].T @ T[:3, :3], np.eye(3), atol=1e-4, rtol=0)
                    or abs(float(np.linalg.det(T[:3, :3])) - 1.0) > 1e-4):
                return unknown("Board transform is not rigid")
            T[2, 3] = z_board / 1000.0
        except (TypeError, ValueError, OverflowError) as error:
            return unknown(str(error))

        def point(u, v, height=0.0):
            return (T[:3, :3] @ np.array([u, v, height]) + T[:3, 3]) * 1000.0

        def interval(base, axis):
            # Exact intersection of |base + t*axis| <= R with a line.
            a = float(np.dot(axis, axis))
            b = float(np.dot(base, axis))
            c = float(np.dot(base, base)) - self.R_precheck_mm**2
            discriminant = b*b - a*c
            if a <= 0 or discriminant < 0:
                return None
            half = math.sqrt(discriminant)
            return ((-b-half)/a, (-b+half)/a)

        max_app = max_grasp = max_grid = max_depth = 0.0
        min_grid = min_depth = float("inf")
        nearest_cell = farthest_cell = (0, 0)
        shift_lower, shift_upper = -20.0, float("inf")
        height_lower, height_upper = -float("inf"), float("inf")
        column_axis, normal = T[:3, 0], T[:3, 2]
        rows, columns = self.geom.board.rows, self.geom.board.columns
        for row in range(rows):
            for col in range(columns):
                u = (col-(columns-1)/2) * self.geom.grid_cell_width_mm / 1000.0
                v = (row-(rows-1)/2) * self.geom.grid_cell_length_mm / 1000.0
                p = point(u, v)
                grasp = point(u, v, self.piece_height_mm / 2000.0)
                approach = point(u, v, H / 1000.0)
                grasp[2] += self.tool_length_mm
                approach[2] += self.tool_length_mm
                grid_dist = float(np.linalg.norm(p[:2]))
                if grid_dist < min_grid:
                    min_grid, nearest_cell = grid_dist, (row, col)
                max_grid = max(max_grid, grid_dist)
                min_depth, max_depth = min(min_depth, abs(p[0])), max(max_depth, abs(p[0]))
                max_grasp = max(max_grasp, float(np.linalg.norm(grasp)))
                app_dist = float(np.linalg.norm(approach))
                if app_dist > max_app:
                    max_app, farthest_cell = app_dist, (row, col)
                # All cells and both endpoint heights constrain d; the farthest
                # cell can change as the board moves along its column axis.
                for endpoint in (grasp, approach):
                    bounds = interval(endpoint-d*column_axis, column_axis)
                    if bounds is None:
                        shift_lower, shift_upper = float("inf"), -float("inf")
                    else:
                        shift_lower, shift_upper = max(shift_lower, bounds[0]), min(shift_upper, bounds[1])
                bounds = interval(approach-H*normal, normal)
                if bounds is None:
                    height_lower, height_upper = float("inf"), -float("inf")
                else:
                    height_lower, height_upper = max(height_lower, bounds[0]), min(height_upper, bounds[1])

        hw, hl = self.geom.outer_width_mm / 2000.0, self.geom.outer_length_mm / 2000.0
        corners_x = [point(u, v)[0] for u in (-hw, hw) for v in (-hl, hl)]
        min_x, max_x = min(corners_x), max(corners_x)
        near_edge = 0.0 if min_x <= 0 <= max_x else min(abs(min_x), abs(max_x))
        far_edge = max(abs(min_x), abs(max_x))
        # Round published upper limits inward, never past the exact reach sphere.
        d_max = math.floor(shift_upper*100)/100 if shift_lower <= shift_upper else None
        H_max = math.floor(height_upper*100)/100 if height_lower <= height_upper and max_grasp <= self.R_precheck_mm else None
        app_margin, grasp_margin = self.R_precheck_mm-max_app, self.R_precheck_mm-max_grasp
        passed = app_margin >= 0 and grasp_margin >= 0 and d >= -20.0
        center = [float(T[0, 3]), float(T[1, 3]), z_board/1000-self.geom.board_thickness_m/2]
        return {
            "type": "placement_analysis", "is_geometric_known": True,
            "forward_shift_mm": round(d, 2), "board_surface_z_mm": round(z_board, 2),
            "safe_transit_height_mm": round(H, 2), "board_yaw_deg": round(state.board_yaw_deg, 2),
            "board_center_robot_xyz_m": [round(value, 5) for value in center],
            "board_center_distance_mm": round(abs(T[0, 3])*1000, 2),
            "near_board_edge_distance_mm": round(near_edge, 2), "far_board_edge_distance_mm": round(far_edge, 2),
            "near_grid_depth_mm": round(min_depth, 2), "far_grid_depth_mm": round(max_depth, 2),
            "nearest_grid_cell": list(nearest_cell), "nearest_grid_cell_distance_mm": round(min_grid, 2),
            "farthest_grid_cell": list(farthest_cell), "farthest_grid_cell_distance_mm": round(max_grid, 2),
            "far_grasp_distance_mm": round(max_grasp, 2), "far_approach_distance_mm": round(max_app, 2),
            "r_precheck_mm": round(self.R_precheck_mm, 2),
            "grasp_reach_margin_mm": round(grasp_margin, 2), "approach_reach_margin_mm": round(app_margin, 2),
            "d_max_for_current_h_mm": d_max, "h_max_for_current_d_mm": H_max,
            "status": "GEOMETRIC PASS" if passed else "GEOMETRIC FAIL", "is_geometric_pass": bool(passed),
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
