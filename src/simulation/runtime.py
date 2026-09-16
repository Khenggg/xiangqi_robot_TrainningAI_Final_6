"""
Virtual Xiangqi Simulation Coordinator / Runtime.

Coordinates:
- VirtualFR3Backend (authoritative joint/Cartesian kinematics)
- VirtualPhysicalWorld (PyBullet physics, 32 rigid pieces, finite board)
- TelemetryPublisher (WebSocket streaming to Three.js viewer)
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from src.hardware.backends.base import RobotStateSnapshot
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.kinematics.urdf_chain import matrix_to_rpy
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.transforms import (
    DEFAULT_R_ROBOT_TO_WORLD,
    continuous_board_coord,
    rpy_deg_to_quat,
)
from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.state import DropEvent, GraspResult, GraspStatus, WorldStateSnapshot
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.virtual_fr3_backend import VirtualFR3Backend
from src.domain.geometry import get_physical_geometry


class VirtualXiangqiSimulation:
    """
    Unified runtime coordinator bridging Virtual FR3 Backend with
    the PyBullet Virtual Physical World and Telemetry streaming.
    """

    def __init__(
        self,
        backend: Optional[VirtualFR3Backend] = None,
        world: Optional[VirtualPhysicalWorld] = None,
        telemetry: Optional[TelemetryPublisher] = None,
        auto_sync_telemetry: bool = True,
        scene_config_path: Optional[Union[str, Path]] = None,
        enable_collision_guard: bool = True,
    ):
        self.world = world or VirtualPhysicalWorld()
        self.backend = backend or VirtualFR3Backend()
        self.telemetry = telemetry
        self.auto_sync_telemetry = auto_sync_telemetry

        # Attach collision guard
        if enable_collision_guard:
            self.collision_guard = FR3CollisionGuard(world=self.world)
            self.backend.set_collision_guard(self.collision_guard)
        else:
            self.collision_guard = None

        # Project root resolution
        project_root = Path(__file__).resolve().parent.parent.parent
        self.scene_config_path = Path(scene_config_path) if scene_config_path else (
            project_root / "shared" / "virtual_fr3_scene.json"
        )
        self._load_scene_config()

        # Geometry
        self.geom = get_physical_geometry()

        # Tracking state
        self._last_time = time.time()
        self._last_flange_pos_m = np.array(self.backend.get_state_snapshot().flange_pose_mm_deg[:3]) / 1000.0
        self._last_gripper_closed = self.backend.get_state_snapshot().gripper_closed

        # Scheduled mid-motion force drop state
        self._scheduled_drop: Optional[Dict[str, Any]] = None
        self.last_drop_event: Optional[DropEvent] = None

        # Register listener with backend
        self.backend.add_state_listener(self._on_robot_state_update)

        # Initial gripper sync to TCP
        self._sync_gripper_to_tcp(self.backend.get_state_snapshot())

    def _load_scene_config(self):
        if self.scene_config_path.is_file():
            with open(self.scene_config_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            bp = cfg.get("virtual_board_placement", {})
            self.grid_origin_robot = bp.get("grid_origin_in_robot_base_m", [-0.18, -0.16, 0.0105])
            self.board_surface_z = bp.get("board_surface_height_m", 0.0105)
            if "target_tool_orientation_matrix" in bp:
                R_mat = np.array(bp["target_tool_orientation_matrix"], dtype=float)
                self.target_tool_euler_deg = [round(float(v), 2) for v in np.rad2deg(matrix_to_rpy(R_mat))]
            else:
                self.target_tool_euler_deg = bp.get("target_tool_orientation_euler_deg", [180.0, 0.0, 90.0])
        else:
            self.grid_origin_robot = [-0.18, -0.16, 0.0105]
            self.board_surface_z = 0.0105
            self.target_tool_euler_deg = [180.0, 0.0, 90.0]

        repo_root = Path(__file__).resolve().parent.parent.parent
        reach_path = repo_root / "shared" / "cell_reachability_dataset.json"
        self.reachability_dataset = {}
        if reach_path.is_file():
            try:
                with open(reach_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.reachability_dataset = {
                        (c["row"], c["col"]): c for c in data.get("cells", [])
                    }
            except Exception:
                pass

    def find_nearest_cell(self, pos_robot_m: Sequence[float]) -> Tuple[int, int]:
        """Map a 3D position in robot_base to nearest board grid (row, col)."""
        px, py = float(pos_robot_m[0]), float(pos_robot_m[1])
        x0, y0, _ = self.grid_origin_robot
        col_sp = self.geom.board.column_spacing / 1000.0
        row_sp = self.geom.board.row_spacing / 1000.0
        row = int(round((x0 - px) / row_sp))
        col = int(round((py - y0) / col_sp))
        return max(0, min(9, row)), max(0, min(8, col))

    def _sync_gripper_to_tcp(self, snapshot: RobotStateSnapshot):
        """Authoritative synchronization of physical gripper proxies to backend TCP."""
        pos_m = np.array(snapshot.tcp_pose_mm_deg[:3], dtype=float) / 1000.0
        rpy_deg = snapshot.tcp_pose_mm_deg[3:]
        quat_xyzw = rpy_deg_to_quat(rpy_deg)

        # Update kinematic gripper and slaved attachments
        self.world.update_robot_tcp(
            tcp_xyz_m=pos_m,
            tcp_quat=quat_xyzw,
            gripper_closed=snapshot.gripper_closed,
        )

    def _on_robot_state_update(self, snapshot: RobotStateSnapshot):
        """Called automatically when VirtualFR3Backend state changes."""
        self._sync_gripper_to_tcp(snapshot)

        # Detect gripper transition
        if snapshot.gripper_closed != self._last_gripper_closed:
            if snapshot.gripper_closed:
                self.world.try_grasp()
            else:
                self.world.release_attached_piece()
            self._last_gripper_closed = snapshot.gripper_closed

        # Mid-motion scheduled force drop check (must trigger while robot is in MOVING state)
        if (
            self._scheduled_drop is not None
            and not self._scheduled_drop["triggered"]
            and snapshot.motion_state == "MOVING"
        ):
            piece = self.world.get_attached_piece()
            if piece is not None:
                tgt_id = self._scheduled_drop.get("target_piece_id")
                if tgt_id is None or tgt_id == piece.piece_id:
                    curr_p = np.array(snapshot.tcp_pose_mm_deg[:3], dtype=float) / 1000.0
                    if self._scheduled_drop.get("start_tcp_m") is None:
                        self._scheduled_drop["start_tcp_m"] = curr_p.copy()

                    start_p = self._scheduled_drop["start_tcp_m"]
                    target_p = self._scheduled_drop.get("target_xyz_m")

                    if target_p is not None:
                        total_dist = float(np.linalg.norm(target_p - start_p))
                        curr_dist = float(np.linalg.norm(curr_p - start_p))
                        progress = (curr_dist / max(total_dist, 1e-4)) if total_dist > 1e-4 else 1.0
                    else:
                        step_cnt = self._scheduled_drop.get("step_count", 0) + 1
                        self._scheduled_drop["step_count"] = step_cnt
                        expected_steps = self._scheduled_drop.get("expected_steps", 20)
                        progress = min(1.0, step_cnt / float(expected_steps))

                    if progress >= self._scheduled_drop["progress_threshold"]:
                        self._trigger_scheduled_drop(snapshot, piece, progress)

        # Step physics to advance any dynamics or attachments
        self.world.step(1)

        # Stream world state if telemetry connected
        if self.telemetry is not None and self.auto_sync_telemetry:
            self.telemetry.update_world_state(self.world.get_snapshot())

    def connect(self) -> bool:
        """Connect backend and settle simulation."""
        ok = self.backend.connect()
        self.world.step_until_settled(max_steps=60)
        if self.telemetry and self.auto_sync_telemetry:
            self.telemetry.update_world_state(self.world.get_snapshot())
        return ok

    def disconnect(self) -> bool:
        """Disconnect backend."""
        return self.backend.disconnect()

    def step(self, num_steps: int = 1) -> WorldStateSnapshot:
        """Advance physics simulation by specified number of steps."""
        self.world.step(num_steps)
        snap = self.world.get_snapshot()
        if self.telemetry and self.auto_sync_telemetry:
            self.telemetry.update_world_state(snap)
        return snap

    def settle(self, max_steps: int = 120) -> bool:
        """Settle all pieces until static equilibrium is reached."""
        steps = self.world.step_until_settled(max_steps=max_steps)
        snap = self.world.get_snapshot()
        if self.telemetry and self.auto_sync_telemetry:
            self.telemetry.update_world_state(snap)
        return steps < max_steps

    def get_world_snapshot(self) -> WorldStateSnapshot:
        return self.world.get_snapshot()

    def get_robot_snapshot(self) -> RobotStateSnapshot:
        return self.backend.get_state_snapshot()

    def cell_to_robot_xyz(self, col: int, row: int, z_height_m: Optional[float] = None) -> Tuple[float, float, float]:
        """Convert board cell (col, row) to robot_base (x, y, z) in meters."""
        x0, y0, _ = self.grid_origin_robot
        col_sp = self.geom.board.column_spacing / 1000.0
        row_sp = self.geom.board.row_spacing / 1000.0
        x = x0 - row * row_sp
        y = y0 + col * col_sp
        z = self.board_surface_z if z_height_m is None else float(z_height_m)
        return x, y, z

    def pick_piece(
        self,
        piece_id: str,
        hover_height_m: float = 0.060,
        speed_factor: float = 50.0,
    ) -> GraspResult:
        """
        Execute pick trajectory over piece:
        1. Open gripper
        2. Move above piece (hover)
        3. Descend to grasp center
        4. Close gripper (grasp)
        5. Lift back to hover
        """
        piece = self.world.pieces.get(piece_id)
        if piece is None:
            return GraspResult(success=False, status=None, reason=f"Piece {piece_id} not found")

        pos_robot, _ = piece.get_pose_robot_base()
        px, py, pz = pos_robot

        # Open gripper
        self.backend.set_gripper(False)

        # Target orientations
        rx, ry, rz = self.target_tool_euler_deg

        # Nearest cell verified approach
        r, c = self.find_nearest_cell(pos_robot)
        cell_info = self.reachability_dataset.get((r, c))

        hover_pose = [px * 1000.0, py * 1000.0, (pz + hover_height_m) * 1000.0, rx, ry, rz]
        if cell_info and "approach_joints_deg" in cell_info:
            self.backend.move_joint(cell_info["approach_joints_deg"], speed_factor=speed_factor)
            self.backend.move_cartesian(hover_pose, speed_factor=speed_factor)
        else:
            ik = self.backend.solve_tcp_ik(hover_pose, allow_multi_seed=True)
            if ik.success:
                self.backend.move_joint(np.degrees(ik.joints_rad), speed_factor=speed_factor)
            else:
                return GraspResult(success=False, status=None, reason="Hover pose unreachable")

        # Descend to grasp (TCP directly at piece center)
        grasp_pose = [px * 1000.0, py * 1000.0, pz * 1000.0, rx, ry, rz]
        self.backend.set_allowed_grasp_piece_id(piece_id)
        if not self.backend.move_cartesian(grasp_pose, speed_factor=speed_factor):
            self.backend.set_allowed_grasp_piece_id(None)
            return GraspResult(success=False, status=None, reason=f"Grasp descent rejected: {self.backend._last_error}")

        # Close gripper (triggers _on_robot_state_update -> try_grasp)
        self.backend.set_gripper(True)
        attached = self.world.get_attached_piece()
        if attached is not None:
            res = GraspResult(success=True, status=GraspStatus.SUCCESS, piece_id=attached.piece_id)
        else:
            res = self.world.try_grasp()

        # Lift back to hover
        self.backend.move_cartesian(hover_pose, speed_factor=speed_factor)
        self.backend.set_allowed_grasp_piece_id(None)

        return res

    def place_piece(
        self,
        col: int,
        row: int,
        hover_height_m: float = 0.060,
        speed_factor: float = 50.0,
    ) -> bool:
        """
        Execute place trajectory to target board cell:
        1. Move to hover above cell
        2. Descend to board surface + piece thickness / 2
        3. Open gripper (release)
        4. Lift back to hover
        """
        tx, ty, tz = self.cell_to_robot_xyz(col, row)
        piece_h = self.geom.piece_height_mm / 1000.0
        piece_z = tz + piece_h / 2.0

        rx, ry, rz = self.target_tool_euler_deg

        hover_pose = [tx * 1000.0, ty * 1000.0, (piece_z + hover_height_m) * 1000.0, rx, ry, rz]
        place_pose = [tx * 1000.0, ty * 1000.0, piece_z * 1000.0, rx, ry, rz]

        # 1. Move to hover
        if not self.backend.move_cartesian(hover_pose, speed_factor=speed_factor):
            ik = self.backend.solve_tcp_ik(hover_pose, allow_multi_seed=True)
            if ik.success:
                self.backend.move_joint(np.degrees(ik.joints_rad), speed_factor=speed_factor)
            else:
                return False

        # 2. Descend to place
        self.backend.move_cartesian(place_pose, speed_factor=speed_factor)

        # 3. Open gripper (release)
        self.backend.set_gripper(False)
        self.world.release_attached_piece()
        self.world.step_until_settled(max_steps=20)

        # 4. Lift back to hover
        self.backend.move_cartesian(hover_pose, speed_factor=speed_factor)
        return True

    def schedule_force_drop(
        self,
        progress_threshold: float = 0.5,
        target_xyz_m: Optional[Sequence[float]] = None,
        target_piece_id: Optional[str] = None,
        expected_steps: int = 20,
    ) -> None:
        """
        Schedule an automatic force-drop to trigger mid-motion when
        trajectory progress >= progress_threshold and motion_state == 'MOVING'.
        """
        self._scheduled_drop = {
            "progress_threshold": float(progress_threshold),
            "target_xyz_m": np.asarray(target_xyz_m, dtype=float) if target_xyz_m is not None else None,
            "target_piece_id": target_piece_id,
            "expected_steps": int(expected_steps),
            "step_count": 0,
            "triggered": False,
            "start_tcp_m": None,
        }
        self.last_drop_event = None

    def _trigger_scheduled_drop(
        self,
        snapshot: RobotStateSnapshot,
        piece: XiangqiPieceBody,
        progress: float,
    ) -> DropEvent:
        pos_robot, quat_robot = piece.get_pose_robot_base()
        lin_vel, ang_vel = self.world.gripper.estimate_velocity()
        gripper_pos = list(self.world.gripper.grasp_pos)
        gripper_quat = list(self.world.gripper.grasp_quat)

        # Detach piece mid-flight from gripper
        self.backend.set_gripper(False)
        self.world.force_drop_attached_piece()
        speed = float(np.linalg.norm(lin_vel))

        event = DropEvent(
            triggered=True,
            timestamp=time.time(),
            sim_time=self.world.sim_time,
            robot_motion_state=snapshot.motion_state,  # Authoritatively "MOVING"
            release_position=pos_robot.tolist(),
            release_linear_velocity=lin_vel.tolist(),
            release_angular_velocity=ang_vel.tolist(),
            attached_piece_id=piece.piece_id,
            trajectory_progress=float(progress),
            release_speed=speed,
            release_gripper_position=gripper_pos,
            release_gripper_orientation=gripper_quat,
            release_piece_orientation=quat_robot.tolist(),
        )
        self.last_drop_event = event
        self._scheduled_drop["triggered"] = True

        if self.telemetry and self.auto_sync_telemetry:
            self.telemetry.update_world_state(self.world.get_snapshot())

        return event

    def move_cartesian(
        self,
        target_pose_or_xyz: Sequence[float],
        target_rpy_deg: Optional[Union[Sequence[float], float]] = None,
        speed_factor: Optional[float] = None,
        samples: int = 20,
    ) -> bool:
        """Execute linear motion, automatically seeding target_xyz_m for any scheduled drop."""
        if len(target_pose_or_xyz) == 3 and target_rpy_deg is not None and hasattr(target_rpy_deg, "__len__") and len(target_rpy_deg) == 3:
            scale = 1000.0 if max(abs(v) for v in target_pose_or_xyz) < 5.0 else 1.0
            target_pose_mm_deg = [
                float(target_pose_or_xyz[0]) * scale,
                float(target_pose_or_xyz[1]) * scale,
                float(target_pose_or_xyz[2]) * scale,
                float(target_rpy_deg[0]),
                float(target_rpy_deg[1]),
                float(target_rpy_deg[2]),
            ]
        elif len(target_pose_or_xyz) == 6:
            target_pose_mm_deg = list(target_pose_or_xyz)
            if speed_factor is None and isinstance(target_rpy_deg, (int, float)):
                speed_factor = float(target_rpy_deg)
        else:
            raise ValueError("target_pose must be 6 elements [x,y,z,rx,ry,rz] or (xyz, rpy)")

        if self._scheduled_drop is not None and not self._scheduled_drop.get("triggered", False):
            if self._scheduled_drop.get("target_xyz_m") is None:
                self._scheduled_drop["target_xyz_m"] = np.array(target_pose_mm_deg[:3], dtype=float) / 1000.0
            self._scheduled_drop["expected_steps"] = samples

        return self.backend.move_cartesian(target_pose_mm_deg, speed_factor=speed_factor, samples=samples)

    def force_drop(self) -> Optional[DropEvent]:
        """Trigger dynamic force-drop release immediately and record a DropEvent."""
        attached = self.world.get_attached_piece()
        if attached is None:
            return None

        snap = self.backend.get_state_snapshot()
        pos, quat = attached.get_pose_robot_base()
        lin_vel, ang_vel = self.world.gripper.estimate_velocity()
        gripper_pos = list(self.world.gripper.grasp_pos)
        gripper_quat = list(self.world.gripper.grasp_quat)
        self.backend.set_gripper(False)
        dropped = self.world.force_drop_attached_piece()

        event = DropEvent(
            triggered=True,
            timestamp=time.time(),
            sim_time=self.world.sim_time,
            robot_motion_state=snap.motion_state,
            release_position=pos.tolist(),
            release_linear_velocity=lin_vel.tolist(),
            release_angular_velocity=ang_vel.tolist(),
            attached_piece_id=attached.piece_id,
            trajectory_progress=1.0,
            release_speed=float(np.linalg.norm(lin_vel)),
            release_gripper_position=gripper_pos,
            release_gripper_orientation=gripper_quat,
            release_piece_orientation=quat.tolist(),
        )
        self.last_drop_event = event

        if self.telemetry and self.auto_sync_telemetry:
            self.telemetry.update_world_state(self.world.get_snapshot())

        return event

    def cell_to_robot_xyz_m(self, row: int, col: int, z_m: float) -> List[float]:
        """Convert board cell (row, col) and altitude z_m to robot base XYZ coordinates."""
        x0, y0, _ = self.grid_origin_robot
        row_spacing = self.geom.grid_cell_length_mm / 1000.0
        col_spacing = self.geom.grid_cell_width_mm / 1000.0
        x = x0 - row * row_spacing
        y = y0 + col * col_spacing
        return [round(x, 5), round(y, 5), round(z_m, 5)]

    def execute_3stage_trajectory(
        self,
        src_cell: Tuple[int, int],
        dst_cell: Tuple[int, int],
        speed_factor: Optional[float] = None,
        samples_per_stage: int = 20,
    ) -> Dict[str, Any]:
        """
        Execute authoritative 3-stage Pick & Place Cartesian trajectory:
        1. LIFT: Cartesian MoveL (same X/Y, increasing Z from grasp to approach)
        2. TRANSIT: Cartesian MoveL (source approach -> target approach at constant safe Z)
        3. LAND: Cartesian MoveL (same target X/Y, decreasing Z from approach to grasp)

        Uses downward tool orientation [180.0, 0.0, -90.0] deg.
        Pre-validates collision guard and publishes authoritative telemetry.
        """
        r_src, c_src = src_cell
        r_dst, c_dst = dst_cell

        # Canonical heights
        board_z = self.board_surface_z  # 0.0105 m
        piece_h = self.geom.piece_height_mm / 1000.0  # 0.00943 m
        z_grasp = board_z + piece_h / 2.0  # 0.015215 m (piece center)
        z_transit = board_z + 0.070        # 0.0805 m (canonical +70mm safe clearance)
        tool_rpy = list(self.target_tool_euler_deg)

        src_app_m = self.cell_to_robot_xyz_m(r_src, c_src, z_transit)
        dst_app_m = self.cell_to_robot_xyz_m(r_dst, c_dst, z_transit)
        dst_grasp_m = self.cell_to_robot_xyz_m(r_dst, c_dst, z_grasp)

        to_mm_deg = lambda p_m: [p_m[0] * 1000.0, p_m[1] * 1000.0, p_m[2] * 1000.0] + tool_rpy

        # Ensure robot is positioned at src grasp pose before starting Lift
        src_info = self.reachability_dataset.get((r_src, c_src))
        if src_info and "grasp_joints_deg" in src_info:
            self.backend.move_joint(src_info["grasp_joints_deg"], speed_factor=speed_factor)

        # Stage 1: LIFT (vertical MoveL from grasp to safe transit height)
        ok1 = self.move_cartesian(to_mm_deg(src_app_m), speed_factor=speed_factor, samples=samples_per_stage)
        if not ok1:
            return {"success": False, "failed_stage": "LIFT", "error": self.backend._last_error}

        # Stage 2: TRANSIT (horizontal MoveL across safe transit plane)
        ok2 = self.move_cartesian(to_mm_deg(dst_app_m), speed_factor=speed_factor, samples=samples_per_stage)
        if not ok2:
            return {"success": False, "failed_stage": "TRANSIT", "error": self.backend._last_error}

        # Stage 3: LAND (vertical MoveL from safe transit height down to grasp target)
        ok3 = self.move_cartesian(to_mm_deg(dst_grasp_m), speed_factor=speed_factor, samples=samples_per_stage)
        if not ok3:
            return {"success": False, "failed_stage": "LAND", "error": self.backend._last_error}

        return {
            "success": True,
            "stages": ["LIFT", "TRANSIT", "LAND"],
            "src": src_cell,
            "dst": dst_cell,
            "z_grasp_m": z_grasp,
            "z_transit_m": z_transit,
        }

    def start(self) -> None:
        """Start or initialize simulation coordinator (idempotent)."""
        if not self.backend.is_connected():
            self.backend.connect()

    def stop(self) -> None:
        """Stop simulation coordinator and clean up resources."""
        if self.backend.is_connected():
            self.backend.disconnect()
        self.world.close()


# Backward-compatibility alias
SimulationRuntime = VirtualXiangqiSimulation


