"""
Authoritative Virtual FAIRINO FR3 Backend.

Implements the RobotBackend interface for headless digital-twin simulation.
- Owns authoritative joint, flange, TCP, gripper, and motion state
- Performs URDF-validated MoveJ and Cartesian MoveL trajectory execution
- Decoupled from Three.js; publishes state snapshots to TelemetryPublisher if connected
- Thread-safe state access with fast-execution support for unit tests
"""

import logging
import math
from pathlib import Path
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Union
import numpy as np

logger = logging.getLogger(__name__)

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.simulation.kinematics.fr3 import FR3Kinematics, IKResult, IKStatus
from src.simulation.kinematics.urdf_chain import Pose3D


class VirtualFR3Backend(RobotBackend):
    """
    Authoritative virtual FR3 robot actuator and state manager.
    """

    DEFAULT_HOME_JOINTS_DEG = [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]

    def __init__(
        self,
        kinematics: Optional[FR3Kinematics] = None,
        telemetry_publisher=None,
        default_speed_factor: float = 1.0,
        scene_config_path: Optional[Union[str, Path]] = None,
    ):
        self.kinematics = kinematics or FR3Kinematics()
        self.telemetry_publisher = telemetry_publisher
        self.default_speed_factor = max(0.01, float(default_speed_factor))
        self.scene_config_path = scene_config_path

        self._state_lock = threading.RLock()
        self._connected = False
        self._motion_state = "DISCONNECTED"
        self._gripper_closed = False
        self._last_error = None

        # Authoritative state values (degrees, radians, mm, deg)
        self._current_joints_deg = list(self.DEFAULT_HOME_JOINTS_DEG)
        self._current_joints_rad = np.array(
            [math.radians(d) for d in self._current_joints_deg], dtype=float
        )
        self._flange_pose_mm_deg = self._compute_flange_pose_mm_deg(self._current_joints_rad)
        # In P2, provisional tool transform is identity relative to flange
        self._tcp_pose_mm_deg = list(self._flange_pose_mm_deg)

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

    def _compute_flange_pose_mm_deg(self, joints_rad: np.ndarray) -> List[float]:
        pose = self.kinematics.forward_kinematics(joints_rad)
        return pose.to_xyz_rpy_deg()

    def connect(self) -> bool:
        """Connect virtual backend and initialize authoritative state."""
        with self._state_lock:
            self._connected = True
            self._motion_state = "IDLE"
            self._last_error = None
            self._sync_telemetry()
        return True

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
                last_error=self._last_error,
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
            last_error=self._last_error,
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
            self._sync_telemetry()
            return True

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
            start_rad = self._current_joints_rad.copy()
            self._motion_state = "MOVING"

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

            with self._state_lock:
                self._current_joints_rad = q_interp
                self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in q_interp]
                self._flange_pose_mm_deg = flange
                self._tcp_pose_mm_deg = list(flange)
                self._sync_telemetry()

            if sleep_time > 0:
                time.sleep(sleep_time)

        with self._state_lock:
            # Set exact final target
            self._current_joints_rad = target_rad
            self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in target_rad]
            self._flange_pose_mm_deg = self._compute_flange_pose_mm_deg(target_rad)
            self._tcp_pose_mm_deg = list(self._flange_pose_mm_deg)
            self._motion_state = "IDLE"
            self._sync_telemetry()

        return True

    def move_cartesian(
        self,
        target_pose_mm_deg: Sequence[float],
        speed_factor: Optional[float] = None,
        samples: int = 20,
    ) -> bool:
        """
        Execute Cartesian linear motion (MoveL) by sampling Cartesian waypoints
        and solving IK for each waypoint.
        Fails fast if any waypoint is unreachable.
        """
        if len(target_pose_mm_deg) != 6:
            with self._state_lock:
                self._last_error = f"MoveCartesian requires 6 pose values, got {len(target_pose_mm_deg)}"
                self._motion_state = "ERROR"
            return False

        if not all(math.isfinite(v) for v in target_pose_mm_deg):
            with self._state_lock:
                self._last_error = "MoveCartesian target contains non-finite values"
                self._motion_state = "ERROR"
            return False

        with self._state_lock:
            if not self._connected:
                self._last_error = "Cannot move: robot not connected"
                return False
            start_pose_mm_deg = list(self._tcp_pose_mm_deg)
            start_joints_rad = self._current_joints_rad.copy()

        # Generate linear interpolation waypoints in Cartesian space
        start_p = np.array(start_pose_mm_deg[:3], dtype=float)
        target_p = np.array(target_pose_mm_deg[:3], dtype=float)
        start_rot = np.array(start_pose_mm_deg[3:], dtype=float)
        target_rot = np.array(target_pose_mm_deg[3:], dtype=float)

        # Shortest-path angle difference in [-180, +180] deg to prevent 358-deg wraparounds
        rot_diff = np.array(
            [(t - s + 180.0) % 360.0 - 180.0 for s, t in zip(start_rot, target_rot)],
            dtype=float,
        )

        num_samples = max(2, samples)
        joint_trajectory = []
        seed = start_joints_rad.copy()

        self._stop_event.clear()

        # Pre-validate all waypoints before executing motion
        for i in range(1, num_samples + 1):
            alpha = float(i) / float(num_samples)
            p_i = start_p + alpha * (target_p - start_p)
            rot_i = start_rot + alpha * rot_diff
            wp_target = list(p_i) + list(rot_i)

            ik_res = self.kinematics.inverse_kinematics(
                wp_target, seed_joints=seed, allow_multi_seed=False
            )
            if not ik_res.success:
                # Try with multi-seed fallback
                ik_res = self.kinematics.inverse_kinematics(
                    wp_target, seed_joints=seed, allow_multi_seed=True
                )

            if not ik_res.success:
                with self._state_lock:
                    self._last_error = (
                        f"Cartesian waypoint {i}/{num_samples} unreachable: {ik_res.failure_reason}"
                    )
                    self._motion_state = "ERROR"
                return False

            joint_trajectory.append(ik_res.joints_rad)
            seed = ik_res.joints_rad.copy()

        # Waypoints all validated: execute trajectory
        with self._state_lock:
            self._motion_state = "MOVING"

        # Calculate timing based on URDF max joint velocities across waypoints
        max_vels = np.array(
            [j.max_velocity_rad_s for j in self.kinematics.chain.joints], dtype=float
        )
        prev_q = start_joints_rad
        total_joint_time = 0.0
        for q_wp in joint_trajectory:
            dq = np.abs(q_wp - prev_q)
            step_time = float(np.max(dq / np.maximum(max_vels, 1e-4)))
            total_joint_time += step_time
            prev_q = q_wp

        sf = speed_factor if speed_factor is not None else self.default_speed_factor
        scaled_duration_s = max(total_joint_time / max(sf, 1e-4), 0.02)
        sleep_time = (scaled_duration_s / len(joint_trajectory)) if sf < 50.0 else 0.0

        for q_step in joint_trajectory:
            if self._stop_event.is_set():
                with self._state_lock:
                    self._motion_state = "IDLE"
                    self._last_error = "MoveCartesian aborted by stop() request"
                    self._sync_telemetry()
                return False

            flange = self._compute_flange_pose_mm_deg(q_step)
            with self._state_lock:
                self._current_joints_rad = q_step
                self._current_joints_deg = [round(math.degrees(float(val)), 3) for val in q_step]
                self._flange_pose_mm_deg = flange
                self._tcp_pose_mm_deg = list(flange)
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
        with self._state_lock:
            if self._motion_state == "MOVING":
                self._motion_state = "IDLE"
            self._sync_telemetry()
        return True
