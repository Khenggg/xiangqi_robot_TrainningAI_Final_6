from pathlib import Path
import json

import pytest

from src.simulation.physics.gripper import VirtualGripper, asset_fingerprint


def test_text_fingerprint_accepts_checkout_newlines_but_rejects_geometry_change():
    lf = b'{"stroke": 0.0052}\n'
    assert asset_fingerprint(lf, "UTF8_LF_V1") == asset_fingerprint(
        lf.replace(b"\n", b"\r\n"), "UTF8_LF_V1")
    assert asset_fingerprint(lf, "UTF8_LF_V1") != asset_fingerprint(
        lf.replace(b"0.0052", b"0.0062"), "UTF8_LF_V1")


def test_actual_profile_mutation_is_rejected_before_physics(tmp_path):
    root = Path(__file__).resolve().parents[2]
    profile = json.loads((root / "shared/virtual_gripper_profile.json").read_text())
    profile["palm"]["dimensions_m"][0] += 0.001
    modified = tmp_path / "gripper.json"
    modified.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        VirtualGripper(modified)


def test_committed_assets_validate_without_controller_or_pybullet_connection():
    gripper = VirtualGripper()
    assert len(gripper.collision_asset["fixed_boxes"]) == 19
    assert len(gripper.collision_asset["finger_boxes"]) == 2
