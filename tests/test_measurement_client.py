import csv
from pathlib import Path
import tempfile
import queue
import unittest
from unittest.mock import Mock, patch

import numpy as np
from src.ui import measurement_client as client


class GuidedMeasurementTests(unittest.TestCase):
    def test_canvas_click_maps_exact_rounded_display_to_original(self):
        w, h = 1283, 721
        scale = min(780 / w, 440 / h)
        dw, dh = round(w * scale), round(h * scale)
        x = (780 - dw) / 2 + dw * .25
        y = (440 - dh) / 2 + dh * .75
        pixel = client.canvas_to_pixel(x, y, w, h)
        self.assertAlmostEqual(pixel[0], w * .25)
        self.assertAlmostEqual(pixel[1], h * .75)
        self.assertIsNone(client.canvas_to_pixel(390, 0, w, h))

    def test_xyz_requires_three_finite_numbers(self):
        self.assertEqual(client.parse_xyz('10, 20, 210'), [10, 20, 210])
        for text in ('', '1 2', '1 2 3 4', '1 nan 210', 'abc'):
            with self.assertRaises(ValueError):
                client.parse_xyz(text)

    def test_camera_writes_each_click_and_undo(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(client, 'new_report', return_value=Path(folder)):
            session = client.CameraMeasurement(np.zeros((100, 100, 3), np.uint8), np.eye(3))
            session.click((2, 3))
            self.assertEqual(session.rows[0]['delta_col'], 2)
            session.undo()
            with (Path(folder) / 'camera-grid.csv').open(encoding='utf-8-sig') as file:
                self.assertEqual(list(csv.DictReader(file)), [])
            for name in ('camera-original.png', 'camera-grid-overlay.png', 'perspective-used.npy', 'camera-metadata.json'):
                self.assertTrue((Path(folder) / name).exists())

    def test_camera_rejects_invalid_matrix_before_creating_report(self):
        with patch.object(client, 'new_report') as report:
            for matrix in (np.zeros((3, 3)), np.eye(2), np.full((3, 3), np.nan)):
                with self.assertRaises(ValueError):
                    client.CameraMeasurement(np.zeros((10, 10, 3), np.uint8), matrix)
            report.assert_not_called()

    def test_callback_failure_keeps_event_poll_running(self):
        app = Mock()
        app.messages = queue.Queue()
        app.messages.put((Mock(side_effect=ValueError('bad matrix')), None, None))
        with patch.object(client.messagebox, 'showerror') as error:
            client.MeasurementClient.poll(app)
        error.assert_called_once()
        app.after.assert_called_once()
        self.assertFalse(app.busy)

    def make_robot(self):
        robot = Mock()
        robot.connected = True
        robot.tool_num, robot.user_num = 0, 1
        robot.teaching_points = {}
        robot.board_to_pose_bilinear.return_value = [10, 20, 210, -179, -1.5, -11.3]
        robot.robot.Mode.return_value = robot.robot.RobotEnable.return_value = 0
        robot.move_safe_pose.return_value = 0
        return robot

    def test_guided_flow_has_no_gripper_and_records_only_after_move(self):
        robot = self.make_robot()
        with tempfile.TemporaryDirectory() as folder, patch.object(client, 'new_report', return_value=Path(folder)), \
             patch.object(client.config, 'SAFE_Z', 210), patch.object(client.config, 'PICK_Z', 178):
            session = client.RobotMeasurement(robot)
            robot.robot.Mode.assert_not_called()
            robot.move_safe_pose.assert_not_called()
            with self.assertRaises(RuntimeError):
                session.record([11, 22, 178])
            with self.assertRaises(ValueError):
                session.move([0, 0, 178])
            robot.robot.Mode.assert_not_called()
            session.move([0, 0, 250])
            self.assertEqual([call.args[0][2] for call in robot.move_safe_pose.call_args_list], [250, 210])
            with self.assertRaises(RuntimeError):
                session.move([0, 0, 250])
            with self.assertRaises(ValueError):
                session.record([11, 22, 180])
            self.assertEqual(session.index, 0)
            entry = session.record([11, 22, 178])
            self.assertEqual((entry['delta_x_mm'], entry['delta_y_mm']), (1, 2))
            self.assertEqual(session.index, 1)
            self.assertFalse(session.arrived)
            self.assertTrue((Path(folder) / 'grid-robot.csv').exists())
        robot.connect.assert_not_called()
        robot.gripper_ctrl.assert_not_called()
        robot.robot.SetToolDO.assert_not_called()

    def test_move_failure_does_not_allow_recording(self):
        for failure in ('mode', 'move'):
            robot = self.make_robot()
            if failure == 'mode':
                robot.robot.Mode.return_value = 1
            else:
                robot.move_safe_pose.return_value = 112
            with tempfile.TemporaryDirectory() as folder, patch.object(client, 'new_report', return_value=Path(folder)):
                session = client.RobotMeasurement(robot)
                with self.assertRaises(RuntimeError):
                    session.move([0, 0, client.config.SAFE_Z])
                self.assertFalse(session.arrived)
                with self.assertRaises(RuntimeError):
                    session.record([11, 22, session.z])

    def test_invalid_plan_never_enables_robot(self):
        robot = self.make_robot()
        robot.board_to_pose_bilinear.return_value = [float('nan'), 20, 210, 0, 0, 0]
        with tempfile.TemporaryDirectory() as folder, patch.object(client, 'new_report', return_value=Path(folder)):
            with self.assertRaises(ValueError):
                client.RobotMeasurement(robot)
        robot.robot.Mode.assert_not_called()
        robot.robot.RobotEnable.assert_not_called()
        robot.move_safe_pose.assert_not_called()

    def test_raw_connection_does_not_initialize_gripper(self):
        robot = self.make_robot()
        connection = Mock(SDK_state=True)
        with patch('src.hardware.robot_VIP.FR5Robot', return_value=robot), \
             patch('src.hardware.robot_VIP.robot_sdk_core.RPC', return_value=connection), \
             patch.object(client.config, 'DRY_RUN', False), \
             patch.object(client.time, 'sleep'), \
             patch.object(client, 'RobotMeasurement') as session:
            self.assertEqual(client.connect_robot(), session.return_value)
        robot.connect.assert_not_called()
        robot.gripper_ctrl.assert_not_called()
        connection.SetToolDO.assert_not_called()
        connection.Mode.assert_not_called()
        connection.RobotEnable.assert_not_called()


if __name__ == '__main__':
    unittest.main()
