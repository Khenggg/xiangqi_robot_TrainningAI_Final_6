import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.core import xiangqi
from src.ui.input_handler import InputHandler
from src.vision.snapshot_detector import SnapshotDetector


class HumanMoveConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.detector = SnapshotDetector("missing-perspective.npy", {})
        self.board = xiangqi.get_board()

    def test_no_changed_red_piece_is_not_a_new_human_move(self):
        recognized = [row[:] for row in self.board]
        self.assertFalse(self.detector.has_new_human_move(
            [], self.board, cchess_result={"success": True, "board": recognized}
        ))

    def test_changed_red_piece_is_a_new_human_move_even_when_illegal(self):
        recognized = [row[:] for row in self.board]
        # Red pawn moves sideways before crossing the river: a new move is
        # visible, but Xiangqi must reject it in the sufficient gate.
        recognized[6][0] = "."
        recognized[6][1] = "r_P"
        self.assertTrue(self.detector.has_new_human_move(
            [], self.board, cchess_result={"success": True, "board": recognized}
        ))
        self.assertFalse(xiangqi.is_valid_move((0, 6), (1, 6), self.board, "r"))

    def test_yolo_fallback_requires_a_red_piece_to_leave_its_baseline_square(self):
        self.detector._baseline_occ = [[False for _ in range(9)] for _ in range(10)]
        self.detector._baseline_occ[6][0] = True
        self.assertFalse(self.detector.has_new_human_move([], self.board))

    def test_malformed_cchess_result_falls_back_to_yolo_evidence(self):
        self.detector._baseline_occ = [[False for _ in range(9)] for _ in range(10)]
        self.detector._baseline_occ[6][0] = True
        current = [[False for _ in range(9)] for _ in range(10)]
        current[5][0] = True
        self.detector._build_occupancy = lambda detections: current
        self.assertTrue(self.detector.has_new_human_move(
            [], self.board, cchess_result={"success": True, "board": [["."]]}
        ))

    def test_yolo_capture_uses_visual_evidence_when_destination_occupancy_is_stable(self):
        self.detector._baseline_occ = [[False for _ in range(9)] for _ in range(10)]
        self.detector._baseline_occ[6][0] = True
        self.detector._baseline_occ[3][0] = True
        current = [[False for _ in range(9)] for _ in range(10)]
        current[3][0] = True
        self.detector._build_occupancy = lambda detections: current
        self.board[3][0] = "b_P"
        self.detector._has_capture_visual_change = lambda candidates, frame: True
        self.assertTrue(self.detector.has_new_human_move([], self.board, frame=object()))

    def test_confirmation_reports_missing_or_illegal_as_distinct_outcomes(self):
        class Detector:
            _baseline_occ = [[False for _ in range(9)] for _ in range(10)]
            _baseline_time = 0

            def __init__(self, changed):
                self.changed = changed

            def has_baseline(self):
                return True

            def detect_move(self, *args, **kwargs):
                return None, None, None

            def has_new_human_move(self, *args, **kwargs):
                if isinstance(self.changed, list):
                    return self.changed.pop(0)
                return self.changed

        class State:
            board = xiangqi.get_board()
            statuses = []
            manual_override_active = False
            turn = "r"
            game_over = False

            def save_rollback_state(self, *args):
                pass

            def set_status(self, text, **kwargs):
                self.statuses.append(text)

        class Camera:
            def get_fresh_snapshot(self):
                return None, []

        class Hardware:
            cchess_recognizer = None

            def __init__(self, changed):
                self.yolo_detector = Detector(changed)
                self.cam_monitor = Camera()

            def clear_yolo_baseline(self):
                pass

            def reset_hand_interaction_monitor(self):
                pass

        missing_state = State()
        self.assertFalse(InputHandler(missing_state, Hardware(False))._handle_space_key())
        self.assertEqual(missing_state.statuses[-1], "⚠️ No legal move could be identified.")

        invalid_state = State()
        self.assertFalse(InputHandler(invalid_state, Hardware(True))._handle_space_key())
        self.assertEqual(
            invalid_state.statuses[-1],
            "⚠️ Board changed, but one legal move could not be identified.",
        )

        retry_state = State()
        retry_handler = InputHandler(retry_state, Hardware([True, False]))
        self.assertFalse(retry_handler.try_auto_confirm_move(retries=2, retry_seconds=0))
        self.assertEqual(retry_state.statuses[-1], "❌ NƯỚC ĐI KHÔNG HỢP LỆ")

    def test_rejected_move_while_red_general_is_in_check_reports_check(self):
        class Detector:
            _baseline_occ = [[False for _ in range(9)] for _ in range(10)]
            _baseline_time = 0

            def has_baseline(self):
                return True

            def detect_move(self, *args, **kwargs):
                # Red pawn moves legally by itself, but does not answer the
                # rook check on the Red General.
                return (0, 6), (0, 5), "r_P"

        class State:
            game_over = False
            turn = "r"
            manual_override_active = False
            snapshot_continue_required = False
            snapshot_continue_can_commit_pending = False

            def __init__(self):
                self.board = [["." for _ in range(9)] for _ in range(10)]
                self.board[9][4] = "r_K"
                self.board[0][3] = "b_K"
                self.board[5][4] = "b_R"
                self.board[6][0] = "r_P"
                self.statuses = []

            def save_rollback_state(self, *args):
                pass

            def set_status(self, text, **kwargs):
                self.statuses.append(text)

            def set_invalid_flash(self, *args):
                pass

        class Camera:
            def get_fresh_snapshot(self):
                return None, []

        class Hardware:
            cchess_recognizer = None
            yolo_detector = Detector()
            cam_monitor = Camera()

            def clear_yolo_baseline(self):
                pass

        state = State()
        self.assertTrue(xiangqi.is_king_in_check("r", state.board))
        self.assertFalse(xiangqi.is_valid_move((0, 6), (0, 5), state.board, "r"))

        self.assertFalse(InputHandler(state, Hardware())._handle_space_key())
        self.assertEqual(
            "⚠️ CHECK — Your General is in check. Block, capture, or move your General.",
            state.statuses[-1],
        )


if __name__ == "__main__":
    unittest.main()
