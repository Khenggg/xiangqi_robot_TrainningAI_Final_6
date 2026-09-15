"""
Authoritative FR3 Kinematics Engine.

Derived from canonical URDF: robot-3d-viewer/assets/fr3_v6/fairino3_v6.urdf
Profile: shared/robot_profiles/fr3.json

Implements:
- Forward Kinematics (FK) using exact URDF transformation chain
- Full 6-DOF Numerical Inverse Kinematics (IK) via Damped Least Squares (DLS)
  with exact geometric Jacobian and joint limit enforcement
- Multi-seed restart capability for high convergence reliability
- Structured IKResult with typed IKStatus (SUCCESS, UNREACHABLE, JOINT_LIMIT, etc.)
- Manipulability and condition number metrics for singularity avoidance
"""

from dataclasses import dataclass
from enum import Enum
import json
import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union
import numpy as np

from src.simulation.kinematics.urdf_chain import (
    Pose3D,
    URDFKinematicChain,
    matrix_to_rpy,
    rpy_to_matrix,
)


class IKStatus(str, Enum):
    """Structured IK completion status."""
    SUCCESS = "SUCCESS"
    UNREACHABLE = "UNREACHABLE"
    JOINT_LIMIT = "JOINT_LIMIT"
    NON_CONVERGED = "NON_CONVERGED"
    INVALID_TARGET = "INVALID_TARGET"
    SINGULARITY = "SINGULARITY"


@dataclass(frozen=True)
class IKResult:
    """Detailed result of an inverse kinematics query."""
    status: IKStatus
    success: bool
    joints_rad: Optional[np.ndarray]
    joints_deg: Optional[List[float]]
    position_error_mm: float
    orientation_error_deg: float
    iterations: int
    condition_number: float
    failure_reason: Optional[str] = None

    def __repr__(self) -> str:
        if self.success:
            return (
                f"<IKResult {self.status.value}: pos_err={self.position_error_mm:.3f}mm, "
                f"rot_err={self.orientation_error_deg:.2f}deg in {self.iterations} iters>"
            )
        return f"<IKResult {self.status.value}: reason={self.failure_reason}>"


def _rotation_error_vector(R_target: np.ndarray, R_current: np.ndarray) -> np.ndarray:
    """
    Compute 3D axis-angle rotation error vector e_o such that R_target ≈ exp([e_o]x) @ R_current.
    """
    R_err = R_target @ R_current.T
    tr = float(np.trace(R_err))
    cos_theta = float(np.clip((tr - 1.0) / 2.0, -1.0, 1.0))
    theta = math.acos(cos_theta)
    if theta < 1e-7:
        return np.zeros(3, dtype=float)
    vec = np.array([
        R_err[2, 1] - R_err[1, 2],
        R_err[0, 2] - R_err[2, 0],
        R_err[1, 0] - R_err[0, 1]
    ], dtype=float)
    return 0.5 * (theta / math.sin(theta)) * vec


class FR3Kinematics:
    """
    Authoritative FR3 Kinematics Engine implementing FK, DLS numerical IK,
    Jacobian computation, and workspace validation.
    """

    # Approximate max physical reach from base origin (shoulder to flange full extension)
    # d1=0.14m, a2=0.28m, a3=0.24m, d4+d6=0.204m -> max span ~ 0.63m
    MAX_REACH_RADIUS_M = 0.65

    def __init__(self, profile_path: Optional[Union[str, Path]] = None):
        if profile_path is None:
            # Default to shared/robot_profiles/fr3.json
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            resolved_path = repo_root / "shared" / "robot_profiles" / "fr3.json"
        else:
            resolved_path = Path(profile_path)

        if not resolved_path.is_file():
            raise FileNotFoundError(f"FR3 profile JSON not found at {resolved_path}")

        with open(resolved_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.chain = URDFKinematicChain.from_profile_dict(data)
        self.profile = data
        self.lower_limits = self.chain.lower_limits
        self.upper_limits = self.chain.upper_limits

        # Predefined reference seed configurations (radians)
        self.reference_seeds = [
            np.array([0.0, -0.785, 1.571, -0.785, -1.571, 0.0], dtype=float),   # Standard elbow up
            np.array([0.0, -1.2, 1.8, -2.1, -1.571, 0.0], dtype=float),          # Folded reach
            np.array([0.0, -0.5, 1.2, -1.4, 1.571, 0.0], dtype=float),           # Downward wrist flip
            np.zeros(6, dtype=float),                                             # Zero pose
        ]

    def forward_kinematics(self, joints_rad: Sequence[float]) -> Pose3D:
        """
        Compute forward kinematics from base to flange.
        Input: 6 joint angles in radians.
        Output: Pose3D (translation in meters, 3x3 rotation matrix).
        """
        q = np.asarray(joints_rad, dtype=float)
        if len(q) != 6:
            raise ValueError(f"FR3 requires 6 joint angles, got {len(q)}")
        if not np.all(np.isfinite(q)):
            raise ValueError(f"Joint angles contain non-finite values: {q}")
        return self.chain.forward_kinematics(q)

    def forward_kinematics_deg(self, joints_deg: Sequence[float]) -> List[float]:
        """
        Compute forward kinematics with inputs in degrees and outputs in mm/degrees.
        Returns: [X_mm, Y_mm, Z_mm, Rx_deg, Ry_deg, Rz_deg].
        """
        q_rad = [math.radians(float(d)) for d in joints_deg]
        pose = self.forward_kinematics(q_rad)
        return pose.to_xyz_rpy_deg()

    def geometric_jacobian(self, joints_rad: Sequence[float]) -> np.ndarray:
        """Compute 6x6 geometric Jacobian at specified joint angles."""
        return self.chain.geometric_jacobian(joints_rad)

    def compute_condition_number(self, J: np.ndarray) -> float:
        """Compute condition number of Jacobian (sigma_max / sigma_min)."""
        try:
            s = np.linalg.svd(J, compute_uv=False)
            if s[-1] < 1e-9:
                return float("inf")
            return float(s[0] / s[-1])
        except Exception:
            return float("inf")

    def compute_manipulability(self, J: np.ndarray) -> float:
        """Compute Yoshikawa manipulability index: sqrt(det(J @ J^T))."""
        try:
            JJT = J @ J.T
            det = np.linalg.det(JJT)
            return float(math.sqrt(max(0.0, det)))
        except Exception:
            return 0.0

    def inverse_kinematics(
        self,
        target: Union[Pose3D, np.ndarray, Sequence[float]],
        seed_joints: Optional[Sequence[float]] = None,
        max_iterations: int = 150,
        pos_tol_mm: float = 1.0,
        rot_tol_deg: float = 1.0,
        damping: float = 0.02,
        allow_multi_seed: bool = True,
    ) -> IKResult:
        """
        Solve full 6-DOF Inverse Kinematics using Damped Least Squares (DLS).
        
        Args:
            target: Pose3D, 4x4 matrix, or [X_mm, Y_mm, Z_mm, Rx_deg, Ry_deg, Rz_deg].
            seed_joints: Initial joint configuration in radians (optional).
            max_iterations: Maximum solver iterations per seed.
            pos_tol_mm: Position tolerance threshold in mm (default: 1.0 mm).
            rot_tol_deg: Orientation tolerance threshold in degrees (default: 1.0 deg).
            damping: Levenberg-Marquardt damping factor lambda.
            allow_multi_seed: Try alternate reference seeds if primary seed fails.
            
        Returns:
            IKResult with success boolean, status enum, solved joints, and errors.
        """
        # Parse target into Pose3D
        try:
            if isinstance(target, Pose3D):
                target_pose = target
            elif isinstance(target, np.ndarray) and target.shape == (4, 4):
                target_pose = Pose3D.from_matrix(target)
            elif isinstance(target, (list, tuple, np.ndarray)) and len(target) == 6:
                # Format: [X_mm, Y_mm, Z_mm, Rx_deg, Ry_deg, Rz_deg]
                vals = [float(v) for v in target]
                if not all(math.isfinite(v) for v in vals):
                    raise ValueError("Target contains non-finite values")
                xyz_m = [vals[0] / 1000.0, vals[1] / 1000.0, vals[2] / 1000.0]
                rpy_rad = [math.radians(vals[3]), math.radians(vals[4]), math.radians(vals[5])]
                target_pose = Pose3D.from_xyz_rpy(xyz_m, rpy_rad)
            else:
                return IKResult(
                    status=IKStatus.INVALID_TARGET,
                    success=False,
                    joints_rad=None,
                    joints_deg=None,
                    position_error_mm=float("inf"),
                    orientation_error_deg=float("inf"),
                    iterations=0,
                    condition_number=float("inf"),
                    failure_reason=f"Unsupported target format: {type(target)}",
                )
        except (ValueError, TypeError) as err:
            return IKResult(
                status=IKStatus.INVALID_TARGET,
                success=False,
                joints_rad=None,
                joints_deg=None,
                position_error_mm=float("inf"),
                orientation_error_deg=float("inf"),
                iterations=0,
                condition_number=float("inf"),
                failure_reason=f"Invalid target: {err}",
            )

        # Validate target finitude
        p_target = target_pose.translation_m
        R_target = target_pose.rotation_matrix
        if not (np.all(np.isfinite(p_target)) and np.all(np.isfinite(R_target))):
            return IKResult(
                status=IKStatus.INVALID_TARGET,
                success=False,
                joints_rad=None,
                joints_deg=None,
                position_error_mm=float("inf"),
                orientation_error_deg=float("inf"),
                iterations=0,
                condition_number=float("inf"),
                failure_reason="Target contains non-finite coordinates or rotation elements",
            )

        # Pre-check reachability distance from base origin
        dist_from_base = float(np.linalg.norm(p_target))
        if dist_from_base > self.MAX_REACH_RADIUS_M:
            return IKResult(
                status=IKStatus.UNREACHABLE,
                success=False,
                joints_rad=None,
                joints_deg=None,
                position_error_mm=(dist_from_base - self.MAX_REACH_RADIUS_M) * 1000.0,
                orientation_error_deg=180.0,
                iterations=0,
                condition_number=float("inf"),
                failure_reason=f"Target distance {dist_from_base*1000.0:.1f}mm exceeds max FR3 reach {self.MAX_REACH_RADIUS_M*1000.0:.1f}mm",
            )

        # Assemble list of candidate seeds to attempt
        seeds = []
        if seed_joints is not None:
            s_arr = np.asarray(seed_joints, dtype=float)
            if len(s_arr) == 6 and np.all(np.isfinite(s_arr)):
                seeds.append(s_arr)

        if allow_multi_seed or not seeds:
            # Base yaw seed aligned with target azimuth in XY
            yaw_base = math.atan2(float(p_target[1]), float(p_target[0]))
            for ref_s in self.reference_seeds:
                s_cand = ref_s.copy()
                s_cand[0] = yaw_base
                # Also try reverse yaw for alternate arm pose
                s_cand_rev = ref_s.copy()
                s_cand_rev[0] = (yaw_base + math.pi) % (2.0 * math.pi) - math.pi
                seeds.append(s_cand)
                seeds.append(s_cand_rev)

        pos_tol_m = pos_tol_mm / 1000.0
        rot_tol_rad = math.radians(rot_tol_deg)

        best_q = None
        best_pos_err = float("inf")
        best_rot_err = float("inf")
        best_cond = float("inf")
        total_iters = 0

        for seed in seeds:
            q = np.clip(seed, self.lower_limits, self.upper_limits)
            for it in range(max_iterations):
                total_iters += 1
                chain_transforms = self.chain.forward_kinematics_chain(q)
                p_cur = chain_transforms[-1][:3, 3]
                R_cur = chain_transforms[-1][:3, :3]

                e_p = p_target - p_cur
                e_o = _rotation_error_vector(R_target, R_cur)
                e = np.concatenate([e_p, e_o])

                pos_err_m = float(np.linalg.norm(e_p))
                rot_err_rad = float(np.linalg.norm(e_o))

                if pos_err_m < best_pos_err:
                    best_pos_err = pos_err_m
                    best_rot_err = rot_err_rad
                    best_q = q.copy()

                # Check convergence
                if pos_err_m <= pos_tol_m and rot_err_rad <= rot_tol_rad:
                    J = self.chain.geometric_jacobian(q, chain_transforms)
                    cond = self.compute_condition_number(J)
                    joints_deg = [round(math.degrees(float(val)), 3) for val in q]
                    return IKResult(
                        status=IKStatus.SUCCESS,
                        success=True,
                        joints_rad=q,
                        joints_deg=joints_deg,
                        position_error_mm=round(pos_err_m * 1000.0, 4),
                        orientation_error_deg=round(math.degrees(rot_err_rad), 3),
                        iterations=total_iters,
                        condition_number=round(cond, 2),
                        failure_reason=None,
                    )

                J = self.chain.geometric_jacobian(q, chain_transforms)
                best_cond = self.compute_condition_number(J)

                # Damped Least Squares update: delta_q = (J^T J + lambda^2 I)^-1 J^T e
                JTJ = J.T @ J
                damped_matrix = JTJ + (damping ** 2) * np.eye(6, dtype=float)
                try:
                    delta_q = np.linalg.solve(damped_matrix, J.T @ e)
                except np.linalg.LinAlgError:
                    break

                # Clamp max step size to prevent divergence
                step_mag = float(np.linalg.norm(delta_q))
                if step_mag > 0.15:
                    delta_q = delta_q * (0.15 / step_mag)

                q = np.clip(q + delta_q, self.lower_limits, self.upper_limits)

        # Solver did not converge to within specified tolerance
        best_pos_err_mm = round(best_pos_err * 1000.0, 3)
        best_rot_err_deg = round(math.degrees(best_rot_err), 3)

        # Assess failure mode
        status = IKStatus.NON_CONVERGED
        if best_pos_err_mm > 50.0:
            status = IKStatus.UNREACHABLE
        elif any(abs(best_q[i] - self.lower_limits[i]) < 1e-4 or abs(best_q[i] - self.upper_limits[i]) < 1e-4 for i in range(6)):
            status = IKStatus.JOINT_LIMIT

        return IKResult(
            status=status,
            success=False,
            joints_rad=best_q,
            joints_deg=[round(math.degrees(float(val)), 3) for val in best_q] if best_q is not None else None,
            position_error_mm=best_pos_err_mm,
            orientation_error_deg=best_rot_err_deg,
            iterations=total_iters,
            condition_number=round(best_cond, 2),
            failure_reason=(
                f"Solver terminated with position error {best_pos_err_mm:.2f}mm (tol {pos_tol_mm}mm) "
                f"and orientation error {best_rot_err_deg:.2f}deg (tol {rot_tol_deg}deg)"
            ),
        )
