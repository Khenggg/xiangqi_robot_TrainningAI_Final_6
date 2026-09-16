"""
Tests for Phase P3.2.2: Scene Pose, Grounded Board Support, and Tool Orientation Parity.
Verifies:
1. Canonical home pose in virtual_fr3_scene.json is upright [0, -45, 90, -45, -90, 0].
2. VirtualFR3Backend.DEFAULT_HOME_JOINTS_DEG matches canonical home pose exactly.
3. Target tool orientation maps local +Z_tool to -Z_robot (downwards into board).
4. Robot-to-world rotation maps -Z_robot to -Y_world in Three.js coordinates.
5. Board normal +Z_robot maps to +Y_world in Three.js coordinates.
6. Validation of shared/gripper_visual_asset.json schema and edge cases.
"""

import json
from pathlib import Path
import numpy as np
import pytest

from src.simulation.physics.validation import validate_gripper_visual_asset
from src.simulation.virtual_fr3_backend import VirtualFR3Backend

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHARED_DIR = REPO_ROOT / "shared"
SCENE_JSON_PATH = SHARED_DIR / "virtual_fr3_scene.json"
GRIPPER_ASSET_JSON_PATH = SHARED_DIR / "gripper_visual_asset.json"


class TestScenePoseAndToolOrientation:
    @pytest.fixture(autouse=True)
    def setup(self):
        with open(SCENE_JSON_PATH, "r", encoding="utf-8") as f:
            self.scene = json.load(f)
        with open(GRIPPER_ASSET_JSON_PATH, "r", encoding="utf-8") as f:
            self.gripper_asset = json.load(f)

    def test_canonical_home_pose_upright(self):
        """Verify home pose is non-zero, finite, 6-dof, and matches upright pose."""
        assert "home_pose" in self.scene
        home_joints = self.scene["home_pose"].get("joints_deg")
        assert isinstance(home_joints, list)
        assert len(home_joints) == 6
        assert all(isinstance(v, (int, float)) and np.isfinite(v) for v in home_joints)

        # Expected canonical upright pose
        expected = [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]
        assert home_joints == expected
        # Crucially, must NOT be horizontal all-zeros
        assert home_joints != [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def test_backend_default_home_matches_scene_config(self):
        """VirtualFR3Backend.DEFAULT_HOME_JOINTS_DEG must match virtual_fr3_scene.json."""
        backend_home = VirtualFR3Backend.DEFAULT_HOME_JOINTS_DEG
        scene_home = self.scene["home_pose"]["joints_deg"]
        assert list(backend_home) == list(scene_home)

    def test_tool_orientation_points_downward_in_robot_base(self):
        """
        Target tool approach axis (+Z_tool = [0, 0, 1]^T) must map to -Z_robot ([0, 0, -1]^T).
        In the robot base frame, +Z is normal to the board, so -Z points down into the board.
        """
        target_matrix = np.array(
            self.scene["virtual_board_placement"]["target_tool_orientation_matrix"],
            dtype=float,
        )
        assert target_matrix.shape == (3, 3)

        # Verify orthogonal matrix with det = 1 or -1 (proper/improper rotation)
        det = np.linalg.det(target_matrix)
        assert np.isclose(np.abs(det), 1.0)

        # Local tool approach vector
        z_tool = np.array([0.0, 0.0, 1.0])
        approach_in_robot_base = target_matrix @ z_tool

        # Must point purely in -Z direction of robot base
        np.testing.assert_allclose(
            approach_in_robot_base,
            [0.0, 0.0, -1.0],
            atol=1e-6,
            err_msg="Tool approach axis (+Z_tool) must point downward along -Z_robot",
        )

    def test_tool_orientation_points_downward_in_viewer_world(self):
        """
        Approach vector in Three.js world must point downward along -Y_world ([0, -1, 0]^T).
        Under R_robot_base_to_world:
        world_x = -robot_y
        world_y = +robot_z
        world_z = -robot_x
        Therefore -Z_robot maps to -Y_world.
        """
        r_world = np.array(
            self.scene["robot_base_to_3d_world"]["rotation_matrix"],
            dtype=float,
        )
        target_matrix = np.array(
            self.scene["virtual_board_placement"]["target_tool_orientation_matrix"],
            dtype=float,
        )
        z_tool = np.array([0.0, 0.0, 1.0])
        approach_in_robot_base = target_matrix @ z_tool

        approach_in_world = r_world @ approach_in_robot_base
        np.testing.assert_allclose(
            approach_in_world,
            [0.0, -1.0, 0.0],
            atol=1e-6,
            err_msg="Tool approach axis must point vertically down along -Y_world in Three.js",
        )

    def test_board_normal_maps_to_upward_in_viewer_world(self):
        """
        Board normal in robot base (+Z_robot) must map to +Y_world in Three.js.
        Approach axis (-Z_robot -> -Y_world) is anti-parallel to board normal.
        """
        r_world = np.array(
            self.scene["robot_base_to_3d_world"]["rotation_matrix"],
            dtype=float,
        )
        board_normal_base = np.array([0.0, 0.0, 1.0])
        board_normal_world = r_world @ board_normal_base
        np.testing.assert_allclose(board_normal_world, [0.0, 1.0, 0.0], atol=1e-6)

    def test_gripper_visual_asset_schema_valid(self):
        """Verify shared/gripper_visual_asset.json passes validation."""
        validate_gripper_visual_asset(self.gripper_asset)
        assert self.gripper_asset["schema_version"] == 1
        assert self.gripper_asset["status"] == "VISUAL_CALIBRATION_PROVISIONAL"
        assert self.gripper_asset["scale_to_m"] == 0.0008
        assert "fr3" in self.gripper_asset["profiles"]
        assert "fr5" in self.gripper_asset["profiles"]

    def test_gripper_visual_asset_rejects_invalid_inputs(self):
        """Negative tests for validate_gripper_visual_asset."""
        with pytest.raises(ValueError, match="JSON object"):
            validate_gripper_visual_asset("not a dict")

        with pytest.raises(ValueError, match="schema_version"):
            cfg = dict(self.gripper_asset)
            cfg["schema_version"] = 2
            validate_gripper_visual_asset(cfg)

        with pytest.raises(ValueError, match="scale_to_m"):
            cfg = dict(self.gripper_asset)
            cfg["scale_to_m"] = -0.5
            validate_gripper_visual_asset(cfg)

        with pytest.raises(ValueError, match="profiles.fr3"):
            cfg = dict(self.gripper_asset)
            cfg["profiles"] = {}
            validate_gripper_visual_asset(cfg)
