"""Physical snapshots -> shared PyBullet world -> render-only telemetry.

This adapter never commands a robot. Payload attachment is a simulated belief
following a successful gripper command, not evidence of a physical grasp.
"""

from dataclasses import replace
import logging
import math
import threading
import time

import numpy as np

from src.domain.game_move import MoveActor
from src.digital_twin.world_sync import sync_world_from_robot_snapshot
from src.simulation.physics.world import VirtualPhysicalWorld

logger = logging.getLogger(__name__)


class LiveTwinBridge:
    def __init__(self, backend, board_pose_provider, telemetry=None, *, world=None,
                 poll_hz=25.0, max_snapshot_age_s=0.5):
        if not 1.0 <= poll_hz <= 60.0:
            raise ValueError("Twin polling rate must be between 1 and 60 Hz")
        self.backend = backend
        self.board_pose_provider = board_pose_provider
        # No virtual scene placement fallback: use exactly the motion provider.
        self.placement = board_pose_provider.get_board_placement_state()
        self.world = world or VirtualPhysicalWorld(board_placement_state=self.placement)
        if self.world.board_placement_state is not self.placement:
            raise ValueError("Twin world and motion must share the same board placement")
        self.telemetry = telemetry
        self.period_s = 1.0 / poll_hz
        self.max_snapshot_age_s = max_snapshot_age_s
        self._lock = threading.RLock()
        self._poll_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._last_measurement = -math.inf
        self.latest_snapshot = None
        self.last_error = None
        self.recovery_required = False
        self.expected_payload_id = None
        self.active_move = None
        self._payload_sequence = []
        self._released = []
        self._committed = set()
        self._cells = {(int(p["row"]), int(p["col"])): p["id"]
                       for p in self.world.layout_cfg["pieces"]}
        self.tcp_position_error_mm = None
        if telemetry is not None:
            telemetry.source = "PHYSICAL" if not getattr(backend, "dry_run", False) else "PHYSICAL_DRY_RUN"
            telemetry.controller_ip = getattr(backend, "ip", None)
            # The viewer has no physical motion authority in this mode.
            telemetry.register_command_handler(self._reject_viewer_command)
            telemetry.broadcast_custom(self.placement.to_dict())

    def _reject_viewer_command(self, command):
        if self.telemetry is not None:
            self.telemetry.broadcast_custom({
                "type": "trajectory_result", "success": False,
                "error": "Physical Digital Twin is read-only; use the authorized game motion pipeline.",
            })

    def _fail(self, message, *, recovery=False):
        self.last_error = str(message)
        self.recovery_required |= recovery
        if self.telemetry is not None:
            self.telemetry.broadcast_custom({"type": "twin_status", "error": self.last_error,
                                             "recovery_required": self.recovery_required,
                                             "physical_grasp_verified": False})
        return False

    def _publish_world(self):
        if self.telemetry is not None:
            packet = self.world.get_snapshot().to_dict()
            packet.update(physical_grasp_verified=False, payload_evidence="COMMAND_AND_SIMULATED_GEOMETRY")
            self.telemetry.update_world_state(packet)

    def sync_robot_state(self, snapshot):
        with self._lock, self.world._physics_lock:
            measured = getattr(snapshot, "measurement_timestamp", None)
            measured = snapshot.timestamp if measured is None else measured
            if (not snapshot.connected or not getattr(snapshot, "joints_valid", True)
                    or not math.isfinite(measured) or time.time() - measured > self.max_snapshot_age_s):
                return self._fail("Actual joint telemetry unavailable or stale", recovery=self.active_move is not None)
            if measured < self._last_measurement:
                return False  # Out-of-order read must never restore an older joint pose.
            if self.board_pose_provider.get_board_placement_state() is not self.placement:
                return self._fail("Physical board calibration changed; restart/reconcile the twin", recovery=True)
            sync_world_from_robot_snapshot(self.world, snapshot)
            self._last_measurement = measured
            self.latest_snapshot = snapshot
            tcp = np.asarray(snapshot.tcp_pose_mm_deg[:3], dtype=float)
            self.tcp_position_error_mm = (
                float(np.linalg.norm(tcp - self.world.gripper.tcp_pos * 1000.0))
                if getattr(snapshot, "tcp_valid", True) and np.all(np.isfinite(tcp)) else None
            )
            self.world.step(1)
            if self.telemetry is not None:
                self.telemetry.update_from_snapshot(replace(snapshot, placement_version=self.placement.placement_version))
                self._publish_world()
            # A real error does not roll back joints or teleport payloads to targets.
            if snapshot.motion_state in ("ERROR", "DISCONNECTED", "ESTOP", "STOPPED"):
                return self._fail(snapshot.last_error or snapshot.motion_state, recovery=self.active_move is not None)
            elif not self.recovery_required:
                self.last_error = None
            return True

    def poll_once(self):
        # Serializes reads with command-edge callbacks, never with MoveJ/MoveCart.
        with self._poll_lock:
            return self.sync_robot_state(self.backend.get_state_snapshot())

    def _run(self):
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.poll_once()
            except Exception as exc:
                with self._lock:
                    self._fail(f"Twin telemetry read failed: {exc}", recovery=self.active_move is not None)
            self._stop.wait(max(0.001, self.period_s - (time.monotonic() - started)))

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="PhysicalTwinReader", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                raise RuntimeError("Twin reader has not stopped; retain world until its read finishes")

    def close(self):
        self.stop()
        self.world.close()

    def _validate_context(self, context):
        if self._cells.get(tuple(context.src)) != context.piece_id:
            raise ValueError("Source piece identity differs from the twin's committed board")
        if self._cells.get(tuple(context.dst)) != context.captured_piece_id:
            raise ValueError("Destination occupancy differs from the semantic move")
        piece = self.world.pieces[context.piece_id]
        expected_side = "r" if context.actor == MoveActor.HUMAN else "b"
        if piece.side != expected_side:
            raise ValueError("Move actor does not match the moving piece")
        if context.captured_piece_id and self.world.pieces[context.captured_piece_id].side == piece.side:
            raise ValueError("Cannot capture a piece on the same side")

    def _commit_cells(self, context):
        del self._cells[tuple(context.src)]
        self._cells[tuple(context.dst)] = context.piece_id
        self._committed.add(context.move_id)

    def reconcile_human_move(self, context):
        with self._lock, self.world._physics_lock:
            if context.actor != MoveActor.HUMAN:
                return self._fail("Only HUMAN moves may reconcile piece positions")
            if context.move_id in self._committed:
                return True
            if self.active_move is not None or self.recovery_required:
                return self._fail("Scene requires recovery before accepting a human move")
            try:
                self._validate_context(context)
                self.world.reconcile_piece_move(context.piece_id, context.dst, context.captured_piece_id)
                self._commit_cells(context)
                self._publish_world()
                return True
            except (KeyError, ValueError) as exc:
                return self._fail(exc, recovery=True)

    def begin_robot_move(self, context):
        if not self.poll_once():
            return False
        with self._lock:
            if context.actor != MoveActor.ROBOT or self.active_move is not None or self.recovery_required:
                return self._fail("Robot move unavailable: actor, pending move, or recovery state")
            if context.move_id in self._committed:
                return self._fail("Robot move already executed")
            if self.latest_snapshot.motion_state not in ("IDLE", "READY"):
                return self._fail("Physical robot is not idle")
            try:
                self._validate_context(context)
            except (KeyError, ValueError) as exc:
                return self._fail(exc, recovery=True)
            self.active_move = context
            self._released = []
            self._payload_sequence = ([context.captured_piece_id] if context.captured_piece_id else []) + [context.piece_id]
            return True

    def set_expected_payload(self, piece_id):
        with self._lock:
            if (self.active_move is None or self.recovery_required
                    or len(self._released) >= len(self._payload_sequence)
                    or piece_id != self._payload_sequence[len(self._released)]):
                return self._fail("Payload ID does not match the pending capture/move sequence", recovery=True)
            if self.world.get_attached_piece() is not None:
                return self._fail("Previous payload has not been released", recovery=True)
            self.expected_payload_id = piece_id
            return True

    def on_gripper_closed(self, piece_id):
        if not self.poll_once():
            return False
        with self._lock, self.world._physics_lock:
            if self.recovery_required or piece_id != self.expected_payload_id or not self.latest_snapshot.gripper_closed:
                return self._fail("Gripper close lacks its expected payload/command state", recovery=True)
            result = self.world.try_grasp(target_piece_id=piece_id)
            if not result.success:
                return self._fail(f"Twin attachment failed: {result.reason}", recovery=True)
            self._publish_world()
            return True

    def on_gripper_opened(self):
        if not self.poll_once():
            return False
        with self._lock, self.world._physics_lock:
            if self.latest_snapshot.gripper_closed:
                return self._fail("Gripper open command has not succeeded", recovery=True)
            attached = self.world.get_attached_piece()
            self.world.release_attached_piece()
            if attached is not None:
                if attached.piece_id != self.expected_payload_id:
                    return self._fail("Released payload identity mismatch", recovery=True)
                self._released.append(attached.piece_id)
                self.expected_payload_id = None
                self.world.step_until_settled(max_steps=120)
            self._publish_world()
            return not self.recovery_required

    def end_robot_move(self, context, success):
        # Keep the latest actual joints even when the execution failed.
        fresh = self.poll_once()
        with self._lock, self.world._physics_lock:
            if self.active_move != context:
                return self._fail("Pending robot move mismatch", recovery=True)
            verified = bool(success and fresh and not self.recovery_required
                            and self._released == self._payload_sequence
                            and self.world.get_attached_piece() is None
                            and self.latest_snapshot.motion_state in ("IDLE", "READY"))
            if verified:
                piece = self.world.pieces[context.piece_id]
                row, col, distance = piece.get_nearest_intersection()
                # Simulated landing check only; not a hardware grasp sensor.
                verified = (row, col) == tuple(context.dst) and distance < piece.radius_m
                if context.captured_piece_id:
                    pos = self.world.pieces[context.captured_piece_id].get_position_robot()
                    verified &= not self.placement.is_in_bounds_robot(pos)
            self.active_move = None
            if not verified:
                return self._fail("Physical execution or twin placement incomplete; recovery required", recovery=True)
            self._commit_cells(context)
            self._publish_world()
            return True
