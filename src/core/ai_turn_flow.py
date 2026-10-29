"""AI job completion and supervised physical handoff, without UI startup."""
from dataclasses import dataclass

from src.core import xiangqi


@dataclass(frozen=True)
class AIJobResult:
    move: object = None
    error: str | None = None


def evaluate_ai_result(state, result):
    """Return a legal move, or pause an engine error without inventing a win."""
    error = result.error
    move = result.move
    if error is None and move is None:
        if not xiangqi.find_all_valid_moves('b', state.board):
            state.handle_game_over('r')
            state.api_client.end_match(winner='RED', reason='CHECKMATE')
            return None
        error = 'Engine không trả nước đi dù Đen vẫn còn nước hợp lệ.'
    if error is None:
        try:
            source, destination = move
            if not xiangqi.is_valid_move(source, destination, state.board, 'b'):
                error = 'Engine trả nước đi không hợp lệ.'
        except (TypeError, ValueError, IndexError):
            error = 'Engine trả nước đi sai định dạng.'
    if error is not None:
        state.ai_failure = error
        state.snapshot_continue_required = True
        state.snapshot_continue_can_commit_pending = False
        state.set_status(f'AI lỗi: {error} FEN giữ nguyên; V/Continue để thử lại.',
                         color=(180, 0, 0), duration=3600)
        return None
    state.ai_failure = None
    return move


def dispatch_pending_ai_move(state, hardware, input_handler, config):
    """Leave real FEN pending until one verified motion/recovery commits it."""
    if bool(getattr(getattr(state, 'rollback_runtime', None), 'blocked', False)):
        return False
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
