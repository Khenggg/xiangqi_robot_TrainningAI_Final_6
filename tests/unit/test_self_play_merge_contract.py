from types import SimpleNamespace
from unittest.mock import Mock
from src.core.game_state import GameState
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.motion.result import MotionExecutionResult
from src.motion.stages import MotionStage


def controller(result=None, physical=False):
    state=GameState()
    state.api_client.send_move_update_board=Mock()
    state.api_client.end_match=Mock()
    state.sync_current_board=Mock(return_value=True)
    hw=SimpleNamespace(is_robot_ready=True,dry_run=False,
        simulation_runtime=None if physical else object(),cam_monitor=object(),
        config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL" if physical else "VIRTUAL",VISUAL_PICK_ENABLED=physical),
        ai_ctrl=SimpleNamespace(pick_move=Mock(return_value=((0,6),(0,5)))),
        difficulty_availability=Mock(return_value={"easy":True,"medium":True,"hard":True}),
        execute_piece_move=Mock(return_value=result if result is not None else MotionExecutionResult.ok()),
        verify_physical_board=Mock(return_value=True),
        get_robot_center_pick_targets=Mock(return_value={"moving":object()}),
        is_cell_visually_clear=Mock(return_value=True))
    ctrl=SelfPlayController(state,hw)
    assert ctrl.start("easy","hard")
    return state,hw,ctrl


def step(ctrl):
    assert ctrl.request_next_move()
    ctrl._thread.join(2)
    ctrl.tick()
    if ctrl._thread is not None:
        ctrl._thread.join(2)
        ctrl.tick()


def test_base_typed_success_commits_virtual_move_without_camera():
    state,hw,ctrl=controller(); step(ctrl)
    assert state.board[5][0]=="r_P" and state.turn=="b"
    assert ctrl.status is SelfPlayStatus.READY
    hw.verify_physical_board.assert_not_called()
    hw.ai_ctrl.pick_move.assert_called_once()
    assert hw.ai_ctrl.pick_move.call_args.kwargs["difficulty"]=="easy"


def test_boolean_success_is_rejected():
    state,hw,ctrl=controller(True); before=[row[:] for row in state.board];step(ctrl)
    assert state.board==before
    assert ctrl.status is SelfPlayStatus.FAULTED


def test_failed_motion_preserves_board_and_pending_recovery():
    from src.motion.result import MotionFailureCategory
    failure=MotionExecutionResult.fail(MotionStage.LAND,MotionFailureCategory.MOTION_COMMAND_FAILED,"112")
    state,hw,ctrl=controller(failure);before=[row[:] for row in state.board];step(ctrl)
    assert state.board==before and state.pending_ai_move is not None
    assert state.snapshot_continue_required


def test_reset_epoch_rejects_thought_even_with_same_board():
    state,hw,ctrl=controller();assert ctrl.request_next_move();ctrl._thread.join(2)
    state.game_epoch+=1;ctrl.tick()
    hw.execute_piece_move.assert_not_called()
    assert ctrl.status is SelfPlayStatus.FAULTED


def test_post_motion_camera_failure_never_commits():
    state,hw,ctrl=controller(physical=True)
    hw.verify_physical_board.side_effect=[True,True,False]
    before=[row[:] for row in state.board];step(ctrl)
    assert state.board==before and ctrl.status is SelfPlayStatus.FAULTED


def test_epoch_change_during_camera_verify_never_commits():
    state,hw,ctrl=controller(physical=True)
    calls=[]
    def verify(_):
        calls.append(1)
        if len(calls)==3:state.game_epoch+=1
        return True
    hw.verify_physical_board.side_effect=verify
    before=[row[:] for row in state.board];step(ctrl)
    assert state.board==before and ctrl.status is SelfPlayStatus.FAULTED


def test_ai_controller_applies_per_player_profile_override():
    from src.ai.ai_controller import AIController
    local=Mock()
    cfg=SimpleNamespace(AI_DIFFICULTY="hard",ENGINE_TYPE="LOCAL",MOONFISH_THINK_MS=1000,
        AI_DIFFICULTY_PROFILES={"easy":{"think_ms":10,"depth":1,"nodes":20,"temperature":0.5}})
    AIController(local,None,cfg).pick_move([],color="r",difficulty="easy")
    assert local.pick_best_move.call_args.kwargs["depth"]==1
    assert cfg.AI_DIFFICULTY=="hard"


def test_shared_ai_engine_request_response_is_serialized():
    import threading
    from src.ai.ai_controller import AIController
    first_inside=threading.Event();release_first=threading.Event();second_started=threading.Event()
    active=[];overlap=[];results=[]
    def pick(board,*args,**kwargs):
        if active:overlap.append(True)
        active.append(board)
        if board==[1]:
            first_inside.set()
            assert release_first.wait(2)
        active.pop()
        return board
    cfg=SimpleNamespace(AI_DIFFICULTY="impossible",MOONFISH_THINK_MS=10)
    ai=AIController(SimpleNamespace(pick_best_move=pick),None,cfg)
    first=threading.Thread(target=lambda:results.append(ai.pick_move([1])))
    def second_call():
        second_started.set();results.append(ai.pick_move([2]))
    second=threading.Thread(target=second_call)
    first.start();assert first_inside.wait(2)
    second.start();assert second_started.wait(2)
    assert ai._engine_request_lock.locked()
    release_first.set();first.join(2);second.join(2)
    assert not overlap and results==[[1],[2]]
