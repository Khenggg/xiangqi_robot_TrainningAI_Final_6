"""AI job completion and supervised physical handoff, without UI startup."""
from dataclasses import dataclass

from src.core import xiangqi


@dataclass(frozen=True)
class AIJobResult:
    move: object = None
    error: str | None = None


def evaluate_ai_result(state, result):
    """Validate engine output; failures use a legal move, never an invented win."""
    if state.game_over or state.turn != 'b':
        return None
    if state.pending_ai_move is not None or state.physical_sync_fault:
        return None
    if state.check_no_legal_moves():
        return None
    legal = xiangqi.find_all_valid_moves('b', state.board)
    move = result.move
    if result.error is not None or move not in legal:
        # Legal generation includes king safety: a fallback must escape check.
        import random
        move = random.choice(legal)
        state.set_status('AI dùng nước hợp lệ dự phòng — tiếp tục ván cờ.',
                         color=(0, 100, 180), duration=8)
    state.ai_failure = None
    state.snapshot_continue_required = False
    state.snapshot_continue_can_commit_pending = False
    return move


def dispatch_pending_ai_move(state, hardware, input_handler, config):
    """Leave real FEN pending until one verified motion/recovery commits it."""
    if state.pending_ai_move is None:
        raise RuntimeError('No pending AI move to dispatch')
    if config.DRY_RUN:
        return input_handler._finalize_pending_ai_move('Your turn!', (0, 100, 180))
    robot = hardware.robot
    if robot is None or not robot.connected:
        pending = state.pending_ai_move
        pending['manual_handoff'] = True
        source, destination = pending['move']
        state.physical_sync_fault = True
        state.snapshot_continue_required = True
        state.snapshot_continue_can_commit_pending = False
        state.set_status(f'Robot chưa kết nối. Di quân Đen {source}→{destination}, '
                         'rồi V/SPACE để xác nhận; FEN giữ nguyên.',
                         color=(180, 100, 0), duration=3600)
        return False
    if getattr(robot, 'communication_fault', False) is True:
        state.physical_sync_fault = True
        state.snapshot_continue_required = True
        state.snapshot_continue_can_commit_pending = False
        state.set_status('Chưa xác nhận controller đã dừng sau lỗi kết nối. '
                         'V để kiểm tra lại; chưa gửi motion mới.', duration=3600)
        return False
    # This entry point verifies/commits once in both synchronous and async modes.
    # No optimistic robot_success flag can authorize a second FEN commit.
    input_handler.start_pending_ai_motion()
    return True
