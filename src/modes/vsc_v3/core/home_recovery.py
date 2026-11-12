"""Keep a failed move uncommitted while the operator resets it at HOMECHESS."""
from dataclasses import dataclass

from src.modes.vsc_v3.core.game_state import pending_move_signature


@dataclass
class HomeRecoveryRequest:
    pending: object
    signature: object
    board: tuple
    token: tuple
    error: str
    status: str = 'returning_home'
    reason: str = ''
    owner: str = 'ai'
    test_move: tuple = None

    @classmethod
    def create(cls, state, error):
        if state.pending_ai_move is None:
            raise RuntimeError('No unfinished move to recover')
        return cls(state.pending_ai_move, pending_move_signature(state.pending_ai_move),
                   tuple(tuple(row) for row in state.board), cls.state_token(state), str(error))

    @staticmethod
    def state_token(state):
        return tuple(getattr(state, name, 0) for name in
                     ('game_epoch', 'ai_epoch', 'human_commit_generation'))

    @classmethod
    def create_test(cls, state, error, source, destination):
        if state.pending_ai_move is not None or not state.pick_test_mode:
            raise RuntimeError('Test no longer owns the board')
        return cls(None, None, tuple(tuple(row) for row in state.pick_test_board),
                   cls.state_token(state), str(error), owner='test',
                   test_move=(tuple(source), tuple(destination)))

    def is_current(self, state):
        if self.owner == 'test':
            return (state.pending_ai_move is None and state.pick_test_mode
                    and self.state_token(state) == self.token
                    and state.pick_test_board is not None
                    and tuple(tuple(row) for row in state.pick_test_board) == self.board
                    and not state.game_over)
        return (state.pending_ai_move is self.pending
                and pending_move_signature(state.pending_ai_move) == self.signature
                and self.state_token(state) == self.token
                and tuple(tuple(row) for row in state.board) == self.board
                and not state.game_over and state.turn == 'b')

    def message(self):
        if self.status == 'waiting_manual' and self.owner == 'test':
            return ('Stopped at HOMECHESS. Clear the gripper and restore the board. '
                    'R: retry test. T: exit test.')
        if self.status == 'waiting_manual':
            return ('Đã dừng ở HOMECHESS. Lấy quân khỏi kẹp, khôi phục bàn '
                    '(cả quân bị ăn), rút tay. R: chạy lại.')
        if self.status == 'home_failed':
            return (f'Chưa về được HOMECHESS: {self.reason}. Xử lý lỗi controller; '
                    'H: yêu cầu về HOMECHESS lại. Chưa được lấy quân/chạy lại khi tay còn chuyển động.')
        if self.status == 'retrying':
            return 'Đang thực hiện lại đúng nước đi đã khôi phục; không chọn nước mới.'
        return 'Thao tác lỗi; đang đưa tay về HOMECHESS, giữ nguyên kẹp. Chờ tay dừng.'
