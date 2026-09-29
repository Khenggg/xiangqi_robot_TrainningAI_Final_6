from src.core import xiangqi
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.hardware.robot_VIP import MotionResult, MotionStage


class _ImmediateThread:
    """Run controller workers deterministically inside this unit test."""
    def __init__(self, target, daemon=False):
        self._target = target

    def start(self):
        self._target()

    def is_alive(self):
        return False


class _State:
    def __init__(self):
        self.board = xiangqi.get_board()
        self.turn = "r"
        self.game_epoch = 0
        self.move_history = []
        self.physical_sync_fault = True
        self.pending = None

    def set_status(self, *_args, **_kwargs):
        pass

    def set_pending_physical_move(self, move, expected_after, destination, color):
        self.pending = (move, expected_after, destination, color)

    def commit_pending_physical_move(self):
        _move, expected_after, _destination, _color = self.pending
        self.board = expected_after
        self.turn = "b"
        self.move_history.append(_move)
        return True

    def handle_game_over(self, _winner):
        pass


class _Robot:
    connected = True

    def move_piece(self, *_args, **_kwargs):
        return MotionResult(True, MotionStage.COMPLETED)


class _Hardware:
    dry_run = False
    robot = _Robot()

    class ai_ctrl:
        @staticmethod
        def pick_move(board, color, difficulty):
            return xiangqi.find_all_valid_moves(color, board)[0]

    @staticmethod
    def difficulty_availability():
        return {"easy": True}

    @staticmethod
    def get_robot_center_pick_targets(expected_cells):
        return {name: None for name in expected_cells}

    @staticmethod
    def is_cell_visually_clear(_cell):
        return True

    @staticmethod
    def verify_physical_board(_board):
        raise AssertionError("self-play must not request camera/FEN verification")

    @staticmethod
    def capture_baseline_if_needed(**_kwargs):
        raise AssertionError("self-play must not capture a camera board baseline")


def test_self_play_trusts_fen_without_camera_board_verification(monkeypatch):
    monkeypatch.setattr("src.core.self_play_controller.threading.Thread", _ImmediateThread)
    state = _State()
    controller = SelfPlayController(state, _Hardware())

    assert controller.start("easy", "easy", "step")
    assert state.physical_sync_fault is False
    assert controller.request_next_move()

    controller.tick()  # Engine result -> robot motion.
    controller.tick()  # Robot result -> FEN commit.

    assert controller.status is SelfPlayStatus.READY
    assert state.turn == "b"
    assert len(state.move_history) == 1
