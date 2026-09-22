"""
Unit tests for Physical Board Pose Calibration and Real FR3 Board Integration.
Tests all requirements from the task specification:
- Section 22: Mandatory automated tests for calibration and motion coordinator.
- Section 23: Reconstruction of known arbitrary rigid transform.
- Section 25: Failure modes disabling physical motion without silent fallback.
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
    BoardPoseProvider,
    FixedBoardPoseProvider,
    PhysicalTeachingPointBoardPoseProvider,
    calibrate_board_from_teaching_points,
    CANONICAL_WIDTH_MM,
    CANONICAL_LENGTH_MM,
)
from src.motion.coordinator import MotionCoordinator, MotionProfile
from src.hardware.backends import PhysicalFR3Backend, VirtualFR3Backend
from src.hardware.hardware_manager import HardwareManager


# Standard nominal teaching points forming a canonical 320x360mm board at Z=18.0mm
# Under 90-degree yaw convention:
# R1 = (col 0, row 0) -> u=-160, v=-180 -> robot x = center_x + 160, robot y = center_y + 180
# Center at (-120.0, 0.0, 18.0)
NOMINAL_TEACHING_POINTS = {
    "R1": [40.0, 180.0, 18.0],
    "R2": [-280.0, 180.0, 18.0],
    "R3": [-280.0, -180.0, 18.0],
    "R4": [40.0, -180.0, 18.0],
}


class TestPhysicalBoardCalibration:

    def test_physical_board_pose_from_teaching_points(self):
        """Test deriving a valid BoardPlacementState from clean teaching points."""
        result = calibrate_board_from_teaching_points(NOMINAL_TEACHING_POINTS)

        assert result.success is True
        assert result.state is not None
        assert result.error_message is None
        assert result.measured_width_mm == pytest.approx(320.0, abs=1e-2)
        assert result.measured_length_mm == pytest.approx(360.0, abs=1e-2)
        assert result.rms_error_mm < 1e-3
        assert result.max_error_mm < 1e-3

        state = result.state
        assert state.board_surface_z_robot_m == pytest.approx(0.018, abs=1e-4)
        assert state.board_center_robot_m[0] == pytest.approx(-0.120, abs=1e-4)
        assert state.board_center_robot_m[1] == pytest.approx(0.0, abs=1e-4)

    def test_board_pose_reconstructs_r1_r2_r3_r4(self):
        """Test that projecting corner cells through estimated pose reconstructs R1-R4."""
        result = calibrate_board_from_teaching_points(NOMINAL_TEACHING_POINTS)
        assert result.success is True
        state = result.state

        # Canonical corner cells:
        # R1: row 0, col 0
        # R2: row 0, col 8
        # R3: row 9, col 8
        # R4: row 9, col 0
        corner_cells = {
            "R1": (0, 0),
            "R2": (0, 8),
            "R3": (9, 8),
            "R4": (9, 0),
        }

        for name, (row, col) in corner_cells.items():
            predicted_xyz_m = state.cell_to_robot_xyz(row, col, z_rel_m=0.0)
            predicted_xyz_mm = predicted_xyz_m * 1000.0
            expected_xyz_mm = np.array(NOMINAL_TEACHING_POINTS[name])

            error_mm = np.linalg.norm(predicted_xyz_mm - expected_xyz_mm)
            assert error_mm < 0.05, f"Corner {name} reconstruction error too large: {error_mm:.4f} mm"

    def test_board_pose_corner_residuals(self):
        """Test residual error calculation when teaching points have small measurement noise."""
        perturbed_points = {
            "R1": [40.5, 179.7, 18.2],
            "R2": [-279.4, 180.3, 17.9],
            "R3": [-280.2, -179.6, 18.1],
            "R4": [39.8, -180.2, 17.8],
        }

        result = calibrate_board_from_teaching_points(perturbed_points)
        assert result.success is True
        assert result.state is not None

        residuals = result.residuals
        assert "R1" in residuals
        assert "R2" in residuals
        assert "R3" in residuals
        assert "R4" in residuals
        assert "RMS" in residuals
        assert "Max" in residuals

        # Verify residuals match individually computed distances
        state = result.state
        corner_cells = {"R1": (0, 0), "R2": (0, 8), "R3": (9, 8), "R4": (9, 0)}
        errs = []
        for name, (r, c) in corner_cells.items():
            pred_mm = state.cell_to_robot_xyz(r, c) * 1000.0
            meas_mm = np.array(perturbed_points[name])
            err = float(np.linalg.norm(pred_mm - meas_mm))
            errs.append(err)
            assert residuals[name] == pytest.approx(err, abs=1e-3)

        expected_rms = float(np.sqrt(np.mean(np.array(errs) ** 2)))
        expected_max = float(np.max(errs))
        assert result.rms_error_mm == pytest.approx(expected_rms, abs=1e-3)
        assert result.max_error_mm == pytest.approx(expected_max, abs=1e-3)

    def test_board_pose_center_mapping(self):
        """Test board center mapping: (row=4.5, col=4.0) maps to board physical center."""
        result = calibrate_board_from_teaching_points(NOMINAL_TEACHING_POINTS)
        assert result.success is True
        state = result.state

        # Center in grid space: row=4.5, col=4.0
        center_robot = state.cell_to_robot_xyz(4.5, 4.0, z_rel_m=0.0)
        expected_center = np.array([-0.120, 0.0, 0.018])

        np.testing.assert_allclose(center_robot, expected_center, atol=1e-4)
        np.testing.assert_allclose(state.board_center_robot_m[:2], expected_center[:2], atol=1e-4)
        assert state.board_surface_z_robot_m == pytest.approx(0.018, abs=1e-4)

    def test_board_pose_all_90_cells(self):
        """
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

    def test_physical_board_provider_rejects_missing_r_point(self):
        """Test that missing or unreadable teaching points fail calibration cleanly."""
        # Missing R4
        incomplete = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-280.0, 180.0, 18.0],
            "R3": [-280.0, -180.0, 18.0],
        }
        result = calibrate_board_from_teaching_points(incomplete)
        assert result.success is False
        assert "Missing required teaching point" in result.error_message

        # Provider fails fast when calibration fails
        provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(incomplete)
        assert provider.is_calibrated is False
        with pytest.raises(RuntimeError):
            provider.get_board_placement_state()

    def test_physical_board_provider_rejects_invalid_geometry(self):
        """Test that degenerate or out-of-tolerance geometry is rejected."""
        # Case A: Swapped R2 and R4 (inverted orientation / quadrilateral)
        swapped = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [40.0, -180.0, 18.0],  # Swapped with R4
            "R3": [-280.0, -180.0, 18.0],
            "R4": [-280.0, 180.0, 18.0],  # Swapped with R2
        }
        res_swapped = calibrate_board_from_teaching_points(swapped)
        assert res_swapped.success is False

        # Case B: Dimension mismatch (width is 200 mm instead of 320 mm)
        bad_width = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-160.0, 180.0, 18.0],  # Width 200 mm
            "R3": [-160.0, -180.0, 18.0],
            "R4": [40.0, -180.0, 18.0],
        }
        res_width = calibrate_board_from_teaching_points(bad_width)
        assert res_width.success is False
        assert "width mismatch" in res_width.error_message.lower()

        # Case C: Large non-coplanar Z difference (tilted by 30 mm)
        tilted_z = {
            "R1": [40.0, 180.0, 18.0],
            "R2": [-280.0, 180.0, 18.0],
            "R3": [-280.0, -180.0, 48.0],  # +30 mm
            "R4": [40.0, -180.0, 18.0],
        }
        res_tilted = calibrate_board_from_teaching_points(tilted_z)
        assert res_tilted.success is False
        assert "z variation" in res_tilted.error_message.lower()

    def test_virtual_provider_does_not_require_hardware(self):
        """Test that Virtual FixedBoardPoseProvider works completely offline."""
        provider = FixedBoardPoseProvider.from_forward_shift(forward_shift_mm=25.0)
        state = provider.get_board_placement_state()

        assert isinstance(state, BoardPlacementState)
        assert state.forward_shift_mm == pytest.approx(25.0, abs=1e-2)
        # Verify cell mapping works offline
        p_xyz = state.cell_to_robot_xyz(0, 0)
        assert len(p_xyz) == 3

    def test_physical_and_virtual_share_board_coordinate_semantics(self):
        """Test that physical and virtual providers share identical board coordinate semantics."""
        virt_provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        phys_provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(NOMINAL_TEACHING_POINTS)

        v_state = virt_provider.get_board_placement_state()
        p_state = phys_provider.get_board_placement_state()

        # Test local coordinate conversion
        for r, c in [(0, 0), (0, 8), (9, 0), (9, 8), (4.5, 4.0)]:
            u_v, v_v = v_state.cell_to_board_local(r, c)
            u_p, v_p = p_state.cell_to_board_local(r, c)
            assert u_v == pytest.approx(u_p, abs=1e-6)
            assert v_v == pytest.approx(v_p, abs=1e-6)

    def test_motion_coordinator_uses_injected_board_pose(self):
        """Test that MotionCoordinator respects custom injected board pose instead of hardcoded coords."""
        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.get_state_snapshot.return_value = MagicMock(connected=True)
        mock_backend.move_cartesian.return_value = True
        mock_backend.set_gripper.return_value = True

        # Custom shifted board pose (+50mm X, -30mm Y, +10mm Z)
        shifted_points = {
            "R1": [90.0, 150.0, 28.0],
            "R2": [-230.0, 150.0, 28.0],
            "R3": [-230.0, -210.0, 28.0],
            "R4": [90.0, -210.0, 28.0],
        }
        phys_provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(shifted_points)

        coordinator = MotionCoordinator(
            backend=mock_backend,
            board_pose_provider=phys_provider,
        )

        ok = coordinator.pick(row=0, col=0)
        assert ok is True

        # Check call arguments to backend
        # Pick should target R1 in mm: X=90.0, Y=150.0, Z=28.0 + pick_height
        assert mock_backend.move_cartesian.called
        assert mock_backend.move_cartesian.call_count == 3
        # Call 1 is pick pose (descend)
        pick_call = mock_backend.move_cartesian.call_args_list[1]
        target_pose = pick_call[0][0]

        assert target_pose[0] == pytest.approx(90.0, abs=1.0)
        assert target_pose[1] == pytest.approx(150.0, abs=1.0)
        assert target_pose[2] == pytest.approx(28.0 + 4.715, abs=1.0)

    def test_runtime_pick_height_uses_motion_profile(self):
        """Test that pick target Z uses MotionProfile rather than hardcoded 0 or surface."""
        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.get_state_snapshot.return_value = MagicMock(connected=True)
        mock_backend.move_cartesian.return_value = True
        mock_backend.set_gripper.return_value = True

        phys_provider = PhysicalTeachingPointBoardPoseProvider.from_teaching_points(NOMINAL_TEACHING_POINTS)

        # Custom pick height: 8.0 mm
        custom_profile = MotionProfile(
            pick_tcp_height_above_board_mm=8.0,
            place_tcp_height_above_board_mm=8.0,
            safe_clearance_above_board_mm=50.0,
            provenance="MEASURED_APPROXIMATE",
        )

        coordinator = MotionCoordinator(
            backend=mock_backend,
            board_pose_provider=phys_provider,
            motion_profile=custom_profile,
        )

        ok = coordinator.pick(row=4, col=4)
        assert ok is True

        # Target Z for pick should be 18.0 mm (board surface) + 8.0 mm = 26.0 mm
        pick_call = mock_backend.move_cartesian.call_args_list[1]
        target_pose = pick_call[0][0]
        assert target_pose[2] == pytest.approx(26.0, abs=1e-2)

    def test_pick_height_not_hardcoded_zero(self):
        """Test that default MotionProfile pick height is strictly above board surface."""
        default_profile = MotionProfile()
        assert default_profile.pick_tcp_height_above_board_mm > 0.0
        assert default_profile.pick_tcp_height_above_board_mm == pytest.approx(4.715, abs=1e-3)
        assert default_profile.provenance == "SIMULATION_GEOMETRIC_DEFAULT"

    def test_safe_clearance_is_relative_to_board_surface(self):
        """Test approach and retract heights are relative to board surface Z, not absolute world Z."""
        mock_backend = MagicMock(spec=PhysicalFR3Backend)
        mock_backend.get_state_snapshot.return_value = MagicMock(connected=True)
        mock_backend.move_cartesian.return_value = True
        mock_backend.set_gripper.return_value = True

        # Board surface at Z = 50.0 mm
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

    def test_reconstruct_known_arbitrary_transform(self):
        """
        Section 23 requirement:
        Synthesize R1-R4 from an arbitrary known 3D rigid transform (translation + yaw + small pitch/roll),
        pass to calibration algorithm, and verify the estimated transform recovers ground truth.
        """
        # Ground truth translation (in meters)
        p_gt = np.array([-0.145, 0.035, 0.022], dtype=float)

        # Ground truth rotation with yaw=92.5 deg, pitch=0.8 deg, roll=-0.6 deg
        # Base 90-degree board orientation:
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
        # Canonical baseline R0 for yaw=0
        R_0 = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        R_gt = R_z @ R_y @ R_x @ R_0

        # Canonical corner coordinates in board-local frame (in meters):
        # Center is (col 4, row 4.5)
        # R1: u = -0.160, v = -0.180
        # R2: u = +0.160, v = -0.180
        # R3: u = +0.160, v = +0.180
        # R4: u = -0.160, v = +0.180
        local_corners = {
            "R1": np.array([-0.160, -0.180, 0.0]),
            "R2": np.array([0.160, -0.180, 0.0]),
            "R3": np.array([0.160, 0.180, 0.0]),
            "R4": np.array([-0.160, 0.180, 0.0]),
        }

        # Synthesize measured teaching points in robot frame (in mm):
        synth_points = {}
        for name, p_local in local_corners.items():
            p_robot_m = p_gt + R_gt @ p_local
            synth_points[name] = list(p_robot_m * 1000.0)

        # Run calibration
        result = calibrate_board_from_teaching_points(synth_points)

        assert result.success is True, f"Calibration failed: {result.error_message}"
        assert result.state is not None
        assert result.rms_error_mm < 0.05
        assert result.max_error_mm < 0.05

        state = result.state

        # Verify translation reconstruction
        assert state.board_center_robot_m[0] == pytest.approx(p_gt[0], abs=1e-4)
        assert state.board_center_robot_m[1] == pytest.approx(p_gt[1], abs=1e-4)
        assert state.board_surface_z_robot_m == pytest.approx(p_gt[2], abs=1e-4)

        # Verify rotation matrix reconstruction
        R_est = state.R_robot_from_board
        rot_diff = np.linalg.norm(R_est - R_gt)
        assert rot_diff < 1e-3, f"Rotation matrix difference too large: {rot_diff}"

        # Verify corners project back accurately
        for name, p_local in local_corners.items():
            p_expected_mm = np.array(synth_points[name])
            r, c = {"R1": (0, 0), "R2": (0, 8), "R3": (9, 8), "R4": (9, 0)}[name]
            p_reconstructed_mm = state.cell_to_robot_xyz(r, c) * 1000.0
            corner_err = np.linalg.norm(p_reconstructed_mm - p_expected_mm)
            assert corner_err < 0.05, f"Corner {name} reconstruction error: {corner_err:.4f} mm"

    def test_physical_calibration_failure_disables_robot_motion(self):
        """
        Section 25 & 31: If physical calibration fails, robot motion must be DISABLED.
        No silent fallback to simulation coordinates.
        """
        class BadConfig:
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

        hw = HardwareManager(BadConfig(), ".")

        # Mock physical backend with degenerate teaching points (width=100mm instead of 320mm)
        backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        backend.set_mock_teaching_points({
            "R1": [0, 40.0, 180.0, 18.0, 0.0, 0.0],
            "R2": [0, -60.0, 180.0, 18.0, 0.0, 0.0],  # Width 100 mm -> degenerate!
            "R3": [0, -60.0, -180.0, 18.0, 0.0, 0.0],
            "R4": [0, 40.0, -180.0, 18.0, 0.0, 0.0],
        })
        hw.backend = backend

        hw._calibrate_robot()

        # Calibration must have failed
        assert hw.board_pose_provider is None
        assert hw.motion_coordinator is None
        assert hw.is_robot_ready is False

        # Attempting move_piece must return False without moving
        ok = hw.move_piece(0, 0, 0, 1, is_capture=False)
        assert ok is False
