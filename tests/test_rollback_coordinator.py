import unittest
from types import SimpleNamespace
from copy import deepcopy

from src.core.rollback_coordinator import RollbackCoordinator


class Journal:
    def __init__(self):
        self.records = []

    def save(self, record):
        self.records.append(record)


class CoordinatorTests(unittest.TestCase):
    def make(self, captures=False):
        boards = [[[str(i)]] for i in range(4)]
        transfer = SimpleNamespace(src=(0, 0), dst=(1, 0), piece='rP',
                                   before=boards[2], after=boards[3], side='r')
        plan = SimpleNamespace(transfers=(transfer,), restorations=(),
                               after_arm=boards[3], target=boards[0])
        cycle = SimpleNamespace(s0=SimpleNamespace(board=boards[0]),
                                s2=SimpleNamespace(board=boards[2]), cycle_id='cycle',
                                status='READY', to_dict=lambda: {'cycle_id': 'cycle'})
        robot = SimpleNamespace(verify_rollback_ready=lambda **kw: {'ready': True})
        self.motions, self.commits, self.events = [], [], []
        robot.move_piece = lambda *args, **kw: self.motions.append((args, kw))
        self.actual = boards[2]

        def proof(board, **kw):
            return {'matched': board == self.actual, 'complete': board == self.actual}

        def motion(*args, **kw):
            self.motions.append((args, kw))
            self.actual = boards[3]

        robot.move_piece = motion
        hw = SimpleNamespace(robot=robot, verify_rollback_board=proof,
                             get_robot_center_pick_targets=lambda cells: {
                                 'moving': SimpleNamespace(col=0., row=0.)})
        self.baseline_ok = True

        def commit(snapshot, commit_id):
            self.commits.append(commit_id)

        # For this fixture there are no victims: final board is the arm checkpoint.
        cycle.s0.board = boards[3]
        plan.target = boards[3]
        coordinator = RollbackCoordinator(cycle, hw, Journal(), commit=commit,
                                          baseline=lambda: self.baseline_ok,
                                          plan=plan)
        return coordinator

    def test_complete_uses_measured_source_and_never_capture(self):
        c = self.make()
        self.assertEqual(c.start(), 'DONE')
        self.assertEqual(len(self.motions), 1)
        self.assertFalse(self.motions[0][0][4])
        self.assertTrue(self.motions[0][1]['require_visual_target'])
        self.assertEqual(len(self.commits), 1)
        c.resume()
        self.assertEqual(len(self.motions), 1)

    def test_baseline_retry_does_not_repeat_motion_or_commit(self):
        c = self.make()
        self.baseline_ok = False
        self.assertEqual(c.start(), 'COMMITTED_WAIT_BASELINE')
        self.baseline_ok = True
        self.assertEqual(c.resume(), 'DONE')
        self.assertEqual(len(self.motions), 1)
        self.assertEqual(len(self.commits), 1)
        self.assertEqual(c.abort(), 'DONE')

    def test_lost_ack_does_not_replay_completed_transfer(self):
        c = self.make()
        original = c.hw.robot.move_piece

        def lost(*args, **kw):
            original(*args, **kw)
            raise TimeoutError('lost ACK')

        c.hw.robot.move_piece = lost
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.assertEqual(c.resume(), 'PAUSED_FAULT')
        self.assertEqual(c.resume(operator_empty_gripper_confirmed=True), 'DONE')
        self.assertEqual(len(self.motions), 1)

    def test_mismatch_never_moves_or_commits(self):
        c = self.make()
        self.actual = [['wrong']]
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.assertEqual(self.motions, [])
        self.assertEqual(self.commits, [])

    def test_verified_abort_returns_cycle_without_committing(self):
        c = self.make()
        self.assertEqual(c.abort(), 'ABORTED_VERIFIED')
        self.assertFalse(self.commits)

    def test_checkpoint_failure_blocks_second_transfer(self):
        c = self.make()
        c.hw.robot.move_piece = lambda *a, **kw: self.motions.append((a, kw))
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.assertEqual(c.next_transfer, 0)
        self.assertEqual(len(self.motions), 1)
        self.assertFalse(self.commits)

    def test_journal_failure_prevents_motion(self):
        c = self.make()
        c.journal.save = lambda record: (_ for _ in ()).throw(OSError('disk full'))
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.assertFalse(self.motions)

    def real(self, capture=False):
        from src.core.rollback_cycle import StateSnapshot, CycleRecord, MoveRecord
        board = [['.'] * 9 for _ in range(10)]
        board[6][0], board[3][2] = 'r_P', 'b_R'
        if capture:
            board[5][0] = 'b_P'
        snap = lambda turn: StateSnapshot.from_state(SimpleNamespace(board=board, turn=turn))
        s0 = snap('r')
        board[6][0], board[5][0] = '.', 'r_P'
        s1 = snap('b')
        board[3][2], board[4][2] = '.', 'b_R'
        cycle = CycleRecord.start(s0, s1,
            MoveRecord('r', (0, 6), (0, 5), 'r_P', 'b_P' if capture else None), 0, 1)
        cycle.complete(snap('r'), MoveRecord('b', (2, 3), (2, 4), 'b_R', physical_verified=True))
        cycle.seal(arm_parked=True, controller_idle=True, board_verified=True,
                   baseline_ready=True, no_fault=True)
        c = self.make()
        self.actual = deepcopy(board)

        def proof(expected, allowed_missing_cells=(), **kw):
            missing = []
            for row in range(10):
                for col in range(9):
                    if expected[row][col] == self.actual[row][col]:
                        continue
                    if (col, row) in allowed_missing_cells and self.actual[row][col] == '.':
                        missing.append((col, row))
                    else:
                        return {'matched': False, 'complete': False}
            return {'matched': True, 'complete': not missing, 'missing': missing}

        def motion(sc, sr, dc, dr, capture, **kw):
            self.motions.append((sc, sr, dc, dr))
            self.actual[dr][dc], self.actual[sr][sc] = self.actual[sr][sc], '.'

        c.hw.verify_rollback_board = proof
        c.hw.robot.move_piece = motion
        return RollbackCoordinator(cycle, c.hw, c.journal, commit=c.commit, baseline=c.baseline)

    def test_manual_partial_then_wrong_then_correct_without_replaying_arm(self):
        c = self.real(capture=True)
        self.assertEqual(c.start(), 'WAIT_PLAYER')
        self.assertEqual(len(self.motions), 2)
        self.actual[5][0] = 'b_R'
        self.assertEqual(c.resume(), 'WAIT_PLAYER')
        self.assertFalse(self.commits)
        self.actual[5][0] = 'b_P'
        self.assertEqual(c.resume(), 'DONE')
        self.assertEqual(len(self.motions), 2)
        self.assertEqual(len(self.commits), 1)

    def test_restart_retains_journal_and_never_automatically_commands_arm(self):
        c = self.real()
        c._save('PREFLIGHT')
        saved = c.record()
        restored = RollbackCoordinator.restore(saved, c.hw, c.journal,
                                               commit=c.commit, baseline=c.baseline)
        self.assertEqual(restored.phase, 'RECOVERY_REQUIRED')
        self.assertFalse(self.motions)
        self.assertEqual(restored.resume(), 'PAUSED_FAULT')
        self.assertFalse(self.motions)
        self.assertEqual(restored.resume(operator_empty_gripper_confirmed=True), 'DONE')

    def test_consumed_runtime_ledger_does_not_corrupt_restart_authority(self):
        c = self.real()
        old_commit = c.commit

        def commit(snapshot, commit_id):
            old_commit(snapshot, commit_id)
            c.cycle.consume()

        c.commit = commit
        self.baseline_ok = False
        self.assertEqual(c.start(), 'COMMITTED_WAIT_BASELINE')
        restored = RollbackCoordinator.restore(c.record(), c.hw, c.journal,
                                               commit=commit, baseline=c.baseline)
        self.baseline_ok = True
        self.assertEqual(restored.resume(operator_empty_gripper_confirmed=True), 'DONE')
        self.assertEqual(len(self.commits), 1)

    def test_commit_ack_loss_retries_same_id_only_after_s0_proof(self):
        c = self.real()
        applied = set()

        def commit(snapshot, commit_id):
            if commit_id not in applied:
                applied.add(commit_id)
                raise TimeoutError('commit applied, acknowledgement lost')

        c.commit = commit
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.assertTrue(c.commit_intent)
        self.assertFalse(c.committed)
        restored = RollbackCoordinator.restore(c.record(), c.hw, c.journal,
                                               commit=commit, baseline=c.baseline)
        self.assertEqual(restored.resume(operator_empty_gripper_confirmed=True), 'DONE')
        self.assertEqual(applied, {c.commit_id})
        self.assertEqual(len(self.motions), 2)

    def test_lost_ack_unknown_board_requires_manual_recovery(self):
        c = self.real()
        original = c.hw.robot.move_piece

        def lost(*args, **kw):
            original(*args, **kw)
            self.actual[0][0] = 'r_R'
            raise TimeoutError('lost ACK')

        c.hw.robot.move_piece = lost
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.assertEqual(c.resume(operator_empty_gripper_confirmed=True), 'PAUSED_FAULT')
        self.assertEqual(len(self.motions), 1)
        self.assertFalse(self.commits)

    def test_not_executed_uncertain_step_can_retry_only_after_explicit_confirmation(self):
        c = self.real()
        original = c.hw.robot.move_piece
        c.hw.robot.move_piece = lambda *a, **kw: (_ for _ in ()).throw(TimeoutError('no ACK'))
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        c.hw.robot.move_piece = original
        self.assertEqual(c.resume(), 'PAUSED_FAULT')
        self.assertFalse(self.motions)
        self.assertEqual(c.resume(operator_empty_gripper_confirmed=True), 'DONE')
        self.assertEqual(len(self.motions), 2)

    def test_committed_board_changed_blocks_baseline_without_second_commit(self):
        c = self.real()
        self.baseline_ok = False
        self.assertEqual(c.start(), 'COMMITTED_WAIT_BASELINE')
        self.actual[0][0] = 'r_R'
        self.baseline_ok = True
        self.assertEqual(c.resume(), 'COMMITTED_WAIT_BASELINE')
        self.assertEqual(len(self.commits), 1)
        self.assertEqual(len(self.motions), 2)

    def test_restore_rejects_coerced_types_and_unknown_phases(self):
        c = self.real()
        for key, value in [('version', True), ('commit_applied', 'false'),
                           ('commit_intent', 0), ('uncertain', 'false'),
                           ('next_transfer', '0'), ('next_transfer', True),
                           ('in_flight', False), ('phase', 'invented'),
                           ('transaction_id', ''), ('commit_id', 'foreign'),
                           ('scope', 'foreign-account'), ('error', {})]:
            with self.subTest(key=key, value=value):
                saved = c.record()
                saved[key] = value
                with self.assertRaises(ValueError):
                    RollbackCoordinator.restore(saved, c.hw, c.journal,
                                                commit=c.commit, baseline=c.baseline)

    def test_restore_rejects_inconsistent_commit_progress(self):
        c = self.real()
        examples = [
            dict(phase='DONE', commit_intent=True, commit_applied=True),
            dict(phase='COMMIT_S0', commit_intent=True),
            dict(phase='COMMITTED_WAIT_BASELINE'),
            dict(phase='WAIT_PLAYER'),
            dict(phase='TRANSFER'),
            dict(phase='ABORTED_VERIFIED', in_flight=0),
        ]
        for fields in examples:
            with self.subTest(fields=fields):
                saved = c.record()
                saved.update(fields)
                with self.assertRaises(ValueError):
                    RollbackCoordinator.restore(saved, c.hw, c.journal,
                                                commit=c.commit, baseline=c.baseline)

    def test_verified_abort_after_uncertain_motion_has_restorable_terminal_record(self):
        c = self.real()
        original = c.hw.robot.move_piece

        def lost(*args, **kwargs):
            original(*args, **kwargs)
            raise TimeoutError('lost acknowledgement')

        c.hw.robot.move_piece = lost
        self.assertEqual(c.start(), 'PAUSED_FAULT')
        self.actual = [list(row) for row in c.cycle.s2.board]
        self.assertEqual(c.abort(operator_empty_gripper_confirmed=True), 'ABORTED_VERIFIED')
        restored = RollbackCoordinator.restore(c.record(), c.hw, c.journal,
                                               commit=c.commit, baseline=c.baseline)
        self.assertEqual(restored.phase, 'ABORTED_VERIFIED')
        self.assertFalse(restored.active)
        self.assertFalse(self.commits)


if __name__ == '__main__':
    unittest.main()
