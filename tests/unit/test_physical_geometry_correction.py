"""
Unit test suite for Post-Merge Physical Geometry Correction.

Verifies:
1. test_tool_length_source
2. test_tcp_transform_matches_physical_profile
3. test_gripper_mesh_tcp_alignment
4. test_90_cell_reachability_with_measured_tool
5. test_board_collision_with_measured_tool
6. test_pick_place_trajectory_with_measured_tool
"""

import json
import math
from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import (
    ProvenanceStatus,
    ToolGeometry,
    get_canonical_tool_geometry,
    get_physical_constants_provenance,
    get_physical_geometry,
)
from src.simulation.placement import BoardPlacementAnalyzer, BoardPlacementState
from src.simulation.virtual_fr3_backend import VirtualFR3Backend
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.physics.collision_guard import FR3CollisionGuard


class TestPhysicalGeometryCorrection(unittest.TestCase):
    """Rigorous verification of physical geometry correction to 150mm canonical tool."""

    def test_tool_length_source(self):
        """Verify tool length is loaded from single source of truth with explicit provenance."""
        # 1. Verify shared/robot_profiles/fr3.json
        profile_path = _PROJECT_ROOT / "shared" / "robot_profiles" / "fr3.json"
        self.assertTrue(profile_path.is_file(), f"Profile missing: {profile_path}")
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tool_data = data.get("tool", {})
        self.assertEqual(tool_data.get("name"), "FAIRINO_FR3_PARALLEL_GRIPPER")
        self.assertEqual(tool_data.get("mount_type"), "DIRECT_J6_FLANGE")
        self.assertFalse(tool_data.get("has_adapter_plate"))

        can_tcp = tool_data.get("canonical_tcp", {})
        self.assertEqual(can_tcp.get("flange_to_tcp_xyz_m"), [0.0, 0.0, 0.150])
        self.assertEqual(can_tcp.get("flange_to_tcp_distance_m"), 0.150)
        self.assertEqual(can_tcp.get("length_mm"), 150.0)
        self.assertEqual(can_tcp.get("provenance"), "MEASURED_APPROXIMATE")

        cad_geom = tool_data.get("cad_geometry", {})
        self.assertEqual(cad_geom.get("length_mm"), 147.5)
        self.assertEqual(cad_geom.get("provenance"), "CAD_DERIVED")

        legacy_geom = tool_data.get("legacy_geometry", {})
        self.assertEqual(legacy_geom.get("length_mm"), 218.0)
        self.assertEqual(legacy_geom.get("provenance"), "LEGACY_UNVERIFIED")
        self.assertIn("OBSOLETE", legacy_geom.get("status", ""))

        # 2. Verify domain geometry loader
        tool = get_canonical_tool_geometry()
        self.assertIsInstance(tool, ToolGeometry)
        self.assertEqual(tool.canonical_tcp_offset_m, (0.0, 0.0, 0.150))
        self.assertEqual(tool.flange_to_tcp_distance_m, 0.150)
        self.assertEqual(tool.flange_to_tcp_distance_mm, 150.0)
        self.assertEqual(tool.cad_length_mm, 147.5)
        self.assertEqual(tool.legacy_unverified_length_mm, 218.0)
        self.assertEqual(tool.status, ProvenanceStatus.MEASURED_APPROXIMATE)
        self.assertEqual(tool.cad_status, ProvenanceStatus.CAD_DERIVED)
        self.assertEqual(tool.legacy_status, ProvenanceStatus.LEGACY_UNVERIFIED)

        # 3. Verify provenance registry coverage
        prov = get_physical_constants_provenance()
        critical_keys = [
            "tool_length", "cad_tool_length", "legacy_tool_length",
            "board_outer_width", "board_outer_length", "board_thickness",
            "grid_column_spacing", "grid_row_spacing", "piece_diameter",
            "piece_height", "board_pose_nominal", "tool_orientation",
            "SAFE_Z", "PICK_Z", "PLACE_Z"
        ]
        for key in critical_keys:
            self.assertIn(key, prov, f"Missing provenance record for {key}")
            rec = prov[key]
            self.assertIsInstance(rec.status, ProvenanceStatus)
            self.assertTrue(len(rec.description) > 0)

    def test_tcp_transform_matches_physical_profile(self):
        """Verify all subsystems match the canonical 150mm tool transform."""
        # 1. Virtual backend
        backend = VirtualFR3Backend()
        self.assertAlmostEqual(backend.flange_to_tcp_distance_m, 0.150, places=4)
        self.assertAlmostEqual(backend._T_flange_tcp[2, 3], 0.150, places=4)

        # 2. BoardPlacementAnalyzer
        analyzer = BoardPlacementAnalyzer()
        self.assertAlmostEqual(analyzer.tool_length_m, 0.150, places=4)
        self.assertAlmostEqual(analyzer.tool_length_mm, 150.0, places=1)

        # 3. PyBullet world
        world = VirtualPhysicalWorld()
        self.assertAlmostEqual(world._tool_offset[2], 0.150, places=4)
        world.close()

        # 4. Scene configuration file
        scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"
        with open(scene_path, "r", encoding="utf-8") as f:
            scene_cfg = json.load(f)
        tool_cfg = scene_cfg.get("tool_transform", {})
        self.assertEqual(tool_cfg.get("status"), "MEASURED_APPROXIMATE")
        self.assertEqual(tool_cfg.get("flange_to_tcp_xyz_m"), [0.0, 0.0, 0.150])

    def test_gripper_mesh_tcp_alignment(self):
        """Verify CAD visual mesh is not artificially distorted or scaled to force-match TCP."""
        asset_path = _PROJECT_ROOT / "shared" / "gripper_visual_asset.json"
        self.assertTrue(asset_path.is_file())
        with open(asset_path, "r", encoding="utf-8") as f:
            asset_cfg = json.load(f)

        # Mesh scale should remain authentic CAD tessellation scale (0.0008), not scaled to 150mm
        self.assertAlmostEqual(asset_cfg.get("scale_to_m"), 0.0008, places=6)
        
        # Verify CAD length is recorded as 147.5mm while canonical TCP is 150.0mm (+2.5mm grasp center offset)
        tool = get_canonical_tool_geometry()
        self.assertAlmostEqual(tool.cad_length_mm, 147.5, places=1)
        self.assertAlmostEqual(tool.flange_to_tcp_distance_mm, 150.0, places=1)
        delta_mm = tool.flange_to_tcp_distance_mm - tool.cad_length_mm
        self.assertAlmostEqual(delta_mm, 2.5, places=1, msg="TCP grasp center must be 2.5mm beyond fingertip edge")

    def test_90_cell_reachability_with_measured_tool(self):
        """Verify shared/cell_reachability_dataset.json reflects measured tool and 100% reachability."""
        dataset_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
        self.assertTrue(dataset_path.is_file(), f"Dataset missing: {dataset_path}")
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metadata = data.get("metadata", {})
        self.assertAlmostEqual(metadata.get("gripper_length_m"), 0.150, places=3)
        self.assertEqual(metadata.get("total_cells"), 90)

        cells = data.get("cells", [])
        self.assertEqual(len(cells), 90)
        for cell in cells:
            self.assertTrue(cell["reachable"], f"Cell ({cell['row']}, {cell['col']}) unreachable")
            self.assertEqual(len(cell["grasp_joints_deg"]), 6)
            self.assertEqual(len(cell["approach_joints_deg"]), 6)
            self.assertFalse(cell.get("penetrates_board", False))

    def test_board_collision_with_measured_tool(self):
        """Verify robot links maintain positive clearance to board across extreme board cells."""
        dataset_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cells_dict = {(c["row"], c["col"]): c for c in data["cells"]}
        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)

        # Test all corners, edges, and center
        test_cells = [(0, 0), (0, 8), (9, 0), (9, 8), (4, 4), (0, 4), (9, 4), (4, 0), (4, 8)]
        for r, c in test_cells:
            cell_data = cells_dict[(r, c)]
            q_gr = np.deg2rad(cell_data["grasp_joints_deg"])
            q_ap = np.deg2rad(cell_data["approach_joints_deg"])

            # Validate approach configuration
            col_ap = guard.validate_configuration(q_ap)
            self.assertTrue(col_ap.safe, f"Approach collision at ({r}, {c}): {col_ap.failure_reason}")

            # Validate grasp configuration
            col_gr = guard.validate_configuration(q_gr, allowed_grasp_piece_id="*")
            self.assertTrue(col_gr.safe, f"Grasp collision at ({r}, {c}): {col_gr.failure_reason}")

        world.close()

    def test_pick_place_trajectory_with_measured_tool(self):
        """Verify 3-stage MoveL pick trajectory (Approach -> Land -> Lift) succeeds without collision."""
        dataset_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cells_dict = {(c["row"], c["col"]): c for c in data["cells"]}
        cell_44 = cells_dict[(4, 4)]
        q_ap = np.deg2rad(cell_44["approach_joints_deg"])

        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)
        backend = VirtualFR3Backend()
        backend.set_collision_guard(guard)

        state = BoardPlacementState.compute(forward_shift_mm=25.0, safe_transit_height_mm=40.0, board_yaw_deg=90.0)
        p_ap = state.cell_to_robot_xyz(4, 4, 0.040)
        p_gr = state.cell_to_robot_xyz(4, 4, 0.004715)
        pose_ap_mm = [p_ap[0] * 1000.0, p_ap[1] * 1000.0, p_ap[2] * 1000.0, 180.0, 0.0, 90.0]
        pose_gr_mm = [p_gr[0] * 1000.0, p_gr[1] * 1000.0, p_gr[2] * 1000.0, 180.0, 0.0, 90.0]

        # Land MoveL: Approach -> Grasp
        plan_land = backend.plan_cartesian(q_ap, pose_gr_mm, samples=15, check_collision=True, allowed_grasp_piece_id="*")
        self.assertTrue(plan_land.success, f"Land MoveL failed: {plan_land.failure_reason}")

        # Lift MoveL: Grasp -> Approach
        plan_lift = backend.plan_cartesian(plan_land.final_q, pose_ap_mm, samples=15, check_collision=True, allowed_grasp_piece_id="*")
        self.assertTrue(plan_lift.success, f"Lift MoveL failed: {plan_lift.failure_reason}")

        world.close()


if __name__ == "__main__":
    unittest.main()
