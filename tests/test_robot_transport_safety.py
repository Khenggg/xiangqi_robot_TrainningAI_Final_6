"""Offline transport regressions: no hardware sockets or actuator commands."""
import http.client
import socket
import threading
import time
import unittest
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer
from unittest.mock import Mock, patch
from xml.parsers.expat import ExpatError

from src.hardware import robot_sdk_core as sdk


class RobotTransportSafetyTests(unittest.TestCase):
    def rpc(self, transport):
        rpc = sdk.RPC.__new__(sdk.RPC)
        rpc.robot = xmlrpc.client.ServerProxy("http://offline.invalid:20003", transport=transport)
        rpc.reconnect_wait_timeout = .02
        rpc.stop_event = threading.Event()
        rpc.reconnect_flag = False
        rpc.closeRPC_state = False
        rpc.is_conect = True
        transport.cancel_check = lambda: rpc.closeRPC_state or rpc.stop_event.is_set()
        rpc.GetSafetyCode = Mock(return_value=0)
        return rpc

    def test_lost_response_never_replays_motion_or_tool_output(self):
        # Exercise real ServerProxy + Transport.single_request; only the HTTP
        # connection is fake. Stdlib Transport.request would replay some errors.
        for method, args in (
                ("MoveCart", dict(desc_pos=[1]*6, tool=0, user=1)),
                ("MoveJ", dict(joint_pos=[1]*6, desc_pos=[1]*6, tool=0, user=1)),
                ("SetToolDO", dict(id=0, status=1))):
            for failure in (http.client.RemoteDisconnected("response lost"),
                            ConnectionResetError("response lost"),
                            socket.timeout("response timeout")):
                with self.subTest(method=method, failure=type(failure).__name__):
                    transport = sdk.SingleAttemptTransport(timeout=.2)
                    connection = Mock()
                    connection.getresponse.side_effect = failure
                    send = Mock(return_value=connection)
                    rpc = self.rpc(transport)
                    with patch.object(transport, "send_request", send):
                        with self.assertRaises(sdk.RobotCommunicationError):
                            getattr(rpc, method)(**args)
                    self.assertEqual(send.call_count, 1)
                    self.assertEqual(xmlrpc.client.loads(send.call_args.args[2])[1], method)

    def test_idle_peer_closed_connection_does_not_break_next_distinct_command(self):
        """A loopback controller fixture closes keepalive after a valid reply."""
        peer_closed = threading.Event()
        received = []

        class ClosingHandler(SimpleXMLRPCRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_POST(self):
                super().do_POST()
                self.close_connection = True

            def finish(self):
                super().finish()
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.connection.close()
                peer_closed.set()

        server = SimpleXMLRPCServer(('127.0.0.1', 0), requestHandler=ClosingHandler,
                                    logRequests=False, allow_none=True)
        def set_output(*args):
            received.append(args)
            return 0
        server.register_function(set_output, 'SetToolDO')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        transport = sdk.SingleAttemptTransport(timeout=1)
        rpc = self.rpc(transport)
        rpc.robot = xmlrpc.client.ServerProxy(f'http://127.0.0.1:{server.server_address[1]}', transport=transport)
        try:
            self.assertEqual(0, rpc.SetToolDO(0, 0))
            self.assertTrue(peer_closed.wait(2))
            self.assertEqual(0, rpc.SetToolDO(1, 0))
            self.assertEqual([(0, 0, 0, 0), (1, 0, 0, 0)], received)
        finally:
            transport.close()
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_queued_output_is_cancelled_if_connection_closes_while_waiting(self):
        transport = sdk.SingleAttemptTransport()
        rpc = self.rpc(transport)
        gate_passed = threading.Event()
        failures = []
        original_gate = rpc._wait_for_reconnect

        def gate():
            original_gate()
            gate_passed.set()

        def command():
            try:
                rpc.SetToolDO(0, 1)
            except Exception as exc:
                failures.append(exc)

        worker = threading.Thread(target=command)
        with patch.object(rpc, '_wait_for_reconnect', side_effect=gate), \
                patch.object(transport, 'single_request') as send:
            try:
                with transport._request_lock:
                    worker.start()
                    self.assertTrue(gate_passed.wait(2))
                    rpc.stop_event.set()
            finally:
                rpc.stop_event.set()
                worker.join(2)
            self.assertFalse(worker.is_alive())
            send.assert_not_called()
        self.assertEqual(1, len(failures))
        self.assertIsInstance(failures[0], sdk.RobotCommunicationError)
        self.assertIn('command not sent', str(failures[0]))

    def test_http_connections_have_a_real_socket_timeout(self):
        transport = sdk.SingleAttemptTransport(timeout=.25)
        connection = transport.make_connection("offline.invalid:20003")
        self.assertEqual(connection.timeout, .25)
        sock = Mock()
        connection.sock = sock
        self.assertIs(transport.make_connection("offline.invalid:20003"), connection)
        sock.settimeout.assert_called_once_with(.25)

    def test_invalid_responses_abort_without_retry(self):
        for failure in (xmlrpc.client.ProtocolError("offline", 500, "bad response", {}),
                        ExpatError("truncated XML")):
            with self.subTest(failure=type(failure).__name__):
                transport = sdk.SingleAttemptTransport()
                with patch.object(transport, "single_request", side_effect=failure) as send:
                    with self.assertRaises(sdk.RobotCommunicationError):
                        self.rpc(transport).MoveCart([1]*6, 0, 1)
                    send.assert_called_once()

    def test_reconnect_wait_exits_without_sending(self):
        transport = sdk.SingleAttemptTransport()
        rpc = self.rpc(transport)
        rpc.reconnect_flag = True
        start = time.monotonic()
        with patch.object(transport, "single_request") as send:
            with self.assertRaisesRegex(sdk.RobotCommunicationError, "reconnect wait timed out"):
                rpc.MoveCart([1]*6, 0, 1)
            send.assert_not_called()
        self.assertLess(time.monotonic() - start, .5)

    def test_close_cancels_reconnect_wait(self):
        rpc = self.rpc(sdk.SingleAttemptTransport())
        rpc.reconnect_flag = True
        rpc.stop_event.set()
        with self.assertRaisesRegex(sdk.RobotCommunicationError, "closed"):
            rpc.SetToolDO(0, 1)

    def test_closed_connection_cannot_send_even_without_reconnect_flag(self):
        transport = sdk.SingleAttemptTransport()
        rpc = self.rpc(transport)
        rpc.stop_event.set()
        with patch.object(transport, "single_request") as send:
            with self.assertRaisesRegex(sdk.RobotCommunicationError, "closed"):
                rpc.MoveCart([1]*6, 0, 1)
            send.assert_not_called()

    def test_constructor_keeps_initial_health_and_global_socket_defaults(self):
        with patch.object(sdk.RPC, "connect_to_robot", return_value=True), \
                patch.object(sdk.threading, "Thread"), \
                patch.object(sdk.time, "sleep"), \
                patch.object(sdk.SingleAttemptTransport, "single_request", return_value=[0, "offline"]), \
                patch.object(sdk.socket, "setdefaulttimeout") as global_timeout:
            rpc = sdk.RPC("offline.invalid", rpc_timeout=.1)
        self.assertTrue(rpc.is_conect)
        self.assertTrue(rpc.SDK_state)
        global_timeout.assert_not_called()

    def test_failed_initial_probe_does_not_enable_commands(self):
        with patch.object(sdk.RPC, "connect_to_robot", return_value=True), \
                patch.object(sdk.threading, "Thread"), \
                patch.object(sdk.time, "sleep"), \
                patch.object(sdk.SingleAttemptTransport, "single_request", side_effect=socket.timeout):
            rpc = sdk.RPC("offline.invalid", rpc_timeout=.1)
        self.assertFalse(rpc.is_conect)
        self.assertFalse(rpc.SDK_state)
        with patch.object(sdk.SingleAttemptTransport, "single_request") as send:
            self.assertEqual(rpc.MoveCart([1]*6, 0, 1), sdk.RobotError.ERR_RPC_ERROR)
            send.assert_not_called()

    def test_recovery_status_requires_fresh_post_probe_packet(self):
        rpc = self.rpc(sdk.SingleAttemptTransport())
        rpc.SDK_state = True
        rpc.sock_cli_state_state = True
        packet = sdk.RobotStatePkg()
        packet.motion_done = 1
        packet.robot_state = 1
        rpc._publish_state_packet(packet)
        received = rpc._latest_state_health[0]
        self.assertTrue(rpc.has_fresh_idle_state(after=received-.001, timeout=0))
        self.assertFalse(rpc.has_fresh_idle_state(after=received+.001, timeout=0))
        rpc._latest_state_health = (received-2,) + rpc._latest_state_health[1:]
        self.assertFalse(rpc.has_fresh_idle_state(after=received-3, timeout=0))

    def test_recovery_status_rejects_moving_queued_faulted_or_disconnected(self):
        rpc = self.rpc(sdk.SingleAttemptTransport())
        rpc.SDK_state = True
        rpc.sock_cli_state_state = True
        for field, value in (("motion_done", 0), ("mc_queue_len", 1), ("robot_state", 2),
                             ("main_code", 1), ("sub_code", 1), ("safety_stop0_state", 1),
                             ("safety_stop1_state", 1), ("EmergencyStop", 1), ("collisionState", 1),
                             ("tl_dgt_output_l", 1), ("tl_dgt_output_l", 2)):
            with self.subTest(field=field):
                packet = sdk.RobotStatePkg()
                packet.motion_done = 1
                packet.robot_state = 1
                setattr(packet, field, value)
                rpc._publish_state_packet(packet)
                self.assertFalse(rpc.has_fresh_idle_state(after=rpc._latest_state_health[0]-.001, timeout=0))
        packet = sdk.RobotStatePkg()
        packet.motion_done = packet.robot_state = 1
        rpc._publish_state_packet(packet)
        rpc.sock_cli_state_state = False
        self.assertFalse(rpc.has_fresh_idle_state(after=rpc._latest_state_health[0]-.001, timeout=0))


if __name__ == "__main__":
    unittest.main()
