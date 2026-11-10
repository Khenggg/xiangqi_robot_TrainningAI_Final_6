"""Policy-driven physical startup coordination, separate from gameplay state."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicalStartupPolicy:
    camera_required: bool


@dataclass(frozen=True)
class PhysicalStartupReadiness:
    robot_connected: bool = False
    robot_telemetry_fresh: bool = False
    camera_ready: bool = False
    calibration_ready: bool = False
    board_verified: bool = False
    baseline_captured: bool = False
    enable_ready: bool = False
    blocked_reason: str | None = None
    failed_stage: str | None = None

    @property
    def ready(self):
        return (self.robot_connected and self.robot_telemetry_fresh
                and self.blocked_reason is None
                and (not self.camera_ready or (self.calibration_ready
                     and self.board_verified and self.baseline_captured)))


class PhysicalStartupOwner:
    """Run startup stages once and roll back resources opened by this attempt."""

    def __init__(self, policy: PhysicalStartupPolicy):
        self.policy = policy
        self.resources = []
        self._closers = {}
        self._close_resource = None

    def acquire(self, name, factory, closer):
        """Create and retain one physical handle; repeated names borrow it."""
        for resource_name, resource in self.resources:
            if resource_name == name:
                return resource
        resource = factory()
        if resource is None:
            raise RuntimeError(f"Physical resource unavailable: {name}")
        self.resources.append((name, resource))
        self._closers[name] = closer
        return resource

    def owns(self, name):
        return any(resource_name == name for resource_name, _ in self.resources)

    def cleanup(self, *, close_resource=None):
        """Close retained resources in reverse order; keep failed handles for retry."""
        closer = close_resource or self._close_resource
        failures = []
        remaining = []
        for name, resource in reversed(self.resources):
            try:
                (closer or self._closers[name])(resource)
            except Exception as exc:
                failures.append((name, resource, exc))
                remaining.append((name, resource))
        self.resources = list(reversed(remaining))
        if failures:
            raise RuntimeError("; ".join(str(exc) for _, _, exc in failures)) from failures[0][2]
        return True

    def start(self, *, robot, camera, telemetry=None, calibrate, verify_board, capture_baseline,
              enable_gate=None, close_resource=None):
        if self.resources:
            raise RuntimeError("PhysicalStartupOwner already owns physical resources")
        opened = self.resources
        state = dict(robot_connected=False, robot_telemetry_fresh=False,
                     camera_ready=False, calibration_ready=False,
                     board_verified=False, baseline_captured=False, enable_ready=False,
                     blocked_reason=None)
        close_resource = close_resource or (lambda resource: None)
        self._close_resource = close_resource
        stage = "robot_connect"
        try:
            robot_resource = robot()
            state["robot_connected"] = bool(robot_resource)
            if not state["robot_connected"]:
                raise RuntimeError("Physical robot connection unavailable")
            opened.append(("robot", robot_resource))

            stage = "robot_telemetry"
            if telemetry is None:
                raise RuntimeError("Fresh robot telemetry callback is required")
            state["robot_telemetry_fresh"] = bool(telemetry(robot_resource))
            if not state["robot_telemetry_fresh"]:
                raise RuntimeError("Fresh robot telemetry unavailable")

            stage = "camera_open"
            try:
                camera_resource = camera()
            except Exception as exc:
                if self.policy.camera_required:
                    raise
                state["blocked_reason"] = None
                return PhysicalStartupReadiness(**state)
            state["camera_ready"] = bool(camera_resource)
            if state["camera_ready"]:
                opened.append(("camera", camera_resource))
            elif self.policy.camera_required:
                raise RuntimeError("Physical camera unavailable")
            if state["camera_ready"]:
                stage = "camera_calibration"
                state["calibration_ready"] = bool(calibrate(robot_resource, camera_resource))
                if not state["calibration_ready"]:
                    raise RuntimeError("Physical camera calibration unavailable")
                stage = "board_verification"
                state["board_verified"] = bool(verify_board(robot_resource, camera_resource))
                if not state["board_verified"]:
                    raise RuntimeError("Physical board does not match expected position")
                stage = "baseline_capture"
                state["baseline_captured"] = bool(capture_baseline(camera_resource))
                if not state["baseline_captured"]:
                    raise RuntimeError("Fresh camera baseline unavailable")
            stage = "enable_readiness"
            state["enable_ready"] = bool(enable_gate and enable_gate(robot_resource))
            return PhysicalStartupReadiness(**state)
        except Exception as exc:
            state["failed_stage"] = stage
            state["blocked_reason"] = str(exc)
            try:
                self.cleanup()
            except Exception as close_exc:
                state["blocked_reason"] += "; cleanup failed: " + str(close_exc)
            return PhysicalStartupReadiness(**state)
