

import pytest
from pathlib import Path

@pytest.fixture(autouse=True)
def explicit_phase3_scene(request, monkeypatch):
    # Golden coordinate/trajectory assertions describe this exact historical fixture,
    # not the operator's mutable production default scene.
    names = {"test_phase3_board_orientation_90", "test_phase3_final_g90_corrective", "test_phase3_isolation_and_fail_fast"}
    if request.module.__name__.rsplit(".", 1)[-1] in names:
        monkeypatch.setenv("XIANGQI_SCENE_CONFIG", str(Path(__file__).resolve().parents[1] / "fixtures" / "legacy_yaw90_scene.json"))

    if request.module.__name__.rsplit(".", 1)[-1] in {"test_phase3_dynamic_board_placement"}:
        monkeypatch.setenv("XIANGQI_SCENE_CONFIG", str(Path(__file__).resolve().parents[1] / "fixtures" / "legacy_yaw0_scene.json"))

    if request.module.__name__.rsplit(".", 1)[-1] == "test_phase3_final_master":
        monkeypatch.setenv("XIANGQI_SCENE_CONFIG", str(Path(__file__).resolve().parents[1] / "fixtures" / "retained_yaw0_scene.json"))
