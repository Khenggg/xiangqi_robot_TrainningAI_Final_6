"""Live physical arm telemetry with nominal 3D board piece-state synchronization."""
import logging
import threading

from src.core.project_logging import event
from src.digital_twin.world_sync import sync_world_from_robot_snapshot
from src.domain.board_pose import BoardPlacementState
from src.domain.game_move import MoveActor
from src.simulation.physics.world import VirtualPhysicalWorld


class PhysicalStateRelay:
    board_sync_available = True
    uncalibrated_board = True

    def __init__(self, backend, telemetry, reason, poll_hz=25, *, world=None, owns_world=True):
        self.backend, self.telemetry, self.reason = backend, telemetry, str(reason)
        self.period_s = 1.0 / max(1.0, float(poll_hz))
        self.placement = BoardPlacementState.compute(0.0)
        self.world = world or VirtualPhysicalWorld(board_placement_state=self.placement)
        self.owns_world = owns_world
        self._lock = threading.RLock()
        self._poll_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.latest_snapshot = None
        self.last_error = self.reason
        self.recovery_required = False
        self.active_move = None
        self._command_animation = False
        self._payload_sequence = []
        self._released = []
        self._committed = set()
        self._cells = {
            (int(p["row"]), int(p["col"])): p["id"]
            for p in self.world.layout_cfg["pieces"]
        }
        if telemetry:
            telemetry.source = 'PHYSICAL'
            telemetry.controller_ip = getattr(backend, 'ip', None)
            telemetry.register_command_handler(self._reject_command)
            telemetry.broadcast_custom(self.placement.to_dict())
            self._publish_world()

    def _reject_command(self, _):
        if self.telemetry:
            self.telemetry.broadcast_custom(dict(
                type='trajectory_result',
                success=False,
                error='Physical viewer is read-only; use the game controls.',
            ))

    def _publish_world(self):
        if self.telemetry is not None:
            packet = self.world.get_snapshot().to_dict()
            packet.update(
                physical_grasp_verified=False,
                payload_evidence="NOMINAL_BOARD_STATE_MIRROR",
            )
            self.telemetry.update_world_state(packet)

    def poll_once(self):
        with self._poll_lock:
            snapshot = self.backend.get_state_snapshot()
            self.latest_snapshot = snapshot
            if getattr(snapshot, 'connected', False) and getattr(snapshot, 'joints_valid', True):
                try:
                    with self._lock, self.world._physics_lock:
                        sync_world_from_robot_snapshot(self.world, snapshot)
                        self.world.step(1)
                        self._publish_world()
                except Exception as exc:
                    event('twin.relay_world_sync_failed', str(exc), level=logging.WARNING)
            if self.telemetry:
                self.telemetry.update_from_snapshot(snapshot)
            return snapshot

    def _validate_context(self, context):
        if self._cells.get(tuple(context.src)) != context.piece_id:
            raise ValueError("Source piece identity differs from the twin's committed board")
        if self._cells.get(tuple(context.dst)) != context.captured_piece_id:
            raise ValueError("Destination occupancy differs from the semantic move")
        piece = self.world.pieces[context.piece_id]
        if context.captured_piece_id and self.world.pieces[context.captured_piece_id].side == piece.side:
            raise ValueError("Cannot capture a piece on the same side")

    def _commit_cells(self, context):
        del self._cells[tuple(context.src)]
        self._cells[tuple(context.dst)] = context.piece_id
        self._committed.add(context.move_id)

    def reconcile_human_move(self, context) -> bool:
        with self._lock, self.world._physics_lock:
            if context.actor != MoveActor.HUMAN:
                return False
            if context.move_id in self._committed:
                return True
            if self.active_move is not None:
                return False
            try:
                self._validate_context(context)
                self.world.reconcile_piece_move(
                    context.piece_id, context.dst, context.captured_piece_id
                )
                self._commit_cells(context)
                self._publish_world()
                return True
            except (KeyError, ValueError) as exc:
                self.last_error = str(exc)
                return False

    def reconcile_new_game(self) -> bool:
        cells = {
            (int(p["row"]), int(p["col"])): p["id"]
            for p in self.world.layout_cfg["pieces"]
        }
        return self.reconcile_to_board_cells(cells)

    def reconcile_to_board_cells(self, piece_cells: dict) -> bool:
        with self._lock, self.world._physics_lock:
            if self._command_animation and self.active_move is None:
                self.world.release_attached_piece()
                self._command_animation = False
            if self.active_move is not None or self.world.get_attached_piece() is not None:
                return False
            try:
                self.world.reconcile_to_board_cells(piece_cells)
            except (KeyError, TypeError, ValueError) as exc:
                self.last_error = f"Board reconciliation rejected: {exc}"
                return False
            self._cells = dict(piece_cells)
            self._committed.clear()
            self.active_move = None
            self._payload_sequence = []
            self._released = []
            self.recovery_required = False
            self._publish_world()
            return True

    def begin_command_animation(self, context):
        with self._lock:
            self.active_move = context
            self._command_animation = True
            self._released = []
            self._payload_sequence = (
                ([context.captured_piece_id] if context.captured_piece_id else [])
                + [context.piece_id]
            )

    def animate_command_gripper(self, event_name, closed):
        if event_name != 'gripper' or not self._command_animation:
            return
        try:
            self.poll_once()
            with self._lock, self.world._physics_lock:
                if (closed and self.world.get_attached_piece() is None
                        and len(self._released) < len(self._payload_sequence)):
                    piece = self.world.pieces[self._payload_sequence[len(self._released)]]
                    self.world.gripper.attach_piece(piece)
                elif not closed:
                    piece = self.world.release_attached_piece()
                    if piece is not None:
                        self._released.append(piece.piece_id)
                self._publish_world()
        except Exception as exc:
            event('twin.animation_failed', str(exc), level=logging.WARNING)

    def finish_command_animation(self):
        with self._lock:
            self.active_move = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def run():
            while not self._stop.is_set():
                try:
                    self.poll_once()
                except Exception as exc:
                    if self.telemetry:
                        self.telemetry.broadcast_custom(dict(type='twin_status', error=str(exc)))
                self._stop.wait(self.period_s)

        self._thread = threading.Thread(target=run, name='PhysicalStateRelay', daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(2)
            if self._thread.is_alive():
                raise RuntimeError('Physical telemetry reader still running; retain SDK connection')
        if self.owns_world and self.world is not None:
            self.world.close()

