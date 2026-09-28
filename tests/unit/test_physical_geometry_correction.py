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
import pytest

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
from src.simulation.runtime import VirtualXiangqiSimulation


class TestPhysicalGeometryCorrection(unittest.TestCase):
    """Verify the active measured flange-to-tip geometry and virtual collision contract."""

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
        self.assertEqual(can_tcp.get("flange_to_tcp_xyz_m"), [0.0, 0.0, 0.1683])
        self.assertEqual(can_tcp.get("flange_to_tcp_distance_m"), 0.1683)
        self.assertEqual(can_tcp.get("length_mm"), 168.3)
        self.assertEqual(can_tcp.get("provenance"), "MEASURED_PHYSICAL")

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
        self.assertEqual(tool.canonical_tcp_offset_m, (0.0, 0.0, 0.1683))
        self.assertEqual(tool.flange_to_tcp_distance_m, 0.1683)
        self.assertEqual(tool.flange_to_tcp_distance_mm, 168.3)
        self.assertEqual(tool.cad_length_mm, 147.5)
        self.assertEqual(tool.legacy_unverified_length_mm, 218.0)
        self.assertEqual(tool.status, ProvenanceStatus.MEASURED_PHYSICAL)
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
        self.assertEqual(prov["tool_length"].status, tool.status)

    def test_tcp_transform_matches_physical_profile(self):
        """Verify all subsystems match the canonical 168.3 mm tool transform."""
        # 1. Virtual backend
        backend = VirtualFR3Backend()
        self.assertAlmostEqual(backend.flange_to_tcp_distance_m, 0.1683, places=4)
        self.assertAlmostEqual(backend._T_flange_tcp[2, 3], 0.1683, places=4)

        # 2. BoardPlacementAnalyzer
        analyzer = BoardPlacementAnalyzer()
        self.assertAlmostEqual(analyzer.tool_length_m, 0.1683, places=4)
        self.assertAlmostEqual(analyzer.tool_length_mm, 168.3, places=1)

        # 3. PyBullet world
        world = VirtualPhysicalWorld()
        self.assertAlmostEqual(world._tool_offset[2], 0.2683, places=4)
        world.close()

        # 4. Scene configuration file
        scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"
        with open(scene_path, "r", encoding="utf-8") as f:
            scene_cfg = json.load(f)
        tool_cfg = scene_cfg.get("tool_transform", {})
        self.assertEqual(tool_cfg.get("status"), "MEASURED_PHYSICAL")
        self.assertEqual(tool_cfg.get("flange_to_tcp_xyz_m"), [0.0, 0.0, 0.1683])

    def test_gripper_mesh_tcp_alignment(self):
        """Verify CAD visual mesh is not artificially distorted or scaled to force-match TCP."""
        asset_path = _PROJECT_ROOT / "shared" / "gripper_visual_asset.json"
        self.assertTrue(asset_path.is_file())
        with open(asset_path, "r", encoding="utf-8") as f:
            asset_cfg = json.load(f)

        # Visual mesh remains provisional and must not be used as the collision envelope.
        self.assertAlmostEqual(asset_cfg.get("scale_to_m"), 0.0008, places=6)
        self.assertEqual(asset_cfg.get("status"), "VISUAL_CALIBRATION_PROVISIONAL")
        tool = get_canonical_tool_geometry()
        self.assertAlmostEqual(tool.cad_length_mm, 147.5, places=1)
        self.assertAlmostEqual(tool.flange_to_tcp_distance_mm, 168.3, places=1)
        delta_mm = tool.flange_to_tcp_distance_mm - tool.cad_length_mm
        self.assertAlmostEqual(delta_mm, 20.8, places=1)

    def test_90_cell_reachability_with_measured_tool(self):
        """Historical reachability seeds must be marked stale after the geometry change."""
        dataset_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
        self.assertTrue(dataset_path.is_file(), f"Dataset missing: {dataset_path}")
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metadata = data.get("metadata", {})
        self.assertEqual(metadata.get("status"), "STALE/UNVALIDATED")
        self.assertNotAlmostEqual(metadata.get("gripper_length_m"), get_canonical_tool_geometry().flange_to_tcp_distance_m)
        self.assertEqual(metadata.get("total_cells"), 90)

        cells = data.get("cells", [])
        self.assertEqual(len(cells), 90)
        for cell in cells:
            self.assertTrue(cell["reachable"], f"Cell ({cell['row']}, {cell['col']}) unreachable")
            self.assertEqual(len(cell["grasp_joints_deg"]), 6)
            self.assertEqual(len(cell["approach_joints_deg"]), 6)
            self.assertFalse(cell.get("penetrates_board", False))

    def test_board_collision_with_measured_tool(self):
        """Measure clearance only for reachable poses; track blocked poses explicitly."""
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            reachable = set()
            blocked = set()
            for r, c in [(0, 0), (0, 8), (9, 0), (9, 8), (4, 4), (0, 4), (9, 4), (4, 0), (4, 8)]:
                piece_id = sim._get_piece_at_cell(r, c)
                for stage, z in (("hover", sim.board_surface_z + 0.070),
                                 ("grasp", sim.board_surface_z + sim.geom.piece_height_mm / 2000.0)):
                    xyz = sim.cell_to_robot_xyz_m(r, c, z)
                    pose = [v * 1000.0 for v in xyz] + list(sim.target_tool_euler_deg)
                    cands = sim.backend.solve_tcp_ik_candidates(
                        pose, allow_alternate_yaw=True, allowed_grasp_piece_id=piece_id
                    )
                    if not cands:
                        blocked.add((r, c, stage))
                        continue
                    reachable.add((r, c, stage))
                    q = cands[0].joints_rad
                    self.assertTrue(sim.collision_guard.validate_configuration(
                        q, allowed_grasp_piece_id=piece_id
                    ).safe)
                    sim.world.sync_robot_collision_configuration(q)
                    clearance_m, _ = sim.world.get_board_to_robot_clearance()
                    self.assertGreaterEqual(clearance_m, 0.0005)
            self.assertGreaterEqual(len(reachable), 14, f"Reachability regressed: {blocked}")
            self.assertIn((4, 4, "grasp"), reachable)
            self.assertIn((0, 0, "grasp"), reachable)
        finally:
            sim.stop()

    @pytest.mark.acceptance
    def test_gate_18_of_18_key_poses_acceptance(self):
        """
        Simulator endpoint gate for 18 hover/grasp poses across nine cells.
        This does not test the path, bilateral jaw contact, or hardware safety.
        """
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            reachable = set()
            blocked = set()
            for r, c in [(0, 0), (0, 8), (9, 0), (9, 8), (4, 4), (0, 4), (9, 4), (4, 0), (4, 8)]:
                piece_id = sim._get_piece_at_cell(r, c)
                for stage, z in (("hover", sim.board_surface_z + 0.070),
                                 ("grasp", sim.board_surface_z + sim.geom.piece_height_mm / 2000.0)):
                    xyz = sim.cell_to_robot_xyz_m(r, c, z)
                    pose = [v * 1000.0 for v in xyz] + list(sim.target_tool_euler_deg)
                    cands = sim.backend.solve_tcp_ik_candidates(
                        pose, allow_alternate_yaw=True, allowed_grasp_piece_id=piece_id
                    )
                    if not cands:
                        blocked.add((r, c, stage))
                        continue
                    q = cands[0].joints_rad
                    if not sim.collision_guard.validate_configuration(q, allowed_grasp_piece_id=piece_id).safe:
                        blocked.add((r, c, stage))
                        continue
                    reachable.add((r, c, stage))
            self.assertEqual(
                len(reachable), 18,
                f"ACCEPTANCE GATE NOT PASSED (chưa đạt): Only {len(reachable)}/18 key poses reachable. Blocked: {blocked}"
            )
        finally:
            sim.stop()

    def test_pick_place_rejects_unverified_jaw_contact(self):
        """The current CAD stroke cannot claim a physical grip on a 22.5 mm piece."""
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            self.assertTrue(sim.backend.collision_guard_enabled)
            result = sim.execute_3stage_trajectory((0, 0), (4, 4), grasp_piece=True)
            self.assertFalse(result["success"])
            self.assertEqual(result["failed_stage"], "GRASP")
            self.assertIn("NO_JAW_CONTACT", result["error"])
            self.assertIsNone(sim.world.get_attached_piece())
            self.assertFalse(sim.world.gripper.is_closed)
        finally:
            sim.stop()


if __name__ == "__main__":
    unittest.main()
