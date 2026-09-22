"""
Unit tests for HardwareManager integration with RobotBackend and MotionCoordinator.
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.hardware.backends.base import RobotBackend
from src.hardware.hardware_manager import HardwareManager
from src.motion.coordinator import MotionCoordinator


class MockConfig:
    DRY_RUN = True
    ROBOT_BACKEND = "VIRTUAL"
    ROBOT_IP = "127.0.0.1"
    BOARD_CALIBRATION_MODE = "POINTER_CONTACT"
    BOARD_ORIGIN_X = 200.0
    BOARD_ORIGIN_Y = -100.0
    ROTATION = [-179.164, -3.047, -26.304]
    PICK_TOOL_ROTATION = [-179.164, -3.047, -26.304]
    SAFE_CLEARANCE_Z_MM = 40.0
    PICK_DEPTH_OFFSET_MM = 0.0
    CAPTURE_BIN_X = -226.123
    CAPTURE_BIN_Y = 225.024
    CAPTURE_BIN_Z = 291.68
    ENGINE_TYPE = "LOCAL"
    MOONFISH_EXE = "dummy_moonfish"
    MOONFISH_NNUE = None
    MOONFISH_THINK_MS = 100
    VISUAL_PICK_ENABLED = False


class HardwareManagerIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.config = MockConfig()
        self.project_dir = str(Path(__file__).resolve().parent.parent.parent)

    @patch("src.hardware.hardware_manager.MoonfishEngine")
    def test_virtual_backend_initialization(self, mock_engine):
        mock_engine.return_value = MagicMock()
        self.config.ROBOT_BACKEND = "VIRTUAL"

        hw = HardwareManager(self.config, self.project_dir)
        hw._init_ai()
        hw._init_robot()

        self.assertIsNotNone(hw.backend)
        self.assertIsNotNone(hw.motion_coordinator)
        self.assertTrue(hw.is_robot_ready)

        # Test move piece execution via coordinator
        ok = hw.move_piece(s_col=0, s_row=0, d_col=0, d_row=1, is_capture=False)
        self.assertTrue(ok)

        # Test capture move piece
        ok_cap = hw.move_piece(s_col=0, s_row=0, d_col=0, d_row=1, is_capture=True)
        self.assertTrue(ok_cap)

        hw.cleanup()

    @patch("src.hardware.hardware_manager.MoonfishEngine")
    def test_physical_backend_dry_run_initialization(self, mock_engine):
        mock_engine.return_value = MagicMock()
        self.config.ROBOT_BACKEND = "PHYSICAL"

        hw = HardwareManager(self.config, self.project_dir)
        hw._init_ai()
        hw._init_robot()

        self.assertIsInstance(hw.backend, PhysicalFR3Backend)
        self.assertIsNotNone(hw.gripper_driver)
        self.assertIsNotNone(hw.motion_coordinator)
        self.assertTrue(hw.is_robot_ready)

        ok = hw.move_piece(s_col=1, s_row=2, d_col=1, d_row=3, is_capture=False)
        self.assertTrue(ok)

        hw.cleanup()


if __name__ == "__main__":
    unittest.main()
