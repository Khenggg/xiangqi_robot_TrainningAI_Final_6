"""Actual loopback transport and Pygame events; no robot/controller imports."""
import json
import queue
import socket
import time

import pytest

from src.core import xiangqi
from src.core.pvp_room import LocalRoomHost, LocalRoomClient, MAX_FRAME, _messages
from src.ui.pvp_client import ClientApp, ClientBoard, view_cell


def until(predicate, timeout=3):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.01)
    raise AssertionError('Loopback condition did not arrive before deadline')


def take(events, kind):
    def find():
        while True:
            try: packet = events.get_nowait()
            except queue.Empty: return None
            if packet['type'] == kind:
                return packet
    return until(find)


def test_real_loopback_join_move_disconnect_rejoin_and_clean_registry(tmp_path):
    host = LocalRoomHost(tmp_path)
    client = LocalRoomClient(host.code, tmp_path)
    other = None
    try:
        until(lambda: host.connected and client.connected)
        welcome = take(client.events, 'welcome')
        first = welcome['generation']
        host.publish(dict(board=xiangqi.get_board(),turn='b',revision=4,epoch=2))
        state = take(client.events,'state')
        assert state['session'] == host.session and state['revision'] == 4
        request_id = client.send_move((0,3),(0,4),4,2)
        request = take(host.events,'request')
        assert request['generation'] == first
        assert request['packet']['request_id'] == request_id and request['packet']['epoch'] == 2
        # A second peer cannot replace the current Black player's authority.
        other = LocalRoomClient(host.code,tmp_path)
        assert take(other.events,'rejected')['reason'] == 'ROOM_OCCUPIED'
        client.close()
        until(lambda: not host.connected)
        other.close()
        other = LocalRoomClient(host.code,tmp_path)
        until(lambda: other.connected and host.connected)
        assert other.generation != first
        assert take(other.events,'state')['revision'] == 4
        assert json.loads(host.path.read_text())['port'] == host.port
    finally:
        client.close()
        if other: other.close()
        host.close()
    assert not host.path.exists() and not host._acceptor.is_alive()
    assert all(not t.is_alive() for t in host._threads)


def test_close_retires_unauthenticated_peer_without_lingering_thread(tmp_path):
    host = LocalRoomHost(tmp_path)
    sock = socket.create_connection(('127.0.0.1',host.port),timeout=1)
    try:
        until(lambda: len(host._threads) == 1)
        host.close()
        assert all(not t.is_alive() for t in host._threads)
    finally:
        sock.close()
        host.close()


def test_room_parser_rejects_oversized_or_non_object_frames():
    import threading
    for payload in [b'[]\n', b'x'*(MAX_FRAME+1)]:
        reader, writer = socket.socketpair()
        try:
            writer.sendall(payload)
            writer.shutdown(socket.SHUT_WR)
            with pytest.raises(ValueError):
                list(_messages(reader,threading.Event()))
        finally:
            reader.close(); writer.close()


def state_packet(**kwargs):
    return dict(type='state',session='room',board=xiangqi.get_board(),turn='b',revision=1,
                epoch=4,busy=False,blocked=None,game_over=False,**kwargs)


def test_client_only_adopts_authoritative_state_and_disables_stale_or_disconnected_input():
    model = ClientBoard()
    model.receive(dict(type='welcome', session='room'))
    model.receive(state_packet())
    assert model.can_move(True)
    before = [row[:] for row in model.board]
    model.pending = 'request'
    model.receive(dict(type='move_result',request_id='request',accepted=True,reason='queued'))
    assert model.board == before and not model.can_move(True)  # No optimistic commit.
    model.receive(dict(type='move_finished',request_id='request',reason='cancelled'))
    assert model.can_move(True)
    model.seen_at = time.monotonic()-3
    assert not model.can_move(True)
    model.receive(dict(type='disconnected'))
    assert model.board is None and not model.can_move(True)


def test_client_ignores_wrong_session_stale_state_and_malformed_board():
    model = ClientBoard()
    model.receive(dict(type='welcome',session='room'))
    model.receive(state_packet())
    packet = state_packet()
    packet['board'][0][0] = {}
    model.receive(packet)
    assert model.board[0][0] == 'b_R'
    packet = state_packet()
    packet['session'] = 'wrong'
    packet['turn'] = 'r'
    model.receive(packet)
    assert model.snapshot['turn'] == 'b'
    packet = state_packet()
    packet['revision'] = 0
    model.receive(packet)
    assert model.snapshot['revision'] == 1


@pytest.mark.serial
def test_black_pygame_clicks_send_logical_cells_and_heartbeat_keeps_selection(monkeypatch):
    import pygame
    from types import SimpleNamespace
    from unittest.mock import Mock
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    app = ClientApp()
    app.client = SimpleNamespace(connected=True,events=queue.Queue(),send_move=Mock(return_value='id'),close=Mock())
    try:
        app.model.receive(dict(type='welcome',session='room'))
        app.model.receive(state_packet())
        def click(cell):
            c,r = view_cell(cell)
            app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                pos=(app.origin[0]+c*app.grid,app.origin[1]+r*app.grid),button=1))
        click((0,3))
        assert app.selected == (0,3)
        app.client.events.put(state_packet())
        app.poll()
        assert app.selected == (0,3)  # Heartbeat must not deselect before the destination click.
        changed = state_packet()
        changed['revision'] = 2
        app.client.events.put(changed)
        app.poll()
        assert app.selected is None
        click((0,3))
        click((0,4))
        app.client.send_move.assert_called_once_with((0,3),(0,4),2,4)
        assert app.model.board[3][0] == 'b_P' and app.model.board[4][0] == '.'
        assert app.model.pending == 'id'
        app.draw()
        assert view_cell(view_cell((2,8))) == (2,8)
    finally:
        app.close()
