from types import SimpleNamespace

from src.hardware.hardware_manager import HardwareManager
from src.ui.board_renderer import DIFFICULTY_OPTIONS, HOME_VS_ROBOT_RECT, BoardRenderer


def test_home_screen_vs_robot_button_starts_only_that_flow():
    assert BoardRenderer.home_action_from_pixel(*HOME_VS_ROBOT_RECT.center) == "vs_robot"
    assert BoardRenderer.home_action_from_pixel(0, 0) is None


def test_difficulty_menu_maps_each_card_to_its_engine():
    for key, _, rect, _ in DIFFICULTY_OPTIONS:
        assert BoardRenderer.difficulty_from_pixel(*rect.center) == key
    assert BoardRenderer.difficulty_from_pixel(0, 0) is None


def test_unavailable_policy_cannot_be_selected(tmp_path):
    manager = HardwareManager.__new__(HardwareManager)
    manager.config = SimpleNamespace(
        EASY_POLICY_MODEL=str(tmp_path / "missing-easy.pt"),
        MEDIUM_POLICY_MODEL=str(tmp_path / "missing-medium.pt"),
        MOONFISH_EXE=str(tmp_path / "missing-moonfish.py"),
        AI_DIFFICULTY="hard",
    )
    manager._difficulty_availability = {"easy": False, "medium": False, "hard": False, "impossible": False}
    available = manager.difficulty_availability()
    assert available == {"easy": False, "medium": False, "hard": False, "impossible": False}
    ok, message = manager.select_difficulty("easy")
    assert not ok
    assert "not ready" in message


def test_selecting_the_current_difficulty_still_confirms_the_profile():
    manager = HardwareManager.__new__(HardwareManager)
    manager.config = SimpleNamespace(
        AI_DIFFICULTY="easy",
        AI_DIFFICULTY_PROFILES={
            "easy": {"depth": 3, "nodes": 2_000, "temperature": 1.35, "think_ms": 200},
        },
    )
    manager.ai_ctrl = None
    manager._difficulty_availability = {"easy": True}

    ok, message = manager.select_difficulty("easy")

    assert ok
    assert "Đã chọn EASY" in message
    assert "2,000 nodes" in message
