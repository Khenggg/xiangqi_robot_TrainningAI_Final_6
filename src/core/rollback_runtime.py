"""Application binding for the physical rollback ledger and durable worker.

The main chess position remains committed S2 while the coordinator manipulates
checkpoint boards. Only its final verified commit callback can install S0.
"""
from copy import deepcopy
import time
from functools import wraps
from threading import RLock
import config

from src.core.rollback_cycle import CycleRecord, MoveRecord, StateSnapshot
from src.core.rollback_journal import RollbackJournal
from src.core.fen_utils import board_array_to_fen


def _validate_fen(snapshot):
    data = snapshot.to_dict()
    if snapshot.current_fen != board_array_to_fen(snapshot.board, snapshot.turn, data['move_number']):
        raise ValueError('FEN trong journal không khớp board/lượt/bộ đếm')


def _cell(square):
    return f'{chr(97 + square[0])}{square[1]}'


def _piece(piece):
    names = {'P': 'Tốt', 'R': 'Xe', 'N': 'Mã', 'H': 'Mã', 'C': 'Pháo',
             'A': 'Sĩ', 'B': 'Tượng', 'E': 'Tượng', 'K': 'Tướng'}
    return names.get(piece[-1:], piece) + (' Đỏ' if piece.startswith('r_') else ' Đen')


def _serialized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


class _TransactionJournal:
    def __init__(self, runtime):
        self.runtime = runtime

    def save(self, record):
        with self.runtime._lock:
            self.runtime._coordinator_record = deepcopy(record)
            self.runtime.persist()


class RollbackRuntime:
    def __init__(self, state):
        self._lock = RLock()
        self.state, self.hw = state, None
        self.cycle = self.coordinator = self.journal = None
        self.audit, self.move_audit = [], []
        self.revision = 0
        self.applied_commits, self.queued_commits = set(), set()
        self.pending_sync = {}
        self._last_sync_retry = 0.0
        self.recovery_error = ''
        self.restart_pending = False
        self.needs_seal = False
        self.session_closed = False
        self._coordinator_record = None
        self.scope = None

    @property
    def blocked(self):
        return bool(self.recovery_error or self.restart_pending or self.needs_seal or self.pending_sync or
                    (self.coordinator is not None and self.coordinator.active))

    @property
    def preserve_room(self):
        return self.blocked

    def attach_hardware(self, hw):
        self.hw = hw
        if self.coordinator is not None:
            self.coordinator.hw = hw

    def configure(self, path):
        """Restore committed state, but never start motion or create a room."""
        self.journal = RollbackJournal(path)
        self.scope = self.state.api_client._outbox_scope()
        try:
            saved = self.journal.load()
            if saved is None:
                return False
            if saved.get('version') != 1 or saved.get('scope') != self.scope:
                raise ValueError('Journal khác tài khoản/schema; giữ nguyên file để phục hồi')
            snapshot = StateSnapshot.from_dict(saved['committed_snapshot'])
            cycle = CycleRecord.from_dict(saved['cycle']) if saved.get('cycle') else None
            for item in (snapshot, cycle.s0 if cycle else None, cycle.s1 if cycle else None,
                         cycle.s2 if cycle else None):
                if item is not None:
                    _validate_fen(item)
            # Validate all data before replacing any live state.
            revision = int(saved['revision'])
            audit, moves = saved.get('audit', []), saved.get('move_audit', [])
            if not isinstance(audit, list) or not isinstance(moves, list):
                raise ValueError('Journal audit không hợp lệ')
            applied = saved.get('applied_commits', [])
            queued = saved.get('queued_commits', [])
            pending_sync = saved.get('pending_sync', {})
            if (any(not isinstance(items, list) or any(not isinstance(i, str) for i in items)
                    for items in (applied, queued)) or not isinstance(pending_sync, dict)
                    or not isinstance(saved.get('needs_seal', False), bool)
                    or type(saved.get('session_closed', False)) is not bool
                    or isinstance(saved['revision'], bool) or revision < 0
                    or not set(queued).issubset(set(applied))):
                raise ValueError('Journal commit metadata không hợp lệ')
            for key, value in pending_sync.items():
                if (key not in applied or not isinstance(value, dict)
                        or not isinstance(value.get('fen'), str)
                        or type(value.get('revision')) is not int
                        or value['revision'] < 0
                        or not isinstance(value.get('room_id'), (str, int, type(None)))):
                    raise ValueError('Journal FEN pending không hợp lệ')
                if (value['fen'] != snapshot.current_fen or value['revision'] != revision
                        or value['room_id'] != saved.get('room_id')):
                    raise ValueError('FEN pending không khớp committed authority')
            record = saved.get('coordinator')
            coordinator = None
            if record:
                if record.get('scope') != self.scope:
                    raise ValueError('Transaction khác account scope')
                from src.core.rollback_coordinator import RollbackCoordinator
                coordinator = RollbackCoordinator.restore(record, self.hw,
                    _TransactionJournal(self), commit=self._commit,
                    baseline=self._baseline, notify=self._notify)
                if cycle is None or cycle.cycle_id != coordinator.cycle.cycle_id:
                    raise ValueError('Transaction không khớp latest cycle')
                outer, inner = cycle.to_dict(), coordinator.cycle.to_dict()
                if any(outer[key] != inner[key] for key in outer if key != 'status'):
                    raise ValueError('Transaction thay đổi snapshot/epoch của latest cycle')
                locally_applied = coordinator.commit_id in applied
                if coordinator.committed and not locally_applied:
                    raise ValueError('Thiếu local commit marker')
                if locally_applied and not coordinator.commit_intent:
                    raise ValueError('Local commit thiếu intent')
                if pending_sync and set(pending_sync) != {coordinator.commit_id}:
                    raise ValueError('Pending FEN không thuộc transaction hiện tại')
                expected = coordinator.cycle.s0 if locally_applied else coordinator.cycle.s2
                keys = ('board', 'turn', 'current_fen', 'move_number', 'move_history',
                        'move_log', 'r_captured', 'b_captured', 'last_move')
                if any(snapshot.to_dict()[key] != expected.to_dict()[key] for key in keys):
                    raise ValueError('Committed snapshot không khớp marker S0/S2')
            if saved.get('session_closed') is True:
                if pending_sync or (coordinator and coordinator.active):
                    raise ValueError('Session đóng khi transaction chưa hoàn tất')
                self.audit = audit
                # Keep archived evidence, but never resurrect a closed room or
                # carry that game's move feed/rollback authority into New Game.
                return False
            snapshot.apply_to(self.state)
            self.cycle, self.coordinator = cycle, coordinator
            self.revision, self.audit, self.move_audit = revision, audit, moves
            self.applied_commits, self.queued_commits = set(applied), set(queued)
            self.pending_sync = pending_sync
            self.needs_seal = bool(saved.get('needs_seal', False))
            self._coordinator_record = record
            self.state.api_client.room_id = saved.get('room_id')
            self._cancel_ai()
            self.restart_pending = True
            self.state.manual_override_active = True
            self.state.set_status('Phục hồi journal: chưa chạy arm. V đối soát; nếu có motion dở, '
                                  'đưa arm về nghỉ/kẹp rỗng rồi E xác nhận.', duration=3600)
            return True
        except Exception as exc:
            self.recovery_error = str(exc)
            self.state.set_status(f'Khóa phục hồi rollback: {exc}. Giữ journal để kiểm tra.', duration=3600)
            return False

    @_serialized
    def persist(self):
        if self.journal is None:
            return
        try:
            self.journal.save(dict(version=1, scope=self.scope,
                room_id=self.state.api_client.room_id,
                committed_snapshot=StateSnapshot.from_state(self.state).to_dict(),
                cycle=self.cycle.to_dict() if self.cycle else None,
                coordinator=self._coordinator_record, revision=self.revision,
                audit=self.audit, move_audit=self.move_audit,
                pending_sync=self.pending_sync,
                needs_seal=self.needs_seal,
                session_closed=self.session_closed,
                applied_commits=sorted(self.applied_commits), queued_commits=sorted(self.queued_commits)))
        except Exception as exc:
            self.recovery_error = str(exc)
            self.state.set_status(f'Không lưu được journal; khóa thao tác: {exc}', duration=3600)
            raise

    @_serialized
    def _record(self, event, **details):
        self.audit.append(dict(event=event, at=time.time(), revision=self.revision, **details))

    def invalidate(self, reason):
        if self.cycle is not None:
            self.cycle.invalidate()
        self._record('invalidated', reason=reason)

    @_serialized
    def human_committed(self, before, src, dst, piece, victim, *, eligible=True):
        self.invalidate('new_human_move' if eligible else 'operator_edit')
        self.revision += 1
        self.coordinator, self._coordinator_record = None, None
        entry = dict(turn='r', src=tuple(src), dst=tuple(dst), piece=piece,
                     revision=self.revision, rolled_back=False)
        self.move_audit.append(entry)
        if eligible:
            self.cycle = CycleRecord.start(before, StateSnapshot.from_state(self.state),
                MoveRecord('r', src, dst, piece, victim, True),
                self.state.game_epoch, self.revision)
        else:
            self.cycle = None
        self.persist()

    @_serialized
    def black_committed(self, src, dst, piece, victim):
        self.revision += 1
        self.move_audit.append(dict(turn='b', src=tuple(src), dst=tuple(dst), piece=piece,
                                    revision=self.revision, rolled_back=False))
        cycle = self.cycle
        if cycle is not None and cycle.status == 'BUILDING' and cycle.s2 is None:
            cycle.complete(StateSnapshot.from_state(self.state),
                           MoveRecord('b', src, dst, piece, victim, True))
            self.needs_seal = callable(getattr(self.hw, 'verify_rollback_board', None))
        self.persist()

    def eligibility(self, *, worker_owned=False):
        state = self.state
        if self.blocked:
            return False, 'Đang rollback/phục hồi — V quét lại, E xác nhận kẹp rỗng, X hủy khi bàn S2'
        if state.game_over:
            return False, 'Không rollback trận đã kết thúc'
        if any((getattr(state, 'physical_motion_busy', False) and not worker_owned, state.ai_thinking,
                state.pending_ai_move is not None, state.physical_sync_fault,
                state.visual_pick_retry is not None, state.pick_test_mode,
                state.pick_test_resume_required, state.emergency_mode,
                state.snapshot_continue_required)):
            return False, 'Chờ arm, AI và đối soát/baseline hoàn tất'
        cycle = self.cycle
        if cycle is None or cycle.status != 'READY':
            return False, 'Chỉ mở Z sau một cycle Đỏ–Đen đã xác minh'
        if cycle.game_epoch != state.game_epoch or state.turn != 'r' or (
                cycle.s2.board != tuple(tuple(row) for row in state.board)):
            return False, 'Cycle cũ không còn khớp state hiện tại'
        return True, 'Z: hoàn tác cycle Đỏ–Đen gần nhất'

    def seal(self, *, baseline_ready=False):
        cycle = self.cycle
        if (cycle is None or cycle.status != 'BUILDING' or cycle.s2 is None
                or self.state.game_over or self.hw is None):
            return False
        try:
            proof = self.hw.verify_rollback_board(self.state.board)
            safety = self.hw.robot.verify_rollback_ready()
            if not (isinstance(proof, dict) and proof.get('matched') is True
                    and proof.get('complete') is True and isinstance(safety, dict)
                    and safety.get('ready') is True and baseline_ready):
                self.state.set_status('Cycle đã đi xong nhưng chưa đủ proof bàn/arm/baseline; '
                                      'Z đang khóa. V để đối soát lại.', duration=3600)
                return False
            cycle.seal(arm_parked=True, controller_idle=True, board_verified=True,
                       baseline_ready=True, no_fault=not self.state.physical_sync_fault)
            self.needs_seal = False
            self.state.snapshot_continue_required = False
            self.state.manual_override_active = False
            self._record('cycle_ready', cycle_id=cycle.cycle_id)
            self.persist()
            return True
        except Exception as exc:
            self.state.set_status(f'Z chưa sẵn sàng: {exc}. V để đối soát lại.', duration=3600)
            return False

    def _cancel_ai(self):
        state = self.state
        state.ai_epoch += 1
        state.ai_job_token, state.ai_result, state.ai_failure = None, None, None
        state.ai_results = {}
        state.ai_thinking = False
        state.ai_retry_requested = False
        state.ai_started_for_human_commit_generation = state.human_commit_generation
        state.selected_pos = None

    def start(self, *, worker_owned=False):
        allowed, reason = self.eligibility(worker_owned=worker_owned)
        if not allowed:
            self.state.set_status(reason, duration=15)
            return False
        if self.journal is None:
            self.state.set_status('Chưa cấu hình durable rollback journal; không chạy arm.', duration=30)
            return False
        from src.core.rollback_coordinator import RollbackCoordinator
        # Coordinator retains its immutable authority even when runtime consumes
        # the ledger after the final local commit.
        cycle = CycleRecord.from_dict(self.cycle.to_dict())
        self.coordinator = RollbackCoordinator(cycle, self.hw, _TransactionJournal(self),
            commit=self._commit, baseline=self._baseline, notify=self._notify, scope=self.scope)
        self._cancel_ai()
        self.state.manual_override_active = True
        self._record('requested', cycle_id=cycle.cycle_id)
        self._coordinator_record = self.coordinator.record()
        self.persist()
        self.coordinator.start()
        self._after_operation()
        return True

    def resume(self, *, empty_gripper_confirmed=False, abort=False):
        if self.recovery_error:
            self.state.set_status(f'Journal đang lỗi: {self.recovery_error}; chưa được chạy arm.', duration=3600)
            return False
        self.retry_pending_sync(force=True)
        if self.coordinator is not None and self.coordinator.active:
            if abort:
                self.coordinator.abort(operator_empty_gripper_confirmed=empty_gripper_confirmed)
            else:
                self.coordinator.resume(operator_empty_gripper_confirmed=empty_gripper_confirmed)
            self._after_operation()
            return not self.blocked
        if self.restart_pending:
            if self.hw is None:
                return False
            safety = self.hw.robot.verify_rollback_ready(
                operator_empty_gripper_confirmed=empty_gripper_confirmed, uncertain_recovery=True)
            proof = self.hw.verify_rollback_board(self.state.board)
            if not (safety.get('ready') is True and proof.get('matched') is True
                    and proof.get('complete') is True and self._baseline()):
                self.state.set_status('Phục hồi chưa khớp bàn/arm/kẹp rỗng. Kiểm tra rồi E để xác nhận.', duration=3600)
                return False
            self.restart_pending = False
            self.state.manual_override_active = False
            self.state.physical_sync_fault = False
            if self.state.turn == 'b':
                self.state.prepare_ai_retry_after_physical_miss()
            self.persist()
        if self.cycle and self.cycle.status == 'BUILDING' and self.cycle.s2:
            return self.seal(baseline_ready=self._baseline())
        return not self.blocked

    def _baseline(self):
        return bool(self.hw and self.hw.capture_baseline_if_needed(force_delay=0.0))

    @_serialized
    def _commit(self, snapshot, commit_id):
        _validate_fen(snapshot)
        if commit_id not in self.applied_commits:
            state = self.state
            epoch, ai_epoch = state.game_epoch, state.ai_epoch
            snapshot.apply_to(state)
            state.game_epoch, state.ai_epoch = epoch + 1, ai_epoch + 1
            state.clear_pending_ai_move()
            self._cancel_ai()
            self.revision += 1
            for entry in self.move_audit[-2:]:
                entry['rolled_back'] = True
            if self.cycle and self.cycle.status == 'READY':
                self.cycle.consume()
            self.applied_commits.add(commit_id)
            self.pending_sync[commit_id] = dict(fen=snapshot.current_fen,
                revision=self.revision, room_id=self.state.api_client.room_id)
            self._record('committed_s0', commit_id=commit_id)
            self.persist()
        self.retry_pending_sync(force=True)

    @_serialized
    def retry_pending_sync(self, *, force=False):
        if not self.pending_sync or self.recovery_error:
            return
        now = time.monotonic()
        if not force and now - self._last_sync_retry < 2.0:
            return
        self._last_sync_retry = now
        for commit_id, payload in list(self.pending_sync.items()):
            try:
                persisted = (True if config.DRY_RUN else
                    self.state.api_client.queue_fen_commit(payload['fen'], commit_id,
                        payload['revision'], room_id=payload['room_id']))
                if persisted is True:
                    self.queued_commits.add(commit_id)
                    del self.pending_sync[commit_id]
                    self.persist()
            except Exception:
                # This is remote-data recovery, never a reason to replay arm.
                self.state.set_status('Bàn/FEN local đã rollback; FEN từ journal còn chờ '
                                      'lưu vào outbox để đồng bộ máy chủ.', duration=3600)

    def _notify(self, phase, details):
        self._record(phase, **{k: v for k, v in details.items() if k != 'verification'})
        phrases = {'PREFLIGHT': 'Đang xác minh toàn bàn trước rollback',
                   'VERIFY_CHECKPOINT': 'Đã xác minh checkpoint rollback',
                   'FINAL_VERIFY': 'Đang xác minh toàn bàn S0',
                   'COMMIT_S0': 'Bàn S0 đúng — đang đồng bộ FEN',
                   'COMMITTED_WAIT_BASELINE': 'FEN đã rollback; đang chờ baseline mới',
                   'DONE': 'Rollback xong — đã đồng bộ bàn/FEN, đến lượt Đỏ',
                   'ABORTED_VERIFIED': 'Đã xác minh bàn S2 và hủy rollback'}
        message = phrases.get(phase, phase)
        if phase == 'TRANSFER':
            message = 'Đang đưa quân ' + ('Đỏ' if details.get('side') == 'r' else 'Đen') + ' về'
            if self.coordinator and self.coordinator.plan.transfers[0].side == 'b':
                message += ' (Đen trước: chặn ô cũ Đỏ hoặc quân Đỏ đã bị ăn)'
        if phase == 'WAIT_PLAYER':
            items = self.coordinator.plan.restorations
            message = 'Đặt lại: ' + '; '.join(f'{_piece(r.piece)} tại {_cell(r.square)}' for r in items)
            message += '. Rút tay, SPACE/V để quét lại.'
        if self.coordinator and self.coordinator.error:
            message += ' | ' + self.coordinator.error
        report = details.get('verification', self.coordinator.verification if self.coordinator else {})
        if report.get('errors'):
            message += ' | ' + '; '.join(map(str, report['errors'][:3]))
        if phase in ('PAUSED_FAULT', 'RECOVERY_REQUIRED'):
            message += '. V đối soát; sau khi arm về nghỉ và kẹp rỗng, E xác nhận để tiếp tục; X hủy khi bàn S2.'
        self.state.set_status(message, color=(0, 120, 0) if phase == 'DONE' else (180, 100, 0), duration=3600)

    def _after_operation(self):
        coordinator = self.coordinator
        if coordinator and not coordinator.active:
            self.restart_pending = False
            self.state.manual_override_active = False
            self.state.physical_sync_fault = False
            self.state.snapshot_continue_required = False
            self._record('operation_finished', phase=coordinator.phase)
        self.persist()

    def reset(self):
        if self.blocked:
            raise RuntimeError('Không New Game khi rollback chưa hoàn tất')
        self._record('game_archived', moves=deepcopy(self.move_audit))
        self.move_audit = []
        self.cycle, self.coordinator, self._coordinator_record = None, None, None
        self.needs_seal = False
        self.session_closed = False
        self.revision += 1
        self._record('new_game')
        self.persist()

    @_serialized
    def new_session(self):
        if self.blocked:
            raise RuntimeError('Không thay session khi recovery đang khóa')
        self.session_closed = False
        self._record('session_started')
        self.persist()

    @_serialized
    def close_session(self):
        if self.preserve_room:
            return False
        self.session_closed = True
        self.invalidate('session_closed')
        self._record('session_closed', moves=deepcopy(self.move_audit))
        self.persist()
        return True

    def render_state(self):
        enabled, reason = self.eligibility()
        coordinator = self.coordinator
        return dict(rollback_enabled=enabled, rollback_reason=reason,
            rollback_active=self.blocked,
            rollback_phase=coordinator.phase if coordinator else '',
            rollback_restorations=([dict(square=r.square, piece=r.piece)
                for r in coordinator.plan.restorations] if coordinator and coordinator.active else []),
            rollback_target=(self.cycle.s0.board if coordinator and coordinator.active and self.cycle else None),
            rollback_target_cells=([dict(square=(c, r), piece=piece)
                for r, row in enumerate(self.cycle.s0.board) for c, piece in enumerate(row)
                if piece != '.' and piece != self.cycle.s2.board[r][c]]
                if coordinator and coordinator.active and self.cycle and self.cycle.s2 else []),
            rollback_transfer=(dict(src=coordinator.plan.transfers[coordinator.next_transfer].src,
                                    dst=coordinator.plan.transfers[coordinator.next_transfer].dst)
                if coordinator and coordinator.active and coordinator.next_transfer < len(coordinator.plan.transfers) else None))
