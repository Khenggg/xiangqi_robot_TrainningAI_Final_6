"""Accept urgent UI requests while normal work is busy; defer session replacement."""
from src.core.project_logging import event


class SessionControl:
    def __init__(self, state, hardware, self_play):
        self.state = state
        self.hardware = hardware
        self.self_play = self_play
        self.action = None
        self.stop = None
        self._reported = None
        self._reset_started = False
        self._reset_done = False
        self._reset_error = None
        self._surrender_winner = None
        hardware.session_control = self

    def workers_finished(self):
        controller_thread = getattr(self.self_play, "_thread", None)
        ai_thread = getattr(self.state, "ai_thread", None)
        retired = tuple(getattr(self.state, "_retired_ai_threads", ()))
        return all(thread is None or not thread.is_alive()
                   for thread in (controller_thread, ai_thread, *retired))

    def request(self, action):
        if action not in {"pause", "reset", "quit", "home"}:
            raise ValueError("Unknown session control action")
        if self.action == "quit":
            return True
        if self.action in {"reset", "home"} and action == "pause":
            return True
        if action == "reset" and self._reset_done and self._reset_error is not None:
            # A deliberate retry after fixing storage must pass the stop/pending
            # barriers again; polling alone must never repeat a failed reset.
            self._reset_started = self._reset_done = False
            self._reset_error = None
            self._reported = None
        self.action = action
        self._reported = None
        if self.self_play is not None and self.self_play.active:
            self.self_play.end_match()
        else:
            self.state.retire_ai_job()
        self.stop = self.hardware.request_controlled_stop(
            action, workers_finished=self.workers_finished)
        event("session.stop_requested", "Request accepted; waiting for the robot to stop", action=action)
        self.state.set_status("Stopping the robot; play resumes when it has stopped.", duration=30)
        return True

    def request_surrender(self, winner):
        if winner not in {'r','b'}:
            raise ValueError('Invalid surrender winner')
        if self.state.game_over or self.action in {'reset','home','quit','surrender'}:
            return False
        self.action = 'surrender'
        self._reported = None
        self._surrender_winner = winner
        self.stop = None
        # Let a current pick/place finish. No new GUI/AI move may be admitted.
        self.state.manual_override_active = True
        self.state.snapshot_continue_required = True
        if self.state.pending_move is None and self.state.pending_ai_move is None:
            self.state.retire_ai_job()
            self.state.ai_epoch += 1
            self.state.ai_job_token = None
        event('session.surrender_requested', "Resignation accepted; waiting for the current operation to finish", winner=winner)
        self.state.set_status("Resignation accepted; waiting for the current move to finish, no new move.", duration=30)
        return True

    def _report(self, message):
        if message != self._reported:
            self._reported = message
            self.state.set_status(message, duration=60)
            event("session.control_waiting", message, action=self.action)

    def resume_virtual(self):
        hw = self.hardware
        if (self.state.game_over or self.state.mode_change_pending or self.state._match_end_intent is not None
                or (hw.simulation_runtime is None and not hw.dry_run)
                or self.action in {"reset", "quit", "home", "surrender"} or hw.motion_worker.busy
                or self.state.pending_move is not None or self.state.pending_ai_move is not None
                or self.state.pending_test_motion is not None
                or self.state.visual_capture_checkpoint is not None
                or self.state.pick_test_resume_required
                or self.state.move_sync_error or self.state.physical_sync_fault
                or not hw.stop_coordinator.safe_for_release()):
            return False
        before = (self.state.manual_override_active, self.state.snapshot_continue_required,
                  self.state.recovery_required)
        self.state.manual_override_active = False
        self.state.snapshot_continue_required = False
        self.state.recovery_required = False
        try:
            self.state.persist_checkpoint("OPERATOR_RESUMED_VIRTUAL")
            hw.stop_coordinator.clear_after_recovery()
        except Exception:
            (self.state.manual_override_active, self.state.snapshot_continue_required,
             self.state.recovery_required) = before
            raise
        self.action = None
        self._reported = None
        self.state.set_status("Simulation session resumed from the current board.", duration=10)
        return True

    def poll(self):
        """Return 'quit' only when physical stop and all local workers are settled."""
        if self.action == 'surrender' and self.stop is None:
            if not self.workers_finished() or self.hardware.motion_worker.busy:
                return None
            self.stop = self.hardware.request_controlled_stop('surrender', workers_finished=self.workers_finished)
        if self.action is None or self.stop is None or not self.stop.done.is_set():
            return None
        if not self.stop.result.safe:
            refresh = getattr(self.hardware.stop_coordinator, 'refresh_acknowledged_stop', None)
            if callable(refresh):
                refresh()
        if not self.stop.result.safe:
            self.state.physical_sync_fault = True
            self.state.snapshot_continue_can_commit_pending = False
            detail = getattr(self.hardware.stop_coordinator, 'last_settle_diagnostic', None) or self.stop.result.reason
            self._report(f"Stop not confirmed: {detail}. Check the arm/gripper and controller have stopped, then V to confirm.")
            return None
        if not self.workers_finished() or self.hardware.motion_worker.busy:
            return None
        if self.self_play is not None and self.self_play.status.value == "ending":
            return None
        if not self.hardware.stop_coordinator.safe_for_release():
            self._report("RECOVERY_REQUIRED: the stop state is stale; re-check on the pendant, then V to confirm.")
            return None
        if self.action == 'surrender':
            if (self.state.pending_move is not None or self.state.pending_ai_move is not None
                    or self.state.pending_test_motion is not None or self.state.visual_capture_checkpoint is not None):
                self._report("Stopped; resignation is waiting to reconcile the unfinished move. V only reconciles, it does not replay the move.")
                return None
            winner = self.state.winner if self.state.game_over else self._surrender_winner
            reason = (self.state.game_over_reason or 'CHECKMATE') if self.state.game_over else 'RESIGN'
            try:
                self.state.handle_game_over(winner, reason=reason)
                self.state.publish_match_end(winner='RED' if winner == 'r' else 'BLACK', reason=reason)
            except Exception as exc:
                self._report(f'Could not save the resignation result: {exc}')
                return None
            self.action = None
            self._surrender_winner = None
            self.state.set_status("Game ended by resignation. Reset the board, then NEW GAME to start a new game.", duration=60)
            event('session.surrendered', "Resignation result saved", winner=winner)
            return 'surrender'
        if self.action == "quit":
            return "quit"
        if self.action == "pause":
            self._report("Robot stopped; play resumes when the arm reports idle.")
            self.action = None
            return None
        if self._reset_done and self.action == "reset":
            if self._reset_error is not None:
                self._report(f"Reset not finished: {self._reset_error}")
                return None
            if self.hardware.simulation_runtime is not None or self.hardware.dry_run:
                self.hardware.stop_coordinator.clear_after_recovery()
            self.action = None
            self._reset_started = False
            self._reset_done = False
            self._reported = None
            return "reset"
        if (getattr(self.state, "pending_move", None) is not None
                or getattr(self.state, "pending_test_motion", None) is not None
                or getattr(self.state, "pending_ai_move", None) is not None
                or getattr(self.state, "visual_capture_checkpoint", None) is not None):
            if self.hardware.simulation_runtime is not None or self.hardware.dry_run:
                # An explicit virtual New Game may discard a settled virtual transaction.
                # This branch is unavailable to a physical board/controller.
                if not self.state.discard_stopped_virtual_work(self.hardware):
                    self._report("Could not save the simulated move cancellation; the session is kept for recovery.")
                return None
            self._report("New Game accepted; V to reconcile the pending move before switching turns. No automatic replay.")
            return None
        if self.action == "home":
            if not self.hardware.dry_run and self.state.pick_test_resume_required:
                self._report("Restore the board/New Game after the test, then select a mode; the pending session is kept.")
                return None
            if self.self_play is not None:
                self.self_play.retire_settled_session()
            return "home"
        if not self._reset_started:
            if self.self_play is not None:
                self.self_play.retire_settled_session()
            self._reset_started = True
            def completed(value, error):
                self._reset_error = error or (RuntimeError("Reset not persisted") if value is False else None)
                self._reset_done = True
            if not self.hardware.motion_worker.start(
                    lambda: self.state.reset_game(self.hardware), completed):
                self._reset_started = False
        return None
