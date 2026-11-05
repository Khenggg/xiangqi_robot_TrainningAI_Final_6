"""Read-only command authority snapshots; no SDK call or physical enable here."""
import hashlib
from pathlib import Path

from src.core.session_journal import dumps


def digest(value):
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def capture_execution_binding(hardware):
    profile = hardware.profile
    runtime = hardware.simulation_runtime
    config, robot = hardware.config, hardware.robot
    binding = dict(environment=profile.execution_environment, game_mode=profile.game_mode,
                   scene_id=hardware.scene_id if runtime is not None else None)
    if runtime is not None:
        placement = runtime.placement_state
        binding.update(scene_epoch=getattr(runtime, "scene_epoch", 0),
                       calibration_version=placement.placement_version,
                       calibration_token=digest(placement.to_dict()),
                       speed_factor=hardware.backend.default_speed_factor,
                       playback_profile=getattr(getattr(hardware, "simulation_playback_profile", None), "name", None))
    elif not hardware.dry_run:
        # The physical command mapping remains the visual controller's mapping.
        # Optional mirror placement must not become a physical planning gate.
        names = ("OFFSET_X", "OFFSET_Y", "PICK_Z", "PLACE_Z", "SAFE_Z", "ROTATION",
                 "PICK_TOOL_ROTATION", "PLACE_TOOL_ROTATION",
                 "IDLE_X", "IDLE_Y", "IDLE_Z", "MOVE_SPEED")
        parameters = {name: getattr(config, name, None) for name in names}
        parameters.update({name: value for name, value in vars(config).items()
                           if name.startswith(("GRIPPER_", "VISUAL_"))})
        binding.update(calibration_version=getattr(robot, "teaching_points_version", 0),
                       calibration_token=digest(dict(points=robot.teaching_points,
                           tool=robot.tool_num, user=robot.user_num, speed=robot.default_vel,
                           parameters=parameters)))
        perspective = Path(hardware.perspective_path)
        binding["camera_calibration_token"] = (
            hashlib.sha256(perspective.read_bytes()).hexdigest() if perspective.is_file() else None)
    else:
        binding.update(calibration_version=None, calibration_token="GAME_ONLY")
    return binding
