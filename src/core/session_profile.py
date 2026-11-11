"""Immutable game capabilities, independent of the launcher's requested hardware."""
from dataclasses import dataclass


GAME_MODES = {"HUMAN_VS_ROBOT", "HUMAN_VS_HUMAN_ROBOT"}


@dataclass(frozen=True)
class SessionProfile:
    game_mode: str
    requested_environment: str
    execution_environment: str
    backend: str
    camera_enabled: bool
    physical_robot_enabled: bool
    robot_moves_enabled: bool
    ai_enabled: bool
    simulation_enabled: bool
    viewer_enabled: bool
    mouse_input: str

    @property
    def dry_run(self):
        return not self.physical_robot_enabled

    @property
    def game_only(self):
        return self.backend == "VIRTUAL" and not self.simulation_enabled

    @property
    def match_names(self):
        if self.game_mode == "HUMAN_VS_HUMAN_ROBOT":
            return ("Red player", "Black player")
        return ("Player", "Robot AI")


def make_profile(game_mode, requested_environment, *, simulation_enabled=True, viewer_enabled=True):
    mode = str(game_mode).upper()
    if mode not in GAME_MODES:
        raise ValueError("Unsupported game mode")
    requested = str(requested_environment).upper()
    if requested not in {"VIRTUAL", "PHYSICAL"}:
        raise ValueError("Unsupported execution environment")
    robot_pvp = mode == "HUMAN_VS_HUMAN_ROBOT"
    if robot_pvp and not simulation_enabled:
        raise ValueError("Two-human robot mode requires simulation or physical robot mode")
    physical = requested == "PHYSICAL"
    environment = "PHYSICAL" if physical else "VIRTUAL"
    return SessionProfile(
        game_mode=mode, requested_environment=requested, execution_environment=environment,
        backend=environment, camera_enabled=physical, physical_robot_enabled=physical,
        robot_moves_enabled=True, ai_enabled=not robot_pvp,
        simulation_enabled=simulation_enabled,
        viewer_enabled=simulation_enabled and viewer_enabled,
        mouse_input="ROBOT_COMMANDS" if robot_pvp else ("VIRTUAL_TEST_ADAPTER" if not physical else "NONE"))


def profile_from_config(config):
    requested = ("PHYSICAL" if str(getattr(config, "ROBOT_BACKEND", "VIRTUAL")).upper() == "PHYSICAL"
                 and not getattr(config, "DRY_RUN", True) else "VIRTUAL")
    mode = str(getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT")).upper()
    if requested == "PHYSICAL" and getattr(config, "GAME_ONLY", False):
        raise ValueError("Game-only cannot enable physical hardware")
    return make_profile(mode, requested, simulation_enabled=not getattr(config, "GAME_ONLY", False))


def configure_session(config, options, *, mode=None):
    """Build and apply one session profile.

    ``mode`` is the customer-facing preset used by the launcher:
    ``BOARD_ONLY`` (2D game only), ``SIMULATION`` (virtual robot + 3D viewer),
    or ``PHYSICAL`` (camera + real robot, optionally with the 3D mirror).
    Omitting it preserves the existing CLI-derived behavior.
    """
    no_viewer = bool(getattr(options, "no_viewer", False))
    if mode is not None:
        normalized = str(mode).strip().upper()
        if normalized == "BOARD_ONLY":
            requested, simulation_enabled, viewer_enabled = "VIRTUAL", False, False
        elif normalized == "SIMULATION":
            requested, simulation_enabled, viewer_enabled = "VIRTUAL", True, not no_viewer
        elif normalized == "PHYSICAL":
            requested, simulation_enabled, viewer_enabled = "PHYSICAL", True, not no_viewer
        else:
            raise ValueError(f"Unsupported session mode: {mode!r}")
        physical = requested == "PHYSICAL"
    else:
        physical_opt = getattr(options, "physical", None)
        if physical_opt is None:
            physical = (str(getattr(config, "ROBOT_BACKEND", "VIRTUAL")).upper() == "PHYSICAL"
                        and not getattr(config, "DRY_RUN", True))
        else:
            physical = bool(physical_opt)
        requested = "PHYSICAL" if physical else "VIRTUAL"
        simulation_enabled = not getattr(options, "virtual", False) and not getattr(config, "GAME_ONLY", False)
        viewer_enabled = not no_viewer
    profile = make_profile(
        getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT"),
        requested,
        simulation_enabled=simulation_enabled,
        viewer_enabled=viewer_enabled,
    )
    playback = getattr(options, "simulation_profile", None)
    if playback is not None:
        if profile.physical_robot_enabled or not profile.simulation_enabled:
            raise ValueError("Simulation playback profile requires an active virtual executor")
        if playback not in {"detailed", "fast"}:
            raise ValueError("Unsupported simulation playback profile")
        config.SIMULATION_PROFILE = playback
    config.SESSION_PROFILE = profile
    config.GAME_MODE = profile.game_mode
    config.REQUESTED_EXECUTION_ENVIRONMENT = profile.requested_environment
    config.EXECUTION_ENVIRONMENT = profile.execution_environment
    config.ROBOT_BACKEND = profile.backend
    config.DRY_RUN = profile.dry_run
    config.GAME_ONLY = profile.game_only
    return profile
