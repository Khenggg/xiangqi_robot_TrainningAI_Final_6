"""The virtual move adapter must forward the configured playback speed.

pick_piece/place_piece default to 50.0, which the backend treats as "no
interpolation": one step and no sleep, so the viewer only sees the final pose of
each stage. The adapter therefore has to pass the backend's playback speed.
"""
from types import SimpleNamespace

import numpy as np

import src.hardware.simulation_adapter as adapter
from src.hardware.simulation_adapter import _playback_speed, execute_virtual_move


class _Piece:
    def __init__(self, position):
        self._position = np.array(position, dtype=float)

    def get_position_robot(self):
        return self._position


class _Runtime:
    """Minimal stand-in: no pybullet, but the same call shape as the real runtime."""

    def __init__(self, speed):
        self.backend = SimpleNamespace(default_speed_factor=speed)
        self.world = SimpleNamespace(
            pieces={"red_pawn_1": _Piece([0.1, 0.2, 0.01])},
            get_attached_piece=lambda: None,
        )
        self.placement_state = SimpleNamespace(
            is_in_bounds_robot=lambda position, xy_margin_m=0.0: True,
            cell_to_robot_xyz=lambda row, col: np.array([0.5, 0.5, 0.0]),
        )
        self.calls = []

    def find_nearest_cell(self, position):
        return (6, 4)

    def pick_piece(self, piece_id, **kwargs):
        self.calls.append(("pick", kwargs.get("speed_factor")))
        captured = self.world.pieces.get(piece_id)
        if captured is not None and piece_id.startswith("black"):
            captured._position = np.array([0.4, 0.0, 0.0])  # moved to the capture slot
        return {"success": True}

    def place_piece(self, **kwargs):
        self.calls.append(("place", kwargs.get("speed_factor")))
        return {"success": True}


def test_playback_speed_reads_the_backend_configuration():
    assert _playback_speed(_Runtime(0.2)) == 0.2
    assert _playback_speed(SimpleNamespace()) is None


def test_virtual_move_forwards_the_playback_speed_to_pick_and_place():
    runtime = _Runtime(0.2)
    result = execute_virtual_move(runtime, 4, 6, 4, 5, False, piece_id="red_pawn_1")
    assert getattr(result, "success", False), getattr(result, "message", result)
    assert runtime.calls == [("pick", 0.2), ("place", 0.2)]


def test_virtual_capture_forwards_the_playback_speed_to_every_motion():
    runtime = _Runtime(0.5)
    runtime.world.pieces["black_rook_1"] = _Piece([0.5, 0.5, 0.01])
    runtime.world.capture_piece = lambda piece_id: SimpleNamespace(piece_id=piece_id)
    runtime.calls.clear()

    original = adapter.select_capture_slot
    adapter.select_capture_slot = lambda _runtime: [0.4, 0.0, 0.0]
    try:
        result = execute_virtual_move(runtime, 4, 6, 4, 5, True,
                                      piece_id="red_pawn_1", captured_piece_id="black_rook_1")
    finally:
        adapter.select_capture_slot = original

    assert getattr(result, "success", False), getattr(result, "message", result)
    assert [speed for _, speed in runtime.calls] == [0.5, 0.5, 0.5, 0.5]
