"""Latest visual physical API returns typed results; all stage operations are mocked."""
from unittest.mock import Mock
from src.hardware.robot_VIP import FR5Robot, MotionResult
from src.motion.stages import MotionStage


def make_robot():
    robot=FR5Robot();robot.connected=True;robot.dry=False
    robot.physical_motion_authorized=True
    robot.teaching_points={name:{"pose":[x,y,10,180,0,0],"joints":[0]*6}
        for name,x,y in [("R1",-200,500),("R2",-200,180),("R3",160,180),("R4",160,500),
                         ("R_Trash",-250,600)]}
    for method in ["pick_at","move_to_extra_safe","place_in_capture_bin","place_at","go_to_home_chess"]:
        setattr(robot,method,Mock(return_value=0))
    return robot


def test_success_returns_complete_typed_result_after_home():
    robot=make_robot();result=robot.move_piece(0,0,0,1,False)
    assert isinstance(result,MotionResult) and result.success and bool(result)
    assert result.last_completed_stage is MotionStage.COMPLETE
    robot.go_to_home_chess.assert_called_once()


def test_place_exception_returns_failed_stage_without_home_or_success():
    robot=make_robot();robot.place_at.side_effect=RuntimeError("place failed")
    result=robot.move_piece(0,0,0,1,False)
    assert not result and result.failed_stage is MotionStage.POST_RELEASE_LIFT
    assert "place failed" in result.message
    robot.go_to_home_chess.assert_not_called()


def test_capture_verification_failure_returns_recovery_result_before_moving_piece():
    robot=make_robot();clear=Mock(return_value=False)
    result=robot.move_piece(0,0,0,1,True,verify_capture_cleared=clear)
    assert not result and result.failed_stage is MotionStage.SETTLE
    assert "not visually clear" in result.message
    robot.pick_at.assert_called_once_with(0,1,visual_target=None)
    robot.place_at.assert_not_called()


def test_failed_visual_refresh_never_falls_back_to_nominal_pick():
    robot=make_robot();refresh=Mock(return_value=None)
    result=robot.move_piece(0,0,0,1,False,refresh_moving_visual_target=refresh)
    assert not result and "Fresh visual correction unavailable" in result.message
    robot.pick_at.assert_not_called();robot.place_at.assert_not_called()
