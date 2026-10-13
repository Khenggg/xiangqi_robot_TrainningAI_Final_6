"""Execute visual game moves through the retained simulation/motion boundary."""
from src.core import xiangqi
from src.domain.game_move import MoveActor
from src.motion.result import MotionExecutionResult
from src.core.project_logging import event
import logging
import time


def execute_ai_move(state, hw, best_move, dry_run=False, visual_pick_enabled=False):
    if getattr(state, "game_over", False) or getattr(state, "turn_confirmation_required", False):
        return False
    if getattr(state, "pick_test_mode", False) or getattr(state, "pick_test_resume_required", False):
        return False
    if not best_move or state.physical_sync_fault or state.move_sync_error:
        return False
    src, dst = best_move
    if not xiangqi.is_valid_move(src, dst, state.board, state.turn):
        event("ai.illegal_move", "Nước đi AI không hợp lệ", level=logging.ERROR,
              code="ENGINE_ILLEGAL_MOVE", src=src, dst=dst, fen=state.current_fen)
        state.set_status("Engine returned an illegal move; board unchanged.", duration=10)
        return False
    if not hw.is_robot_ready:
        event("robot.not_ready", "Backend chưa sẵn sàng", level=logging.WARNING,
              code="ROBOT_NOT_READY", src=src, dst=dst)
        state.set_status("Robot backend is not ready; board unchanged.", duration=10)
        return False
    expected, _ = xiangqi.make_temp_move(state.board, best_move)
    captured = state.board[dst[1]][dst[0]]
    before = [row[:] for row in state.board]
    token = (state.game_epoch, state.ai_epoch, state.turn)
    started = time.monotonic()
    context = None
    from src.core.visual_move_coordinator import retry_is_current, pause_visual_pick, execute_pending_ai_motion
    from src.vision.pick_consensus import PickTargetUnavailable
    request = getattr(state, "visual_pick_retry", None)
    try:
        if request is not None:
            if not retry_is_current(state, request) or state.pending_ai_move["move"] != best_move:
                raise RuntimeError("Stale retry; pending move cannot be replaced")
            context = state.pending_move
        else:
            context = state.create_move_context(src, dst, MoveActor.ROBOT)
            state.mark_move_pending(context)
        event("move.started", "Bắt đầu thực hiện nước AI", move_id=context.move_id,
              piece_id=context.piece_id, captured_piece_id=context.captured_piece_id,
              src=src, dst=dst, cell_order="col,row", fen_before=state.current_fen,
              backend=getattr(getattr(hw, "config", None), "ROBOT_BACKEND", "UNKNOWN"))
        if request is None:
            state.set_pending_physical_move(best_move, expected, captured, state.turn)
        if getattr(getattr(hw, "config", None), "GAME_ONLY", False) is True:
            if not dry_run or getattr(hw.config, "ROBOT_BACKEND", None) != "VIRTUAL":
                raise RuntimeError("Game-only mode requires VIRTUAL and DRY_RUN")
            committed = state.commit_pending_physical_move()
            event("move.finished", "Kết thúc nước game-only", move_id=context.move_id,
                  committed=committed, fen_after=state.current_fen,
                  duration_s=round(time.monotonic() - started, 3))
            return committed
        if getattr(hw, "simulation_runtime", None) is None:
            execute_pending_ai_motion(state, hw, stage=request["stage"] if request else "pre_pick")
        else:
            result = hw.execute_piece_move(
                s_col=src[0], s_row=src[1], d_col=dst[0], d_row=dst[1], is_capture=captured != ".",
                moving_visual_target=None, captured_visual_target=None,
                piece_id=context.piece_id, captured_piece_id=context.captured_piece_id, move_context=context)
            if not isinstance(result, MotionExecutionResult) or not result.success:
                raise RuntimeError(getattr(result, "message", "Motion returned no verified success"))
            if state.board != before or token != (state.game_epoch, state.ai_epoch, state.turn):
                raise RuntimeError("Game changed during motion; reconcile board")
        committed = state.commit_pending_physical_move()
        event("move.finished", "Kết thúc thực hiện nước AI", move_id=context.move_id,
              committed=committed, fen_after=state.current_fen,
              duration_s=round(time.monotonic() - started, 3))
        return committed
    except PickTargetUnavailable as exc:
        pause_visual_pick(state, exc)
        return False
    except Exception as exc:
        event("move.failed", str(exc), level=logging.ERROR, code="MOVE_REJECTED", exc_info=True,
              move_id=getattr(context, "move_id", None), src=src, dst=dst,
              duration_s=round(time.monotonic() - started, 3), fen=state.current_fen)
        print(f"[AI MOVE STOPPED] {exc}")
        state.mark_move_failed(str(exc))
        state.move_sync_error = str(exc)
        state.physical_sync_fault = True
        state.snapshot_continue_required = True
        state.snapshot_continue_can_commit_pending = False
        state.set_status(f"Move stopped: {exc}. Verify board before continuing.", duration=30)
        return False
