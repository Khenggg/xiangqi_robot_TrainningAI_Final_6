"""Characterize current mode routing and one-pass device initialization."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]


def test_launcher_keeps_hvr_and_robot_pvp_on_their_current_session_factories():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "_launch_session_mode")
    source = ast.get_source_segment((ROOT / "main.py").read_text(encoding="utf-8"), function)

    assert 'config.GAME_MODE == "HUMAN_VS_ROBOT"' in source
    assert "VscV3Session" in source
    assert "build_session(config, launch_options" in source


def test_both_game_states_own_their_opening_fen_and_baseline_is_not_fen_import():
    shared = (ROOT / "src/core/game_state.py").read_text(encoding="utf-8")
    donor = (ROOT / "src/modes/vsc_v3/core/game_state.py").read_text(encoding="utf-8")
    shared_hw = (ROOT / "src/hardware/hardware_manager.py").read_text(encoding="utf-8")
    donor_hw = (ROOT / "src/modes/vsc_v3/hardware/hardware_manager.py").read_text(encoding="utf-8")

    assert "self.current_fen = INITIAL_FEN" in shared
    assert "self.current_fen = INITIAL_FEN" in donor
    assert "capture_baseline" in shared_hw and "update_fen" not in shared_hw.split("def capture_baseline_if_needed", 1)[1].split("def clear_yolo_baseline", 1)[0]
    assert "capture_baseline" in donor_hw and "update_fen" not in donor_hw.split("def capture_baseline_if_needed", 1)[1].split("def clear_yolo_baseline", 1)[0]


def test_manual_f9_f10_enable_handler_is_in_outer_shared_mode_loop():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    handler = source.split("if (event.key == pygame.K_F9 and config.ROBOT_BACKEND == \"PHYSICAL\"", 1)[1]
    handler = handler.split("if hw.motion_worker.busy:", 1)[0]
    assert 'config.GAME_MODE != "HUMAN_VS_HUMAN_ROBOT"' in handler
    assert "pygame.K_F10" in handler
    assert 'config.GAME_MODE != "HUMAN_VS_HUMAN_ROBOT"' in handler
    assert "hw.activate_physical_game(state, commissioned=True)" in handler
    assert "automatic_startup.tick()" in source
    assert "K_F10" not in (ROOT / "src/modes/vsc_v3_session.py").read_text(encoding="utf-8")


def test_vsc_v3_startup_opens_its_robot_and_camera_once(monkeypatch):
    from src.modes.vsc_v3.hardware.hardware_manager import HardwareManager

    manager = HardwareManager.__new__(HardwareManager)
    manager._init_ai = Mock()
    manager._init_robot = Mock()
    manager._init_camera = Mock()

    assert manager.initialize_all() is manager
    manager._init_ai.assert_called_once_with()
    manager._init_robot.assert_called_once_with()
    manager._init_camera.assert_called_once_with()


def test_shared_physical_startup_opens_robot_and_camera_once(monkeypatch):
    from src.hardware.hardware_manager import HardwareManager

    profile = SimpleNamespace(ai_enabled=False, physical_robot_enabled=True,
                              simulation_enabled=False, camera_enabled=True,
                              game_mode="HUMAN_VS_HUMAN_ROBOT")
    manager = HardwareManager.__new__(HardwareManager)
    manager.profile = profile
    manager.startup_cancelled = None
    manager._init_robot = Mock()
    manager._init_camera = Mock()
    manager.cleanup = Mock()

    assert manager.initialize_all() is manager
    manager._init_robot.assert_called_once_with()
    manager._init_camera.assert_called_once_with()
