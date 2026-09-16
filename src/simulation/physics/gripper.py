"""
Virtual kinematic gripper proxy and deterministic grasp / attachment manager.
"""

from collections import deque
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.state import GraspResult, GraspStatus, PiecePhysicalState
from src.simulation.physics.transforms import (
    quat_to_rot_matrix,
    rot_matrix_to_quat,
)


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

        with open(profile_path, "r", encoding="utf-8-sig") as f:
            self.profile = json.load(f)

        self.model = self.profile.get("gripper_model", "PROCEDURAL_2JAW_V1")
        self.tcp_to_grasp_center = np.array(
            self.profile.get("tcp_to_grasp_center_m", [0.0, 0.0, 0.035]),
            dtype=float,
        )
        cap = self.profile.get("capture_volume", {})
        self.capture_radius_xy = float(cap.get("xy_radius_m", 0.016))
        self.capture_half_height_z = float(cap.get("z_half_height_m", 0.012))

        stroke = self.profile.get("stroke", {})
        self.open_width_m = float(stroke.get("open_width_m", 0.040))
        self.closed_width_m = float(stroke.get("closed_width_m", 0.020))

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

    def set_tcp_pose(
        self,
        pos_m: Sequence[float],
        quat: Sequence[float],
        timestamp: float,
    ) -> None:
        """Update kinematic TCP pose and derive grasp center."""
        self.tcp_pos = np.asarray(pos_m, dtype=float)
        self.tcp_quat = np.asarray(quat, dtype=float)

        # Grasp center = TCP + R(tcp_quat) * tcp_to_grasp_center
        R_tcp = quat_to_rot_matrix(self.tcp_quat)
        self.grasp_pos = self.tcp_pos + R_tcp @ self.tcp_to_grasp_center
        self.grasp_quat = self.tcp_quat.copy()

        self._history.append((float(timestamp), self.grasp_pos.copy()))

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
        """Set gripper jaw open/closed state."""
        self.is_closed = bool(closed)
        self.jaw_width_m = self.closed_width_m if self.is_closed else self.open_width_m

    def estimate_velocity(self) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate grasp center linear and angular velocity from recent history."""
        if len(self._history) < 2:
            return np.zeros(3, dtype=float), np.zeros(3, dtype=float)

        t_now, p_now = self._history[-1]
        t_prev, p_prev = self._history[-2]
        dt = t_now - t_prev
        if dt <= 1e-6:
            return np.zeros(3, dtype=float), np.zeros(3, dtype=float)

        lin_vel = (p_now - p_prev) / dt
        ang_vel = np.zeros(3, dtype=float)
        return lin_vel, ang_vel

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

        # Inherit velocity
        lin_vel, ang_vel = self.estimate_velocity()
        piece.set_velocity(lin_vel, ang_vel)

        return piece

    def to_state_dict(self) -> Dict[str, Any]:
        """Telemetry state dictionary."""
        return {
            "is_closed": self.is_closed,
            "jaw_width_m": round(self.jaw_width_m, 4),
            "attached_piece_id": self.attached_piece.piece_id if self.attached_piece else None,
            "tcp_position_m": [round(float(v), 5) for v in self.tcp_pos],
            "grasp_position_m": [round(float(v), 5) for v in self.grasp_pos],
        }
