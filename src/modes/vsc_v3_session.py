"""Isolated vsc-v3 Player-vs-Robot controller and a read-only showcase adapter.

The donor game owns decisions and commits. Projection failures never authorize,
reject, retry or commit a game/physical move.
"""
from copy import deepcopy
from pathlib import Path
import queue
import random
import threading
import time


class VscV3StartupError(RuntimeError):
    """Retain the owner when partial startup could not retire its resources."""
    def __init__(self, session, cause, cleanup_error):
        super().__init__(f'VSC-v3 startup recovery required: {cause}; cleanup: {cleanup_error}')
        self.session, self.cause, self.cleanup_error = session, cause, cleanup_error


def committed_piece_cells(board, history):
    """Replay stable identities, then match scanned/reset positions by symbol."""
    from src.domain.game_move import initial_piece_identities, piece_symbol_for_identity
    canonical = initial_piece_identities()
    cells = dict(canonical)
    for move in history:
        src = (move['src'][1], move['src'][0])
        dst = (move['dst'][1], move['dst'][0])
        identity = cells.pop(src, None)
        cells.pop(dst, None)
        if identity:
            cells[dst] = identity
    assigned, used = {}, set()
    for row in range(10):
        for col in range(9):
            identity = cells.get((row, col))
            if identity and piece_symbol_for_identity(identity) == board[row][col]:
                assigned[row, col] = identity
                used.add(identity)
    for row in range(10):
        for col in range(9):
            if board[row][col] == '.' or (row, col) in assigned:
                continue
            candidates = [pid for pid in canonical.values() if pid not in used
                          and piece_symbol_for_identity(pid) == board[row][col]]
            if not candidates:
                raise ValueError('Committed board contains unrepresentable piece identities')
            assigned[row, col] = candidates[0]
            used.add(candidates[0])
    return assigned


class VscV3Showcase:
    """Current 3D viewer with one borrowed SDK and committed donor positions."""
    def __init__(self, session):
        self.session = session
        self.telemetry = self.viewer = self.relay = self.runtime = None
        self.error = None
        self._last = None
        self._stop = threading.Event()
        self._updates = queue.Queue()
        self._thread = None
        self._original_move = self._original_listener = None
        self._closed = False

    def start(self):
        s = self.session
        if s.selected_mode == 'BOARD_ONLY' or getattr(s.options, 'no_viewer', False):
            return
        from src.core.launch_options import ViewerServer, check_viewer_assets
        from src.hardware.telemetry_publisher import TelemetryPublisher
        from src.digital_twin.physical_state_relay import PhysicalStateRelay
        check_viewer_assets(s.root)
        self.telemetry = TelemetryPublisher(host='127.0.0.1', port=s.config.TELEMETRY_PORT, robot_model='FR3')
        if s.config.DRY_RUN:
            from src.simulation.runtime import VirtualXiangqiSimulation
            self.runtime = VirtualXiangqiSimulation()
            self.runtime.connect()
            self.relay = PhysicalStateRelay(self.runtime.backend, self.telemetry,
                                           'VSC-v3 showcase', world=self.runtime.world, owns_world=False)
            self.telemetry.source = 'VIRTUAL'
        else:
            from src.hardware.simulation_adapter import BorrowedPhysicalStateSource
            from src.digital_twin.physical_board_display import PhysicalBoardDisplay
            from src.domain.board_pose import BoardPlacementState
            backend = BorrowedPhysicalStateSource(s.hw.robot)
            display = PhysicalBoardDisplay(s.hw.robot, s.config, BoardPlacementState.compute(0).board_surface_z_m)
            self.relay = PhysicalStateRelay(backend, self.telemetry, 'VSC-v3 measured arm', display_mapping=display)
            self._observe_physical_commands()
        self.telemetry.start()
        self.relay.start()
        self.viewer = ViewerServer(s.root, getattr(s.options, 'viewer_port', 8000))
        self.viewer.start(s.config.TELEMETRY_PORT, telemetry_available=True)
        self._thread = threading.Thread(target=self._project, name='vsc-v3-showcase', daemon=False)
        self._thread.start()

    def _observe_physical_commands(self):
        robot = self.session.hw.robot
        self._original_move = robot.move_piece
        self._original_listener = getattr(robot, 'motion_listener', None)
        def observed_gripper(*args, **kwargs):
            try:
                self.relay.animate_command_gripper(*args, **kwargs)
            except Exception as exc:
                self.error = str(exc)
        robot.motion_listener = observed_gripper

        def observed_move(sc, sr, dc, dr, capture, *args, **kwargs):
            from src.domain.game_move import MoveContext, MoveActor
            state = self.session.state
            try:
                cells = committed_piece_cells(state.board, state.move_history)
                context = MoveContext(cells[sr, sc], (sr, sc), (dr, dc), MoveActor.ROBOT,
                                      cells.get((dr, dc)) if capture else None)
                self.relay.begin_command_animation(context)
            except Exception as exc:
                self.error = str(exc)
            try:
                return self._original_move(sc, sr, dc, dr, capture, *args, **kwargs)
            finally:
                # Only the donor verifier may decide whether a move succeeded.
                try:
                    self.relay.finish_command_animation()
                except Exception as exc:
                    self.error = str(exc)
        robot.move_piece = observed_move

    def tick(self):
        state = self.session.state
        if self._closed or self.relay is None or getattr(state, 'physical_motion_busy', False) or state.ai_thinking:
            return
        board = deepcopy(state.board)
        history = deepcopy(state.move_history)
        signature = (tuple(tuple(row) for row in board),
                     tuple((tuple(m['src']), tuple(m['dst'])) for m in history))
        if signature != self._last:
            self._last = signature
            self._updates.put((board, history))

    def _project(self):
        previous_history = []
        while not self._stop.is_set():
            try:
                board, history = self._updates.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                target = committed_piece_cells(board, history)
                # Virtual arm replay is presentation AFTER donor commit, with no
                # physical SDK and no path back to the game state.
                if self.runtime is not None and len(history) == len(previous_history) + 1 and history[:-1] == previous_history:
                    from src.hardware.simulation_adapter import execute_virtual_move
                    move = history[-1]
                    src, dst = move['src'], move['dst']
                    current = dict(self.relay._cells)
                    pid = current.get((src[1], src[0]))
                    victim = current.get((dst[1], dst[0]))
                    if pid and move.get('turn') == 'b':
                        result = execute_virtual_move(self.runtime, *src, *dst, victim is not None,
                                                      piece_id=pid, captured_piece_id=victim)
                        if not result.success:
                            self.error = result.message
                if not self.relay.reconcile_to_board_cells(target):
                    self.error = 'Showcase reconciliation pending'
                    self._last = None
                previous_history = history
            except Exception as exc:
                self.error = str(exc)
                self._last = None

    def close(self):
        if self._closed:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)
            if self._thread.is_alive():
                raise RuntimeError('Showcase replay still running; retain its world until completion')
        if self._original_move is not None:
            self.session.hw.robot.move_piece = self._original_move
            self.session.hw.robot.motion_listener = self._original_listener
        for resource, method in ((self.relay, 'close'), (self.viewer, 'close'),
                                 (self.telemetry, 'stop'), (self.runtime, 'stop')):
            if resource is not None:
                getattr(resource, method)()
        self._closed = True


class VscV3Session:
    def __init__(self, config, options, root, selected_mode, *, camera_recalibration=False, cancelled=None):
        from src.modes.vsc_v3.config import configure
        self.config = configure(config, selected_mode, root, camera_recalibration=camera_recalibration)
        self.options, self.root = options, Path(root)
        self.selected_mode = selected_mode
        self.cancelled = cancelled
        self.state = self.hw = self.input = self.renderer = None
        self.showcase = VscV3Showcase(self)
        self.difficulty_active = True
        self.difficulty_message = ''
        self.wants_home = False
        self._closed = False
        self._api_end_sent = False

    def initialize(self):
        from src.modes.vsc_v3.core.game_state import GameState
        from src.modes.vsc_v3.hardware.hardware_manager import HardwareManager
        from src.modes.vsc_v3.ui.input_handler import InputHandler
        try:
            if self.cancelled is not None and self.cancelled.is_set():
                raise RuntimeError('Startup cancelled')
            self.state = GameState(allow_mouse_move=self.config.DRY_RUN)
            self.hw = HardwareManager(self.config, str(self.root))
            self.hw.startup_cancelled = self.cancelled
            self.hw.initialize_all()
            self.input = InputHandler(self.state, self.hw)
            if self.cancelled is not None and self.cancelled.is_set():
                raise RuntimeError('Startup cancelled')
            try:
                self.showcase.start()
            except Exception as exc:
                self.showcase.error = str(exc)
                # A viewer failure is never permission to change donor decisions.
                self.showcase.close()
            return self
        except Exception as error:
            try:
                self.close()
            except Exception as cleanup_error:
                raise VscV3StartupError(self, error, cleanup_error) from error
            raise

    def activate(self, screen):
        from src.modes.vsc_v3.ui.board_renderer import BoardRenderer
        self.renderer = BoardRenderer(screen)

    def draw(self, screen):
        if self.renderer is None:
            self.activate(screen)
        r, state = self.renderer, self.state
        r.draw_ui(state.get_render_state())
        r.draw_pieces(state.pick_test_board if state.pick_test_mode else state.board)
        r.draw_highlight(state.last_move, state.selected_pos, state.invalid_flash_pos, state.invalid_flash_expiry)
        if state.game_over:
            r.draw_game_over(state.winner)
        if self.difficulty_active:
            r.draw_difficulty_menu(self.hw.difficulty_availability(), self.difficulty_message)
        import pygame
        from src.ui.board_renderer import BTN_MODE_SELECT_RECT
        pygame.draw.rect(screen, (25,111,91), BTN_MODE_SELECT_RECT, border_radius=10)
        label = r.ui_font.render('MODE SELECT (Esc)', True, (255,255,255))
        screen.blit(label, label.get_rect(center=BTN_MODE_SELECT_RECT.center))

    def handle_event(self, event):
        import pygame
        from src.ui.board_renderer import BTN_MODE_SELECT_RECT
        if ((event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE)
                or (event.type == pygame.MOUSEBUTTONDOWN and BTN_MODE_SELECT_RECT.collidepoint(event.pos))):
            if getattr(self.state, 'home_recovery', None) is not None:
                self.state.set_status(self.state.home_recovery.message(), duration=3600)
                return
            if not getattr(self.state, 'physical_motion_busy', False) and not self.state.ai_thinking:
                self.wants_home = True
            else:
                self.state.set_status('Chờ worker hoàn tất trước khi đổi chế độ.', duration=10)
            return
        if self.difficulty_active:
            choice = None
            if event.type == pygame.KEYDOWN:
                choice = {pygame.K_1:'easy', pygame.K_2:'medium', pygame.K_3:'hard', pygame.K_4:'impossible'}.get(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                choice = self.renderer.difficulty_from_pixel(*event.pos)
            if choice:
                ok, reason = self.hw.select_difficulty(choice)
                if ok:
                    self.difficulty_active = False
                    self.difficulty_message = ''
                    self.state.set_status(reason, color=(0,110,70), duration=6)
                    self.hw.capture_baseline_if_needed(force_delay=1.0)
                    if not self.config.DRY_RUN:
                        self.state.api_client.create_match(red_name='Người chơi Thật', black_name='Robot AI')
                else:
                    self.difficulty_message = reason
            return
        if event.type == pygame.KEYDOWN:
            self.input.handle_keyboard(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.input.handle_mouse_down(*event.pos)

    def tick(self):
        state = self.state
        if self.hw.cam_monitor is not None:
            if self.hw.cam_monitor.update_display() == ord('q') and not getattr(state, 'physical_motion_busy', False):
                self.wants_home = True
        if self.difficulty_active:
            return
        if getattr(self.config, 'AUTO_MOVE_CONFIRM_ENABLED', False) and state.turn == 'r' and not state.game_over:
            self.input.poll_board_stability()
        if state.turn == 'b' and not state.game_over and not state.physical_sync_fault:
            self._tick_ai()
        self.showcase.tick()

    def close_display(self):
        if self.hw.cam_monitor is not None:
            self.hw.cam_monitor.close_display()

    def _tick_ai(self):
        from src.modes.vsc_v3.core import xiangqi
        state, hw = self.state, self.hw
        if state.can_start_ai_turn():
            board = deepcopy(state.board)
            state.mark_ai_turn_started()
            token = (state.game_epoch, state.ai_epoch, state.human_commit_generation)
            state.ai_job_token = token
            state.ai_thinking = True
            state.ai_think_start = time.time()
            def think():
                try:
                    state.ai_results[token] = hw.ai_ctrl.pick_move(board, color='b')
                except Exception as exc:
                    state.ai_results[token] = exc
            state.ai_thread = threading.Thread(target=think, name='vsc-v3-ai', daemon=True)
            state.ai_thread.start()
            return
        if not state.ai_thinking or state.ai_thread is None or state.ai_thread.is_alive():
            return
        state.ai_thinking, state.ai_thread = False, None
        token = state.ai_job_token
        best = state.ai_results.pop(token, None)
        state.ai_result = None
        if token != (state.game_epoch, state.ai_epoch, state.human_commit_generation):
            return
        if isinstance(best, Exception):
            state.set_status(f'AI lỗi: {best}. F5 để thử lại.', duration=30)
            return
        if not best:
            state.handle_game_over('r')
            state.api_client.end_match(winner='RED', reason='CHECKMATE')
            return
        src, dst = best
        if len(state.move_history) > 8 and [m['src'] for m in state.move_history[-6:]].count(src) >= 3:
            valid = xiangqi.find_all_valid_moves('b', state.board)
            if valid:
                src, dst = random.choice(valid)
        captured = state.board[dst[1]][dst[0]]
        expected, _ = xiangqi.make_temp_move(state.board, (src,dst))
        state.set_pending_ai_move((src,dst), expected, captured)
        from src.modes.vsc_v3.core.home_recovery import HomeRecoveryRequest
        operation = HomeRecoveryRequest.create(state, '')
        success = True
        if not self.config.DRY_RUN and not hw.robot.connected:
            success = False
            state.physical_sync_fault = state.snapshot_continue_required = True
            state.snapshot_continue_can_commit_pending = False
            self.input.begin_home_recovery(RuntimeError('Robot mất kết nối; FEN giữ nguyên'), operation=operation)
        elif not self.config.DRY_RUN and hw.robot.connected:
            try:
                if getattr(self.config, 'VISUAL_MOTION_ASYNC_ENABLED', False):
                    self.input.start_pending_ai_motion()
                    success = False
                else:
                    from src.modes.vsc_v3.core.visual_move_coordinator import execute_pending_ai_motion
                    execute_pending_ai_motion(state, hw, self.config)
            except Exception as exc:
                from src.modes.vsc_v3.vision.pick_consensus import PickTargetUnavailable
                success = False
                if isinstance(exc, PickTargetUnavailable) and exc.stage == 'pre_pick':
                    state.pause_visual_pick('ai',src,dst,exc)
                else:
                    state.physical_sync_fault = state.snapshot_continue_required = True
                    state.snapshot_continue_can_commit_pending = False
                    self.input.begin_home_recovery(exc, operation=operation)
        if success:
            state.commit_pending_ai_move()
            state.api_client.send_move_update_board(state.current_fen)
            if xiangqi.get_king_pos('r', state.board) is None:
                state.handle_game_over('b')
                state.api_client.end_match(winner='BLACK', reason='CHECKMATE')
            elif hw.robot.connected:
                hw.capture_baseline_if_needed(force_delay=1.0)
                state.set_status('Your turn!', color=(0,100,180), duration=5)
            else:
                hw.clear_yolo_baseline()
                state.set_status(f'AI: {src}→{dst} | Di quân rồi SPACE', duration=30)

    def close(self):
        if self._closed:
            return
        for worker in (getattr(self.input, '_motion_thread', None), getattr(self.state, 'ai_thread', None)):
            if worker is not None:
                worker.join(5)
                if worker.is_alive():
                    robot = getattr(self.hw, 'robot', None)
                    if (getattr(robot, '_gripper_hold_active', False) is True
                            or getattr(robot, '_gripper_pulse_active', False) is True
                            or isinstance(getattr(robot, '_gripper_stop_failure', None), BaseException)):
                        robot.stop_gripper_for_shutdown()
                    raise RuntimeError('VSC-v3 worker still owns session resources')
        self.showcase.close()
        client = getattr(self.state, 'api_client', None)
        if client is not None and not getattr(self, '_api_end_sent', False):
            # Preserve donor exit's match publication without replay on cleanup retry.
            self._api_end_sent = True
            try:
                client.end_match(reason='OTHER')
            except Exception:
                pass
        if self.hw is not None:
            self.hw.cleanup()
        if client is not None:
            close = getattr(client, 'close', None)
            if callable(close):
                close()
        self._closed = True
