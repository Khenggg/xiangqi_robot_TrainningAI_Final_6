import torch

from src.ai.policy_engine import (
    DIFFICULTY_ARCHITECTURES,
    PolicyEngine,
    XiangqiPolicyNet,
    encode_board,
    move_to_action,
)
from src.core import xiangqi
from src.ai.ai_controller import AIController


def test_encoder_and_move_index_are_stable():
    board = xiangqi.get_board()
    encoded = encode_board(board, "b")
    assert encoded.shape == (15, 10, 9)
    assert encoded[:, 0, 0].sum() == 1
    assert encoded[14, 0, 0] == 0
    assert move_to_action(((0, 0), (0, 1))) == 9


def test_policy_engine_masks_illegal_moves(tmp_path):
    architecture = DIFFICULTY_ARCHITECTURES["easy"]
    model = XiangqiPolicyNet(channels=architecture["channels"], residual_blocks=architecture["residual_blocks"])
    checkpoint = tmp_path / "easy.pt"
    torch.save({
        "model_state": model.state_dict(),
        "architecture": {"channels": architecture["channels"], "residual_blocks": architecture["residual_blocks"]},
        "temperature": architecture["temperature"], "top_k": architecture["top_k"],
        "difficulty": "easy", "trained": True,
    }, checkpoint)
    board = xiangqi.get_board()
    move = PolicyEngine(checkpoint, "easy").pick_best_move(board, "b")
    assert move in xiangqi.find_all_valid_moves("b", board)


def test_policy_engine_rejects_untrained_or_mismatched_checkpoints(tmp_path):
    architecture = DIFFICULTY_ARCHITECTURES["easy"]
    model = XiangqiPolicyNet(channels=architecture["channels"], residual_blocks=architecture["residual_blocks"])
    checkpoint = tmp_path / "unsafe.pt"
    torch.save({"model_state": model.state_dict(), "architecture": {"channels": architecture["channels"], "residual_blocks": architecture["residual_blocks"]}, "trained": False, "difficulty": "easy"}, checkpoint)
    try:
        PolicyEngine(checkpoint, "easy")
        assert False, "untrained checkpoint must be rejected"
    except ValueError as error:
        assert "untrained" in str(error)
    torch.save({"model_state": model.state_dict(), "architecture": {"channels": architecture["channels"], "residual_blocks": architecture["residual_blocks"]}, "trained": True, "difficulty": "medium"}, checkpoint)
    try:
        PolicyEngine(checkpoint, "easy")
        assert False, "mismatched checkpoint must be rejected"
    except ValueError as error:
        assert "difficulty" in str(error)


def test_controller_uses_selected_policy_before_other_engines():
    class Policy:
        def pick_best_move(self, board, color):
            return ((0, 0), (0, 1))

    class Config:
        AI_DIFFICULTY = "easy"
        ENGINE_TYPE = "CLOUD"

    assert AIController(None, None, Config(), policy_engine=Policy()).pick_move(xiangqi.get_board()) == ((0, 0), (0, 1))


def test_controller_uses_moonfish_when_selected_checkpoint_is_missing():
    class LocalEngine:
        def pick_best_move(self, board, color, movetime_ms):
            return ((1, 2), (1, 3))

    class Config:
        AI_DIFFICULTY = "medium"
        ENGINE_TYPE = "CLOUD"
        MOONFISH_THINK_MS = 1000

    assert AIController(LocalEngine(), None, Config()).pick_move(xiangqi.get_board()) == ((1, 2), (1, 3))


def test_hard_level_prefers_moonfish_over_cloud():
    class LocalEngine:
        def pick_best_move(self, board, color, movetime_ms):
            return ((2, 2), (2, 3))

    class CloudEngine:
        def pick_best_move(self, board, color):
            raise AssertionError("cloud must not run for Moonfish level")

    class Config:
        AI_DIFFICULTY = "hard"
        ENGINE_TYPE = "HYBRID"
        MOONFISH_THINK_MS = 1000

    assert AIController(LocalEngine(), CloudEngine(), Config()).pick_move(xiangqi.get_board()) == ((2, 2), (2, 3))


def test_hard_level_never_falls_back_to_cloud():
    class LocalEngine:
        def pick_best_move(self, board, color, movetime_ms):
            raise RuntimeError("Moonfish unavailable")

    class CloudEngine:
        def pick_best_move(self, board, color):
            raise AssertionError("cloud must not run after a Moonfish error")

    class Config:
        AI_DIFFICULTY = "hard"
        ENGINE_TYPE = "HYBRID"
        MOONFISH_THINK_MS = 1000

    assert AIController(LocalEngine(), CloudEngine(), Config()).pick_move(xiangqi.get_board()) is None
