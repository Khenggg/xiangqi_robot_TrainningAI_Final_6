"""
AI Move Execution Service.

Coordinates physical or dry-run execution of AI-generated moves.
Enforces safety invariants:
  - In PHYSICAL mode (dry_run=False), if robot is not ready, AI move MUST NOT
    be committed to GameState, and manual piece movement prompt with automatic
    success is forbidden.
  - State changes are only committed after physical motion completes successfully.
"""

from typing import Any, Optional, Tuple
from src.core import xiangqi


def execute_ai_move(
    state: Any,
    hw: Any,
    best_move: Any,
    dry_run: bool = False,
    visual_pick_enabled: bool = False,
) -> bool:
    """
    Execute AI move through HardwareManager and commit to GameState upon success.

    Returns:
        True if the move was executed and committed to GameState.
        False if execution failed or was rejected due to safety invariants.
    """
    if not best_move:
        return False

    try:
        s, d = best_move
    except Exception:
        s, d = best_move[0], best_move[1]

    cap_p = state.board[d[1]][d[0]]
    is_cap = cap_p != "."

    # 1. PHYSICAL MODE: Safety gate - robot must be ready
    if not dry_run:
        if not getattr(hw, "is_robot_ready", False):
            print("\n" + "=" * 60)
            print("❌ [SAFETY] Physical robot not ready! AI move commit rejected.")
            print("   GameState preserved: Turn remains Black ('b'), board unchanged.")
            print("=" * 60 + "\n")
            if hasattr(state, "set_status"):
                state.set_status(
                    "⚠️ Robot chưa sẵn sàng! Không thể thực hiện nước đi của AI.",
                    color=(180, 0, 0),
                    duration=10.0,
                )
            return False

        # Robot is ready -> execute motion
        print(f"[AI] Robot executing move: {s}->{d}")
        try:
            pick_targets = {"moving": None, "captured": None}
            if visual_pick_enabled and hasattr(hw, "get_visual_pick_targets"):
                expected_cells = {"moving": s}
                if is_cap:
                    expected_cells["captured"] = d
                pick_targets = hw.get_visual_pick_targets(expected_cells)

            robot_success = bool(
                hw.move_piece(
                    s[0], s[1], d[0], d[1], is_cap,
                    moving_visual_target=pick_targets.get("moving"),
                    captured_visual_target=pick_targets.get("captured"),
                )
            )
            if not robot_success:
                print("❌ [CRITICAL] Robot motion failed! (hw.move_piece returned False)")
        except Exception as e:
            print(f"❌ [CRITICAL] Robot motion exception: {e}")
            robot_success = False

        if not robot_success:
            print("❌ [SAFETY] Motion failed! Board state NOT updated. State remains recoverable.")
            if hasattr(state, "set_status"):
                state.set_status(
                    "⚠️ Robot di chuyển thất bại! Ván cờ chưa cập nhật.",
                    color=(180, 0, 0),
                    duration=5.0,
                )
            return False
    else:
        # DRY_RUN mode: Virtual commit
        robot_success = True

    # 2. COMMIT TO GAMESTATE
    state.move_history.append({"turn": "b", "src": s, "dst": d})
    if is_cap and hasattr(state, "r_captured"):
        state.r_captured.append(cap_p)
    state.board, _ = xiangqi.make_temp_move(state.board, (s, d))
    state.last_move = (s, d)
    state.turn = "r"
    if hasattr(state, "update_fen_from_board"):
        state.update_fen_from_board()
    print(f"[FEN] {getattr(state, 'current_fen', '')}")

    # API update
    if hasattr(state, "api_client") and state.api_client:
        try:
            state.api_client.send_move_update_board(state.current_fen)
        except Exception as e:
            print(f"[API] Error updating board: {e}")

    # Check game over
    if xiangqi.get_king_pos("r", state.board) is None:
        if hasattr(state, "handle_game_over"):
            state.handle_game_over("b")
        if hasattr(state, "api_client") and state.api_client:
            try:
                state.api_client.end_match(winner="BLACK", reason="CHECKMATE")
            except Exception:
                pass
    else:
        if getattr(hw, "is_robot_ready", False) and hasattr(hw, "capture_baseline_if_needed"):
            hw.capture_baseline_if_needed(force_delay=1.0)
            if hasattr(state, "set_status"):
                state.set_status("Your turn!", color=(0, 100, 180), duration=5.0)
        else:
            if hasattr(hw, "clear_yolo_baseline"):
                hw.clear_yolo_baseline()
            if hasattr(state, "set_status"):
                state.set_status("Your turn!", color=(0, 100, 180), duration=5.0)
        print("[GAME] Your turn...")

    return True
