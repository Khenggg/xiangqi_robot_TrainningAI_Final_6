"""Camera acquisition/retry adapter for the retained typed execution boundary.

No direct SDK calls and no FEN commits. The caller owns the semantic move.
"""
import logging
import time

from src.motion.result import MotionExecutionResult
from src.vision.pick_consensus import PickTargetUnavailable, require_pick_target
from src.core.project_logging import event
from src.core.session_journal import dumps


def signature(state):
    pending = state.pending_ai_move
    context = state.pending_move
    return (state.game_epoch, state.ai_epoch, state.turn,
            getattr(state, "human_commit_generation", 0),
            tuple(tuple(row) for row in state.board),
            pending["move"] if pending else None,
            tuple(tuple(row) for row in pending["expected_board"]) if pending else None,
            pending.get("captured_piece") if pending else None,
            pending.get("moving_color") if pending else None,
            getattr(context, "move_id", None), getattr(context, "piece_id", None),
            getattr(context, "captured_piece_id", None),
            dumps(getattr(state, "pending_execution_binding", None)),
            tuple(sorted(getattr(state, "piece_ids", {}).items())))


def retry_is_current(state, request=None):
    request = request if request is not None else getattr(state, "visual_pick_retry", None)
    return bool(request and not state.game_over and not state.physical_sync_fault
                and not state.move_sync_error and state.pending_ai_move is request["pending"]
                and state.pending_move is request["context"] and signature(state) == request["signature"])


def acquire_pick_targets(hw, expected_cells, stage, cfg, *, attempts=None, interval=None):
    """Acquire measured centres with a bounded retry for transient occlusion/lighting."""
    if attempts is None:
        attempts = max(1, int(getattr(cfg, "VISUAL_PICK_RETRY_ATTEMPTS", 1)))
    if interval is None:
        interval = max(0.0, float(getattr(cfg, "VISUAL_PICK_RETRY_INTERVAL_SEC", 0.0)))
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return hw.get_robot_center_pick_targets(dict(expected_cells))
        except PickTargetUnavailable as exc:
            last = exc
            event("vision.pick_retry",
                  f"Đo tâm quân chưa đạt, thử lại {attempt}/{attempts} ({stage})",
                  level=logging.INFO, attempt=attempt, attempts=attempts, stage=stage,
                  reason=str(exc), resolution=getattr(exc, "resolution", {}))
            if attempt >= attempts:
                break
            if interval > 0:
                time.sleep(interval)
    if last is None:
        raise PickTargetUnavailable("Pick target acquisition failed", stage)
    raise PickTargetUnavailable(str(last), stage, resolution=getattr(last, "resolution", {}))


def pause_visual_pick(state, exc):
    resolution = getattr(exc, "resolution", None)
    from src.vision.board_diagnostics import pick_cells_description
    pending = state.pending_ai_move
    cells = {}
    if pending is not None:
        source, destination = pending['move']
        role = ('captured' if pending['captured_piece'] != '.' and exc.stage != 'capture_removed' else 'moving')
        cells[role] = destination if role == 'captured' else source
    named_target = pick_cells_description(cells, state.board)
    state.visual_pick_retry = dict(pending=state.pending_ai_move, context=state.pending_move,
                                   signature=signature(state), stage=exc.stage, reason=str(exc),
                                   resolution=resolution)
    state.set_status(f"{named_target}. Camera chưa đủ điều kiện: {exc}. Y/V: đo lại đúng nước đang chờ.", duration=60)
    event("vision.retry_paused", f"{named_target}. Chờ đo lại tâm quân ({exc.stage}): {exc}",
          stage=exc.stage, reason=str(exc), move_id=getattr(state.pending_move, "move_id", None),
          resolution=resolution, expected_pick_cells=cells, expected_pick_description=named_target)


def execute_pending_ai_motion(state, hw, config=None, stage="pre_pick"):
    pending, context = state.pending_ai_move, state.pending_move
    if pending is None or stage not in ("pre_pick", "capture_removed"):
        raise RuntimeError("No pending move at a supported checkpoint")
    source, destination = pending["move"]
    before = [row[:] for row in state.board]
    expected = pending["expected_board"]
    token = signature(state)

    def ensure_current():
        if (state.game_over or state.pending_ai_move is not pending or state.pending_move is not context
                or signature(state) != token or state.turn != pending["moving_color"]
                or state.physical_sync_fault or state.move_sync_error):
            raise RuntimeError("Stale move identity/epoch/actor; acquisition/motion blocked")
        state.assert_execution_binding(context)

    ensure_current()
    capture = pending["captured_piece"] != "."
    missing_king = {"r_K": "r", "b_K": "b"}.get(pending["captured_piece"])
    terminal_kwargs = {"missing_king_color": missing_king} if missing_king is not None else {}
    checkpoint = getattr(state, "visual_capture_checkpoint", None)
    checkpoint_matches = bool(checkpoint and checkpoint["pending"] is pending
                              and checkpoint["signature"] == token)
    pre_board = [row[:] for row in before]
    if stage == "capture_removed":
        if not capture or not checkpoint_matches:
            raise RuntimeError("No verified capture-removal checkpoint")
        pre_board[destination[1]][destination[0]] = "."
    elif checkpoint_matches:
        raise RuntimeError("Capture already removed; replay of captured pick forbidden")
    if not hw.verify_physical_board(pre_board, **(terminal_kwargs if stage == "capture_removed" else {})):
        # No new motion was dispatched: preserve this guarded checkpoint so
        # another V/Y can reverify, rather than converting a transient camera
        # failure into a motion fault that discards the pending retry.
        raise PickTargetUnavailable("Camera did not confirm the complete pre-motion board", stage,
                                    resolution={"reason": "BOARD_VERIFICATION_FAILED"})
    ensure_current()
    cfg = config or getattr(hw, "config", None)
    visual = any(bool(getattr(cfg, key, False)) for key in
                 ("VISUAL_PICK_ENABLED", "VISUAL_HEIGHT_PICK_ENABLED", "VISUAL_TOP_FACE_ENABLED", "VISUAL_RING_PICK_ENABLED"))
    physical_capture = capture and stage != "capture_removed"
    name, cell = ("captured", destination) if physical_capture else ("moving", source)
    try:
        targets = acquire_pick_targets(hw, {name: cell}, stage, cfg) if visual else {}
    except PickTargetUnavailable as exc:
        raise PickTargetUnavailable(str(exc), stage, resolution=getattr(exc, "resolution", {})) from exc
    if visual:
        require_pick_target(hw, targets, name, stage)
    ensure_current()

    def capture_cleared():
        ensure_current()
        removed = [row[:] for row in before]
        removed[destination[1]][destination[0]] = "."
        if not hw.is_cell_visually_clear(destination) or not hw.verify_physical_board(removed, **terminal_kwargs):
            return False
        ensure_current()
        state.visual_capture_checkpoint = dict(pending=pending, signature=token)
        state.persist_checkpoint("CAPTURE_REMOVED")
        return True

    def refresh_moving():
        ensure_current()
        if not getattr(state, "visual_capture_checkpoint", None):
            raise RuntimeError("Source refresh needs a verified capture checkpoint")
        try:
            fresh = acquire_pick_targets(hw, {"moving": source}, "capture_removed", cfg)
            target = require_pick_target(hw, fresh, "moving", "capture_removed")
        except PickTargetUnavailable as exc:
            raise PickTargetUnavailable(str(exc), "capture_removed",
                                        resolution=getattr(exc, "resolution", {})) from exc
        ensure_current()
        if target is None:
            raise RuntimeError("Missing measured source after capture")
        return target

    result = hw.execute_piece_move(
        s_col=source[0], s_row=source[1], d_col=destination[0], d_row=destination[1],
        is_capture=physical_capture, moving_visual_target=targets.get("moving"),
        captured_visual_target=targets.get("captured"),
        refresh_moving_visual_target=refresh_moving if physical_capture and visual else None,
        verify_capture_cleared=capture_cleared if physical_capture else None,
        piece_id=getattr(context, "piece_id", None), captured_piece_id=getattr(context, "captured_piece_id", None),
        move_context=context)
    ensure_current()
    if not isinstance(result, MotionExecutionResult) or not result.success:
        metadata = getattr(result, "metadata", {})
        if (metadata.get("visual_retry_stage") == "capture_removed"
                and (getattr(state, "visual_capture_checkpoint", None) or {}).get("pending") is pending):
            raise PickTargetUnavailable(result.message, "capture_removed",
                                        resolution=metadata.get("pick_resolution"))
        raise RuntimeError(getattr(result, "message", "No typed motion success"))
    if not hw.verify_physical_board(expected, **terminal_kwargs):
        raise RuntimeError("Camera did not confirm the complete expected board")
    ensure_current()
    state.visual_pick_retry = None
    state.visual_capture_checkpoint = None
    return result
