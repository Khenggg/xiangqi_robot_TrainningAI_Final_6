from types import SimpleNamespace

from src.hardware.hardware_manager import HardwareManager
from src.ui.board_renderer import DIFFICULTY_OPTIONS, BoardRenderer


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
    manager._difficulty_availability = {"easy": False, "medium": False, "hard": False}
    available = manager.difficulty_availability()
    assert available == {"easy": False, "medium": False, "hard": False}
    ok, message = manager.select_difficulty("easy")
    assert not ok
    assert "not ready" in message
