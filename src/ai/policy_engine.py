"""Trainable, rule-safe Xiangqi policy engines.

A neural policy only ranks moves.  ``xiangqi.find_all_valid_moves`` remains the
authority for legality, which is essential before a move is sent to the robot.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import torch
from torch import nn

from src.core import xiangqi

BOARD_ROWS, BOARD_COLS = 10, 9
SQUARES = BOARD_ROWS * BOARD_COLS
ACTION_SIZE = SQUARES * SQUARES
PIECE_ORDER = (
    "b_K", "b_A", "b_E", "b_N", "b_R", "b_C", "b_P",
    "r_K", "r_A", "r_E", "r_N", "r_R", "r_C", "r_P",
)
PIECE_INDEX = {piece: index for index, piece in enumerate(PIECE_ORDER)}


def move_to_action(move: tuple[tuple[int, int], tuple[int, int]]) -> int:
    """Map a move to a stable from-square/to-square policy index."""
    (src_col, src_row), (dst_col, dst_row) = move
    return (src_row * BOARD_COLS + src_col) * SQUARES + (dst_row * BOARD_COLS + dst_col)


def encode_board(board: list[list[str]], color: str) -> torch.Tensor:
    """Return 15 planes: fourteen piece planes plus the side-to-move plane."""
    encoded = torch.zeros((15, BOARD_ROWS, BOARD_COLS), dtype=torch.float32)
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            piece = board[row][col]
            index = PIECE_INDEX.get(piece)
            if index is not None:
                encoded[index, row, col] = 1.0
    encoded[14].fill_(1.0 if color == "r" else 0.0)
    return encoded


class ResidualBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
        )
        self.activation = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.activation(x + self.layers(x))


class XiangqiPolicyNet(nn.Module):
    """Small policy-only residual CNN; capacity is selected per difficulty."""
    def __init__(self, channels: int = 64, residual_blocks: int = 4) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(15, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
        )
        self.trunk = nn.Sequential(*(ResidualBlock(channels) for _ in range(residual_blocks)))
        self.head = nn.Sequential(
            nn.Conv2d(channels, 32, 1), nn.ReLU(inplace=True), nn.Flatten(),
            nn.Linear(32 * BOARD_ROWS * BOARD_COLS, ACTION_SIZE),
        )

    def forward(self, boards: torch.Tensor) -> torch.Tensor:
        return self.head(self.trunk(self.stem(boards)))


DIFFICULTY_ARCHITECTURES = {
    "easy": {"channels": 48, "residual_blocks": 2, "temperature": 1.35, "top_k": 4},
    "medium": {"channels": 80, "residual_blocks": 5, "temperature": 0.75, "top_k": 1},
}


class PolicyEngine:
    """Inference adapter with a hard legal-move mask."""
    def __init__(self, checkpoint_path: str | Path, difficulty: str, device: str = "cpu") -> None:
        if difficulty not in DIFFICULTY_ARCHITECTURES:
            raise ValueError(f"Unsupported policy difficulty: {difficulty}")
        self.difficulty = difficulty
        self.device = torch.device(device)
        checkpoint = torch.load(Path(checkpoint_path), map_location=self.device, weights_only=True)
        if checkpoint.get("trained") is not True:
            raise ValueError("Refusing an untrained Xiangqi policy checkpoint")
        if checkpoint.get("difficulty") != difficulty:
            raise ValueError("Checkpoint difficulty does not match the selected difficulty")
        architecture = checkpoint.get("architecture", DIFFICULTY_ARCHITECTURES[difficulty])
        self.model = XiangqiPolicyNet(**{key: architecture[key] for key in ("channels", "residual_blocks")})
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.to(self.device).eval()
        self.temperature = float(checkpoint.get("temperature", DIFFICULTY_ARCHITECTURES[difficulty]["temperature"]))
        self.top_k = int(checkpoint.get("top_k", DIFFICULTY_ARCHITECTURES[difficulty]["top_k"]))

    @torch.inference_mode()
    def pick_best_move(self, board: list[list[str]], color: str, **_: object):
        legal_moves = xiangqi.find_all_valid_moves(color, board)
        if not legal_moves:
            return None
        logits = self.model(encode_board(board, color).unsqueeze(0).to(self.device))[0]
        action_ids = torch.tensor([move_to_action(move) for move in legal_moves], device=self.device)
        legal_logits = logits[action_ids]
        top_count = min(self.top_k, len(legal_moves))
        values, positions = torch.topk(legal_logits, top_count)
        if top_count == 1:
            return legal_moves[int(positions[0])]
        probabilities = torch.softmax(values / max(self.temperature, 0.01), dim=0)
        selected = torch.multinomial(probabilities, 1).item()
        return legal_moves[int(positions[selected])]


def save_initial_checkpoint(path: str | Path, difficulty: str) -> None:
    """Create an explicitly untrained checkpoint, useful to validate plumbing."""
    architecture = DIFFICULTY_ARCHITECTURES[difficulty]
    model = XiangqiPolicyNet(channels=architecture["channels"], residual_blocks=architecture["residual_blocks"])
    torch.save({
        "model_state": model.state_dict(),
        "architecture": {"channels": architecture["channels"], "residual_blocks": architecture["residual_blocks"]},
        "temperature": architecture["temperature"], "top_k": architecture["top_k"],
        "difficulty": difficulty,
        "trained": False,
    }, Path(path))
