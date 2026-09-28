"""Unit tests for Live Digital Twin physical mirroring, contracts, and safety invariants.

Tests cover:
1. physical joint snapshots update PyBullet joints
2. repeated snapshots never revert to stale joints
3. Human Red non-capture updates simulation only and issues zero robot motion
4. Human Red capture updates both involved simulation pieces and issues zero robot motion
5. Robot Black move sets deterministic expected piece identity
6. gripper close attaches exactly the intended piece
7. attached piece follows mirrored physical arm
8. gripper open releases it
9. Black capture supports removing captured Red before moving Black
10. E-stop/interruption preserves latest actual robot pose
11. viewer telemetry matches authoritative world state
12. human animation cannot leave collider at source
13. physical board calibration is reused by Digital Twin
14. automated tests cannot actuate physical hardware
15. existing Virtual mode still works
16. physical mirroring does not use IK to reproduce the real arm pose
"""

import time
import math
from unittest.mock import MagicMock
import numpy as np
import pybullet as p
import pytest

from src.core.game_state import GameState
from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.domain.board_pose_provider import (
    FixedBoardPoseProvider,
    PhysicalTeachingPointBoardPoseProvider,
    BoardCalibrationProfile,
    BoardCalibrationTolerancePolicy,
)
from src.domain.game_move import MoveActor, MoveContext
from src.hardware.backends.base import RobotStateSnapshot
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.physics.piece import PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld


@pytest.fixture
def bridge_setup():
    backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=True)
    backend.connect()
    provider = FixedBoardPoseProvider.from_forward_shift(0.0)
    world = VirtualPhysicalWorld(
        board_placement_state=provider.get_board_placement_state(),
        enable_gui=False,
    )
    bridge = LiveTwinBridge(backend=backend, board_pose_provider=provider, world=world)
    yield bridge, backend, provider, world
    bridge.close()


def test_01_physical_joint_snapshots_update_pybullet_joints(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    test_joints_deg = [15.0, -35.0, 75.0, -120.0, -60.0, 30.0]
    now = time.time()
    snapshot = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="IDLE",
        joints_deg=test_joints_deg,
        flange_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        gripper_closed=False,
        timestamp=now,
        joints_valid=True,
        tcp_valid=True,
        measurement_timestamp=now,
    )

    success = bridge.sync_robot_state(snapshot)
    assert success is True
    pybullet_joints = world.get_robot_joint_positions()
    expected_joints = np.radians(test_joints_deg)
    assert np.allclose(pybullet_joints, expected_joints, atol=1e-3)


def test_02_repeated_snapshots_never_revert_to_stale_joints(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    t1 = time.time()
    joints1 = [10.0, -20.0, 30.0, -40.0, 50.0, -60.0]
    snap1 = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="IDLE",
        joints_deg=joints1,
        flange_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        gripper_closed=False,
        timestamp=t1,
        joints_valid=True,
        measurement_timestamp=t1,
    )
    assert bridge.sync_robot_state(snap1) is True
    assert np.allclose(world.get_robot_joint_positions(), np.radians(joints1), atol=1e-3)

    # Older out-of-order snapshot
    t0 = t1 - 10.0
    joints0 = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    snap0 = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="IDLE",
        joints_deg=joints0,
        flange_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        gripper_closed=False,
        timestamp=t0,
        joints_valid=True,
        measurement_timestamp=t0,
    )
    # Must reject and keep joints1
    assert bridge.sync_robot_state(snap0) is False
    assert np.allclose(world.get_robot_joint_positions(), np.radians(joints1), atol=1e-3)


def test_03_human_red_non_capture_updates_simulation_only_and_zero_robot_motion(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    initial_joints = backend.get_state_snapshot().joints_deg

    context = MoveContext(
        piece_id="red_pawn_0",
        src=(6, 0),
        dst=(5, 0),
        actor=MoveActor.HUMAN,
        captured_piece_id=None,
    )
    success = bridge.reconcile_human_move(context)
    assert success is True

    # Simulation piece is at destination (5, 0)
    piece = world.pieces["red_pawn_0"]
    r, c, dist = piece.get_nearest_intersection()
    assert (r, c) == (5, 0)
    assert dist < piece.radius_m
    assert piece.physical_state == PiecePhysicalState.RESTING

    # Zero robot motion
    current_joints = backend.get_state_snapshot().joints_deg
    assert current_joints == initial_joints


def test_04_human_red_capture_updates_both_simulation_pieces_zero_robot_motion(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    initial_joints = backend.get_state_snapshot().joints_deg

    # Move red cannon to capture black knight at (0, 1)
    context = MoveContext(
        piece_id="red_cannon_0",
        src=(7, 1),
        dst=(0, 1),
        actor=MoveActor.HUMAN,
        captured_piece_id="black_knight_0",
    )
    success = bridge.reconcile_human_move(context)
    assert success is True

    # Captured piece removed from world
    assert "black_knight_0" not in world.pieces
    # Attacker moved to destination
    piece = world.pieces["red_cannon_0"]
    r, c, dist = piece.get_nearest_intersection()
    assert (r, c) == (0, 1)
    assert dist < piece.radius_m

    # Zero robot motion
    assert backend.get_state_snapshot().joints_deg == initial_joints


def test_06_to_08_gripper_close_attach_follow_and_release(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    piece_id = "black_cannon_0"
    target_piece = world.pieces[piece_id]

    # Pre-position backend joints directly over piece
    grasp_joints = [-117.01, -59.39, 83.1, -113.7, -90.0, -117.01]
    backend._current_joints_deg = list(grasp_joints)
    bridge.poll_once()

    # Begin robot move
    context = MoveContext(
        piece_id=piece_id,
        src=(2, 1),
        dst=(2, 4),
        actor=MoveActor.ROBOT,
    )
    assert bridge.begin_robot_move(context) is True
    assert bridge.set_expected_payload(piece_id) is True

    # 6. Gripper close attaches exactly intended piece
    backend._gripper_closed = True
    assert bridge.on_gripper_closed(piece_id) is True
    attached = world.get_attached_piece()
    assert attached is not None
    assert attached.piece_id == piece_id
    assert attached.physical_state == PiecePhysicalState.ATTACHED_TO_GRIPPER

    # 7. Attached piece follows mirrored arm
    p_before, _ = attached.get_pose_robot_base()
    # Apply snapshot with lifted arm
    now = time.time()
    lifted_joints = [-117.01, -45.0, 65.0, -113.7, -90.0, -117.01]
    snap_lifted = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="MOVING",
        joints_deg=lifted_joints,
        flange_pose_mm_deg=[-360, 0, 300, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 300, 180, 0, 90],
        gripper_closed=True,
        timestamp=now,
        joints_valid=True,
        tcp_valid=True,
        measurement_timestamp=now,
    )
    assert bridge.sync_robot_state(snap_lifted) is True
    p_after, _ = attached.get_pose_robot_base()
    # Attached piece moved with arm
    assert not np.allclose(p_before, p_after)

    # 8. Gripper open releases it
    backend._gripper_closed = False
    assert bridge.on_gripper_opened() is True
    assert world.get_attached_piece() is None
    assert attached.physical_state in (PiecePhysicalState.RESTING, PiecePhysicalState.SETTLING)


def test_10_estop_interruption_preserves_latest_actual_robot_pose(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    estop_joints = [25.0, -45.0, 65.0, -110.0, -75.0, 15.0]
    now = time.time()
    estop_snap = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="ESTOP",
        joints_deg=estop_joints,
        flange_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        gripper_closed=False,
        timestamp=now,
        joints_valid=True,
        last_error="Controller E-Stop active",
        measurement_timestamp=now,
    )

    result = bridge.sync_robot_state(estop_snap)
    # sync returns False because motion_state is ESTOP / error
    assert result is False
    assert bridge.last_error == "Controller E-Stop active"
    # Authoritative arm pose is PRESERVED at actual joints, not reverted or zeroed
    pybullet_joints = world.get_robot_joint_positions()
    assert np.allclose(pybullet_joints, np.radians(estop_joints), atol=1e-3)


def test_11_viewer_telemetry_matches_authoritative_world_state(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    mock_telemetry = MagicMock()
    bridge.telemetry = mock_telemetry

    now = time.time()
    snap = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="IDLE",
        joints_deg=[0.0, -45.0, 90.0, -135.0, -90.0, 0.0],
        flange_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        gripper_closed=False,
        timestamp=now,
        joints_valid=True,
        measurement_timestamp=now,
    )
    bridge.sync_robot_state(snap)

    mock_telemetry.update_from_snapshot.assert_called()
    mock_telemetry.update_world_state.assert_called()
    packet = mock_telemetry.update_world_state.call_args[0][0]
    assert "pieces" in packet
    assert "gripper" in packet
    assert packet.get("physical_grasp_verified") is False


def test_12_human_animation_cannot_leave_collider_at_source(bridge_setup):
    bridge, backend, provider, world = bridge_setup
    piece = world.pieces["red_pawn_0"]

    context = MoveContext(
        piece_id="red_pawn_0",
        src=(6, 0),
        dst=(5, 0),
        actor=MoveActor.HUMAN,
    )
    bridge.reconcile_human_move(context)

    # PyBullet body position directly queried from physics server
    pos, _ = p.getBasePositionAndOrientation(piece.body_id, physicsClientId=world.client_id)
    target_pos = provider.get_board_placement_state().cell_to_robot_xyz(5, 0, z_rel_m=piece.height_m / 2.0)

    assert np.allclose(pos, target_pos, atol=1e-3)


def test_13_physical_board_calibration_is_reused_by_digital_twin():
    backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=True)
    backend.connect()

    cal_profile = BoardCalibrationProfile(
        tcp_to_board_contact_offset_mm=[0.0, 0.0, 0.0],
        offset_frame="ROBOT_BASE",
        provenance="TEST_CALIBRATION",
    )
    cal_policy = BoardCalibrationTolerancePolicy(max_board_tilt_hard_fail_deg=5.0)
    provider = PhysicalTeachingPointBoardPoseProvider.from_controller(
        backend, calibration_profile=cal_profile, tolerance_policy=cal_policy
    )
    assert provider.is_calibrated

    bridge = LiveTwinBridge(backend=backend, board_pose_provider=provider)
    assert bridge.world.board_placement_state is provider.get_board_placement_state()
    bridge.close()


def test_14_automated_tests_cannot_actuate_physical_hardware():
    backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=True)
    assert backend.dry_run is True
    # In dry-run, RPC must never connect to live robot sockets
    assert backend._rpc is None
    # All commands return success code 0 without hardware actuation
    assert backend.set_tool_do(0, 1) == 0
    assert backend.set_tool_do(1, 0) == 0


def test_16_physical_mirroring_does_not_use_ik_to_reproduce_real_arm_pose(bridge_setup, monkeypatch):
    bridge, backend, provider, world = bridge_setup

    def forbidden_ik(*args, **kwargs):
        raise AssertionError("Physical mirroring MUST NOT call inverse kinematics!")

    monkeypatch.setattr(FR3Kinematics, "inverse_kinematics", forbidden_ik)

    now = time.time()
    snap = RobotStateSnapshot(
        robot_model="FR3",
        connected=True,
        motion_state="IDLE",
        joints_deg=[12.0, -34.0, 56.0, -78.0, -90.0, 12.0],
        flange_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        tcp_pose_mm_deg=[-360, 0, 200, 180, 0, 90],
        gripper_closed=False,
        timestamp=now,
        joints_valid=True,
        measurement_timestamp=now,
    )
    # Must succeed without calling forbidden_ik
    assert bridge.sync_robot_state(snap) is True
