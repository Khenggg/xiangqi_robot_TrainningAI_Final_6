"""Camera-confirmed boards update actual PyBullet bodies, never robot commands."""

from dataclasses import replace
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pybullet as p
import pytest

from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.domain.board_pose import BoardPlacementState, compute_rotation_matrix
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.domain.game_move import MoveActor, MoveContext, initial_piece_identities
from src.hardware.backends.base import RobotStateSnapshot
from src.hardware.telemetry_publisher import TelemetryPublisher


@pytest.fixture
def twin():
    placement = BoardPlacementState.compute(
        forward_shift_mm=0.0, board_yaw_deg=31.0, nominal_board_center_robot_m=[-0.55, 0.35, 0.1],
        nominal_board_surface_z_m=0.2,
    )
    angle = np.radians(2.0)
    tilt = np.array([[1, 0, 0], [0, np.cos(angle), -np.sin(angle)],
                     [0, np.sin(angle), np.cos(angle)]])
    placement.rotation_matrix = (compute_rotation_matrix(31) @ tilt).tolist()
    snapshot = RobotStateSnapshot(
        "FR3", True, "IDLE", [0, -70, 60, -80, -90, 0],
        [0] * 6, [0] * 6, False, time.time(),
    )
    forbidden = Mock(side_effect=AssertionError("Camera synchronization issued a robot command"))
    backend = SimpleNamespace(
        get_state_snapshot=lambda: replace(snapshot, timestamp=time.time()),
        move_joint=forbidden, move_cartesian=forbidden, set_gripper=forbidden,
        connect=forbidden, enable_robot=forbidden,
    )
    telemetry = TelemetryPublisher(port=0)
    bridge = LiveTwinBridge(backend, FixedBoardPoseProvider(placement), telemetry)
    try:
        yield bridge, forbidden, telemetry
    finally:
        bridge.close()


@pytest.mark.parametrize("piece,src,dst,captured", [
    ("red_pawn_0", (6, 0), (5, 0), None),
    ("black_pawn_0", (3, 0), (4, 0), None),
    ("red_cannon_0", (7, 1), (0, 1), "black_knight_0"),
    ("black_cannon_0", (2, 1), (9, 1), "red_knight_0"),
])
def test_both_colors_moves_and_captures_update_real_bodies(twin, piece, src, dst, captured):
    bridge, forbidden, telemetry = twin
    world = bridge.world
    body = world.pieces[piece].body_id
    joints_before = world.get_robot_joint_positions()
    bodies_before = p.getNumBodies(physicsClientId=world.client_id)
    context = MoveContext(piece, src, dst, MoveActor.HUMAN, captured)
    assert bridge.reconcile_human_move(context)
    assert bridge.reconcile_human_move(context)  # replay is idempotent
    position, orientation = p.getBasePositionAndOrientation(body, physicsClientId=world.client_id)
    expected = bridge.placement.cell_to_robot_xyz(*dst, z_rel_m=world.pieces[piece].height_m / 2)
    np.testing.assert_allclose(position, expected, atol=1e-8)
    np.testing.assert_allclose(orientation, bridge.placement.quat_robot_from_board, atol=1e-8)
    aabb = p.getAABB(body, physicsClientId=world.client_id)
    np.testing.assert_allclose((np.array(aabb[0]) + aabb[1]) / 2, expected, atol=1e-8)
    assert p.getNumBodies(physicsClientId=world.client_id) == bodies_before - bool(captured)
    packets = {item["id"]: item for item in telemetry._latest_world_state["pieces"]}
    assert packets[piece]["nearest_row"] == dst[0]
    assert packets[piece]["nearest_col"] == dst[1]
    assert captured not in packets
    assert captured not in world.pieces
    assert world.get_robot_joint_positions() == joints_before
    forbidden.assert_not_called()


def test_full_confirmed_scan_relocates_both_colors_and_restores_removed_body(twin):
    bridge, forbidden, _ = twin
    cells = initial_piece_identities()
    cells[(5, 0)] = cells.pop((6, 0))
    cells[(4, 8)] = cells.pop((3, 8))
    del cells[(0, 1)]
    assert bridge.reconcile_to_board_cells(cells)
    assert set(bridge.world.pieces) == set(cells.values())
    for cell, pid in cells.items():
        piece = bridge.world.pieces[pid]
        np.testing.assert_allclose(piece.get_position_robot(), bridge.placement.cell_to_robot_xyz(
            *cell, z_rel_m=piece.height_m / 2), atol=1e-8)
    assert bridge.reconcile_new_game()
    assert len(bridge.world.pieces) == 32
    assert bridge.world.pieces["black_knight_0"].get_nearest_intersection()[:2] == (0, 1)
    forbidden.assert_not_called()


@pytest.mark.parametrize("cells", [
    {(0, 0): "unknown"}, {(11, 0): "black_rook_0"},
    {(0, 0): "black_rook_0", (0, 1): "black_rook_0"},
    {(0.5, 0): "black_rook_0"},
])
def test_invalid_full_scan_preserves_entire_scene(twin, cells):
    bridge, forbidden, _ = twin
    before = {pid: piece.get_position_robot() for pid, piece in bridge.world.pieces.items()}
    assert not bridge.reconcile_to_board_cells(cells)
    assert set(before) == set(bridge.world.pieces)
    for pid, pos in before.items():
        np.testing.assert_array_equal(bridge.world.pieces[pid].get_position_robot(), pos)
    forbidden.assert_not_called()


def test_camera_scan_cannot_release_attached_payload(twin):
    bridge, forbidden, _ = twin
    piece = bridge.world.pieces["black_rook_0"]
    bridge.world.gripper.attach_piece(piece)  # setup only, no physical grasp assertion
    assert not bridge.reconcile_to_board_cells(initial_piece_identities())
    assert not bridge.reconcile_new_game()
    assert bridge.world.get_attached_piece() is piece
    forbidden.assert_not_called()


def test_robot_can_manipulate_red_and_scan_cannot_override_pending_move(twin):
    bridge, forbidden, _ = twin
    context = MoveContext("red_pawn_0", (6, 0), (5, 0), MoveActor.ROBOT)
    assert bridge.begin_robot_move(context)
    assert not bridge.reconcile_to_board_cells(initial_piece_identities())
    assert bridge.active_move == context
    forbidden.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"connected": False}, {"motion_state": "MOVING"}, {"joints_valid": False},
    {"timestamp": 0.0}, {"timestamp": float("nan")},
])
def test_full_scan_cannot_clear_recovery_using_cached_idle_snapshot(twin, changes):
    bridge, forbidden, _ = twin
    assert bridge.poll_once()
    bridge.recovery_required = True
    original = dict(bridge._cells)
    current = bridge.backend.get_state_snapshot()
    bridge.backend.get_state_snapshot = lambda: replace(current, **changes)
    assert not bridge.reconcile_to_board_cells(initial_piece_identities())
    assert bridge.recovery_required
    assert bridge._cells == original
    forbidden.assert_not_called()
