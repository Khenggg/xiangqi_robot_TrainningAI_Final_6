"""Read-only explanation of existing recovery gates; never clears a lock."""


def describe_recovery(state):
    if state.get("pick_test_fault") or state.get("pick_test_resume_required"):
        reason = state.get("pick_test_fault") or "Game đã tạm dừng để test gắp/thả."
        action = "Nếu test đã dời quân, đặt lại thế khởi đầu. Bấm NEW GAME. Robot thật cần xác minh bàn và kích hoạt riêng."
    elif state.get("turn_confirmation_required"):
        reason = "Camera đã đối soát bàn nhưng chưa biết bên nào tới lượt."
        action = "Xác nhận lượt: phím 1 = Đỏ, phím 2 = Đen."
    elif state.get("physical_sync_fault") or state.get("move_sync_error"):
        reason = state.get("move_sync_error") or state.get("move_execution_error") or "Trạng thái bàn thật chưa được xác minh."
        action = "V: đối soát camera. F4: quét lại toàn bàn nếu thế cờ khác. Xác nhận lượt khi được hỏi. Không lặp lệnh gắp."
        if state.get("robot_backend") == "VIRTUAL":
            action = "Mô phỏng đang dừng. Xem lỗi backend/log. Sửa nguyên nhân, rồi NEW GAME để đồng bộ lại bàn."
    elif state.get("snapshot_continue_required"):
        reason = "Game đang chờ duyệt trạng thái camera."
        action = "Kiểm tra thế cờ và bấm CONTINUE để đối soát trước khi tiếp tục."
    else:
        return None
    pending = state.get("pending_ai_move") or state.get("pending_move")
    if isinstance(pending, dict):
        pending = pending.get("move")
    elif pending is not None and hasattr(pending, "src") and hasattr(pending, "dst"):
        pending = (pending.src, pending.dst)
    return {"reason": str(reason), "pending": str(pending) if pending else "Không có nước chờ",
            "execution": str(state.get("move_execution_status") or "IDLE"), "action": action}
