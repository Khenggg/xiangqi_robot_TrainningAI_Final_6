import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vision import auto_calibrate
from src.vision.calibrate_camera import RETRY_AUTO_CALIBRATION


class AutoCalibrationRetryTests(unittest.TestCase):
    @patch("src.vision.auto_calibrate.time.sleep")
    @patch("src.vision.auto_calibrate.calibrate_perspective_camera")
    def test_manual_v_retry_restarts_the_ai_first_flow(self, manual_calibrate, _sleep):
        cap = Mock()
        cap.read.return_value = (True, object())
        expected_matrix = object()
        manual_calibrate.side_effect = [RETRY_AUTO_CALIBRATION, expected_matrix]

        with (
            patch.object(auto_calibrate.config, "DRY_RUN", False),
            patch("builtins.print"),
        ):
            result = auto_calibrate.run_calibration_flow(
                cap,
                "perspective.npy",
                pose_model_path=None,
            )

        self.assertIs(result, expected_matrix)
        self.assertEqual(manual_calibrate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
