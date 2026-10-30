"""Rollback proofs with fake camera/controller; never connects hardware."""
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np

from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot
from src.vision.height_pick_geometry import HeightPickEstimator
from src.vision.visual_pick_estimator import VisualPickEstimator


class Clock:
    def __init__(self): self.now = 0.
    def time(self): return self.now
    def sleep(self, seconds): self.now += max(seconds, .1)


class RollbackHardwareTests(unittest.TestCase):
    def hardware(self, layouts=None):
        h = HardwareManager.__new__(HardwareManager)
        h.config = SimpleNamespace(VISUAL_PICK_MIN_CONFIDENCE=.45)
        frames = [np.zeros((2, 2, 3), dtype=np.uint8) for _ in range(100)]
        h.cam_monitor = SimpleNamespace(get_fresh_pick_snapshot=Mock(side_effect=[(f, []) for f in frames]))
        self.board = [['.'] * 9 for _ in range(10)]
        h.recognize_board_state = Mock(side_effect=layouts) if layouts else Mock(return_value={
            'success': True, 'board': self.board, 'confidence': np.ones((10, 9))})
        estimator = HeightPickEstimator.__new__(HeightPickEstimator)
        estimator.has_detection_in_cell = Mock(return_value=False)
        estimator.estimate_pick_target = Mock(return_value=None)
        h._occupancy_estimator = Mock(return_value=estimator)
        return h

    def verify(self, h, **kwargs):
        clock = Clock()
        with patch('src.hardware.hardware_manager.time.monotonic', side_effect=clock.time), \
             patch('src.hardware.hardware_manager.time.sleep', side_effect=clock.sleep):
            return h.verify_rollback_board(self.board, timeout=2, **kwargs)

    def test_full_board_requires_three_new_frames_and_one_second(self):
        h = self.hardware()
        report = self.verify(h)
        self.assertTrue(report['matched'])
        self.assertTrue(report['complete'])
        self.assertGreaterEqual(report['stable_samples'], 3)
        self.assertGreaterEqual(report['stable_seconds'], 1.)

    def test_reused_frame_does_not_count_as_fresh(self):
        h = self.hardware()
        h.cam_monitor.get_fresh_pick_snapshot.side_effect = None
        h.cam_monitor.get_fresh_pick_snapshot.return_value = (np.zeros((2, 2, 3)), [])
        self.assertFalse(self.verify(h)['matched'])

    def test_low_confidence_unknown_and_geometry_fail_closed(self):
        h = self.hardware()
        h.recognize_board_state.return_value['confidence'][0][0] = .1
        self.assertTrue(self.verify(h)['low_confidence'])
        h.recognize_board_state.return_value['confidence'][0][0] = 1.
        self.board[0][0] = 'x'
        self.assertFalse(self.verify(h)['matched'])
        self.board[0][0] = '.'
        h._occupancy_estimator.return_value = SimpleNamespace(has_detection_in_cell=lambda *a, **k: False)
        self.assertTrue(self.verify(h)['geometry_errors'])

    def test_layout_confidence_must_be_strictly_above_point_seven(self):
        for score, accepted in ((.699, False), (.7, False), (.700001, True), (.799, True),
                                (float('nan'), False), (float('inf'), False)):
            with self.subTest(score=score):
                h = self.hardware()
                h.recognize_board_state.return_value['confidence'][1][0] = score
                result = self.verify(h)
                self.assertEqual(accepted, result['matched'])
                self.assertEqual([] if accepted else [(0, 1)], result['low_confidence'])

    def test_layout_threshold_override_and_wrong_piece_still_reject(self):
        h = self.hardware()
        h.recognize_board_state.return_value['confidence'][1][0] = .799
        self.assertFalse(self.verify(h, min_confidence=.8)['matched'])
        for piece in ('x', 'b_P'):
            with self.subTest(piece=piece):
                h = self.hardware()
                observed = [row[:] for row in self.board]
                observed[1][0] = piece
                h.recognize_board_state.return_value['board'] = observed
                h.recognize_board_state.return_value['confidence'][1][0] = .799
                self.assertFalse(self.verify(h)['matched'])

    def test_allowed_missing_is_stable_but_incomplete(self):
        h = self.hardware()
        expected = [row[:] for row in self.board]
        expected[0][0] = 'r_P'
        self.board = expected
        report = self.verify(h, allowed_missing_cells=((0, 0),))
        self.assertTrue(report['matched'])
        self.assertFalse(report['complete'])
        self.assertTrue(report['missing'])

    def test_mismatch_resets_consecutive_proof(self):
        good = [['.'] * 9 for _ in range(10)]
        wrong = [row[:] for row in good]
        wrong[0][0] = 'b_P'
        samples = [{'success': True, 'board': wrong if i % 3 == 2 else good,
                    'confidence': np.ones((10, 9))} for i in range(100)]
        h = self.hardware(samples)
        result = self.verify(h)
        self.assertFalse(result['matched'])
        self.assertLess(result['stable_samples'], 3)

    def test_unknown_observation_and_missing_confidence_denied(self):
        h = self.hardware()
        actual = [row[:] for row in self.board]
        actual[0][0] = 'x'
        h.recognize_board_state.return_value['board'] = actual
        self.assertEqual(self.verify(h)['unknown'], [(0, 0)])
        h.recognize_board_state.return_value.pop('confidence')
        self.assertTrue(self.verify(h)['errors'])

    def test_missing_piece_outside_restoration_and_cancel_denied(self):
        h = self.hardware()
        expected = [row[:] for row in self.board]
        expected[0][0] = 'r_P'
        self.board = expected
        self.assertFalse(self.verify(h)['matched'])
        self.assertTrue(self.verify(h, cancel_check=lambda: True)['errors'])

    def robot(self):
        r = FR5Robot.__new__(FR5Robot)
        r.dry, r.connected, r.communication_fault = False, True, False
        r.tool_num, r.user_num = 0, 1
        packet = SimpleNamespace(tl_cur_pos=[1., 2., 3., 0., 0., 0.], tool=0, user=1,
            tl_dgt_output_l=0, motion_done=1, mc_queue_len=0, robot_state=1,
            main_code=0, sub_code=0, safety_stop0_state=0, safety_stop1_state=0,
            EmergencyStop=0, collisionState=0)
        r.robot = SimpleNamespace(GetControllerIP=Mock(return_value=(0, 'fake')),
            GetRobotTeachingPoint=Mock(return_value=(0, packet.tl_cur_pos)),
            has_fresh_idle_state=Mock(return_value=True), robot_state_pkg=packet,
            _latest_state_health=(100., 1, 0, 1, 0, 0, 0, 0, 0, 0, 0))
        return r

    def test_readiness_requires_fresh_safe_pose_and_low_outputs(self):
        r = self.robot()
        with patch('src.hardware.robot_VIP.time.monotonic', return_value=100.):
            self.assertTrue(r.verify_rollback_ready()['ready'])
            r.robot.robot_state_pkg.tl_cur_pos = [999.] * 6
            self.assertFalse(r.verify_rollback_ready()['ready'])
            r.robot.robot_state_pkg.tl_cur_pos = [1., 2., 3., 0., 0., 0.]
            r.robot.robot_state_pkg.tl_dgt_output_l = 1
            self.assertFalse(r.verify_rollback_ready()['ready'])

    def test_uncertain_recovery_confirmation_not_sticky(self):
        r = self.robot()
        with patch('src.hardware.robot_VIP.time.monotonic', return_value=100.):
            self.assertFalse(r.verify_rollback_ready(uncertain_recovery=True)['ready'])
            self.assertTrue(r.verify_rollback_ready(uncertain_recovery=True,
                operator_empty_gripper_confirmed=True)['ready'])
            self.assertFalse(r.verify_rollback_ready(uncertain_recovery=True)['ready'])
            r.robot.has_fresh_idle_state.return_value = False
            self.assertFalse(r.verify_rollback_ready(operator_empty_gripper_confirmed=True)['ready'])

    def test_missing_home_wrong_tool_stale_and_dry_denied(self):
        with patch('src.hardware.robot_VIP.time.monotonic', return_value=100.):
            for kind in ('home', 'tool', 'stale', 'dry', 'moving'):
                with self.subTest(kind=kind):
                    r = self.robot()
                    if kind == 'home': r.robot.GetRobotTeachingPoint.return_value = (1, [])
                    if kind == 'tool': r.robot.robot_state_pkg.tool = 4
                    if kind == 'stale': r.robot._latest_state_health = (0.,)
                    if kind == 'dry': r.dry = True
                    if kind == 'moving': r.robot.robot_state_pkg.motion_done = 0
                    self.assertFalse(r.verify_rollback_ready()['ready'])

    def test_recovery_startup_connects_read_only_without_home_or_calibration(self):
        h = HardwareManager.__new__(HardwareManager)
        h.dry_run = False
        h.robot = Mock(connected=True)
        h._init_ai, h._init_camera, h._calibrate_robot = Mock(), Mock(), Mock()
        h.initialize_all(recovery_mode=True)
        h.robot.connect.assert_called_once_with(recovery_mode=True)
        h.robot.go_to_home_chess.assert_not_called()
        h._calibrate_robot.assert_not_called()

    def test_robot_recovery_connect_never_enables_modes_or_gripper(self):
        r = FR5Robot.__new__(FR5Robot)
        r.dry, r.ip = False, 'fake'
        r._load_teaching_points = Mock()
        r._validate_gripper_config = Mock()
        r._set_gripper_safe_idle, r.gripper_ctrl = Mock(), Mock()
        sdk = Mock(SDK_state=True)
        with patch('src.hardware.robot_VIP.robot_sdk_core.RPC', return_value=sdk), \
             patch('src.hardware.robot_VIP.time.sleep'):
            r.connect(recovery_mode=True)
        sdk.RobotEnable.assert_not_called()
        sdk.Mode.assert_not_called()
        r._set_gripper_safe_idle.assert_not_called()
        r.gripper_ctrl.assert_not_called()
        self.assertTrue(r.communication_fault)

    def test_mismatch_errors_describe_expected_and_observed_cell(self):
        h = self.hardware()
        actual = [row[:] for row in self.board]
        actual[0][0] = 'b_P'
        h.recognize_board_state.return_value['board'] = actual
        result = self.verify(h)
        self.assertTrue(any('(0, 0)' in error and 'b_P' in error and 'expected .' in error
                            for error in result['errors']))

    def test_layout_occupancy_does_not_require_unrelated_piece_to_be_pickable(self):
        h = self.hardware()
        self.board[4][4] = 'r_P'
        geometry = SimpleNamespace(width=800., height=900.,
            pixels_to_top_xy=lambda points: np.asarray(points), xy_to_grid=lambda points: points)
        estimator = HeightPickEstimator(geometry, min_confidence=.45, max_offset_cells=.25)
        h._occupancy_estimator.return_value = estimator
        box = [4.3, 3.9, 4.5, 4.1]  # center col4.4: occupied, unsafe to pick
        h.cam_monitor.get_fresh_pick_snapshot.side_effect = lambda: (
            np.zeros((2, 2, 3)), [(0, .99, box)])
        with patch('builtins.print'):
            result = self.verify(h)
        self.assertTrue(result['matched'])
        self.assertTrue(result['complete'])
        self.assertEqual([], result['geometry_errors'])
        self.assertFalse(result['missing'])
        self.assertIsNone(estimator.estimate_pick_target([(0, .99, box)], 4, 4))
        box[:] = [4., 3.9, 4.2, 4.1]  # center col4.1 within safe limit
        with patch('builtins.print'):
            result = self.verify(h)
        self.assertTrue(result['matched'])
        self.assertTrue(result['complete'])

    def test_pvp_rollback_occupancy_uses_foot_mapping_without_intrinsics(self):
        h = self.hardware()
        h.config.VISUAL_PVP_PICK_ENABLED = True
        h.config.VISUAL_HEIGHT_PICK_ENABLED = True
        h.config.VISUAL_RING_PICK_ENABLED = True
        h.config.VISUAL_TOP_FACE_ENABLED = True
        self.board[3][8] = 'b_P'
        with tempfile.TemporaryDirectory() as folder:
            matrix = Path(folder) / 'perspective.npy'
            np.save(matrix, np.eye(3))
            h.pick_estimator = VisualPickEstimator(matrix, foot_ratio=.85)
            del h._occupancy_estimator
            box = [8.3, 2.15, 8.5, 3.15]  # foot at row3, col8.4; center at row2.65
            h.cam_monitor.get_fresh_pick_snapshot.side_effect = lambda: (
                np.zeros((2, 2, 3)), [(0, .99, box)])
            with patch('src.hardware.hardware_manager.geometry_from_board',
                       side_effect=AssertionError('PvP must not load height/intrinsics')):
                result = self.verify(h)
            self.assertTrue(result['matched'], result['errors'])
            self.assertTrue(result['complete'])
            self.assertIsNone(h.pick_estimator.estimate_pick_target([(0, .99, box)], 8, 3))
            # A visible piece in a different square still cannot prove S2.
            self.board[3][8] = '.'
            self.assertFalse(self.verify(h)['matched'])


if __name__ == '__main__': unittest.main()
