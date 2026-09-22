"""
Physical FR3 Robot Backend implementing canonical RobotBackend interface.

Communicates with physical FAIRINO FR3 (or compatible controller) via Ethernet RPC SDK.
Adheres strictly to the canonical RobotBackend abstraction from src/hardware/backends/base.py.
Does NOT manage Xiangqi rules, camera homography, or game state.
"""

from typing import Any, List, Optional, Sequence
import logging
import math
import time
import numpy as np

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot

logger = logging.getLogger(__name__)

try:
    from src.hardware import robot_sdk_core
except ImportError:
    robot_sdk_core = None


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
        self._motion_state: str = "DISCONNECTED"
        self._last_error: Optional[str] = None
        self._gripper_closed: bool = False

        # Internal state cache (for dry-run and between read cycles)
        self._current_joints_deg: List[float] = [0.0, -45.0, 90.0, -135.0, -90.0, 0.0]
        self._current_tcp_pose_mm_deg: List[float] = [-360.0, 0.0, 200.0, 180.0, 0.0, 90.0]
        self._current_flange_pose_mm_deg: List[float] = [-360.0, 0.0, 418.0, 180.0, 0.0, 90.0]

    def connect(self) -> bool:
        """Connect to the physical robot controller or initialize dry-run mock."""
        if self.dry_run:
            logger.info("[PhysicalFR3Backend] DRY_RUN mode enabled — skipping physical connection.")
            self._connected = True
            self._motion_state = "IDLE"
            return True

        if robot_sdk_core is None:
            err = "Module 'robot_sdk_core' is not available. Cannot connect to physical FR3."
            logger.error(f"[PhysicalFR3Backend] {err}")
            self._last_error = err
            self._connected = False
            self._motion_state = "ERROR"
            return False

        try:
            logger.info(f"[PhysicalFR3Backend] Connecting to FAIRINO FR3 at {self.ip}...")
            self._rpc = robot_sdk_core.RPC(self.ip)
            time.sleep(1.0)
            
            # Check SDK connection status
            sdk_state = getattr(self._rpc, "SDK_state", False)
            if not sdk_state:
                raise RuntimeError(f"FAIRINO RPC failed to connect to {self.ip} (SDK_state=False)")

            # Enable robot
            err = self._rpc.RobotEnable(1)
            if err != 0:
                logger.warning(f"[PhysicalFR3Backend] RobotEnable(1) returned code {err}")

            # Set mode 0 (manual/program auto mode)
            err = self._rpc.Mode(0)
            if err != 0:
                logger.warning(f"[PhysicalFR3Backend] Mode(0) returned code {err}")

            self._connected = True
            self._motion_state = "IDLE"
            self._last_error = None
            logger.info(f"[PhysicalFR3Backend] Successfully connected to FR3 at {self.ip}")
            self._sync_hardware_state()
            return True

        except Exception as exc:
            self._last_error = str(exc)
            self._connected = False
            self._motion_state = "ERROR"
            logger.error(f"[PhysicalFR3Backend] Connection error: {exc}")
            return False

    def disconnect(self) -> bool:
        """Disconnect and release the RPC handle."""
        self._connected = False
        self._motion_state = "DISCONNECTED"
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

    def _sync_hardware_state(self) -> None:
        """Query actual hardware joint positions and TCP pose."""
        if not self._connected or self.dry_run or self._rpc is None:
            return

        try:
            # Query actual joints
            if hasattr(self._rpc, "GetActualJointPosDegree"):
                err, joints = self._rpc.GetActualJointPosDegree(flag=1)
                if err == 0 and len(joints) >= 6:
                    self._current_joints_deg = [float(v) for v in joints[:6]]

            # Query actual TCP pose
            if hasattr(self._rpc, "GetActualTCPPose"):
                err, pose = self._rpc.GetActualTCPPose(flag=1)
                if err == 0 and len(pose) >= 6:
                    self._current_tcp_pose_mm_deg = [float(v) for v in pose[:6]]
        except Exception as exc:
            logger.debug(f"[PhysicalFR3Backend] Hardware state sync failed: {exc}")

    def get_state_snapshot(self) -> RobotStateSnapshot:
        """Return immutable, thread-safe snapshot of current authoritative state."""
        self._sync_hardware_state()
        return RobotStateSnapshot(
            robot_model="FR3",
            connected=self._connected,
            motion_state=self._motion_state,
            joints_deg=list(self._current_joints_deg),
            flange_pose_mm_deg=list(self._current_flange_pose_mm_deg),
            tcp_pose_mm_deg=list(self._current_tcp_pose_mm_deg),
            gripper_closed=self._gripper_closed,
            timestamp=time.time(),
            last_error=self._last_error,
        )

    def move_joint(
        self,
        target_joints_deg: Sequence[float],
        speed_factor: Optional[float] = None,
    ) -> bool:
        """Execute joint-space motion (MoveJ) to target angles."""
        if not self._connected:
            self._last_error = "Cannot move_joint: Robot not connected"
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
            # Codes 0 or 112 (complete/ok) are success
            if err not in (0, 112):
                raise RuntimeError(f"MoveJ failed with return code {err}")
            self._current_joints_deg = target_q
            self._motion_state = "IDLE"
            return True
        except Exception as exc:
            self._last_error = str(exc)
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
            if err not in (0, 112):
                raise RuntimeError(f"MoveCart failed with return code {err}")
            self._current_tcp_pose_mm_deg = target_pose
            self._motion_state = "IDLE"
            return True
        except Exception as exc:
            self._last_error = str(exc)
            self._motion_state = "ERROR"
            logger.error(f"[PhysicalFR3Backend] MoveCart error: {exc}")
            return False

    def set_gripper(self, closed: bool) -> bool:
        """Command gripper open/close."""
        self._gripper_closed = bool(closed)
        if self.gripper_driver is not None:
            if closed:
                return bool(self.gripper_driver.close())
            else:
                return bool(self.gripper_driver.open())

        # Fallback if no separate gripper driver injected
        if self.dry_run or self._rpc is None:
            logger.info(f"[PhysicalFR3Backend] DRY Gripper -> {'CLOSE' if closed else 'OPEN'}")
            return True

        try:
            # Verified wiring default: DO0=close, DO1=open
            if closed:
                self._rpc.SetToolDO(0, 1, block=0)
                time.sleep(0.3)
                self._rpc.SetToolDO(0, 0, block=0)
            else:
                self._rpc.SetToolDO(1, 1, block=0)
                time.sleep(0.3)
                self._rpc.SetToolDO(1, 0, block=0)
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"[PhysicalFR3Backend] set_gripper error: {exc}")
            return False

    def stop(self) -> bool:
        """Emergency stop / halt current motion immediately."""
        self._motion_state = "IDLE"
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
