"""Read-only donor review probes. Defect tests assert the observed bad behavior.

No hardware manager is instantiated; every robot and camera is a fake.
The socket probe binds loopback only and stores its registry under pytest tmp_path.
"""
import copy
import importlib.util
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest


SNAPSHOT = Path(__file__).parent / "final"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


donor = load_module("review_donor_pvp", SNAPSHOT / "player_vs_player.py")
donor.xiangqi = load_module("review_donor_xiangqi", SNAPSHOT / "src/core/xiangqi.py")


@pytest.fixture
def mode(monkeypatch):
    result = donor.PlayerVsPlayerMode(SimpleNamespace(screen=object()))
    result.room = donor.LocalRoom("robot")
    result.room.joined_black = True
    result.player_side = result.active_tab = "r"
    result.page = "game"
    result.draw = Mock()
    result._publish_state = Mock()
    monkeypatch.setattr(pygame.display, "flip", lambda: None)
    monkeypatch.setattr(donor.time, "sleep", lambda _: None)
    result.hardware = SimpleNamespace(
        robot=SimpleNamespace(connected=True, move_piece=Mock()),
        cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(), []))),
        yolo_detector=None,
        get_visual_pick_targets=Mock(return_value={"moving": None, "captured": None}),
        recognize_board_state=Mock(),
    )
    return result


RED_MOVE = ((0, 6), (0, 5))
BLACK_MOVE = ((0, 3), (0, 4))


def test_defect_camera_rejection_leaves_board_and_turn_committed(mode):
    before = copy.deepcopy(mode.room.board)
    observed_during_verification = []

    def recognize(_):
        observed_during_verification.append((copy.deepcopy(mode.room.board), mode.room.turn))
        return {"success": True, "board": before}

    mode.hardware.recognize_board_state.side_effect = recognize
    mode._perform_move("r", *RED_MOVE)
    expected, _ = donor.xiangqi.make_temp_move(before, RED_MOVE)
    assert not mode.room.physical_sync
    assert mode.room.board == expected and mode.room.turn == "b"
    assert observed_during_verification == [(expected, "b")] * 3


def test_defect_bad_quality_duplicate_nonconsecutive_scans_are_accepted(mode):
    before = copy.deepcopy(mode.room.board)
    expected, _ = donor.xiangqi.make_temp_move(before, RED_MOVE)
    bad_quality = {"success": True, "board": expected, "quality_ok": False,
                   "confidence": [[0.0] * 9 for _ in range(10)],
                   "frame_sequence": 1, "captured_at": 1.0}
    mode.hardware.recognize_board_state.side_effect = [
        bad_quality, {"success": False, "board": before}, bad_quality,
    ]
    mode._perform_move("r", *RED_MOVE)
    assert mode.room.physical_sync is True
    assert mode.robot_retry_pending is None


def test_defect_missing_visual_target_still_calls_robot(mode):
    mode.hardware.recognize_board_state.return_value = {"success": False}
    mode._perform_move("r", *RED_MOVE)
    mode.hardware.robot.move_piece.assert_called_once()
    assert mode.hardware.robot.move_piece.call_args.kwargs["moving_visual_target"] is None


def test_defect_rejected_structured_motion_result_is_treated_as_completion(mode):
    before = copy.deepcopy(mode.room.board)
    expected, _ = donor.xiangqi.make_temp_move(before, RED_MOVE)
    mode.hardware.robot.move_piece.return_value = SimpleNamespace(success=False, message="rejected")
    mode.hardware.recognize_board_state.return_value = {"success": True, "board": expected}
    mode._perform_move("r", *RED_MOVE)
    assert mode.room.board == expected and mode.room.turn == "b"
    assert mode.room.physical_sync


def test_defect_move_executes_synchronously_in_event_caller_thread(mode):
    thread_ids = []
    mode.hardware.robot.move_piece.side_effect = lambda *a, **kw: thread_ids.append(threading.get_ident())
    mode.hardware.recognize_board_state.return_value = {"success": False}
    for col, row in RED_MOVE:
        mode._on_board_click(mode.board_left + col * mode.cell, mode.board_top + row * mode.cell)
    assert thread_ids == [threading.get_ident()]


def test_defect_back_to_menu_keeps_old_room_and_prevents_joining_new_room(mode):
    mode.hardware = None
    old_room = mode.room
    mode._back_to_menu()
    mode._join("ZZZZZZ" if old_room.code != "ZZZZZZ" else "AAAAAA")
    assert mode.page == "menu" and mode.room is old_room
    assert "Mã không hợp lệ" in mode.status


def test_defect_single_window_join_cannot_play_black(mode):
    mode.hardware = None
    mode.room.mode = "local"
    mode._join(mode.room.code)
    mode._perform_move("r", *RED_MOVE)
    before = copy.deepcopy(mode.room.board)
    mode.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB), (0, 0))
    assert mode.active_tab == "b" and mode.player_side == "r"
    mode._on_board_click(mode.board_left, mode.board_top + 3 * mode.cell)
    assert mode.room.board == before and mode.room.turn == "b"
    assert "Cửa sổ này" in mode.status


def test_defect_disconnected_client_can_commit_an_offline_move(mode):
    mode.hardware = None
    mode.room.mode = "local"
    mode.room.turn = "b"
    mode.player_side = mode.active_tab = "b"
    events = queue.Queue()
    events.put({"type": "disconnected"})
    client = SimpleNamespace(events=events, close=Mock())
    mode.room_client = client
    mode.poll_remote()
    assert mode.room_client is None and mode.room.joined_black
    for col, row in BLACK_MOVE:
        c, r = donor.PlayerVsPlayerMode._board_view_pos(col, row, True)
        mode._on_board_click(mode.board_left + c * mode.cell, mode.board_top + r * mode.cell)
    assert mode.room.turn == "r" and mode.room.board[4][0] == "b_P"


def test_current_pick_test_contract_rejects_donor_call(mode):
    from src.hardware.hardware_manager import HardwareManager
    mode.hardware.execute_pick_place_test = HardwareManager.execute_pick_place_test.__get__(mode.hardware)
    mode.pick_test_board = donor.xiangqi.get_board()
    mode._run_pick_test(*RED_MOVE)
    assert mode.pick_test_blocked
    assert "move_context" in mode.status


def test_safe_local_two_turns_and_board_orientation():
    m = donor.PlayerVsPlayerMode(SimpleNamespace(screen=object()))
    m.room = donor.LocalRoom("local")
    m._perform_move("r", *RED_MOVE)
    m._perform_move("b", *BLACK_MOVE)
    assert m.room.turn == "r" and m.room.board[5][0] == "r_P" and m.room.board[4][0] == "b_P"
    assert m._board_view_pos(0, 3, True) == (8, 6)
    assert m._board_view_pos(8, 6, True) == (0, 3)


def test_defect_donor_connect_enables_and_commands_gripper_without_camera(mode, monkeypatch):
    robot_module = load_module("review_donor_robot", SNAPSHOT / "src/hardware/robot_VIP.py")
    rpc = SimpleNamespace(SDK_state=True, RobotEnable=Mock(return_value=0), Mode=Mock(return_value=0))
    monkeypatch.setattr(robot_module, "robot_sdk_core", SimpleNamespace(RPC=lambda _: rpc))
    robot = robot_module.FR5Robot.__new__(robot_module.FR5Robot)
    robot.dry = False
    robot.ip = "mock-only"
    for name in ["_validate_gripper_config", "_set_gripper_safe_idle", "gripper_ctrl", "_load_teaching_points"]:
        setattr(robot, name, Mock())
    robot.connect()
    rpc.RobotEnable.assert_called_once_with(1)
    rpc.Mode.assert_called_once_with(0)
    assert robot.gripper_ctrl.call_count == 2


def test_defect_donor_capture_accepts_no_targets_or_clearance_callbacks(mode):
    robot_module = load_module("review_donor_capture", SNAPSHOT / "src/hardware/robot_VIP.py")
    robot = robot_module.FR5Robot.__new__(robot_module.FR5Robot)
    robot.connected = True
    robot.dry = True
    for name in ["pick_at", "move_to_extra_safe", "place_in_capture_bin", "place_at", "go_to_home_chess"]:
        setattr(robot, name, Mock())
    robot.move_piece(0, 5, 0, 4, True)
    assert robot.pick_at.call_count == 2
    assert all(call.kwargs["visual_target"] is None for call in robot.pick_at.call_args_list)
    robot.place_in_capture_bin.assert_called_once()
    robot.go_to_home_chess.assert_called_once()


def wait_event(events, wanted):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        event = events.get(timeout=max(0.001, deadline - time.monotonic()))
        if event.get("type") == wanted:
            return event
    raise AssertionError(f"Missing event: {wanted}")


@pytest.mark.serial
def test_loopback_room_join_state_and_move(tmp_path, monkeypatch):
    monkeypatch.setattr(donor, "ROOM_REGISTRY", str(tmp_path))
    host = donor.LocalRoomHost("ABC234", "local")
    client = None
    try:
        client = donor.LocalRoomClient("ABC234", host.port)
        assert wait_event(host.events, "joined")["type"] == "joined"
        assert host.send({"type": "state", "turn": "b", "revision": 1})
        assert wait_event(client.events, "state")["revision"] == 1
        assert client.send({"type": "move", "src": [0, 3], "dst": [0, 4]})
        assert wait_event(host.events, "move")["dst"] == [0, 4]
    finally:
        if client is not None:
            client.close()
            client.thread.join(3)
        host.close()
        host.thread.join(3)
    assert not host.thread.is_alive()
    assert not (tmp_path / "ABC234.json").exists()
