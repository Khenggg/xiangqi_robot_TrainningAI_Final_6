"""
Authoritative Dynamic Board Placement State and Analytical Geometry Analyzer.

Enforces:
- Robot Base frame {B} authority
- Dynamic board forward shift d (d > 0 means farther from robot along -X_robot, Three.js +Z_world)
- Canonical coordinate transformation contract:
    x(r, d) = -0.180 - d/1000.0 - 0.040*r
    y(c)    = -0.160 + 0.040*c
    z_board = board surface height
- Exact analytical reach prechecks (d_max(H), H_max(d))
- Quality scoring across 90 cells (joint limits, condition number, manipulability, clearance)

NOTE on Continuous Interval Search / Automated Optimization:
Continuous parameter optimization of board placement (e.g. automated Nelder-Mead / gradient
interval search) is currently TODO / NOT IMPLEMENTED.
The parameter pair (forward_shift_mm=28.5, safe_transit_height_mm=40.0) represents a
previously tested candidate / known regression candidate, NOT a globally optimized or
physically calibrated placement.
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


def load_nominal_scene_placement(scene_config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load nominal placement parameters from shared/virtual_fr3_scene.json."""
    if scene_config_path is None:
        scene_config_path = Path(__file__).resolve().parent.parent.parent / "shared" / "virtual_fr3_scene.json"
    if scene_config_path.is_file():
        try:
            with open(scene_config_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return data.get("virtual_board_placement", {})
        except Exception:
            pass
    return {
        "grid_origin_in_robot_base_m": [-0.18, -0.16, 0.0105],
        "board_center_in_robot_base_m": [-0.36, 0.0, 0.0105],
        "grid_origin_in_3d_world_m": [0.16, 0.0105, 0.18],
        "board_center_in_3d_world_m": [0.0, 0.0105, 0.36],
        "board_surface_height_m": 0.0105,
    }


@dataclass
class BoardPlacementState:
    """
    Authoritative runtime state for Xiangqi board placement.
    Disambiguates:
      - physical_board_center_robot_m: Center of board physical box in robot base {B}
      - physical_board_center_world_m: Center of board physical box in Three.js world {W}
      - board_surface_z_robot_m: Height of board playing surface in {B}
      - board_visual_root_world_m: Visual root placement in Three.js {W}
      - grid_origin_robot_m: Intersection of (row 0, col 0) in {B}
      - board_center_robot_m / board_center_world_m: Backward-compatible aliases
    """
    forward_shift_mm: float = 0.0
    safe_transit_height_mm: float = 70.0
    board_height_offset_mm: float = 0.0
    grid_origin_robot_m: List[float] = field(default_factory=lambda: [-0.180, -0.160, 0.0105])
    physical_board_center_robot_m: List[float] = field(default_factory=lambda: [-0.360, 0.0, 0.00525])
    physical_board_center_world_m: List[float] = field(default_factory=lambda: [0.0, 0.00525, 0.360])
    board_surface_z_robot_m: float = 0.0105
    board_visual_root_world_m: List[float] = field(default_factory=lambda: [0.0, 0.0105, 0.360])
    # Backward compatible aliases
    board_center_robot_m: List[float] = field(default_factory=lambda: [-0.360, 0.0, 0.00525])
    board_center_world_m: List[float] = field(default_factory=lambda: [0.0, 0.0105, 0.360])
    placement_version: int = 1
    timestamp: float = field(default_factory=time.time)

    @property
    def board_surface_z_m(self) -> float:
        return self.board_surface_z_robot_m

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "board_placement",
            "forward_shift_mm": round(self.forward_shift_mm, 2),
            "safe_transit_height_mm": round(self.safe_transit_height_mm, 2),
            "board_height_offset_mm": round(self.board_height_offset_mm, 2),
            "grid_origin_robot_m": [round(v, 5) for v in self.grid_origin_robot_m],
            "physical_board_center_robot_m": [round(v, 5) for v in self.physical_board_center_robot_m],
            "physical_board_center_world_m": [round(v, 5) for v in self.physical_board_center_world_m],
            "board_surface_z_robot_m": round(self.board_surface_z_robot_m, 5),
            "board_surface_z_m": round(self.board_surface_z_robot_m, 5),
            "board_visual_root_world_m": [round(v, 5) for v in self.board_visual_root_world_m],
            "board_center_robot_m": [round(v, 5) for v in self.board_center_robot_m],
            "board_center_world_m": [round(v, 5) for v in self.board_center_world_m],
            "placement_version": self.placement_version,
            "timestamp": self.timestamp,
        }

    @classmethod
    def compute(
        cls,
        forward_shift_mm: float,
        safe_transit_height_mm: float = 70.0,
        board_height_offset_mm: float = 0.0,
        nominal_grid_origin_m: Optional[Sequence[float]] = None,
        nominal_board_center_robot_m: Optional[Sequence[float]] = None,
        nominal_board_surface_z_m: Optional[float] = None,
        placement_version: int = 1,
    ) -> "BoardPlacementState":
        """
        Compute authoritative BoardPlacementState from forward shift d and vertical offset.
        d > 0 means board moves farther from robot along -X_robot.
        """
        d_m = float(forward_shift_mm) / 1000.0
        h_offset_m = float(board_height_offset_mm) / 1000.0

        if nominal_grid_origin_m is None or nominal_board_center_robot_m is None or nominal_board_surface_z_m is None:
            nom_cfg = load_nominal_scene_placement()
            if nominal_grid_origin_m is None:
                nominal_grid_origin_m = nom_cfg.get("grid_origin_in_robot_base_m", [-0.180, -0.160, 0.0105])
            if nominal_board_surface_z_m is None:
                nominal_board_surface_z_m = nom_cfg.get("board_surface_height_m", 0.0105)
            if nominal_board_center_robot_m is None:
                bc = nom_cfg.get("board_center_in_robot_base_m", [-0.360, 0.0, 0.0105])
                nominal_board_center_robot_m = [bc[0], bc[1], nominal_board_surface_z_m / 2.0]

        orig_x0, orig_y0, orig_z = nominal_grid_origin_m
        nom_cx, nom_cy, nom_cz = nominal_board_center_robot_m

        grid_origin_robot_m = [
            round(orig_x0 - d_m, 6),
            round(orig_y0, 6),
            round(orig_z + h_offset_m, 6),
        ]

        physical_board_center_robot_m = [
            round(nom_cx - d_m, 6),
            round(nom_cy, 6),
            round(nom_cz + h_offset_m, 6),
        ]

        board_surface_z_robot_m = round(nominal_board_surface_z_m + h_offset_m, 6)

        # Mapping to Three.js world:
        # world_x = -robot_y
        # world_y = +robot_z
        # world_z = -robot_x
        physical_board_center_world_m = [
            round(-physical_board_center_robot_m[1], 6),
            round(physical_board_center_robot_m[2], 6),
            round(-physical_board_center_robot_m[0], 6),
        ]

        board_visual_root_world_m = [
            round(-physical_board_center_robot_m[1], 6),
            round(board_surface_z_robot_m, 6),
            round(-physical_board_center_robot_m[0], 6),
        ]

        return cls(
            forward_shift_mm=float(forward_shift_mm),
            safe_transit_height_mm=float(safe_transit_height_mm),
            board_height_offset_mm=float(board_height_offset_mm),
            grid_origin_robot_m=grid_origin_robot_m,
            physical_board_center_robot_m=physical_board_center_robot_m,
            physical_board_center_world_m=physical_board_center_world_m,
            board_surface_z_robot_m=board_surface_z_robot_m,
            board_visual_root_world_m=board_visual_root_world_m,
            board_center_robot_m=physical_board_center_robot_m,
            board_center_world_m=board_visual_root_world_m,
            placement_version=int(placement_version),
            timestamp=time.time(),
        )


def canonical_cell_to_robot_xyz_m(
    row: int,
    col: int,
    forward_shift_mm: float = 0.0,
    z_m: float = 0.0105,
    nominal_x0: float = -0.180,
    nominal_y0: float = -0.160,
    row_spacing_m: float = 0.040,
    col_spacing_m: float = 0.040,
) -> Tuple[float, float, float]:
    """
    Single canonical cell coordinate formula:
    x(r, d) = -0.180 - d/1000 - r*0.040
    y(c)    = -0.160 + c*0.040
    z       = z_m
    """
    x = nominal_x0 - (forward_shift_mm / 1000.0) - float(row) * row_spacing_m
    y = nominal_y0 + float(col) * col_spacing_m
    z = float(z_m)
    return round(x, 6), round(y, 6), round(z, 6)


def find_nearest_cell(
    pos_robot_m: Sequence[float],
    grid_origin_robot_m: Sequence[float] = (-0.180, -0.160, 0.0105),
    row_spacing_m: float = 0.040,
    col_spacing_m: float = 0.040,
) -> Tuple[int, int]:
    """Map a 3D position in robot_base to nearest board grid (row, col)."""
    px, py = float(pos_robot_m[0]), float(pos_robot_m[1])
    x0, y0 = float(grid_origin_robot_m[0]), float(grid_origin_robot_m[1])
    row = int(round((x0 - px) / row_spacing_m))
    col = int(round((py - y0) / col_spacing_m))
    return max(0, min(9, row)), max(0, min(8, col))


class BoardPlacementAnalyzer:
    """
    Analytical and empirical analyzer for Xiangqi board placement feasibility and optimization.
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

        # Rough geometric reach precheck radius (mm)
        self.R_precheck_m = float(self.kinematics.MAX_REACH_RADIUS_M)
        self.R_precheck_mm = self.R_precheck_m * 1000.0

    def compute_geometric_precheck(
        self,
        forward_shift_mm: float,
        safe_transit_height_mm: float = 70.0,
        board_surface_mm: Optional[float] = None,
        placement_version: int = 1,
    ) -> Dict[str, Any]:
        """
        Derive pure analytical geometric feasibility precheck.
        """
        d = float(forward_shift_mm)
        H = float(safe_transit_height_mm)
        z_board = board_surface_mm if board_surface_mm is not None else self.board_surface_nominal_mm

        # Flange heights
        z_tcp_grasp = z_board + self.piece_height_mm / 2.0
        z_flange_grasp = z_tcp_grasp + self.tool_length_mm

        z_tcp_approach = z_board + H
        z_flange_approach = z_tcp_approach + self.tool_length_mm

        # Far corner (Row 9, lateral col 0 or 8: |Y_far| = 160mm)
        x_far_mag = 540.0 + d
        y_far_mag = 160.0

        # Scalar Euclidean distances from Robot Base origin to Flange
        d_far_grasp = math.sqrt(x_far_mag**2 + y_far_mag**2 + z_flange_grasp**2)
        d_far_approach = math.sqrt(x_far_mag**2 + y_far_mag**2 + z_flange_approach**2)

        # Analytic d_max for current H:
        # R^2 >= (540+d)^2 + 160^2 + z_flange_approach^2
        radicand_d = self.R_precheck_mm**2 - y_far_mag**2 - z_flange_approach**2
        if radicand_d >= 0:
            d_max_analytic = math.sqrt(radicand_d) - 540.0
        else:
            d_max_analytic = float("-inf")

        # Analytic H_max for current d:
        # R^2 >= (540+d)^2 + 160^2 + (z_board + H + L_tool)^2
        radicand_h = self.R_precheck_mm**2 - y_far_mag**2 - (540.0 + d)**2
        if radicand_h >= 0:
            h_max_analytic = math.sqrt(radicand_h) - z_board - self.tool_length_mm
        else:
            h_max_analytic = float("-inf")

        # Margins
        grasp_margin = self.R_precheck_mm - d_far_grasp
        approach_margin = self.R_precheck_mm - d_far_approach

        # Board distance metrics from robot base
        row0_center_dist = 180.0 + d
        far_row_center_dist = 540.0 + d
        board_center_dist = 360.0 + d
        near_board_edge_dist = 360.0 + d - (self.geom.outer_length_mm / 2.0)
        far_board_edge_dist = 360.0 + d + (self.geom.outer_length_mm / 2.0)

        # Status: Geometric precheck pass if approach distance <= R_precheck
        is_geometric_pass = (approach_margin >= 0.0) and (grasp_margin >= 0.0) and (d >= -20.0)

        return {
            "type": "placement_analysis",
            "forward_shift_mm": round(d, 2),
            "board_surface_z_mm": round(z_board, 2),
            "safe_transit_height_mm": round(H, 2),
            "row0_center_distance_mm": round(row0_center_dist, 2),
            "far_row_center_distance_mm": round(far_row_center_dist, 2),
            "board_center_distance_mm": round(board_center_dist, 2),
            "near_board_edge_distance_mm": round(near_board_edge_dist, 2),
            "far_board_edge_distance_mm": round(far_board_edge_dist, 2),
            "far_grasp_distance_mm": round(d_far_grasp, 2),
            "far_approach_distance_mm": round(d_far_approach, 2),
            "r_precheck_mm": round(self.R_precheck_mm, 2),
            "grasp_reach_margin_mm": round(grasp_margin, 2),
            "approach_reach_margin_mm": round(approach_margin, 2),
            "d_max_for_current_h_mm": round(d_max_analytic, 2) if math.isfinite(d_max_analytic) else None,
            "h_max_for_current_d_mm": round(h_max_analytic, 2) if math.isfinite(h_max_analytic) else None,
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
        cond_penalty = math.log(c_clamped)  # ~0 to 4.6

        score = (
            15.0 * manipulability +
            0.15 * joint_limit_margin_deg +
            0.10 * collision_clearance_mm +
            0.05 * reach_margin_mm -
            1.5 * cond_penalty
        )
        return float(score)
