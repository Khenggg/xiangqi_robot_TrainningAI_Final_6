"""Physical adapter safety tests: SDK is always mocked."""
from unittest.mock import MagicMock, patch
import pytest
import config
from src.hardware.robot_VIP import FR5Robot, RobotCommandError
from src.motion.stages import MotionStage


def ready_robot():
    arm=FR5Robot(); arm.dry=False; arm.connected=True
    arm.physical_motion_authorized=True
    arm.robot=MagicMock(); arm.robot.MoveCart.return_value=0
    arm.robot.MoveJ.return_value=0; arm.robot.SetToolDO.return_value=0
    arm.robot.Mode.return_value=0; arm.robot.RobotEnable.return_value=0
    arm.robot.GetRobotTeachingPoint.return_value = (0, [0.0]*12 + [arm.tool_num, arm.user_num])
    arm.teaching_points={name:{"pose":[x,y,10,180,0,0],"joints":[0]*6}
        for name,x,y in [("R1",-200,500),("R2",-200,180),("R3",160,180),("R4",160,500)]}
    return arm


def test_connect_never_actuates_even_when_dry_run_is_false():
    arm=ready_robot(); sdk=arm.robot; sdk.SDK_state=True
    sdk.GetRobotTeachingPoint.return_value=(0,[0]*12)
    with patch("src.hardware.robot_VIP.robot_sdk_core") as module, patch.object(arm,"_load_teaching_points"):
        module.RPC.return_value=sdk
        assert arm.connect()
    assert not arm.physical_motion_authorized
    for name in ["RobotEnable","Mode","SetToolDO","MoveCart","MoveJ"]:
        getattr(sdk,name).assert_not_called()


def test_explicit_activation_requires_commissioning_and_valid_corners():
    arm=ready_robot(); arm.physical_motion_authorized=False
    with pytest.raises(RobotCommandError): arm.activate_physical_control()
    arm.robot.RobotEnable.assert_not_called()
    assert arm.activate_physical_control(commissioned=True)
    arm.robot.RobotEnable.assert_called_once_with(1)
    arm.robot.SetToolDO.assert_not_called()


@pytest.mark.parametrize("method,args",[("move_safe_pose",([0,0,200,180,0,0],)),
    ("movel_pose",([0,0,200,180,0,0],)),("movej_joint",([0]*6,[0,0,200,180,0,0])),
    ("gripper_ctrl",(config.GRIPPER_ACTION_OPEN_MAX,))])
def test_read_only_connection_rejects_all_actuation(method,args):
    arm=ready_robot(); arm.physical_motion_authorized=False
    with pytest.raises(RobotCommandError): getattr(arm,method)(*args)
    assert arm.robot.mock_calls==[]


@pytest.mark.parametrize("method,args",[("move_safe_pose",([0,0,200,180,0,0],)),
    ("movel_pose",([0,0,200,180,0,0],)),("movej_joint",([0]*6,[0,0,200,180,0,0]))])
def test_status_112_is_a_command_failure(method,args):
    arm=ready_robot(); arm.robot.MoveCart.return_value=112; arm.robot.MoveJ.return_value=112
    with pytest.raises(RobotCommandError) as error: getattr(arm,method)(*args)
    assert error.value.backend_code==112


def test_land_failure_stops_before_grip_and_reports_stage():
    arm=ready_robot(); arm.robot.MoveCart.side_effect=[0,112]
    with patch("src.hardware.robot_VIP.time.sleep"):
        result=arm.move_piece(0,0,0,1,False)
    assert not result and not result.success
    assert result.failed_stage==MotionStage.LAND
    assert result.last_completed_stage==MotionStage.APPROACH
    assert result.backend_code==112
    arm.robot.SetToolDO.assert_not_called()
    assert arm.robot.MoveCart.call_count==2


def test_gripper_failure_stops_before_lift_or_place():
    arm=ready_robot(); arm.robot.SetToolDO.return_value=77
    with patch("src.hardware.robot_VIP.time.sleep"):
        result=arm.move_piece(0,0,0,1,False)
    assert not result; assert result.failed_stage==MotionStage.GRIP
    assert arm.robot.MoveCart.call_count==2


def test_missing_corner_never_falls_back_to_config():
    arm=ready_robot(); arm.teaching_points.pop("R4")
    with pytest.raises(KeyError): arm.board_to_pose(4,5,200)
    result=arm.move_piece(0,0,0,1,False)
    assert not result; assert arm.robot.mock_calls==[]


@pytest.mark.parametrize("col,row,z",[(-1,0,200),(9,0,200),(0,10,200),(0,0,float("nan"))])
def test_out_of_board_and_nonfinite_geometry_reject(col,row,z):
    with pytest.raises(ValueError): ready_robot().board_to_pose(col,row,z)


def test_rotated_corner_geometry_retains_distances_and_center():
    arm=ready_robot(); arm._calculate_cell_sizes_from_corners()
    assert arm.auto_cell_sizes=={"x":40,"y":40}
    with patch.object(config,"OFFSET_X",0),patch.object(config,"OFFSET_Y",0):
        assert arm.board_to_pose(4,4.5,200)[:3]==[-20,340,200]


def test_failed_home_does_not_invent_idle_recovery_motion():
    arm=ready_robot(); arm.robot.GetRobotTeachingPoint.return_value=(77,[])
    with pytest.raises(RobotCommandError): arm.go_to_home_chess()
    arm.robot.MoveCart.assert_not_called(); arm.robot.MoveJ.assert_not_called()


def test_capture_without_taught_bin_rejects_before_first_motion():
    arm=ready_robot(); result=arm.move_piece(0,0,0,1,True)
    assert not result; assert arm.robot.mock_calls==[]


def test_rejected_nested_pick_result_stops_sequence():
    arm=ready_robot()
    with patch.object(arm,"pick_at",return_value=False), patch.object(arm,"place_at") as place:
        result=arm.move_piece(0,0,0,1,False)
    assert not result
    place.assert_not_called()


def test_activation_failure_revokes_previous_authorization():
    arm=ready_robot(); arm.robot.Mode.return_value=112
    with pytest.raises(RobotCommandError): arm.activate_physical_control(commissioned=True)
    assert not arm.physical_motion_authorized
    arm.robot.RobotEnable.assert_not_called()
