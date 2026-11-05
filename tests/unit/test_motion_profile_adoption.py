"""The adopted visual-correction-v2 motion profile is explicit and provenance-tracked."""
import config


def test_visual_v2_motion_profile_values():
    assert config.MOTION_PROFILE_SOURCE == "origin/feature/visual-correction-v2@fb0598d"
    assert config.MOTION_PROFILE_VERIFIED is False
    assert config.SAFE_Z == 220.0
    assert config.PICK_Z == 178.0
    assert config.PLACE_Z == 178.0
    assert config.ROTATION == [180, 0, -73.2]
    assert config.PICK_TOOL_ROTATION == config.ROTATION
    assert config.PLACE_TOOL_ROTATION == config.ROTATION
    assert config.MOVE_SPEED == 50
