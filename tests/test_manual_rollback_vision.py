"""Manual rollback verification uses only fresh camera evidence and baseline data."""
import unittest
from unittest.mock import Mock
import numpy as np

from src.hardware.hardware_manager import HardwareManager
from src.vision.manual_rollback_verifier import ManualRollbackVerifier, match_layout


class ManualRollbackVisionTests(unittest.TestCase):
    def setUp(self):
        self.board = [['.'] * 9 for _ in range(10)]
        self.board[0][4] = 'b_K'
        self.board[9][4] = 'r_K'
        self.recognition = dict(success=True, board=self.board, confidence=np.ones((10, 9)))
        self.hardware = HardwareManager.__new__(HardwareManager)
        self.hardware.cam_monitor = Mock()
        self.hardware.cchess_recognizer = object()
        self.hardware.recognize_board_state = Mock(return_value=self.recognition)
        self.hardware.cam_monitor.get_fresh_pick_snapshot.return_value = (np.zeros((4, 4, 3)), [])
        self.hardware.yolo_detector = Mock()
        self.hardware.yolo_detector._build_occupancy.return_value = [[p != '.' for p in row] for row in self.board]
        self.hardware.yolo_detector.capture_baseline.return_value = True

    def test_complete_identity_layout_matches(self):
        sample = self.hardware.sample_manual_rollback(self.board)
        self.assertTrue(sample['matched'])
        self.assertEqual(self.board, sample['observed_board'])
        self.hardware.cam_monitor.get_fresh_pick_snapshot.assert_called_once_with()
        self.hardware.recognize_board_state.assert_called_once_with(sample['frame'])

    def test_wrong_missing_unknown_or_extra_piece_is_rejected(self):
        for piece in ('.', 'r_K', '?', 'x', None):
            actual = [row[:] for row in self.board]
            actual[0][4] = piece
            self.assertFalse(match_layout(self.board, dict(self.recognition, board=actual)))
        actual = [row[:] for row in self.board]
        actual[3][2] = 'r_R'
        self.assertFalse(match_layout(self.board, dict(self.recognition, board=actual)))

    def test_low_nonfinite_or_missing_confidence_is_rejected(self):
        for confidence in (0.7, 0.69, float('nan'), float('inf')):
            values = np.ones((10, 9))
            values[3][3] = confidence
            self.assertFalse(match_layout(self.board, dict(self.recognition, confidence=values)))
        for values in (None, np.ones((9, 9))):
            self.assertFalse(match_layout(self.board, dict(self.recognition, confidence=values)))

    def test_confidence_above_threshold_matches(self):
        self.assertTrue(match_layout(self.board, dict(self.recognition, confidence=np.full((10, 9), .71))))

    def test_camera_inference_failure_cannot_match(self):
        self.hardware.cam_monitor.get_fresh_pick_snapshot.side_effect = RuntimeError('camera lost')
        self.assertFalse(self.hardware.sample_manual_rollback(self.board)['matched'])
        self.hardware.recognize_board_state.assert_not_called()

    def test_recognizer_unavailable_cannot_match(self):
        self.hardware.cchess_recognizer = None
        self.assertFalse(self.hardware.sample_manual_rollback(self.board)['matched'])
        self.hardware.cam_monitor.get_fresh_pick_snapshot.assert_not_called()

    def test_stable_proof_requires_three_new_frames_and_one_second(self):
        verifier = ManualRollbackVerifier()
        self.assertFalse(verifier.observe(dict(matched=True, frame=object()), 1.0))
        self.assertFalse(verifier.observe(dict(matched=True, frame=object()), 1.5))
        self.assertTrue(verifier.observe(dict(matched=True, frame=object()), 2.0))

    def test_samples_alone_do_not_establish_stability(self):
        verifier = ManualRollbackVerifier()
        for now in (1, 1.1, 1.2, 1.3):
            self.assertFalse(verifier.observe(dict(matched=True, frame=object()), now))

    def test_reused_exposure_resets_proof(self):
        verifier = ManualRollbackVerifier()
        frame = object()
        verifier.observe(dict(matched=True, frame=frame), 1)
        self.assertFalse(verifier.observe(dict(matched=True, frame=frame), 2))
        self.assertEqual(0, verifier.samples)

    def test_mismatch_or_clock_reversal_resets_stability(self):
        for sample, now in ((dict(matched=False, frame=object()), 2),
                            (dict(matched=True, frame=None), 2),
                            (dict(matched=True, frame=object()), .5)):
            verifier = ManualRollbackVerifier()
            verifier.observe(dict(matched=True, frame=object()), 1)
            self.assertFalse(verifier.observe(sample, now))
            self.assertEqual(0, verifier.samples)

    def test_baseline_publishes_same_verified_exposure(self):
        sample = self.hardware.sample_manual_rollback(self.board)
        self.assertTrue(self.hardware.publish_manual_rollback_baseline(sample))
        self.hardware.yolo_detector.capture_baseline.assert_called_once_with(sample['frame'], sample['detections'])
        self.hardware.cam_monitor.get_fresh_pick_snapshot.assert_called_once()

    def test_yolo_dropout_does_not_veto_verified_identity_layout(self):
        sample = self.hardware.sample_manual_rollback(self.board)
        self.hardware.yolo_detector._build_occupancy.return_value = [[False] * 9 for _ in range(10)]
        self.assertTrue(self.hardware.publish_manual_rollback_baseline(sample))
        self.hardware.yolo_detector.capture_baseline.assert_called_once_with(sample['frame'], sample['detections'])
        self.hardware.yolo_detector._build_occupancy.assert_not_called()

    def test_unmatched_board_never_publishes_baseline(self):
        sample = self.hardware.sample_manual_rollback(self.board)
        self.assertFalse(self.hardware.publish_manual_rollback_baseline(dict(sample, matched=False)))
        self.hardware.yolo_detector.capture_baseline.assert_not_called()

    def test_actual_baseline_keeps_measured_grid_not_synthetic_full_occupancy(self):
        from src.vision.snapshot_detector import SnapshotDetector
        detector = SnapshotDetector.__new__(SnapshotDetector)
        detector.num_rows, detector.num_cols = 10, 9
        measured = [[False] * 9 for _ in range(10)]
        measured[0][4] = True  # YOLO misses the Red king, identity model sees both.
        detector._build_occupancy = Mock(return_value=measured)
        self.hardware.yolo_detector = detector
        sample = self.hardware.sample_manual_rollback(self.board)
        self.assertTrue(self.hardware.publish_manual_rollback_baseline(sample))
        self.assertEqual(measured, detector._baseline_occ)
        np.testing.assert_array_equal(sample['frame'], detector._baseline_frame)
        self.assertIsNot(sample['frame'], detector._baseline_frame)
        self.assertTrue(detector.has_baseline())
        self.assertFalse(detector.has_new_human_move(sample['detections'], self.board,
                                                   frame=sample['frame']))

    def test_baseline_capture_failure_is_not_success(self):
        sample = self.hardware.sample_manual_rollback(self.board)
        self.hardware.yolo_detector.capture_baseline.return_value = False
        self.assertFalse(self.hardware.publish_manual_rollback_baseline(sample))
        self.assertIn('baseline', sample['baseline_error'])


if __name__ == '__main__':
    unittest.main()
