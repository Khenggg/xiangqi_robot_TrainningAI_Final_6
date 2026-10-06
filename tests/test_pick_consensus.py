"""TDD anchors for bounded metric consensus and motion-aware retries.

All camera, inference, API and robot operations are mocked; no main import.
"""
import contextlib
import copy
import importlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pygame

from src.core.game_state import GameState, pending_move_signature
from src.hardware.hardware_manager import HardwareManager
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer
from src.vision.visual_pick_estimator import GridTarget


def consensus_module():
    return importlib.import_module('src.vision.pick_consensus')


def coordinator():
    return importlib.import_module('src.core.visual_move_coordinator').execute_pending_ai_motion


def target(x_mm=0., y_mm=0., confidence=.9):
    return GridTarget(4+x_mm/31.25, 4+y_mm/31.25, confidence, np.hypot(x_mm, y_mm)/31.25)


def state_with_pending(capture=False):
    with patch('src.core.game_state.TuongKyDaiSuClient') as client:
        state = GameState()
        state.api_client = client.return_value
        state.api_client.room_id = None
    state.board = [['.' for _ in range(9)] for _ in range(10)]
    state.board[4][4] = 'b_R'
    state.board[9][4] = 'r_K'
    state.board[0][4] = 'b_K'
    if capture:
        state.board[4][6] = 'r_P'
    state.turn = 'b'
    state.update_fen_from_board()
    after = copy.deepcopy(state.board)
    after[4][6], after[4][4] = after[4][4], '.'
    state.set_pending_ai_move(((4, 4), (6, 4)), after, 'r_P' if capture else '.')
    state.game_epoch, state.ai_epoch, state.human_commit_generation = 10, 20, 30
    return state


class MetricConsensusTests(unittest.TestCase):
    def select(self, values, **kwargs):
        return consensus_module().select_consensus(values, **kwargs)

    def test_coherent_two_of_three_ignores_early_confident_outlier(self):
        result = self.select([target(14, confidence=.99), target(.2, confidence=.6), target(.4, confidence=.7)])
        self.assertIsNotNone(result.target)
        self.assertEqual(result.support, (1, 2))
        self.assertEqual(result.valid_count, 3)
        self.assertAlmostEqual((result.target.col-4)*31.25, .3)

    def test_strict_majority_recovery_keeps_original_attempt_indices(self):
        result = self.select([None, target(14), target(-.2), target(.2), None, target(.1)])
        self.assertEqual(result.support, (2, 3, 5))
        self.assertEqual(result.valid_count, 4)
        self.assertAlmostEqual((result.target.col-4)*31.25, .1)

    def test_latest_outlier_or_missing_observation_vetoes_earlier_agreement(self):
        for values in ([target(0), target(.2), target(14)], [target(0), target(.2), None]):
            with self.subTest(values=values):
                result = self.select(values)
                self.assertIsNone(result.target)

    def test_tied_maximum_support_is_rejected_even_if_latest_is_in_one_group(self):
        result = self.select([target(0), target(4), target(8)])
        self.assertIsNone(result.target)
        self.assertTrue(result.reason)

    def test_separated_groups_have_no_strict_majority(self):
        result = self.select([target(0), target(.2), target(14), target(14.2)])
        self.assertIsNone(result.target)

    def test_transitive_chain_cannot_create_a_wide_cluster(self):
        result = self.select([target(0), target(6), target(12)])
        self.assertIsNone(result.target)

    def test_chain_inside_median_radius_is_not_rejected(self):
        self.assertIsNotNone(self.select([target(0), target(3), target(6)]).target)

    def test_larger_old_group_cannot_be_replaced_with_latest_smaller_group(self):
        result = self.select([target(0), target(.1), target(.2), target(14), target(14.1)])
        self.assertIsNone(result.target)
        self.assertEqual(result.support, (0, 1, 2))

    def test_metric_radius_boundary_is_inclusive_and_next_step_rejected(self):
        result = self.select([target(0), target(7.5)])
        self.assertIsNotNone(result.target)
        self.assertAlmostEqual((result.target.col-4)*31.25, 3.75)
        self.assertIsNone(self.select([target(0), target(7.501)]).target)

    def test_metric_distance_not_grid_or_independent_axis_cutoff(self):
        self.assertIsNone(self.select([target(0, 0), target(6, 6)]).target)
        # Non-square pitch makes the same grid delta physically larger in Y.
        values = [GridTarget(4, 4, .9, 0), GridTarget(4, 4.2, .9, .2)]
        self.assertIsNone(self.select(values, pitch_mm=(31.25, 40.)).target)

    def test_empty_or_only_none_has_no_authority(self):
        for values in ([], [None], [None, None, None], [target()]):
            with self.subTest(values=values):
                self.assertIsNone(self.select(values).target)

    def test_nonfinite_observation_or_invalid_limits_raise_not_soft_consensus(self):
        bad = [GridTarget(float('nan'), 4, .9, 0), GridTarget(4, float('inf'), .9, 0),
               GridTarget(4, 4, float('nan'), 0), GridTarget(4, 4, .9, float('nan'))]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select([target(), value])
        for kwargs in ({'radius_mm': 0}, {'radius_mm': float('nan')},
                       {'pitch_mm': (0, 31.25)}, {'min_samples': 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.select([target(), target()], **kwargs)


class BoundedAcquisitionTests(unittest.TestCase):
    def hardware(self, values):
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = SimpleNamespace(VISUAL_TOP_FACE_ENABLED=True,
            VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES=3, VISUAL_PICK_CONSENSUS_MAX_SAMPLES=6,
            VISUAL_PICK_CONSENSUS_TIMEOUT_SEC=3., VISUAL_PICK_CONSENSUS_RADIUS_MM=3.75,
            VISUAL_PICK_MIN_STABLE_SAMPLES=2, VISUAL_BOARD_WIDTH_MM=250.,
            VISUAL_BOARD_HEIGHT_MM=281.25, VISUAL_PIECE_HEIGHT_MM=10.,
            VISUAL_GEOMETRY_CORNER_TOLERANCE_PX=4., VISUAL_CENTER_PICK_ATTEMPTS=3,
            VISUAL_CENTER_PICK_MAX_JITTER_CELLS=.12)
        hw.actual_camera_index, hw.perspective_path = 1, 'unused.npy'
        hw.cam_monitor = Mock()
        self.clock = SimpleNamespace(now=0.)
        self.frames = []
        def fresh():
            frame = np.full((8, 8, 3), len(self.frames), np.uint8)
            self.frames.append(frame)
            return frame, [('frame', len(self.frames))]
        hw.cam_monitor.get_fresh_pick_snapshot.side_effect = fresh
        hw.top_face_pick_estimator = Mock()
        hw.top_face_pick_estimator.geometry.profile_id = 'synthetic'
        hw.top_face_pick_estimator.geometry.grid_to_xy.side_effect = lambda p: np.asarray(p)*31.25
        hw.top_face_pick_estimator.geometry.xy_to_grid.side_effect = lambda p: np.asarray(p)/31.25
        hw.top_face_pick_estimator.last_reason = 'synthetic'
        values = iter(values)
        def extract(frame, detections, col, row):
            self.assertEqual(detections[0][1], int(frame[0, 0, 0])+1)
            return next(values)
        hw.top_face_pick_estimator.estimate_pick_target.side_effect = extract
        hw.get_visual_pick_targets = Mock()
        return hw

    def resolve(self, hw, expected_cells=None):
        with patch('src.hardware.hardware_manager.np.load', return_value=np.eye(3)), \
                patch('src.hardware.hardware_manager.time.monotonic', side_effect=lambda: self.clock.now), \
                contextlib.redirect_stdout(io.StringIO()):
            return hw.get_robot_center_pick_targets(expected_cells or {'moving': (4, 4)})

    def test_initial_three_coherent_samples_stop_without_more_reads(self):
        hw = self.hardware([target(), target(.2), target(.3)])
        self.assertIsNotNone(self.resolve(hw)['moving'])
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 3)
        hw.get_visual_pick_targets.assert_not_called()

    def test_soft_missing_samples_retry_fresh_frames_until_consensus(self):
        hw = self.hardware([None, None, target(.2), target(.3)])
        self.assertIsNotNone(self.resolve(hw)['moving'])
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 4)
        self.assertEqual(len({id(f) for f in self.frames}), 4)

    def test_six_attempt_limit_records_consensus_failure(self):
        hw = self.hardware([None]*6)
        self.assertIsNone(self.resolve(hw)['moving'])
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 6)
        self.assertEqual(hw.last_pick_resolution['failure'], 'consensus')
        self.assertEqual(hw.last_pick_resolution['attempts'], 6)

    def test_typed_transient_read_failure_is_one_missing_attempt_not_hard(self):
        hw = self.hardware([target(), target(.2)])
        fresh = hw.cam_monitor.get_fresh_pick_snapshot.side_effect
        calls = [0]
        def read():
            calls[0] += 1
            if calls[0] == 1:
                raise consensus_module().FreshPickTransientError('temporary frame timeout')
            return fresh()
        hw.cam_monitor.get_fresh_pick_snapshot.side_effect = read
        self.assertIsNotNone(self.resolve(hw)['moving'])
        self.assertEqual(calls[0], 3)

    def test_hard_geometry_or_unavailable_camera_aborts_immediately(self):
        for failure in ('camera', 'geometry'):
            hw = self.hardware([target()]*6)
            if failure == 'camera':
                hw.cam_monitor.get_fresh_pick_snapshot.side_effect = RuntimeError('camera unavailable')
            else:
                hw.top_face_pick_estimator.geometry.validate_context.side_effect = ValueError('invalid geometry')
            with self.subTest(failure=failure):
                self.assertIsNone(self.resolve(hw)['moving'])
                self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 1)
                self.assertEqual(hw.last_pick_resolution['failure'], 'hard')

    def test_late_inference_or_extraction_results_cannot_authorize_motion(self):
        for delayed_stage in ('inference', 'extraction'):
            hw = self.hardware([target()]*6)
            if delayed_stage == 'inference':
                original = hw.cam_monitor.get_fresh_pick_snapshot.side_effect
                def delayed():
                    result = original()
                    self.clock.now = 3.1
                    return result
                hw.cam_monitor.get_fresh_pick_snapshot.side_effect = delayed
            else:
                original = hw.top_face_pick_estimator.estimate_pick_target.side_effect
                def delayed(*args):
                    result = original(*args)
                    self.clock.now = 3.1
                    return result
                hw.top_face_pick_estimator.estimate_pick_target.side_effect = delayed
            with self.subTest(stage=delayed_stage):
                self.assertIsNone(self.resolve(hw)['moving'])
                self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 1)
                self.assertEqual(hw.last_pick_resolution['failure'], 'deadline')

    def test_deadline_after_consensus_discards_late_candidate(self):
        module = consensus_module()
        hw = self.hardware([target()]*6)
        actual = module.select_consensus
        def delayed(*args, **kwargs):
            result = actual(*args, **kwargs)
            self.clock.now = 3.1
            return result
        with patch('src.hardware.hardware_manager.select_consensus', side_effect=delayed):
            self.assertIsNone(self.resolve(hw)['moving'])
        self.assertEqual(hw.last_pick_resolution['failure'], 'deadline')

    def test_latest_missing_observation_requires_a_new_supported_frame(self):
        hw = self.hardware([target(), target(.2), None, target(.3)])
        self.assertIsNotNone(self.resolve(hw)['moving'])
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 4)

    def test_invalid_configuration_blocks_before_acquisition(self):
        for field, value in (('VISUAL_PICK_CONSENSUS_MAX_SAMPLES', 7),
                             ('VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES', 2),
                             ('VISUAL_PICK_CONSENSUS_TIMEOUT_SEC', float('nan'))):
            hw = self.hardware([target()]*6)
            setattr(hw.config, field, value)
            self.assertIsNone(self.resolve(hw)['moving'])
            hw.cam_monitor.get_fresh_pick_snapshot.assert_not_called()
            self.assertEqual(hw.last_pick_resolution['failure'], 'hard')

    def test_multiple_cells_must_both_support_the_same_latest_frame(self):
        hw = self.hardware([target(), target(), target(), None, None, target(), target(.1), target(.1)])
        values = self.resolve(hw, {'moving': (4, 4), 'captured': (4, 4)})
        self.assertTrue(all(t is not None for t in values.values()))
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 4)


class MotionCoordinatorTests(unittest.TestCase):
    def hardware(self):
        hw = SimpleNamespace(robot=Mock(connected=True),
            get_robot_center_pick_targets=Mock(return_value={'moving': target(), 'captured': target()}),
            is_cell_visually_clear=Mock(return_value=True), verify_visual_move=Mock(return_value=True),
            last_pick_resolution=dict(failure='', reason='', attempts=3))
        return hw

    def execute(self, state, hw, stage='pre_pick'):
        return coordinator()(state, hw, SimpleNamespace(VISUAL_PICK_ENABLED=True,
                             VISUAL_TOP_FACE_ENABLED=True), stage=stage)

    def test_pre_motion_consensus_exhaustion_retains_fen_pending_and_zero_motion(self):
        state, hw = state_with_pending(), self.hardware()
        fen, pending = state.current_fen, copy.deepcopy(state.pending_ai_move)
        hw.get_robot_center_pick_targets.return_value = {'moving': None}
        hw.last_pick_resolution = dict(failure='consensus', reason='newest outlier', attempts=6)
        with self.assertRaises(consensus_module().PickTargetUnavailable) as raised:
            self.execute(state, hw)
        self.assertEqual(raised.exception.stage, 'pre_pick')
        hw.robot.move_piece.assert_not_called()
        self.assertEqual(state.current_fen, fen)
        self.assertEqual(state.pending_ai_move, pending)

    def test_hard_target_failure_is_not_retryable(self):
        state, hw = state_with_pending(), self.hardware()
        hw.get_robot_center_pick_targets.return_value = {'moving': None}
        hw.last_pick_resolution = dict(failure='hard', reason='geometry changed', attempts=1)
        with self.assertRaises(RuntimeError) as raised:
            self.execute(state, hw)
        self.assertNotIsInstance(raised.exception, consensus_module().PickTargetUnavailable)
        hw.robot.move_piece.assert_not_called()

    def test_coordinator_motion_and_verification_never_commit_fen_themselves(self):
        state, hw = state_with_pending(), self.hardware()
        fen = state.current_fen
        self.execute(state, hw)
        hw.robot.move_piece.assert_called_once()
        hw.verify_visual_move.assert_called_once_with((4, 4), (6, 4))
        self.assertEqual(state.current_fen, fen)
        self.assertIsNotNone(state.pending_ai_move)
        state.api_client.send_move_update_board.assert_not_called()

    def test_partial_capture_source_exhaustion_tags_only_after_verified_removal(self):
        state, hw = state_with_pending(True), self.hardware()
        hw.get_robot_center_pick_targets.side_effect = [
            {'captured': target()}, {'moving': None}]
        hw.last_pick_resolution = dict(failure='consensus', reason='missing source', attempts=6)
        captured = []
        def remove_then_refresh(*args, **kwargs):
            captured.append(args)
            self.assertTrue(kwargs['verify_capture_cleared']())
            kwargs['refresh_moving_visual_target']()
        hw.robot.move_piece.side_effect = remove_then_refresh
        fen, pending = state.current_fen, copy.deepcopy(state.pending_ai_move)
        with self.assertRaises(consensus_module().PickTargetUnavailable) as raised:
            self.execute(state, hw)
        self.assertEqual(raised.exception.stage, 'capture_removed')
        self.assertTrue(captured[0][4])
        self.assertEqual(state.current_fen, fen)
        self.assertEqual(state.pending_ai_move, pending)

    def test_capture_removed_retry_rechecks_clear_and_never_replays_capture(self):
        state, hw = state_with_pending(True), self.hardware()
        state.visual_capture_checkpoint = dict(pending=state.pending_ai_move,
            signature=pending_move_signature(state.pending_ai_move),
            token=(10, 20, 30), source=(4, 4), destination=(6, 4))
        fen, pending = state.current_fen, copy.deepcopy(state.pending_ai_move)
        self.execute(state, hw, stage='capture_removed')
        hw.is_cell_visually_clear.assert_called_with((6, 4))
        hw.get_robot_center_pick_targets.assert_called_with({'moving': (4, 4)})
        self.assertFalse(hw.robot.move_piece.call_args.args[4])
        self.assertEqual(state.pending_ai_move, pending)
        self.assertEqual(state.current_fen, fen)

    def test_capture_removed_retry_blocks_if_destination_no_longer_clear(self):
        state, hw = state_with_pending(True), self.hardware()
        state.visual_capture_checkpoint = dict(pending=state.pending_ai_move,
            signature=pending_move_signature(state.pending_ai_move),
            token=(10, 20, 30), source=(4, 4), destination=(6, 4))
        hw.is_cell_visually_clear.return_value = False
        with self.assertRaises(RuntimeError) as raised:
            self.execute(state, hw, stage='capture_removed')
        self.assertNotIsInstance(raised.exception, consensus_module().PickTargetUnavailable)
        hw.robot.move_piece.assert_not_called()
        hw.get_robot_center_pick_targets.assert_not_called()

    def test_generic_motion_and_post_verification_errors_are_nonretryable(self):
        for failure in ('112 MoveCart failed', 'unknown motor fault', 'verify'):
            state, hw = state_with_pending(), self.hardware()
            fen = state.current_fen
            if failure == 'verify':
                hw.verify_visual_move.return_value = False
            else:
                hw.robot.move_piece.side_effect = RuntimeError(failure)
            with self.subTest(failure=failure), self.assertRaises(RuntimeError) as raised:
                self.execute(state, hw)
            self.assertNotIsInstance(raised.exception, consensus_module().PickTargetUnavailable)
            self.assertEqual(state.current_fen, fen)
            self.assertIsNotNone(state.pending_ai_move)

    def test_source_only_resume_requires_a_real_checkpoint(self):
        state, hw = state_with_pending(True), self.hardware()
        with self.assertRaises(RuntimeError):
            self.execute(state, hw, stage='capture_removed')
        hw.robot.move_piece.assert_not_called()
        hw.get_robot_center_pick_targets.assert_not_called()

    def test_failed_capture_clearance_cannot_create_a_checkpoint(self):
        state, hw = state_with_pending(True), self.hardware()
        hw.is_cell_visually_clear.return_value = False
        def stop(*args, **kwargs):
            self.assertFalse(kwargs['verify_capture_cleared']())
            raise RuntimeError('destination not clear')
        hw.robot.move_piece.side_effect = stop
        with self.assertRaises(RuntimeError) as raised:
            self.execute(state, hw)
        self.assertNotIsInstance(raised.exception, consensus_module().PickTargetUnavailable)
        self.assertIsNone(state.visual_capture_checkpoint)
        self.assertEqual(hw.get_robot_center_pick_targets.call_count, 1)

    def test_epoch_changed_during_measurement_blocks_motion(self):
        state, hw = state_with_pending(), self.hardware()
        def measure(*args):
            state.game_epoch += 1
            return {'moving': target()}
        hw.get_robot_center_pick_targets.side_effect = measure
        with self.assertRaises(RuntimeError):
            self.execute(state, hw)
        hw.robot.move_piece.assert_not_called()

    def test_real_motion_coordinator_capture_checkpoint_resumes_source_only(self):
        from src.hardware.robot_VIP import FR5Robot
        state, hw = state_with_pending(True), self.hardware()
        robot = FR5Robot.__new__(FR5Robot)
        robot.connected, robot.dry = True, True
        for name in ('pick_at', 'move_to_extra_safe', 'place_in_capture_bin', 'place_at', 'go_to_home_chess'):
            setattr(robot, name, Mock())
        hw.robot = robot
        captured_target = GridTarget(6, 4, .9, 0)
        hw.get_robot_center_pick_targets.side_effect = [{'captured': captured_target}, {'moving': None}]
        hw.last_pick_resolution = dict(failure='consensus', reason='source unavailable')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(consensus_module().PickTargetUnavailable) as raised:
            self.execute(state, hw)
        self.assertEqual(raised.exception.stage, 'capture_removed')
        robot.pick_at.assert_called_once_with(6, 4, visual_target=captured_target)
        robot.place_at.assert_not_called()
        state.pause_visual_pick('ai', (4, 4), (6, 4), raised.exception)
        hw.get_robot_center_pick_targets.side_effect = None
        hw.get_robot_center_pick_targets.return_value = {'moving': target()}
        hw.last_pick_resolution['failure'] = ''
        with contextlib.redirect_stdout(io.StringIO()):
            self.execute(state, hw, stage='capture_removed')
        self.assertEqual([call.args[:2] for call in robot.pick_at.call_args_list], [(6, 4), (4, 4)])
        robot.place_in_capture_bin.assert_called_once()
        robot.place_at.assert_called_once_with(6, 4)
        self.assertIsNotNone(state.pending_ai_move)  # coordinator never commits

    def test_pending_changed_during_motion_blocks_verification_and_commit(self):
        state, hw = state_with_pending(), self.hardware()
        def mutate(*args, **kwargs):
            state.pending_ai_move['expected_board'][3][3] = 'r_P'
        hw.robot.move_piece.side_effect = mutate
        with self.assertRaises(RuntimeError):
            self.execute(state, hw)
        hw.verify_visual_move.assert_not_called()
        state.api_client.send_move_update_board.assert_not_called()

    def test_main_all_motion_exception_handlers_mark_execution_unsuccessful(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).parents[1] / 'main.py').read_text(encoding='utf-8'))
        guarded = [node for node in ast.walk(tree) if isinstance(node, ast.Try)
                   and any(isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                           and isinstance(statement.value.func, ast.Name)
                           and statement.value.func.id == 'execute_pending_ai_motion'
                           for statement in node.body)]
        self.assertEqual(len(guarded), 1)
        for handler in guarded[0].handlers:
            self.assertTrue(any(isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                                and node.value.value is False and any(isinstance(t, ast.Name)
                                and t.id == 'robot_success' for t in node.targets)
                                for node in ast.walk(handler)))


class RetryOwnershipAndUiTests(unittest.TestCase):
    def pause(self, state, owner='ai', stage='pre_pick'):
        exc = consensus_module().PickTargetUnavailable('consensus weak', stage=stage)
        state.pause_visual_pick(owner, (4, 4), (6, 4), exc)
        return state.visual_pick_retry

    def handler(self, state):
        hw = SimpleNamespace(config=SimpleNamespace(VISUAL_PICK_ENABLED=True, VISUAL_TOP_FACE_ENABLED=True),
            robot=Mock(connected=True), execute_pick_place_test=Mock(return_value=target()),
            get_robot_center_pick_targets=Mock(return_value={'moving': target()}),
            verify_visual_move=Mock(return_value=True), is_cell_visually_clear=Mock(return_value=True),
            capture_baseline_if_needed=Mock(return_value=True), yolo_detector=None,
            last_pick_resolution=dict(failure='', reason='', attempts=3))
        return InputHandler(state, hw), hw

    def test_pause_binds_epochs_cells_owner_and_blocks_ai_start(self):
        state = state_with_pending()
        request = self.pause(state)
        self.assertEqual(request['token'], (10, 20, 30))
        self.assertEqual(request['source'], (4, 4))
        self.assertEqual(request['destination'], (6, 4))
        self.assertEqual(request['owner'], 'ai')
        self.assertTrue(state.visual_pick_retry_is_current())
        self.assertFalse(state.can_start_ai_turn())

    def test_changed_epoch_pending_or_test_board_invalidates_request(self):
        for field in ('game_epoch', 'ai_epoch', 'human_commit_generation', 'pending'):
            state = state_with_pending()
            self.pause(state)
            if field == 'pending':
                state.pending_ai_move['move'] = ((4, 4), (7, 4))
            else:
                setattr(state, field, getattr(state, field)+1)
            with self.subTest(field=field):
                self.assertFalse(state.visual_pick_retry_is_current())
        state = state_with_pending()
        state.pending_ai_move = None
        state.pick_test_mode = True
        state.pick_test_board = copy.deepcopy(state.board)
        self.pause(state, owner='test')
        state.pick_test_board[3][3] = 'r_P'
        self.assertFalse(state.visual_pick_retry_is_current())

    def test_changed_pending_expected_board_or_capture_metadata_invalidates_request(self):
        for changed in ('board', 'capture'):
            state = state_with_pending(True)
            self.pause(state)
            if changed == 'board':
                state.pending_ai_move['expected_board'][3][3] = 'r_P'
            else:
                state.pending_ai_move['captured_piece'] = '.'
            self.assertFalse(state.visual_pick_retry_is_current())

    def test_capture_retry_commits_once_without_repeating_removed_piece(self):
        state = state_with_pending(True)
        state.visual_capture_checkpoint = dict(pending=state.pending_ai_move, token=(10, 20, 30),
                                              signature=pending_move_signature(state.pending_ai_move),
                                              source=(4, 4), destination=(6, 4))
        self.pause(state, stage='capture_removed')
        handler, hw = self.handler(state)
        handler.handle_keyboard(pygame.K_r)
        self.assertFalse(hw.robot.move_piece.call_args.args[4])
        self.assertEqual(state.r_captured, ['r_P'])
        state.api_client.send_move_update_board.assert_called_once()
        self.assertEqual(len(state.move_log), 1)
        self.assertIsNone(state.visual_capture_checkpoint)
        handler.handle_keyboard(pygame.K_r)
        self.assertEqual(hw.robot.move_piece.call_count, 1)

    def test_retry_board_clicks_are_blocked_and_buttons_dispatch(self):
        from src.ui.board_renderer import BTN_PICK_RETRY_RECT, BTN_PICK_CANCEL_RECT
        state = state_with_pending()
        self.pause(state)
        handler, hw = self.handler(state)
        handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(4, 4))
        self.assertIsNone(state.selected_pos)
        hw.robot.move_piece.assert_not_called()
        handler.handle_mouse_down(*BTN_PICK_CANCEL_RECT.center)
        self.assertIsNone(state.visual_pick_retry)
        self.pause(state)
        handler.handle_mouse_down(*BTN_PICK_RETRY_RECT.center)
        hw.robot.move_piece.assert_called_once()

    def test_x_retains_ai_pending_and_fen_without_motion_or_commit(self):
        state = state_with_pending()
        fen, pending = state.current_fen, copy.deepcopy(state.pending_ai_move)
        self.pause(state)
        handler, hw = self.handler(state)
        handler.handle_keyboard(pygame.K_x)
        self.assertIsNone(state.visual_pick_retry)
        self.assertTrue(state.physical_sync_fault)
        self.assertEqual(state.pending_ai_move, pending)
        self.assertEqual(state.current_fen, fen)
        hw.robot.move_piece.assert_not_called()
        state.api_client.send_move_update_board.assert_not_called()

    def test_r_retries_original_ai_move_and_finalizes_exactly_once(self):
        state = state_with_pending()
        self.pause(state)
        handler, hw = self.handler(state)
        handler.handle_keyboard(pygame.K_r)
        self.assertEqual(hw.robot.move_piece.call_count, 1)
        args = hw.robot.move_piece.call_args.args
        self.assertEqual(args[:4], (4, 4, 6, 4))
        self.assertIsNone(state.pending_ai_move)
        self.assertEqual(state.board[4][6], 'b_R')
        state.api_client.send_move_update_board.assert_called_once()
        handler.handle_keyboard(pygame.K_r)
        self.assertEqual(hw.robot.move_piece.call_count, 1)
        state.api_client.send_move_update_board.assert_called_once()

    def test_api_error_after_commit_does_not_claim_old_fen_or_replay_motion(self):
        state = state_with_pending()
        fen = state.current_fen
        self.pause(state)
        state.api_client.send_move_update_board.side_effect = RuntimeError('API offline')
        handler, hw = self.handler(state)
        handler.handle_keyboard(pygame.K_r)
        self.assertNotEqual(state.current_fen, fen)
        self.assertIsNone(state.pending_ai_move)
        self.assertIsNone(state.visual_pick_retry)
        self.assertFalse(state.physical_sync_fault)
        self.assertTrue(state.manual_override_active)
        self.assertIn('FEN đã cập nhật', state.status_message)
        handler.handle_keyboard(pygame.K_r)
        self.assertEqual(hw.robot.move_piece.call_count, 1)
        state.api_client.send_move_update_board.assert_called_once()

    def test_stale_retry_cannot_acquire_move_or_finalize(self):
        state = state_with_pending()
        self.pause(state)
        state.game_epoch += 1
        handler, hw = self.handler(state)
        handler.handle_keyboard(pygame.K_r)
        hw.get_robot_center_pick_targets.assert_not_called()
        hw.robot.move_piece.assert_not_called()
        state.api_client.send_move_update_board.assert_not_called()

    def test_test_retry_routes_r_and_x_before_test_keyboard_guard(self):
        state = state_with_pending()
        state.pending_ai_move = None
        state.pick_test_mode = state.pick_test_resume_required = True
        state.pick_test_board = copy.deepcopy(state.board)
        fen = state.current_fen
        self.pause(state, owner='test')
        handler, hw = self.handler(state)
        handler.handle_keyboard(pygame.K_r)
        self.assertEqual(hw.execute_pick_place_test.call_args.args, ((4, 4), (6, 4)))
        self.assertTrue(callable(hw.execute_pick_place_test.call_args.kwargs['validate_request']))
        self.assertEqual(state.pick_test_board[4][6], 'b_R')
        self.assertEqual(state.current_fen, fen)
        state.api_client.send_move_update_board.assert_not_called()
        self.pause(state, owner='test')
        handler.handle_keyboard(pygame.K_x)
        self.assertIsNone(state.visual_pick_retry)

    def test_only_typed_pre_motion_test_failure_offers_retry(self):
        for retryable in (False, True):
            state = state_with_pending()
            state.pending_ai_move = None
            state.pick_test_mode = state.pick_test_resume_required = True
            state.pick_test_board = copy.deepcopy(state.board)
            state.selected_pos = (4, 4)
            handler, hw = self.handler(state)
            exc = (consensus_module().PickTargetUnavailable('consensus weak') if retryable
                   else RuntimeError('arm already moved but post-check failed'))
            hw.execute_pick_place_test.side_effect = exc
            handler._handle_pick_test_click(*BoardRenderer.grid_to_pixel(6, 4))
            with self.subTest(retryable=retryable):
                self.assertEqual(state.visual_pick_retry is not None, retryable)
                self.assertEqual(state.pick_test_board[4][4], 'b_R')
                self.assertEqual(state.pick_test_board[4][6], '.')


if __name__ == '__main__':
    unittest.main()
