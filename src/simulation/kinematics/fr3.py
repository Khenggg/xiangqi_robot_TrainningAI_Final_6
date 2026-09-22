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
            np.array([0.0, -0.785, 1.571, -0.785, -1.571, 0.0], dtype=float),   # Standard elbow up (J5 ~ -90)
            np.array([0.0, -1.2, 1.8, -2.1, -1.571, 0.0], dtype=float),          # Folded reach (J5 ~ -90)
            np.array([0.0, -1.0, 2.0, -2.4, -1.571, 0.0], dtype=float),          # Deep reach (J5 ~ -90)
            np.array([0.0, -1.4, 2.4, -2.6, -1.571, 0.0], dtype=float),          # Extended reach (J5 ~ -90)
            np.array([0.0, -0.5, 1.2, -1.4, 1.571, 0.0], dtype=float),           # Downward wrist flip (J5 ~ +90)
            np.array([0.0, -0.8, 1.5, 0.4, 1.571, 2.5], dtype=float),            # Near-board folded (J5 ~ +90)
            np.array([0.0, -1.2, 1.8, 0.4, 1.571, 2.0], dtype=float),            # Near-board high (J5 ~ +90)
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

    def _solve_single_seed(
        self,
        p_target: np.ndarray,
        R_target: np.ndarray,
        seed: np.ndarray,
        max_iterations: int = 150,
        pos_tol_m: float = 0.001,
        rot_tol_rad: float = 0.017453,
        damping: float = 0.02,
    ) -> Optional[Tuple[np.ndarray, float, float, int, float]]:
        """
        Run Damped Least Squares on a single seed.
        Returns (q, pos_err_m, rot_err_rad, iterations, cond) if converged, else None.
        """
        q = np.clip(seed, self.lower_limits, self.upper_limits)
        for it in range(1, max_iterations + 1):
            chain_transforms = self.chain.forward_kinematics_chain(q)
            p_cur = chain_transforms[-1][:3, 3]
            R_cur = chain_transforms[-1][:3, :3]

            e_p = p_target - p_cur
            e_o = _rotation_error_vector(R_target, R_cur)
            e = np.concatenate([e_p, e_o])

            pos_err_m = float(np.linalg.norm(e_p))
            rot_err_rad = float(np.linalg.norm(e_o))

            if pos_err_m <= pos_tol_m and rot_err_rad <= rot_tol_rad:
                J = self.chain.geometric_jacobian(q, chain_transforms)
                cond = self.compute_condition_number(J)
                return q, pos_err_m, rot_err_rad, it, cond

            J = self.chain.geometric_jacobian(q, chain_transforms)
            JTJ = J.T @ J
            damped_matrix = JTJ + (damping ** 2) * np.eye(6, dtype=float)
            try:
                delta_q = np.linalg.solve(damped_matrix, J.T @ e)
            except np.linalg.LinAlgError:
                break

            step_mag = float(np.linalg.norm(delta_q))
            if step_mag > 0.15:
                delta_q = delta_q * (0.15 / step_mag)

            q = np.clip(q + delta_q, self.lower_limits, self.upper_limits)

        return None

    def solve_ik_candidates(
        self,
        target: Union[Pose3D, np.ndarray, Sequence[float]],
        seed_joints: Optional[Sequence[float]] = None,
        max_iterations: int = 150,
        pos_tol_mm: float = 1.0,
        rot_tol_deg: float = 1.0,
        damping: float = 0.02,
        ref_joints: Optional[Sequence[float]] = None,
    ) -> List[IKResult]:
        """
        Generate multiple valid, converged IK candidates across candidate seeds.
        Candidates are scored according to:
        1. Minimum joint-space displacement from ref_joints (or seed_joints)
        2. Same IK branch / wrist orientation (|Delta J5|)
        3. Joint limit margin
        4. Singularity / Jacobian condition number
        """
        try:
            if isinstance(target, Pose3D):
                target_pose = target
            elif isinstance(target, np.ndarray) and target.shape == (4, 4):
                target_pose = Pose3D.from_matrix(target)
            elif isinstance(target, (list, tuple, np.ndarray)) and len(target) == 6:
                vals = [float(v) for v in target]
                if not all(math.isfinite(v) for v in vals):
                    return []
                xyz_m = [vals[0] / 1000.0, vals[1] / 1000.0, vals[2] / 1000.0]
                rpy_rad = [math.radians(vals[3]), math.radians(vals[4]), math.radians(vals[5])]
                target_pose = Pose3D.from_xyz_rpy(xyz_m, rpy_rad)
            else:
                return []
        except Exception:
            return []

        p_target = target_pose.translation_m
        R_target = target_pose.rotation_matrix
        if not (np.all(np.isfinite(p_target)) and np.all(np.isfinite(R_target))):
            return []

        dist_from_base = float(np.linalg.norm(p_target))
        if dist_from_base > self.MAX_REACH_RADIUS_M:
            return []

        pos_tol_m = pos_tol_mm / 1000.0
        rot_tol_rad = math.radians(rot_tol_deg)

        # Reference joints for continuity scoring
        q_ref = None
        if ref_joints is not None:
            q_ref = np.asarray(ref_joints, dtype=float)
        elif seed_joints is not None:
            q_ref = np.asarray(seed_joints, dtype=float)

        seeds = []
        # Priority 1: ref_joints (continuity with current/previous posture)
        if q_ref is not None and len(q_ref) == 6 and np.all(np.isfinite(q_ref)):
            seeds.append(q_ref)

        # Priority 2: seed_joints (warm-start seed if different from ref_joints)
        if seed_joints is not None:
            s_arr = np.asarray(seed_joints, dtype=float)
            if len(s_arr) == 6 and np.all(np.isfinite(s_arr)):
                if not any(np.allclose(s_arr, s, atol=1e-3) for s in seeds):
                    seeds.append(s_arr)

        # Fast continuation check: if primary reference seed converges locally,
        # return immediately to preserve maximum trajectory evaluation speed
        if seeds:
            res_fast = self._solve_single_seed(
                p_target, R_target, seeds[0],
                max_iterations=max(min(max_iterations, 80), 30),
                pos_tol_m=pos_tol_m,
                rot_tol_rad=rot_tol_rad,
                damping=damping,
            )
            if res_fast is not None:
                q_sol, pos_err_m, rot_err_rad, iters, cond = res_fast
                disp = float(np.linalg.norm(q_sol - seeds[0]))
                branch_diff = float(abs(q_sol[4] - seeds[0][4]))
                margin_rad = min(
                    min(q_sol[k] - self.lower_limits[k], self.upper_limits[k] - q_sol[k])
                    for k in range(6)
                )
                if disp < 0.25 and branch_diff < 0.25 and margin_rad > 0.05:
                    return [
                        IKResult(
                            status=IKStatus.SUCCESS,
                            success=True,
                            joints_rad=q_sol,
                            joints_deg=[round(math.degrees(float(val)), 3) for val in q_sol],
                            position_error_mm=round(pos_err_m * 1000.0, 4),
                            orientation_error_deg=round(math.degrees(rot_err_rad), 3),
                            iterations=iters,
                            condition_number=round(cond, 2),
                            failure_reason=None,
                        )
                    ]

        # Multi-seed search: assemble concise set of candidate postures
        yaw_fr3 = math.atan2(-float(p_target[1]), -float(p_target[0]))
        for ref_s in self.reference_seeds:
            s_cand = ref_s.copy()
            s_cand[0] = yaw_fr3
            seeds.append(s_cand)
            s_cand_rev = ref_s.copy()
            s_cand_rev[0] = (yaw_fr3 + math.pi) % (2.0 * math.pi) - math.pi
            seeds.append(s_cand_rev)

        candidates: List[Tuple[float, IKResult]] = []
        seen_solutions: List[np.ndarray] = []

        max_it_search = min(max_iterations, 50)
        for s in seeds:
            res = self._solve_single_seed(
                p_target, R_target, s,
                max_iterations=max_it_search,
                pos_tol_m=pos_tol_m,
                rot_tol_rad=rot_tol_rad,
                damping=damping,
            )
            if res is None:
                continue

            q_sol, pos_err_m, rot_err_rad, iters, cond = res

            # Deduplicate
            if any(np.allclose(q_sol, seen_q, atol=1e-2) for seen_q in seen_solutions):
                continue
            seen_solutions.append(q_sol)

            # Joint limit margin
            margin_rad = min(
                min(q_sol[k] - self.lower_limits[k], self.upper_limits[k] - q_sol[k])
                for k in range(6)
            )

            # Continuity score: lower is better
            disp = float(np.linalg.norm(q_sol - q_ref)) if q_ref is not None else 0.0
            branch_diff = float(abs(q_sol[4] - q_ref[4])) if q_ref is not None else 0.0
            margin_penalty = 0.1 / max(margin_rad, 0.01)
            cond_penalty = cond / 200.0

            score = 2.0 * disp + 3.0 * branch_diff + margin_penalty + cond_penalty

            ik_res = IKResult(
                status=IKStatus.SUCCESS,
                success=True,
                joints_rad=q_sol,
                joints_deg=[round(math.degrees(float(val)), 3) for val in q_sol],
                position_error_mm=round(pos_err_m * 1000.0, 4),
                orientation_error_deg=round(math.degrees(rot_err_rad), 3),
                iterations=iters,
                condition_number=round(cond, 2),
                failure_reason=None,
            )
            candidates.append((score, ik_res))

        candidates.sort(key=lambda item: item[0])

        return [c[1] for c in candidates]

    def inverse_kinematics(
        self,
        target: Union[Pose3D, np.ndarray, Sequence[float]],
        seed_joints: Optional[Sequence[float]] = None,
        max_iterations: int = 150,
        pos_tol_mm: float = 1.0,
        rot_tol_deg: float = 1.0,
        damping: float = 0.02,
        allow_multi_seed: bool = True,
        ref_joints: Optional[Sequence[float]] = None,
    ) -> IKResult:
        """
        Solve full 6-DOF Inverse Kinematics using Damped Least Squares (DLS).
        When allow_multi_seed is True, evaluates multiple candidate seeds and
        ranks results by continuity to ref_joints (or seed_joints).
        """
        # Parse target into Pose3D
        try:
            if isinstance(target, Pose3D):
                target_pose = target
            elif isinstance(target, np.ndarray) and target.shape == (4, 4):
                target_pose = Pose3D.from_matrix(target)
            elif isinstance(target, (list, tuple, np.ndarray)) and len(target) == 6:
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

        pos_tol_m = pos_tol_mm / 1000.0
        rot_tol_rad = math.radians(rot_tol_deg)

        # Fast path: single seed requested and valid
        if not allow_multi_seed and seed_joints is not None:
            s_arr = np.asarray(seed_joints, dtype=float)
            if len(s_arr) == 6 and np.all(np.isfinite(s_arr)):
                res = self._solve_single_seed(
                    p_target, R_target, s_arr,
                    max_iterations=max_iterations,
                    pos_tol_m=pos_tol_m,
                    rot_tol_rad=rot_tol_rad,
                    damping=damping,
                )
                if res is not None:
                    q_sol, pos_err_m, rot_err_rad, iters, cond = res
                    return IKResult(
                        status=IKStatus.SUCCESS,
                        success=True,
                        joints_rad=q_sol,
                        joints_deg=[round(math.degrees(float(val)), 3) for val in q_sol],
                        position_error_mm=round(pos_err_m * 1000.0, 4),
                        orientation_error_deg=round(math.degrees(rot_err_rad), 3),
                        iterations=iters,
                        condition_number=round(cond, 2),
                        failure_reason=None,
                    )

        # Multi-seed search with continuity ranking
        candidates = self.solve_ik_candidates(
            target_pose,
            seed_joints=seed_joints,
            max_iterations=max_iterations,
            pos_tol_mm=pos_tol_mm,
            rot_tol_deg=rot_tol_deg,
            damping=damping,
            ref_joints=ref_joints if ref_joints is not None else seed_joints,
        )
        if candidates:
            return candidates[0]

        # Fallback tracking for non-converged diagnostics
        seeds = []
        if seed_joints is not None:
            seeds.append(np.asarray(seed_joints, dtype=float))
        yaw_base = math.atan2(float(p_target[1]), float(p_target[0]))
        for ref_s in self.reference_seeds:
            s_cand = ref_s.copy()
            s_cand[0] = yaw_base
            seeds.append(s_cand)

        best_q = None
        best_pos_err = float("inf")
        best_rot_err = float("inf")
        best_cond = float("inf")

        for seed in seeds:
            q = np.clip(seed, self.lower_limits, self.upper_limits)
            for it in range(min(max_iterations, 30)):
                chain_transforms = self.chain.forward_kinematics_chain(q)
                p_cur = chain_transforms[-1][:3, 3]
                R_cur = chain_transforms[-1][:3, :3]
                e_p = p_target - p_cur
                e_o = _rotation_error_vector(R_target, R_cur)
                pos_err_m = float(np.linalg.norm(e_p))
                rot_err_rad = float(np.linalg.norm(e_o))
                if pos_err_m < best_pos_err:
                    best_pos_err = pos_err_m
                    best_rot_err = rot_err_rad
                    best_q = q.copy()
                J = self.chain.geometric_jacobian(q, chain_transforms)
                best_cond = self.compute_condition_number(J)
                damped_matrix = J.T @ J + (damping ** 2) * np.eye(6, dtype=float)
                try:
                    delta_q = np.linalg.solve(damped_matrix, J.T @ np.concatenate([e_p, e_o]))
                except np.linalg.LinAlgError:
                    break
                step_mag = float(np.linalg.norm(delta_q))
                if step_mag > 0.15:
                    delta_q = delta_q * (0.15 / step_mag)
                q = np.clip(q + delta_q, self.lower_limits, self.upper_limits)

        best_pos_err_mm = round(best_pos_err * 1000.0, 3)
        best_rot_err_deg = round(math.degrees(best_rot_err), 3)
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
            iterations=len(seeds) * 30,
            condition_number=round(best_cond, 2),
            failure_reason=(
                f"Solver terminated with position error {best_pos_err_mm:.2f}mm (tol {pos_tol_mm}mm) "
                f"and orientation error {best_rot_err_deg:.2f}deg (tol {rot_tol_deg}deg)"
            ),
        )

