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


@dataclass(frozen=True)
class BoardCell:
    """
    Authoritative canonical typed Xiangqi board cell representation.
    Order is strictly (row, col) where:
      row in [0, 9] (0 = Black home side, 9 = Red home side)
      col in [0, 8] (0 = Near side of robot, 8 = Far side of robot under +90 deg orientation)
    """
    row: int
    col: int

    def __post_init__(self):
        r = int(self.row)
        c = int(self.col)
        if not (0 <= r <= 9):
            raise ValueError(f"BoardCell row {r} out of valid Xiangqi bounds [0, 9]")
        if not (0 <= c <= 8):
            raise ValueError(f"BoardCell col {c} out of valid Xiangqi bounds [0, 8]")
        object.__setattr__(self, "row", r)
        object.__setattr__(self, "col", c)

    def to_tuple(self) -> Tuple[int, int]:
        return (self.row, self.col)

    def __iter__(self):
        yield self.row
        yield self.col

    def __getitem__(self, index: int) -> int:
        if index == 0:
            return self.row
        elif index == 1:
            return self.col
        raise IndexError(f"BoardCell index {index} out of range (must be 0 for row or 1 for col)")

    def __repr__(self) -> str:
        return f"BoardCell(row={self.row}, col={self.col})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, BoardCell):
            return self.row == other.row and self.col == other.col
        if isinstance(other, (tuple, list)) and len(other) == 2:
            return self.row == other[0] and self.col == other[1]
        return False


def rot_matrix_to_quat(R: np.ndarray) -> np.ndarray:
    """
    Convert a 3x3 orthonormal rotation matrix to quaternion [x, y, z, w].
    Uses a numerically stable branch selection based on trace and diagonals.
    """
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    q = np.array([x, y, z, w], dtype=float)
    n = np.linalg.norm(q)
    if n > 1e-12:
        q = q / n
    return q


DEFAULT_BOARD_YAW_DEG: float = 90.0


def compute_rotation_matrix(board_yaw_deg: float) -> np.ndarray:
    """
    Compute canonical 3x3 rotation matrix R_robot_from_board.

    Convention:
      yaw = 0.0 deg (legacy baseline):
        +u (column axis) -> +Y_robot
        +v (row axis)    -> -X_robot
        +z               -> +Z_robot
        R_0 = [[0.0, -1.0, 0.0],
               [1.0,  0.0, 0.0],
               [0.0,  0.0, 1.0]]

      yaw = +90.0 deg (production 90° orientation):
        R = R_z(+90) @ R_0 =
            [[-1.0,  0.0, 0.0],
             [ 0.0, -1.0, 0.0],
             [ 0.0,  0.0, 1.0]]
        +u (column axis) -> -X_robot
        +v (row axis)    -> -Y_robot
        +z               -> +Z_robot
    """
    theta = math.radians(board_yaw_deg)
    R_z = np.array([
        [math.cos(theta), -math.sin(theta), 0.0],
        [math.sin(theta), math.cos(theta), 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=float)
    R_0 = np.array([
        [0.0, -1.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=float)
    return R_z @ R_0


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
        "grid_origin_in_robot_base_m": [-0.20, 0.18, 0.0105],
        "board_center_in_robot_base_m": [-0.36, 0.0, 0.0105],
        "grid_origin_in_3d_world_m": [-0.18, 0.0105, 0.20],
        "board_center_in_3d_world_m": [0.0, 0.0105, 0.36],
        "board_surface_height_m": 0.0105,
    }


@dataclass
class BoardPlacementState:
    """
    Authoritative runtime state and spatial transform for Xiangqi board placement.
    Canonical relation:
        p_robot = T_robot_from_board @ p_board
        p_board = T_board_from_robot @ p_robot
    """
    forward_shift_mm: float = 0.0
    safe_transit_height_mm: float = 40.0
    board_height_offset_mm: float = 0.0
    board_yaw_deg: float = 90.0

    # Authoritative coordinates in robot base {B}
    board_center_robot_m: List[float] = field(default_factory=lambda: [-0.360, 0.0, 0.00525])
    board_surface_z_robot_m: float = 0.0105
    grid_origin_robot_m: List[float] = field(default_factory=lambda: [-0.200, 0.180, 0.0105])

    # 3D world representation
    physical_board_center_world_m: List[float] = field(default_factory=lambda: [0.0, 0.00525, 0.360])
    board_visual_root_world_m: List[float] = field(default_factory=lambda: [0.0, 0.0105, 0.360])

    # Backward compatible aliases
    physical_board_center_robot_m: List[float] = field(default_factory=lambda: [-0.360, 0.0, 0.00525])
    board_center_world_m: List[float] = field(default_factory=lambda: [0.0, 0.0105, 0.360])

    placement_version: int = 1
    timestamp: float = field(default_factory=time.time)

    @property
    def board_surface_z_m(self) -> float:
        return self.board_surface_z_robot_m

    @property
    def R_robot_from_board(self) -> np.ndarray:
        return compute_rotation_matrix(self.board_yaw_deg)

    @property
    def R_board_from_robot(self) -> np.ndarray:
        return self.R_robot_from_board.T

    @property
    def T_robot_from_board(self) -> np.ndarray:
        T = np.eye(4, dtype=float)
        T[:3, :3] = self.R_robot_from_board
        T[0, 3] = self.board_center_robot_m[0]
        T[1, 3] = self.board_center_robot_m[1]
        T[2, 3] = self.board_surface_z_robot_m
        return T

    @property
    def T_board_from_robot(self) -> np.ndarray:
        T = np.eye(4, dtype=float)
        R_inv = self.R_board_from_robot
        T[:3, :3] = R_inv
        p_surf = np.array([
            self.board_center_robot_m[0],
            self.board_center_robot_m[1],
            self.board_surface_z_robot_m,
        ], dtype=float)
        T[:3, 3] = -R_inv @ p_surf
        return T

    @property
    def quat_robot_from_board(self) -> List[float]:
        q = rot_matrix_to_quat(self.R_robot_from_board)
        return [float(v) for v in q]

    @property
    def quat_world(self) -> List[float]:
        R_w_from_b = np.array([[0.0, -1.0, 0.0], [0.0, 0.0, 1.0], [-1.0, 0.0, 0.0]], dtype=float)
        M_world = R_w_from_b @ self.R_robot_from_board
        q = rot_matrix_to_quat(M_world)
        return [float(v) for v in q]

    def cell_to_board_local(self, row: float, col: float) -> Tuple[float, float]:
        """
        Convert semantic Xiangqi grid (row, col) to board-local (u, v) in meters.
        u = (col - 4.0) * 0.040 m (column span: 320 mm, col 0 -> -160mm, col 8 -> +160mm)
        v = (row - 4.5) * 0.040 m (row span: 360 mm, row 0 -> -180mm, row 9 -> +180mm)
        """
        u_m = (float(col) - 4.0) * 0.040
        v_m = (float(row) - 4.5) * 0.040
        return u_m, v_m

    def board_local_to_cell(self, u_m: float, v_m: float) -> Tuple[float, float]:
        """
        Convert board-local (u, v) in meters back to continuous semantic (row, col).
        u = (col - 4.0) * 0.040 -> col = u / 0.040 + 4.0
        v = (row - 4.5) * 0.040 -> row = v / 0.040 + 4.5
        Returns:
            (row, col) in canonical Xiangqi order.
        """
        col = float(u_m) / 0.040 + 4.0
        row = float(v_m) / 0.040 + 4.5
        return row, col

    def board_local_to_robot(
        self, u_m: float, v_m: float, z_rel_m: float = 0.0
    ) -> np.ndarray:
        """
        Transform a board-local point [u, v, z_rel] to robot base coordinates {B}.
        z_rel is relative to the board playing surface (z_rel=0 is surface).
        p_robot = p_surface_center + R_robot_from_board @ [u, v, z_rel]
        """
        p_board = np.array([float(u_m), float(v_m), float(z_rel_m)], dtype=float)
        p_center = np.array([
            float(self.board_center_robot_m[0]),
            float(self.board_center_robot_m[1]),
            float(self.board_surface_z_robot_m),
        ], dtype=float)
        return p_center + self.R_robot_from_board @ p_board

    def robot_to_board_local(
        self, pos_robot_m: Sequence[float]
    ) -> np.ndarray:
        """
        Transform a robot base 3D point to board-local coordinates [u, v, z_rel].
        [u, v, z_rel] = R_board_from_robot @ (pos_robot_m - p_surface_center)
        """
        p_robot = np.array(pos_robot_m[:3], dtype=float)
        p_center = np.array([
            float(self.board_center_robot_m[0]),
            float(self.board_center_robot_m[1]),
            float(self.board_surface_z_robot_m),
        ], dtype=float)
        return self.R_board_from_robot @ (p_robot - p_center)

    def cell_to_robot_xyz(
        self, row: float, col: float, z_rel_m: float = 0.0
    ) -> np.ndarray:
        """
        Map semantic grid cell (row, col) directly to robot base coordinates {B}.
        """
        u_m, v_m = self.cell_to_board_local(row, col)
        return self.board_local_to_robot(u_m, v_m, z_rel_m=z_rel_m)

    def robot_xyz_to_nearest_cell(
        self, pos_robot_m: Sequence[float]
    ) -> Tuple[int, int, float]:
        """
        Map a 3D position in robot base {B} to nearest valid board intersection.
        Returns:
            (nearest_row, nearest_col, dist_m) in canonical Xiangqi order.
        """
        p_local = self.robot_to_board_local(pos_robot_m)
        r_float, c_float = self.board_local_to_cell(p_local[0], p_local[1])
        nearest_r = max(0, min(9, int(round(r_float))))
        nearest_c = max(0, min(8, int(round(c_float))))
        p_target = self.cell_to_robot_xyz(nearest_r, nearest_c, z_rel_m=0.0)
        dx = float(pos_robot_m[0]) - float(p_target[0])
        dy = float(pos_robot_m[1]) - float(p_target[1])
        dist_m = math.hypot(dx, dy)
        return nearest_r, nearest_c, dist_m

    def is_in_bounds_board_local(
        self, u_m: float, v_m: float, xy_margin_m: float = 0.0
    ) -> bool:
        """
        Check whether board-local coordinates (u, v) lie within canonical board physical extents:
        width = 367 mm (half_w = 183.5 mm along u)
        length = 410 mm (half_l = 205.0 mm along v)
        """
        half_w = 0.367 / 2.0 + float(xy_margin_m)
        half_l = 0.410 / 2.0 + float(xy_margin_m)
        return (abs(float(u_m)) <= half_w) and (abs(float(v_m)) <= half_l)

    def is_in_bounds_robot(
        self, pos_robot_m: Sequence[float], xy_margin_m: float = 0.0
    ) -> bool:
        """Check whether robot base position lies within board physical extents."""
        p_local = self.robot_to_board_local(pos_robot_m)
        return self.is_in_bounds_board_local(p_local[0], p_local[1], xy_margin_m=xy_margin_m)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "board_placement",
            "forward_shift_mm": round(self.forward_shift_mm, 2),
            "safe_transit_height_mm": round(self.safe_transit_height_mm, 2),
            "board_height_offset_mm": round(self.board_height_offset_mm, 2),
            "board_yaw_deg": round(self.board_yaw_deg, 2),
            "grid_origin_robot_m": [round(v, 5) for v in self.grid_origin_robot_m],
            "physical_board_center_robot_m": [round(v, 5) for v in self.physical_board_center_robot_m],
            "physical_board_center_world_m": [round(v, 5) for v in self.physical_board_center_world_m],
            "board_surface_z_robot_m": round(self.board_surface_z_robot_m, 5),
            "board_surface_z_m": round(self.board_surface_z_robot_m, 5),
            "board_visual_root_world_m": [round(v, 5) for v in self.board_visual_root_world_m],
            "board_center_robot_m": [round(v, 5) for v in self.board_center_robot_m],
            "board_center_world_m": [round(v, 5) for v in self.board_center_world_m],
            "quat_robot_from_board": [round(v, 5) for v in self.quat_robot_from_board],
            "quat_world": [round(v, 5) for v in self.quat_world],
            "T_robot_from_board": [[round(float(v), 5) for v in row] for row in self.T_robot_from_board.tolist()],
            "placement_version": self.placement_version,
            "timestamp": self.timestamp,
        }

    to_telemetry_dict = to_dict

    @classmethod
    def compute(
        cls,
        forward_shift_mm: float,
        safe_transit_height_mm: float = 40.0,
        board_height_offset_mm: float = 0.0,
        board_yaw_deg: float = 90.0,
        nominal_board_center_robot_m: Optional[Sequence[float]] = None,
        nominal_board_surface_z_m: Optional[float] = None,
        placement_version: int = 1,
        **kwargs,
    ) -> "BoardPlacementState":
        d_m = float(forward_shift_mm) / 1000.0
        h_offset_m = float(board_height_offset_mm) / 1000.0
        yaw_deg = float(board_yaw_deg)

        if nominal_board_center_robot_m is None or nominal_board_surface_z_m is None:
            nom_cfg = load_nominal_scene_placement()
            if nominal_board_surface_z_m is None:
                nominal_board_surface_z_m = nom_cfg.get("board_surface_height_m", 0.0105)
            if nominal_board_center_robot_m is None:
                bc = nom_cfg.get("board_center_in_robot_base_m", [-0.360, 0.0, 0.0105])
                nominal_board_center_robot_m = [bc[0], bc[1], nominal_board_surface_z_m / 2.0]

        nom_cx, nom_cy, _ = nominal_board_center_robot_m
        nom_surface_z = float(nominal_board_surface_z_m)
        thickness_m = 0.0105  # canonical 10.5 mm

        # Board center translates along -X_robot with forward shift d
        center_x = round(nom_cx - d_m, 6)
        center_y = round(nom_cy, 6)
        surface_z = round(nom_surface_z + h_offset_m, 6)
        box_center_z = round(surface_z - thickness_m / 2.0, 6)

        board_center_robot_m = [center_x, center_y, box_center_z]

        physical_board_center_world_m = [
            round(-center_y, 6),
            round(box_center_z, 6),
            round(-center_x, 6),
        ]
        board_visual_root_world_m = [
            round(-center_y, 6),
            round(surface_z, 6),
            round(-center_x, 6),
        ]

        instance = cls(
            forward_shift_mm=float(forward_shift_mm),
            safe_transit_height_mm=float(safe_transit_height_mm),
            board_height_offset_mm=float(board_height_offset_mm),
            board_yaw_deg=yaw_deg,
            board_center_robot_m=board_center_robot_m,
            board_surface_z_robot_m=surface_z,
            physical_board_center_robot_m=board_center_robot_m,
            physical_board_center_world_m=physical_board_center_world_m,
            board_visual_root_world_m=board_visual_root_world_m,
            board_center_world_m=board_visual_root_world_m,
            placement_version=int(placement_version),
            timestamp=time.time(),
        )
        p_c00 = instance.cell_to_robot_xyz(0, 0, z_rel_m=0.0)
        instance.grid_origin_robot_m = [round(float(v), 6) for v in p_c00]
        return instance


def canonical_cell_to_robot_xyz_m(
    row: int,
    col: int,
    forward_shift_mm: float = 0.0,
    z_m: float = 0.0105,
    nominal_x0: Optional[float] = None,
    nominal_y0: Optional[float] = None,
    row_spacing_m: float = 0.040,
    col_spacing_m: float = 0.040,
    board_yaw_deg: float = 90.0,
) -> Tuple[float, float, float]:
    """
    Authoritative cell coordinate mapping using BoardPlacementState.
    """
    state = BoardPlacementState.compute(
        forward_shift_mm=forward_shift_mm,
        board_yaw_deg=board_yaw_deg,
    )
    p = state.cell_to_robot_xyz(row, col, z_rel_m=float(z_m) - state.board_surface_z_robot_m)
    return round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6)


def find_nearest_cell(
    pos_robot_m: Sequence[float],
    grid_origin_robot_m: Optional[Sequence[float]] = None,
    row_spacing_m: float = 0.040,
    col_spacing_m: float = 0.040,
    forward_shift_mm: float = 0.0,
    board_yaw_deg: float = 90.0,
) -> Tuple[int, int]:
    """Map a 3D position in robot_base to nearest board grid (row, col)."""
    fwd = float(forward_shift_mm)
    if grid_origin_robot_m is not None and abs(fwd) < 1e-6:
        # Inferred forward shift: x0 = -0.200 - fwd_m -> fwd_m = -0.200 - x0
        fwd = (-0.200 - float(grid_origin_robot_m[0])) * 1000.0
    state = BoardPlacementState.compute(
        forward_shift_mm=fwd,
        board_yaw_deg=board_yaw_deg,
    )
    r, c, _ = state.robot_xyz_to_nearest_cell(pos_robot_m)
    return r, c


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
