import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.rollback_cycle import (StateSnapshot, MoveRecord, CycleRecord,
    build_inverse_plan, manual_restoration_check)
from src.core.rollback_journal import RollbackJournal, JournalError


def snapshot(board, turn='r'):
    return StateSnapshot.from_state(SimpleNamespace(board=board, turn=turn,
        current_fen='test', move_history=[{'turn': 'r', 'src': (1, 2), 'dst': (1, 3)}], move_log=[],
        r_captured=[], b_captured=[], move_number=1))


def cycle(red_capture=False, black_capture=None, conflict=False):
    board = [['.'] * 9 for _ in range(10)]
    board[6][0], board[3][2] = 'r_P', 'b_R'
    if red_capture:
        board[5][0] = 'b_P'
    if black_capture == 'other':
        board[4][2] = 'r_C'
    s0 = snapshot(board)
    red = MoveRecord('r', (0, 6), (0, 5), 'r_P', 'b_P' if red_capture else None)
    board[6][0], board[5][0] = '.', 'r_P'
    s1 = snapshot(board, 'b')
    dst = (0, 6) if conflict else ((0, 5) if black_capture == 'mover' else (2, 4))
    victim = board[dst[1]][dst[0]]
    black = MoveRecord('b', (2, 3), dst, 'b_R', None if victim == '.' else victim,
                       physical_verified=True)
    board[3][2], board[dst[1]][dst[0]] = '.', 'b_R'
    c = CycleRecord.start(s0, s1, red, 0, 1)
    c.complete(snapshot(board), black)
    c.seal(arm_parked=True, controller_idle=True, board_verified=True,
           baseline_ready=True, no_fault=True)
    return c


class RollbackCycleTests(unittest.TestCase):
    def test_six_capture_cases_restore_exact_s0(self):
        for red_capture in (False, True):
            for black_capture in (None, 'other', 'mover'):
                with self.subTest(red=red_capture, black=black_capture):
                    c = cycle(red_capture, black_capture)
                    p = build_inverse_plan(c)
                    self.assertEqual(len(p.transfers), 1 if black_capture == 'mover' else 2)
                    board = [list(row) for row in p.after_arm]
                    for r in p.restorations:
                        board[r.square[1]][r.square[0]] = r.piece
                    self.assertEqual(tuple(map(tuple, board)), c.s0.board)
                    self.assertTrue(manual_restoration_check(p, board)['complete'])

    def test_conflict_black_first(self):
        p = build_inverse_plan(cycle(True, conflict=True))
        self.assertEqual([t.side for t in p.transfers], ['b', 'r'])
        self.assertTrue(all(t.capture is False for t in p.transfers))

    def test_snapshot_deep_copy_and_roundtrip(self):
        c = cycle()
        d = c.to_dict()
        c2 = CycleRecord.from_dict(json.loads(json.dumps(d)))
        self.assertEqual(c2.to_dict(), d)
        d['s0']['board'][0][0] = 'r_K'
        self.assertEqual(c.s0.board[0][0], '.')
        state = SimpleNamespace()
        c.s0.apply_to(state)
        state.move_history[0]['src'][0] = 9
        self.assertEqual(c.s0.to_dict()['move_history'][0]['src'], [1, 2])

    def test_seal_and_consumption_gates(self):
        c = cycle()
        c.status = 'BUILDING'
        with self.assertRaises(ValueError):
            c.seal(arm_parked=False, controller_idle=True, board_verified=True,
                   baseline_ready=True, no_fault=True)
        c.status = 'READY'
        c.consume()
        with self.assertRaises(ValueError):
            build_inverse_plan(c)
        with self.assertRaises(ValueError):
            c.consume()

    def test_manual_subset_and_unknown(self):
        p = build_inverse_plan(cycle(True, 'other'))
        board = [list(r) for r in p.after_arm]
        self.assertEqual(len(manual_restoration_check(p, board)['missing']), 2)
        item = p.restorations[0]
        board[item.square[1]][item.square[0]] = item.piece
        self.assertEqual(len(manual_restoration_check(p, board)['missing']), 1)
        board[0][0] = 'x'
        check = manual_restoration_check(p, board)
        self.assertTrue(check['unknown'])
        self.assertFalse(check['complete'])
        board[0][0] = 'b_K'
        self.assertTrue(manual_restoration_check(p, board)['unexpected'])

    def test_tampered_ledger_rejected(self):
        c = cycle()
        c.black = MoveRecord('b', (8, 8), (2, 4), 'b_R', physical_verified=True)
        with self.assertRaises(ValueError):
            build_inverse_plan(c)

    def test_atomic_journal_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rollback.json'
            journal = RollbackJournal(path)
            self.assertIsNone(journal.load())
            record = {'phase': 'TRANSFER', 'cycle': cycle().to_dict(), 'commit_id': 'id'}
            journal.save(record)
            self.assertEqual(journal.load(), record)
            record['phase'] = 'COMMITTED_WAIT_BASELINE'
            journal.save(record)
            self.assertEqual(journal.load()['phase'], record['phase'])
            path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(JournalError):
                journal.load()

    def test_failed_journal_replace_keeps_last_durable_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = RollbackJournal(Path(tmp) / 'rollback.json')
            journal.save({'phase': 'BEFORE'})
            with patch('src.core.rollback_journal.os.replace', side_effect=OSError('disk')):
                with self.assertRaises(JournalError):
                    journal.save({'phase': 'STARTED'})
            self.assertEqual(journal.load(), {'phase': 'BEFORE'})
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])

    def test_corrupt_terminal_or_incomplete_ready_not_plannable(self):
        c = cycle()
        data = c.to_dict()
        data['s2']['game_over'] = True
        with self.assertRaises(ValueError):
            build_inverse_plan(CycleRecord.from_dict(data))

    def test_malformed_snapshot_metadata_rejected_before_apply(self):
        base = cycle().s0.to_dict()
        malformed = {'move_log': {}, 'move_history': [None], 'move_number': -1,
            'game_epoch': True, 'human_commit_generation': -1, 'game_over': 'no',
            'winner': 'yellow', 'turn': 'w', 'r_captured': ['b_P'],
            'b_captured': ['garbage'], 'last_move': [[0, 0], [99, 99]],
            'current_fen': 123}
        for key, value in malformed.items():
            with self.subTest(key=key):
                data = dict(base, **{key: value})
                with self.assertRaises(ValueError):
                    StateSnapshot.from_dict(data)
        for token in (None, '?', 'r_B', 'garbage'):
            with self.subTest(token=token):
                data = json.loads(json.dumps(base))
                data['board'][0][0] = token
                with self.assertRaises(ValueError):
                    StateSnapshot.from_dict(data)

    def test_malformed_history_and_cycle_epoch_rejected(self):
        for name in ('move_log', 'move_history'):
            data = cycle().s0.to_dict()
            data[name] = [{'turn': 'r', 'src': [0, 0], 'dst': [True, 2]}]
            with self.assertRaises(ValueError):
                StateSnapshot.from_dict(data)
        data = cycle().to_dict()
        data['s1']['game_epoch'] = 42
        with self.assertRaises(ValueError):
            CycleRecord.from_dict(data)

    def test_half_complete_cycle_and_truthy_seal_denied(self):
        data = cycle().to_dict()
        data['s2'] = None
        data['status'] = 'BUILDING'
        with self.assertRaises(ValueError):
            CycleRecord.from_dict(data)
        c = cycle()
        c.status = 'BUILDING'
        with self.assertRaises(ValueError):
            c.seal(arm_parked='false', controller_idle=True, board_verified=True,
                   baseline_ready=True, no_fault=True)


if __name__ == '__main__':
    unittest.main()
