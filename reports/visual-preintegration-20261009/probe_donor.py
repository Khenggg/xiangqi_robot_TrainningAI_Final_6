"""Counterexamples against exact visual SHA, using SDK/camera mocks only."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import config
from src.hardware.robot_VIP import FR5Robot
from src.hardware.hardware_manager import HardwareManager
from src.vision.visual_pick_estimator import GridTarget
from src.vision.height_pick_geometry import aggregate_height_targets

with patch.object(config, 'DRY_RUN', True):
    robot = FR5Robot()
robot.dry = False
robot.connected = True
robot.robot = Mock()
trace = []
robot.robot.MoveCart.side_effect = lambda *a,**k: (trace.append('MoveCart:112'),112)[1]
robot.gripper_ctrl = Mock(side_effect=lambda action: trace.append('gripper:'+str(action)))
robot.board_to_pose_bilinear = Mock(side_effect=lambda c,r,z,rotation=None: [c,r,z,*(rotation or [180,0,90])])
robot.board_to_pose = robot.board_to_pose_bilinear
manager = HardwareManager.__new__(HardwareManager)
manager.config = config
manager.robot = robot
manager.center_pick_estimator = Mock()
manager.cam_monitor = Mock()
manager.is_cell_visually_clear = Mock(return_value=True)
manager.get_robot_center_pick_targets = Mock(return_value={'moving':GridTarget(4,4,.9,0)})
manager.verify_visual_move = Mock(return_value=True)
manager.last_pick_resolution = {}
with patch('time.sleep'):
    returned = manager.execute_pick_place_test((4,4),(4,5))

accepted, reason = aggregate_height_targets([GridTarget(4,4,.9,0),GridTarget(4.01,4,.9,.01),None,None],(4,4))
result = dict(physical_sdk_called=False,sdk='Mock',camera='Mock',
              motion_error_112_calls=robot.robot.MoveCart.call_count,
              gripper_calls_total=robot.gripper_ctrl.call_count,
              gripper_calls_after_first_motion_error=sum(x.startswith('gripper:') for x in trace[trace.index('MoveCart:112')+1:]),
              call_trace=trace, manual_test_returned_target=returned is not None,
              height_accepts_old_samples_with_latest_missing=accepted is not None,
              height_aggregation_reason=reason)
Path('D:/OJT/xiangqi_robot_TrainningAI_Final_6/reports/visual-preintegration-20261009/donor-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
