"""Customer-facing session presets must map onto the existing physical safety model."""

from types import SimpleNamespace

import pytest

from src.core.launch_options import configure_runtime, parse_options
from src.core.session_profile import configure_session


def _config():
    return SimpleNamespace(
        GAME_MODE="HUMAN_VS_ROBOT",
        GAME_ONLY=False,
        ROBOT_BACKEND="VIRTUAL",
        DRY_RUN=True,
    )


@pytest.mark.parametrize(
    "mode,backend,physical,simulation,viewer,game_only",
    [
        ("BOARD_ONLY", "VIRTUAL", False, False, False, True),
        ("SIMULATION", "VIRTUAL", False, True, True, False),
        ("PHYSICAL", "PHYSICAL", True, True, True, False),
    ],
)
def test_three_session_modes_apply_expected_capabilities(
        mode, backend, physical, simulation, viewer, game_only):
    cfg = _config()
    profile = configure_session(cfg, parse_options([]), mode=mode)
    assert profile.backend == backend
    assert profile.physical_robot_enabled is physical
    assert profile.camera_enabled is physical
    assert profile.simulation_enabled is simulation
    assert profile.viewer_enabled is viewer
    assert profile.game_only is game_only
    assert cfg.ROBOT_BACKEND == backend
    assert cfg.DRY_RUN is (not physical)
    assert cfg.GAME_ONLY is game_only
    assert cfg.REQUESTED_EXECUTION_ENVIRONMENT == backend
    assert cfg.EXECUTION_ENVIRONMENT == backend


def test_three_d_toggle_never_disables_simulation_or_physical_robot():
    cfg = _config()
    profile = configure_session(cfg, parse_options(["--no-3d"]), mode="PHYSICAL")
    assert profile.physical_robot_enabled is True
    assert profile.simulation_enabled is True
    assert profile.viewer_enabled is False
    assert cfg.DRY_RUN is False

    cfg = _config()
    profile = configure_session(cfg, parse_options(["--no-3d"]), mode="SIMULATION")
    assert profile.physical_robot_enabled is False
    assert profile.simulation_enabled is True
    assert profile.viewer_enabled is False


def test_board_only_ignores_a_viewer_request_and_rejects_playback_profile():
    cfg = _config()
    profile = configure_session(cfg, parse_options(["--no-3d"]), mode="BOARD_ONLY")
    assert profile.game_only is True
    assert profile.simulation_enabled is False
    assert profile.viewer_enabled is False
    with pytest.raises(ValueError):
        configure_session(_config(), parse_options(["--simulation-profile", "fast"]),
                          mode="BOARD_ONLY")


@pytest.mark.parametrize("argv,backend,dry,game_only", [
    (["--board-only"], "VIRTUAL", True, True),
    (["--sim"], "VIRTUAL", True, False),
    (["--simulation"], "VIRTUAL", True, False),
    (["--robot"], "PHYSICAL", False, False),
    (["--robot", "--no-3d"], "PHYSICAL", False, False),
])
def test_cli_aliases_preserve_physical_and_simulation_boundaries(
        argv, backend, dry, game_only):
    cfg = SimpleNamespace()
    configure_runtime(cfg, parse_options(argv))
    assert (cfg.ROBOT_BACKEND, cfg.DRY_RUN, cfg.GAME_ONLY) == (backend, dry, game_only)


@pytest.mark.parametrize("argv", [
    ["--sim", "--robot"],
    ["--simulation", "--board-only"],
    ["--sim", "--board-only"],
])
def test_simulation_preset_cannot_be_combined_with_other_modes(argv):
    with pytest.raises(SystemExit):
        parse_options(argv)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        configure_session(_config(), parse_options([]), mode="not-a-mode")


def test_human_vs_human_never_claims_physical_robot_capability():
    cfg = _config()
    cfg.GAME_MODE = "HUMAN_VS_HUMAN"
    profile = configure_session(cfg, parse_options([]), mode="PHYSICAL")
    assert profile.physical_robot_enabled is False
    assert profile.camera_enabled is False
    assert profile.simulation_enabled is True
    assert cfg.DRY_RUN is True
    assert cfg.ROBOT_BACKEND == "VIRTUAL"
