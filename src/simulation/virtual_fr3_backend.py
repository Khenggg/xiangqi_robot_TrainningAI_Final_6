"""
Authoritative Virtual FAIRINO FR3 Backend.

Implements the RobotBackend interface for headless digital-twin simulation.
- Owns authoritative joint, flange, TCP, gripper, and motion state
- Performs URDF-validated MoveJ and Cartesian MoveL trajectory execution
- Decoupled from Three.js; publishes state snapshots to TelemetryPublisher if connected
- Thread-safe state access with fast-execution support for unit tests
"""

import json
import logging
import math
from pathlib import Path
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union
import numpy as np

logger = logging.getLogger(__name__)

from src.domain.geometry import get_canonical_tool_geometry
from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.simulation.kinematics.fr3 import FR3Kinematics, IKResult, IKStatus
from src.simulation.kinematics.urdf_chain import Pose3D, matrix_to_rpy, rpy_to_matrix


@dataclass
class PlannedTrajectory:
    """Outcome of Cartesian trajectory planning without committing robot state."""
    success: bool
    start_q: np.ndarray
    target_tcp_pose: Sequence[float]
    waypoints_cartesian: List[np.ndarray]
    q_samples: List[np.ndarray]
    ik_success: bool = True
    collision_safe: bool = True
    collision_result: Optional[Any] = None
    failure_reason: Optional[str] = None
    first_failing_sample: Optional[int] = None
    q_failed: Optional[List[float]] = None
    colliding_links_or_bodies: Optional[str] = None
    final_q: Optional[np.ndarray] = None
    min_joint_margin_deg: Optional[float] = None
    worst_condition_number: Optional[float] = None
    min_manipulability: Optional[float] = None


@dataclass(frozen=True)
class VirtualBackendStateSnapshot:
    """Immutable snapshot of authoritative virtual FR3 backend state."""
    joints_deg: List[float]
    joints_rad: List[float]
    tcp_pose_mm_deg: List[float]
    flange_pose_mm_deg: List[float]
    motion_state: str
    connected: bool
    gripper_closed: bool
    attached_piece_id: Optional[str]
    last_error: Optional[str]
    collision_validated: bool = False


DEFAULT_HOME_JOINTS_DEG = [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]
SERVICE_SAFE_JOINTS_DEG = [0.0, -70.0, 60.0, -80.0, -90.0, 0.0]


class VirtualFR3Backend(RobotBackend):
    """
    Authoritative virtual FR3 robot actuator and state manager.
    """

    DEFAULT_HOME_JOINTS_DEG = [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]
    SERVICE_SAFE_JOINTS_DEG = [0.0, -70.0, 60.0, -80.0, -90.0, 0.0]

    def __init__(
        self,
        kinematics: Optional[FR3Kinematics] = None,
        telemetry_publisher=None,
        default_speed_factor: float = 1.0,
        scene_config_path: Optional[Union[str, Path]] = None,
        allow_unsafe_diagnostics: bool = False,
    ):
        self.kinematics = kinematics or FR3Kinematics()
        self.telemetry_publisher = telemetry_publisher
        self.default_speed_factor = max(0.01, float(default_speed_factor))
        self.allow_unsafe_diagnostics = bool(allow_unsafe_diagnostics)
        self.placement_version: int = 1

        repo_root = Path(__file__).resolve().parent.parent.parent
        self.scene_config_path = Path(scene_config_path) if scene_config_path else (
            repo_root / "shared" / "virtual_fr3_scene.json"
        )
        self._load_tool_transform()

        self.collision_guard = None
        self._allowed_grasp_piece_id: Optional[str] = None
        self._attached_piece_id: Optional[str] = None

        self._state_lock = threading.RLock()
        self._connected = False
        self._motion_state = "DISCONNECTED"
        self._trajectory_stage: Optional[str] = None
        self._gripper_closed = False
        self._last_error = None
        self._collision_validated = False

        # Authoritative state values (degrees, radians, mm, deg)
        self._current_joints_deg = list(self.DEFAULT_HOME_JOINTS_DEG)
        self._current_joints_rad = np.array(
            [math.radians(d) for d in self._current_joints_deg], dtype=float
        )
        self._flange_pose_mm_deg = self._compute_flange_pose_mm_deg(self._current_joints_rad)
        self._tcp_pose_mm_deg = self._compute_tcp_pose_mm_deg(self._current_joints_rad)

        # Simulation execution parameters
        self._step_delay_s = 0.01
        self._stop_event = threading.Event()
        self._listeners: List[Callable[[RobotStateSnapshot], None]] = []

    def add_state_listener(self, callback: Callable[[RobotStateSnapshot], None]) -> None:
        """Register a callback invoked whenever robot authoritative state updates."""
        with self._state_lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_state_listener(self, callback: Callable[[RobotStateSnapshot], None]) -> None:
        """Unregister a state listener callback."""
        with self._state_lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _load_tool_transform(self) -> None:
        """Load fixed tool transform from canonical tool geometry and scene configuration."""
        canonical_tool = get_canonical_tool_geometry()
        tool_xyz = list(canonical_tool.canonical_tcp_offset_m)
        tool_rpy = [0.0, 0.0, 0.0]
        if self.scene_config_path.is_file():
            try:
                with open(self.scene_config_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                tool_cfg = data.get("tool_transform", {})
                tool_xyz = tool_cfg.get("flange_to_tcp_xyz_m", tool_xyz)
                tool_rpy = tool_cfg.get("flange_to_tcp_rpy_deg", tool_rpy)
            except Exception as e:
                logger.warning(f"Could not load tool_transform from {self.scene_config_path}: {e}")

        R_tool = rpy_to_matrix(np.radians(tool_rpy))
        T_flange_tcp = np.eye(4, dtype=float)
        T_flange_tcp[:3, :3] = R_tool
        T_flange_tcp[:3, 3] = np.array(tool_xyz, dtype=float)

        self._T_flange_tcp = T_flange_tcp
        self._T_tcp_flange = np.linalg.inv(T_flange_tcp)
        self.flange_to_tcp_distance_m = float(np.linalg.norm(T_flange_tcp[:3, 3]))

        self.collision_guard = None
        self.collision_guard_enabled = True

    def set_collision_guard(self, guard) -> None:
        """Attach collision guard validator."""
        self.collision_guard = guard
        with self._state_lock:
            self._collision_validated = False
            self._sync_telemetry()

    def set_collision_guard_enabled(self, enabled: bool) -> None:
        """Dynamically enable or disable collision guard checking."""
        if not enabled and not self.allow_unsafe_diagnostics:
            logger.warning("[BACKEND] Disabling collision guard is blocked in normal mode (requires allow_unsafe_diagnostics=True)")
            self.collision_guard_enabled = True
            return
        self.collision_guard_enabled = bool(enabled)
        with self._state_lock:
            self._collision_validated = False
            self._sync_telemetry()
        logger.info(f"[BACKEND] Collision guard enabled set to: {self.collision_guard_enabled}")

    def set_placement_version(self, version: int) -> None:
        """Set authoritative placement version."""
        with self._state_lock:
            self.placement_version = int(version)
            self._sync_telemetry()

    def set_allowed_grasp_piece_id(self, piece_id: Optional[str]) -> None:
        """Set or clear the allowed target piece during grasp (wildcard '*' rejected)."""
        if piece_id == "*":
            self._allowed_grasp_piece_id = None
        else:
            self._allowed_grasp_piece_id = piece_id

    @property
    def allowed_grasp_piece_id(self) -> Optional[str]:
        return self._allowed_grasp_piece_id

    def set_attached_piece_id(self, piece_id: Optional[str]) -> None:
        """Set or clear ID of piece attached to gripper."""
        with self._state_lock:
            self._attached_piece_id = piece_id

    def get_attached_piece_id(self) -> Optional[str]:
        """Return ID of piece currently attached to gripper, or None."""
        with self._state_lock:
            return self._attached_piece_id

    @property
    def attached_piece_id(self) -> Optional[str]:
        with self._state_lock:
            return self._attached_piece_id

    def set_authoritative_joints(self, joints_deg_or_rad: Sequence[float], is_deg: bool = True) -> bool:
        """Set setup joints only when the attached collision guard accepts the pose."""
        if is_deg:
            q_deg = [round(float(v), 3) for v in joints_deg_or_rad]
            q_rad = np.radians(q_deg)
        else:
            q_rad = np.array(joints_deg_or_rad, dtype=float)
            q_deg = [round(math.degrees(v), 3) for v in q_rad]
        flange = self._compute_flange_pose_mm_deg(q_rad)
        tcp = self._compute_tcp_pose_mm_deg(q_rad)
        collision_validated = False
        if self.collision_guard is not None and getattr(self, "collision_guard_enabled", True):
            result = self.collision_guard.validate_configuration(q_rad, restore_state=True)
            if not result.safe:
                with self._state_lock:
                    self._motion_state = "COLLISION_REJECTED"
                    self._last_error = f"Authoritative joint setup rejected by collision guard: {result.failure_reason}"
                    self._sync_telemetry()
                return False
            collision_validated = True
        with self._state_lock:
            self._current_joints_rad = q_rad.copy()
            self._current_joints_deg = q_deg
            self._flange_pose_mm_deg = flange
            self._tcp_pose_mm_deg = tcp
            self._motion_state = "IDLE"
            self._last_error = None
            self._collision_validated = collision_validated
            self._sync_telemetry()
        return True

    def get_state_snapshot(self) -> VirtualBackendStateSnapshot:
        """Return an immutable snapshot of current authoritative backend state."""
        with self._state_lock:
            return VirtualBackendStateSnapshot(
                joints_deg=list(self._current_joints_deg),
                joints_rad=[float(v) for v in self._current_joints_rad],
                tcp_pose_mm_deg=list(self._tcp_pose_mm_deg),
                flange_pose_mm_deg=list(self._flange_pose_mm_deg),
                motion_state=str(self._motion_state),
                connected=bool(self._connected),
                gripper_closed=bool(self._gripper_closed),
                attached_piece_id=self._attached_piece_id,
                last_error=self._last_error,
                collision_validated=self._collision_validated,
            )

    def _compute_flange_pose_mm_deg(self, joints_rad: np.ndarray) -> List[float]:
        pose = self.kinematics.forward_kinematics(joints_rad)
        return pose.to_xyz_rpy_deg()

    def _compute_tcp_pose_mm_deg(self, joints_rad: np.ndarray) -> List[float]:
        """Compute tool TCP pose via rigid transformation composition: T_base_tcp = T_base_flange @ T_flange_tcp."""
        pose_flange = self.kinematics.forward_kinematics(joints_rad)
        T_base_flange = pose_flange.as_matrix()
        T_base_tcp = T_base_flange @ self._T_flange_tcp
        return Pose3D.from_matrix(T_base_tcp).to_xyz_rpy_deg()

    def connect(self) -> bool:
        """Connect virtual backend and initialize authoritative state."""
        if self.collision_guard is not None:
            if not getattr(self, "collision_guard_enabled", True):
                return self.refuse_connection("Simulation startup refused: collision guard is disabled")
            result = self.collision_guard.validate_configuration(
                self._current_joints_rad.copy(),
                restore_state=True,
            )
            if not result.safe:
                return self.refuse_connection(
                    f"Simulation startup pose rejected by collision guard: {result.failure_reason}"
                )
            collision_validated = True
        else:
            # A bare backend may be used for isolated kinematics tests, but is
            # never considered safe to render as an operational simulator pose.
            collision_validated = False
        with self._state_lock:
            self._connected = True
            self._motion_state = "IDLE"
            self._last_error = None
            self._collision_validated = collision_validated
            self._sync_telemetry()
        return True

    def refuse_connection(self, reason: str) -> bool:
        """Leave the backend non-operational when startup cannot be validated."""
        with self._state_lock:
            self._connected = False
            self._motion_state = "COLLISION_REJECTED"
            self._last_error = str(reason)
            self._collision_validated = False
            self._sync_telemetry()
        return False

    def disconnect(self) -> bool:
        """Disconnect virtual backend."""
        with self._state_lock:
            self._connected = False
            self._motion_state = "DISCONNECTED"
            self._sync_telemetry()
        return True

    def is_connected(self) -> bool:
        with self._state_lock:
            return self._connected

    def solve_tcp_ik_candidates(
        self,
        tcp_pose_mm_deg: Sequence[float],
        seed_joints: Optional[Sequence[float]] = None,
        ref_joints: Optional[Sequence[float]] = None,
        allow_alternate_yaw: bool = False,
        allowed_grasp_piece_id: Optional[str] = None,
    ) -> List[IKResult]:
        """
        Generate multiple valid, collision-checked IK candidates for target TCP pose,
        ranked by continuity score against ref_joints (or current robot configuration).
        """
        q_ref = ref_joints if ref_joints is not None else np.radians(self._current_joints_deg)

        poses_to_try = [list(tcp_pose_mm_deg)]
        if allow_alternate_yaw:
            alt_pose = list(tcp_pose_mm_deg)
            alt_pose[5] = (alt_pose[5] + 180.0 + 180.0) % 360.0 - 180.0
            poses_to_try.append(alt_pose)

        all_candidates: List[IKResult] = []
        seen: List[np.ndarray] = []

        for p_target in poses_to_try:
            p_m = np.array(p_target[:3], dtype=float) / 1000.0
            R_tcp = rpy_to_matrix(np.radians(p_target[3:]))
            T_tcp = np.eye(4, dtype=float)
            T_tcp[:3, :3] = R_tcp
            T_tcp[:3, 3] = p_m
            T_flange = T_tcp @ self._T_tcp_flange
            pose_flange = Pose3D.from_matrix(T_flange)

            cands = self.kinematics.solve_ik_candidates(
                pose_flange,
                seed_joints=seed_joints,
                ref_joints=q_ref,
            )
            for c in cands:
                if any(np.allclose(c.joints_rad, s, atol=1e-2) for s in seen):
                    continue
                seen.append(c.joints_rad)

                # Collision check if collision guard attached
                if self.collision_guard is not None and getattr(self, "collision_guard_enabled", True):
                    col = self.collision_guard.validate_configuration(
                        c.joints_rad,
                        allowed_grasp_piece_id=allowed_grasp_piece_id,
                        restore_state=True,
                    )
                    if not col.safe:
                        continue
                all_candidates.append(c)

        def score_fn(cand: IKResult) -> float:
            disp = float(np.linalg.norm(cand.joints_rad - q_ref)) if q_ref is not None else 0.0
            branch_diff = float(abs(cand.joints_rad[4] - q_ref[4])) if q_ref is not None else 0.0
            margin_rad = min(
                min(cand.joints_rad[k] - self.kinematics.lower_limits[k],
                    self.kinematics.upper_limits[k] - cand.joints_rad[k])
                for k in range(6)
            )
            margin_penalty = 0.1 / max(margin_rad, 0.01)
            cond_penalty = (cand.condition_number or 10.0) / 200.0
            return 2.0 * disp + 3.0 * branch_diff + margin_penalty + cond_penalty

        all_candidates.sort(key=score_fn)
        return all_candidates

    def solve_tcp_ik(
        self,
        tcp_pose_mm_deg: Sequence[float],
        seed_joints: Optional[Sequence[float]] = None,
        allow_multi_seed: bool = True,
        ref_joints: Optional[Sequence[float]] = None,
        allow_alternate_yaw: bool = False,
        allowed_grasp_piece_id: Optional[str] = None,
    ) -> IKResult:
        """
        Solve inverse kinematics for a target TCP pose (in mm and deg).
        Prioritizes continuity with ref_joints (or current robot posture).
        """
        q_ref = ref_joints if ref_joints is not None else np.radians(self._current_joints_deg)

        if allow_multi_seed or allow_alternate_yaw:
            cands = self.solve_tcp_ik_candidates(
                tcp_pose_mm_deg,
                seed_joints=seed_joints,
                ref_joints=q_ref,
                allow_alternate_yaw=allow_alternate_yaw,
                allowed_grasp_piece_id=allowed_grasp_piece_id,
            )
            if cands:
                return cands[0]

        # Single seed fast path or fallback
        p_m = np.array(tcp_pose_mm_deg[:3], dtype=float) / 1000.0
        R_tcp = rpy_to_matrix(np.radians(tcp_pose_mm_deg[3:]))
        T_tcp = np.eye(4, dtype=float)
        T_tcp[:3, :3] = R_tcp
        T_tcp[:3, 3] = p_m
        T_flange = T_tcp @ self._T_tcp_flange
        pose_flange = Pose3D.from_matrix(T_flange)
        return self.kinematics.inverse_kinematics(
            pose_flange,
            seed_joints=seed_joints,
            allow_multi_seed=allow_multi_seed,
            ref_joints=q_ref,
        )


    def set_trajectory_stage(self, stage: Optional[str]) -> None:
        """Set current 3-stage trajectory phase (PREPOSITION, LIFT, TRANSIT, LAND, COMPLETE, FAILED, None)."""
        with self._state_lock:
            self._trajectory_stage = stage
            self._sync_telemetry()

    def get_trajectory_stage(self) -> Optional[str]:
        """Return current trajectory stage."""
        with self._state_lock:
            return self._trajectory_stage

    @property
    def trajectory_stage(self) -> Optional[str]:
        with self._state_lock:
            return self._trajectory_stage

    def get_state_snapshot(self) -> RobotStateSnapshot:
        """Return immutable, thread-safe snapshot of current authoritative state."""
        with self._state_lock:
            return RobotStateSnapshot(
                robot_model="FR3",
                connected=self._connected,
                motion_state=self._motion_state,
                joints_deg=list(self._current_joints_deg),
                flange_pose_mm_deg=list(self._flange_pose_mm_deg),
                tcp_pose_mm_deg=list(self._tcp_pose_mm_deg),
                gripper_closed=self._gripper_closed,
                timestamp=time.time(),
                flange_pose_source="DERIVED",
                last_error=self._last_error,
                trajectory_stage=self._trajectory_stage,
                placement_version=self.placement_version,
                collision_validated=self._collision_validated,
            )

    def _sync_telemetry(self):
        """Push current authoritative state to telemetry publisher and listeners."""
        snapshot = RobotStateSnapshot(
            robot_model="FR3",
            connected=self._connected,
            motion_state=self._motion_state,
            joints_deg=list(self._current_joints_deg),
            flange_pose_mm_deg=list(self._flange_pose_mm_deg),
            tcp_pose_mm_deg=list(self._tcp_pose_mm_deg),
            gripper_closed=self._gripper_closed,
            timestamp=time.time(),
            flange_pose_source="DERIVED",
            last_error=self._last_error,
            trajectory_stage=self._trajectory_stage,
            placement_version=self.placement_version,
            collision_validated=self._collision_validated,
        )

        if self.telemetry_publisher is not None:
            try:
                if hasattr(self.telemetry_publisher, "update_from_snapshot"):
                    self.telemetry_publisher.update_from_snapshot(snapshot)
                elif hasattr(self.telemetry_publisher, "update_state"):
                    self.telemetry_publisher.update_state(
                        joints_deg=self._current_joints_deg,
                        tcp_mm_deg=self._tcp_pose_mm_deg,
                        gripper=self._gripper_closed,
                        robot_model="FR3",
                        motion_state=self._motion_state,
                        trajectory_stage=self._trajectory_stage,
                        last_error=self._last_error,
                        connected=self._connected,
                        collision_validated=self._collision_validated,
                    )
            except Exception as e:
                self._last_error = f"Telemetry sync warning: {e}"

        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception as e:
                logger.warning("Robot state listener %r raised exception: %s", listener, e)

    def set_gripper(self, closed: bool) -> bool:
        """Set gripper virtual actuator state."""
        with self._state_lock:
            if not self._connected:
                self._last_error = "Cannot set gripper: robot not connected"
                return False
            self._gripper_closed = bool(closed)
            if not self._gripper_closed:
                self._attached_piece_id = None
            self._sync_telemetry()
            return True

    def is_gripper_closed(self) -> bool:
        """Check if gripper virtual actuator is in closed state."""
        with self._state_lock:
            return bool(self._gripper_closed)

    def open_gripper(self) -> bool:
        """Convenience method to open virtual gripper."""
        return self.set_gripper(False)

    def close_gripper(self) -> bool:
        """Convenience method to close virtual gripper."""
        return self.set_gripper(True)

    def move_joint(
        self,
        target_joints_deg: Sequence[float],
        speed_factor: Optional[float] = None,
        steps: int = 20,
    ) -> bool:
        """
        Execute joint-space motion (MoveJ) with validation and interpolation.
        """
        target_deg = [float(v) for v in target_joints_deg]
        if len(target_deg) != 6:
            with self._state_lock:
                self._last_error = f"MoveJ requires 6 joint angles, got {len(target_deg)}"
                self._motion_state = "ERROR"
            return False

        if not all(math.isfinite(v) for v in target_deg):
            with self._state_lock:
                self._last_error = "MoveJ target contains non-finite values"
                self._motion_state = "ERROR"
            return False

        target_rad = np.array([math.radians(d) for d in target_deg], dtype=float)
        is_valid, margins = self.kinematics.chain.check_joint_limits(target_rad)
        if not is_valid:
            with self._state_lock:
                self._last_error = f"MoveJ target violates joint limits: margins={margins}"
                self._motion_state = "ERROR"
            return False

        with self._state_lock:
            if not self._connected:
                self._last_error = "Cannot move: robot not connected"
                return False
            self._last_error = None
            start_rad = self._current_joints_rad.copy()
            self._motion_state = "MOVING"

        # Pre-validate trajectory through collision guard if configured
        if self.collision_guard is not None and getattr(self, "collision_guard_enabled", True):
            max_joint_step_rad = math.radians(1.0)  # Bounded to <= 1.0 degree
            diff_rad = np.abs(target_rad - start_rad)
            n_sub = max(2, int(math.ceil(float(np.max(diff_rad)) / max_joint_step_rad)))
            q_samples = [start_rad + (float(k) / n_sub) * (target_rad - start_rad) for k in range(1, n_sub + 1)]
            col_res = self.collision_guard.validate_trajectory(
                q_samples,
                allowed_grasp_piece_id=self._allowed_grasp_piece_id,
                restore_state=True,
            )
            if not col_res.safe:
                with self._state_lock:
                    self._last_error = f"MoveJ rejected by collision guard: {col_res.failure_reason}"
                    self._motion_state = "COLLISION_REJECTED"
                    # Preserve last safe state strictly
                    self._current_joints_rad = start_rad.copy()
                    self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in start_rad]
                    self._flange_pose_mm_deg = self._compute_flange_pose_mm_deg(start_rad)
                    self._tcp_pose_mm_deg = self._compute_tcp_pose_mm_deg(start_rad)
                    self._sync_telemetry()
                return False
            with self._state_lock:
                self._collision_validated = True
        else:
            with self._state_lock:
                self._collision_validated = False

        # Physical motion duration constrained by URDF maximum joint velocities:
        # t_i = |Delta q_i| / v_max,i
        delta_rad = np.abs(target_rad - start_rad)
        max_vels = np.array(
            [j.max_velocity_rad_s for j in self.kinematics.chain.joints], dtype=float
        )
        joint_durations = delta_rad / np.maximum(max_vels, 1e-4)
        min_duration_s = float(np.max(joint_durations)) if len(joint_durations) > 0 else 0.05

        sf = speed_factor if speed_factor is not None else self.default_speed_factor
        scaled_duration_s = max(min_duration_s / max(sf, 1e-4), 0.02)
        step_dt = 0.02  # 50 Hz interpolation steps
        actual_steps = max(1, int(math.ceil(scaled_duration_s / step_dt))) if sf < 50.0 else 1
        sleep_time = (scaled_duration_s / actual_steps) if sf < 50.0 else 0.0

        self._stop_event.clear()

        for s in range(1, actual_steps + 1):
            if self._stop_event.is_set():
                with self._state_lock:
                    self._motion_state = "IDLE"
                    self._last_error = "MoveJ aborted by stop() request"
                    self._sync_telemetry()
                return False

            alpha = float(s) / float(actual_steps)
            q_interp = start_rad + alpha * (target_rad - start_rad)
            flange = self._compute_flange_pose_mm_deg(q_interp)
            tcp = self._compute_tcp_pose_mm_deg(q_interp)

            with self._state_lock:
                self._current_joints_rad = q_interp
                self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in q_interp]
                self._flange_pose_mm_deg = flange
                self._tcp_pose_mm_deg = tcp
                self._sync_telemetry()

            if sleep_time > 0:
                time.sleep(sleep_time)

        with self._state_lock:
            # Set exact final target
            self._current_joints_rad = target_rad
            self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in target_rad]
            self._flange_pose_mm_deg = self._compute_flange_pose_mm_deg(target_rad)
            self._tcp_pose_mm_deg = self._compute_tcp_pose_mm_deg(target_rad)
            self._motion_state = "IDLE"
            self._sync_telemetry()

        return True

    def move_joint_with_lift_recovery(
        self,
        target_joints_deg: Sequence[float],
        speed_factor: Optional[float] = None,
        safe_plane_z_m: Optional[float] = None,
        min_safe_z_m: Optional[float] = None,
        lift_delta_m: float = 0.065,
    ) -> bool:
        """
        Execute joint motion with reactive lift-first escape on collision detection:
        If direct motion is rejected due to obstacle/piece collision risk, automatically
        elevates the arm vertically into safe free space above obstacles, then re-adjusts
        to target joint configuration from the safe clearance altitude.
        """
        # 1. Attempt direct joint motion (or preemptive branch switch if already at SERVICE_SAFE)
        curr_snap = self.get_state_snapshot()
        branch_diff = abs(target_joints_deg[4] - curr_snap.joints_deg[4])
        is_near_service_safe = (
            abs(curr_snap.joints_deg[0] - self.SERVICE_SAFE_JOINTS_DEG[0]) < 15.0 and
            abs(curr_snap.joints_deg[1] - self.SERVICE_SAFE_JOINTS_DEG[1]) < 15.0 and
            abs(curr_snap.joints_deg[2] - self.SERVICE_SAFE_JOINTS_DEG[2]) < 15.0 and
            abs(curr_snap.joints_deg[3] - self.SERVICE_SAFE_JOINTS_DEG[3]) < 15.0
        )
        if branch_diff > 90.0 and is_near_service_safe:
            q_safe_flipped = list(self.SERVICE_SAFE_JOINTS_DEG)
            q_safe_flipped[4] = target_joints_deg[4]
            if self.move_joint(q_safe_flipped, speed_factor=speed_factor):
                if self.move_joint(target_joints_deg, speed_factor=speed_factor):
                    return True

        if self.move_joint(target_joints_deg, speed_factor=speed_factor):
            return True

        if self._motion_state != "COLLISION_REJECTED":
            return False

        logger.info("[COLLISION RECOVERY] Direct move rejected. Initiating vertical lift-first escape...")
        orig_stage = self._trajectory_stage
        self.set_trajectory_stage("RECOVERY_LIFT")

        curr_snap = self.get_state_snapshot()
        curr_tcp = list(curr_snap.tcp_pose_mm_deg)
        curr_z_m = curr_tcp[2] / 1000.0

        lift_success = False

        # Strategy A: Vertical Cartesian lift if tool is over board / downward oriented
        effective_safe_z = safe_plane_z_m if safe_plane_z_m is not None else min_safe_z_m
        if effective_safe_z is not None:
            target_lift_z_m = max(curr_z_m + lift_delta_m, effective_safe_z)
        else:
            target_lift_z_m = curr_z_m + lift_delta_m

        # Cap recovery lift within feasible workspace reach
        target_lift_z_m = min(target_lift_z_m, 0.40)
        lift_tcp_mm = list(curr_tcp)
        lift_tcp_mm[2] = target_lift_z_m * 1000.0

        if self.move_cartesian(lift_tcp_mm, speed_factor=speed_factor, samples=15):
            lift_success = True
        else:
            ik_lift = self.solve_tcp_ik(lift_tcp_mm, allow_multi_seed=True)
            if ik_lift.success:
                q_lift_deg = [round(math.degrees(v), 3) for v in ik_lift.joints_rad]
                if self.move_joint(q_lift_deg, speed_factor=speed_factor):
                    lift_success = True

        # Strategy B: Joint shoulder-elevation escape (especially useful when starting near Home)
        if not lift_success:
            curr_deg = curr_snap.joints_deg
            q_elevate = list(curr_deg)
            q_elevate[1] = min(q_elevate[1] - 20.0, -65.0)
            if self.move_joint(q_elevate, speed_factor=speed_factor):
                lift_success = True

        if not lift_success:
            logger.warning("[COLLISION RECOVERY] Vertical lift escape failed. Restoring stage.")
            self.set_trajectory_stage(orig_stage or "IDLE")
            return False

        # 2. Adjust pose to target from safe elevated clearance
        logger.info("[COLLISION RECOVERY] Arm successfully lifted. Adjusting pose to target from safe altitude...")
        target_ok = self.move_joint(target_joints_deg, speed_factor=speed_factor)

        # Strategy C: If target move failed and requires branch switch, reconfigure at SERVICE_SAFE
        if not target_ok and abs(target_joints_deg[4] - curr_snap.joints_deg[4]) > 90.0:
            logger.info("[COLLISION RECOVERY] Elevated move rejected due to branch flip. Reconfiguring at SERVICE_SAFE...")
            q_safe_curr = list(self.SERVICE_SAFE_JOINTS_DEG)
            q_safe_curr[4] = curr_snap.joints_deg[4]
            if self.move_joint(q_safe_curr, speed_factor=speed_factor):
                q_safe_target = list(self.SERVICE_SAFE_JOINTS_DEG)
                q_safe_target[4] = target_joints_deg[4]
                if self.move_joint(q_safe_target, speed_factor=speed_factor):
                    target_ok = self.move_joint(target_joints_deg, speed_factor=speed_factor)

        self.set_trajectory_stage(orig_stage or "IDLE")

        if target_ok:
            logger.info("[COLLISION RECOVERY] Lift-first recovery succeeded! Target pose reached.")
            return True
        else:
            logger.warning("[COLLISION RECOVERY] Move to target from elevated pose failed.")
            return False

    def plan_cartesian(
        self,
        start_q: Sequence[float],
        target_pose_mm_deg: Sequence[float],
        samples: int = 20,
        allowed_grasp_piece_id: Optional[str] = None,
        check_collision: bool = True,
    ) -> PlannedTrajectory:
        """
        Plan Cartesian linear motion (MoveL) from start_q to target_pose_mm_deg
        WITHOUT committing or mutating robot state.
        Fails fast if any waypoint is unreachable or collides.
        """
        start_q_arr = np.array(start_q, dtype=float)
        if len(target_pose_mm_deg) != 6:
            return PlannedTrajectory(
                success=False,
                start_q=start_q_arr,
                target_tcp_pose=target_pose_mm_deg,
                waypoints_cartesian=[],
                q_samples=[],
                ik_success=False,
                failure_reason=f"MoveCartesian requires 6 pose values, got {len(target_pose_mm_deg)}",
            )

        if not all(math.isfinite(v) for v in target_pose_mm_deg):
            return PlannedTrajectory(
                success=False,
                start_q=start_q_arr,
                target_tcp_pose=target_pose_mm_deg,
                waypoints_cartesian=[],
                q_samples=[],
                ik_success=False,
                failure_reason="MoveCartesian target contains non-finite values",
            )

        start_tcp = self._compute_tcp_pose_mm_deg(start_q_arr)
        start_p = np.array(start_tcp[:3], dtype=float)
        target_p = np.array(target_pose_mm_deg[:3], dtype=float)
        start_rot = np.array(start_tcp[3:], dtype=float)
        target_rot = np.array(target_pose_mm_deg[3:], dtype=float)

        # Shortest-path angle difference in [-180, +180] deg to prevent 358-deg wraparounds
        rot_diff = np.array(
            [(t - s + 180.0) % 360.0 - 180.0 for s, t in zip(start_rot, target_rot)],
            dtype=float,
        )

        dist_mm = float(np.linalg.norm(target_p - start_p))
        n_trans = int(math.ceil(dist_mm / 3.0))
        max_rot_deg = float(np.max(np.abs(rot_diff))) if len(rot_diff) > 0 else 0.0
        n_rot = int(math.ceil(max_rot_deg / 1.0))
        num_samples = max(n_trans, n_rot, samples, 10)

        waypoints_cartesian = []
        joint_trajectory = []
        seed = start_q_arr.copy()

        min_margin_deg = float("inf")
        worst_cond = 0.0
        min_manip = float("inf")

        for i in range(1, num_samples + 1):
            alpha = float(i) / float(num_samples)
            p_i = start_p + alpha * (target_p - start_p)
            rot_i = start_rot + alpha * rot_diff
            waypoints_cartesian.append(p_i)

            p_m = p_i / 1000.0
            R_tcp_i = rpy_to_matrix(np.radians(rot_i))
            T_base_tcp_i = np.eye(4, dtype=float)
            T_base_tcp_i[:3, :3] = R_tcp_i
            T_base_tcp_i[:3, 3] = p_m
            T_base_flange_i = T_base_tcp_i @ self._T_tcp_flange
            wp_flange = Pose3D.from_matrix(T_base_flange_i)

            ik_res = self.kinematics.inverse_kinematics(
                wp_flange, seed_joints=seed, allow_multi_seed=False, ref_joints=seed
            )
            if not ik_res.success:
                ik_res = self.kinematics.inverse_kinematics(
                    wp_flange, seed_joints=seed, allow_multi_seed=True, ref_joints=seed
                )

            if not ik_res.success:
                return PlannedTrajectory(
                    success=False,
                    start_q=start_q_arr,
                    target_tcp_pose=target_pose_mm_deg,
                    waypoints_cartesian=waypoints_cartesian,
                    q_samples=joint_trajectory,
                    ik_success=False,
                    first_failing_sample=i,
                    failure_reason=f"Cartesian waypoint {i}/{num_samples} unreachable: {ik_res.failure_reason}",
                )

            q_curr = ik_res.joints_rad
            joint_trajectory.append(q_curr)
            seed = q_curr.copy()

            # Joint limit margin
            margin_i = min(
                min(q_curr[k] - self.kinematics.lower_limits[k], self.kinematics.upper_limits[k] - q_curr[k])
                for k in range(len(q_curr))
            )
            min_margin_deg = min(min_margin_deg, math.degrees(margin_i))

            # Jacobian metrics
            J_i = self.kinematics.geometric_jacobian(q_curr)
            cond_i = self.kinematics.compute_condition_number(J_i)
            worst_cond = max(worst_cond, cond_i)
            manip_i = self.kinematics.compute_manipulability(J_i)
            min_manip = min(min_manip, manip_i)

        # Pre-validate trajectory through collision guard if configured
        if check_collision and self.collision_guard is not None and getattr(self, "collision_guard_enabled", True):
            col_res = self.collision_guard.validate_trajectory(
                joint_trajectory,
                allowed_grasp_piece_id=allowed_grasp_piece_id,
                restore_state=True,
            )
            if not col_res.safe:
                return PlannedTrajectory(
                    success=False,
                    start_q=start_q_arr,
                    target_tcp_pose=target_pose_mm_deg,
                    waypoints_cartesian=waypoints_cartesian,
                    q_samples=joint_trajectory,
                    collision_safe=False,
                    collision_result=col_res,
                    first_failing_sample=col_res.sample_index,
                    q_failed=col_res.q_failed,
                    colliding_links_or_bodies=col_res.colliding_body,
                    failure_reason=f"MoveCartesian rejected by collision guard: {col_res.failure_reason}",
                    min_joint_margin_deg=round(min_margin_deg, 2) if math.isfinite(min_margin_deg) else None,
                    worst_condition_number=round(worst_cond, 2) if math.isfinite(worst_cond) else None,
                    min_manipulability=round(min_manip, 4) if math.isfinite(min_manip) else None,
                )

        return PlannedTrajectory(
            success=True,
            start_q=start_q_arr,
            target_tcp_pose=target_pose_mm_deg,
            waypoints_cartesian=waypoints_cartesian,
            q_samples=joint_trajectory,
            final_q=joint_trajectory[-1] if joint_trajectory else start_q_arr,
            min_joint_margin_deg=round(min_margin_deg, 2) if math.isfinite(min_margin_deg) else None,
            worst_condition_number=round(worst_cond, 2) if math.isfinite(worst_cond) else None,
            min_manipulability=round(min_manip, 4) if math.isfinite(min_manip) else None,
        )

    def move_cartesian(
        self,
        target_pose_mm_deg: Sequence[float],
        speed_factor: Optional[float] = None,
        samples: int = 20,
    ) -> bool:
        """
        Execute Cartesian linear motion (MoveL) by sampling Cartesian waypoints
        and solving IK for each waypoint.
        Uses plan_cartesian() to pre-validate and then commits state.
        """
        with self._state_lock:
            if not self._connected:
                self._last_error = "Cannot move: robot not connected"
                return False
            self._last_error = None
            start_pose_mm_deg = list(self._tcp_pose_mm_deg)
            start_joints_rad = self._current_joints_rad.copy()

        plan = self.plan_cartesian(
            start_q=start_joints_rad,
            target_pose_mm_deg=target_pose_mm_deg,
            samples=samples,
            allowed_grasp_piece_id=self._allowed_grasp_piece_id,
            check_collision=(self.collision_guard is not None and getattr(self, "collision_guard_enabled", True)),
        )

        if not plan.success:
            with self._state_lock:
                self._last_error = plan.failure_reason
                self._motion_state = "COLLISION_REJECTED" if not plan.collision_safe else "ERROR"
                # Preserve last safe state strictly
                self._current_joints_rad = start_joints_rad.copy()
                self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in start_joints_rad]
                self._flange_pose_mm_deg = self._compute_flange_pose_mm_deg(start_joints_rad)
                self._tcp_pose_mm_deg = list(start_pose_mm_deg)
                self._sync_telemetry()
            return False

        # Plan validated: execute trajectory
        with self._state_lock:
            self._motion_state = "MOVING"

        # Calculate timing based on URDF max joint velocities across waypoints
        max_vels = np.array(
            [j.max_velocity_rad_s for j in self.kinematics.chain.joints], dtype=float
        )
        prev_q = start_joints_rad
        total_joint_time = 0.0
        for q_wp in plan.q_samples:
            dq = np.abs(q_wp - prev_q)
            step_time = float(np.max(dq / np.maximum(max_vels, 1e-4)))
            total_joint_time += step_time
            prev_q = q_wp

        sf = speed_factor if speed_factor is not None else self.default_speed_factor
        scaled_duration_s = max(total_joint_time / max(sf, 1e-4), 0.02)
        sleep_time = (scaled_duration_s / len(plan.q_samples)) if sf < 50.0 else 0.0

        self._stop_event.clear()

        for q_step in plan.q_samples:
            if self._stop_event.is_set():
                with self._state_lock:
                    self._motion_state = "IDLE"
                    self._last_error = "MoveCartesian aborted by stop() request"
                    self._sync_telemetry()
                return False

            flange = self._compute_flange_pose_mm_deg(q_step)
            tcp = self._compute_tcp_pose_mm_deg(q_step)
            with self._state_lock:
                self._current_joints_rad = q_step
                self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in q_step]
                self._flange_pose_mm_deg = flange
                self._tcp_pose_mm_deg = tcp
                self._sync_telemetry()

            if sleep_time > 0:
                time.sleep(sleep_time)

        with self._state_lock:
            self._motion_state = "IDLE"
            self._sync_telemetry()

        return True

    def stop(self) -> bool:
        """Halt motion immediately across threads."""
        self._stop_event.set()
        self.set_allowed_grasp_piece_id(None)
        with self._state_lock:
            if self._motion_state == "MOVING":
                self._motion_state = "IDLE"
            self._sync_telemetry()
        return True

    def reset_to_home(self, speed_factor: Optional[float] = None) -> bool:
        """Move arm back to canonical home joint pose."""
        return self.move_joint(self.DEFAULT_HOME_JOINTS_DEG, speed_factor=speed_factor)

    @property
    def home_joints_deg(self) -> List[float]:
        return list(self.DEFAULT_HOME_JOINTS_DEG)

    def is_service_safe(self, tolerance_deg: float = 2.0) -> bool:
        """
        Check if robot is in SERVICE_SAFE pose (within tolerance_deg on all joints)
        and gripper is open / not attached / connected / not moving.
        """
        if not self.is_connected():
            return False
        with self._state_lock:
            if self._motion_state != "IDLE":
                return False
            if self._gripper_closed:
                return False
            if self._attached_piece_id is not None:
                return False
            curr = self._current_joints_deg
            for c, target in zip(curr, self.SERVICE_SAFE_JOINTS_DEG):
                if abs(c - target) > tolerance_deg:
                    return False
            return True

    def go_service_safe(self, speed_factor: Optional[float] = None) -> bool:
        """
        Safely move arm to SERVICE_SAFE joint configuration and open gripper.
        Uses lift recovery if near or below transit safe plane.
        """
        self.open_gripper()
        return self.move_joint_with_lift_recovery(
            self.SERVICE_SAFE_JOINTS_DEG,
            speed_factor=speed_factor,
        )

    def jog_joint(
        self,
        joint_idx: int,
        delta_deg: float,
        speed_factor: Optional[float] = None,
    ) -> bool:
        """
        Jog a single joint by delta_deg while validating joint limits and collisions.
        """
        if joint_idx < 0 or joint_idx >= 6:
            self._last_error = f"Invalid joint index {joint_idx}"
            return False

        with self._state_lock:
            target_deg = list(self._current_joints_deg)

        target_deg[joint_idx] += float(delta_deg)
        return self.move_joint(target_deg, speed_factor=speed_factor)

    def jog_tcp(
        self,
        delta_xyz_mm: Optional[Sequence[float]] = None,
        delta_rpy_deg: Optional[Sequence[float]] = None,
        speed_factor: Optional[float] = None,
        samples: int = 10,
    ) -> bool:
        """
        Jog TCP in Cartesian space by delta_xyz_mm and delta_rpy_deg.
        """
        with self._state_lock:
            current_pose = list(self._tcp_pose_mm_deg)

        target_pose = list(current_pose)
        if delta_xyz_mm is not None:
            for i in range(min(3, len(delta_xyz_mm))):
                target_pose[i] += float(delta_xyz_mm[i])
        if delta_rpy_deg is not None:
            for i in range(min(3, len(delta_rpy_deg))):
                target_pose[3 + i] += float(delta_rpy_deg[i])

        return self.move_cartesian(target_pose, speed_factor=speed_factor, samples=samples)
