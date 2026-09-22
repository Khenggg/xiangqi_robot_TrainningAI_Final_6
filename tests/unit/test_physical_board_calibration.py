"""
Unit tests for Physical Board Pose Calibration Safety and Frame Validation.

Validates the full 17-test Acceptance Matrix from the corrective task specification:
1. Known rigid transform reconstruction
2. Noisy rigid transform reconstruction
3. All 90 cell round-trip
4. Missing R point fails
5. Bad dimensions fail for correct reason
6. Swapped corners fail
7. Frame mismatch fails
8. Known teaching TCP offset reconstructs board surface
9. Tilted but coplanar board succeeds
10. Non-coplanar point fails
11. Physical calibration failure disables motion
12. No motion command occurs before calibration success
13. Physical backend requires explicit calibrated provider
14. Virtual provider remains hardware-independent
15. Pick height uses MotionProfile
16. Safe clearance remains board-relative
17. Old 218 mm cache assumption removed
"""

import math
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.domain.board_pose import (
    BoardPlacementState,
    compute_rotation_matrix,
    rot_matrix_to_quat,
)
from src.domain.board_pose_provider import (
    BoardCalibrationResult,
    BoardCalibrationProfile,
    BoardCalibrationTolerancePolicy,
    TeachingPointObservation,
    parse_teaching_point_observation,
    BoardPoseProvider,
    FixedBoardPoseProvider,
    PhysicalTeachingPointBoardPoseProvider,
    calibrate_board_from_teaching_points,
    CANONICAL_WIDTH_MM,
    CANONICAL_LENGTH_MM,
    CANONICAL_THICKNESS_MM,
    CANONICAL_DIAGONAL_MM,
)
from src.motion.coordinator import MotionCoordinator, MotionProfile
from src.hardware.backends import PhysicalFR3Backend, VirtualFR3Backend
from src.hardware.hardware_manager import HardwareManager


# Standard nominal teaching points forming a canonical 320x360mm board at Z=18.0mm
# Under 90-degree yaw convention:
# R1 = (col 0, row 0) -> u=-160, v=-180 -> robot x = center_x + 160, robot y = center_y + 180
# Center at (-120.0, 0.0, 18.0)
NOMINAL_TEACHING_POINTS = {
    "R1": [40.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
    "R2": [-280.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
    "R3": [-280.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
    "R4": [40.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
}


class TestPhysicalBoardCalibration:

    # -------------------------------------------------------------------------
    # Matrix #1: Known rigid transform reconstruction
    # -------------------------------------------------------------------------
    def test_known_rigid_transform_reconstruction(self):
        """
        Matrix #1:
        Synthesize R1-R4 from an arbitrary known 3D rigid transform (translation + yaw + pitch + roll),
        pass to calibration algorithm, and verify estimated transform recovers ground truth.
        """
        p_gt = np.array([-0.145, 0.035, 0.022], dtype=float)

        theta_z = math.radians(92.5)
        theta_y = math.radians(0.8)
        theta_x = math.radians(-0.6)

        R_x = np.array([
            [1.0, 0.0, 0.0],
            [0.0, math.cos(theta_x), -math.sin(theta_x)],
            [0.0, math.sin(theta_x), math.cos(theta_x)],
        ])
        R_y = np.array([
            [math.cos(theta_y), 0.0, math.sin(theta_y)],
            [0.0, 1.0, 0.0],
            [-math.sin(theta_y), 0.0, math.cos(theta_y)],
        ])
        R_z = np.array([
            [math.cos(theta_z), -math.sin(theta_z), 0.0],
            [math.sin(theta_z), math.cos(theta_z), 0.0],
            [0.0, 0.0, 1.0],
        ])
        R_0 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        R_gt = R_z @ R_y @ R_x @ R_0

        local_corners = {
            "R1": np.array([-0.160, -0.180, 0.0]),
            "R2": np.array([0.160, -0.180, 0.0]),
            "R3": np.array([0.160, 0.180, 0.0]),
            "R4": np.array([-0.160, 0.180, 0.0]),
        }

        synth_points = {}
        for name, p_local in local_corners.items():
            p_robot_m = p_gt + R_gt @ p_local
            synth_points[name] = list(p_robot_m * 1000.0)

        result = calibrate_board_from_teaching_points(synth_points)

        assert result.success is True, f"Calibration failed: {result.error_message}"
        assert result.state is not None
        assert result.rms_error_mm < 0.05
        assert result.max_error_mm < 0.05

        state = result.state
        assert state.board_center_robot_m[0] == pytest.approx(p_gt[0], abs=1e-4)
        assert state.board_center_robot_m[1] == pytest.approx(p_gt[1], abs=1e-4)
        assert state.board_surface_z_robot_m == pytest.approx(p_gt[2], abs=1e-4)

        R_est = state.R_robot_from_board
        rot_diff = np.linalg.norm(R_est - R_gt)
        assert rot_diff < 1e-3, f"Rotation matrix difference too large: {rot_diff}"

    # -------------------------------------------------------------------------
    # Matrix #2: Noisy rigid transform reconstruction
    # -------------------------------------------------------------------------
    def test_noisy_rigid_transform_reconstruction(self):
        """
        Matrix #2:
        Add small realistic measurement noise (+/- 0.5mm) to known rigid transform
        and verify calibration succeeds within warning bounds.
        """
        noisy_points = {
            "R1": [40.4, 179.7, 18.2],
            "R2": [-279.6, 180.3, 17.8],
            "R3": [-280.3, -179.6, 18.1],
            "R4": [39.7, -180.2, 17.9],
        }

        result = calibrate_board_from_teaching_points(noisy_points)
        assert result.success is True
        assert result.state is not None
        assert result.rms_error_mm <= 1.0
        assert result.max_error_mm <= 1.5

        state = result.state
        assert state.board_surface_z_robot_m == pytest.approx(0.018, abs=1e-3)
        assert state.board_center_robot_m[0] == pytest.approx(-0.120, abs=1e-3)
        assert state.board_center_robot_m[1] == pytest.approx(0.0, abs=1e-3)

    # -------------------------------------------------------------------------
    # Matrix #3: All 90 cell round-trip
    # -------------------------------------------------------------------------
    def test_all_90_cell_round_trip(self):
        """
        Matrix #3:
        Test that all 90 canonical cells are generated from the single rigid BoardPlacementState
        and invert back to the exact same continuous row and col.
        """
        result = calibrate_board_from_teaching_points(NOMINAL_TEACHING_POINTS)
        assert result.success is True
        state = result.state

        cell_count = 0
        for r in range(10):
            for c in range(9):
                p_robot = state.cell_to_robot_xyz(r, c, z_rel_m=0.0)
                nearest_r, nearest_c, dist_m = state.robot_xyz_to_nearest_cell(p_robot)

                assert nearest_r == r, f"Row mismatch for cell ({r}, {c}): got {nearest_r}"
                assert nearest_c == c, f"Col mismatch for cell ({r}, {c}): got {nearest_c}"
                assert dist_m < 1e-4, f"Distance error too large for cell ({r}, {c}): {dist_m}"
                cell_count += 1

        assert cell_count == 90

    # -------------------------------------------------------------------------
    # Matrix #4: Missing R point fails
    # -------------------------------------------------------------------------
    def test_missing_r_point_fails(self):
        """
        Matrix #4:
        Missing R-point or controller read error must fail fast and not authorize motion.
        """
        # Case A: Missing key in dictionary
        incomplete = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-280.0, 180.0, 18.0],
            "R3": [-280.0, -180.0, 18.0],
        }
        res = calibrate_board_from_teaching_points(incomplete)
        assert res.success is False
        assert "Missing required teaching point" in res.error_message

        provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(incomplete)
        assert provider.is_calibrated is False
        with pytest.raises(RuntimeError):
            provider.get_board_placement_state()

        # Case B: Controller read error
        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.get_teaching_point.side_effect = lambda name: (0, [40.0, 180.0, 18.0]) if name != "R2" else (-1, [])
        provider_ctrl = PhysicalTeachingPointBoardPoseProvider.from_controller(mock_backend)
        assert provider_ctrl.is_calibrated is False
        assert "Controller failed to read teaching point 'R2'" in provider_ctrl.calibration_result.error_message

    # -------------------------------------------------------------------------
    # Matrix #5: Bad dimensions fail for correct reason
    # -------------------------------------------------------------------------
    def test_bad_dimensions_fail_for_correct_reason(self):
        """
        Matrix #5:
        Verify dimension errors fail specifically for the intended reason and report measured values.
        """
        # Bad width = 100 mm (expected 320 mm)
        bad_width = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-60.0, 180.0, 18.0],   # Width: 40 - (-60) = 100.0 mm
            "R3": [-60.0, -180.0, 18.0],
            "R4": [40.0, -180.0, 18.0],
        }
        res_w = calibrate_board_from_teaching_points(bad_width)
        assert res_w.success is False
        assert res_w.measured_width_mm == pytest.approx(100.0, abs=1.0)
        assert "width mismatch" in res_w.error_message.lower()

        # Bad length = 200 mm (expected 360 mm)
        bad_length = {
            "R1": [40.0, 100.0, 18.0],
            "R2": [-280.0, 100.0, 18.0],
            "R3": [-280.0, -100.0, 18.0],  # Length: 100 - (-100) = 200.0 mm
            "R4": [40.0, -100.0, 18.0],
        }
        res_l = calibrate_board_from_teaching_points(bad_length)
        assert res_l.success is False
        assert res_l.measured_length_mm == pytest.approx(200.0, abs=1.0)
        assert "length mismatch" in res_l.error_message.lower()

    # -------------------------------------------------------------------------
    # Matrix #6: Swapped corners fail
    # -------------------------------------------------------------------------
    def test_swapped_corners_fail(self):
        """
        Matrix #6:
        Swapped corners (inverted quadrilateral or inverted normal) must fail calibration.
        """
        # Swapped R2 and R4
        swapped = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [40.0, -180.0, 18.0],  # Swapped with R4
            "R3": [-280.0, -180.0, 18.0],
            "R4": [-280.0, 180.0, 18.0],  # Swapped with R2
        }
        res_swapped = calibrate_board_from_teaching_points(swapped)
        assert res_swapped.success is False
        assert (
            "asymmetry" in res_swapped.error_message.lower()
            or "residual" in res_swapped.error_message.lower()
            or "normal" in res_swapped.error_message.lower()
            or "width mismatch" in res_swapped.error_message.lower()
            or "mismatch" in res_swapped.error_message.lower()
        )

        # Inverted corner ordering (normal points downward: z < 0.707)
        inverted = {
            "R1": [40.0, -180.0, 18.0],
            "R2": [-280.0, -180.0, 18.0],
            "R3": [-280.0, 180.0, 18.0],
            "R4": [40.0, 180.0, 18.0],
        }
        res_inv = calibrate_board_from_teaching_points(inverted)
        assert res_inv.success is False
        assert "normal" in res_inv.error_message.lower()

    # -------------------------------------------------------------------------
    # Matrix #7: Frame mismatch fails
    # -------------------------------------------------------------------------
    def test_frame_mismatch_fails(self):
        """
        Matrix #7:
        R1-R4 must belong to the exact same tool and user/wobj frame.
        """
        # Case A: R3 different tool
        tool_mismatch = {
            "R1": [40.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "R2": [-280.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "R3": [-280.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 1, 0],  # tool = 1
            "R4": [40.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
        }
        res_tool = calibrate_board_from_teaching_points(tool_mismatch)
        assert res_tool.success is False
        assert "teaching point frame mismatch" in res_tool.error_message.lower()
        assert "R3 tool=1" in res_tool.error_message

        # Case B: R2 different wobj/user frame
        wobj_mismatch = {
            "R1": [40.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "R2": [-280.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 2],  # wobj = 2
            "R3": [-280.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "R4": [40.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
        }
        res_wobj = calibrate_board_from_teaching_points(wobj_mismatch)
        assert res_wobj.success is False
        assert "teaching point frame mismatch" in res_wobj.error_message.lower()
        assert "R2 wobj=2" in res_wobj.error_message

        # Case C: All points in user frame != 0 (non-base frame)
        non_base = {
            "R1": [40.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 1],
            "R2": [-280.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 1],
            "R3": [-280.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 1],
            "R4": [40.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 1],
        }
        res_nb = calibrate_board_from_teaching_points(non_base)
        assert res_nb.success is False
        assert "user frame" in res_nb.error_message.lower()
        assert "robot base" in res_nb.error_message.lower()

    # -------------------------------------------------------------------------
    # Matrix #8: Known teaching TCP offset reconstructs board surface
    # -------------------------------------------------------------------------
    def test_known_teaching_tcp_offset_reconstructs_board_surface(self):
        """
        Matrix #8:
        Synthetic example:
          True board surface Z = 20.0 mm
          Teaching TCP is 10 mm above board (Z = 30.0 mm)
          Offset in robot frame = [0, 0, -10] mm
          Calibrated board surface must accurately be reconstructed at Z = 20.0 mm.
        """
        # Teaching TCP at Z = 30.0 mm
        elevated_tcp_points = {
            "R1": [40.0, 180.0, 30.0],
            "R2": [-280.0, 180.0, 30.0],
            "R3": [-280.0, -180.0, 30.0],
            "R4": [40.0, -180.0, 30.0],
        }

        profile = BoardCalibrationProfile(
            tcp_to_board_contact_offset_mm=[0.0, 0.0, -10.0],
            offset_frame="ROBOT_BASE",
            provenance="CALIBRATION_FIXTURE_KNOWN_OFFSET",
            description="10mm downward offset to true board surface",
        )

        result = calibrate_board_from_teaching_points(
            elevated_tcp_points,
            calibration_profile=profile,
        )

        assert result.success is True
        assert result.state is not None
        # Must reconstruct true surface Z = 20.0 mm (0.020 m)
        assert result.state.board_surface_z_robot_m == pytest.approx(0.020, abs=1e-4)

    # -------------------------------------------------------------------------
    # Matrix #9: Tilted but coplanar board succeeds
    # -------------------------------------------------------------------------
    def test_tilted_but_coplanar_board_succeeds(self):
        """
        Matrix #9:
        A rigid plane tilted at ~1.5 deg has corners with different raw Z coordinates,
        but the orthogonal point-to-plane residual is 0.0 mm.
        Must succeed without false rejection from naive Z range check.
        """
        # Tilted plane: z = 18.0 + 0.02 * (x - 40.0) + 0.03 * (y - 180.0)
        # R1: x=40, y=180 -> z = 18.0
        # R2: x=-280, y=180 -> z = 18.0 + 0.02*(-320) = 11.6 mm
        # R3: x=-280, y=-180 -> z = 18.0 + 0.02*(-320) + 0.03*(-360) = 0.8 mm
        # R4: x=40, y=-180 -> z = 18.0 + 0.03*(-360) = 7.2 mm
        # Max Z diff = 18.0 - 0.8 = 17.2 mm!
        tilted_points = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-280.0, 180.0, 11.6],
            "R3": [-280.0, -180.0, 0.8],
            "R4": [40.0, -180.0, 7.2],
        }

        # Policy allows plane residual up to 3.0 mm and tilt <= 45 deg
        result = calibrate_board_from_teaching_points(tilted_points)
        assert result.success is True, f"Failed tilted coplanar board: {result.error_message}"
        assert result.max_plane_residual_mm < 0.1
        assert result.state is not None

    # -------------------------------------------------------------------------
    # Matrix #10: Non-coplanar point fails
    # -------------------------------------------------------------------------
    def test_non_coplanar_point_fails(self):
        """
        Matrix #10:
        One point protruding 8.0 mm out of plane must be rejected by point-to-plane residual.
        """
        non_coplanar_points = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-280.0, 180.0, 18.0],
            "R3": [-280.0, -180.0, 26.0],  # +8.0 mm out of plane!
            "R4": [40.0, -180.0, 18.0],
        }

        result = calibrate_board_from_teaching_points(non_coplanar_points)
        assert result.success is False
        assert "non-coplanar" in result.error_message.lower()
        assert result.max_plane_residual_mm > 3.0

    # -------------------------------------------------------------------------
    # Matrix #11: Physical calibration failure disables motion
    # -------------------------------------------------------------------------
    def test_physical_calibration_failure_disables_motion(self):
        """
        Matrix #11:
        Verify physical calibration failure sets physical_motion_authorized=False,
        is_robot_ready=False, and move_piece returns False.
        """
        class MockConfig:
            DRY_RUN = True
            ROBOT_BACKEND = "PHYSICAL"
            ROBOT_IP = "127.0.0.1"
            BOARD_ORIGIN_X = 200.0
            BOARD_ORIGIN_Y = -100.0
            ROTATION = [-179.164, -3.047, -26.304]
            PICK_TOOL_ROTATION = [-179.164, -3.047, -26.304]
            SAFE_CLEARANCE_Z_MM = 40.0
            PICK_DEPTH_OFFSET_MM = 0.0
            CAPTURE_BIN_X = -226.123
            CAPTURE_BIN_Y = 225.024
            CAPTURE_BIN_Z = 291.68
            ENGINE_TYPE = "LOCAL"

        hw = HardwareManager(MockConfig(), ".")

        # Fixed fixture bug: provide well-formed teaching points that fail on intended geometry (bad width=100mm)
        backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        backend.set_mock_teaching_points({
            "R1": [40.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "R2": [-60.0, 180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],  # Width 100mm!
            "R3": [-60.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "R4": [40.0, -180.0, 18.0, 180.0, 0.0, 90.0, 0, 0, 0, 0, 0, 0, 0, 0],
        })
        hw.backend = backend

        hw._calibrate_robot()

        assert hw.board_pose_provider is None
        assert hw.motion_coordinator is None
        assert hw.physical_motion_authorized is False
        assert hw.is_robot_ready is False

        ok = hw.move_piece(0, 0, 0, 1, is_capture=False)
        assert ok is False

    # -------------------------------------------------------------------------
    # Matrix #12: No motion command occurs before calibration success
    # -------------------------------------------------------------------------
    def test_no_motion_command_occurs_before_calibration_success(self):
        """
        Matrix #12:
        Startup must never invoke go_to_home_chess, MoveJ, MoveL, or MoveCart before calibration succeeds.
        """
        class MockConfig:
            DRY_RUN = False
            ROBOT_BACKEND = "PHYSICAL"
            ROBOT_IP = "192.168.58.2"

        hw = HardwareManager(MockConfig(), ".")

        # Mock both legacy robot and physical backend
        mock_legacy = MagicMock()
        mock_legacy.connected = True
        hw.robot = mock_legacy

        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.connect.return_value = True
        mock_backend.get_state_snapshot.return_value = MagicMock(connected=True)
        # Return invalid teaching points to force calibration failure
        mock_backend.get_teaching_point.return_value = (-1, [])
        hw.backend = mock_backend

        # Simulate startup
        hw._calibrate_robot()

        # Assert NO motion commands were issued
        mock_legacy.go_to_home_chess.assert_not_called()
        mock_backend.move_cartesian.assert_not_called()
        mock_backend.move_joint.assert_not_called()
        assert hw.physical_motion_authorized is False
        assert hw.is_robot_ready is False

    # -------------------------------------------------------------------------
    # Matrix #13: Physical backend requires explicit calibrated provider
    # -------------------------------------------------------------------------
    def test_physical_backend_requires_explicit_calibrated_provider(self):
        """
        Matrix #13:
        Instantiating MotionCoordinator with PhysicalFR3Backend and board_pose_provider=None must raise ValueError.
        """
        backend = PhysicalFR3Backend(dry_run=True)
        with pytest.raises(ValueError, match="requires an explicit calibrated BoardPoseProvider"):
            MotionCoordinator(backend=backend, board_pose_provider=None)

    # -------------------------------------------------------------------------
    # Matrix #14: Virtual provider remains hardware-independent
    # -------------------------------------------------------------------------
    def test_virtual_provider_remains_hardware_independent(self):
        """
        Matrix #14:
        VirtualFR3Backend works offline and allows default FixedBoardPoseProvider without hardware.
        """
        virtual_backend = VirtualFR3Backend()
        coordinator = MotionCoordinator(backend=virtual_backend, board_pose_provider=None)
        assert coordinator.board_pose_provider is not None
        assert isinstance(coordinator.board_pose_provider, FixedBoardPoseProvider)
        assert coordinator.board_placement is not None

    # -------------------------------------------------------------------------
    # Matrix #15: Pick height uses MotionProfile
    # -------------------------------------------------------------------------
    def test_pick_height_uses_motion_profile(self):
        """
        Matrix #15:
        Pick target Z uses MotionProfile rather than hardcoded 0 or board surface.
        """
        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.get_state_snapshot.return_value = MagicMock(connected=True)
        mock_backend.move_cartesian.return_value = True
        mock_backend.set_gripper.return_value = True

        phys_provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(NOMINAL_TEACHING_POINTS)

        custom_profile = MotionProfile(
            pick_tcp_height_above_board_mm=7.5,
            place_tcp_height_above_board_mm=7.5,
            safe_clearance_above_board_mm=45.0,
            provenance="MEASURED",
        )
        assert custom_profile.is_physical_validated is True

        coordinator = MotionCoordinator(
            backend=mock_backend,
            board_pose_provider=phys_provider,
            motion_profile=custom_profile,
        )

        ok = coordinator.pick(row=0, col=0)
        assert ok is True

        # Target Z for pick should be 18.0 mm (board surface) + 7.5 mm = 25.5 mm
        pick_call = mock_backend.move_cartesian.call_args_list[1]
        target_pose = pick_call[0][0]
        assert target_pose[2] == pytest.approx(25.5, abs=1e-2)

    # -------------------------------------------------------------------------
    # Matrix #16: Safe clearance remains board-relative
    # -------------------------------------------------------------------------
    def test_safe_clearance_remains_board_relative(self):
        """
        Matrix #16:
        Approach and retract waypoints are strictly relative to board surface Z.
        """
        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.get_state_snapshot.return_value = MagicMock(connected=True)
        mock_backend.move_cartesian.return_value = True
        mock_backend.set_gripper.return_value = True

        elevated_points = {
            "R1": [40.0, 180.0, 50.0],
            "R2": [-280.0, 180.0, 50.0],
            "R3": [-280.0, -180.0, 50.0],
            "R4": [40.0, -180.0, 50.0],
        }
        phys_provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(elevated_points)

        coordinator = MotionCoordinator(
            backend=mock_backend,
            board_pose_provider=phys_provider,
            motion_profile=MotionProfile(safe_clearance_above_board_mm=40.0),
        )

        coordinator.pick(row=0, col=0)

        # Approach waypoint should be at Z = 50.0 + 40.0 = 90.0 mm
        approach_call = mock_backend.move_cartesian.call_args_list[0]
        approach_pose = approach_call[0][0]
        assert approach_pose[2] == pytest.approx(90.0, abs=1e-2)

    # -------------------------------------------------------------------------
    # Matrix #17: Old 218 mm cache assumption removed
    # -------------------------------------------------------------------------
    def test_old_218mm_cache_assumption_removed(self):
        """
        Matrix #17:
        Verify dry-run PhysicalFR3Backend initial geometry does not encode old 218 mm tool length.
        """
        backend = PhysicalFR3Backend(dry_run=True)
        tcp_z = backend._current_tcp_pose_mm_deg[2]
        flange_z = backend._current_flange_pose_mm_deg[2]
        diff_mm = abs(flange_z - tcp_z)

        # Must not be old 218 mm
        assert diff_mm != pytest.approx(218.0, abs=1.0)
        # Must match canonical 150 mm tool profile
        assert diff_mm == pytest.approx(150.0, abs=1.0)
