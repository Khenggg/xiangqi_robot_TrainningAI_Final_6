"""Single in-process, idempotent owner for human move mutation.

Remote API synchronisation remains inside the existing GameState compatibility
method for now; the lock prevents SPACE, polling and mouse from applying the
same physical move twice in one process tick.
"""
from __future__ import annotations

import threading

from src.core import xiangqi


class HumanMoveCommitCoordinator:
    def __init__(self, game_state):
        self.state = game_state
        self._lock = threading.RLock()
        self._consumed = set()

    def try_commit(self, request, piece=None):
        # The request token identifies one turn; use it before checking the
        # mutable board so a retry after the first commit is a DUPLICATE.
        key = (request.turn_token, request.move)
        with self._lock:
            if key in self._consumed:
                return "DUPLICATE"
            if self.state.game_over or self.state.turn != "r":
                return "STALE"
            src, dst = request.move
            if not xiangqi.is_valid_move(src, dst, self.state.board, "r"):
                return "RULE_MISMATCH"
            name = piece or self.state.board[src[1]][src[0]]
            self._consumed.add(key)
            self.state.process_human_move(src, dst, name)
            return "ACCEPTED"
