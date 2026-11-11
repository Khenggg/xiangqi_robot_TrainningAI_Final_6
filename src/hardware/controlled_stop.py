"""Single-attempt controlled stop; an unknown reply requires operator recovery."""
from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class StopResult:
    safe: bool
    acknowledged: bool
    reason: str


class StopRequest:
    def __init__(self, reason):
        self.reason = reason
        self.done = threading.Event()
        self.result = None
        self.thread = None
        self.requires_measurements = False
        self.observation_only = False
        self.observed_generation = None

    def finish(self, result):
        self.result = result
        self.done.set()


class ControlledStopCoordinator:
    def __init__(self, hardware):
        self.hardware = hardware
        self._lock = threading.Lock()
        self.request = None
        self._worker_checks = []
        self.generation = 0
        self._settle_probe = None
        self._next_settle_probe = 0.0
        self.last_settle_diagnostic = None

    @property
    def blocked(self):
        """True only while the stop attempt itself is still running.

        The request used to stay latched after the attempt finished, so a single
        stop paused the game until an operator confirmed recovery. The pause now
        lasts exactly as long as the stop takes; ``request`` remains for
        diagnostics and for callers that inspect its result.
        """
        request = self.request
        return request is not None and not request.done.is_set()

    def workers_idle(self, *, ignore_current_worker=False):
        hw = self.hardware
        if hw._piece_move_lock.locked():
            return False
        worker = getattr(hw, "motion_worker", None)
        if ignore_current_worker and getattr(worker, "_thread", None) is threading.current_thread():
            return True
        return worker is None or not worker.running

    def begin(self, reason, workers_finished=None, timeout=5.0):
        with self._lock:
            self.generation += 1
            if workers_finished is not None:
                self._worker_checks.append(workers_finished)
            # A repeated click observes the original request. It never replays StopMotion.
            if self.request is not None and not getattr(self.request, 'observation_only', False):
                return self.request
            request = self.request = StopRequest(reason)
            robot = self.hardware.robot
            owned = (getattr(robot, "physical_motion_authorized", False) is True
                     or getattr(robot, "_activation_owned", False) is True)
            state = getattr(self.hardware, "game_state", None)
            uncertain_prior_motion = state is not None and (
                state.pending_move is not None or state.pending_ai_move is not None
                or state.pending_test_motion is not None
                or state.pick_test_resume_required
                # Fresh startup archives pending commands, but retains this
                # durable recovery latch until operator verification succeeds.
                or getattr(state, "recovery_required", False) is True)
            request.requires_measurements = (self.hardware.simulation_runtime is None
                                             and not self.hardware.dry_run
                                             and (owned or uncertain_prior_motion))
            latch = getattr(robot, "latch_motion_stop", None)
            if callable(latch):
                latch()
            request.thread = threading.Thread(
                target=self._run, args=(request, owned, timeout),
                name="xiangqi-controlled-stop", daemon=False)
            request.thread.start()
            return request

    def _all_workers_finished(self):
        return all(check() for check in tuple(self._worker_checks))

    def observe_operator_idle(self, *, approved=False, timeout=2.0):
        """Temporary measured proof for explicit V, without issuing a stop.

        A completed game command may fail camera verification with no stop RPC
        ever requested. Prove idle outside the lock so an urgent real stop can
        still supersede this observation. The caller must discard the receipt.
        """
        if not approved:
            raise RuntimeError('Explicit operator recovery approval required')
        with self._lock:
            if self.request is not None:
                return None  # Preserve the existing real-stop recovery path.
            generation = self.generation
        physical = self.hardware.simulation_runtime is None and not self.hardware.dry_run
        if not physical:
            return None
        self._wait_idle(timeout, True, self._all_workers_finished, ignore_current_worker=True)
        with self._lock:
            if self.generation != generation or self.request is not None:
                raise RuntimeError('Stop changed during operator observation; verify again')
            if (not self.workers_idle(ignore_current_worker=True) or not self._all_workers_finished()
                    or getattr(self.hardware.robot, '_gripper_pulse_active', False) is True):
                raise RuntimeError('Worker or gripper changed during operator observation')
            request = StopRequest('Operator observed stopped arm/gripper for board reconciliation')
            request.requires_measurements = request.observation_only = True
            request.observed_generation = generation
            request.finish(StopResult(True, False, 'Fresh idle observed; no stop command sent'))
            self.request = request
            return request

    def discard_operator_observation(self, request):
        """Remove only this scoped proof; never erase a newer real stop."""
        with self._lock:
            if (request is not None and request.observation_only
                    and self.request is request and self.generation == request.observed_generation):
                self.request = None

    def safe_for_release(self, *, ignore_current_worker=False):
        request = self.request
        if (request is None or not request.done.is_set() or not request.result.safe
                or not self.workers_idle(ignore_current_worker=ignore_current_worker)
                or not self._all_workers_finished()
                or getattr(self.hardware.robot, "_gripper_pulse_active", False) is True):
            return False
        owned_now = (getattr(self.hardware.robot, "physical_motion_authorized", False) is True
                     or getattr(self.hardware.robot, "_activation_owned", False) is True)
        if not request.requires_measurements and not (owned_now and not self.hardware.dry_run):
            return True
        # A completed stop from an earlier pause is not current idle evidence.
        try:
            snapshot = self.hardware.backend.get_state_snapshot()
            measured = snapshot.measurement_timestamp
            return (snapshot.connected and snapshot.joints_valid and measured is not None
                    and 0 <= time.time() - measured <= .5
                    and snapshot.motion_state in {"IDLE", "READY"})
        except Exception:
            return False

    def _run(self, request, owned, timeout):
        acknowledged = False
        try:
            hw = self.hardware
            physical = hw.simulation_runtime is None and not hw.dry_run
            if physical and owned:
                # Separate bounded transport: a blocking MoveCart owns the SDK lock.
                code = hw.robot.send_controlled_stop(timeout=min(2.0, timeout))
                if isinstance(code, bool) or code != 0:
                    raise RuntimeError(f"Controller rejected stop: {code}")
                acknowledged = True
            # Read-only sessions must never stop a robot controlled by the pendant.
            self._wait_idle(timeout, request.requires_measurements, self._all_workers_finished)
            request.finish(StopResult(True, acknowledged, request.reason))
        except Exception as exc:
            request.finish(StopResult(False, acknowledged, str(exc)))
            from src.core.project_logging import event
            import logging
            event("motion.stop_uncertain", str(exc), level=logging.ERROR,
                  code="STOP_RECOVERY_REQUIRED", acknowledged=acknowledged, reason=request.reason)

    def refresh_acknowledged_stop(self):
        """Read-only settling after a worker outlasts the initial stop wait.

        Never resend StopMotion or recover an unknown/unacknowledged outcome.
        Two distinct fresh idle samples must follow worker/gripper quiescence.
        """
        with self._lock:
            request = self.request
            if (request is None or not request.done.is_set() or request.result.safe
                    or not request.result.acknowledged):
                return False
            if time.monotonic() < self._next_settle_probe:
                return False
            self._next_settle_probe = time.monotonic()+.1
            try:
                workers_ready = self.workers_idle() and self._all_workers_finished()
            except Exception as exc:
                self.last_settle_diagnostic = f'Could not determine the worker state: {exc}'
                self._settle_probe = None
                return False
            if (not workers_ready or getattr(self.hardware.robot, '_gripper_pulse_active', False) is True):
                self.last_settle_diagnostic = "Worker or gripper pulse has not finished"
                self._settle_probe = None
                return False
            probe = self._settle_probe
            if probe is None or probe['request'] is not request:
                probe = self._settle_probe = dict(request=request, since=time.time(), last=None, count=0)
            try:
                snapshot = self.hardware.backend.get_state_snapshot()
                measured = snapshot.measurement_timestamp
                fresh = (snapshot.connected and snapshot.joints_valid and measured is not None
                         and measured > probe['since'] and 0 <= time.time()-measured <= .5
                         and snapshot.motion_state in {'IDLE','READY'})
                self.last_settle_diagnostic = (None if fresh else
                    f'Invalid stop telemetry: {snapshot.motion_state}; {getattr(snapshot, "stale/no measurement image", None) or "ảnh đo cũ/thiếu dữ liệu"}')
            except Exception as exc:
                self.last_settle_diagnostic = f'Could not read robot state: {exc}'
                fresh = False
            if not fresh:
                probe['count'] = 0
            elif probe['last'] is None or measured > probe['last']:
                probe['last'] = measured
                probe['count'] += 1
            if probe['count'] < 2:
                return False
            request.finish(StopResult(True, True, 'Acknowledged stop; workers and fresh idle telemetry settled'))
            self._settle_probe = None
            self.last_settle_diagnostic = None
            from src.core.project_logging import event
            event('motion.stop_settled', 'Đã xác nhận dừng sau khi worker hoàn tất; không gửi lại lệnh dừng')
            return True

    def _wait_idle(self, timeout, require_measurements, workers_finished=None, *, ignore_current_worker=False):
        deadline = time.monotonic() + timeout
        quiescent_since = None
        last_measurement = None
        samples = 0
        while time.monotonic() < deadline:
            if (not self.workers_idle(ignore_current_worker=ignore_current_worker)
                    or (workers_finished is not None and not workers_finished())
                    or getattr(self.hardware.robot, "_gripper_pulse_active", False) is True):
                quiescent_since = None
                samples = 0
            elif not require_measurements:
                return
            else:
                if quiescent_since is None:
                    # Evidence from before the last local worker exited is insufficient.
                    quiescent_since = time.time()
                snapshot = self.hardware.backend.get_state_snapshot()
                measured = snapshot.measurement_timestamp
                fresh_idle = (snapshot.connected and snapshot.joints_valid
                              and measured is not None and measured > quiescent_since
                              and 0 <= time.time() - measured <= .5
                              and snapshot.motion_state in {"IDLE", "READY"})
                if not fresh_idle:
                    samples = 0
                elif last_measurement is None or measured > last_measurement:
                    samples += 1
                    last_measurement = measured
                    if samples >= 2:
                        return
            time.sleep(.025)
        raise RuntimeError("RECOVERY_REQUIRED: stop/idle evidence incomplete; verify pendant, no automatic retry")

    def confirm_operator_stop(self, *, approved=False, timeout=2.0):
        """Read-only recheck after an operator has stopped/inspected the robot."""
        with self._lock:
            request = self.request
            if not approved or request is None or not request.done.is_set():
                raise RuntimeError("Operator approval and completed stop request required")
            if not self.workers_idle(ignore_current_worker=True) or not self._all_workers_finished():
                raise RuntimeError("Wait for local workers before operator recovery")
            # Approval includes inspection of the arm and gripper on the pendant.
            # This is operator evidence, not a measured gripper-state claim.
            self.hardware.robot._gripper_pulse_active = False
            physical = self.hardware.simulation_runtime is None and not self.hardware.dry_run
            self._wait_idle(timeout, physical, self._all_workers_finished, ignore_current_worker=True)
            request.requires_measurements = physical
            request.finish(StopResult(True, request.result.acknowledged, "Operator confirmed stopped"))
            return True

    def clear_after_recovery(self, *, ignore_current_worker=False, expected_generation=None,
                             force=False):
        """Drop the finished stop request.

        ``force`` skips the verification gate for the automatic re-enable path:
        the app no longer asks an operator to confirm recovery, so a stop whose
        reply was unconfirmed must not keep the game paused. The caller is
        expected to log that the stop was not verified.
        """
        with self._lock:
            request = self.request
            if request is None:
                return
            if force:
                if not request.done.is_set() or expected_generation is not None and                         expected_generation != self.generation:
                    raise RuntimeError("Stop still running; cannot clear the request")
            elif (not request.done.is_set() or not request.result.safe
                    or not self.safe_for_release(ignore_current_worker=ignore_current_worker)
                    or (expected_generation is not None and expected_generation != self.generation)):
                raise RuntimeError("Verified stop and finished workers required before recovery")
            self.request = None
            self._worker_checks = []
