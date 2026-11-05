"""Board mirror surface Z may come from an independent measurement or R1-R4."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.hardware.simulation_adapter import physical_board_provider


def _point(x, y, z):
    return [x, y, z, 180.0, 0.0, 0.0] + [0.0] * 6 + [0.0, 0.0, 100.0, 100.0, 0.0, 0.0, 0.0, 0.0]


def _robot(z_values):
    points = {
        "R1": _point(-160.0, -180.0, z_values[0]),
        "R2": _point(160.0, -180.0, z_values[1]),
        "R3": _point(160.0, 180.0, z_values[2]),
        "R4": _point(-160.0, 180.0, z_values[3]),
    }
    cached = {
        name: {"pose": value[:6], "joints": [0.0] * 6, "tool": 0, "user": 0}
        for name, value in points.items()
    }
    rpc = Mock()
    rpc.GetRobotTeachingPoint.side_effect = lambda name: (0, points[name])
    return SimpleNamespace(
        robot=rpc, tool_num=0, user_num=0, teaching_points=cached,
        teaching_points_version=0,
        board_to_pose_bilinear=lambda col, row, z: [-160.0 + 40.0 * col,
                                                    -180.0 + 40.0 * row, z, 180.0, 0.0, 0.0],
    )


def _config(**overrides):
    values = dict(
        BOARD_CALIBRATION_MODEL="XY_SE2",
        BOARD_CALIBRATION_GRID_DIMENSIONS_MM=(320.0, 360.0),
        BOARD_CALIBRATION_PROVENANCE="TEST_ONLY",
        BOARD_SURFACE_Z_SOURCE="R1_R4",
        R1_R4_TAUGHT_AT_BOARD_SURFACE=True,
        BOARD_CALIBRATION_Z_TOLERANCE_MM=1.0,
        ROBOT_USER_FRAME=0,
        ROBOT_TOOL_FRAME=None,
        BOARD_CALIBRATION_REQUIRE_BASE_FRAME=True,
        SAFE_TRANSIT_HEIGHT_MM=40.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_surface_z_uses_median_of_r1_r4(caplog):
    robot = _robot([182.0, 182.5, 181.8, 181.9])
    with caplog.at_level("INFO", logger="xiangqi"):
        provider = physical_board_provider(robot, _config())
    assert provider.is_calibrated
    assert provider.get_board_placement_state().board_surface_z_robot_m == pytest.approx(0.18195)
    record = next(r for r in caplog.records if getattr(r, "event", None) == "board.surface_z_resolved")
    assert record.event_data["source"] == "R1_R4"
    assert record.event_data["value_mm"] == pytest.approx(181.95)
    assert record.event_data["details"]["spread_mm"] == pytest.approx(0.7)


def test_surface_z_requires_explicit_board_surface_confirmation():
    robot = _robot([182.0, 182.0, 182.0, 182.0])
    with pytest.raises(ValueError, match="R1_R4_TAUGHT_AT_BOARD_SURFACE"):
        physical_board_provider(robot, _config(R1_R4_TAUGHT_AT_BOARD_SURFACE=False))


def test_surface_z_rejects_nonflat_r1_r4():
    robot = _robot([182.0, 182.0, 183.5, 182.0])
    with pytest.raises(ValueError, match="spread"):
        physical_board_provider(robot, _config())


def test_surface_z_measured_mode_remains_available():
    robot = _robot([182.0, 182.0, 182.0, 182.0])
    provider = physical_board_provider(robot, _config(
        BOARD_SURFACE_Z_SOURCE="MEASURED",
        BOARD_CALIBRATION_SURFACE_Z_MM=182.0,
    ))
    assert provider.is_calibrated
    assert provider.get_board_placement_state().board_surface_z_robot_m == pytest.approx(0.182)


def test_surface_z_near_safe_z_is_logged_as_suspicious(caplog):
    robot = _robot([220.0, 220.0, 220.0, 220.0])
    with caplog.at_level("WARNING", logger="xiangqi"):
        provider = physical_board_provider(robot, _config(SAFE_Z=220.0, PICK_Z=178.0))
    assert provider.is_calibrated
    record = next(r for r in caplog.records
                  if getattr(r, "event", None) == "board.surface_z_suspicious")
    assert "SAFE_Z" in record.event_data["warnings"][0]
