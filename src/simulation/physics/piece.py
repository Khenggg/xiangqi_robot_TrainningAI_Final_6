"""
Xiangqi piece rigid body wrapper for PyBullet simulation.
"""

from typing import List, Optional, Sequence, Tuple
import numpy as np
import pybullet as p

from src.simulation.physics.state import PiecePhysicalState, PieceSnapshot
from src.simulation.physics.transforms import (
    continuous_board_coord,
    nearest_intersection_metrics,
    tilt_angle_deg,
    transform_point_robot_to_world,
    transform_quat_robot_to_world,
)


class XiangqiPieceBody:
    """
    Manages a single rigid-body Xiangqi piece cylinder in PyBullet.
    """

    def __init__(
        self,
        piece_id: str,
        side: str,
        piece_type: str,
        body_id: int,
        client_id: int,
        radius_m: float,
        height_m: float,
        mass_kg: float,
        grid_origin_robot: Sequence[float],
        col_spacing_m: float = 0.040,
        row_spacing_m: float = 0.040,
    ):
        self.piece_id = str(piece_id)
        self.side = str(side)
        self.piece_type = str(piece_type)
        self.body_id = int(body_id)
        self.client_id = int(client_id)
        self.radius_m = float(radius_m)
        self.height_m = float(height_m)
        self.mass_kg = float(mass_kg)
        self.grid_origin_robot = tuple(float(v) for v in grid_origin_robot)
        self.col_spacing_m = float(col_spacing_m)
        self.row_spacing_m = float(row_spacing_m)

        self.physical_state = PiecePhysicalState.SETTLING
        self.attached_to_gripper = False

        # In-bounds tracking
        self._consecutive_settled_steps = 0

    def get_pose_robot_base(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (position [3], quaternion [x, y, z, w]) in robot_base."""
        pos, orn = p.getBasePositionAndOrientation(
            self.body_id, physicsClientId=self.client_id
        )
        return np.array(pos, dtype=float), np.array(orn, dtype=float)

    def get_velocity(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return (linear_velocity [3], angular_velocity [3]) in robot_base."""
        lin, ang = p.getBaseVelocity(self.body_id, physicsClientId=self.client_id)
        return np.array(lin, dtype=float), np.array(ang, dtype=float)

    def get_tilt_deg(self) -> float:
        """Calculate tilt angle relative to vertical up (+Z in robot_base)."""
        _, orn = self.get_pose_robot_base()
        return tilt_angle_deg(orn)

    def get_continuous_board_coord(self) -> Tuple[float, float]:
        """Return continuous (col, row) on board plane."""
        pos, _ = self.get_pose_robot_base()
        return continuous_board_coord(
            pos,
            self.grid_origin_robot,
            self.col_spacing_m,
            self.row_spacing_m,
        )

    def get_nearest_intersection(self) -> Tuple[int, int, float]:
        """Return (nearest_col, nearest_row, distance_to_target_m)."""
        pos, _ = self.get_pose_robot_base()
        c_float, r_float = self.get_continuous_board_coord()
        return nearest_intersection_metrics(
            c_float,
            r_float,
            pos,
            self.grid_origin_robot,
            self.col_spacing_m,
            self.row_spacing_m,
        )

    @property
    def tilt_angle_deg(self) -> float:
        return self.get_tilt_deg()

    @property
    def nearest_dist_m(self) -> float:
        _, _, dist = self.get_nearest_intersection()
        return dist

    def set_pose_robot_base(self, position: Sequence[float], orientation: Sequence[float]) -> None:
        """Force set position and orientation in robot_base."""
        p.resetBasePositionAndOrientation(
            self.body_id,
            list(position),
            list(orientation),
            physicsClientId=self.client_id,
        )

    def set_velocity(self, linear_vel: Sequence[float], angular_vel: Sequence[float]) -> None:
        """Set linear and angular velocity."""
        p.resetBaseVelocity(
            self.body_id,
            linearVelocity=list(linear_vel),
            angularVelocity=list(angular_vel),
            physicsClientId=self.client_id,
        )

    def to_snapshot(self) -> PieceSnapshot:
        """Generate immutable snapshot for telemetry and diagnostics."""
        pos_robot, quat_robot = self.get_pose_robot_base()
        lin_vel, ang_vel = self.get_velocity()

        pos_world = transform_point_robot_to_world(pos_robot)
        quat_world = transform_quat_robot_to_world(quat_robot)

        col_float, row_float = self.get_continuous_board_coord()
        nearest_c, nearest_r, dist_m = self.get_nearest_intersection()

        return PieceSnapshot(
            id=self.piece_id,
            side=self.side,
            type=self.piece_type,
            position_robot_base_m=[round(float(v), 5) for v in pos_robot],
            orientation_quaternion_robot_base=[round(float(v), 5) for v in quat_robot],
            position_3d_world_m=[round(float(v), 5) for v in pos_world],
            orientation_quaternion_3d_world=[round(float(v), 5) for v in quat_world],
            linear_velocity_m_s=[round(float(v), 5) for v in lin_vel],
            angular_velocity_rad_s=[round(float(v), 5) for v in ang_vel],
            physical_state=self.physical_state.value,
            attached=self.attached_to_gripper,
            tilt_deg=round(self.get_tilt_deg(), 2),
            col_float=round(col_float, 3),
            row_float=round(row_float, 3),
            nearest_col=nearest_c,
            nearest_row=nearest_r,
            distance_to_nearest_intersection_m=round(dist_m, 5),
        )
