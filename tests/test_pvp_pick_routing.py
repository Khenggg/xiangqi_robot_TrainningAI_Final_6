"""PvP coordinate parity without opening a camera or connecting a robot."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import config
from src.core.game_state import GameState
from src.core.visual_move_coordinator import execute_pending_ai_motion
from src.hardware.hardware_manager import HardwareManager
from src.vision.visual_pick_estimator import VisualPickEstimator


class PvpPickRoutingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = SimpleNamespace(**{name: getattr(config, name) for name in dir(config)
                                     if name.isupper()})

    def hardware(self):
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = self.cfg
        hw.robot = Mock(connected=True)
        hw.cam_monitor = Mock()
        hw.is_cell_visually_clear = Mock(return_value=True)
        hw.verify_visual_move = Mock(return_value=True)
        hw._get_height_pick_targets = Mock(side_effect=AssertionError('height path used'))
        hw._get_top_face_targets = Mock(side_effect=AssertionError('top-face path used'))
        return hw

    def pending_state(self, capture=False):
        with patch('src.core.game_state.TuongKyDaiSuClient'):
            state = GameState()
        state.turn = 'b'
        state.board = [['.' for _ in range(9)] for _ in range(10)]
        state.board[4][4] = 'b_R'
        victim = 'r_P' if capture else '.'
        state.board[4][6] = victim
        state.update_fen_from_board()
        after = copy.deepcopy(state.board)
        after[4][4], after[4][6] = '.', 'b_R'
        state.set_pending_ai_move(((4, 4), (6, 4)), after, victim)
        return state

    def test_default_mode_uses_actual_legacy_foot_mapping_and_nonraw_snapshots(self):
        self.assertTrue(self.cfg.VISUAL_PVP_PICK_ENABLED)
        hw = self.hardware()
        with tempfile.TemporaryDirectory() as folder:
            matrix_path = Path(folder) / 'perspective.npy'
            np.save(matrix_path, np.eye(3))
            hw.pick_estimator = VisualPickEstimator(matrix_path, foot_ratio=.85)
            hw.cam_monitor.get_fresh_snapshot.return_value = (
                np.zeros((10, 10, 3), dtype=np.uint8), [(1, .9, (6.6, -.4, 7.4, 0.))])
            result = hw.get_robot_center_pick_targets({'moving': (7, 0)})['moving']
        self.assertAlmostEqual(result.col, 7.)
        self.assertAlmostEqual(result.row, -.06, places=6)  # center would be -.2
        self.assertEqual(hw.cam_monitor.get_fresh_snapshot.call_count, 3)
        hw.cam_monitor.get_fresh_pick_snapshot.assert_not_called()
        hw._get_height_pick_targets.assert_not_called()

    def test_mode_takes_priority_over_ring_top_height_switches(self):
        hw = self.hardware()
        self.cfg.VISUAL_RING_PICK_ENABLED = self.cfg.VISUAL_TOP_FACE_ENABLED = True
        hw.get_visual_pick_targets = Mock(return_value={'moving': None})
        self.assertEqual(hw.get_robot_center_pick_targets({'moving': (7, 0)}), {'moving': None})
        self.assertFalse(hw._top_face_enabled())
        hw._occupancy_snapshot()
        hw.cam_monitor.get_fresh_snapshot.assert_called_once()
        hw.cam_monitor.get_fresh_pick_snapshot.assert_not_called()

    def test_disabling_pvp_restores_height_router(self):
        hw = self.hardware()
        self.cfg.VISUAL_PVP_PICK_ENABLED = False
        hw._get_height_pick_targets = Mock(return_value={'moving': 'height'})
        self.assertEqual(hw.get_robot_center_pick_targets({'moving': (7, 0)}), {'moving': 'height'})

    def test_ai_missing_target_uses_logical_fallback_but_does_not_commit_fen(self):
        hw, state = self.hardware(), self.pending_state()
        hw.get_visual_pick_targets = Mock(return_value={'moving': None})
        fen = state.current_fen
        execute_pending_ai_motion(state, hw, self.cfg)
        kwargs = hw.robot.move_piece.call_args.kwargs
        self.assertFalse(kwargs['require_visual_target'])
        self.assertIsNone(kwargs['moving_visual_target'])
        hw.verify_visual_move.assert_called_once_with((4, 4), (6, 4))
        self.assertEqual(state.current_fen, fen)
        self.assertIsNotNone(state.pending_ai_move)

    def test_capture_remeasures_source_after_confirmed_removal_using_legacy_picker(self):
        hw, state = self.hardware(), self.pending_state(capture=True)
        hw.get_visual_pick_targets = Mock(side_effect=[{'captured': None}, {'moving': None}])
        def move(*args, **kwargs):
            self.assertTrue(kwargs['verify_capture_cleared']())
            self.assertIsNone(kwargs['refresh_moving_visual_target']())
        hw.robot.move_piece.side_effect = move
        execute_pending_ai_motion(state, hw, self.cfg)
        self.assertEqual([c.args[0] for c in hw.get_visual_pick_targets.call_args_list],
                         [{'captured': (6, 4)}, {'moving': (4, 4)}])
        self.assertIsNotNone(state.visual_capture_checkpoint)

    def test_failed_post_move_verification_keeps_fen_pending(self):
        hw, state = self.hardware(), self.pending_state()
        hw.get_visual_pick_targets = Mock(return_value={'moving': None})
        hw.verify_visual_move.return_value = False
        fen = state.current_fen
        with self.assertRaises(RuntimeError):
            execute_pending_ai_motion(state, hw, self.cfg)
        self.assertEqual(state.current_fen, fen)
        self.assertIsNotNone(state.pending_ai_move)

    def test_pick_place_test_allows_same_logical_fallback(self):
        hw = self.hardware()
        hw.center_pick_estimator = object()
        hw.get_visual_pick_targets = Mock(return_value={'moving': None})
        result = hw.execute_pick_place_test((8, 0), (7, 0))
        self.assertEqual((result.col, result.row, result.confidence), (8., 0., 0.))
        self.assertFalse(hw.robot.move_piece.call_args.kwargs['require_visual_target'])
        self.assertIsNone(hw.robot.move_piece.call_args.kwargs['moving_visual_target'])

    def test_hover_requires_measurement_and_does_not_fake_corner_fallback(self):
        hw = self.hardware()
        hw.get_visual_pick_targets = Mock(return_value={'moving': None})
        with self.assertRaises(RuntimeError):
            hw.execute_hover_test((8, 0))
        hw.robot.hover_at.assert_not_called()


if __name__ == '__main__':
    unittest.main()
