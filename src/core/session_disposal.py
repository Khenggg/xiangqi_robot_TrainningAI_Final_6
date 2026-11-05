"""Ordered resource retirement after the session's controlled-stop barrier."""
class SessionDisposal:
    def __init__(self, state, hardware, controller, telemetry, viewer, dashboard=None,
                 *, require_settled=True, publish_end=True):
        self.state, self.hardware, self.controller = state, hardware, controller
        self.telemetry, self.viewer, self.dashboard = telemetry, viewer, dashboard
        self._closed_steps = set()
        self._stop_proved = False
        self.require_settled = require_settled
        self.publish_end = publish_end

    def _step(self, name, operation):
        if name not in self._closed_steps:
            operation()
            self._closed_steps.add(name)

    def run(self):
        if not self._stop_proved:
            if self.hardware is not None and not self.hardware.stop_coordinator.safe_for_release():
                raise RuntimeError("Mode switch waits for verified stop")
            pending_transaction = (self.state.pending_move is not None
                                   or self.state.pending_test_motion is not None
                                   or self.state.pending_ai_move is not None
                                   or self.state.visual_capture_checkpoint is not None)
            physical_test = (self.hardware is not None and not self.hardware.dry_run
                             and self.state.pick_test_resume_required)
            if self.require_settled and (pending_transaction or physical_test):
                raise RuntimeError("Resolve pending transaction before switching modes")
            self._stop_proved = True
        if self.hardware is not None:
            self.hardware._closing = True
        if self.controller is not None:
            self._step("controller", self.controller.close)
        if self._has_pending_work() or not self.publish_end:
            # A shutdown may retain an interrupted transaction for the next launch.
            # It must not publish a finished match or discard its command receipts.
            self._step("recovery checkpoint", lambda: self.state.persist_checkpoint("RECOVERY_REQUIRED"))
        else:
            self._step("end intent", lambda: self.state.publish_match_end(
                winner=("RED" if self.state.winner == "r" else "BLACK") if self.state.game_over else "DRAW",
                reason=getattr(self.state, "game_over_reason", "OTHER") or "OTHER", retiring=True))
        self._step("projection", self.state.close_projection_worker)
        if self.hardware is not None:
            self._step("hardware", self.hardware.cleanup)
        if self.telemetry is not None:
            self._step("telemetry", self.telemetry.stop)
        if self.viewer is not None:
            self._step("viewer", self.viewer.close)
        if self.dashboard is not None:
            self._step("dashboard", self.dashboard.close)
        if callable(getattr(self.state.api_client, "close", None)):
            self._step("api", self.state.api_client.close)
        # Accepted API callbacks record room/FEN acknowledgements in this journal.
        # They must finish before its file lease and connection are released.
        self._step("journal", lambda: self.state.close_journal(clean=not self._has_pending_work()))
        return True

    def _has_pending_work(self):
        return (self.state.pending_move is not None or self.state.pending_ai_move is not None
                or self.state.pending_test_motion is not None
                or self.state.visual_capture_checkpoint is not None
                or self.state.pick_test_resume_required)
