import csv
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np
from src.vision.geometry_measurement import camera_grid_error, robot_xy_error, save_csv


spec = importlib.util.spec_from_file_location('measure_geometry', Path(__file__).resolve().parents[1] / 'scripts' / 'measure_geometry.py')
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


class GeometryMeasurementTests(unittest.TestCase):
    def test_camera_error_keeps_out_of_grid_coordinates(self):
        matrix = np.array([[0.01, 0, -1], [0, 0.01, -1], [0, 0, 1]])
        entry = camera_grid_error(matrix, (97, 1004), (0, 9))
        self.assertAlmostEqual(entry['delta_col'], -0.03)
        self.assertAlmostEqual(entry['delta_row'], 0.04)
        self.assertAlmostEqual(entry['error_cells'], 0.05)

    def test_camera_rejects_invalid_projection(self):
        with self.assertRaises(ValueError):
            camera_grid_error(np.zeros((3, 3)), (100, 100), (0, 0))

    def test_robot_delta_is_aligned_minus_command(self):
        result = robot_xy_error((8, 9), [300, 100, 210], [304, 98, 178], 178)
        self.assertEqual((result['delta_x_mm'], result['delta_y_mm']), (4, -2))

    def test_robot_rejects_wrong_height_and_nonfinite_pose(self):
        for aligned in ([304, 98, 180], [float('nan'), 98, 178]):
            with self.assertRaises(ValueError):
                robot_xy_error((8, 9), [300, 100, 210], aligned, 178)

    def test_csv_undo_all_clears_old_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.csv'
            save_csv(path, [{'x': 1}])
            save_csv(path, [], fieldnames=['x'])
            with path.open(encoding='utf-8-sig') as stream:
                self.assertEqual(list(csv.DictReader(stream)), [])

    def run_robot(self, move, inputs, movement_result=0):
        robot = Mock()
        robot.ip = 'fake-ip'
        robot.tool_num = 0
        robot.user_num = 1
        robot.teaching_points = {}
        robot.board_to_pose_bilinear.return_value = [10, 20, 210, -179, -1.5, -11.3]
        robot.move_safe_pose.return_value = movement_result
        connection = Mock(SDK_state=True)
        connection.Mode.return_value = 0
        connection.RobotEnable.return_value = 0
        with tempfile.TemporaryDirectory() as directory, \
             patch('src.hardware.robot_VIP.FR5Robot', return_value=robot), \
             patch('src.hardware.robot_VIP.robot_sdk_core.RPC', return_value=connection), \
             patch.object(measure.config, 'DRY_RUN', False), \
             patch.object(measure.config, 'SAFE_Z', 210), \
             patch.object(measure, 'output_dir', return_value=Path(directory)), \
             patch.object(measure.time, 'sleep'), \
             patch('builtins.input', side_effect=inputs), \
             patch('builtins.print'):
            measure.robot_measure(SimpleNamespace(move=move, z=178))
        return robot, connection

    def test_plan_never_enables_or_moves_robot_or_gripper(self):
        robot, connection = self.run_robot(False, [])
        robot.connect.assert_not_called()
        robot.gripper_ctrl.assert_not_called()
        robot.move_safe_pose.assert_not_called()
        connection.Mode.assert_not_called()
        connection.RobotEnable.assert_not_called()
        connection.SetToolDO.assert_not_called()

    def test_supervised_robot_only_moves_at_safe_height_without_gripper(self):
        robot, connection = self.run_robot(True, ['MOVE', '0 0 250', '11 22 178', 'Q'])
        self.assertEqual([call.args[0][2] for call in robot.move_safe_pose.call_args_list], [250, 210])
        robot.gripper_ctrl.assert_not_called()
        robot.connect.assert_not_called()
        connection.SetToolDO.assert_not_called()

    def test_low_current_height_aborts_before_any_motion(self):
        with self.assertRaisesRegex(RuntimeError, 'below SAFE_Z'):
            self.run_robot(True, ['MOVE', '0 0 178'])

    def test_error_112_does_not_continue_measurement(self):
        with self.assertRaisesRegex(RuntimeError, '112'):
            self.run_robot(True, ['MOVE', '0 0 250'], movement_result=112)


if __name__ == '__main__':
    unittest.main()
