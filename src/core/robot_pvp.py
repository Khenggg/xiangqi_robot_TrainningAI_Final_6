"""Two GUI players, one retained execution/journal owner; no AI or RPC here."""
import json
import logging
import queue
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from src.core import xiangqi
from src.core.ai_execution import execute_ai_move
from src.core.pvp_room import LocalRoomHost
from src.core.project_logging import event

ROBOT_PVP_MODE = 'HUMAN_VS_HUMAN_ROBOT'


def _cell(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(v) is not int for v in value)):
        return None
    col, row = value
    return (col, row) if 0 <= col < 9 and 0 <= row < 10 else None


class RobotPvPController:
    def __init__(self, state, hardware, room=None):
        if hardware.profile.game_mode != ROBOT_PVP_MODE:
            raise ValueError('Robot PvP requires its dedicated session profile')
        self.state, self.hw = state, hardware
        self.room = room if room is not None else LocalRoomHost()
        self._closed = self._busy = False
        self._seen = set()
        self._last_snapshot = None
        self._published_at = 0
        self._child = None
        self._selected_token = None
        self.publish(force=True)

    def _blocked(self, *, in_worker=False):
        s, hw = self.state, self.hw
        if self._closed or getattr(hw, '_closing', False):
            return "Session is closing"
        control = getattr(hw, 'session_control', None)
        if control is not None and control.action is not None:
            return "Stopping/switching session; finish the current request first"
        if (s.recovery_required or s.mode_change_pending or s.physical_sync_fault
                or s.move_sync_error or s.snapshot_continue_required
                or s.manual_override_active or s.turn_confirmation_required):
            return "Session needs recovery; V to reconcile and check the robot"
        if s.game_over:
            return "Game is over"
        if (s.pending_move is not None or s.pending_ai_move is not None
                or s.pending_test_motion is not None or s.visual_pick_retry
                or s.pick_test_mode or s.pick_test_resume_required):
            return "A move/test is still pending; no new move accepted"
        if s.ai_thinking or (not in_worker and (self._busy or hw.motion_worker.busy)):
            return "Move in progress"
        stop = getattr(hw, 'stop_coordinator', None)
        if stop is not None and stop.blocked:
            return "Robot is stopping; recovery required first"
        if not hw.is_robot_ready:
            return "Robot is not ready yet; the host is enabling it automatically"
        return None

    def _reply(self, request_id, accepted, reason):
        packet = dict(type='move_result', request_id=request_id, accepted=accepted, reason=reason)
        self.room.send(packet)
        if not accepted:
            self.state.set_status(reason, duration=15)
        return accepted

    def submit(self, side, src, dst, *, request_id=None, revision=None, epoch=None, generation=None):
        """Admit once, then revalidate in MotionWorker immediately before execution."""
        request_id = request_id or uuid4().hex
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
            return False
        if request_id in self._seen:
            return self._reply(request_id, False, "Request already handled; do not repeat the command")
        if len(self._seen) >= 10000:
            return self._reply(request_id, False, "Room reached its request limit; create a new session")
        self._seen.add(request_id)
        src, dst = _cell(src), _cell(dst)
        reason = self._blocked()
        if side not in {'r', 'b'} or side != self.state.turn:
            reason = "Not your turn yet"
        if (type(revision) is not int or revision != self.state.board_revision
                or type(epoch) is not int or epoch != self.state.game_epoch):
            reason = "Board changed; wait for the new host state"
        if (not self.room.connected or (side == 'b' and generation != self.room.generation)):
            reason = "Black player not connected or the connection changed"
        if src is None or dst is None:
            reason = "Invalid square"
        if reason is None and not xiangqi.is_valid_move(src, dst, self.state.board, side):
            reason = "Invalid move"
        if reason:
            return self._reply(request_id, False, reason)
        token = (self.state.game_epoch, self.state.board_revision, self.state.turn, self.room.generation)
        stop = getattr(self.hw, 'stop_coordinator', None)
        stop_generation = stop.generation if stop is not None else None
        self._busy = True

        def operation():
            current = (self.state.game_epoch, self.state.board_revision, self.state.turn, self.room.generation)
            if (self._blocked(in_worker=True) or token != current or not self.room.connected
                    or (stop is not None and stop.generation != stop_generation)):
                return False  # No pending transaction or actuator command created.
            committed = execute_ai_move(self.state, self.hw, (src, dst), self.hw.dry_run, True)
            if committed:
                try:
                    self._after_commit()  # Camera/API work stays off the GUI thread.
                except Exception as exc:
                    self.state.manual_override_active = self.state.snapshot_continue_required = True
                    event('pvp.post_commit_failed', str(exc), level=logging.WARNING, board_revision=self.state.board_revision)
                    self.state.set_status(f'Move committed; post-move update failed: {exc}', duration=30)
            return committed

        def completed(committed, error):
            self._busy = False
            self.room.send(dict(type='move_finished', request_id=request_id, committed=bool(committed),
                                reason="Move confirmed" if committed else "Move not finished; check the host state"))
            if error:
                self.state.set_status(f'Move stopped: {error}; check the state before retrying.', duration=30)
            elif not committed and not self.state.visual_pick_retry and not self.state.physical_sync_fault:
                self.state.set_status("Request cancelled before running; choose again after checking the connection.", duration=20)
            self.publish(force=True)

        if not self.hw.motion_worker.start(operation, completed):
            self._busy = False
            return self._reply(request_id, False, "Robot is busy; choose again when ready")
        self.state.selected_pos = None
        self._reply(request_id, True, "Accepted; the turn changes only when execution is confirmed")
        self.publish(force=True)
        return True

    def _after_commit(self):
        s = self.state
        if xiangqi.get_king_pos(s.turn, s.board) is None or not xiangqi.find_all_valid_moves(s.turn, s.board):
            s.handle_game_over('b' if s.turn == 'r' else 'r', reason='CHECKMATE')
        s.publish_committed_fen()
        if s.game_over:
            s.publish_match_end(winner='RED' if s.winner == 'r' else 'BLACK', reason=s.game_over_reason or 'CHECKMATE')
        # Each new physical turn needs a verified baseline, without granting a move.
        if not self.hw.dry_run:
            try:
                captured = self.hw.capture_baseline_if_needed(force_delay=0)
            except Exception as exc:
                event('camera.baseline_rejected', str(exc), level=logging.WARNING,
                      code='CAMERA_VERIFY_FAILED', operation='ROBOT_PVP_POST_COMMIT')
                captured = False
            if not captured:
                s.manual_override_active = s.snapshot_continue_required = True
                s.set_status("Move committed; baseline not ready. V to reconcile before the next turn.", duration=30)

    def handle_click(self, col, row):
        cell = _cell((col, row))
        if cell is None:
            return False
        reason = self._blocked()
        if reason or self.state.turn != 'r' or not self.room.connected:
            self.state.set_status(reason or "Host selected a Red piece; waiting for Black to connect/move.", duration=15)
            return False
        piece = self.state.board[row][col]
        if piece.startswith('r'):
            self.state.selected_pos = cell
            self._selected_token = (self.state.game_epoch, self.state.board_revision,
                                    self.state.piece_ids.get((row,col)))
            return True
        source = self.state.selected_pos
        if source is None:
            return False
        current = (self.state.game_epoch, self.state.board_revision,
                   self.state.piece_ids.get((source[1],source[0])))
        if self._selected_token != current:
            self.state.selected_pos = None
            self._selected_token = None
            self.state.set_status("Board changed; select the Red piece again.", duration=15)
            return False
        return self.submit('r', source, cell, revision=self.state.board_revision, epoch=self.state.game_epoch)

    def tick(self):
        if self._closed:
            return
        for _ in range(32):
            try:
                message = self.room.events.get_nowait()
            except queue.Empty:
                break
            if message.get('type') == 'request':
                packet = message['packet']
                if (packet.get('type') != 'move' or packet.get('session') != self.room.session
                        or packet.get('generation') != message['generation']
                        or not isinstance(packet.get('request_id'), str)):
                    continue
                self.submit('b', packet.get('src'), packet.get('dst'), request_id=packet.get('request_id'),
                            revision=packet.get('revision'), epoch=packet.get('epoch'), generation=message['generation'])
            elif message.get('type') == 'disconnected':
                self.state.selected_pos = None
                self.state.set_status("Black player disconnected; no new moves accepted. Do not repeat the move in progress.", duration=30)
        self.publish()

    def publish(self, *, force=False):
        with self.state._transition_lock:
            snapshot = dict(board=[row[:] for row in self.state.board], turn=self.state.turn,
                revision=self.state.board_revision, epoch=self.state.game_epoch,
                busy=self._busy or self.hw.motion_worker.busy, blocked=self._blocked(),
                game_over=self.state.game_over, winner=self.state.winner,
                retry=bool(self.state.visual_pick_retry), status=self.state.status_message)
        signature = json.dumps(snapshot, sort_keys=True)
        now = time.monotonic()
        if force or signature != self._last_snapshot or now-self._published_at >= .5:
            self.room.publish(snapshot)
            self._last_snapshot, self._published_at = signature, now
        self.state.pvp_room = dict(code=self.room.code, connected=self.room.connected,
                                   busy=snapshot['busy'], blocked=snapshot['blocked'])

    def open_client(self):
        if self._child is None or self._child.poll() is not None:
            self._child = launch_client(self.room.code)

    def close(self):
        self._closed = True
        self.room.close()
        self.state.pvp_room = None


def launch_client(code=None):
    args = [sys.executable, '-m', 'src.ui.pvp_client']
    if code:
        args += ['--room', code]
    return subprocess.Popen(args, cwd=Path(__file__).resolve().parents[2])
