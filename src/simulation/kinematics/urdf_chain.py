"""
URDF kinematic chain implementation with homogeneous transforms and geometric Jacobian.

Conforms to standard URDF transformation definitions:
- Joint origin: translation (xyz) followed by extrinsic Euler rotation (rpy = roll, pitch, yaw)
  R_origin = R_z(yaw) @ R_y(pitch) @ R_x(roll)
- Joint rotation: revolute rotation about specified joint axis (axis_xyz) by angle q
- Forward Kinematics:
  T_parent_child(q) = Trans(xyz) @ Rot(rpy) @ Rot(axis, q)
- Geometric Jacobian:
  J_v,i = z_i x (p_e - p_i)
  J_w,i = z_i
"""

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


def rpy_to_matrix(rpy: Sequence[float]) -> np.ndarray:
    """
    Convert extrinsic roll-pitch-yaw (r, p, y) in radians to 3x3 rotation matrix.
    R = R_z(yaw) @ R_y(pitch) @ R_x(roll)
    """
    r, p, y = float(rpy[0]), float(rpy[1]), float(rpy[2])
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)

    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]], dtype=float)
    Ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]], dtype=float)
    Rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=float)

    return Rz @ Ry @ Rx


def matrix_to_rpy(R: np.ndarray) -> np.ndarray:
    """
    Extract extrinsic roll-pitch-yaw [roll, pitch, yaw] from 3x3 rotation matrix.
    R = R_z(yaw) @ R_y(pitch) @ R_x(roll)
    """
    # Clamp R[2, 0] for asin numerical stability
    sin_p = -float(np.clip(R[2, 0], -1.0, 1.0))
    pitch = math.asin(sin_p)

    cos_p = math.cos(pitch)
    if abs(cos_p) > 1e-6:
        roll = math.atan2(float(R[2, 1]), float(R[2, 2]))
        yaw = math.atan2(float(R[1, 0]), float(R[0, 0]))
    else:
        # Gimbal lock: pitch is near +/- 90 degrees
        roll = 0.0
        yaw = math.atan2(-float(R[0, 1]), float(R[1, 1]))

    return np.array([roll, pitch, yaw], dtype=float)


def axis_angle_to_matrix(axis: Sequence[float], angle_rad: float) -> np.ndarray:
    """
    Convert unit axis and angle to 3x3 rotation matrix using Rodrigues formula.
    """
    ax = np.array(axis, dtype=float)
    norm = np.linalg.norm(ax)
    if norm < 1e-9:
        return np.eye(3, dtype=float)
    u = ax / norm
    q = float(angle_rad)
    cq = math.cos(q)
    sq = math.sin(q)
    K = np.array([
        [0.0, -u[2], u[1]],
        [u[2], 0.0, -u[0]],
        [-u[1], u[0], 0.0]
    ], dtype=float)
    return cq * np.eye(3, dtype=float) + sq * K + (1.0 - cq) * np.outer(u, u)


@dataclass(frozen=True)
class Pose3D:
    """
    Authoritative 3D pose representation: translation (meters) and 3x3 rotation matrix.
    """
    translation_m: np.ndarray  # shape (3,)
    rotation_matrix: np.ndarray  # shape (3, 3)

    def __post_init__(self):
        # Validate shapes and finitude
        trans = np.asarray(self.translation_m, dtype=float)
        rot = np.asarray(self.rotation_matrix, dtype=float)
        if trans.shape != (3,):
            raise ValueError(f"translation_m must have shape (3,), got {trans.shape}")
        if rot.shape != (3, 3):
            raise ValueError(f"rotation_matrix must have shape (3, 3), got {rot.shape}")
        if not np.all(np.isfinite(trans)):
            raise ValueError(f"translation_m contains non-finite values: {trans}")
        if not np.all(np.isfinite(rot)):
            raise ValueError(f"rotation_matrix contains non-finite values: {rot}")
        object.__setattr__(self, "translation_m", trans)
        object.__setattr__(self, "rotation_matrix", rot)

    @classmethod
    def from_matrix(cls, T: np.ndarray) -> "Pose3D":
        """Create Pose3D from 4x4 homogeneous transformation matrix."""
        mat = np.asarray(T, dtype=float)
        if mat.shape != (4, 4):
            raise ValueError(f"Expected 4x4 transform, got {mat.shape}")
        return cls(translation_m=mat[:3, 3], rotation_matrix=mat[:3, :3])

    @classmethod
    def from_xyz_rpy(cls, xyz: Sequence[float], rpy: Sequence[float]) -> "Pose3D":
        """Create Pose3D from xyz (meters) and rpy (radians)."""
        rot = rpy_to_matrix(rpy)
        return cls(translation_m=np.array(xyz, dtype=float), rotation_matrix=rot)

    @classmethod
    def identity(cls) -> "Pose3D":
        """Return identity pose at origin."""
        return cls(translation_m=np.zeros(3, dtype=float), rotation_matrix=np.eye(3, dtype=float))

    def as_matrix(self) -> np.ndarray:
        """Return 4x4 homogeneous transformation matrix."""
        T = np.eye(4, dtype=float)
        T[:3, :3] = self.rotation_matrix
        T[:3, 3] = self.translation_m
        return T

    def to_xyz_rpy_deg(self) -> List[float]:
        """
        Convert to [X_mm, Y_mm, Z_mm, Rx_deg, Ry_deg, Rz_deg] for compatibility/telemetry boundaries.
        Euler convention: Extrinsic R = Rz(Rz) @ Ry(Ry) @ Rx(Rx).
        """
        rpy_rad = matrix_to_rpy(self.rotation_matrix)
        x_mm = round(float(self.translation_m[0]) * 1000.0, 3)
        y_mm = round(float(self.translation_m[1]) * 1000.0, 3)
        z_mm = round(float(self.translation_m[2]) * 1000.0, 3)
        rx_deg = round(math.degrees(float(rpy_rad[0])), 3)
        ry_deg = round(math.degrees(float(rpy_rad[1])), 3)
        rz_deg = round(math.degrees(float(rpy_rad[2])), 3)
        return [x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg]

    def transform_pose(self, other: "Pose3D") -> "Pose3D":
        """Compose transforms: self @ other."""
        T = self.as_matrix() @ other.as_matrix()
        return Pose3D.from_matrix(T)


@dataclass(frozen=True)
class URDFJoint:
    """Specification of a single URDF joint."""
    name: str
    parent: str
    child: str
    type: str
    origin_xyz: np.ndarray  # shape (3,)
    origin_rpy: np.ndarray  # shape (3,)
    axis: np.ndarray  # shape (3,)
    lower_limit: float
    upper_limit: float
    velocity_limit: float

    def local_transform(self, q: float) -> np.ndarray:
        """
        Compute 4x4 transform T_parent_child(q) = T_origin @ T_joint(q).
        """
        R_orig = rpy_to_matrix(self.origin_rpy)
        R_joint = axis_angle_to_matrix(self.axis, q)
        R = R_orig @ R_joint

        T = np.eye(4, dtype=float)
        T[:3, :3] = R
        T[:3, 3] = self.origin_xyz
        return T


class URDFKinematicChain:
    """
    Kinematic chain of sequential revolute joints derived from URDF.
    """
    def __init__(
        self,
        joints: Sequence[URDFJoint],
        base_link: str = "base_link",
        flange_link: str = "wrist3_link",
    ):
        self.joints = list(joints)
        self.base_link = base_link
        self.flange_link = flange_link
        self.num_joints = len(self.joints)

        # Precompute origin transforms
        self._origin_transforms = []
        for j in self.joints:
            T_orig = np.eye(4, dtype=float)
            T_orig[:3, :3] = rpy_to_matrix(j.origin_rpy)
            T_orig[:3, 3] = j.origin_xyz
            self._origin_transforms.append(T_orig)

        # Cache joint limits
        self.lower_limits = np.array([j.lower_limit for j in self.joints], dtype=float)
        self.upper_limits = np.array([j.upper_limit for j in self.joints], dtype=float)
        self.velocity_limits = np.array([j.velocity_limit for j in self.joints], dtype=float)

    @classmethod
    def from_profile_dict(cls, data: dict) -> "URDFKinematicChain":
        """Instantiate kinematic chain from robot profile dict."""
        joints = []
        for j_data in data.get("joints", []):
            joint = URDFJoint(
                name=j_data["name"],
                parent=j_data["parent"],
                child=j_data["child"],
                type=j_data.get("type", "revolute"),
                origin_xyz=np.array(j_data["origin_xyz_m"], dtype=float),
                origin_rpy=np.array(j_data["origin_rpy_rad"], dtype=float),
                axis=np.array(j_data["axis"], dtype=float),
                lower_limit=float(j_data["lower_rad"]),
                upper_limit=float(j_data["upper_rad"]),
                velocity_limit=float(j_data.get("velocity_rad_s", 3.14)),
            )
            joints.append(joint)

        return cls(
            joints=joints,
            base_link=data.get("base_link", "base_link"),
            flange_link=data.get("flange_link", "wrist3_link"),
        )

    def forward_kinematics_chain(self, joints_rad: Sequence[float]) -> List[np.ndarray]:
        """
        Compute cumulative 4x4 transformation matrices from base to each child frame.
        Returns list of N matrices: [T_0_1, T_0_2, ..., T_0_N].
        """
        if len(joints_rad) != self.num_joints:
            raise ValueError(f"Expected {self.num_joints} joint angles, got {len(joints_rad)}")

        chain_transforms = []
        T_current = np.eye(4, dtype=float)
        for i, joint in enumerate(self.joints):
            T_i = joint.local_transform(joints_rad[i])
            T_current = T_current @ T_i
            chain_transforms.append(T_current.copy())

        return chain_transforms

    def forward_kinematics(self, joints_rad: Sequence[float]) -> Pose3D:
        """
        Compute forward kinematics from base to flange.
        Returns Pose3D of the flange frame in base frame.
        """
        chain = self.forward_kinematics_chain(joints_rad)
        return Pose3D.from_matrix(chain[-1])

    def geometric_jacobian(
        self,
        joints_rad: Sequence[float],
        chain_transforms: Optional[List[np.ndarray]] = None,
        target_point: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Compute 6xN geometric Jacobian in the base frame.
        J = [ J_v ]
            [ J_w ]
        where for revolute joint i:
        J_v,i = z_i x (p_e - p_i)
        J_w,i = z_i
        """
        if chain_transforms is None:
            chain_transforms = self.forward_kinematics_chain(joints_rad)

        p_e = target_point if target_point is not None else chain_transforms[-1][:3, 3]

        J = np.zeros((6, self.num_joints), dtype=float)
        T_prev = np.eye(4, dtype=float)

        for i in range(self.num_joints):
            # Joint origin frame in base coordinates: T_prev @ T_orig_i
            T_joint_origin = T_prev @ self._origin_transforms[i]

            # Rotation axis in base coordinates: R_joint_origin @ joint_axis
            z_i = T_joint_origin[:3, :3] @ self.joints[i].axis
            p_i = T_joint_origin[:3, 3]

            J[:3, i] = np.cross(z_i, p_e - p_i)
            J[3:, i] = z_i

            T_prev = chain_transforms[i]

        return J

    def check_joint_limits(self, joints_rad: Sequence[float]) -> Tuple[bool, List[float]]:
        """
        Check if joints are within [lower, upper] limits.
        Returns (is_valid, margins) where margin = min(q - lower, upper - q).
        """
        q = np.asarray(joints_rad, dtype=float)
        margins = []
        valid = True
        for i in range(self.num_joints):
            m_lower = float(q[i] - self.lower_limits[i])
            m_upper = float(self.upper_limits[i] - q[i])
            margin = min(m_lower, m_upper)
            margins.append(margin)
            if margin < 0.0:
                valid = False
        return valid, margins
