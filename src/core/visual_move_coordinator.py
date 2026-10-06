"""Execute one pending AI motion; only the caller may commit verified FEN."""
from src.vision.pick_consensus import require_pick_target
from src.core.game_state import pending_move_signature


def execute_pending_ai_motion(state, hw, config, stage="pre_pick"):
    pending = state.pending_ai_move
    if pending is None or stage not in {"pre_pick", "capture_removed"}:
        raise RuntimeError("No valid pending physical move")
    source, destination = pending["move"]
    signature = pending_move_signature(pending)
    capture = pending["captured_piece"] != "."
    token = tuple(getattr(state, name, 0) for name in
                  ("game_epoch", "ai_epoch", "human_commit_generation"))
    board = tuple(tuple(row) for row in state.board)
    request = getattr(state, "visual_pick_retry", None)

    def ensure_current():
        current_token = tuple(getattr(state, name, 0) for name in
                              ("game_epoch", "ai_epoch", "human_commit_generation"))
        if (state.pending_ai_move is not pending or pending["move"] != (source, destination)
                or pending_move_signature(pending) != signature
                or current_token != token or state.game_over or state.turn != "b"
                or tuple(tuple(row) for row in state.board) != board
                or (request is not None and not state.visual_pick_retry_is_current(request))):
            raise RuntimeError("Stale physical move; no acquisition/motion/commit authorized")

    ensure_current()
    if not hw.robot or not hw.robot.connected:
        raise RuntimeError("Robot disconnected; pending move not executed")
    checkpoint = getattr(state, "visual_capture_checkpoint", None)
    checkpoint_matches = (checkpoint is not None and checkpoint["pending"] is pending
                          and checkpoint["token"] == token
                          and checkpoint["signature"] == signature
                          and checkpoint["source"] == source and checkpoint["destination"] == destination)
    if stage == "capture_removed":
        if not capture or not checkpoint_matches:
            raise RuntimeError("No verified capture-removal checkpoint")
        if not hw.is_cell_visually_clear(destination):
            raise RuntimeError("Capture destination no longer confirmed clear; manual recovery required")
    elif checkpoint_matches:
        raise RuntimeError("Capture already removed; full capture replay forbidden")

    visual = bool(getattr(config, "VISUAL_PICK_ENABLED", False))
    required = visual and bool(getattr(config, "VISUAL_TOP_FACE_ENABLED", False))
    physical_capture = capture and stage != "capture_removed"
    name = "captured" if physical_capture else "moving"
    cell = destination if physical_capture else source
    targets = hw.get_robot_center_pick_targets({name: cell}) if visual else {}
    if required:
        require_pick_target(hw, targets, name, stage)
    ensure_current()

    def verify_capture_cleared():
        ensure_current()
        clear = hw.is_cell_visually_clear(destination)
        if clear:
            # Robot invokes this only after successful captured placement/lift.
            state.visual_capture_checkpoint = dict(pending=pending, token=token,
                                                   signature=signature,
                                                   source=source, destination=destination)
        return clear

    def refresh_moving_target():
        ensure_current()
        if not physical_capture:
            return targets.get("moving")
        fresh = hw.get_robot_center_pick_targets({"moving": source})
        ensure_current()
        if required:
            checkpoint = getattr(state, "visual_capture_checkpoint", None)
            if checkpoint is None or checkpoint["pending"] is not pending:
                raise RuntimeError("Source refresh without verified capture-removal checkpoint")
            return require_pick_target(hw, fresh, "moving", "capture_removed")
        return fresh.get("moving")

    hw.robot.move_piece(*source, *destination, physical_capture,
                       moving_visual_target=targets.get("moving"),
                       captured_visual_target=targets.get("captured"),
                       refresh_moving_visual_target=refresh_moving_target,
                       verify_capture_cleared=verify_capture_cleared,
                       require_visual_target=required)
    ensure_current()
    if visual and not hw.verify_visual_move(source, destination):
        raise RuntimeError("Arm command completed but source/destination not verified; FEN unchanged")
    ensure_current()
