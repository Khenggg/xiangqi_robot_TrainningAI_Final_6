"""Execute visual game moves through the retained simulation/motion boundary."""
from src.core import xiangqi
from src.domain.game_move import MoveActor
from src.motion.result import MotionExecutionResult


def execute_ai_move(state, hw, best_move, dry_run=False, visual_pick_enabled=False):
    if not best_move or state.physical_sync_fault or state.move_sync_error:
        return False
    src, dst = best_move
    if not xiangqi.is_valid_move(src, dst, state.board, state.turn):
        state.set_status("Engine returned an illegal move; board unchanged.", duration=10)
        return False
    if not hw.is_robot_ready:
        state.set_status("Robot backend is not ready; board unchanged.", duration=10)
        return False
    expected, _ = xiangqi.make_temp_move(state.board, best_move)
    captured = state.board[dst[1]][dst[0]]
    before = [row[:] for row in state.board]
    token = (state.game_epoch, state.ai_epoch, state.turn)
    try:
        context = state.create_move_context(src, dst, MoveActor.ROBOT)
        state.mark_move_pending(context)
        state.set_pending_physical_move(best_move, expected, captured, state.turn)
        targets = {"moving": None, "captured": None}
        if visual_pick_enabled and getattr(hw, "simulation_runtime", None) is None:
            targets = hw.get_robot_center_pick_targets({"captured": dst} if captured != "." else {"moving": src})
        def refresh_moving():
            return hw.get_robot_center_pick_targets({"moving": src}).get("moving")
        if getattr(hw, "simulation_runtime", None) is None:
            if not hw.verify_physical_board(before):
                raise RuntimeError("Camera did not confirm the board before motion")
            if state.board != before or token != (state.game_epoch, state.ai_epoch, state.turn):
                raise RuntimeError("Game changed during pre-motion camera verification")
        result = hw.execute_piece_move(
            s_col=src[0], s_row=src[1], d_col=dst[0], d_row=dst[1], is_capture=captured != ".",
            moving_visual_target=targets.get("moving"), captured_visual_target=targets.get("captured"),
            refresh_moving_visual_target=refresh_moving if captured != "." and visual_pick_enabled else None,
            verify_capture_cleared=(lambda: hw.is_cell_visually_clear(dst)) if captured != "." else None,
            piece_id=context.piece_id, captured_piece_id=context.captured_piece_id, move_context=context,
        )
        if not isinstance(result, MotionExecutionResult) or not result.success:
            raise RuntimeError(getattr(result, "message", "Motion returned no verified success"))
        if state.board != before or token != (state.game_epoch, state.ai_epoch, state.turn):
            raise RuntimeError("Game changed during motion; reconcile board")
        if getattr(hw, "simulation_runtime", None) is None:
            if not hw.verify_physical_board(expected):
                raise RuntimeError("Camera did not confirm the complete expected board")
        if state.board != before or token != (state.game_epoch, state.ai_epoch, state.turn):
            raise RuntimeError("Game changed during camera verification")
        return state.commit_pending_physical_move()
    except Exception as exc:
        print(f"[AI MOVE STOPPED] {exc}")
        state.mark_move_failed(str(exc))
        state.move_sync_error = str(exc)
        state.physical_sync_fault = True
        state.snapshot_continue_required = True
        state.snapshot_continue_can_commit_pending = False
        state.set_status(f"Move stopped: {exc}. Verify board before continuing.", duration=30)
        return False
