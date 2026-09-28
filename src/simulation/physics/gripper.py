"""
Virtual kinematic gripper proxy and deterministic grasp / attachment manager.
"""

from collections import deque
import hashlib
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
    # CAD-derived virtual jaw clearance tolerance for deterministic grasp verification.
    # The closed CAD jaws enclose the 22.5 mm piece with gaps of ~2.17 mm (left) and ~6.61 mm (right)
    # due to CAD jaw stroke and tip taper. 8.0 mm (0.008 m) bounds both closed jaws while rejecting
    # off-target pieces (> 8.0 mm) and penetrations (< -0.1 mm).
    MAX_JAW_CONTACT_GAP_M = 0.008

    def __init__(
        self,
        profile_path: Optional[Union[str, Path]] = None,
    ):
        if profile_path is None:
            profile_path = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "virtual_gripper_profile.json"

        profile_path = Path(profile_path)
        if not profile_path.is_file():
            raise FileNotFoundError(f"Gripper profile not found at {profile_path}")

        gripper_profile_bytes = profile_path.read_bytes()
        self.profile = json.loads(gripper_profile_bytes.decode("utf-8-sig"))

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

        # The collision envelope is generated from the exact STEP used by the
        # viewer. A changed mesh or mounting transform must regenerate it.
        root = Path(__file__).resolve().parents[3]
        collision_asset = json.loads(
            (root / "shared" / "gripper_collision_asset.json").read_text(encoding="utf-8")
        )
        visual_bytes = (root / "shared" / "gripper_visual_asset.json").read_bytes()
        profile_bytes = (root / "shared" / "robot_profiles" / "fr3.json").read_bytes()
        visual = json.loads(visual_bytes)
        step_bytes = (root / "robot-3d-viewer" / "assets" / "fr3_v6" / visual["asset_file"]).read_bytes()
        if (collision_asset.get("schema_version") != 2 or
                hashlib.sha256(visual_bytes).hexdigest() != collision_asset.get("source_visual_sha256") or
                hashlib.sha256(profile_bytes).hexdigest() != collision_asset.get("source_profile_sha256") or
                hashlib.sha256(gripper_profile_bytes).hexdigest() != collision_asset.get("source_gripper_profile_sha256") or
                hashlib.sha256(step_bytes).hexdigest() != collision_asset.get("source_step_sha256")):
            raise ValueError("Gripper STEP/profile/visual changed; regenerate CAD-derived collision envelope")
        self.collision_asset = collision_asset
        fingers = collision_asset["finger_boxes"]
        cad_open_gap = (fingers[1]["center_m"][0] - fingers[1]["half_extents_m"][0]
                        - fingers[0]["center_m"][0] - fingers[0]["half_extents_m"][0])
        cad_closed_gap = cad_open_gap - 2.0 * collision_asset["finger_travel_m"]
        if abs(self.open_width_m - cad_open_gap) > 1e-5 or abs(self.closed_width_m - cad_closed_gap) > 1e-5:
            raise ValueError("Gripper stroke differs from CAD-derived open/closed jaw gap")

        # PyBullet body IDs (managed by VirtualPhysicalWorld)
        self.client_id: int = -1
        self.palm_body_id: int = -1
        self.fixed_body_ids: List[int] = []
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
        return [b for b in (*self.fixed_body_ids, self.left_jaw_body_id, self.right_jaw_body_id) if b >= 0]

    def spawn_proxies(self, client_id: int) -> None:
        """
        Spawn CAD-derived conservative component boxes. Every rendered STEP
        triangle is inside one of these boxes, including the visual adapter.
        """
        self.client_id = client_id
        fixed = self.collision_asset["fixed_boxes"]
        # PyBullet silently truncates compound collision arrays above 16
        # children. Keep each chunk smaller and verify every child exists.
        self.fixed_body_ids = []
        for offset in range(0, len(fixed), 12):
            chunk = fixed[offset:offset + 12]
            shape = p.createCollisionShapeArray(
                shapeTypes=[p.GEOM_BOX] * len(chunk),
                halfExtents=[box["half_extents_m"] for box in chunk],
                collisionFramePositions=[box["center_m"] for box in chunk],
                physicsClientId=client_id,
            )
            body = p.createMultiBody(
                baseMass=0.0, baseCollisionShapeIndex=shape,
                basePosition=[0.0, 0.0, -10.0], physicsClientId=client_id,
            )
            actual = len(p.getCollisionShapeData(body, -1, physicsClientId=client_id))
            if actual != len(chunk):
                raise RuntimeError(f"PyBullet omitted fixed gripper geometry: {actual}/{len(chunk)}")
            self.fixed_body_ids.append(body)
        self.palm_body_id = self.fixed_body_ids[0]

        finger_boxes = self.collision_asset["finger_boxes"]
        col_left = p.createCollisionShape(
            p.GEOM_MESH, vertices=finger_boxes[0]["vertices_m"], physicsClientId=client_id,
        )
        col_right = p.createCollisionShape(
            p.GEOM_MESH, vertices=finger_boxes[1]["vertices_m"], physicsClientId=client_id,
        )
        self.left_jaw_body_id = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=col_left,
            basePosition=[0.0, 0.0, -10.0],
            physicsClientId=client_id,
        )
        self.right_jaw_body_id = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=col_right,
            basePosition=[0.0, 0.0, -10.0],
            physicsClientId=client_id,
        )
        self._update_proxy_poses()

    def remove_proxies(self) -> None:
        """Safely remove proxy bodies from PyBullet."""
        if self.client_id >= 0:
            for b in self.proxy_body_ids:
                if b >= 0:
                    try:
                        p.removeBody(b, physicsClientId=self.client_id)
                    except Exception:
                        pass
        self.palm_body_id = -1
        self.fixed_body_ids = []
        self.left_jaw_body_id = -1
        self.right_jaw_body_id = -1

    def set_collision_proxy_pose(
        self,
        pos_m: Sequence[float],
        quat: Sequence[float],
        jaw_width: Optional[float] = None,
    ) -> None:
        """
        Side-effect-free update of kinematic PyBullet proxy bodies for collision checking only.
        Does NOT update runtime tcp_pos/quat, grasp_pos/quat, _history, velocity, or attached piece!
        """
        if self.client_id < 0 or self.palm_body_id < 0:
            return

        p_tcp = np.asarray(pos_m, dtype=float)
        q_tcp = np.asarray(quat, dtype=float)
        R_tcp = quat_to_rot_matrix(q_tcp)

        w = float(jaw_width) if jaw_width is not None else float(self.jaw_width_m)
        travel_fraction = np.clip(
            (self.open_width_m - w) / (self.open_width_m - self.closed_width_m), 0.0, 1.0
        )
        finger_shift = float(travel_fraction * self.collision_asset["finger_travel_m"])
        for body in self.fixed_body_ids:
            p.resetBasePositionAndOrientation(
                body, p_tcp.tolist(), list(q_tcp), physicsClientId=self.client_id,
            )
        p_left = p_tcp + R_tcp @ np.array([finger_shift, 0.0, 0.0])
        p_right = p_tcp + R_tcp @ np.array([-finger_shift, 0.0, 0.0])

        p.resetBasePositionAndOrientation(
            self.left_jaw_body_id,
            p_left.tolist(),
            list(q_tcp),
            physicsClientId=self.client_id,
        )
        p.resetBasePositionAndOrientation(
            self.right_jaw_body_id,
            p_right.tolist(),
            list(q_tcp),
            physicsClientId=self.client_id,
        )

    def _update_proxy_poses(self) -> None:
        """Synchronize kinematic PyBullet proxy bodies to current TCP pose and jaw width."""
        if np.allclose(self.tcp_pos, 0.0) and not np.allclose(self.grasp_pos, 0.0):
            R_tcp = quat_to_rot_matrix(self.grasp_quat)
            self.tcp_pos = self.grasp_pos - R_tcp @ self.tcp_to_grasp_center
            self.tcp_quat = self.grasp_quat.copy()
        self.set_collision_proxy_pose(self.tcp_pos, self.tcp_quat, self.jaw_width_m)

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

    def _jaw_gap_to_piece_m(self, jaw_id: int, piece: XiangqiPieceBody) -> Optional[float]:
        """Read the separation of a CAD jaw hull from a piece in PyBullet."""
        points = p.getClosestPoints(
            jaw_id, piece.body_id, distance=0.05, physicsClientId=self.client_id,
        )
        return min(float(point[8]) for point in points) if points else None

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
        5. Both CAD jaw hulls must touch that piece within numerical tolerance.
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
        for candidate in pieces:
            if candidate.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                continue

            pos_robot, _ = candidate.get_pose_robot_base()
            dx = pos_robot[0] - self.grasp_pos[0]
            dy = pos_robot[1] - self.grasp_pos[1]
            dz = pos_robot[2] - self.grasp_pos[2]

            r_xy = math.hypot(dx, dy)
            if r_xy <= self.capture_radius_xy and abs(dz) <= self.capture_half_height_z:
                dist_3d = math.sqrt(dx * dx + dy * dy + dz * dz)
                candidates.append((candidate, dist_3d))

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
        if self.client_id < 0 or self.left_jaw_body_id < 0 or self.right_jaw_body_id < 0:
            return GraspResult(
                success=False, status=GraspStatus.NO_JAW_CONTACT, piece_id=piece.piece_id,
                reason="CAD jaw collision bodies are unavailable; grasp cannot be verified",
            )
        jaw_gaps_m = [self._jaw_gap_to_piece_m(jaw_id, piece) for jaw_id in
                      (self.left_jaw_body_id, self.right_jaw_body_id)]
        if any(gap is None or gap > self.MAX_JAW_CONTACT_GAP_M for gap in jaw_gaps_m):
            gap_text = [None if gap is None else round(gap * 1000, 3) for gap in jaw_gaps_m]
            return GraspResult(
                success=False, status=GraspStatus.NO_JAW_CONTACT, piece_id=piece.piece_id,
                reason=f"Closed CAD jaws do not both contact {piece.piece_id}; gaps={gap_text}mm",
            )
        if any(gap < -0.0001 for gap in jaw_gaps_m):
            return GraspResult(
                success=False, status=GraspStatus.NO_JAW_CONTACT, piece_id=piece.piece_id,
                reason="A CAD jaw penetrates the selected piece instead of gripping it",
            )
        return GraspResult(
            success=True,
            status=GraspStatus.SUCCESS,
            piece_id=piece.piece_id,
            distance_m=dist,
            reason=(f"Both CAD jaws contact {piece.piece_id}; center offset={dist*1000:.1f}mm, "
                    f"jaw gaps={[round(gap*1000, 3) for gap in jaw_gaps_m]}mm"),
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
