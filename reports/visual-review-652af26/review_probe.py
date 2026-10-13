"""Review reproduction only; no real SDK or camera calls."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pygame
import numpy as np
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer
from src.ui.debug_dashboard import DebugDashboard

evidence = {}
robot = FR5Robot()
robot.connected = True
robot.dry = False
robot.robot = Mock()
robot.robot.MoveCart.return_value = 112
robot.teaching_points = {name: {"pose": [x,y,178,180,0,0], "joints":[0]*6}
    for name,x,y in [("R1",0,0),("R2",320,0),("R3",320,360),("R4",0,360)]}
robot.gripper_ctrl = Mock(return_value=0)
robot.go_to_home_chess = Mock()
target = SimpleNamespace(col=.1,row=.1,confidence=.9,offset_cells=.14)
hw = HardwareManager.__new__(HardwareManager)
hw.robot = robot
hw.cam_monitor = hw.center_pick_estimator = object()
hw.get_robot_center_pick_targets = Mock(return_value={"moving":target})
hw.is_cell_visually_clear = Mock(return_value=True)
hw.verify_visual_move = Mock(return_value=True)
returned = hw.execute_pick_place_test((0,0),(3,4))
evidence["sdk_112"] = {"reported_success": returned is target,
    "failed_MoveCart_calls": robot.robot.MoveCart.call_count,
    "gripper_calls_after_motion_error": robot.gripper_ctrl.call_count,
    "home_requested": robot.go_to_home_chess.called}

board = [["." for _ in range(9)] for _ in range(10)]
board[0][0]="b_R";board[9][0]="r_R"
state = SimpleNamespace(board=board,game_over=False,turn="r",selected_pos=None,
    ai_thinking=False,ai_thread=None,pending_ai_move=None,set_status=Mock())
mock_hw = SimpleNamespace(execute_pick_place_test=Mock(side_effect=[
    RuntimeError("Motion executed; camera verification failed"),target]))
handler = InputHandler(state,mock_hw)
handler.handle_keyboard(pygame.K_t)
for cell in [(0,0),(3,4),(0,9),(3,5)]:
    handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(*cell))
evidence["failed_postcheck"] = {"motion_attempts_without_reconciliation": mock_hw.execute_pick_place_test.call_count,
    "mode_still_active":state.pick_test_mode,"second_move_updated_test_board":state.pick_test_board[5][3]=="r_R"}

with patch("src.ui.debug_dashboard.subprocess.Popen", side_effect=OSError("Review disables UI spawn")):
    dashboard=DebugDashboard(True)
dashboard.robot=SimpleNamespace(visual_pick_correction={"cell":[0,0],"target":[.1,.1]},connected=False)
with patch("src.ui.debug_dashboard.camera_correction",side_effect=np.linalg.LinAlgError("Singular matrix")):
    try:
        dashboard.snapshot()
    except Exception as exc:
        evidence["debug_projection"]={"uncaught_exception":type(exc).__name__,"message":str(exc)}
print("REVIEW_EVIDENCE="+json.dumps(evidence,ensure_ascii=False))
