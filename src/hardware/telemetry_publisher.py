"""
TelemetryPublisher & FR5 Kinematics Simulator for 3D Live Mirror (robot-3d-viewer)
Broadcasts real-time FR5 cobot state over WebSocket ws://127.0.0.1:8765.
"""

import asyncio
import json
import math
import threading
import time
from typing import List, Optional, Set
import numpy as np

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    websockets = None
    WebSocketServerProtocol = None


class FR5Kinematics:
    """
    Standard Fairino FR5 6-DOF Kinematics (DH parameters in meters / radians).
    Link dimensions (mm):
      Base to Shoulder (d1): 152 mm
      Upperarm length (a2): 425 mm
      Forearm length (a3): 395 mm
      Wrist 1 (d4): 102 mm
      Wrist 2 (d5): 102 mm
      Wrist 3 / Flange (d6): 100 mm
    """
    D1 = 0.152
    A2 = 0.425
    A3 = 0.395
    D4 = 0.1021
    D5 = 0.1020
    D6 = 0.1000

    @classmethod
    def forward_kinematics(cls, joints_deg: List[float]) -> List[float]:
        """
        Approximate Forward Kinematics for FR5.
        Input: 6 joint angles in degrees.
        Output: [X, Y, Z (mm), Rx, Ry, Rz (deg)].
        """
        j = [math.radians(deg) for deg in joints_deg]
        j1, j2, j3, j4, j5, j6 = j

        # Base rotation in XY plane
        r = cls.A2 * math.cos(j2) + cls.A3 * math.cos(j2 + j3) + (cls.D4 + cls.D6) * math.sin(j2 + j3 + j4)
        x_m = r * math.cos(j1)
        y_m = r * math.sin(j1)
        z_m = cls.D1 + cls.A2 * math.sin(j2) + cls.A3 * math.sin(j2 + j3) - (cls.D4 + cls.D6) * math.cos(j2 + j3 + j4)

        # Orientation approximation (Rx, Ry, Rz in degrees)
        rx = 180.0
        ry = 0.0
        rz = math.degrees(j1 + j6)

        return [round(x_m * 1000.0, 2), round(y_m * 1000.0, 2), round(z_m * 1000.0, 2), round(rx, 2), round(ry, 2), round(rz, 2)]

    @classmethod
    def inverse_kinematics(cls, tcp_mm: List[float], seed_joints: Optional[List[float]] = None) -> List[float]:
        """
        Inverse Kinematics for vertical pick-and-place with downward pointing tool.
        Input: TCP [X, Y, Z (mm), Rx, Ry, Rz (deg)].
        Output: 6 joint angles in degrees.
        """
        x = tcp_mm[0] / 1000.0
        y = tcp_mm[1] / 1000.0
        z = tcp_mm[2] / 1000.0

        # Joint 1: Base yaw pointing towards target
        j1 = math.atan2(y, x)

        # Wrist position in cylindrical coordinates (radius in XY, height in Z)
        r_xy = math.sqrt(x * x + y * y)
        
        # Flange offset compensation (tool pointing downwards: -Z)
        wrist_r = r_xy - (cls.D5)
        wrist_z = z + cls.D6 - cls.D1

        # 2-link planar IK for upperarm and forearm (A2, A3)
        d_sq = wrist_r * wrist_r + wrist_z * wrist_z
        d_val = math.sqrt(max(0.01, d_sq))

        # Cosine rule for elbow (j3)
        cos_j3 = (d_sq - cls.A2 * cls.A2 - cls.A3 * cls.A3) / (2.0 * cls.A2 * cls.A3)
        cos_j3 = max(-1.0, min(1.0, cos_j3))
        j3 = -math.acos(cos_j3)  # Elbow up

        # Shoulder angle (j2)
        alpha = math.atan2(wrist_z, wrist_r)
        beta = math.atan2(cls.A3 * math.sin(-j3), cls.A2 + cls.A3 * math.cos(j3))
        j2 = alpha + beta

        # Wrist pitch (j4) to keep end-effector vertical
        # Downward vertical constraint: j2 + j3 + j4 = -pi/2
        j4 = -math.pi / 2.0 - (j2 + j3)

        # Wrist roll and yaw
        j5 = -math.pi / 2.0  # standard downward orientation
        tool_rz = math.radians(tcp_mm[5]) if len(tcp_mm) > 5 else 0.0
        j6 = tool_rz - j1

        return [
            round(math.degrees(j1), 2),
            round(math.degrees(j2), 2),
            round(math.degrees(j3), 2),
            round(math.degrees(j4), 2),
            round(math.degrees(j5), 2),
            round(math.degrees(j6), 2),
        ]


class TelemetryPublisher:
    """
    WebSocket Server broadcasting FR5 telemetry packets to 3D Live Mirror (robot-3d-viewer).
    Default URL: ws://127.0.0.1:8765
    """
    _instance: Optional['TelemetryPublisher'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, host: str = "127.0.0.1", port: int = 8765, robot_model: str = "FR3") -> 'TelemetryPublisher':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(host=host, port=port, robot_model=robot_model)
            return cls._instance

    @classmethod
    def reset_instance(cls):
        """Stop and reset singleton instance (useful for clean unit testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, robot_model: str = "FR3"):
        self.host = host
        self.port = port
        self.robot_model = robot_model
        self.clients: Set = set()
        self.clients_lock = threading.Lock()
        self._state_lock = threading.Lock()

        # Default Home Pose and Joints
        if robot_model == "FR3":
            self.current_joints = [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]
            self.current_tcp = [-367.696, -101.999, 66.0, 90.0, 0.0, 0.0]
        else:
            self.current_tcp = [420.0, 0.0, 280.0, 180.0, 0.0, 0.0]
            self.current_joints = FR5Kinematics.inverse_kinematics(self.current_tcp)
        self.is_gripper_active = False
        self._motion_state = "IDLE"
        self._trajectory_stage: Optional[str] = None
        self._last_error: Optional[str] = None
        self._command_handlers: List = []
        self._latest_world_state: Optional[dict] = None
        self._latest_board_placement: Optional[dict] = None
        self.placement_version: int = 1

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False

    def register_command_handler(self, handler):
        """Register a callback to process incoming commands from WebSocket clients."""
        with self._state_lock:
            if handler not in self._command_handlers:
                self._command_handlers.append(handler)

    def start(self):
        """Start WebSocket server in background daemon thread."""
        if self._running:
            return
        self._running = True
        self._server_thread = threading.Thread(target=self._run_server, daemon=True, name="TelemetryServerThread")
        self._server_thread.start()

        # Start continuous 30 FPS heartbeat publisher
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="TelemetryHeartbeatThread")
        self._heartbeat_thread.start()
        print(f"[TELEMETRY] Virtual Robot Telemetry Server started at ws://{self.host}:{self.port}")

    def stop(self):
        """Stop telemetry server and threads."""
        self._running = False

    def _run_server(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def handler(websocket):
            with self.clients_lock:
                self.clients.add(websocket)
            print(f"[TELEMETRY] 3D Viewer Client connected ({len(self.clients)} active).")
            try:
                # Send immediate state on connect
                await websocket.send(self._make_packet_json())
                with self._state_lock:
                    ws_data = self._latest_world_state
                    bp_data = self._latest_board_placement
                if bp_data is not None:
                    await websocket.send(json.dumps(bp_data))
                if ws_data is not None:
                    await websocket.send(json.dumps(ws_data))
                # Listen for incoming client commands
                async for raw_msg in websocket:
                    try:
                        cmd_dict = json.loads(raw_msg)
                        if isinstance(cmd_dict, dict):
                            with self._state_lock:
                                handlers = list(self._command_handlers)
                            for ch in handlers:
                                try:
                                    ch(cmd_dict)
                                except Exception as cmd_err:
                                    print(f"[TELEMETRY WARN] Command execution error: {cmd_err}")
                    except Exception as parse_err:
                        print(f"[TELEMETRY WARN] Failed to parse client message: {parse_err}")
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                print(f"[TELEMETRY WARN] Client socket error: {e}")
            finally:
                with self.clients_lock:
                    self.clients.discard(websocket)
                print(f"[TELEMETRY] 3D Viewer Client disconnected ({len(self.clients)} active).")

        async def main():
            async with websockets.serve(handler, self.host, self.port):
                await asyncio.Future()  # Run forever

        try:
            self._loop.run_until_complete(main())
        except Exception as e:
            print(f"[TELEMETRY] Server loop terminated: {e}")

    def _make_packet_json(self) -> str:
        with self._state_lock:
            packet = {
                "type": "robot_state",
                "robot_model": self.robot_model,
                "timestamp": time.time(),
                "joints": list(self.current_joints),
                "tcp": list(self.current_tcp),
                "gripper": self.is_gripper_active,
                "motion_state": self._motion_state,
                "trajectory_stage": self._trajectory_stage,
                "last_error": self._last_error,
                "placement_version": self.placement_version,
            }
        return json.dumps(packet)

    def update_from_snapshot(self, snapshot):
        """Update telemetry state from authoritative RobotStateSnapshot."""
        with self._state_lock:
            self.robot_model = snapshot.robot_model
            self.current_joints = list(snapshot.joints_deg)
            self.current_tcp = list(snapshot.tcp_pose_mm_deg)
            self.is_gripper_active = bool(snapshot.gripper_closed)
            self._motion_state = snapshot.motion_state
            self._trajectory_stage = getattr(snapshot, "trajectory_stage", None)
            self._last_error = snapshot.last_error
            self.placement_version = getattr(snapshot, "placement_version", 1)
        self._broadcast_sync()

    def update_state(
        self,
        joints_deg: List[float],
        tcp_mm_deg: List[float],
        gripper: bool = False,
        robot_model: str = "FR3",
        motion_state: str = "IDLE",
        trajectory_stage: Optional[str] = None,
        last_error: Optional[str] = None,
    ):
        """Update telemetry state with explicit values."""
        with self._state_lock:
            self.robot_model = robot_model
            self.current_joints = list(joints_deg)
            self.current_tcp = list(tcp_mm_deg)
            self.is_gripper_active = bool(gripper)
            self._motion_state = motion_state
            self._trajectory_stage = trajectory_stage
            self._last_error = last_error
        self._broadcast_sync()

    def update_world_state(self, world_state):
        """Update and broadcast latest world_state (pieces and gripper physics)."""
        if hasattr(world_state, "to_dict"):
            data = world_state.to_dict()
        else:
            data = dict(world_state)
        with self._state_lock:
            self._latest_world_state = data
        self._broadcast_world_state_sync()

    def _broadcast_world_state_sync(self):
        """Broadcast latest world_state packet to connected clients."""
        if not self._loop or not self.clients:
            return
        with self._state_lock:
            if self._latest_world_state is None:
                return
            msg = json.dumps(self._latest_world_state)

        with self.clients_lock:
            clients_copy = list(self.clients)

        for client in clients_copy:
            try:
                asyncio.run_coroutine_threadsafe(client.send(msg), self._loop)
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                print(f"[TELEMETRY WARN] Failed to send world_state packet to client: {e}")

    def _broadcast_sync(self):
        """Broadcast latest packet to all connected clients."""
        if not self._loop or not self.clients:
            return
        msg = self._make_packet_json()

        with self.clients_lock:
            clients_copy = list(self.clients)

        for client in clients_copy:
            try:
                asyncio.run_coroutine_threadsafe(client.send(msg), self._loop)
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                # Throttled/informative warning on failed send
                print(f"[TELEMETRY WARN] Failed to send packet to client: {e}")

    def broadcast_custom(self, packet_dict: dict) -> None:
        """Broadcast an arbitrary event packet (e.g. trajectory_result) to all connected clients."""
        if isinstance(packet_dict, dict) and packet_dict.get("type") == "board_placement":
            with self._state_lock:
                self._latest_board_placement = dict(packet_dict)
                if "placement_version" in packet_dict:
                    self.placement_version = int(packet_dict["placement_version"])
        if not self._loop or not self.clients:
            return
        msg = json.dumps(packet_dict)
        with self.clients_lock:
            clients_copy = list(self.clients)
        for client in clients_copy:
            try:
                asyncio.run_coroutine_threadsafe(client.send(msg), self._loop)
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception:
                pass

    def _heartbeat_loop(self):
        """Broadcast current state at 25 Hz to ensure smooth UI mirror."""
        step_idx = 0
        while self._running:
            self._broadcast_sync()
            if step_idx % 2 == 0:
                self._broadcast_world_state_sync()
            step_idx += 1
            time.sleep(0.04)

    def set_gripper(self, active: bool):
        self.is_gripper_active = active
        self._broadcast_sync()

    def update_pose_immediate(self, tcp: List[float]):
        """Instantly set pose without animation."""
        self.current_tcp = list(tcp)
        self.current_joints = FR5Kinematics.inverse_kinematics(tcp, seed_joints=self.current_joints)
        self._broadcast_sync()

    def update_joints_immediate(self, joints: List[float]):
        """Instantly set joints without animation."""
        self.current_joints = list(joints)
        self.current_tcp = FR5Kinematics.forward_kinematics(joints)
        self._broadcast_sync()

    def animate_to_pose(self, target_tcp: List[float], duration: float = 1.2, fps: int = 30):
        """
        Smoothly interpolate from current TCP to target TCP at specified FPS.
        Calculates Inverse Kinematics at each step and streams to 3D Viewer.
        """
        start_tcp = list(self.current_tcp)
        start_joints = list(self.current_joints)
        target_joints = FR5Kinematics.inverse_kinematics(target_tcp, seed_joints=start_joints)

        steps = max(1, int(duration * fps))
        dt = duration / steps

        for i in range(1, steps + 1):
            t = i / steps
            # Smooth Hermite / Cubic ease in-out
            eased_t = t * t * (3.0 - 2.0 * t)

            # Interpolate TCP
            interp_tcp = [
                start_tcp[k] + (target_tcp[k] - start_tcp[k]) * eased_t
                for k in range(min(len(start_tcp), len(target_tcp)))
            ]
            # Interpolate Joints
            interp_joints = [
                start_joints[k] + (target_joints[k] - start_joints[k]) * eased_t
                for k in range(min(len(start_joints), len(target_joints)))
            ]

            self.current_tcp = interp_tcp
            self.current_joints = interp_joints
            self._broadcast_sync()
            time.sleep(dt)

        self.current_tcp = list(target_tcp)
        self.current_joints = target_joints
        self._broadcast_sync()

    def animate_to_joints(self, target_joints: List[float], duration: float = 1.2, fps: int = 30):
        """
        Smoothly interpolate joint angles.
        """
        start_joints = list(self.current_joints)
        steps = max(1, int(duration * fps))
        dt = duration / steps

        for i in range(1, steps + 1):
            t = i / steps
            eased_t = t * t * (3.0 - 2.0 * t)
            interp_joints = [
                start_joints[k] + (target_joints[k] - start_joints[k]) * eased_t
                for k in range(len(start_joints))
            ]
            self.current_joints = interp_joints
            self.current_tcp = FR5Kinematics.forward_kinematics(interp_joints)
            self._broadcast_sync()
            time.sleep(dt)

        self.current_joints = list(target_joints)
        self.current_tcp = FR5Kinematics.forward_kinematics(target_joints)
        self._broadcast_sync()
