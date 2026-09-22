"""Train an Easy or Medium policy checkpoint from teacher-labelled NPZ data."""
import argparse
from pathlib import Path
import sys

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.policy_engine import ACTION_SIZE, DIFFICULTY_ARCHITECTURES, XiangqiPolicyNet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="NPZ containing inputs [N,15,10,9] and actions [N]")
    parser.add_argument("--difficulty", choices=("easy", "medium"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    args = parser.parse_args()

    data = np.load(args.data)
    inputs = torch.from_numpy(data["inputs"]).float()
    actions = torch.from_numpy(data["actions"]).long()
    if inputs.ndim != 4 or tuple(inputs.shape[1:]) != (15, 10, 9):
        raise ValueError("inputs must have shape [N, 15, 10, 9]")
    if len(inputs) != len(actions):
        raise ValueError("inputs and actions must contain the same number of samples")
    if len(inputs) == 0:
        raise ValueError("training data must contain at least one sample")
    if torch.any(actions < 0) or torch.any(actions >= ACTION_SIZE):
        raise ValueError(f"actions must be in [0, {ACTION_SIZE})")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    architecture = DIFFICULTY_ARCHITECTURES[args.difficulty]
    model = XiangqiPolicyNet(channels=architecture["channels"], residual_blocks=architecture["residual_blocks"]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    loader = DataLoader(TensorDataset(inputs, actions), batch_size=args.batch_size, shuffle=True)
    model.train()
    for epoch in range(args.epochs):
        total_loss = 0.0
        for boards, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.cross_entropy(model(boards.to(device)), labels.to(device))
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(boards)
        print(f"epoch {epoch + 1}/{args.epochs} loss={total_loss / len(inputs):.4f}")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": model.cpu().state_dict(),
        "architecture": {"channels": architecture["channels"], "residual_blocks": architecture["residual_blocks"]},
        "temperature": architecture["temperature"], "top_k": architecture["top_k"],
        "difficulty": args.difficulty,
        "trained": True,
        "samples": len(inputs),
    }, args.output)


if __name__ == "__main__":
    main()
