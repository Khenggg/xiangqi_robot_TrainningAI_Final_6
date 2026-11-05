"""Configured virtual capture slots; never a physical teaching-point fallback."""
import numpy as np


def capture_slots(area, placement, geometry):
    if area.get("support") != "SIMULATED_FLOOR":
        raise ValueError("Capture projection requires configured SIMULATED_FLOOR slots")
    spacing = geometry.piece_diameter_mm / 1000.0 + 0.005
    slots = []
    for cell in area.get("slots_in_board_grid", []):
        if (not isinstance(cell, (list, tuple)) or len(cell) != 2
                or any(isinstance(value, bool) for value in cell)):
            raise ValueError("Capture slot requires finite row/column coordinates")
        row, col = np.asarray(cell, dtype=float)
        if not np.all(np.isfinite([row, col])):
            raise ValueError("Capture slot requires finite row/column coordinates")
        slot = placement.cell_to_robot_xyz(row, col)
        slot[2] = 0.0
        if placement.is_in_bounds_robot(slot, xy_margin_m=geometry.piece_diameter_mm / 2000.0 + 0.005):
            raise ValueError("Capture slot is inside the board")
        if any(np.linalg.norm(slot[:2] - previous[:2]) < spacing for previous in slots):
            raise ValueError("Configured capture slots overlap")
        slots.append(slot)
    return slots
