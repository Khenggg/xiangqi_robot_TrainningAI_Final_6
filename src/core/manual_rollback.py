"""One in-memory player/AI pair, restored by the player and camera proof.

No camera, robot or persistence operations live here. Completion is called on
main UI thread only after fresh full-board verification and baseline capture.
"""
from copy import deepcopy


class ManualRollback:
    FIELDS = ('board', 'turn', 'current_fen', 'move_number', 'last_move',
              'r_captured', 'b_captured', 'move_history', 'move_log')

    def __init__(self, state):
        self.state = state
        self.active = False
        self.session_token = 0
        self._checkpoint = None
        self._post_board = None
        self._origins = {}
        self._highlighted = set()
        self._ready = False
        self._epoch = None
        self._observed = None

    @property
    def target_board(self):
        return deepcopy(self._checkpoint['board']) if self._checkpoint else None

    @property
    def post_board(self):
        return deepcopy(self._post_board)

    @property
    def eligible(self):
        s = self.state
        return bool(self._ready and self._checkpoint and not self.active
                    and self._epoch == s.game_epoch and s.board == self._post_board
                    and s.turn == 'r' and not s.game_over and not s.ai_thinking
                    and s.pending_ai_move is None and not s.physical_sync_fault
                    and not getattr(s, 'physical_motion_busy', False)
                    and not s.pick_test_mode and not s.pick_test_resume_required
                    and not s.emergency_mode and not s.visual_pick_retry)

    def invalidate(self):
        self.session_token += 1
        self.active = False
        self._checkpoint = None
        self._post_board = None
        self._ready = False
        self._origins = {}
        self._highlighted = set()
        self._observed = None

    def record_human(self, src, dst):
        """Called before the accepted normal Red mutation."""
        self.invalidate()
        s = self.state
        if (s.turn != 'r' or s.game_over or s.emergency_mode or s.pick_test_mode
                or s.physical_sync_fault or s.pending_ai_move is not None):
            return
        self._checkpoint = {name: deepcopy(getattr(s, name)) for name in self.FIELDS}
        self._epoch = s.game_epoch
        self._origins = {(c, r): {'piece': piece, 'current': (c, r)}
                         for r, row in enumerate(s.board) for c, piece in enumerate(row)
                         if piece != '.'}
        self._apply_transfer(src, dst)

    def _apply_transfer(self, src, dst):
        src, dst = tuple(src), tuple(dst)
        mover = next((origin for origin, item in self._origins.items()
                      if item['current'] == src), None)
        if mover is None:
            self.invalidate()
            return
        victim = next((origin for origin, item in self._origins.items()
                       if item['current'] == dst), None)
        if victim is not None:
            self._origins[victim]['current'] = None
            self._highlighted.add(victim)
        self._origins[mover]['current'] = dst
        self._highlighted.add(mover)

    def record_black(self, src, dst):
        """Called after the verified Black mutation and terminal-board check."""
        s = self.state
        if not self._checkpoint or self._epoch != s.game_epoch or s.game_over:
            self.invalidate()
            return
        self._apply_transfer(src, dst)
        if self._checkpoint:
            self._post_board = deepcopy(s.board)
            self._ready = True

    def begin(self):
        if not self.eligible:
            return False
        self.active = True
        self.session_token += 1
        self.state.selected_pos = None
        self.state.ai_epoch += 1
        self.state.ai_job_token = None
        self.state.ai_results = {}
        self.state.ai_retry_requested = False
        self.state.set_status('Hoàn tác: đưa quân về các vòng tròn. Camera tự xác nhận.',
                              color=(180, 100, 0), duration=3600)
        return True

    def update_observed_board(self, board):
        if (not self.active or board is None or len(board) != 10
                or any(len(row) != 9 for row in board)):
            return
        self._observed = deepcopy(board)

    observe_board = update_observed_board

    def render_state(self):
        circles = []
        if self.active:
            for origin in sorted(self._highlighted):
                item = self._origins[origin]
                side = item['piece'][0]
                current = item['current']
                if current is not None and current != origin:
                    if (self._observed is None
                            or self._observed[current[1]][current[0]] == item['piece']):
                        circles.append(dict(square=current, side=side, role='source'))
                circles.append(dict(square=origin, side=side,
                                    role='restoration' if current is None else 'destination'))
        return dict(manual_rollback_active=self.active,
                    manual_rollback_enabled=self.eligible,
                    manual_rollback_circles=circles)

    def complete(self, session_token=None):
        """Publish restored state once; caller has verified camera + baseline."""
        s = self.state
        if (not self.active or not self._checkpoint or self._epoch != s.game_epoch
                or s.board != self._post_board
                or (session_token is not None and session_token != self.session_token)):
            return False
        checkpoint = self._checkpoint
        for name, value in checkpoint.items():
            setattr(s, name, deepcopy(value))
        s.game_epoch += 1
        s.ai_epoch += 1
        s.human_commit_generation += 1
        s.ai_started_for_human_commit_generation = s.human_commit_generation
        s.ai_job_token = None
        s.ai_thread = None
        s.ai_results = {}
        s.ai_result = None
        s.ai_thinking = False
        s.ai_failure = None
        s.ai_retry_requested = False
        s.selected_pos = None
        s.visual_pick_retry = None
        s.visual_capture_checkpoint = None
        s.manual_override_active = False
        s.snapshot_continue_required = False
        s.snapshot_continue_can_commit_pending = False
        s.pending_ai_move = None
        s.physical_sync_fault = False
        s.emergency_mode = False
        self.invalidate()
        s.sync_remote_board()
        s.set_status('Đã hoàn tác — đến lượt bạn.', color=(0, 110, 70), duration=8)
        return True
