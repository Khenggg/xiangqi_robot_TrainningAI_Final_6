"""Scoped donor logic with the current measured hardware/profile values."""
from copy import deepcopy

HARDWARE_PREFIXES = ('GRIPPER_', 'ROBOT_', 'PHYSICAL_', 'BOARD_ORIGIN_', 'BOARD_CALIBRATION_', 'BOARD_SURFACE_', 'CAPTURE_BIN_',
                     'CELL_SIZE_', 'OFFSET_', 'MOTION_PROFILE_', 'TELEMETRY_')
HARDWARE_NAMES = {'DRY_RUN', 'ROTATION', 'PICK_TOOL_ROTATION', 'PLACE_TOOL_ROTATION',
                  'SAFE_Z', 'PICK_Z', 'PLACE_Z', 'HOVER_Z', 'MOVE_SPEED', 'RIVER_GAP_Y',
                  'ALLOW_IDENTITY_WOBJ_AS_BASE', 'VIDEO_SOURCE', 'VIDEO_BACKEND',
                  'VIDEO_FRAME_WIDTH', 'VIDEO_FRAME_HEIGHT', 'VISION_DEVICE',
                  'VISUAL_CAMERA_INTRINSICS_PATH', 'VISUAL_HEIGHT_BOARD_MM',
                  'VISUAL_HEIGHT_PIECE_MM', 'VISUAL_BOARD_WIDTH_MM', 'VISUAL_BOARD_HEIGHT_MM',
                  'VISUAL_PIECE_HEIGHT_MM', 'SIMULATION_TOKEN', 'ENGINE_TYPE', 'CLOUD_API_URL',
                  'CLOUD_TIMEOUT_SEC', 'MOONFISH_EXE', 'MOONFISH_NNUE'}

def apply_current_hardware(target, current):
    values = vars(current)
    destination = target if isinstance(target, dict) else vars(target)
    for name, value in values.items():
        if name in HARDWARE_NAMES or name.startswith(HARDWARE_PREFIXES):
            destination[name] = deepcopy(value)

def configure(current, selected_mode, root, *, camera_recalibration=False):
    from . import config
    from pathlib import Path
    apply_current_hardware(config, current)
    config.DRY_RUN = str(selected_mode).upper() != 'PHYSICAL'
    config.ROBOT_BACKEND = 'VIRTUAL' if config.DRY_RUN else 'PHYSICAL'
    config.RESOURCE_ROOT = str(Path(root).resolve())
    config.RECALIBRATE_CAMERA = bool(camera_recalibration)
    config.CAMERA_CALIBRATION_MANUAL_ONLY = bool(camera_recalibration)
    for name in ('MOONFISH_EXE', 'MOONFISH_NNUE'):
        value = getattr(config, name, None)
        if value and not Path(value).is_absolute():
            setattr(config, name, str(Path(root) / value))
    return config
