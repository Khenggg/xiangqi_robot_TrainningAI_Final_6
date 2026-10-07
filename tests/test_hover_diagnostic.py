import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import numpy as np
import config
from src.hardware.robot_VIP import FR5Robot
from src.hardware.hardware_manager import HardwareManager
from src.vision.visual_pick_estimator import GridTarget
from src.vision.pick_debug import draw_pick_debug


class HoverDiagnosticTests(unittest.TestCase):
    def test_hover_only_moves_to_safe_z_with_production_visual_xy(self):
        robot = FR5Robot.__new__(FR5Robot)
        robot.board_to_pose_bilinear = Mock(side_effect=lambda c,r,z,rotation: [c,r,z,0,0,0])
        robot._apply_pick_outward_offset = Mock(side_effect=lambda pose,c,r: pose)
        robot.move_safe_pose = Mock()
        robot.movel_pose = Mock(side_effect=AssertionError("must not descend"))
        robot.gripper_ctrl = Mock(side_effect=AssertionError("must not grip"))
        target = GridTarget(6.9,7.1,.85,.14)
        pose = robot.hover_at(7,7,target)
        self.assertEqual(pose[:3], [6.9,7.1,config.SAFE_Z])
        robot.move_safe_pose.assert_called_once()
        robot.movel_pose.assert_not_called()
        robot.gripper_ctrl.assert_not_called()

    def test_missing_measured_target_prevents_hover(self):
        manager = HardwareManager.__new__(HardwareManager)
        manager.robot = Mock(connected=True)
        manager.config = SimpleNamespace(VISUAL_HEIGHT_PICK_ENABLED=True)
        manager.get_robot_center_pick_targets = Mock(return_value={"moving": None})
        manager.last_pick_resolution = {"failure":"hard", "reason":"Invalid geometry"}
        with self.assertRaises(RuntimeError):
            manager.execute_hover_test((7,7))
        manager.robot.hover_at.assert_not_called()

    def test_overlay_preserves_original_and_projects_to_board(self):
        geometry = Mock()
        geometry.grid_to_xy.side_effect = lambda cells: np.asarray(cells)
        geometry.project.side_effect = lambda cells,top: np.asarray(cells)*10+20
        frame = np.zeros((100,200,3),np.uint8)
        target = GridTarget(3,4,.9,0)
        overlay = draw_pick_debug(frame,(40,50,60,70),(3,4),target,target,geometry)
        self.assertEqual(overlay.shape, (240,200,3))
        self.assertFalse(frame.any())
        self.assertTrue(overlay.any())
        for call in geometry.project.call_args_list:
            self.assertFalse(call.kwargs["top"])


if __name__ == "__main__":
    unittest.main()
