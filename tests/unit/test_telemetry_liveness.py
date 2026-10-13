import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import websockets

from src.hardware.telemetry_publisher import TelemetryPublisher


def test_blocked_command_does_not_freeze_telemetry_or_new_connections():
    publisher = TelemetryPublisher(port=0)
    entered, release = threading.Event(), threading.Event()
    second_entered = threading.Event()

    def blocked(command):
        if command.get("command") == "SECOND":
            second_entered.set()
        else:
            entered.set()
            release.wait(5)

    publisher.register_command_handler(blocked)
    publisher.start()

    async def observe():
        uri = f"ws://127.0.0.1:{publisher.port}"
        async with websockets.connect(uri, open_timeout=1, close_timeout=0.1) as first:
            await first.recv()
            await first.send(json.dumps({"command": "BLOCK"}))
            assert await asyncio.to_thread(entered.wait, 1)
            # An independent viewer must still handshake and receive fresh state.
            async with websockets.connect(uri, open_timeout=1, close_timeout=0.1) as second:
                await second.send(json.dumps({"command": "SECOND"}))
                publisher.update_state([1, 2, 3, 4, 5, 6], [0]*6, motion_state="IDLE")
                for _ in range(30):
                    packet = json.loads(await asyncio.wait_for(second.recv(), 1))
                    if packet.get("joints") == [1, 2, 3, 4, 5, 6]:
                        break
                else:
                    pytest.fail("Updated telemetry never reached the second viewer")
                assert not second_entered.is_set()  # Global dispatch remains serialized.
                release.set()
                assert await asyncio.to_thread(second_entered.wait, 1)
            release.set()

    try:
        asyncio.run(observe())
    finally:
        release.set()
        publisher.stop()


def test_delayed_mirror_snapshot_cannot_rewind_execution_telemetry():
    publisher = TelemetryPublisher()
    def snapshot(timestamp, joints, state):
        return SimpleNamespace(timestamp=timestamp, robot_model="FR3",
                               joints_deg=joints, tcp_pose_mm_deg=[0]*6,
                               gripper_closed=False, motion_state=state,
                               last_error=None, connected=True)
    publisher.update_from_snapshot(snapshot(20, [2]*6, "IDLE"))
    publisher.update_from_snapshot(snapshot(10, [1]*6, "MOVING"))
    packet = json.loads(publisher._make_packet_json())
    assert packet["joints"] == [2]*6
    assert packet["timestamp"] == 20 and packet["motion_state"] == "IDLE"


@pytest.mark.parametrize("physical,expects_fault", [(False, False), (True, True)])
def test_world_lock_delay_is_not_a_virtual_measurement_failure(physical, expects_fault):
    from src.digital_twin.live_twin_bridge import LiveTwinBridge
    # A deterministic clock avoids sleeps and models a read valid before waiting
    # for planning, but older than the age gate after acquiring the world lock.
    bridge = object.__new__(LiveTwinBridge)
    bridge.physical, bridge.owns_world = physical, False
    bridge.max_snapshot_age_s = 0.5
    bridge.active_move = None
    bridge._lock = threading.RLock()
    bridge.world = SimpleNamespace(_physics_lock=threading.RLock())
    bridge._fail = Mock(return_value=False)
    snapshot = SimpleNamespace(timestamp=100.0, measurement_timestamp=100.0,
                               connected=True, joints_valid=True)
    from unittest.mock import patch
    with patch("src.digital_twin.live_twin_bridge.time.time", side_effect=[100.1, 101.0]):
        assert bridge.sync_robot_state(snapshot) is False
    assert bridge._fail.called is expects_fault


def test_slow_viewer_keeps_only_latest_snapshot_and_does_not_delay_fast_viewer():
    from collections import deque
    publisher = TelemetryPublisher()

    async def observe():
        gate, entered = asyncio.Event(), asyncio.Event()
        class Client:
            def __init__(self, slow=False):
                self.slow, self.packets = slow, []
            async def send(self, message):
                if self.slow:
                    entered.set()
                    await gate.wait()
                self.packets.append(message)
            async def close(self, **kwargs):
                pass
        slow, fast = Client(True), Client()
        publisher._loop = asyncio.get_running_loop()
        publisher._outboxes = {client: ({}, deque(), asyncio.Event()) for client in (slow, fast)}
        writers = [asyncio.create_task(publisher._send_client_packets(client)) for client in (slow, fast)]
        try:
            publisher._queue_packet('0', 'robot_state')
            await asyncio.wait_for(entered.wait(), 1)
            for value in range(1, 1001):
                publisher._queue_packet(str(value), 'robot_state')
            await asyncio.sleep(0.1)
            assert len(publisher._outboxes[slow][0]) == 1
            assert fast.packets[-1] == '1000'
            gate.set()
            await asyncio.sleep(0.1)
            assert slow.packets == ['0', '1000']
        finally:
            for writer in writers:
                writer.cancel()
            await asyncio.gather(*writers, return_exceptions=True)
            publisher._loop = None
    asyncio.run(observe())


def test_custom_event_overflow_disconnects_instead_of_silently_losing_history():
    from collections import deque
    publisher = TelemetryPublisher()
    async def observe():
        class Client:
            async def close(self, **kwargs):
                assert kwargs['code'] == 1013
                closed.set()
        closed = asyncio.Event()
        client = Client()
        publisher._loop = asyncio.get_running_loop()
        publisher._outboxes = {client: ({}, deque(), asyncio.Event())}
        for value in range(65):
            publisher._queue_packet(str(value))
        await asyncio.wait_for(closed.wait(), 1)
        assert client not in publisher._outboxes
        publisher._loop = None
    asyncio.run(observe())
