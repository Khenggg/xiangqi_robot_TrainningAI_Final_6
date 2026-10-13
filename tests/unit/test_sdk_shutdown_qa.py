"""Local socket/thread shutdown tests; never connect to a controller."""
import socket
import threading
import time
from unittest.mock import Mock

from src.hardware.robot_sdk_core import RPC, RobotStatePkg


def sdk_handle(connected=True):
    sdk = RPC.__new__(RPC)
    sdk.is_conect = connected
    sdk.SDK_state = connected
    sdk.closeRPC_state = False
    sdk.robot_realstate_exit = False
    sdk.stop_event = threading.Event()
    sdk.reconnect_flag = False
    sdk.sock_cli_state_state = False
    sdk.sock_cli_state = None
    sdk.robot_state_pkg = RobotStatePkg
    sdk.robot = Mock()
    sdk.thread = threading.Thread()
    return sdk


def test_close_rpc_runs_even_when_xmlrpc_connection_failed():
    sdk = sdk_handle(connected=False)
    controller = sdk.robot
    state_socket = Mock()
    sdk.sock_cli_state = state_socket
    sdk.CloseRPC()
    assert sdk.stop_event.is_set()
    assert sdk.closeRPC_state and not sdk.SDK_state
    assert sdk.sock_cli_state is None and sdk.robot is None
    state_socket.close.assert_called_once()
    assert controller.mock_calls == []
    sdk.CloseRPC()  # Idempotent cleanup of a failed/closed connection.


def test_close_rpc_stops_receiver_with_missing_xmlrpc_proxy():
    sdk = sdk_handle()
    sdk.robot = None
    state_socket = Mock()
    sdk.sock_cli_state = state_socket
    sdk.CloseRPC()
    assert sdk.closeRPC_state and sdk.stop_event.is_set()
    assert sdk.sock_cli_state is None
    state_socket.close.assert_called_once()


def test_close_interrupts_reconnect_delay_without_second_attempt():
    sdk = sdk_handle()
    attempted = threading.Event()
    def unavailable():
        attempted.set()
        return False
    sdk.connect_to_robot = Mock(side_effect=unavailable)
    sdk.thread = threading.Thread(target=sdk.reconnect, daemon=True)
    sdk.thread.start()
    try:
        assert attempted.wait(1)
        begin = time.monotonic()
        sdk.CloseRPC()
        assert time.monotonic() - begin < .75
        assert not sdk.thread.is_alive()
        assert not sdk.reconnect_flag and not sdk.SDK_state
        sdk.connect_to_robot.assert_called_once()
    finally:
        sdk.stop_event.set()
        sdk.closeRPC_state = True
        sdk.thread.join(3)


def test_reconnect_does_not_restore_sdk_state_after_stop_during_connect():
    sdk = sdk_handle()
    def cancelled_connect():
        sdk.stop_event.set()
        return True
    sdk.connect_to_robot = Mock(side_effect=cancelled_connect)
    assert not sdk.reconnect()
    assert not sdk.SDK_state and not sdk.reconnect_flag


def test_closed_sdk_never_opens_another_state_socket(monkeypatch):
    sdk = sdk_handle()
    sdk.closeRPC_state = True
    sdk.stop_event.set()
    factory = Mock(side_effect=AssertionError('State socket reopened after close'))
    monkeypatch.setattr('src.hardware.robot_sdk_core.socket.socket', factory)
    assert not sdk.connect_to_robot()
    factory.assert_not_called()


def test_close_wakes_actual_socket_receiver_and_joins_thread():
    sdk = sdk_handle()
    controller = sdk.robot
    receiver, sender = socket.socketpair()
    receiver.settimeout(5)
    sdk.sock_cli_state = receiver
    sdk.sock_cli_state_state = True
    sdk.thread = threading.Thread(target=sdk.robot_state_routine_thread, daemon=True)
    sdk.thread.start()
    try:
        sdk.CloseRPC()
        assert not sdk.thread.is_alive()
        assert not sdk.SDK_state and not sdk.sock_cli_state_state
        assert sdk.robot is None and sdk.sock_cli_state is None
        assert controller.mock_calls == []
    finally:
        sender.close()
        receiver.close()
        sdk.stop_event.set()
        sdk.thread.join(1)
