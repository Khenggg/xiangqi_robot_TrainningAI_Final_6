"""
Physical FR3 Robot Backend implementing canonical RobotBackend interface.

Communicates with physical FAIRINO FR3 (or compatible controller) via Ethernet RPC SDK.
Adheres strictly to the canonical RobotBackend abstraction from src/hardware/backends/base.py.
Does NOT manage Xiangqi rules, camera homography, or game state.
"""

from typing import Any, List, Optional, Sequence, Tuple
import logging
import math
import time
import threading
import numpy as np

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.domain.geometry import get_canonical_tool_geometry

logger = logging.getLogger(__name__)

try:
    from src.hardware import robot_sdk_core
except ImportError:
    robot_sdk_core = None


def is_motion_success_code(code: int) -> bool:
    """
    Check if FAIRINO SDK return code indicates successful motion.
    
    FAIRINO SDK specification: 0 = Success, non-zero = Error code.
    Code 112 was historically treated as an ignorable singularity/out-of-reach warning,
    which is unsafe for closed-loop physical execution. Only code 0 is authoritative success.
    """
    return code == 0


class PhysicalFR3Backend(RobotBackend):
    """
    Physical execution backend for the FAIRINO FR3 collaborative industrial arm.
    """

    def __init__(
        self,
        ip: str = "192.168.58.2",
        dry_run: bool = False,
        tool_num: int = 0,
        user_num: int = 0,
        default_vel: float = 50.0,
        gripper_driver: Optional[Any] = None,
    ):
        self.ip = ip
        self.dry_run = dry_run
        self.tool_num = tool_num
        self.user_num = user_num
        self.default_vel = float(default_vel)
        self.gripper_driver = gripper_driver

        self._rpc: Optional[Any] = None
        self._connected: bool = False
        self._enabled: bool = False
        self._operational_mode: Optional[int] = None
        self._motion_state: str = "DISCONNECTED"
        self._last_error: Optional[str] = None
        self._gripper_closed: bool = False
        self._trajectory_stage: Optional[str] = "IDLE"
        self._snapshot_lock = threading.RLock()
        self._joints_valid = False
        self._tcp_valid = False
        self._measurement_timestamp: Optional[float] = None
        self._telemetry_error: Optional[str] = None
        self._last_stream_packet = None
        self._last_stream_seen_monotonic: Optional[float] = None
        self._stream_stale_after_s = 0.5
        self._controller_fault: Optional[str] = None
        self._controller_status_valid = False
        self._fault_generation = 0
        self._command_error: Optional[str] = None
        self._gripper_outputs_owned = False

        # Internal state cache (for dry-run and between read cycles)
        self._current_joints_deg: List[float] = [0.0, -45.0, 90.0, -135.0, -90.0, 0.0]
        self._current_tcp_pose_mm_deg: List[float] = [-360.0, 0.0, 200.0, 180.0, 0.0, 90.0]
        # Dry-run cache only: +Z_tool points downward at the nominal pose.
        tool_length_mm = get_canonical_tool_geometry().flange_to_tcp_distance_mm
        self._current_flange_pose_mm_deg: List[float] = [
            -360.0, 0.0, 200.0 + tool_length_mm, 180.0, 0.0, 90.0
        ]
        self._flange_authoritative: bool = False
        self._flange_pose_source: str = "MOCK" if self.dry_run else "UNAVAILABLE"

        # Standard FAIRINO SDK teaching point format (20 elements, tool 0, user 0)
        self._dry_run_teaching_points: dict = {
            "R1": [40.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 50, 50, 0, 0, 0, 0],
            "R2": [-280.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 50, 50, 0, 0, 0, 0],
            "R3": [-280.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 50, 50, 0, 0, 0, 0],
            "R4": [40.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 50, 50, 0, 0, 0, 0],
        }

    def set_tool_do(self, do_id: int, status: int) -> int:
        """
        Send Tool Digital Output command to FAIRINO controller.

        Args:
            do_id: Output index on tool flange (0 or 1).
            status: 0 (LOW / de-energized) or 1 (HIGH / energized).

        Returns:
            0 on success, non-zero error code on failure.
        """
        status_int = 1 if status else 0
        if self.dry_run:
            logger.debug(f"[PhysicalFR3Backend] DRY SetToolDO({do_id}, {status_int})")
            return 0
        if not self._connected or self._rpc is None:
            self._last_error = "Cannot set_tool_do: Robot not connected"
            return -1

        try:
            if hasattr(self._rpc, "SetToolDO"):
                self._gripper_outputs_owned = True
                err = self._rpc.SetToolDO(int(do_id), status_int, block=0)
                if err != 0:
                    logger.error(f"[PhysicalFR3Backend] SetToolDO({do_id}, {status_int}) failed with code {err}")
                return err
            else:
                logger.error("[PhysicalFR3Backend] RPC handle has no SetToolDO method")
                return -1
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"[PhysicalFR3Backend] SetToolDO({do_id}, {status_int}) exception: {exc}")
            raise

    @property
    def gripper_outputs_owned(self) -> bool:
        """Whether this session has actually attempted a physical output write."""
        return self._gripper_outputs_owned

    @property
    def operational_mode(self) -> Optional[int]:
        """Return the current operational mode of the controller (0=auto, 1=manual, None=unconfigured)."""
        return self._operational_mode

    @property
    def lifecycle_state(self) -> str:
        """
        Operational lifecycle state:
        DISCONNECTED -> CONNECTED -> ENABLED -> MODE_CONFIGURED
        """
        if not self._connected:
            return "DISCONNECTED"
        if not self._enabled:
            return "CONNECTED"
        if self._operational_mode != 0:
            return "ENABLED"
        return "MODE_CONFIGURED"

    @property
    def is_enabled(self) -> bool:
        """Return True if robot motors are explicitly enabled and active."""
        if self.dry_run:
            return bool(self._enabled)
        if not self._connected or self._rpc is None:
            return False
        return bool(self._enabled)

    def enable_robot(self) -> bool:
        """
        Explicitly energize/enable physical robot servos.

        Must NOT be called automatically upon connection. Requires explicit operator
        or production execution workflow authorization.
        """
        if self.dry_run:
            logger.info("[PhysicalFR3Backend] DRY_RUN: enable_robot() -> True")
            self._enabled = True
            return True

        if not self._connected or self._rpc is None:
            err = "Cannot enable robot: backend is not connected"
            logger.error(f"[PhysicalFR3Backend] {err}")
            self._last_error = err
            return False

        try:
            logger.info(f"[PhysicalFR3Backend] Sending RobotEnable(1) to FR3 at {self.ip}...")
            err = self._rpc.RobotEnable(1)
            if err == 0:
                self._enabled = True
                logger.info("[PhysicalFR3Backend] Robot servos enabled successfully.")
                return True
            else:
                err_msg = f"RobotEnable(1) failed with return code {err}"
                logger.error(f"[PhysicalFR3Backend] {err_msg}")
                self._last_error = err_msg
                self._enabled = False
                return False
        except Exception as exc:
            self._last_error = str(exc)
            self._enabled = False
            logger.error(f"[PhysicalFR3Backend] RobotEnable(1) exception: {exc}")
            return False

    def recover_from_error(self) -> bool:
        """
        Recover from Emergency Stop or controller error:
        1. ResetAllError() to clear fault state.
        2. RobotEnable(1) to re-energize servo motors.
        3. Mode(0) to restore automatic trajectory mode.
        """
        if self.dry_run:
            self._motion_state = "IDLE"
            self._last_error = None
            self._command_error = None
            self._enabled = True
            return True

        if not self._connected or self._rpc is None:
            self._last_error = "Cannot recover: Not connected"
            return False

        try:
            logger.info(f"[PhysicalFR3Backend] Recovering from error/E-stop on FR3 at {self.ip}...")
            if hasattr(self._rpc, "ResetAllError"):
                err_reset = self._rpc.ResetAllError()
                logger.info(f"[PhysicalFR3Backend] ResetAllError returned: {err_reset}")

            err_en = self._rpc.RobotEnable(1)
            logger.info(f"[PhysicalFR3Backend] RobotEnable(1) returned: {err_en}")

            if hasattr(self._rpc, "Mode"):
                self._rpc.Mode(0)

            if err_en == 0:
                self._enabled = True
                self._motion_state = "IDLE"
                self._last_error = None
                self._command_error = None
                return True
            else:
                self._last_error = f"RobotEnable(1) failed with return code {err_en} (Kiểm tra xem nút E-Stop đã xoay nhả chưa)"
                return False
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"[PhysicalFR3Backend] Recovery exception: {exc}")
            return False

    def disable_robot(self) -> bool:
        """Explicitly de-energize physical robot servos."""
        if self.dry_run:
            logger.info("[PhysicalFR3Backend] DRY_RUN: disable_robot() -> True")
            self._enabled = False
            return True

        if not self._connected or self._rpc is None:
            self._enabled = False
            return True

        try:
            logger.info(f"[PhysicalFR3Backend] Sending RobotEnable(0) to FR3 at {self.ip}...")
            err = self._rpc.RobotEnable(0)
            self._enabled = False
            return err == 0
        except Exception as exc:
            self._last_error = str(exc)
            self._enabled = False
            logger.error(f"[PhysicalFR3Backend] RobotEnable(0) exception: {exc}")
            return False

    def set_operational_mode(self, mode: int = 0) -> bool:
        """Explicitly set controller operational mode (e.g. Mode 0 for program/automatic)."""
        if self.dry_run:
            self._operational_mode = mode
            return True

        if not self._connected or self._rpc is None:
            return False

        try:
            err = self._rpc.Mode(int(mode))
            if err == 0:
                self._operational_mode = mode
                return True
            logger.warning(f"[PhysicalFR3Backend] Mode({mode}) returned code {err}")
            return False
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"[PhysicalFR3Backend] Mode({mode}) exception: {exc}")
            return False

    def connect(self) -> bool:
        """
        Connect to the physical robot controller or initialize dry-run mock.

        CRITICAL SAFETY INVARIANT:
        connect() is strictly READ-ONLY. It opens the RPC interface and queries telemetry,
        but NEVER energizes robot servos (no RobotEnable(1)), NEVER modifies controller mode
        (no Mode(0)), and NEVER issues Tool DO writes / safe_idle (no SetToolDO).
        Motors remain unpowered and I/O unwritten until explicit authorization.
        """
        if self.dry_run:
            logger.info("[PhysicalFR3Backend] DRY_RUN mode enabled — skipping physical connection.")
            self._connected = True
            self._enabled = False
            self._operational_mode = None
            self._motion_state = "IDLE"
            return True

        if robot_sdk_core is None:
            err = "Module 'robot_sdk_core' is not available. Cannot connect to physical FR3."
            logger.error(f"[PhysicalFR3Backend] {err}")
            self._last_error = err
            self._connected = False
            self._enabled = False
            self._operational_mode = None
            self._motion_state = "ERROR"
            return False

        try:
            logger.info(f"[PhysicalFR3Backend] Connecting to FAIRINO FR3 at {self.ip} (READ-ONLY)...")
            self._rpc = robot_sdk_core.RPC(self.ip)
            time.sleep(1.0)

            # Check SDK connection status
            sdk_state = getattr(self._rpc, "SDK_state", False)
            if not sdk_state:
                raise RuntimeError(f"FAIRINO RPC failed to connect to {self.ip} (SDK_state=False)")

            self._connected = True
            self._enabled = False
            self._operational_mode = None
            self._motion_state = "IDLE"
            self._last_error = None
            logger.info(f"[PhysicalFR3Backend] Successfully connected to FR3 at {self.ip} (servos unpowered, mode unconfigured)")
            self._sync_hardware_state()
            return True

        except Exception as exc:
            self._last_error = str(exc)
            self._connected = False
            self._enabled = False
            self._operational_mode = None
            self._motion_state = "ERROR"
            logger.error(f"[PhysicalFR3Backend] Connection error: {exc}")
            return False

    def initialize_gripper_outputs(self) -> bool:
        """
        Explicit post-connect commissioning operation to safe-idle gripper outputs.
        MUST NOT be called automatically during read-only connect().
        """
        if self.gripper_driver is None:
            from src.hardware.gripper.two_output import TwoOutputGripperDriver
            self.gripper_driver = TwoOutputGripperDriver(
                set_do_fn=self.set_tool_do,
                dry_run=self.dry_run,
            )
        if hasattr(self.gripper_driver, "safe_idle"):
            try:
                self.gripper_driver.safe_idle()
                return True
            except Exception as exc:
                logger.error(f"[PhysicalFR3Backend] initialize_gripper_outputs error: {exc}")
                return False
        return True

    def disconnect(self) -> bool:
        """Disconnect and release the RPC handle, ensuring servos are disabled."""
        if self._enabled:
            try:
                self.disable_robot()
            except Exception:
                pass
        if self._gripper_outputs_owned and self.gripper_driver is not None and hasattr(self.gripper_driver, "safe_idle"):
            try:
                self.gripper_driver.safe_idle()
            except Exception:
                pass
        self._gripper_outputs_owned = False
        self._connected = False
        self._enabled = False
        self._operational_mode = None
        self._motion_state = "DISCONNECTED"
        self._joints_valid = False
        self._tcp_valid = False
        if self._rpc is not None:
            try:
                # Close connection if SDK supports it
                if hasattr(self._rpc, "CloseRPC"):
                    self._rpc.CloseRPC()
            except Exception:
                pass
            self._rpc = None
        logger.info("[PhysicalFR3Backend] Disconnected.")
        return True

    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def _finite_vector(values) -> Optional[List[float]]:
        try:
            if len(values) < 6:
                return None
            result = [float(v) for v in values[:6]]
            return result if all(math.isfinite(v) for v in result) else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _read_query(self, name: str, **kwargs):
        try:
            method = getattr(self._rpc, name, None)
            result = method(**kwargs) if callable(method) else None
            if isinstance(result, (tuple, list)) and len(result) >= 2 and result[0] == 0:
                return result[1]
        except Exception as exc:
            logger.debug("Read %s failed: %s", name, exc)
        return None

    def _sync_hardware_state(self) -> None:
        """Read telemetry without taking a lock across any motion or output call."""
        with self._snapshot_lock:
            self._sync_hardware_state_locked()

    def _sync_hardware_state_locked(self) -> None:
        if self.dry_run:
            self._joints_valid = self._tcp_valid = self._connected
            self._flange_pose_source = "MOCK"
            self._measurement_timestamp = time.time() if self._connected else self._measurement_timestamp
            return
        if not self._connected or self._rpc is None:
            self._joints_valid = self._tcp_valid = False
            self._controller_status_valid = False
            self._telemetry_error = "Controller disconnected"
            return

        # The bundled SDK getters return an in-memory packet, even when its
        # receive socket has stopped. Pin one packet so joints/TCP/status come
        # from the same frame; a repeated packet must not acquire a new time.
        rpc_fields = vars(self._rpc)
        packet = rpc_fields.get("robot_state_pkg")
        stream_mode = "robot_state_pkg" in rpc_fields
        if stream_mode:
            unavailable = (
                packet is None or isinstance(packet, type)
                or getattr(self._rpc, "sock_cli_state_state", True) is False
                or getattr(self._rpc, "reconnect_flag", False) is True
            )
            now_mono = time.monotonic()
            if unavailable:
                self._joints_valid = self._tcp_valid = False
                self._controller_status_valid = False
                self._telemetry_error = "Controller state stream unavailable"
                return
            if packet is self._last_stream_packet:
                if (self._last_stream_seen_monotonic is None
                        or now_mono - self._last_stream_seen_monotonic > self._stream_stale_after_s):
                    self._joints_valid = self._tcp_valid = False
                    self._controller_status_valid = False
                    self._telemetry_error = "Controller state stream stale"
                return
            self._last_stream_packet = packet
            self._last_stream_seen_monotonic = now_mono
            joints = self._finite_vector(getattr(packet, "jt_cur_pos", None))
            tcp = self._finite_vector(getattr(packet, "tl_cur_pos", None))
            flange = self._finite_vector(getattr(packet, "flange_cur_pos", None))
            estop = getattr(packet, "EmergencyStop", None)
            codes = [getattr(packet, "main_code", None), getattr(packet, "sub_code", None)]
            motion_done = getattr(packet, "motion_done", None)
        else:
            joints = self._finite_vector(self._read_query("GetActualJointPosDegree", flag=1))
            tcp = self._finite_vector(self._read_query("GetActualTCPPose", flag=1))
            flange = self._finite_vector(self._read_query("GetActualToolFlangePose", flag=1))
            estop = self._read_query("GetRobotEmergencyStopState")
            codes = self._read_query("GetRobotErrorCode")
            motion_done = self._read_query("GetRobotMotionDone")

        self._joints_valid = joints is not None
        self._tcp_valid = tcp is not None
        if joints is not None:
            self._current_joints_deg = joints
            self._measurement_timestamp = time.time()
        if tcp is not None:
            self._current_tcp_pose_mm_deg = tcp
        self._flange_authoritative = flange is not None
        self._flange_pose_source = "CONTROLLER" if flange is not None else "UNAVAILABLE"
        if flange is not None:
            self._current_flange_pose_mm_deg = flange
        self._telemetry_error = None if joints is not None and tcp is not None else "Missing or invalid joint/TCP telemetry"

        estop_valid = isinstance(estop, (int, float)) and estop in (0, 1)
        codes_valid = (
            isinstance(codes, (tuple, list)) and len(codes) >= 2
            and all(isinstance(v, (int, float)) and math.isfinite(v) and int(v) == v for v in codes[:2])
        )
        self._controller_status_valid = estop_valid and codes_valid
        fault = None
        if estop_valid and estop == 1:
            fault = "Controller E-Stop active"
        elif codes_valid and any(codes[:2]):
            fault = f"Controller error: main={int(codes[0])}, sub={int(codes[1])}"
        if fault is not None:
            if fault != self._controller_fault:
                self._fault_generation += 1
            self._controller_fault = fault
        elif self._controller_status_valid:
            self._controller_fault = None
        # Incomplete reads never erase a previously observed fault. Likewise,
        # a successful MotionDone read cannot override an E-stop/error.
        if self._controller_fault or self._command_error:
            self._motion_state = "ERROR"
            self._last_error = self._controller_fault or self._command_error
        elif self._controller_status_valid and isinstance(motion_done, (int, float)) and motion_done in (0, 1):
            self._motion_state = "IDLE" if motion_done == 1 else "MOVING"
            self._last_error = None

    def get_state_snapshot(self) -> RobotStateSnapshot:
        """Copy one measured state; never report commanded targets as measurements."""
        with self._snapshot_lock:
            self._sync_hardware_state_locked()
            return RobotStateSnapshot(
                robot_model="FR3",
                connected=self._connected,
                motion_state=self._motion_state,
                joints_deg=list(self._current_joints_deg),
                flange_pose_mm_deg=list(self._current_flange_pose_mm_deg),
                tcp_pose_mm_deg=list(self._current_tcp_pose_mm_deg),
                gripper_closed=self._gripper_closed,
                timestamp=time.time(),
                flange_pose_source=self._flange_pose_source,
                last_error=self._last_error,
                trajectory_stage=self._trajectory_stage,
                joints_valid=self._joints_valid,
                tcp_valid=self._tcp_valid,
                measurement_timestamp=self._measurement_timestamp,
                telemetry_error=self._telemetry_error,
            )

    def _finish_motion(self, fault_generation: int) -> bool:
        snapshot = self.get_state_snapshot()
        if (not snapshot.joints_valid or not self._controller_status_valid
                or self._fault_generation != fault_generation
                or snapshot.motion_state != "IDLE"):
            self._command_error = snapshot.last_error or snapshot.telemetry_error or "Motion completion not verified by controller"
            self._last_error = self._command_error
            self._motion_state = "ERROR"
            return False
        return True

    def set_trajectory_stage(self, stage: Optional[str]) -> None:
        """Set the authoritative trajectory stage (PREPOSITION, LIFT, TRANSIT, LAND, COMPLETE, IDLE)."""
        self._trajectory_stage = stage

    def move_joint(
        self,
        target_joints_deg: Sequence[float],
        speed_factor: Optional[float] = None,
    ) -> bool:
        """Execute joint-space motion (MoveJ) to target angles."""
        if not self._connected:
            self._last_error = "Cannot move_joint: Robot not connected"
            return False

        if not self.dry_run and not self._enabled:
            self._last_error = "Cannot move_joint: Robot not enabled"
            return False

        if len(target_joints_deg) < 6:
            raise ValueError(f"target_joints_deg must contain 6 joint angles, got {len(target_joints_deg)}")

        vel = float(speed_factor * 100.0) if speed_factor is not None else self.default_vel
        target_q = [float(q) for q in target_joints_deg[:6]]

        if self.dry_run:
            logger.info(f"[PhysicalFR3Backend] DRY MoveJ -> joints={[round(q, 1) for q in target_q]} vel={vel}")
            self._current_joints_deg = target_q
            return True

        if self._rpc is None:
            return False

        if self._command_error or self._controller_fault:
            self._last_error = self._controller_fault or self._command_error
            return False
        fault_generation = self._fault_generation
        self._motion_state = "MOVING"
        try:
            # MoveJ call signature for FAIRINO SDK
            err = self._rpc.MoveJ(
                joint_pos=target_q,
                desc_pos=[0.0] * 6,
                tool=self.tool_num,
                user=self.user_num,
                vel=vel,
                acc=0.0,
                ovl=100.0,
                exaxis_pos=[0.0] * 4,
                blendT=-1.0,
                offset_flag=0,
                offset_pos=[0.0] * 6,
            )
            # Strict motion success check: only code 0 is authoritative success
            if not is_motion_success_code(err):
                raise RuntimeError(f"MoveJ failed with return code {err}")
            return self._finish_motion(fault_generation)
        except Exception as exc:
            self._last_error = str(exc)
            self._command_error = str(exc)
            self._motion_state = "ERROR"
            logger.error(f"[PhysicalFR3Backend] MoveJ error: {exc}")
            return False

    def move_cartesian(
        self,
        target_pose_mm_deg: Sequence[float],
        speed_factor: Optional[float] = None,
        samples: int = 20,
    ) -> bool:
        """Execute Cartesian-space linear motion (MoveL/MoveCart) to target end-effector pose."""
        if not self._connected:
            self._last_error = "Cannot move_cartesian: Robot not connected"
            return False

        if not self.dry_run and not self._enabled:
            self._last_error = "Cannot move_cartesian: Robot not enabled"
            return False

        if len(target_pose_mm_deg) < 6:
            raise ValueError(f"target_pose_mm_deg must contain [X, Y, Z, Rx, Ry, Rz], got {len(target_pose_mm_deg)}")

        vel = float(speed_factor * 100.0) if speed_factor is not None else self.default_vel
        target_pose = [float(v) for v in target_pose_mm_deg[:6]]

        if self.dry_run:
            logger.info(f"[PhysicalFR3Backend] DRY MoveCart -> pose={[round(v, 1) for v in target_pose]} vel={vel}")
            self._current_tcp_pose_mm_deg = target_pose
            return True

        if self._rpc is None:
            return False

        if self._command_error or self._controller_fault:
            self._last_error = self._controller_fault or self._command_error
            return False
        fault_generation = self._fault_generation
        self._motion_state = "MOVING"
        try:
            err = self._rpc.MoveCart(
                desc_pos=target_pose,
                tool=self.tool_num,
                user=self.user_num,
                vel=vel,
                acc=0.0,
                ovl=100.0,
                blendT=-1.0,
                config=-1,
            )
            # Strict motion success check: only code 0 is authoritative success
            if not is_motion_success_code(err):
                raise RuntimeError(f"MoveCart failed with return code {err}")
            return self._finish_motion(fault_generation)
        except Exception as exc:
            self._last_error = str(exc)
            self._command_error = str(exc)
            self._motion_state = "ERROR"
            logger.error(f"[PhysicalFR3Backend] MoveCart error: {exc}")
            return False

    def set_gripper(self, closed: bool) -> bool:
        """
        Command gripper open/close.
        Exclusively delegates to the authoritative TwoOutputGripperDriver to enforce
        mutual exclusion, deadtime, calibrated pulse duration, and safe idle.
        Raw uncontrolled SetToolDO fallback is strictly forbidden.
        """
        if self.gripper_driver is None:
            from src.hardware.gripper.two_output import TwoOutputGripperDriver
            import config
            self.gripper_driver = TwoOutputGripperDriver(
                set_do_fn=self.set_tool_do,
                open_do_id=int(getattr(config, "TOOL_DO_OPEN", 1)),
                close_do_id=int(getattr(config, "TOOL_DO_CLOSE", 0)),
                open_pulse_sec=float(getattr(config, "TOOL_DO_OPEN_PULSE_SEC", 0.35)),
                close_pulse_sec=float(getattr(config, "TOOL_DO_CLOSE_PULSE_SEC", 0.30)),
                deadtime_sec=float(getattr(config, "TOOL_DO_DEADTIME_SEC", 0.10)),
                dry_run=self.dry_run,
            )

        try:
            if closed:
                ok = bool(self.gripper_driver.close())
            else:
                ok = bool(self.gripper_driver.open())

            if ok:
                self._gripper_closed = bool(closed)
                return True
            else:
                # Command failed; preserve previous known state
                return False
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"[PhysicalFR3Backend] set_gripper error: {exc}")
            # Ensure outputs return to safe idle after failure
            try:
                if hasattr(self.gripper_driver, "safe_idle"):
                    self.gripper_driver.safe_idle()
            except Exception:
                pass
            return False

    def stop(self) -> bool:
        """Emergency stop / halt current motion immediately and safe-idle gripper."""
        self._fault_generation += 1
        self._command_error = "Motion interrupted by stop"
        self._last_error = self._command_error
        self._motion_state = "ERROR"
        if self._gripper_outputs_owned and self.gripper_driver is not None and hasattr(self.gripper_driver, "safe_idle"):
            try:
                self.gripper_driver.safe_idle()
            except Exception:
                pass

        if self.dry_run or self._rpc is None:
            logger.info("[PhysicalFR3Backend] DRY StopMotion called.")
            return True

        try:
            if hasattr(self._rpc, "StopMotion"):
                self._rpc.StopMotion()
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"[PhysicalFR3Backend] StopMotion error: {exc}")
            return False

    def set_mock_teaching_points(self, points: dict) -> None:
        """Set mock teaching points for dry-run mode and unit testing."""
        self._dry_run_teaching_points = {k: list(v) for k, v in points.items()}

    def get_teaching_point(self, name: str) -> Tuple[int, List[float]]:
        """
        Query teaching point by name from FAIRINO controller.
        Returns (err_code, data_list).
        err_code == 0 indicates success.
        """
        if self.dry_run:
            if name in self._dry_run_teaching_points:
                return 0, list(self._dry_run_teaching_points[name])
            return -1, []

        if not self._connected or self._rpc is None:
            return -1, []

        try:
            if hasattr(self._rpc, "GetRobotTeachingPoint"):
                res = self._rpc.GetRobotTeachingPoint(name)
                if isinstance(res, (list, tuple)) and len(res) >= 2:
                    err, data = res[0], res[1]
                else:
                    return -1, []
                if err == 0 and data is not None:
                    if isinstance(data, str):
                        data = [v.strip() for v in data.split(",") if v.strip()]
                    parsed = [float(str(v).strip()) for v in data]
                    return 0, parsed
                return int(err), []
            return -1, []
        except Exception as exc:
            logger.error(f"[PhysicalFR3Backend] Error reading teaching point '{name}': {exc}")
            return -1, []
