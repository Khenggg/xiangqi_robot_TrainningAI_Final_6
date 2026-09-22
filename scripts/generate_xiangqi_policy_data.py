"""Generate teacher-labelled self-play positions for Easy or Medium policies."""
import argparse
from pathlib import Path
import random
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.moonfish_engine import MoonfishEngine
from src.ai.policy_engine import encode_board, move_to_action
from src.core import xiangqi


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default="moonfish/moonfish_ucci.py")
    parser.add_argument("--difficulty", choices=("easy", "medium"), required=True)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--max-plies", type=int, default=100)
    parser.add_argument("--max-teacher-fallback-rate", type=float, default=0.02)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    depth = 2 if args.difficulty == "easy" else 5
    engine = MoonfishEngine(args.engine)
    inputs, actions, teacher_fallbacks = [], [], 0
    engine.start()
    try:
        for game in range(args.games):
            board, color = xiangqi.get_board(), "r"
            for _ in range(args.max_plies):
                legal_moves = xiangqi.find_all_valid_moves(color, board)
                if not legal_moves:
                    break
                teacher_move = engine.pick_best_move(board, color, depth=depth)
                # A malformed teacher answer must never enter the training set.
                if teacher_move not in legal_moves:
                    teacher_fallbacks += 1
                    teacher_move = random.choice(legal_moves)
                inputs.append(encode_board(board, color).numpy())
                actions.append(move_to_action(teacher_move))
                board, _ = xiangqi.make_temp_move(board, teacher_move)
                color = "b" if color == "r" else "r"
            print(f"game {game + 1}/{args.games}: samples={len(inputs)} teacher_fallbacks={teacher_fallbacks}")
    finally:
        engine.stop()
    if not inputs:
        raise RuntimeError("Teacher produced no training positions")
    fallback_rate = teacher_fallbacks / len(inputs)
    if fallback_rate > args.max_teacher_fallback_rate:
        raise RuntimeError(f"Teacher fallback rate {fallback_rate:.2%} exceeds allowed {args.max_teacher_fallback_rate:.2%}")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, inputs=np.asarray(inputs, dtype=np.float32), actions=np.asarray(actions, dtype=np.int64), teacher_fallbacks=teacher_fallbacks, teacher_depth=depth)
    print(f"saved {len(inputs)} samples; teacher fallback rate={fallback_rate:.2%}")


if __name__ == "__main__":
    main()
