"""
Authoritative Virtual Physical World implemented with PyBullet (DIRECT mode).

Simulates:
- Finite static Xiangqi board collider
- 32 rigid-body Xiangqi piece cylinders
- Gravity, collisions, friction, restitution, and physical settling
- Procedural kinematic gripper with geometric grasp and deterministic attachment
- Dynamic release and force-drop with velocity inheritance
- Out-of-bounds detection and immutable world state snapshots
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pybullet as p

from src.domain.geometry import get_physical_geometry
from src.simulation.physics.gripper import VirtualGripper
from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.state import (
    GraspResult,
    GraspStatus,
    PiecePhysicalState,
    WorldStateSnapshot,
)
from src.simulation.physics.transforms import (
    continuous_board_coord,
    nearest_intersection_metrics,
    quat_to_rot_matrix,
    tilt_angle_deg,
)
from src.simulation.physics.validation import (
    validate_physics_config,
    validate_start_layout,
)


@dataclass
class SweptVolumeReport:
    is_safe: bool
    reason: Optional[str]
    minimum_clearance_mm: float
    first_blocking_step: Optional[int]
    total_steps: int
    blocking_body: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "reason": self.reason,
            "minimum_clearance_mm": round(self.minimum_clearance_mm, 2),
            "first_blocking_step": self.first_blocking_step,
            "total_steps": self.total_steps,
            "blocking_body": self.blocking_body,
        }


class SweptVolumeResult(tuple):
    def __new__(cls, is_safe: bool, reason: Optional[str], report: Optional[SweptVolumeReport] = None):
        inst = super().__new__(cls, (is_safe, reason))
        inst._report = report
        return inst

    @property
    def is_safe(self) -> bool:
        return self[0]

    @property
    def reason(self) -> Optional[str]:
        return self[1]

    @property
    def minimum_clearance_mm(self) -> float:
        return self._report.minimum_clearance_mm if getattr(self, "_report", None) else float("inf")

    @property
    def first_blocking_step(self) -> Optional[int]:
        return self._report.first_blocking_step if getattr(self, "_report", None) else None

    @property
    def blocking_body(self) -> Optional[str]:
        return self._report.blocking_body if getattr(self, "_report", None) else None

    @property
    def details(self) -> Dict[str, Any]:
        return self._report.to_dict() if getattr(self, "_report", None) else {}


class VirtualPhysicalWorld:
    """
    Headless PyBullet rigid-body world for Virtual FAIRINO FR3 Xiangqi simulation.
    Operates strictly in the robot_base frame (Z-up, -X facing board, +Y lateral).
    """

    def __init__(
        self,
        physics_config_path: Optional[Union[str, Path]] = None,
        scene_config_path: Optional[Union[str, Path]] = None,
        gripper_profile_path: Optional[Union[str, Path]] = None,
        start_layout_path: Optional[Union[str, Path]] = None,
        enable_gui: bool = False,
    ):
        shared_dir = Path(__file__).resolve().parent.parent.parent.parent / "shared"
        self.physics_config_path = Path(physics_config_path or (shared_dir / "virtual_physics.json"))
        self.scene_config_path = Path(scene_config_path or (shared_dir / "virtual_fr3_scene.json"))
        self.gripper_profile_path = Path(gripper_profile_path or (shared_dir / "virtual_gripper_profile.json"))
        self.start_layout_path = Path(start_layout_path or (shared_dir / "xiangqi_start_layout.json"))

        # Load configurations
        with open(self.physics_config_path, "r", encoding="utf-8-sig") as f:
            self.physics_cfg = json.load(f)

        with open(self.scene_config_path, "r", encoding="utf-8-sig") as f:
            self.scene_cfg = json.load(f)

        with open(self.start_layout_path, "r", encoding="utf-8-sig") as f:
            self.layout_cfg = json.load(f)

        # Strict fail-fast validation before creating PyBullet client
        validate_physics_config(self.physics_cfg)
        validate_start_layout(self.layout_cfg)

        self.geom = get_physical_geometry()
        self.board_cfg = self.scene_cfg["virtual_board_placement"]

        self.client_id = -1
        try:
            # Physics client initialization
            connection_mode = p.GUI if enable_gui else p.DIRECT
            self.client_id = p.connect(connection_mode)
            if self.client_id < 0:
                raise RuntimeError(f"Failed to connect to PyBullet in mode {connection_mode}")

            # Set environment parameters
            gravity = self.physics_cfg["gravity_m_s2"]
            p.setGravity(gravity[0], gravity[1], gravity[2], physicsClientId=self.client_id)

            self.timestep_s = float(self.physics_cfg["fixed_timestep_s"])
            p.setTimeStep(self.timestep_s, physicsClientId=self.client_id)

            iterations = int(self.physics_cfg["solver_iterations"])
            p.setPhysicsEngineParameter(
                numSolverIterations=iterations,
                physicsClientId=self.client_id,
            )

            self.sim_time = 0.0
            self.board_body_id = -1
            self.pieces: Dict[str, XiangqiPieceBody] = {}

            # Settle thresholds
            settle_cfg = self.physics_cfg["settling"]
            self.max_settle_steps = int(settle_cfg["max_settle_steps"])
            self.lin_vel_thresh = float(settle_cfg["linear_velocity_threshold_m_s"])
            self.ang_vel_thresh = float(settle_cfg["angular_velocity_threshold_rad_s"])
            self.required_settled_steps = int(settle_cfg["consecutive_settled_steps"])

            # Out of bounds config
            oob_cfg = self.physics_cfg["out_of_bounds"]
            self.z_min_oob = float(oob_cfg["z_min_m"])
            self.xy_margin_oob = float(oob_cfg["xy_boundary_margin_m"])

            # Build world
            self._spawn_board()
            self._spawn_pieces()

            self._physics_lock = threading.RLock()

            # Gripper proxy and PyBullet collision bodies
            self.gripper = VirtualGripper(profile_path=self.gripper_profile_path)
            self._spawn_gripper_proxies()

            # Full articulated FR3 robot for collision queries
            self.robot_body_id = -1
            self._spawn_robot()
        except Exception:
            if self.client_id >= 0:
                try:
                    p.disconnect(physicsClientId=self.client_id)
                except Exception:
                    pass
                self.client_id = -1
            raise

    def _spawn_gripper_proxies(self) -> None:
        """Spawn PyBullet collision representations for gripper if supported."""
        if hasattr(self.gripper, "spawn_proxies"):
            self.gripper.spawn_proxies(self.client_id)

    def _spawn_robot(self) -> None:
        """Spawn full articulated FAIRINO FR3 URDF for collision queries in PyBullet."""
        from src.simulation.physics.urdf_resolver import get_simulation_ready_fr3_urdf
        urdf_path = get_simulation_ready_fr3_urdf()
        self.robot_body_id = p.loadURDF(
            str(urdf_path.resolve()),
            basePosition=[0.0, 0.0, 0.0],
            baseOrientation=[0.0, 0.0, 0.0, 1.0],
            useFixedBase=True,
            flags=p.URDF_USE_SELF_COLLISION,
            physicsClientId=self.client_id,
        )

        # Initialize robot to scene home pose and hold joints with position control
        home_deg = self.scene_cfg.get("home_pose", {}).get("joints_deg", [0.0, -45.0, 90.0, -45.0, -90.0, 0.0])
        home_rad = np.deg2rad(home_deg)
        self.sync_robot_runtime_configuration(home_rad)

    def sync_robot_collision_configuration(self, joints_rad: Sequence[float]) -> None:
        """
        Side-effect-free mirror of robot joint configuration into PyBullet FR3 model for collision checks only.
        Updates gripper collision proxies without mutating runtime TCP pose, history, or attached pieces.
        """
        if self.robot_body_id < 0 or self.client_id < 0:
            return
        with self._physics_lock:
            for j_idx in range(min(6, len(joints_rad))):
                target_pos = float(joints_rad[j_idx])
                p.resetJointState(self.robot_body_id, j_idx, target_pos, targetVelocity=0.0, physicsClientId=self.client_id)

            # Flange link 5 (wrist3_link)
            link_state = p.getLinkState(self.robot_body_id, 5, computeForwardKinematics=True, physicsClientId=self.client_id)
            flange_pos = np.array(link_state[4], dtype=float)
            flange_quat = np.array(link_state[5], dtype=float)

            R_flange = quat_to_rot_matrix(flange_quat)
            tool_cfg = self.scene_cfg.get("tool_transform", {})
            tool_offset = np.array(tool_cfg.get("flange_to_tcp_xyz_m", [0.0, 0.0, 0.218]), dtype=float)
            p_tcp = flange_pos + R_flange @ tool_offset
            self.gripper.set_collision_proxy_pose(p_tcp, flange_quat)

    def sync_robot_runtime_configuration(self, joints_rad: Sequence[float]) -> None:
        """
        Authoritative runtime mirror of robot joint configuration into PyBullet FR3 model.
        Updates PyBullet motors, authoritative gripper TCP pose, history, and attached piece transforms.
        """
        if self.robot_body_id < 0 or self.client_id < 0:
            return
        with self._physics_lock:
            for j_idx in range(min(6, len(joints_rad))):
                target_pos = float(joints_rad[j_idx])
                p.resetJointState(self.robot_body_id, j_idx, target_pos, targetVelocity=0.0, physicsClientId=self.client_id)
                p.setJointMotorControl2(
                    self.robot_body_id,
                    j_idx,
                    p.POSITION_CONTROL,
                    targetPosition=target_pos,
                    force=500.0,
                    physicsClientId=self.client_id,
                )

            # Flange link 5 (wrist3_link)
            link_state = p.getLinkState(self.robot_body_id, 5, computeForwardKinematics=True, physicsClientId=self.client_id)
            flange_pos = np.array(link_state[4], dtype=float)
            flange_quat = np.array(link_state[5], dtype=float)

            R_flange = quat_to_rot_matrix(flange_quat)
            tool_cfg = self.scene_cfg.get("tool_transform", {})
            tool_offset = np.array(tool_cfg.get("flange_to_tcp_xyz_m", [0.0, 0.0, 0.218]), dtype=float)
            p_tcp = flange_pos + R_flange @ tool_offset
            self.gripper.set_tcp_pose(p_tcp, flange_quat)

    def sync_robot_configuration(self, joints_rad: Sequence[float]) -> None:
        """Backwards-compatible alias for authoritative runtime synchronization."""
        self.sync_robot_runtime_configuration(joints_rad)

    def get_robot_joint_positions(self) -> List[float]:
        """Get current 6 joint angles of FR3 robot in PyBullet (in radians)."""
        if self.robot_body_id < 0 or self.client_id < 0:
            return []
        with self._physics_lock:
            return [float(p.getJointState(self.robot_body_id, j, physicsClientId=self.client_id)[0]) for j in range(6)]

    def _spawn_board(self) -> None:
        """Create finite static board box collider."""
        board_physics = self.physics_cfg.get("board", {})
        # Canonical board thickness strictly derived from shared/physical_geometry.json (0.0105m)
        thickness_m = self.geom.thickness_mm / 1000.0

        # Dimensions from canonical physical geometry
        outer_length_m = self.geom.outer_length_mm / 1000.0  # Along X in robot_base (410 mm)
        outer_width_m = self.geom.outer_width_mm / 1000.0    # Along Y in robot_base (367 mm)

        half_x = outer_length_m / 2.0
        half_y = outer_width_m / 2.0
        half_z = thickness_m / 2.0

        board_center = self.board_cfg["board_center_in_robot_base_m"]
        surface_height = float(self.board_cfg.get("board_surface_height_m", 0.0105))

        # Box center is placed such that its top surface is at surface_height
        box_center = [board_center[0], board_center[1], surface_height - half_z]

        col_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[half_x, half_y, half_z],
            physicsClientId=self.client_id,
        )

        self.board_body_id = p.createMultiBody(
            baseMass=0.0,  # Static body
            baseCollisionShapeIndex=col_shape,
            basePosition=box_center,
            physicsClientId=self.client_id,
        )

        lat_friction = float(board_physics.get("lateral_friction", 0.6))
        spin_friction = float(board_physics.get("spinning_friction", 0.005))
        restitution = float(board_physics.get("restitution", 0.05))

        p.changeDynamics(
            self.board_body_id,
            -1,
            lateralFriction=lat_friction,
            spinningFriction=spin_friction,
            restitution=restitution,
            physicsClientId=self.client_id,
        )

        # Store board bounding box for out-of-bounds check
        self._nominal_board_center = list(board_center)
        self._nominal_surface_height = surface_height
        self._board_half_x = half_x
        self._board_half_y = half_y
        self._board_half_z = half_z
        self.current_forward_shift_m = 0.0
        self.current_height_offset_m = 0.0

        self.board_x_min = board_center[0] - half_x
        self.board_x_max = board_center[0] + half_x
        self.board_y_min = board_center[1] - half_y
        self.board_y_max = board_center[1] + half_y
        self.board_surface_z = surface_height

    def relocate_board(self, forward_shift_m: float, height_offset_m: float = 0.0) -> bool:
        """
        Reposition PyBullet board collider and consistently translate all pieces ON_BOARD.
        d > 0 means board moves farther from robot along -X_robot.
        """
        shift_m = float(forward_shift_m)
        h_off_m = float(height_offset_m)

        # Delta translation from current placement
        delta_x = -(shift_m - self.current_forward_shift_m)
        delta_y = 0.0
        delta_z = h_off_m - self.current_height_offset_m
        delta = np.array([delta_x, delta_y, delta_z], dtype=float)

        # New board center and surface Z
        new_cx = self._nominal_board_center[0] - shift_m
        new_cy = self._nominal_board_center[1]
        new_surface_z = self._nominal_surface_height + h_off_m
        new_box_cz = new_surface_z - self._board_half_z

        if self.board_body_id >= 0 and self.client_id >= 0:
            p.resetBasePositionAndOrientation(
                self.board_body_id,
                [new_cx, new_cy, new_box_cz],
                [0.0, 0.0, 0.0, 1.0],
                physicsClientId=self.client_id,
            )

        self.board_x_min = new_cx - self._board_half_x
        self.board_x_max = new_cx + self._board_half_x
        self.board_y_min = new_cy - self._board_half_y
        self.board_y_max = new_cy + self._board_half_y
        self.board_surface_z = new_surface_z

        # Relocate resting/on-board pieces
        nom_origin = self.board_cfg.get("grid_origin_in_robot_base_m", [-0.180, -0.160, 0.0105])
        new_origin = (nom_origin[0] - shift_m, nom_origin[1], new_surface_z)

        for p_body in self.pieces.values():
            if p_body.physical_state in (PiecePhysicalState.ON_BOARD, PiecePhysicalState.RESTING):
                pos, orn = p_body.get_pose_robot_base()
                new_pos = pos + delta
                p_body.set_pose_robot_base(new_pos, orn)
                p_body.grid_origin_robot = new_origin

        self.current_forward_shift_m = shift_m
        self.current_height_offset_m = h_off_m
        return True

    def get_board_pose(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (position, quaternion) of board body in PyBullet base frame."""
        if self.board_body_id >= 0 and self.client_id >= 0:
            pos, orn = p.getBasePositionAndOrientation(self.board_body_id, physicsClientId=self.client_id)
            return np.array(pos), np.array(orn)
        return np.array([self._nominal_board_center[0] - self.current_forward_shift_m, self._nominal_board_center[1], self.board_surface_z - self._board_half_z]), np.array([0.0, 0.0, 0.0, 1.0])

    def get_board_to_robot_clearance(self, query_dist: float = 1.0) -> Tuple[float, str]:
        """
        Measure current minimum physical distance from board to moving robot links and gripper.
        Returns: (min_clearance_m, closest_body_or_link_name).
        """
        if self.board_body_id < 0 or self.client_id < 0:
            return float("inf"), "none"

        with self._physics_lock:
            min_dist = float("inf")
            closest_name = "none"

            # Check robot moving links (link 0 to 6; link -1 is fixed base mount)
            if self.robot_body_id >= 0:
                contacts = p.getClosestPoints(
                    self.board_body_id,
                    self.robot_body_id,
                    distance=query_dist,
                    physicsClientId=self.client_id,
                )
                for pt in contacts:
                    link_idx = int(pt[4])
                    if link_idx >= 0:  # Moving links only
                        d = float(pt[8])
                        if d < min_dist:
                            min_dist = d
                            closest_name = f"robot_link_{link_idx}"

            # Check gripper proxies
            for proxy_id in self.gripper.proxy_body_ids:
                contacts = p.getClosestPoints(
                    self.board_body_id,
                    proxy_id,
                    distance=query_dist,
                    physicsClientId=self.client_id,
                )
                for pt in contacts:
                    d = float(pt[8])
                    if d < min_dist:
                        min_dist = d
                        closest_name = f"gripper_proxy_{proxy_id}"

            return min_dist, closest_name

    def check_service_exclusion_occupancy(
        self,
        board_center_xy: Sequence[float],
        board_surface_z: float,
        half_length_m: float,
        half_width_m: float,
        board_thickness_m: float,
        piece_height_m: float,
        xy_margin_m: float = 0.030,
        vertical_clearance_m: float = 0.050,
    ) -> Dict[str, Any]:
        """
        Evaluate full physical occupancy of the board service exclusion volume
        against moving robot links (0..5) and gripper proxies using PyBullet collision detection.
        No permanent side-effects; cleans up temporary collision body in finally block.
        """
        if self.client_id < 0 or self.robot_body_id < 0:
            return {
                "link_inside": False,
                "gripper_inside": False,
                "intruding_links": [],
                "intruding_proxies": [],
                "min_moving_link_dist_m": float("inf"),
                "min_gripper_proxy_dist_m": float("inf"),
            }

        with self._physics_lock:
            hx = float(half_length_m) + float(xy_margin_m)
            hy = float(half_width_m) + float(xy_margin_m)
            hz = (float(board_thickness_m) + float(piece_height_m) + float(vertical_clearance_m) + float(xy_margin_m)) / 2.0
            box_cz = float(board_surface_z) + float(piece_height_m) + float(vertical_clearance_m) - hz
            cx = float(board_center_xy[0])
            cy = float(board_center_xy[1])

            col_shape = p.createCollisionShape(
                p.GEOM_BOX,
                halfExtents=[hx, hy, hz],
                physicsClientId=self.client_id,
            )
            body_id = p.createMultiBody(
                baseMass=0,
                baseCollisionShapeIndex=col_shape,
                basePosition=[cx, cy, box_cz],
                physicsClientId=self.client_id,
            )

            link_inside = False
            gripper_inside = False
            intruding_links = []
            intruding_proxies = []
            min_moving_link_dist = float("inf")
            min_gripper_proxy_dist = float("inf")

            try:
                # 1. Query robot moving links (link 0 to 5)
                pts = p.getClosestPoints(
                    body_id,
                    self.robot_body_id,
                    distance=0.5,
                    physicsClientId=self.client_id,
                )
                for pt in pts:
                    link_idx = int(pt[4])
                    if link_idx >= 0:  # moving link
                        dist = float(pt[8])
                        if dist < min_moving_link_dist:
                            min_moving_link_dist = dist
                        if dist <= 0.0:
                            link_inside = True
                            if link_idx not in intruding_links:
                                intruding_links.append(link_idx)

                # 2. Query gripper proxies
                for proxy_id in self.gripper.proxy_body_ids:
                    pts_g = p.getClosestPoints(
                        body_id,
                        proxy_id,
                        distance=0.5,
                        physicsClientId=self.client_id,
                    )
                    for pt in pts_g:
                        dist = float(pt[8])
                        if dist < min_gripper_proxy_dist:
                            min_gripper_proxy_dist = dist
                        if dist <= 0.0:
                            gripper_inside = True
                            if proxy_id not in intruding_proxies:
                                intruding_proxies.append(proxy_id)
            finally:
                p.removeBody(body_id, physicsClientId=self.client_id)

            return {
                "link_inside": link_inside,
                "gripper_inside": gripper_inside,
                "intruding_links": intruding_links,
                "intruding_proxies": intruding_proxies,
                "min_moving_link_dist_m": min_moving_link_dist,
                "min_gripper_proxy_dist_m": min_gripper_proxy_dist,
            }

    def check_board_swept_volume_collision(
        self,
        new_forward_shift_m: float,
        new_height_offset_m: float = 0.0,
        step_size_m: float = 0.005,
        clearance_margin_m: float = 0.005,
    ) -> SweptVolumeResult:
        """
        Check whether moving the board from current placement to (new_forward_shift_m, new_height_offset_m)
        would collide along the interpolated swept volume against the robot arm or gripper proxies.
        Guarantees clearance >= clearance_margin_m (default: 5.0 mm).
        Returns SweptVolumeResult(is_safe, collision_reason, report) backwards-compatible with (bool, str).
        """
        if self.board_body_id < 0 or self.client_id < 0:
            rep = SweptVolumeReport(True, None, float("inf"), None, 0, None)
            return SweptVolumeResult(True, None, rep)

        with self._physics_lock:
            shift_old = self.current_forward_shift_m
            h_old = self.current_height_offset_m
            shift_new = float(new_forward_shift_m)
            h_new = float(new_height_offset_m)

            dist = math.hypot(shift_new - shift_old, h_new - h_old)
            num_steps = max(2, int(math.ceil(dist / step_size_m)) + 1)

            orig_pos, orig_orn = p.getBasePositionAndOrientation(self.board_body_id, physicsClientId=self.client_id)
            query_dist = max(0.05, clearance_margin_m + 0.01)

            min_clearance_m = float("inf")
            blocking_body = None
            first_blocking_step = None
            collision_reason = None

            try:
                for step_idx in range(num_steps):
                    alpha = step_idx / (num_steps - 1) if num_steps > 1 else 1.0
                    s = (1.0 - alpha) * shift_old + alpha * shift_new
                    h = (1.0 - alpha) * h_old + alpha * h_new

                    cx = self._nominal_board_center[0] - s
                    cy = self._nominal_board_center[1]
                    cz = (self._nominal_surface_height + h) - self._board_half_z

                    p.resetBasePositionAndOrientation(
                        self.board_body_id,
                        [cx, cy, cz],
                        [0.0, 0.0, 0.0, 1.0],
                        physicsClientId=self.client_id,
                    )

                    # 1. Check collision against articulated FR3 robot links
                    if self.robot_body_id >= 0:
                        contacts = p.getClosestPoints(
                            self.board_body_id,
                            self.robot_body_id,
                            distance=query_dist,
                            physicsClientId=self.client_id,
                        )
                        for pt in contacts:
                            contact_dist = float(pt[8])
                            link_idx = int(pt[4])
                            if contact_dist < min_clearance_m:
                                min_clearance_m = contact_dist
                            if contact_dist <= clearance_margin_m and collision_reason is None:
                                first_blocking_step = step_idx
                                blocking_body = f"robot_link_{link_idx}"
                                collision_reason = (
                                    f"Board swept volume collides with robot link {link_idx} "
                                    f"at step {step_idx}/{num_steps} (clearance={contact_dist*1000.0:.2f}mm <= margin {clearance_margin_m*1000.0:.2f}mm)"
                                )

                    # 2. Check collision against gripper proxy bodies
                    for proxy_id in self.gripper.proxy_body_ids:
                        contacts = p.getClosestPoints(
                            self.board_body_id,
                            proxy_id,
                            distance=query_dist,
                            physicsClientId=self.client_id,
                        )
                        for pt in contacts:
                            contact_dist = float(pt[8])
                            if contact_dist < min_clearance_m:
                                min_clearance_m = contact_dist
                            if contact_dist <= clearance_margin_m and collision_reason is None:
                                first_blocking_step = step_idx
                                blocking_body = f"gripper_proxy_{proxy_id}"
                                collision_reason = (
                                    f"Board swept volume collides with gripper proxy at step {step_idx}/{num_steps} "
                                    f"(clearance={contact_dist*1000.0:.2f}mm <= margin {clearance_margin_m*1000.0:.2f}mm)"
                                )

                    if collision_reason is not None:
                        break

                is_safe = (collision_reason is None)
                rep = SweptVolumeReport(
                    is_safe=is_safe,
                    reason=collision_reason,
                    minimum_clearance_mm=min_clearance_m * 1000.0 if math.isfinite(min_clearance_m) else 999.0,
                    first_blocking_step=first_blocking_step,
                    total_steps=num_steps,
                    blocking_body=blocking_body,
                )
                return SweptVolumeResult(is_safe, collision_reason, rep)
            finally:
                p.resetBasePositionAndOrientation(
                    self.board_body_id,
                    orig_pos,
                    orig_orn,
                    physicsClientId=self.client_id,
                )

    def _spawn_pieces(self) -> None:
        """Spawn 32 Xiangqi pieces as cylinder rigid bodies at initial intersections."""
        piece_physics = self.physics_cfg.get("piece", {})
        mass_kg = float(piece_physics.get("mass_kg", 0.020))
        lat_fric = float(piece_physics.get("lateral_friction", 0.5))
        roll_fric = float(piece_physics.get("rolling_friction", 0.001))
        spin_fric = float(piece_physics.get("spinning_friction", 0.001))
        restitution = float(piece_physics.get("restitution", 0.05))

        radius_m = (self.geom.piece_diameter_mm / 2.0) / 1000.0  # 11.25 mm
        height_m = self.geom.piece_height_mm / 1000.0            # 9.43 mm

        grid_origin = self.board_cfg["grid_origin_in_robot_base_m"]
        x0, y0, z0 = grid_origin
        col_spacing_m = self.geom.grid_cell_width_mm / 1000.0
        row_spacing_m = self.geom.grid_cell_length_mm / 1000.0

        col_shape = p.createCollisionShape(
            p.GEOM_CYLINDER,
            radius=radius_m,
            height=height_m,
            physicsClientId=self.client_id,
        )

        for p_info in self.layout_cfg.get("pieces", []):
            piece_id = p_info["id"]
            side = p_info["side"]
            p_type = p_info["type"]
            c = int(p_info["col"])
            r = int(p_info["row"])

            # Position on board grid:
            # Row r along -X, Col c along +Y
            x = x0 - r * row_spacing_m
            y = y0 + c * col_spacing_m
            # Spawn slightly above board surface for safe contact settling (1.0 mm clearance)
            z = z0 + (height_m / 2.0) + 0.001

            body_id = p.createMultiBody(
                baseMass=mass_kg,
                baseCollisionShapeIndex=col_shape,
                basePosition=[x, y, z],
                baseOrientation=[0.0, 0.0, 0.0, 1.0],  # Upright cylinder
                physicsClientId=self.client_id,
            )

            p.changeDynamics(
                body_id,
                -1,
                lateralFriction=lat_fric,
                rollingFriction=roll_fric,
                spinningFriction=spin_fric,
                restitution=restitution,
                physicsClientId=self.client_id,
            )

            piece_body = XiangqiPieceBody(
                piece_id=piece_id,
                side=side,
                piece_type=p_type,
                body_id=body_id,
                client_id=self.client_id,
                radius_m=radius_m,
                height_m=height_m,
                mass_kg=mass_kg,
                grid_origin_robot=grid_origin,
                col_spacing_m=col_spacing_m,
                row_spacing_m=row_spacing_m,
            )
            self.pieces[piece_id] = piece_body

    def reset_pieces(self) -> None:
        """Reset all pieces to their initial canonical grid positions."""
        with self._physics_lock:
            # First release any attached piece
            if self.gripper.attached_piece is not None:
                self.release_attached_piece()

            shift_m = self.current_forward_shift_m
            nom_origin = self.board_cfg.get("grid_origin_in_robot_base_m", [-0.180, -0.160, 0.0105])
            x0 = nom_origin[0] - shift_m
            y0 = nom_origin[1]
            z0 = self.board_surface_z

            height_m = self.geom.piece_height_mm / 1000.0
            col_spacing_m = self.geom.grid_cell_width_mm / 1000.0
            row_spacing_m = self.geom.grid_cell_length_mm / 1000.0

            for p_info in self.layout_cfg.get("pieces", []):
                pid = p_info["id"]
                p_body = self.pieces.get(pid)
                if not p_body:
                    continue
                c = int(p_info["col"])
                r = int(p_info["row"])
                x = x0 - r * row_spacing_m
                y = y0 + c * col_spacing_m
                z = z0 + (height_m / 2.0) + 0.001

                p.resetBasePositionAndOrientation(
                    p_body.body_id,
                    [x, y, z],
                    [0.0, 0.0, 0.0, 1.0],
                    physicsClientId=self.client_id,
                )
                p.resetBaseVelocity(
                    p_body.body_id,
                    [0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                    physicsClientId=self.client_id,
                )
                p_body.physical_state = PiecePhysicalState.SETTLING
                p_body._consecutive_settled_steps = 0
                p_body.grid_origin_robot = (x0, y0, z0)

    def step(self, num_steps: int = 1) -> None:
        """Step the simulation by fixed deterministic timesteps."""
        for _ in range(num_steps):
            p.stepSimulation(physicsClientId=self.client_id)
            self.sim_time += self.timestep_s

            # Update attached piece kinematic slaving
            if self.gripper.attached_piece is not None:
                # Re-apply slaved pose to ensure no gravity/collision drift
                self.gripper.set_tcp_pose(
                    self.gripper.tcp_pos,
                    self.gripper.tcp_quat,
                    self.sim_time,
                )

            # Update piece states and out-of-bounds detection
            for piece in self.pieces.values():
                if piece.attached_to_gripper:
                    piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER
                    continue

                pos, _ = piece.get_pose_robot_base()
                lin_vel, ang_vel = piece.get_velocity()
                v_lin = float(np.linalg.norm(lin_vel))
                v_ang = float(np.linalg.norm(ang_vel))

                # Check out of bounds: fallen below board or thrown far away
                is_oob = (
                    pos[2] < self.z_min_oob
                    or pos[0] < self.board_x_min - self.xy_margin_oob
                    or pos[0] > self.board_x_max + self.xy_margin_oob
                    or pos[1] < self.board_y_min - self.xy_margin_oob
                    or pos[1] > self.board_y_max + self.xy_margin_oob
                )

                if is_oob:
                    piece.physical_state = PiecePhysicalState.OUT_OF_BOUNDS
                    continue

                # Settle vs moving detection
                if v_lin < self.lin_vel_thresh and v_ang < self.ang_vel_thresh:
                    piece._consecutive_settled_steps += 1
                    if piece._consecutive_settled_steps >= self.required_settled_steps:
                        piece.physical_state = PiecePhysicalState.RESTING
                    else:
                        piece.physical_state = PiecePhysicalState.SETTLING
                else:
                    piece._consecutive_settled_steps = 0
                    if pos[2] > self.board_surface_z + piece.height_m + 0.005:
                        piece.physical_state = PiecePhysicalState.FALLING
                    else:
                        piece.physical_state = PiecePhysicalState.ON_BOARD

    def step_until_settled(self, max_steps: Optional[int] = None) -> int:
        """
        Step physics until all non-attached, in-bounds pieces have settled.
        Returns number of steps executed.
        """
        limit = max_steps or self.max_settle_steps
        steps = 0

        while steps < limit:
            self.step(1)
            steps += 1

            all_settled = True
            for p in self.pieces.values():
                if p.attached_to_gripper or p.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                    continue
                if p.physical_state not in (PiecePhysicalState.RESTING, PiecePhysicalState.OUT_OF_BOUNDS):
                    all_settled = False
                    break

            if all_settled and steps >= self.required_settled_steps:
                break

        return steps

    def update_robot_tcp(
        self,
        tcp_xyz_m: Sequence[float],
        tcp_quat: Sequence[float],
        gripper_closed: bool,
    ) -> None:
        """Synchronize kinematic robot state to the virtual gripper."""
        self.gripper.set_gripper_state(gripper_closed)
        self.gripper.set_tcp_pose(tcp_xyz_m, tcp_quat, self.sim_time)

    def try_grasp(self, sim_time: Optional[float] = None, target_piece_id: Optional[str] = None) -> GraspResult:
        """
        Attempt deterministic geometric grasp on candidate pieces.
        If target_piece_id is provided, candidates are filtered strictly to that piece.
        If successful, attaches piece to gripper.
        """
        with self._physics_lock:
            if target_piece_id is not None:
                if target_piece_id not in self.pieces:
                    return GraspResult(
                        success=False,
                        status=GraspStatus.NO_CANDIDATE,
                        piece_id=target_piece_id,
                        reason=f"Target piece {target_piece_id} does not exist in world",
                    )
                candidates = [self.pieces[target_piece_id]]
            else:
                candidates = list(self.pieces.values())

            result = self.gripper.evaluate_grasp_eligibility(candidates)
            if target_piece_id is not None and result.piece_id is not None and result.piece_id != target_piece_id:
                return GraspResult(
                    success=False,
                    status=GraspStatus.AMBIGUOUS,
                    piece_id=target_piece_id,
                    reason=f"Candidate {result.piece_id} does not match requested target piece {target_piece_id}",
                )
            if result.success and result.piece_id:
                target_piece = self.pieces[result.piece_id]
                self.gripper.attach_piece(target_piece)
            return result

    def release_attached_piece(self) -> Optional[XiangqiPieceBody]:
        """Release attached piece. It inherits current motion velocity."""
        self.gripper.set_gripper_state(False)
        return self.gripper.detach_piece()

    def force_drop_attached_piece(self) -> Optional[XiangqiPieceBody]:
        """Failure-injection drop primitive: detaches piece regardless of gripper state."""
        self.gripper.set_gripper_state(False)
        return self.gripper.detach_piece()

    def get_attached_piece(self) -> Optional[XiangqiPieceBody]:
        return self.gripper.attached_piece

    def get_piece(self, piece_id: str) -> Optional[XiangqiPieceBody]:
        """Lookup piece body by its identifier."""
        return self.pieces.get(piece_id)

    def get_snapshot(self) -> WorldStateSnapshot:
        """Return immutable snapshot of authoritative physics state."""
        piece_snapshots = [p.to_snapshot() for p in self.pieces.values()]
        return WorldStateSnapshot(
            timestamp=time.time(),
            simulation_time=self.sim_time,
            gripper=self.gripper.to_state_dict(),
            pieces=piece_snapshots,
        )

    def get_gripper_piece_contacts(self) -> List[Dict[str, Any]]:
        """
        Query contact points between gripper collision proxy bodies and any pieces.
        Useful for diagnostic contact inspection.
        """
        contacts = []
        body_names = {
            self.gripper.palm_body_id: "palm",
            self.gripper.left_jaw_body_id: "left_jaw",
            self.gripper.right_jaw_body_id: "right_jaw",
        }
        for gb, name in body_names.items():
            if gb < 0:
                continue
            for pid, piece in self.pieces.items():
                pts = p.getContactPoints(
                    bodyA=gb,
                    bodyB=piece.body_id,
                    physicsClientId=self.client_id,
                )
                for pt in pts:
                    contacts.append({
                        "gripper_body": name,
                        "piece_id": pid,
                        "contact_distance": pt[8],
                        "normal_force": pt[9],
                    })
        return contacts

    def close(self) -> None:
        """Disconnect PyBullet simulation client and clean up proxy bodies."""
        if hasattr(self, "gripper") and self.gripper is not None:
            self.gripper.remove_proxies()
        if self.client_id >= 0:
            try:
                p.disconnect(self.client_id)
            except Exception:
                pass
            self.client_id = -1
