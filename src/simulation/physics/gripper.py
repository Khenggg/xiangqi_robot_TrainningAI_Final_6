"""
Virtual kinematic gripper proxy and deterministic grasp / attachment manager.
"""

from collections import deque
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

import pybullet as p
from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.state import GraspResult, GraspStatus, PiecePhysicalState
from src.simulation.physics.transforms import (
    quat_to_rot_matrix,
    rot_matrix_to_quat,
)
from src.simulation.physics.validation import validate_gripper_profile


class VirtualGripper:
    """
    Kinematic gripper proxy attached to the Virtual FR3 robot.
    Operates natively in robot_base frame.
    """

    def __init__(
        self,
        profile_path: Optional[Union[str, Path]] = None,
    ):
        if profile_path is None:
            profile_path = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "virtual_gripper_profile.json"

        profile_path = Path(profile_path)
        if not profile_path.is_file():
            raise FileNotFoundError(f"Gripper profile not found at {profile_path}")

        with open(profile_path, "r", encoding="utf-8-sig") as f:
            self.profile = json.load(f)

        validate_gripper_profile(self.profile)

        self.model = self.profile["gripper_model"]
        self.tcp_to_grasp_center = np.array(
            self.profile["tcp_to_grasp_center_m"],
            dtype=float,
        )
        cap = self.profile["capture_volume"]
        self.capture_radius_xy = float(cap["xy_radius_m"])
        self.capture_half_height_z = float(cap["z_half_height_m"])

        stroke = self.profile["stroke"]
        self.open_width_m = float(stroke["open_width_m"])
        self.closed_width_m = float(stroke["closed_width_m"])
        self.travel_axis = stroke.get("travel_axis", "X")

        palm = self.profile["palm"]
        self.palm_dimensions_m = np.array(palm["dimensions_m"], dtype=float)

        jaw = self.profile["jaw"]
        self.jaw_dimensions_m = np.array(jaw["dimensions_m"], dtype=float)

        # PyBullet body IDs (managed by VirtualPhysicalWorld)
        self.client_id: int = -1
        self.palm_body_id: int = -1
        self.left_jaw_body_id: int = -1
        self.right_jaw_body_id: int = -1

        # Runtime state
        self.is_closed = False
        self.jaw_width_m = self.open_width_m

        # Flange/TCP in robot_base: position [m], quaternion [x, y, z, w]
        self.tcp_pos = np.zeros(3, dtype=float)
        self.tcp_quat = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

        # Grasp center frame
        self.grasp_pos = np.zeros(3, dtype=float)
        self.grasp_quat = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

        # Attachment tracking
        self.attached_piece: Optional[XiangqiPieceBody] = None
        self.T_gripper_piece: Optional[np.ndarray] = None  # 4x4 matrix invariant

        # Velocity estimation buffer: stores (timestamp, grasp_pos)
        self._history = deque(maxlen=10)

    @property
    def is_attached(self) -> bool:
        return self.attached_piece is not None

    @property
    def attached_piece_id(self) -> Optional[str]:
        return self.attached_piece.piece_id if self.attached_piece is not None else None

    @property
    def proxy_body_ids(self) -> List[int]:
        return [b for b in (self.palm_body_id, self.left_jaw_body_id, self.right_jaw_body_id) if b >= 0]

    def spawn_proxies(self, client_id: int) -> None:
        """
        Spawn kinematic PyBullet collision proxy bodies for palm, left jaw, and right jaw
        using dimensions strictly loaded from shared/virtual_gripper_profile.json.
        """
        self.client_id = client_id
        palm_half = (self.palm_dimensions_m / 2.0).tolist()
        jaw_half = (self.jaw_dimensions_m / 2.0).tolist()

        col_palm = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=palm_half,
            physicsClientId=client_id,
        )
        self.palm_body_id = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=col_palm,
            basePosition=[0.0, 0.0, -10.0],
            physicsClientId=client_id,
        )

        col_jaw = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=jaw_half,
            physicsClientId=client_id,
        )
        self.left_jaw_body_id = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=col_jaw,
            basePosition=[0.0, 0.0, -10.0],
            physicsClientId=client_id,
        )
        self.right_jaw_body_id = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=col_jaw,
            basePosition=[0.0, 0.0, -10.0],
            physicsClientId=client_id,
        )
        self._update_proxy_poses()

    def remove_proxies(self) -> None:
        """Safely remove proxy bodies from PyBullet."""
        if self.client_id >= 0:
            for b in (self.palm_body_id, self.left_jaw_body_id, self.right_jaw_body_id):
                if b >= 0:
                    try:
                        p.removeBody(b, physicsClientId=self.client_id)
                    except Exception:
                        pass
        self.palm_body_id = -1
        self.left_jaw_body_id = -1
        self.right_jaw_body_id = -1

    def _update_proxy_poses(self) -> None:
        """Synchronize kinematic PyBullet proxy bodies to current TCP pose and jaw width."""
        if self.client_id < 0 or self.palm_body_id < 0:
            return

        R_tcp = quat_to_rot_matrix(self.tcp_quat)
        p_tcp = self.tcp_pos

        palm_dz = float(self.palm_dimensions_m[2])
        jaw_dz = float(self.jaw_dimensions_m[2])
        half_w = float(self.jaw_width_m) / 2.0

        # TCP is at the midpoint of the finger tips at Z=0.
        # Jaws extend backwards (towards flange) along -Z from Z=0 to -jaw_dz.
        # Palm extends backwards behind the jaws from -jaw_dz to -(jaw_dz + palm_dz).
        p_palm = p_tcp + R_tcp @ np.array([0.0, 0.0, -jaw_dz - palm_dz / 2.0])
        p.resetBasePositionAndOrientation(
            self.palm_body_id,
            p_palm.tolist(),
            list(self.tcp_quat),
            physicsClientId=self.client_id,
        )

        if self.travel_axis == "Y":
            left_loc = np.array([0.0, -half_w, -jaw_dz / 2.0])
            right_loc = np.array([0.0, half_w, -jaw_dz / 2.0])
        elif self.travel_axis == "Z":
            left_loc = np.array([0.0, 0.0, -jaw_dz / 2.0 - half_w])
            right_loc = np.array([0.0, 0.0, -jaw_dz / 2.0 + half_w])
        else:  # "X"
            left_loc = np.array([-half_w, 0.0, -jaw_dz / 2.0])
            right_loc = np.array([half_w, 0.0, -jaw_dz / 2.0])

        p_left = p_tcp + R_tcp @ left_loc
        p_right = p_tcp + R_tcp @ right_loc

        p.resetBasePositionAndOrientation(
            self.left_jaw_body_id,
            p_left.tolist(),
            list(self.tcp_quat),
            physicsClientId=self.client_id,
        )
        p.resetBasePositionAndOrientation(
            self.right_jaw_body_id,
            p_right.tolist(),
            list(self.tcp_quat),
            physicsClientId=self.client_id,
        )

    def set_tcp_pose(
        self,
        pos_m: Sequence[float],
        quat: Sequence[float],
        timestamp: Optional[float] = None,
    ) -> None:
        """Update kinematic TCP pose, update collision proxies, and derive grasp center."""
        self.tcp_pos = np.asarray(pos_m, dtype=float)
        self.tcp_quat = np.asarray(quat, dtype=float)

        # Grasp center = TCP + R(tcp_quat) * tcp_to_grasp_center
        R_tcp = quat_to_rot_matrix(self.tcp_quat)
        self.grasp_pos = self.tcp_pos + R_tcp @ self.tcp_to_grasp_center
        self.grasp_quat = self.tcp_quat.copy()

        ts = float(timestamp) if timestamp is not None else time.time()
        self._history.append((ts, self.grasp_pos.copy()))
        self._update_proxy_poses()

        # If a piece is attached, deterministically update its pose
        if self.attached_piece is not None and self.T_gripper_piece is not None:
            T_gripper = np.eye(4, dtype=float)
            T_gripper[:3, :3] = quat_to_rot_matrix(self.grasp_quat)
            T_gripper[:3, 3] = self.grasp_pos

            T_piece = T_gripper @ self.T_gripper_piece
            piece_pos = T_piece[:3, 3]
            piece_quat = rot_matrix_to_quat(T_piece[:3, :3])

            self.attached_piece.set_pose_robot_base(piece_pos, piece_quat)
            # While attached, piece velocity matches gripper velocity
            lin_vel, _ = self.estimate_velocity()
            self.attached_piece.set_velocity(lin_vel, [0.0, 0.0, 0.0])

    def set_gripper_state(self, closed: bool) -> None:
        """Set gripper jaw open/closed state and update proxy bodies."""
        self.is_closed = bool(closed)
        self.jaw_width_m = self.closed_width_m if self.is_closed else self.open_width_m
        self._update_proxy_poses()

    def estimate_velocity(self) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate grasp center linear and angular velocity from recent history."""
        if len(self._history) < 2:
            return np.zeros(3, dtype=float), np.zeros(3, dtype=float)

        t_now, p_now = self._history[-1]
        for i in range(len(self._history) - 2, -1, -1):
            t_prev, p_prev = self._history[i]
            dt = t_now - t_prev
            if dt > 1e-6:
                lin_vel = (p_now - p_prev) / dt
                return lin_vel, np.zeros(3, dtype=float)

        return np.zeros(3, dtype=float), np.zeros(3, dtype=float)

    def evaluate_grasp_eligibility(
        self,
        pieces: Sequence[XiangqiPieceBody],
    ) -> GraspResult:
        """
        Evaluate deterministic geometric grasp criteria:
        1. Gripper must be closed.
        2. No piece already attached.
        3. Piece center must fall inside cylindrical capture volume around grasp_pos.
        4. Exactly one candidate must qualify (ambiguity rejection).
        """
        if not self.is_closed:
            return GraspResult(
                success=False,
                status=GraspStatus.INVALID_GRIPPER_STATE,
                reason="Gripper is not in closed state",
            )

        if self.attached_piece is not None:
            return GraspResult(
                success=False,
                status=GraspStatus.ALREADY_ATTACHED,
                piece_id=self.attached_piece.piece_id,
                reason=f"Piece {self.attached_piece.piece_id} already attached",
            )

        candidates = []
        for p in pieces:
            if p.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                continue

            pos_robot, _ = p.get_pose_robot_base()
            dx = pos_robot[0] - self.grasp_pos[0]
            dy = pos_robot[1] - self.grasp_pos[1]
            dz = pos_robot[2] - self.grasp_pos[2]

            r_xy = math.hypot(dx, dy)
            if r_xy <= self.capture_radius_xy and abs(dz) <= self.capture_half_height_z:
                dist_3d = math.sqrt(dx * dx + dy * dy + dz * dz)
                candidates.append((p, dist_3d))

        if len(candidates) == 0:
            return GraspResult(
                success=False,
                status=GraspStatus.NO_CANDIDATE,
                reason="No piece within gripper capture volume",
            )

        if len(candidates) > 1:
            return GraspResult(
                success=False,
                status=GraspStatus.AMBIGUOUS,
                reason=f"Multiple ambiguous candidates ({len(candidates)}) in capture volume",
            )

        piece, dist = candidates[0]
        return GraspResult(
            success=True,
            status=GraspStatus.SUCCESS,
            piece_id=piece.piece_id,
            distance_m=dist,
            reason=f"Single candidate {piece.piece_id} captured at {dist*1000:.1f}mm",
        )

    def attach_piece(self, piece: XiangqiPieceBody) -> bool:
        """
        Deterministically attach piece to gripper.
        Computes and stores the relative transform invariant:
            T_gripper_piece = inverse(T_gripper) * T_piece
        """
        self.attached_piece = piece
        piece.attached_to_gripper = True
        piece.physical_state = PiecePhysicalState.ATTACHED_TO_GRIPPER

        # Compute T_gripper
        T_gripper = np.eye(4, dtype=float)
        T_gripper[:3, :3] = quat_to_rot_matrix(self.grasp_quat)
        T_gripper[:3, 3] = self.grasp_pos

        # Compute T_piece
        pos_p, quat_p = piece.get_pose_robot_base()
        T_piece = np.eye(4, dtype=float)
        T_piece[:3, :3] = quat_to_rot_matrix(quat_p)
        T_piece[:3, 3] = pos_p

        # Invert T_gripper: [R^T, -R^T * p]
        R_inv = T_gripper[:3, :3].T
        p_inv = -R_inv @ T_gripper[:3, 3]
        T_gripper_inv = np.eye(4, dtype=float)
        T_gripper_inv[:3, :3] = R_inv
        T_gripper_inv[:3, 3] = p_inv

        self.T_gripper_piece = T_gripper_inv @ T_piece

        # Disable collision between attached piece and gripper collision proxies
        if self.client_id >= 0:
            for gb in self.proxy_body_ids:
                p.setCollisionFilterPair(
                    piece.body_id,
                    gb,
                    -1,
                    -1,
                    enableCollision=0,
                    physicsClientId=self.client_id,
                )
        return True

    def detach_piece(self) -> Optional[XiangqiPieceBody]:
        """
        Detach piece from gripper and inherit current motion velocity.
        Returns the released piece or None.
        """
        if self.attached_piece is None:
            return None

        piece = self.attached_piece
        self.attached_piece = None
        self.T_gripper_piece = None

        piece.attached_to_gripper = False
        piece.physical_state = PiecePhysicalState.FALLING

        # Re-enable collision between piece and gripper collision proxies
        if self.client_id >= 0:
            for gb in self.proxy_body_ids:
                p.setCollisionFilterPair(
                    piece.body_id,
                    gb,
                    -1,
                    -1,
                    enableCollision=1,
                    physicsClientId=self.client_id,
                )

        # Inherit velocity
        lin_vel, ang_vel = self.estimate_velocity()
        piece.set_velocity(lin_vel, ang_vel)

        return piece

    def to_state_dict(self) -> Dict[str, Any]:
        """Telemetry state dictionary."""
        return {
            "closed": self.is_closed,
            "is_closed": self.is_closed,
            "jaw_width_m": round(self.jaw_width_m, 4),
            "attached_piece_id": self.attached_piece.piece_id if self.attached_piece else None,
            "tcp_position_m": [round(float(v), 5) for v in self.tcp_pos],
            "grasp_position_m": [round(float(v), 5) for v in self.grasp_pos],
        }
