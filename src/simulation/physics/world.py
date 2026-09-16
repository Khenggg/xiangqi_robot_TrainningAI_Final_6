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

import json
import math
from pathlib import Path
import time
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

            # Gripper proxy and PyBullet collision bodies
            self.gripper = VirtualGripper(profile_path=self.gripper_profile_path)
            self._spawn_gripper_proxies()
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

    def _spawn_board(self) -> None:
        """Create finite static board box collider."""
        board_physics = self.physics_cfg.get("board", {})
        thickness_m = float(board_physics.get("collision_thickness_m", 0.040))

        # Dimensions from canonical physical geometry
        outer_length_m = self.geom.outer_length_mm / 1000.0  # Along X in robot_base (410 mm)
        outer_width_m = self.geom.outer_width_mm / 1000.0    # Along Y in robot_base (367 mm)

        half_x = outer_length_m / 2.0
        half_y = outer_width_m / 2.0
        half_z = thickness_m / 2.0

        board_center = self.board_cfg["board_center_in_robot_base_m"]
        surface_height = float(self.board_cfg.get("board_surface_height_m", 0.05))

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
        self.board_x_min = board_center[0] - half_x
        self.board_x_max = board_center[0] + half_x
        self.board_y_min = board_center[1] - half_y
        self.board_y_max = board_center[1] + half_y
        self.board_surface_z = surface_height

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

    def try_grasp(self) -> GraspResult:
        """
        Attempt deterministic geometric grasp on candidate pieces.
        If successful, attaches piece to gripper.
        """
        candidates = list(self.pieces.values())
        result = self.gripper.evaluate_grasp_eligibility(candidates)
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
