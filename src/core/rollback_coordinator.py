"""Worker-run physical rollback transaction. No UI or logical board mutation.

The injected commit callback MUST be idempotent for commit_id, including across
process restart. Motion is never retried without an explicit resume and fresh
controller, empty-jaw and whole-board evidence.
"""
from copy import deepcopy
from threading import Lock
from uuid import uuid4


class RollbackCoordinator:
    TERMINAL = frozenset({'DONE', 'ABORTED_VERIFIED'})
    PHASES = frozenset({'READY', 'PREFLIGHT', 'TRANSFER', 'VERIFY_CHECKPOINT',
        'WAIT_PLAYER', 'FINAL_VERIFY', 'COMMIT_S0', 'COMMITTED_WAIT_BASELINE',
        'DONE', 'ABORTED_VERIFIED', 'PAUSED_FAULT', 'RECOVERY_REQUIRED'})

    def __init__(self, cycle, hw, journal, *, commit, baseline, notify=None,
                 scope=None, plan=None):
        if plan is None:
            from src.core.rollback_cycle import build_inverse_plan
            plan = build_inverse_plan(cycle)
        self.cycle, self.hw, self.journal, self.plan = cycle, hw, journal, plan
        # The runtime may consume its ledger in commit(). Keep the original
        # READY authority immutable in this transaction's durable record.
        self._cycle_record = deepcopy(cycle.to_dict())
        self.commit, self.baseline, self.notify = commit, baseline, notify
        self.scope = deepcopy(scope or {})
        self.transaction_id = uuid4().hex
        self.commit_id = 'rollback:' + self.transaction_id
        self.phase, self.error = 'READY', ''
        self.next_transfer, self.in_flight = 0, None
        self.commit_intent = self.committed = False
        self.verification = {}
        self._uncertain = False
        self._lock = Lock()

    @property
    def active(self):
        return self.phase not in self.TERMINAL

    def record(self):
        return deepcopy({
            'version': 1, 'transaction_id': self.transaction_id,
            'commit_id': self.commit_id, 'cycle': self._cycle_record,
            'phase': self.phase, 'next_transfer': self.next_transfer,
            'in_flight': self.in_flight, 'commit_intent': self.commit_intent,
            'commit_applied': self.committed, 'uncertain': self._uncertain,
            'error': self.error, 'scope': self.scope,
        })

    @classmethod
    def restore(cls, record, hw, journal, *, commit, baseline, notify=None):
        from src.core.rollback_cycle import CycleRecord
        if not isinstance(record, dict) or type(record.get('version')) is not int or record['version'] != 1:
            raise ValueError('Unsupported rollback journal version')
        for marker in ('commit_intent', 'commit_applied', 'uncertain'):
            if type(record.get(marker)) is not bool:
                raise ValueError('Invalid rollback boolean marker: ' + marker)
        if (type(record.get('next_transfer')) is not int
                or (record.get('in_flight') is not None and type(record['in_flight']) is not int)
                or not isinstance(record.get('phase'), str) or record['phase'] not in cls.PHASES
                or not isinstance(record.get('error'), str)
                or not isinstance(record.get('scope'), dict)):
            raise ValueError('Invalid rollback checkpoint schema')
        transaction_id = record.get('transaction_id')
        if (not isinstance(transaction_id, str) or not transaction_id
                or len(transaction_id) > 128
                or record.get('commit_id') != 'rollback:' + transaction_id):
            raise ValueError('Invalid rollback transaction identity')
        obj = cls(CycleRecord.from_dict(record['cycle']), hw, journal,
                  commit=commit, baseline=baseline, notify=notify,
                  scope=record.get('scope'))
        obj.transaction_id, obj.commit_id = record['transaction_id'], record['commit_id']
        obj.next_transfer = record['next_transfer']
        obj.in_flight = record.get('in_flight')
        if not 0 <= obj.next_transfer <= len(obj.plan.transfers):
            raise ValueError('Invalid rollback checkpoint')
        if obj.in_flight is not None and (obj.in_flight != obj.next_transfer
                or not 0 <= obj.in_flight < len(obj.plan.transfers)):
            raise ValueError('Invalid in-flight rollback checkpoint')
        obj.commit_intent = record['commit_intent']
        obj.committed = record['commit_applied']
        if obj.committed and not obj.commit_intent:
            raise ValueError('Commit marker without intent')
        obj.error = record['error']
        previous = record['phase']
        complete = obj.next_transfer == len(obj.plan.transfers) and obj.in_flight is None
        if obj.commit_intent and not complete:
            raise ValueError('Commit intent before all transfers were verified')
        if obj.committed and previous not in ('COMMITTED_WAIT_BASELINE', 'DONE'):
            raise ValueError('Applied commit in pre-commit phase')
        if obj.commit_intent and not obj.committed and previous not in (
                'COMMIT_S0', 'PAUSED_FAULT', 'RECOVERY_REQUIRED'):
            raise ValueError('Intent marker in inconsistent phase')
        if obj.in_flight is not None and (previous not in (
                'TRANSFER', 'PAUSED_FAULT', 'RECOVERY_REQUIRED') or not record['uncertain']):
            raise ValueError('In-flight motion without uncertainty/recovery phase')
        if previous in ('DONE', 'COMMITTED_WAIT_BASELINE') and not obj.committed:
            raise ValueError('Committed phase without applied commit')
        if previous == 'COMMIT_S0' and not obj.commit_intent:
            raise ValueError('Commit phase without intent')
        if previous in ('WAIT_PLAYER', 'FINAL_VERIFY') and (not complete or obj.commit_intent):
            raise ValueError('Invalid final verification checkpoint')
        if previous == 'TRANSFER' and obj.in_flight is None:
            raise ValueError('Transfer phase without durable started checkpoint')
        if previous == 'READY' and (obj.next_transfer or obj.in_flight is not None or obj.commit_intent):
            raise ValueError('READY transaction already has progress')
        if previous == 'ABORTED_VERIFIED' and (obj.commit_intent or obj.in_flight is not None or obj.next_transfer):
            raise ValueError('Invalid verified-abort checkpoint')
        obj.phase = (previous if previous in cls.TERMINAL else
                     'COMMITTED_WAIT_BASELINE' if obj.committed else 'RECOVERY_REQUIRED')
        obj._uncertain = obj.phase not in cls.TERMINAL
        return obj

    def _save(self, phase=None, **details):
        if phase:
            self.phase = phase
        self.journal.save(self.record())
        if self.notify:
            # UI reporting must not turn a verified operation into an arm retry.
            try:
                self.notify(self.phase, deepcopy(details))
            except Exception:
                pass

    def _safe(self, confirmed=False, recovery=False):
        if recovery and not confirmed:
            raise RuntimeError('Recovery requires operator confirmation of empty gripper')
        result = self.hw.robot.verify_rollback_ready(
            operator_empty_gripper_confirmed=confirmed, uncertain_recovery=recovery)
        if not isinstance(result, dict) or not result.get('ready'):
            raise RuntimeError('Controller/park/gripper not verified: ' + str(result))

    def _proof(self, board, missing=()):
        self.verification = self.hw.verify_rollback_board(
            board, allowed_missing_cells=tuple(missing), min_samples=3, stable_seconds=1.)
        return (isinstance(self.verification, dict)
                and self.verification.get('matched') is True)

    def _exact(self, board):
        return self._proof(board) and self.verification.get('complete') is True

    def start(self):
        if self.phase != 'READY':
            return self.phase
        return self._run(False)

    def resume(self, operator_empty_gripper_confirmed=False):
        return self._run(operator_empty_gripper_confirmed)

    def _run(self, confirmed):
        if not self._lock.acquire(blocking=False):
            return self.phase
        try:
            if self.phase in self.TERMINAL:
                return self.phase
            recovery = self._uncertain or self.phase == 'RECOVERY_REQUIRED'
            self._safe(confirmed, recovery)
            if self.committed:
                return self._finish_baseline()
            if self.in_flight is not None:
                transfer = self.plan.transfers[self.in_flight]
                if self._exact(transfer.after):
                    self.next_transfer += 1
                    self.in_flight = None
                    self._save('VERIFY_CHECKPOINT', recovered='after')
                elif self._exact(transfer.before):
                    self.in_flight = None
                    self._save('VERIFY_CHECKPOINT', recovered='before')
                else:
                    raise RuntimeError('Board matches neither checkpoint; manual recovery required')
            self._uncertain = False
            expected = (self.plan.transfers[self.next_transfer].before
                        if self.next_transfer < len(self.plan.transfers)
                        else self.plan.after_arm)
            # Once arm work is complete, valid manual restoration subsets must
            # survive a resume. Never compare that board against bare after_arm.
            if self.next_transfer < len(self.plan.transfers):
                self._save('PREFLIGHT')
                if not self._exact(expected):
                    raise RuntimeError('Full board does not match rollback checkpoint')
            elif self.next_transfer == 0 and not self._exact(self.cycle.s2.board):
                raise RuntimeError('Full board does not match S2')
            while self.next_transfer < len(self.plan.transfers):
                transfer = self.plan.transfers[self.next_transfer]
                self._safe()
                if not self._exact(transfer.before):
                    raise RuntimeError('Source identity/destination occupancy checkpoint mismatch')
                from src.vision.pick_consensus import require_pick_target
                targets = self.hw.get_robot_center_pick_targets({'moving': transfer.src})
                target = require_pick_target(self.hw, targets, 'moving', 'rollback_pre_pick')
                # Persist BEFORE sending any RPC, not after its acknowledgement.
                self.in_flight = self.next_transfer
                self._uncertain = True
                self._save('TRANSFER', index=self.next_transfer, side=transfer.side)
                self.hw.robot.move_piece(*transfer.src, *transfer.dst, False,
                                         moving_visual_target=target,
                                         require_visual_target=True)
                self._safe()
                if not self._exact(transfer.after):
                    raise RuntimeError('Post-transfer whole-board proof failed')
                self.next_transfer += 1
                self.in_flight, self._uncertain = None, False
                self._save('VERIFY_CHECKPOINT', index=self.next_transfer)
            self._safe()
            missing = [r.square for r in self.plan.restorations]
            if missing:
                self._save('WAIT_PLAYER', restorations=[
                    {'square': r.square, 'piece': r.piece} for r in self.plan.restorations])
                if not self._proof(self.plan.target, missing):
                    self.error = 'Manual restoration mismatch or recognition unverified'
                    self._save('WAIT_PLAYER', verification=self.verification)
                    return self.phase
                if not self.verification.get('complete'):
                    self.error = 'Waiting for captured pieces to be restored'
                    self._save('WAIT_PLAYER', verification=self.verification)
                    return self.phase
            self._save('FINAL_VERIFY')
            if not self._exact(self.cycle.s0.board):
                raise RuntimeError('Final S0 full-board proof failed')
            self.commit_intent = True
            self._save('COMMIT_S0')
            self.commit(self.cycle.s0, self.commit_id)
            self.committed = True
            self._save('COMMITTED_WAIT_BASELINE')
            return self._finish_baseline()
        except Exception as exc:
            self.error = str(exc)
            self.phase = 'COMMITTED_WAIT_BASELINE' if self.committed else 'PAUSED_FAULT'
            try:
                self._save()
            except Exception:
                pass  # The transaction remains paused, with gameplay locked.
            return self.phase
        finally:
            self._lock.release()

    def _finish_baseline(self):
        self.phase = 'COMMITTED_WAIT_BASELINE'
        if not self._exact(self.cycle.s0.board):
            self.error = 'Committed S0 board no longer matches; baseline blocked'
            self._save()
            return self.phase
        if not self.baseline():
            self.error = 'Fresh S0 baseline not ready'
            self._save()
            return self.phase
        self.error = ''
        self._uncertain = False
        self._save('DONE')
        return self.phase

    def abort(self, operator_empty_gripper_confirmed=False):
        if not self._lock.acquire(blocking=False):
            return self.phase
        try:
            if self.committed or self.commit_intent or self.phase in self.TERMINAL:
                return self.phase
            self._safe(operator_empty_gripper_confirmed, self._uncertain)
            if not self._exact(self.cycle.s2.board):
                raise RuntimeError('Abort requires manually restored and verified S2')
            self.error = ''
            self.next_transfer, self.in_flight, self._uncertain = 0, None, False
            self._save('ABORTED_VERIFIED')
        except Exception as exc:
            self.error = str(exc)
            self.phase = 'PAUSED_FAULT'
            try:
                self._save()
            except Exception:
                pass
        finally:
            self._lock.release()
        return self.phase
