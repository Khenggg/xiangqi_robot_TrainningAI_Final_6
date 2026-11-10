"""Read-only explanation of existing recovery gates; never clears a lock."""


def describe_recovery(state):
    if state.get("hardware_recovery_reason"):
        reason = "The camera confirmed the board; " + state["hardware_recovery_reason"]
        action = "Resolve the robot state in the WebApp/controller. When the fault clears and the arm/gripper has stopped, press Ctrl+F8 to confirm, then V to verify."
    elif state.get("pick_test_fault") or state.get("pick_test_resume_required"):
        reason = state.get("pick_test_fault") or "The game is paused for the pick/release test."
        action = "If the test moved pieces, restore the start position. Press NEW GAME. A real robot still needs its own board verification and enable step."
    elif state.get("turn_confirmation_required"):
        reason = "The camera verified the board but the side to move is unknown."
        action = "Confirm the side: key 1 = Red, key 2 = Black."
    elif state.get("physical_sync_fault") or state.get("move_sync_error"):
        reason = state.get("move_sync_error") or state.get("move_execution_error") or "The real board state is not verified."
        action = "V: verify with the camera. F4: rescan the whole board if the position differs. Confirm the side when asked. Do not repeat pick commands."
        if state.get("robot_backend") == "VIRTUAL":
            action = "The simulation is stopped. Check the backend error/log. Fix the cause, then NEW GAME to resync the board."
    elif state.get("snapshot_continue_required"):
        reason = "The game is waiting for camera-state approval."
        action = "Check the position and press CONTINUE to verify before going on."
    else:
        return None
    pending = state.get("pending_ai_move") or state.get("pending_move")
    if isinstance(pending, dict):
        pending = pending.get("move")
    elif pending is not None and hasattr(pending, "src") and hasattr(pending, "dst"):
        pending = (pending.src, pending.dst)
    return {"reason": str(reason), "pending": str(pending) if pending else "No pending move",
            "execution": str(state.get("move_execution_status") or "IDLE"), "action": action}
