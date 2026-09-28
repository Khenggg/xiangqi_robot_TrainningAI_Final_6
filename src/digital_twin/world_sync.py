"""Shared snapshot-to-world boundary. No motion commands or inverse kinematics."""

import numpy as np

from src.simulation.physics.transforms import rpy_deg_to_quat


def sync_world_from_robot_snapshot(world, snapshot, *, measured_tcp=False):
    """Apply six authoritative joints and gripper state atomically.

    Physical mirrors retain the canonical tool rigidly on the joint-derived flange;
    controller TCP is a parity diagnostic. Virtual backends may supply their TCP.
    """
    joints = np.asarray(snapshot.joints_deg, dtype=float)
    if joints.shape != (6,) or not np.all(np.isfinite(joints)):
        raise ValueError("Robot snapshot must contain six finite joint angles")
    with world._physics_lock:
        world.sync_robot_runtime_configuration(np.radians(joints))
        if measured_tcp:
            pos = np.asarray(snapshot.tcp_pose_mm_deg[:3], dtype=float) / 1000.0
            quat = rpy_deg_to_quat(snapshot.tcp_pose_mm_deg[3:])
        else:
            pos, quat = world.gripper.tcp_pos, world.gripper.tcp_quat
        world.update_robot_tcp(pos, quat, snapshot.gripper_closed)
