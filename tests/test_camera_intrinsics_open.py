"""Backend fallback must preserve the requested camera index."""
import unittest
from unittest.mock import Mock, patch
import numpy as np
from scripts.calibrate_camera_intrinsics import open_camera


class IntrinsicsCameraOpenTests(unittest.TestCase):
    def test_releases_unreadable_backend_and_keeps_same_index(self):
        first = Mock()
        first.isOpened.return_value = True
        first.read.return_value = (False, None)
        second = Mock()
        second.isOpened.return_value = True
        second.read.return_value = (True, np.zeros((480, 640, 3), np.uint8))
        with patch('scripts.calibrate_camera_intrinsics.os.name', 'nt'), \
                patch('scripts.calibrate_camera_intrinsics.cv2.VideoCapture', side_effect=[first, second]) as factory:
            self.assertIs(open_camera(1), second)
        first.release.assert_called_once()
        second.release.assert_not_called()
        self.assertEqual([call.args[0] for call in factory.call_args_list], [1, 1])

    def test_explicit_backend_failure_does_not_change_camera(self):
        cap = Mock()
        cap.isOpened.return_value = False
        with patch('scripts.calibrate_camera_intrinsics.cv2.VideoCapture', return_value=cap) as factory:
            with self.assertRaisesRegex(RuntimeError, 'camera index 1'):
                open_camera(1, 'msmf')
        cap.release.assert_called_once()
        self.assertEqual(factory.call_count, 1)
