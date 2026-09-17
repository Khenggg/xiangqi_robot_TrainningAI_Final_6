"""
Virtual Xiangqi Simulation Coordinator / Runtime.

Coordinates:
- VirtualFR3Backend (authoritative joint/Cartesian kinematics)
- VirtualPhysicalWorld (PyBullet physics, 32 rigid pieces, finite board)
- TelemetryPublisher (WebSocket streaming to Three.js viewer)
"""

from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pybullet as p

logger = logging.getLogger(__name__)

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
import contextlib
from enum import Enum
from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.state import (
    DropEvent,
    GraspResult,
    GraspStatus,
    PickResult,
    PiecePhysicalState,
    WorldStateSnapshot,
)
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.placement import BoardPlacementAnalyzer, BoardPlacementState, canonical_cell_to_robot_xyz_m
from src.simulation.virtual_fr3_backend import VirtualFR3Backend
from src.domain.geometry import get_physical_geometry


class RuntimeOperationState(str, Enum):
    """Authoritative state machine for runtime operations and mutual exclusion."""
    IDLE = "IDLE"
    MOTION = "MOTION"
    VALIDATING_LOCAL = "VALIDATING_LOCAL"
    VALIDATING_ROUTES = "VALIDATING_ROUTES"
    BOARD_ADJUSTMENT = "BOARD_ADJUSTMENT"
    SERVICE_MOVE = "SERVICE_MOVE"
    RESETTING = "RESETTING"


class PlaceResult(dict):
    """Structured result for place_piece operation with backwards-compatible boolean behavior."""
    def __init__(
        self,
        success: bool,
        status: str,
        error: Optional[str] = None,
        piece_id: Optional[str] = None,
        target_cell: Optional[Tuple[int, int]] = None,
    ):
        super().__init__(success=success, status=status, error=error, piece_id=piece_id, target_cell=target_cell)

    def __bool__(self) -> bool:
        return bool(self.get("success", False))

    @property
    def success(self) -> bool:
        return bool(self.get("success", False))

    @property
    def status(self) -> str:
        return str(self.get("status", "UNKNOWN"))

    @property
    def error(self) -> Optional[str]:
        return self.get("error")

    @property
    def piece_id(self) -> Optional[str]:
        return self.get("piece_id")

    @property
    def target_cell(self) -> Optional[Tuple[int, int]]:
        return self.get("target_cell")


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

        # Ensure backend is connected to telemetry publisher
        if self.telemetry is not None and getattr(self.backend, "telemetry_publisher", None) is None:
            self.backend.telemetry_publisher = self.telemetry

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

        self._command_lock = threading.RLock()
        self._physics_query_lock = getattr(self.world, "_physics_lock", threading.RLock())
        self._validation_in_progress = False
        self._operation_state = RuntimeOperationState.IDLE
        self._operation_lock = threading.RLock()

        # Register listener with backend
        self.backend.add_state_listener(self._on_robot_state_update)

        # Register command handler with telemetry publisher if provided
        if self.telemetry is not None:
            self.telemetry.register_command_handler(self._handle_client_command)

        # Initial gripper sync to TCP
        self._sync_gripper_to_tcp(self.backend.get_state_snapshot())
        if hasattr(self.world, "step_until_settled"):
            self.world.step_until_settled(max_steps=20)

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

        # Authoritative dynamic placement state and analyzer
        self.placement_state = BoardPlacementState.compute(
            forward_shift_mm=0.0,
            safe_transit_height_mm=70.0,
            board_height_offset_mm=0.0,
            nominal_grid_origin_m=self.grid_origin_robot,
            placement_version=1,
        )
        self.placement_analyzer = BoardPlacementAnalyzer(
            kinematics=self.backend.kinematics,
            board_surface_nominal_m=self.board_surface_z,
        )

    @property
    def operation_state(self) -> RuntimeOperationState:
        with self._operation_lock:
            return self._operation_state

    @contextlib.contextmanager
    def acquire_operation_state(self, target_state: RuntimeOperationState):
        """Atomically enter an operation state. Prevents concurrent mutations."""
        with self._operation_lock:
            if self._operation_state == RuntimeOperationState.RESETTING:
                # RESETTING is a master state permitted to execute nested reset sub-tasks
                yield
                return
            if self._operation_state != RuntimeOperationState.IDLE:
                raise RuntimeError(f"BUSY: System is currently in state {self._operation_state.value}")
            self._operation_state = target_state
            self._broadcast_operation_state()
        try:
            yield
        finally:
            with self._operation_lock:
                if self._operation_state == target_state:
                    self._operation_state = RuntimeOperationState.IDLE
                    self._broadcast_operation_state()

    def _broadcast_operation_state(self) -> None:
        if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
            self.telemetry.broadcast_custom({
                "type": "operation_state",
                "state": self._operation_state.value,
            })

    def _get_piece_at_cell(self, row: int, col: int) -> Optional[str]:
        """Find the ID of any piece currently resting on the given grid cell."""
        try:
            x_cell, y_cell, _ = self.canonical_cell_to_robot_xyz(row, col)
            cell_xy = np.array([x_cell, y_cell], dtype=float)
            for pid, piece in self.world.pieces.items():
                if piece.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                    continue
                p_pos, _ = piece.get_pose_robot_base()
                if np.linalg.norm(np.array(p_pos[:2]) - cell_xy) < 0.025:
                    return pid
        except Exception:
            pass
        return None

    def find_nearest_cell(self, pos_robot_m: Sequence[float]) -> Tuple[int, int]:
        """Map a 3D position in robot_base to nearest board grid (row, col)."""
        px, py = float(pos_robot_m[0]), float(pos_robot_m[1])
        x0, y0 = float(self.placement_state.grid_origin_robot_m[0]), float(self.placement_state.grid_origin_robot_m[1])
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
        if not hasattr(self.world, "client_id") or self.world.client_id < 0 or not p.isConnected(self.world.client_id):
            return
        # Blocker 3: Actual PyBullet articulated FR3 follows runtime execution samples (backend q == PyBullet q == Three.js q)
        if hasattr(self.world, "sync_robot_runtime_configuration"):
            self.world.sync_robot_runtime_configuration(snapshot.joints_rad)
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
            if getattr(self.backend, "telemetry_publisher", None) is None:
                self.telemetry.update_from_snapshot(snapshot)
            self.telemetry.update_world_state(self.world.get_snapshot())

    def connect(self) -> bool:
        """Connect backend and settle simulation."""
        ok = self.backend.connect()
        self.world.step_until_settled(max_steps=60)
        if self.telemetry and self.auto_sync_telemetry:
            self.telemetry.update_from_snapshot(self.backend.get_state_snapshot())
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
        hover_height_m: Optional[float] = None,
        speed_factor: float = 50.0,
    ) -> PickResult:
        """
        Execute pick trajectory over piece with strict fail-fast validation:
        1. Open gripper
        2. Move above piece (hover) using current placement IK (dataset q is SEED only)
        3. Descend to grasp center
        4. Close gripper & verify grasp
        5. Lift back to hover
        """
        with self._command_lock:
            if self._operation_state != RuntimeOperationState.IDLE:
                return PickResult(
                    success=False,
                    status="MOTION_REJECTED_BUSY",
                    error=f"System currently in state {self._operation_state.value}",
                    piece_id=piece_id,
                )

            piece = self.world.pieces.get(piece_id)
            if piece is None:
                return PickResult(success=False, status="PIECE_NOT_FOUND", error=f"Piece {piece_id} not found", piece_id=piece_id)

            pos_robot, _ = piece.get_pose_robot_base()
            px, py, pz = pos_robot

            # Default hover height derives from authoritative dynamic placement
            safe_h_m = (self.placement_state.safe_transit_height_mm / 1000.0) if hasattr(self, "placement_state") else 0.070
            eff_hover_h = hover_height_m if hover_height_m is not None else safe_h_m
            safe_plane_z = self.board_surface_z + safe_h_m

            # 1. Open gripper
            self.backend.set_gripper(False)

            rx, ry, rz = self.target_tool_euler_deg
            hover_pose = [px * 1000.0, py * 1000.0, (pz + eff_hover_h) * 1000.0, rx, ry, rz]

            # Use dataset approach joints STRICTLY as IK seed, never as direct motion target
            r, c = self.find_nearest_cell(pos_robot)
            cell_info = self.reachability_dataset.get((r, c))
            seed_joints = np.radians(cell_info["approach_joints_deg"]) if cell_info and "approach_joints_deg" in cell_info else None

            ik_hover = self.backend.solve_tcp_ik(hover_pose, seed_joints=seed_joints, allow_multi_seed=True)
            if not ik_hover.success:
                return PickResult(success=False, status="HOVER_UNREACHABLE", error="Hover pose unreachable", piece_id=piece_id)

            with self.acquire_operation_state(RuntimeOperationState.MOTION):
                # 2. Preposition / Hover
                ok_hover = self.backend.move_joint_with_lift_recovery(
                    np.degrees(ik_hover.joints_rad),
                    speed_factor=speed_factor,
                    safe_plane_z_m=safe_plane_z,
                )
                if not ok_hover:
                    return PickResult(success=False, status="HOVER_APPROACH_REJECTED", error=f"Hover approach rejected: {self.backend._last_error}", piece_id=piece_id)

                if not self.backend.move_cartesian(hover_pose, speed_factor=speed_factor):
                    return PickResult(success=False, status="HOVER_ALIGNMENT_REJECTED", error=f"Hover Cartesian alignment rejected: {self.backend._last_error}", piece_id=piece_id)

                try:
                    self.backend.set_allowed_grasp_piece_id(piece_id)

                    # 3. Descend to grasp (TCP at piece center)
                    grasp_pose = [px * 1000.0, py * 1000.0, pz * 1000.0, rx, ry, rz]
                    if not self.backend.move_cartesian(grasp_pose, speed_factor=speed_factor):
                        return PickResult(success=False, status="DESCENT_REJECTED", error=f"Grasp descent rejected: {self.backend._last_error}", piece_id=piece_id)

                    # 4. Close gripper (triggers try_grasp)
                    self.backend.set_gripper(True)
                    attached = self.world.get_attached_piece()
                    if attached is not None and attached.piece_id == piece_id:
                        grasp_res = GraspResult(success=True, status=GraspStatus.SUCCESS, piece_id=attached.piece_id)
                    else:
                        raw_res = self.world.try_grasp(target_piece_id=piece_id)
                        if isinstance(raw_res, GraspResult):
                            grasp_res = raw_res
                        elif isinstance(raw_res, bool):
                            grasp_res = GraspResult(
                                success=raw_res,
                                status=GraspStatus.SUCCESS if raw_res else None,
                                piece_id=piece_id if raw_res else None,
                                reason=None if raw_res else "Grasp failed",
                            )
                        elif hasattr(raw_res, "success"):
                            grasp_res = raw_res
                        else:
                            grasp_res = GraspResult(success=bool(raw_res), status=GraspStatus.SUCCESS if raw_res else None)

                    if not grasp_res.success:
                        logger.warning(f"Grasp verification failed for {piece_id}: {grasp_res.reason}")
                        return PickResult(success=False, status=str(getattr(grasp_res, "status", "GRASP_FAILED")), error=f"Grasp verification failed: {grasp_res.reason}", piece_id=piece_id)

                    # 5. Lift back to hover
                    if not self.backend.move_cartesian(hover_pose, speed_factor=speed_factor):
                        return PickResult(success=False, status=GraspStatus.LIFT_FAILED_AFTER_GRASP.value, error=f"Lift after grasp failed: {self.backend._last_error}", piece_id=piece_id)

                    return PickResult(success=True, status=GraspStatus.SUCCESS.value, piece_id=piece_id)
                finally:
                    self.backend.set_allowed_grasp_piece_id(None)

    def place_piece(
        self,
        *args: Any,
        col: Optional[int] = None,
        row: Optional[int] = None,
        target_cell: Optional[Tuple[int, int]] = None,
        hover_height_m: Optional[float] = None,
        speed_factor: float = 50.0,
        **kwargs: Any,
    ) -> PlaceResult:
        """
        Execute place trajectory to target board cell with strict fail-fast semantics:
        1. Verify piece is currently attached
        2. Move to hover above cell
        3. Descend to land pose (surface + piece thickness / 2)
        4. VERIFY LAND SUCCESS - IF FAILED: DO NOT OPEN GRIPPER, DO NOT RELEASE PIECE!
        5. Open gripper & release piece
        6. Settle
        7. Lift back to hover
        """
        with self._command_lock:
            if self._operation_state != RuntimeOperationState.IDLE:
                return PlaceResult(
                    success=False,
                    status="MOTION_REJECTED_BUSY",
                    error=f"System currently in state {self._operation_state.value}",
                )

            attached = self.world.get_attached_piece()
            if attached is None:
                return PlaceResult(success=False, status="INVALID_STATE", error="No piece attached to gripper")

            # Resolve destination coordinates across flexible invocation patterns:
            # e.g.: place_piece(col, row), place_piece("piece_id", target_cell=(r, c)), place_piece(target_cell=(r, c))
            if target_cell is None and "target_cell" in kwargs:
                target_cell = kwargs["target_cell"]

            if target_cell is not None:
                r_target, c_target = int(target_cell[0]), int(target_cell[1])
                tx, ty, tz = self.cell_to_robot_xyz_m(r_target, c_target)
            else:
                positional = [a for a in args if not isinstance(a, str)]
                if len(positional) >= 2:
                    c_val, r_val = int(positional[0]), int(positional[1])
                    tx, ty, tz = self.cell_to_robot_xyz(c_val, r_val)
                elif col is not None and row is not None:
                    tx, ty, tz = self.cell_to_robot_xyz(int(col), int(row))
                else:
                    return PlaceResult(success=False, status="INVALID_ARGS", error="Missing destination cell or (col, row)")

            piece_h = self.geom.piece_height_mm / 1000.0
            piece_z = tz + piece_h / 2.0

            safe_h_m = (self.placement_state.safe_transit_height_mm / 1000.0) if hasattr(self, "placement_state") else 0.070
            eff_hover_h = hover_height_m if hover_height_m is not None else safe_h_m
            safe_plane_z = self.board_surface_z + safe_h_m

            rx, ry, rz = self.target_tool_euler_deg
            hover_pose = [tx * 1000.0, ty * 1000.0, (piece_z + eff_hover_h) * 1000.0, rx, ry, rz]
            place_pose = [tx * 1000.0, ty * 1000.0, piece_z * 1000.0, rx, ry, rz]

            with self.acquire_operation_state(RuntimeOperationState.MOTION):
                # 1. Move to hover
                if not self.backend.move_cartesian(hover_pose, speed_factor=speed_factor):
                    ik = self.backend.solve_tcp_ik(hover_pose, allow_multi_seed=True)
                    if ik.success:
                        ok_app = self.backend.move_joint_with_lift_recovery(
                            np.degrees(ik.joints_rad),
                            speed_factor=speed_factor,
                            safe_plane_z_m=safe_plane_z,
                        )
                        if not ok_app:
                            return PlaceResult(success=False, status="APPROACH_FAILED", error=f"Approach failed: {self.backend._last_error}")
                    else:
                        return PlaceResult(success=False, status="APPROACH_FAILED", error="Hover pose unreachable")
                    # 2. Descend to place (LAND)
                    land_ok = self.backend.move_cartesian(place_pose, speed_factor=speed_factor)
                    if not land_ok:
                        # CRITICAL FAIL-FAST INVARIANT: DO NOT OPEN GRIPPER, DO NOT RELEASE PIECE!
                        logger.error("place_piece LAND failed. Preserving grasp; piece NOT released.")
                        return PlaceResult(success=False, status="LAND_FAILED", error=f"Landing rejected: {self.backend._last_error}")

                    # Verify piece is still attached before release
                    if self.world.get_attached_piece() is None:
                        return PlaceResult(success=False, status="INVALID_STATE", error="Piece lost before release")

                    # 3. Open gripper & release piece
                    self.backend.set_gripper(False)
                    self.world.release_attached_piece()
                    self.world.step_until_settled(max_steps=20)

                    # 4. Lift back to hover
                    lift_ok = self.backend.move_cartesian(hover_pose, speed_factor=speed_factor)
                    if not lift_ok:
                        return PlaceResult(success=True, status="LIFT_FAILED_AFTER_RELEASE", error=f"Lift after release failed: {self.backend._last_error}")

                    return PlaceResult(success=True, status="SUCCESS", error=None)

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

    def cell_to_robot_xyz_m(self, row: int, col: int, z_m: Optional[float] = None) -> List[float]:
        """Convert board cell (row, col) and altitude z_m to robot base XYZ coordinates."""
        d = self.placement_state.forward_shift_mm
        effective_z = self.board_surface_z if z_m is None else float(z_m)
        r_sp = self.geom.grid_cell_length_mm / 1000.0
        c_sp = self.geom.grid_cell_width_mm / 1000.0
        nom_x0 = self.placement_state.grid_origin_robot_m[0] + (d / 1000.0)
        nom_y0 = self.placement_state.grid_origin_robot_m[1]
        x, y, z = canonical_cell_to_robot_xyz_m(
            row=row,
            col=col,
            forward_shift_mm=d,
            z_m=effective_z,
            nominal_x0=nom_x0,
            nominal_y0=nom_y0,
            row_spacing_m=r_sp,
            col_spacing_m=c_sp,
        )
        return [round(x, 5), round(y, 5), round(z, 5)]

    def set_board_placement(
        self,
        forward_shift_mm: float,
        safe_transit_height_mm: Optional[float] = None,
        board_height_offset_mm: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Authoritatively relocate board placement.
        Rejects if robot is moving, active in a trajectory stage, or holding a piece.
        Validates swept volume between current and target placement against arm links.
        """
        with self._command_lock:
            if self._operation_state not in (RuntimeOperationState.IDLE, RuntimeOperationState.BOARD_ADJUSTMENT, RuntimeOperationState.RESETTING):
                err = f"Cannot change board placement while system is in state {self._operation_state.value}"
                return {"success": False, "status": "BOARD_RELOCATION_REJECTED_BUSY", "error": err}
            if getattr(self, "_validation_in_progress", False):
                err = "Cannot change board placement while validation is actively running"
                return {"success": False, "status": "BOARD_RELOCATION_REJECTED_BUSY", "error": err}
            snap = self.backend.get_state_snapshot()
            if snap.motion_state == "MOVING":
                err = "Cannot change board placement while robot is MOVING"
                return {"success": False, "status": "BOARD_RELOCATION_REJECTED_ROBOT_MOVING", "error": err}
            if snap.trajectory_stage not in (None, "IDLE", "COMPLETE"):
                err = f"Cannot change board placement during active trajectory ({snap.trajectory_stage})"
                return {"success": False, "status": "BOARD_RELOCATION_REJECTED_ACTIVE_TRAJECTORY", "error": err}
            cur_h = self.placement_state.safe_transit_height_mm if safe_transit_height_mm is None else float(safe_transit_height_mm)
            cur_z_off = self.placement_state.board_height_offset_mm if board_height_offset_mm is None else float(board_height_offset_mm)

            # Swept volume collision check between current and candidate placement against arm links
            is_safe, col_reason = self.world.check_board_swept_volume_collision(
                new_forward_shift_m=float(forward_shift_mm) / 1000.0,
                new_height_offset_m=cur_z_off / 1000.0,
            )
            if not is_safe:
                return {
                    "success": False,
                    "status": "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR",
                    "error": f"Board swept volume collision: {col_reason}",
                }

            if self.world.get_attached_piece() is not None:
                err = "Cannot change board placement while a piece is attached to gripper"
                return {
                    "success": False,
                    "status": "BOARD_RELOCATION_REJECTED_WORLD_NOT_SETTLED",
                    "error": err,
                    "transient_pieces": [{"id": self.world.get_attached_piece().piece_id, "state": "ATTACHED_TO_GRIPPER"}],
                }

            transient = [
                p_body for p_body in self.world.pieces.values()
                if p_body.physical_state in (PiecePhysicalState.ATTACHED_TO_GRIPPER, PiecePhysicalState.FALLING, PiecePhysicalState.SETTLING)
            ]
            if transient:
                err = "Cannot change board placement while world is not settled (pieces falling/settling/attached)"
                return {
                    "success": False,
                    "status": "BOARD_RELOCATION_REJECTED_WORLD_NOT_SETTLED",
                    "error": err,
                    "transient_pieces": [{"id": p.piece_id, "state": p.physical_state.value} for p in transient],
                }

            with self.acquire_operation_state(RuntimeOperationState.BOARD_ADJUSTMENT):
                new_version = self.placement_state.placement_version + 1
                new_state = BoardPlacementState.compute(
                    forward_shift_mm=float(forward_shift_mm),
                    safe_transit_height_mm=cur_h,
                    board_height_offset_mm=cur_z_off,
                    placement_version=new_version,
                )

                # Relocate in PyBullet world
                self.world.relocate_board(
                    forward_shift_m=new_state.forward_shift_mm / 1000.0,
                    height_offset_m=new_state.board_height_offset_mm / 1000.0,
                )

                self.placement_state = new_state
                self.grid_origin_robot = list(new_state.grid_origin_robot_m)
                self.board_surface_z = new_state.grid_origin_robot_m[2]
                self.backend.set_placement_version(new_version)

                packet = new_state.to_dict()
                analysis_packet = self.placement_analyzer.compute_geometric_precheck(
                    forward_shift_mm=new_state.forward_shift_mm,
                    safe_transit_height_mm=new_state.safe_transit_height_mm,
                    board_surface_mm=new_state.grid_origin_robot_m[2] * 1000.0,
                    placement_version=new_version,
                )
                if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom(packet)
                    self.telemetry.broadcast_custom(analysis_packet)
                    self.telemetry.update_world_state(self.world.get_snapshot())

                return {"success": True, "placement": packet, "analysis": analysis_packet}

    def reset_board_placement(self) -> Dict[str, Any]:
        """Reset board placement to nominal scene configuration."""
        return self.set_board_placement(forward_shift_mm=0.0, safe_transit_height_mm=70.0, board_height_offset_mm=0.0)

    def clear_error(self) -> Dict[str, Any]:
        """Clear error state on robot backend."""
        with self._command_lock:
            self.backend._last_error = None
            if hasattr(self.backend, "_in_error_state"):
                self.backend._in_error_state = False
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom({
                    "type": "error_cleared",
                    "status": "SUCCESS",
                })
            return {"success": True, "status": "ERROR_CLEARED"}

    def reset_robot(self, speed_factor: Optional[float] = None) -> Dict[str, Any]:
        """Safely release any piece, open gripper, and reset robot to HOME pose."""
        with self._command_lock:
            with self.acquire_operation_state(RuntimeOperationState.RESETTING):
                self.backend.stop()
                self.world.release_attached_piece()
                self.backend.set_gripper(False)
                self.backend.reset_to_home(speed_factor=speed_factor)
                self.clear_error()
                self._sync_gripper_to_tcp(self.backend.get_state_snapshot())
                return {"success": True, "status": "ROBOT_RESET_COMPLETE"}

    def reset_board(self) -> Dict[str, Any]:
        """Reset board placement back to nominal scene coordinates."""
        with self._command_lock:
            return self.reset_board_placement()

    def reset_pieces(self) -> Dict[str, Any]:
        """Reset all 32 Xiangqi pieces to standard start layout."""
        with self._command_lock:
            with self.acquire_operation_state(RuntimeOperationState.RESETTING):
                self.world.release_attached_piece()
                self.backend.set_gripper(False)
                if hasattr(self.world, "reset_pieces"):
                    self.world.reset_pieces()
                if hasattr(self.world, "step_until_settled"):
                    self.world.step_until_settled(max_steps=30)
                self._scheduled_drop = None
                self.last_drop_event = None
                if self.telemetry is not None and hasattr(self.telemetry, "update_world_state"):
                    self.telemetry.update_world_state(self.world.get_snapshot())
                return {"success": True, "status": "PIECES_RESET_COMPLETE"}

    def full_reset(self) -> Dict[str, Any]:
        """Convenience alias for reset_all_backend_data."""
        return self.reset_all_backend_data()

    def reset_all_backend_data(self) -> Dict[str, Any]:
        """
        Authoritatively reset all backend data, physics, pieces, robot, and board placement.
        1. Stop any active robot motion.
        2. Detach any piece from gripper and open gripper.
        3. Reset robot joints to HOME pose.
        4. Reset board placement to nominal scene configuration.
        5. Reset all 32 pieces to initial canonical layout.
        6. Step physics until settled (all pieces resting/on_board).
        7. Broadcast updated placement and world state snapshots to 3D Viewer.
        """
        with self._command_lock:
            with self.acquire_operation_state(RuntimeOperationState.RESETTING):
                self._validation_in_progress = False
                self.backend.stop()
                self.world.release_attached_piece()
                self.backend.set_gripper(False)
                self.backend.reset_to_home()
                self.clear_error()

                # Reset board placement (internally relocates PyBullet board & updates placement_state)
                self.reset_board_placement()

                # Reset all pieces to canonical start layout
                if hasattr(self.world, "reset_pieces"):
                    self.world.reset_pieces()
                if hasattr(self.world, "step_until_settled"):
                    self.world.step_until_settled(max_steps=30)

                # Clear any scheduled drop or drop event
                self._scheduled_drop = None
                self.last_drop_event = None

                # Sync gripper to current robot TCP
                self._sync_gripper_to_tcp(self.backend.get_state_snapshot())

                # Broadcast full state update to viewer
                if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom({
                        "type": "backend_data_reset",
                        "status": "SUCCESS",
                        "placement": self.placement_state.to_dict(),
                        "message": "All backend data, pieces, robot pose, and board placement reset to initial state.",
                    })
                    self.telemetry.update_world_state(self.world.get_snapshot())

                logger.info("All backend data and simulation state successfully reset.")
                return {"success": True, "status": "RESET_COMPLETE"}

    def prepare_board_adjustment(self, speed_factor: Optional[float] = None) -> Dict[str, Any]:
        """
        Ensure robot arm is safely in SERVICE_SAFE pose and board area is clear for adjustment.
        """
        with self._command_lock:
            if self._operation_state not in (RuntimeOperationState.IDLE, RuntimeOperationState.BOARD_ADJUSTMENT):
                return {
                    "success": False,
                    "status": "BOARD_ADJUSTMENT_REJECTED_BUSY",
                    "error": f"System currently in state {self._operation_state.value}",
                }

            if self.world.get_attached_piece() is not None:
                return {
                    "success": False,
                    "status": "PREPARE_BOARD_ADJUSTMENT_FAILED",
                    "error": "Cannot prepare board adjustment while piece is attached to gripper. Release piece first.",
                }

            if not self.backend.is_service_safe():
                ok = self.backend.go_service_safe(speed_factor=speed_factor)
                if not ok:
                    return {
                        "success": False,
                        "status": "PREPARE_BOARD_ADJUSTMENT_FAILED",
                        "error": f"Failed to reach SERVICE_SAFE pose: {self.backend._last_error}",
                    }

            self.world.step_until_settled(max_steps=20)
            transient = [
                p_body for p_body in self.world.pieces.values()
                if p_body.physical_state in (PiecePhysicalState.ATTACHED_TO_GRIPPER, PiecePhysicalState.FALLING, PiecePhysicalState.SETTLING)
            ]
            if transient:
                return {
                    "success": False,
                    "status": "PREPARE_BOARD_ADJUSTMENT_FAILED",
                    "error": "World not settled (pieces falling/settling)",
                }

            return {
                "success": True,
                "status": "READY_FOR_BOARD_ADJUSTMENT",
                "service_safe": True,
                "message": "Robot safely parked in SERVICE_SAFE pose. Ready for board placement adjustment.",
            }

    def runtime_go_service_safe(self, speed_factor: Optional[float] = None) -> Dict[str, Any]:
        """Move arm to SERVICE_SAFE joint configuration."""
        with self._command_lock:
            if self._operation_state != RuntimeOperationState.IDLE:
                return {
                    "success": False,
                    "status": "MOTION_REJECTED_BUSY",
                    "error": f"System is currently in state {self._operation_state.value}",
                }

            with self.acquire_operation_state(RuntimeOperationState.SERVICE_MOVE):
                ok = self.backend.go_service_safe(speed_factor=speed_factor)
                if not ok:
                    return {"success": False, "status": "SERVICE_SAFE_FAILED", "error": self.backend._last_error}
                return {"success": True, "status": "SERVICE_SAFE_REACHED"}

    def runtime_retract_from_board(self, speed_factor: Optional[float] = None) -> Dict[str, Any]:
        """Safely lift TCP vertically then move arm to SERVICE_SAFE."""
        with self._command_lock:
            if self._operation_state != RuntimeOperationState.IDLE:
                return {
                    "success": False,
                    "status": "MOTION_REJECTED_BUSY",
                    "error": f"System is currently in state {self._operation_state.value}",
                }

            with self.acquire_operation_state(RuntimeOperationState.SERVICE_MOVE):
                curr_tcp = list(self.backend.get_state_snapshot().tcp_pose_mm_deg)
                safe_z_mm = (self.board_surface_z + self.placement_state.safe_transit_height_mm / 1000.0) * 1000.0 + 30.0
                if curr_tcp[2] < safe_z_mm:
                    curr_tcp[2] = safe_z_mm
                    self.backend.move_cartesian(curr_tcp, speed_factor=speed_factor)
                ok = self.backend.go_service_safe(speed_factor=speed_factor)
                if not ok:
                    return {"success": False, "status": "RETRACT_FAILED", "error": self.backend._last_error}
                return {"success": True, "status": "RETRACT_COMPLETE"}

    def runtime_jog_joint(
        self,
        joint_idx: int,
        delta_deg: float,
        speed_factor: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Jog a single joint by delta_deg while validating limits and collision guard."""
        with self._command_lock:
            if self._operation_state != RuntimeOperationState.IDLE:
                return {
                    "success": False,
                    "status": "MOTION_REJECTED_BUSY",
                    "error": f"System is currently in state {self._operation_state.value}",
                }

            with self.acquire_operation_state(RuntimeOperationState.SERVICE_MOVE):
                ok = self.backend.jog_joint(joint_idx, delta_deg, speed_factor=speed_factor)
                if not ok:
                    err = self.backend._last_error or "Jog joint rejected"
                    status = "JOG_REJECTED_COLLISION" if "collid" in err.lower() else "JOG_REJECTED_LIMIT"
                    return {"success": False, "status": status, "error": err}
                return {"success": True, "status": "JOG_COMPLETE", "joints_deg": list(self.backend.get_state_snapshot().joints_deg)}

    def runtime_jog_tcp(
        self,
        axis: Optional[str] = None,
        delta_xyz_mm: Optional[Sequence[float]] = None,
        delta_rpy_deg: Optional[Sequence[float]] = None,
        step_mm: float = 5.0,
        step_deg: float = 2.0,
        speed_factor: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Jog TCP in Cartesian space along axis or deltas with collision guard protection."""
        with self._command_lock:
            if self._operation_state != RuntimeOperationState.IDLE:
                return {
                    "success": False,
                    "status": "MOTION_REJECTED_BUSY",
                    "error": f"System is currently in state {self._operation_state.value}",
                }

            dx, dy, dz = 0.0, 0.0, 0.0
            drx, dry, drz = 0.0, 0.0, 0.0
            if axis:
                ax = axis.strip().upper()
                if ax == "+X": dx = step_mm
                elif ax == "-X": dx = -step_mm
                elif ax == "+Y": dy = step_mm
                elif ax == "-Y": dy = -step_mm
                elif ax == "+Z": dz = step_mm
                elif ax == "-Z": dz = -step_mm
                elif ax == "+RX": drx = step_deg
                elif ax == "-RX": drx = -step_deg
                elif ax == "+RY": dry = step_deg
                elif ax == "-RY": dry = -step_deg
                elif ax == "+RZ": drz = step_deg
                elif ax == "-RZ": drz = -step_deg

            if delta_xyz_mm is not None:
                dx += delta_xyz_mm[0] if len(delta_xyz_mm) > 0 else 0.0
                dy += delta_xyz_mm[1] if len(delta_xyz_mm) > 1 else 0.0
                dz += delta_xyz_mm[2] if len(delta_xyz_mm) > 2 else 0.0

            if delta_rpy_deg is not None:
                drx += delta_rpy_deg[0] if len(delta_rpy_deg) > 0 else 0.0
                dry += delta_rpy_deg[1] if len(delta_rpy_deg) > 1 else 0.0
                drz += delta_rpy_deg[2] if len(delta_rpy_deg) > 2 else 0.0

            with self.acquire_operation_state(RuntimeOperationState.SERVICE_MOVE):
                ok = self.backend.jog_tcp([dx, dy, dz], [drx, dry, drz], speed_factor=speed_factor)
                if not ok:
                    err = self.backend._last_error or "Jog TCP rejected"
                    status = "JOG_REJECTED_COLLISION" if "collid" in err.lower() else "JOG_REJECTED_IK"
                    return {"success": False, "status": status, "error": err}
                return {"success": True, "status": "JOG_COMPLETE", "tcp_pose": list(self.backend.get_state_snapshot().tcp_pose_mm_deg)}

    def validate_board_placement(
        self,
        expected_placement_version: Optional[int] = None,
        placement_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execution-equivalent 90-cell local trajectory validation at runtime.
        For every one of 90 cells:
          1. Approach endpoint IK & collision
          2. LAND MoveL (Approach -> Grasp) Cartesian trajectory
          3. Grasp endpoint IK & collision (target piece allowed)
          4. LIFT MoveL (Grasp -> Approach) Cartesian trajectory

        Guarantees:
        - Strict state invariance: original PyBullet robot joint state and backend state
          are snapshotted and guaranteed restored in finally.
        - Placement version atomicity: rejects with STALE_VALIDATION_RESULT if placement
          version changed during validation.
        - Trajectory-level collision checking using backend.plan_cartesian() without commit.
        """
        exp_ver = placement_version if placement_version is not None else expected_placement_version
        if exp_ver is not None and exp_ver != self.placement_state.placement_version:
            stale_res = {
                "type": "placement_validation_result",
                "status": "STALE_VALIDATION_RESULT",
                "error": (
                    f"Validation aborted: placement version mismatch (expected {exp_ver}, "
                    f"current {self.placement_state.placement_version})"
                ),
                "placement_version": exp_ver,
                "current_placement_version": self.placement_state.placement_version,
                "all_passed": False,
                "total_cells": 90,
            }
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom(stale_res)
            return stale_res

        # Concurrency mutual exclusion: reject if robot is moving or active in trajectory or not in IDLE
        is_busy = (
            self._operation_state != RuntimeOperationState.IDLE
            or getattr(self.backend, "_motion_state", None) == "MOVING"
            or getattr(self.backend, "_trajectory_stage", None) not in (None, "IDLE", "COMPLETE")
        )
        if is_busy:
            if getattr(self.backend, "_motion_state", None) == "MOVING":
                busy_reason = "robot is MOVING"
            elif getattr(self.backend, "_trajectory_stage", None) not in (None, "IDLE", "COMPLETE"):
                busy_reason = f"active trajectory ({getattr(self.backend, '_trajectory_stage', None)})"
            else:
                busy_reason = f"system currently in state {self._operation_state.value}"
            busy_res = {
                "type": "placement_validation_result",
                "success": False,
                "status": "VALIDATION_REJECTED_BUSY",
                "error": f"Validation rejected: {busy_reason}",
                "reason": f"Validation rejected: {busy_reason}",
                "placement_version": self.placement_state.placement_version,
                "all_passed": False,
                "total_cells": 90,
            }
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom(busy_res)
            return busy_res

        v_start = self.placement_state.placement_version
        d = self.placement_state.forward_shift_mm
        H = self.placement_state.safe_transit_height_mm
        z_off = self.placement_state.board_height_offset_mm
        board_z = self.board_surface_z
        piece_h = self.geom.piece_height_mm / 1000.0
        z_grasp = board_z + piece_h / 2.0
        z_app = board_z + H / 1000.0

        # Snapshot authoritative state for guaranteed restoration (Section K)
        world = self.world
        client = world.client_id
        q_bullet_orig = [p.getJointState(world.robot_body_id, j, physicsClientId=client)[0] for j in range(6)]
        snap_orig = self.backend.get_state_snapshot()
        backend_q_orig = np.array(self.backend._current_joints_rad, copy=True)

        self._validation_in_progress = True
        self._physics_query_lock.acquire()
        try:
            with self.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
                grasp_ik_ok = 0
                app_ik_ok = 0
                grasp_col_free = 0
                app_col_free = 0
                land_traj_ok = 0
                lift_traj_ok = 0
                passed_cells = 0
                failed_cells = []

                for r in range(10):
                    for c in range(9):
                        # Check version mid-validation for early stale rejection
                        if self.placement_state.placement_version != v_start:
                            break

                        pos_gr = self.cell_to_robot_xyz_m(r, c, z_grasp)
                        pos_ap = self.cell_to_robot_xyz_m(r, c, z_app)
                        pose_gr_mm = [v * 1000.0 for v in pos_gr] + list(self.target_tool_euler_deg)
                        pose_ap_mm = [v * 1000.0 for v in pos_ap] + list(self.target_tool_euler_deg)

                        seed_info = self.reachability_dataset.get((r, c))
                        seed_app = np.deg2rad(seed_info["approach_joints_deg"]) if seed_info and "approach_joints_deg" in seed_info else None
                        seed_gr = np.deg2rad(seed_info["grasp_joints_deg"]) if seed_info and "grasp_joints_deg" in seed_info else None

                        # Resolve candidate target piece on cell if any (replaces wildcard '*')
                        target_piece_id = self._get_piece_at_cell(r, c)

                        # 1. Approach endpoint IK
                        ik_ap = self.backend.solve_tcp_ik(pose_ap_mm, seed_joints=seed_app, allow_multi_seed=True)
                        col_ap_safe = False
                        col_ap_reason = None
                        if ik_ap.success:
                            app_ik_ok += 1
                            col_ap = self.collision_guard.validate_configuration(ik_ap.joints_rad, restore_state=True)
                            if col_ap.safe:
                                app_col_free += 1
                                col_ap_safe = True
                            else:
                                col_ap_reason = col_ap.failure_reason

                        # 2. LAND MoveL trajectory (Approach -> Grasp)
                        land_safe = False
                        land_reason = None
                        land_plan = None
                        if ik_ap.success and col_ap_safe:
                            land_plan = self.backend.plan_cartesian(
                                start_q=ik_ap.joints_rad,
                                target_pose_mm_deg=pose_gr_mm,
                                samples=20,
                                allowed_grasp_piece_id=target_piece_id,
                                check_collision=True,
                            )
                            if land_plan.success:
                                land_traj_ok += 1
                                land_safe = True
                            else:
                                land_reason = land_plan.failure_reason

                        # 3. Grasp endpoint IK & collision
                        ik_gr = self.backend.solve_tcp_ik(pose_gr_mm, seed_joints=seed_gr, allow_multi_seed=True)
                        col_gr_safe = False
                        col_gr_reason = None
                        if ik_gr.success:
                            grasp_ik_ok += 1
                            col_gr = self.collision_guard.validate_configuration(
                                ik_gr.joints_rad, allowed_grasp_piece_id=target_piece_id, restore_state=True
                            )
                            if col_gr.safe:
                                grasp_col_free += 1
                                col_gr_safe = True
                            else:
                                col_gr_reason = col_gr.failure_reason

                        # 4. LIFT MoveL trajectory (Grasp -> Approach)
                        lift_safe = False
                        lift_reason = None
                        lift_plan = None
                        start_q_lift = land_plan.final_q if (land_plan and land_plan.success and land_plan.final_q is not None) else (
                            ik_gr.joints_rad if ik_gr.success else None
                        )
                        if start_q_lift is not None and col_gr_safe:
                            lift_plan = self.backend.plan_cartesian(
                                start_q=start_q_lift,
                                target_pose_mm_deg=pose_ap_mm,
                                samples=20,
                                allowed_grasp_piece_id=target_piece_id,
                                check_collision=True,
                            )
                            if lift_plan.success:
                                lift_traj_ok += 1
                                lift_safe = True
                            else:
                                lift_reason = lift_plan.failure_reason

                        cell_passed = (
                            ik_ap.success and col_ap_safe and land_safe and
                            ik_gr.success and col_gr_safe and lift_safe
                        )

                        if cell_passed:
                            passed_cells += 1
                        else:
                            failure_parts = []
                            if not ik_ap.success:
                                failure_parts.append("Approach IK failed")
                            elif not col_ap_safe:
                                failure_parts.append(f"Approach collision: {col_ap_reason}")
                            if not land_safe:
                                failure_parts.append(f"LAND MoveL: {land_reason}")
                            if not ik_gr.success:
                                failure_parts.append("Grasp IK failed")
                            elif not col_gr_safe:
                                failure_parts.append(f"Grasp collision: {col_gr_reason}")
                            if not lift_safe:
                                failure_parts.append(f"LIFT MoveL: {lift_reason}")

                            stage_failed = (
                                "APPROACH" if not (ik_ap.success and col_ap_safe) else (
                                    "LAND" if not land_safe else (
                                        "GRASP" if not (ik_gr.success and col_gr_safe) else "LIFT"
                                    )
                                )
                            )
                            fail_entry = {
                                "row": r,
                                "col": c,
                                "stage": stage_failed,
                                "reason": " | ".join(failure_parts),
                                "approach_ik_ok": ik_ap.success,
                                "approach_col_safe": col_ap_safe,
                                "land_safe": land_safe,
                                "grasp_ik_ok": ik_gr.success,
                                "grasp_col_safe": col_gr_safe,
                                "lift_safe": lift_safe,
                            }
                            if land_plan and not land_plan.success:
                                fail_entry["sample_idx"] = land_plan.first_failing_sample
                                fail_entry["first_failing_sample"] = land_plan.first_failing_sample
                                fail_entry["q_failed"] = land_plan.q_failed
                                fail_entry["colliding_links"] = land_plan.colliding_links_or_bodies
                            elif lift_plan and not lift_plan.success:
                                fail_entry["sample_idx"] = lift_plan.first_failing_sample
                                fail_entry["first_failing_sample"] = lift_plan.first_failing_sample
                                fail_entry["q_failed"] = lift_plan.q_failed
                                fail_entry["colliding_links"] = lift_plan.colliding_links_or_bodies
                            failed_cells.append(fail_entry)

            # Check placement version atomicity
            if self.placement_state.placement_version != v_start:
                stale_res = {
                    "type": "placement_validation_result",
                    "status": "STALE_VALIDATION_RESULT",
                    "error": (
                        f"Validation aborted: placement version changed from v{v_start} "
                        f"to v{self.placement_state.placement_version}"
                    ),
                    "placement_version": v_start,
                    "current_placement_version": self.placement_state.placement_version,
                    "all_passed": False,
                    "total_cells": 90,
                }
                if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom(stale_res)
                return stale_res

            all_passed = (passed_cells == 90)
            res = {
                "type": "placement_validation_result",
                "validation_scope": "local_cell_trajectories",
                "status": "LOCAL_CELL_TRAJECTORIES_PASS" if all_passed else "FAIL",
                "placement_version": v_start,
                "forward_shift_mm": d,
                "safe_transit_height_mm": H,
                "board_height_offset_mm": z_off,
                "grasp_ik_count": grasp_ik_ok,
                "approach_ik_count": app_ik_ok,
                "grasp_collision_free_count": grasp_col_free,
                "approach_collision_free_count": app_col_free,
                "land_trajectory_safe_count": land_traj_ok,
                "land_move_passed_count": land_traj_ok,
                "lift_trajectory_safe_count": lift_traj_ok,
                "lift_move_passed_count": lift_traj_ok,
                "passed_cells_count": passed_cells,
                "total_cells": 90,
                "all_passed": all_passed,
                "failed_cells": failed_cells,
            }
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom(res)
            return res

        finally:
            try:
                # Guaranteed state restoration without mutating gripper history
                world.sync_robot_collision_configuration(q_bullet_orig)
                self.backend._current_joints_rad = np.array(backend_q_orig, copy=True)
                self.backend._current_joints_deg = [round(math.degrees(float(val)), 3) for val in backend_q_orig]
                self.backend._flange_pose_mm_deg = self.backend._compute_flange_pose_mm_deg(backend_q_orig)
                self.backend._tcp_pose_mm_deg = list(snap_orig.tcp_pose_mm_deg)
                self.backend._motion_state = snap_orig.motion_state
            finally:
                self._validation_in_progress = False
                self._physics_query_lock.release()

    def validate_full_board_routes(
        self,
        sample_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Full Board Route Dry-Run Validation (Section J).
        Validates all 90*89 = 8010 ordered routes (or sample_limit routes):
          source grasp -> LIFT -> source approach -> TRANSIT -> dest approach -> LAND -> dest grasp
        Uses plan_cartesian() without state commit.
        Leaves PyBullet and backend robot state 100% unchanged.
        """
        # Concurrency mutual exclusion: reject if robot is moving or active in trajectory or system not in IDLE
        is_busy = (
            self._operation_state != RuntimeOperationState.IDLE
            or getattr(self.backend, "_motion_state", None) == "MOVING"
            or getattr(self.backend, "_trajectory_stage", None) not in (None, "IDLE", "COMPLETE")
        )
        if is_busy:
            if getattr(self.backend, "_motion_state", None) == "MOVING":
                busy_reason = "robot is MOVING"
            elif getattr(self.backend, "_trajectory_stage", None) not in (None, "IDLE", "COMPLETE"):
                busy_reason = f"active trajectory ({getattr(self.backend, '_trajectory_stage', None)})"
            else:
                busy_reason = f"system currently in state {self._operation_state.value}"
            busy_res = {
                "type": "full_route_validation_result",
                "success": False,
                "status": "VALIDATION_REJECTED_BUSY",
                "error": f"Validation rejected: {busy_reason}",
                "reason": f"Validation rejected: {busy_reason}",
                "placement_version": self.placement_state.placement_version,
                "all_passed": False,
                "all_routes_safe": False,
                "total_routes": 0,
            }
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom(busy_res)
            return busy_res

        v_start = self.placement_state.placement_version
        world = self.world
        client = world.client_id
        q_bullet_orig = [p.getJointState(world.robot_body_id, j, physicsClientId=client)[0] for j in range(6)]
        snap_orig = self.backend.get_state_snapshot()
        backend_q_orig = np.array(self.backend._current_joints_rad, copy=True)

        self._validation_in_progress = True
        self._physics_query_lock.acquire()
        try:
            with self.acquire_operation_state(RuntimeOperationState.VALIDATING_ROUTES):
                board_z = self.board_surface_z
                piece_h = self.geom.piece_height_mm / 1000.0
                z_grasp = board_z + piece_h / 2.0
                z_transit = board_z + (self.placement_state.safe_transit_height_mm / 1000.0)

                # Step 1: Pre-plan and cache Approach IK, Grasp IK, LIFT, and LAND for all 90 cells
                cell_plans = {}
                for r in range(10):
                    for c in range(9):
                        pos_gr = self.cell_to_robot_xyz_m(r, c, z_grasp)
                        pos_ap = self.cell_to_robot_xyz_m(r, c, z_transit)
                        pose_gr_mm = [v * 1000.0 for v in pos_gr] + list(self.target_tool_euler_deg)
                        pose_ap_mm = [v * 1000.0 for v in pos_ap] + list(self.target_tool_euler_deg)

                        seed_info = self.reachability_dataset.get((r, c))
                        seed_app = np.deg2rad(seed_info["approach_joints_deg"]) if seed_info and "approach_joints_deg" in seed_info else None
                        seed_gr = np.deg2rad(seed_info["grasp_joints_deg"]) if seed_info and "grasp_joints_deg" in seed_info else None

                        # Resolve explicit piece ID for candidate cell
                        target_piece_id = self._get_piece_at_cell(r, c)

                        ik_ap = self.backend.solve_tcp_ik(pose_ap_mm, seed_joints=seed_app, allow_multi_seed=True)
                        ik_gr = self.backend.solve_tcp_ik(pose_gr_mm, seed_joints=seed_gr, allow_multi_seed=True)

                        lift_plan = None
                        land_plan = None
                        if ik_gr.success:
                            lift_plan = self.backend.plan_cartesian(
                                start_q=ik_gr.joints_rad,
                                target_pose_mm_deg=pose_ap_mm,
                                samples=15,
                                allowed_grasp_piece_id=target_piece_id,
                                check_collision=True,
                            )
                        if ik_ap.success:
                            land_plan = self.backend.plan_cartesian(
                                start_q=ik_ap.joints_rad,
                                target_pose_mm_deg=pose_gr_mm,
                                samples=15,
                                allowed_grasp_piece_id=target_piece_id,
                                check_collision=True,
                            )

                        cell_plans[(r, c)] = {
                            "ik_ap": ik_ap,
                            "ik_gr": ik_gr,
                            "pose_ap_mm": pose_ap_mm,
                            "pose_gr_mm": pose_gr_mm,
                            "lift_plan": lift_plan,
                            "land_plan": land_plan,
                        }

                # Step 2: Validate routes
                all_cells = [(r, c) for r in range(10) for c in range(9)]
                routes_to_test = []
                for src in all_cells:
                    for dst in all_cells:
                        if src != dst:
                            routes_to_test.append((src, dst))

                if sample_limit is not None and sample_limit < len(routes_to_test):
                    # Sample evenly across the route set
                    step = len(routes_to_test) // sample_limit
                    routes_to_test = routes_to_test[::step][:sample_limit]

                total_routes = len(routes_to_test)
                passed_routes = 0
                failed_routes = 0
                worst_route = None
                first_col_stage = None
                col_pair = None
                min_margin_deg = float("inf")
                worst_cond = 1.0

                for src, dst in routes_to_test:
                    if self.placement_state.placement_version != v_start:
                        break

                    src_cp = cell_plans[src]
                    dst_cp = cell_plans[dst]

                    # Stage 1: LIFT
                    if not (src_cp["lift_plan"] and src_cp["lift_plan"].success):
                        failed_routes += 1
                        if worst_route is None:
                            worst_route = {"src": list(src), "dst": list(dst), "stage": "LIFT"}
                            first_col_stage = "LIFT"
                            col_pair = src_cp["lift_plan"].colliding_links_or_bodies if src_cp["lift_plan"] else "Grasp IK failed"
                        continue

                    q_after_lift = src_cp["lift_plan"].final_q

                    # Stage 2: TRANSIT (MoveL at transit height) - carried piece is from src
                    src_piece_id = self._get_piece_at_cell(src[0], src[1])
                    transit_plan = self.backend.plan_cartesian(
                        start_q=q_after_lift,
                        target_pose_mm_deg=dst_cp["pose_ap_mm"],
                        samples=15,
                        allowed_grasp_piece_id=src_piece_id,
                        check_collision=True,
                    )
                    if not transit_plan.success:
                        failed_routes += 1
                        if worst_route is None:
                            worst_route = {"src": list(src), "dst": list(dst), "stage": "TRANSIT"}
                            first_col_stage = "TRANSIT"
                            col_pair = transit_plan.colliding_links_or_bodies
                        continue

                    # Stage 3: LAND
                    if not (dst_cp["land_plan"] and dst_cp["land_plan"].success):
                        failed_routes += 1
                        if worst_route is None:
                            worst_route = {"src": list(src), "dst": list(dst), "stage": "LAND"}
                            first_col_stage = "LAND"
                            col_pair = dst_cp["land_plan"].colliding_links_or_bodies if dst_cp["land_plan"] else "Approach IK failed"
                        continue

                    passed_routes += 1
                    if transit_plan.min_joint_margin_deg is not None:
                        min_margin_deg = min(min_margin_deg, transit_plan.min_joint_margin_deg)
                    if transit_plan.worst_condition_number is not None:
                        worst_cond = max(worst_cond, transit_plan.worst_condition_number)

            all_routes_safe = (passed_routes == total_routes and total_routes > 0)
            res = {
                "type": "full_route_validation_result",
                "total_routes": total_routes,
                "passed_routes": passed_routes,
                "failed_routes": failed_routes,
                "all_routes_safe": all_routes_safe,
                "status": "FULL_BOARD_ROUTE_SAFE" if all_routes_safe else "FAIL",
                "worst_route": worst_route,
                "first_collision_stage": first_col_stage,
                "collision_pair": col_pair,
                "min_joint_margin_deg": round(min_margin_deg, 2) if math.isfinite(min_margin_deg) else None,
                "worst_condition_number": round(worst_cond, 2) if math.isfinite(worst_cond) else None,
                "placement_version": v_start,
            }
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom(res)
            return res

        finally:
            try:
                # Guaranteed state restoration without mutating gripper history
                world.sync_robot_collision_configuration(q_bullet_orig)
                self.backend._current_joints_rad = np.array(backend_q_orig, copy=True)
                self.backend._current_joints_deg = [round(math.degrees(float(val)), 3) for val in backend_q_orig]
                self.backend._flange_pose_mm_deg = self.backend._compute_flange_pose_mm_deg(backend_q_orig)
                self.backend._tcp_pose_mm_deg = list(snap_orig.tcp_pose_mm_deg)
                self.backend._motion_state = snap_orig.motion_state
            finally:
                self._validation_in_progress = False
                self._physics_query_lock.release()

    def set_telemetry(self, telemetry: TelemetryPublisher) -> None:
        """Attach telemetry publisher and register incoming command callback."""
        self.telemetry = telemetry
        if self.backend is not None:
            self.backend.telemetry_publisher = telemetry
        if self.telemetry is not None:
            self.telemetry.register_command_handler(self._handle_client_command)
            # Broadcast initial authoritative board placement and placement analysis
            if hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom(self.placement_state.to_dict())
                analysis_packet = self.placement_analyzer.compute_geometric_precheck(
                    forward_shift_mm=self.placement_state.forward_shift_mm,
                    safe_transit_height_mm=self.placement_state.safe_transit_height_mm,
                    board_surface_mm=self.board_surface_z * 1000.0,
                    placement_version=self.placement_state.placement_version,
                )
                self.telemetry.broadcast_custom(analysis_packet)

    def _handle_client_command(self, cmd: Dict[str, Any]) -> None:
        """Handle incoming command from viewer or external WebSocket client."""
        action = cmd.get("command") or cmd.get("action")
        if not action:
            return

        action = str(action).upper()
        if action == "EXECUTE_3STAGE":
            src = cmd.get("src")
            dst = cmd.get("dst")
            p_ver = cmd.get("placement_version")
            if src is not None and dst is not None and len(src) == 2 and len(dst) == 2:
                threading.Thread(
                    target=self._run_trajectory_async,
                    args=((int(src[0]), int(src[1])), (int(dst[0]), int(dst[1])), p_ver),
                    daemon=True,
                ).start()
        elif action == "SET_GRIPPER":
            closed = bool(cmd.get("closed", False))
            self.backend.set_gripper(closed)
        elif action == "RESET":
            self.backend.reset_to_home()
        elif action == "CLEAR_ERROR":
            self.clear_error()
        elif action == "RESET_ROBOT":
            speed = cmd.get("speed_factor")
            threading.Thread(target=self.reset_robot, kwargs={"speed_factor": speed}, daemon=True).start()
        elif action == "RESET_BOARD":
            self.reset_board()
        elif action == "RESET_PIECES":
            threading.Thread(target=self.reset_pieces, daemon=True).start()
        elif action in ("FULL_RESET", "RESET_ALL_BACKEND_DATA", "RESET_BACKEND_DATA", "RESTART_BACKEND_DATA"):
            self.full_reset()
        elif action == "GO_SERVICE_SAFE":
            speed = cmd.get("speed_factor")
            def _task_safe():
                res = self.runtime_go_service_safe(speed_factor=speed)
                if not res.get("success") and self.telemetry and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom({"type": "error", "message": res.get("error", "Go Service Safe rejected")})
            threading.Thread(target=_task_safe, daemon=True).start()
        elif action == "RETRACT_FROM_BOARD":
            speed = cmd.get("speed_factor")
            def _task_retract():
                res = self.runtime_retract_from_board(speed_factor=speed)
                if not res.get("success") and self.telemetry and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom({"type": "error", "message": res.get("error", "Retract rejected")})
            threading.Thread(target=_task_retract, daemon=True).start()
        elif action == "PREPARE_BOARD_ADJUSTMENT":
            speed = cmd.get("speed_factor")
            def _task_prep():
                res = self.prepare_board_adjustment(speed_factor=speed)
                if not res.get("success") and self.telemetry and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom({"type": "error", "message": res.get("error", "Prepare Board Adjustment rejected")})
            threading.Thread(target=_task_prep, daemon=True).start()
        elif action == "JOG_TCP":
            axis = cmd.get("axis")
            delta_xyz = cmd.get("delta_xyz_mm")
            delta_rpy = cmd.get("delta_rpy_deg")
            step_mm = float(cmd.get("step_mm", 5.0))
            step_deg = float(cmd.get("step_deg", 2.0))
            speed = cmd.get("speed_factor", self.backend.default_speed_factor)
            def _task_jog_tcp():
                res = self.runtime_jog_tcp(axis=axis, delta_xyz_mm=delta_xyz, delta_rpy_deg=delta_rpy, step_mm=step_mm, step_deg=step_deg, speed_factor=speed)
                if not res.get("success") and self.telemetry and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom({"type": "error", "message": res.get("error", "Jog TCP rejected")})
            threading.Thread(target=_task_jog_tcp, daemon=True).start()
        elif action == "JOG_JOINT":
            j_idx = int(cmd.get("joint_idx", 0))
            d_deg = float(cmd.get("delta_deg", 0.0))
            speed = cmd.get("speed_factor", self.backend.default_speed_factor)
            def _task_jog_joint():
                res = self.runtime_jog_joint(j_idx, d_deg, speed_factor=speed)
                if not res.get("success") and self.telemetry and hasattr(self.telemetry, "broadcast_custom"):
                    self.telemetry.broadcast_custom({"type": "error", "message": res.get("error", "Jog Joint rejected")})
            threading.Thread(target=_task_jog_joint, daemon=True).start()
        elif action == "STOP":
            self.backend.stop()
        elif action == "SET_BOARD_PLACEMENT":
            d = float(cmd.get("forward_shift_mm", 0.0))
            h = float(cmd.get("safe_transit_height_mm", self.placement_state.safe_transit_height_mm))
            z_off = float(cmd.get("board_height_offset_mm", self.placement_state.board_height_offset_mm))
            res = self.set_board_placement(forward_shift_mm=d, safe_transit_height_mm=h, board_height_offset_mm=z_off)
            if not res.get("success") and self.telemetry and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom({
                    "type": "error",
                    "message": res.get("error"),
                })
        elif action == "RESET_BOARD_PLACEMENT":
            self.reset_board_placement()
        elif action == "VALIDATE_BOARD_PLACEMENT":
            threading.Thread(target=self.validate_board_placement, daemon=True).start()
        elif action == "VALIDATE_FULL_BOARD_ROUTES":
            limit = cmd.get("sample_limit")
            threading.Thread(target=self.validate_full_board_routes, args=(limit,), daemon=True).start()
        elif action == "MOVE_JOINT":
            joints_deg = cmd.get("joints_deg")
            speed = cmd.get("speed_factor", self.backend.default_speed_factor)
            if joints_deg and len(joints_deg) == 6:
                threading.Thread(target=self.backend.move_joint, args=(joints_deg, speed), daemon=True).start()
        elif action == "SET_COLLISION_GUARD":
            enabled = bool(cmd.get("enabled", True))
            self.backend.set_collision_guard_enabled(enabled)
            if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
                self.telemetry.broadcast_custom({
                    "type": "collision_guard_status",
                    "enabled": self.backend.collision_guard_enabled,
                })

    def _run_trajectory_async(self, src: Tuple[int, int], dst: Tuple[int, int], planned_version: Optional[int] = None) -> None:
        """Execute trajectory asynchronously and broadcast authoritative completion packet."""
        res = self.execute_3stage_trajectory(src, dst, planned_placement_version=planned_version)
        if self.telemetry is not None and hasattr(self.telemetry, "broadcast_custom"):
            self.telemetry.broadcast_custom({
                "type": "trajectory_result",
                "success": bool(res.get("success", False)),
                "failed_stage": res.get("failed_stage"),
                "error": res.get("error"),
                "src": list(src),
                "dst": list(dst),
                "placement_version": res.get("placement_version", self.placement_state.placement_version),
            })

    def execute_3stage_trajectory(
        self,
        src_cell: Tuple[int, int],
        dst_cell: Tuple[int, int],
        speed_factor: Optional[float] = None,
        samples_per_stage: int = 20,
        planned_placement_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute authoritative 3-stage Pick & Place Cartesian trajectory:
        0. PREPOSITION: Move robot to source grasp pose (fail-fast validation before lift)
        1. LIFT: Cartesian MoveL (same X/Y, increasing Z from grasp to transit height)
        2. TRANSIT: Cartesian MoveL (source transit -> target transit at constant safe Z)
        3. LAND: Cartesian MoveL (same target X/Y, decreasing Z from transit to target grasp)

        Uses downward tool orientation [180.0, 0.0, 90.0] deg.
        Pre-validates collision guard, enforces placement version consistency,
        solves on-demand IK, and guarantees allowed_grasp_piece_id cleanup.
        """
        with self._command_lock:
            if getattr(self, "_validation_in_progress", False) or self._operation_state != RuntimeOperationState.IDLE:
                err_msg = f"System busy ({self._operation_state.value})" if self._operation_state != RuntimeOperationState.IDLE else "Validation actively in progress"
                self.backend._last_error = err_msg
                return {
                    "success": False,
                    "status": "MOTION_REJECTED_BUSY",
                    "failed_stage": "PREPOSITION",
                    "error": err_msg,
                    "placement_version": self.placement_state.placement_version,
                }
            with self.acquire_operation_state(RuntimeOperationState.MOTION):
                return self._execute_3stage_trajectory_impl(
                    src_cell=src_cell,
                    dst_cell=dst_cell,
                    speed_factor=speed_factor,
                    samples_per_stage=samples_per_stage,
                    planned_placement_version=planned_placement_version,
                )

    def _execute_3stage_trajectory_impl(
        self,
        src_cell: Tuple[int, int],
        dst_cell: Tuple[int, int],
        speed_factor: Optional[float] = None,
        samples_per_stage: int = 20,
        planned_placement_version: Optional[int] = None,
    ) -> Dict[str, Any]:
            current_ver = self.placement_state.placement_version
            if planned_placement_version is not None and planned_placement_version != current_ver:
                err_msg = (
                    f"Trajectory rejected: Stale placement version "
                    f"(planned={planned_placement_version}, current={current_ver})"
                )
                self.backend._last_error = err_msg
                return {
                    "success": False,
                    "failed_stage": "PRECHECK",
                    "error": err_msg,
                    "placement_version": current_ver,
                }

            r_src, c_src = int(src_cell[0]), int(src_cell[1])
            r_dst, c_dst = int(dst_cell[0]), int(dst_cell[1])

            # Canonical heights derived from authoritative BoardPlacementState
            board_z = self.board_surface_z
            piece_h = self.geom.piece_height_mm / 1000.0
            z_grasp = board_z + piece_h / 2.0
            z_transit = board_z + (self.placement_state.safe_transit_height_mm / 1000.0)
            tool_rpy = list(self.target_tool_euler_deg)

            src_grasp_m = self.cell_to_robot_xyz_m(r_src, c_src, z_grasp)
            src_app_m = self.cell_to_robot_xyz_m(r_src, c_src, z_transit)
            dst_app_m = self.cell_to_robot_xyz_m(r_dst, c_dst, z_transit)
            dst_grasp_m = self.cell_to_robot_xyz_m(r_dst, c_dst, z_grasp)

            to_mm_deg = lambda p_m: [p_m[0] * 1000.0, p_m[1] * 1000.0, p_m[2] * 1000.0] + tool_rpy

            samples_per_stage = max(10, int(samples_per_stage))

            # On-demand IK validation with seed warm-start from dataset if available
            src_seed_info = self.reachability_dataset.get((r_src, c_src))
            dst_seed_info = self.reachability_dataset.get((r_dst, c_dst))
            seed_src_app = np.deg2rad(src_seed_info["approach_joints_deg"]) if (src_seed_info and "approach_joints_deg" in src_seed_info) else None
            seed_src_gr = np.deg2rad(src_seed_info["grasp_joints_deg"]) if (src_seed_info and "grasp_joints_deg" in src_seed_info) else None
            seed_dst_app = np.deg2rad(dst_seed_info["approach_joints_deg"]) if (dst_seed_info and "approach_joints_deg" in dst_seed_info) else None
            seed_dst_gr = np.deg2rad(dst_seed_info["grasp_joints_deg"]) if (dst_seed_info and "grasp_joints_deg" in dst_seed_info) else None

            src_grasp_pose_mm = to_mm_deg(src_grasp_m)
            src_app_pose_mm = to_mm_deg(src_app_m)
            dst_grasp_pose_mm = to_mm_deg(dst_grasp_m)
            dst_app_pose_mm = to_mm_deg(dst_app_m)

            self.backend.set_trajectory_stage("PREPOSITION")

            ik_src_app = self.backend.solve_tcp_ik(src_app_pose_mm, seed_joints=seed_src_app, allow_multi_seed=True)
            ik_src_gr = self.backend.solve_tcp_ik(src_grasp_pose_mm, seed_joints=seed_src_gr, allow_multi_seed=True)
            ik_dst_app = self.backend.solve_tcp_ik(dst_app_pose_mm, seed_joints=seed_dst_app, allow_multi_seed=True)
            ik_dst_gr = self.backend.solve_tcp_ik(dst_grasp_pose_mm, seed_joints=seed_dst_gr, allow_multi_seed=True)

            if not ik_src_gr.success or not ik_src_app.success:
                err_msg = f"Preposition rejected: Source cell {src_cell} is unreachable at current board placement"
                self.backend._last_error = err_msg
                self.backend.set_trajectory_stage("IDLE")
                return {"success": False, "failed_stage": "PREPOSITION", "error": err_msg, "placement_version": current_ver}

            if not ik_dst_gr.success or not ik_dst_app.success:
                err_msg = f"Preposition rejected: Destination cell {dst_cell} is unreachable at current board placement"
                self.backend._last_error = err_msg
                self.backend.set_trajectory_stage("IDLE")
                return {"success": False, "failed_stage": "PREPOSITION", "error": err_msg, "placement_version": current_ver}

            try:
                # Detect if there is a piece at src_cell to allow grasp without proxy collision
                piece_at_src = None
                if hasattr(self.world, "pieces"):
                    for p_id, p_body in self.world.pieces.items():
                        if p_body.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                            continue
                        c_p, r_p, d_p = p_body.get_nearest_intersection()
                        if (r_p, c_p) == (r_src, c_src) and d_p < 0.025:
                            piece_at_src = p_id
                            break
                if piece_at_src:
                    self.backend.set_allowed_grasp_piece_id(piece_at_src)

                # Check if robot is already at or near src_grasp_m
                curr_snap = self.backend.get_state_snapshot()
                curr_p_m = np.array(curr_snap.tcp_pose_mm_deg[:3]) / 1000.0
                dist_to_src_grasp = float(np.linalg.norm(curr_p_m - np.array(src_grasp_m)))

                if dist_to_src_grasp > 0.005:
                    # Preposition safely:
                    # If departing from near Home pose, elevate / retract j2 first to avoid sweeping low over pieces
                    curr_deg = curr_snap.joints_deg
                    is_near_home = (
                        abs(curr_deg[0]) < 10.0 and
                        curr_deg[1] > -55.0 and
                        abs(curr_deg[2] - 90.0) < 20.0
                    )
                    if is_near_home:
                        retract_joints = list(curr_deg)
                        retract_joints[1] = -65.0
                        self.backend.move_joint(retract_joints, speed_factor=speed_factor)

                    # Move to approach pose (safe transit height)
                    target_app_deg = np.degrees(ik_src_app.joints_rad).tolist()
                    ok_app = self.backend.move_joint_with_lift_recovery(
                        target_app_deg,
                        speed_factor=speed_factor,
                        safe_plane_z_m=z_transit,
                    )
                    if not ok_app:
                        err_msg = self.backend._last_error or f"Preposition approach to {src_cell} failed"
                        self.backend.set_trajectory_stage("IDLE")
                        return {"success": False, "failed_stage": "PREPOSITION", "error": err_msg, "placement_version": current_ver}

                    # Descend vertically to src grasp
                    ok_descend = self.backend.move_cartesian(src_grasp_pose_mm, speed_factor=speed_factor, samples=samples_per_stage)
                    if not ok_descend:
                        err_msg = self.backend._last_error or f"Preposition descent to {src_cell} grasp failed"
                        self.backend.set_trajectory_stage("IDLE")
                        return {"success": False, "failed_stage": "PREPOSITION", "error": err_msg, "placement_version": current_ver}

                # --- Stage 1: LIFT (vertical MoveL from grasp to safe transit height) ---
                self.backend.set_trajectory_stage("LIFT")
                ok1 = self.move_cartesian(to_mm_deg(src_app_m), speed_factor=speed_factor, samples=samples_per_stage)
                if not ok1:
                    err_msg = self.backend._last_error or "LIFT stage failed"
                    self.backend.set_trajectory_stage("IDLE")
                    return {"success": False, "failed_stage": "LIFT", "error": err_msg, "placement_version": current_ver}

                # --- Stage 2: TRANSIT (horizontal MoveL across safe transit plane) ---
                self.backend.set_trajectory_stage("TRANSIT")
                ok2 = self.move_cartesian(to_mm_deg(dst_app_m), speed_factor=speed_factor, samples=samples_per_stage)
                if not ok2:
                    err_msg = self.backend._last_error or "TRANSIT stage failed"
                    self.backend.set_trajectory_stage("IDLE")
                    return {"success": False, "failed_stage": "TRANSIT", "error": err_msg, "placement_version": current_ver}

                # --- Stage 3: LAND (vertical MoveL from safe transit height down to grasp target) ---
                self.backend.set_trajectory_stage("LAND")
                ok3 = self.move_cartesian(to_mm_deg(dst_grasp_m), speed_factor=speed_factor, samples=samples_per_stage)
                if not ok3:
                    err_msg = self.backend._last_error or "LAND stage failed"
                    self.backend.set_trajectory_stage("IDLE")
                    return {"success": False, "failed_stage": "LAND", "error": err_msg, "placement_version": current_ver}

                # --- COMPLETE ---
                self.backend.set_trajectory_stage("COMPLETE")
                time.sleep(0.05)
                self.backend.set_trajectory_stage("IDLE")

                return {
                    "success": True,
                    "stages": ["PREPOSITION", "LIFT", "TRANSIT", "LAND", "COMPLETE"],
                    "src": src_cell,
                    "dst": dst_cell,
                    "z_grasp_m": z_grasp,
                    "z_transit_m": z_transit,
                    "placement_version": current_ver,
                }
            finally:
                self.backend.set_allowed_grasp_piece_id(None)

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


