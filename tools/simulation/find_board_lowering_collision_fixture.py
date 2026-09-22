#!/usr/bin/env python3
"""
Reproducibly find a joint configuration fixture (q_fixture) satisfying BC7/BC8 invariants:
1. Initial board-to-robot clearance strictly > 5.0 mm (and >= 7.0 mm).
2. Negative board lowering (-10 mm) sweeps into arm/gripper at step k > 0.
3. First blocking step > 0.
4. Minimum swept clearance <= 5.0 mm.
5. sim.set_board_placement(board_height_offset_mm=-10.0) rejects with
   BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR.
"""

from pathlib import Path
import sys
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.runtime import VirtualXiangqiSimulation


def search_fixture():
    sim = VirtualXiangqiSimulation()
    sim.start()
    sim.reset_robot()

    print("Searching for valid q_fixture satisfying BC7/BC8...")

    for j1 in np.linspace(-65.0, -20.0, 46):
        for j2 in np.linspace(100.0, 155.0, 56):
            for j3 in np.linspace(-155.0, -100.0, 56):
                q = [0.0, float(round(j1, 2)), float(round(j2, 2)), float(round(j3, 2)), -90.0, 0.0]
                sim.world.sync_robot_runtime_configuration(np.radians(q))
                init_dist, closest = sim.world.get_board_to_robot_clearance()
                init_mm = init_dist * 1000.0
                if 7.0 <= init_mm <= 12.0:
                    swept = sim.world.check_board_swept_volume_collision(0.0, -0.010)
                    if not swept.is_safe:
                        k = swept.details.get("first_blocking_step", 0)
                        min_clr = swept.details.get("minimum_clearance_mm", 999.0)
                        if k > 0 and min_clr <= 5.0:
                            sim.backend.move_joint(q)
                            sim.world.sync_robot_runtime_configuration(np.radians(q))
                            res = sim.set_board_placement(board_height_offset_mm=-10.0)
                            if not res.get("success", True) and res.get("status") == "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR":
                                block_body = swept.details.get("blocking_body", closest)
                                print("FOUND VALID FIXTURE:")
                                print(f"q_fixture = {q}")
                                print(f"initial clearance = {init_mm:.2f} mm")
                                print(f"first blocking step = {k}")
                                print(f"minimum clearance = {min_clr:.2f} mm")
                                print(f"link pair = {block_body}")
                                sim.stop()
                                return q, init_mm, k, min_clr, block_body

    sim.stop()
    print("No fixture found.")
    return None


if __name__ == "__main__":
    search_fixture()
