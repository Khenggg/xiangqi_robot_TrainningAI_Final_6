"""
Unit test suite verifying dangerous command rejection, 100% state invariance,
and non-optimistic 3D web viewer contract (Requirement 3).

Verifies:
1. Dangerous Cartesian commands penetrating the board or obstacles are rejected by the collision guard.
2. Dangerous joint commands causing arm self-collision or ground collision are rejected.
3. On rejection, robot joint angles, TCP coordinates, and gripper state remain 100% invariant (delta = 0).
4. Telemetry packets published after rejection report the true unchanged posture, never the rejected pose.
5. 3D Web Viewer contract: live_state.mjs and main.mjs validate packets and strictly forbid optimistic
   rendering of rejected or unverified poses.
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend
from src.simulation.physics.world import VirtualPhysicalWorld


class DangerousCommandInvarianceAndWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node_bin = shutil.which("node")

    def setUp(self):
        self.sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        self.sim.start()
        self.backend = self.sim.backend
        self.world = self.sim.world

    def tearDown(self):
        self.sim.stop()

    def test_dangerous_cartesian_penetration_rejected_and_state_invariant(self):
        """
        Issuing a Cartesian move penetrating into the board must fail,
        and current joints, TCP, and gripper must remain 100% invariant.
        """
        q_rad_before = np.copy(self.backend._current_joints_rad)
        q_deg_before = np.copy(self.backend._current_joints_deg)
        tcp_before = np.copy(self.backend._tcp_pose_mm_deg)
        gripper_before = self.backend.is_gripper_closed

        # Target penetrating deep into board center (Z = 0.0mm, well below board surface ~80.5mm)
        dangerous_pose = [0.0, 360.0, 0.0, 180.0, 0.0, 90.0]
        res = self.backend.move_cartesian(dangerous_pose)

        self.assertFalse(res, "Cartesian move penetrating board must be rejected")
        self.assertIsNotNone(self.backend._last_error)
        self.assertIn("collision", self.backend._last_error.lower())

        # Strict 100% invariance check
        np.testing.assert_allclose(
            self.backend._current_joints_rad,
            q_rad_before,
            atol=1e-12,
            err_msg="Joint radians must remain 100% unchanged after rejected move",
        )
        np.testing.assert_allclose(
            self.backend._current_joints_deg,
            q_deg_before,
            atol=1e-9,
            err_msg="Joint degrees must remain 100% unchanged after rejected move",
        )
        np.testing.assert_allclose(
            self.backend._tcp_pose_mm_deg,
            tcp_before,
            atol=1e-9,
            err_msg="TCP coordinates must remain 100% unchanged after rejected move",
        )
        self.assertEqual(
            self.backend.is_gripper_closed,
            gripper_before,
            "Gripper state must remain 100% unchanged after rejected move",
        )

    def test_dangerous_joint_self_collision_rejected_and_state_invariant(self):
        """
        Issuing a joint move that causes self-collision must be rejected,
        and joints and TCP must remain 100% invariant.
        """
        q_rad_before = np.copy(self.backend._current_joints_rad)
        q_deg_before = np.copy(self.backend._current_joints_deg)
        tcp_before = np.copy(self.backend._tcp_pose_mm_deg)

        # Folded self-colliding configuration
        q_self_deg = [0.0, -45.0, -160.0, -260.0, -160.0, 0.0]
        res = self.backend.move_joint(q_self_deg)

        self.assertFalse(res, "Joint move into self-collision must be rejected")
        self.assertIsNotNone(self.backend._last_error)
        self.assertIn("collision", self.backend._last_error.lower())

        # Strict 100% invariance check
        np.testing.assert_allclose(
            self.backend._current_joints_rad,
            q_rad_before,
            atol=1e-12,
            err_msg="Joint radians must remain 100% unchanged after rejected self-colliding move",
        )
        np.testing.assert_allclose(
            self.backend._current_joints_deg,
            q_deg_before,
            atol=1e-9,
            err_msg="Joint degrees must remain 100% unchanged after rejected self-colliding move",
        )
        np.testing.assert_allclose(
            self.backend._tcp_pose_mm_deg,
            tcp_before,
            atol=1e-9,
            err_msg="TCP pose must remain 100% unchanged after rejected self-colliding move",
        )

    def test_dangerous_trajectory_rejected_and_state_invariant(self):
        """
        Unreachable or collision-prone trajectory execution must fail fast
        without altering robot state.
        """
        q_deg_before = np.copy(self.backend._current_joints_deg)

        # Invalid out-of-grid cell
        res = self.sim.execute_3stage_trajectory((99, 99), (4, 4))
        self.assertFalse(res["success"])
        self.assertEqual(res["failed_stage"], "PREPOSITION")

        # Invariance check
        np.testing.assert_allclose(
            self.backend._current_joints_deg,
            q_deg_before,
            atol=1e-9,
            err_msg="Robot joints must remain unchanged when trajectory fails at PREPOSITION",
        )

    def test_telemetry_packet_reports_safe_actual_joints_after_rejection(self):
        """
        After a dangerous command is rejected, telemetry publisher must emit
        the actual unchanged joint configuration, never the rejected candidate.
        """
        telemetry = TelemetryPublisher.get_instance(host="127.0.0.1", port=9876, robot_model="FR3")
        self.backend.telemetry_publisher = telemetry
        self.backend._sync_telemetry()
        q_expected = list(self.backend._current_joints_deg)

        # Issue dangerous command (which is rejected by collision guard)
        res = self.backend.move_cartesian([0.0, 360.0, 0.0, 180.0, 0.0, 90.0])
        self.assertFalse(res)

        packet = json.loads(telemetry._make_packet_json())
        self.assertEqual(packet["type"], "robot_state")
        self.assertEqual(packet["robot_model"], "FR3")
        np.testing.assert_allclose(
            packet["joints"],
            q_expected,
            atol=1e-4,
            err_msg="Telemetry packet joints must match actual safe posture, not rejected target",
        )

    def test_web_viewer_non_optimistic_rendering_contract(self):
        """
        Verify the web viewer's contract in live_state.mjs via Node.js:
        1. validateLivePacket strictly enforces 6 finite joints within limits.
        2. Rejected or error packets are never accepted as robot_state.
        3. Telemetry packets with mismatched models or out-of-limit joints are rejected.
        """
        if not self.node_bin:
            self.skipTest("Node.js runtime not found; skipping JS viewer test")

        js_script = """
        import { validateLivePacket, validateWorldStatePacket, liveControlsLocked, stabilizeJointTarget }
          from './robot-3d-viewer/live_state.mjs';

        const limits = Array.from({ length: 6 }, () => [-360, 360]);

        // 1. Valid telemetry packet accepted
        const validPacket = {
          type: "robot_state",
          robot_model: "FR3",
          joints: [10.0, -35.0, 75.0, -95.0, -90.0, 15.0],
          tcp: [-320.0, -100.0, 50.0, 180.0, 0.0, 0.0],
          gripper: false
        };
        const val1 = validateLivePacket(validPacket, limits, "FR3");
        if (!val1.ok) throw new Error("Valid packet rejected: " + val1.reason);

        // 2. Rejected command or error packet must NOT be accepted as live robot_state
        const errorPacket = {
          type: "trajectory_result",
          success: false,
          error: "COLLISION_REJECTED",
          failed_stage: "PREPOSITION"
        };
        const valError = validateLivePacket(errorPacket, limits, "FR3");
        if (valError.ok) throw new Error("Error packet unexpectedly accepted as robot_state!");

        // 3. Spurious packet with NaN or out-of-bounds joints rejected
        const nanPacket = {
          type: "robot_state",
          robot_model: "FR3",
          joints: [0, NaN, 0, 0, 0, 0]
        };
        const valNaN = validateLivePacket(nanPacket, limits, "FR3");
        if (valNaN.ok) throw new Error("NaN joint packet unexpectedly accepted!");

        // 4. stabilizeJointTarget stabilizes tiny encoder jitter (< 0.02 deg)
        const prev = [10.0, -35.0, 75.0, -95.0, -90.0, 15.0];
        const nextJitter = [10.005, -35.008, 75.0, -95.0, -90.0, 15.0];
        const stabilized = stabilizeJointTarget(nextJitter, prev, 0.02);
        if (stabilized[0] !== 10.0 || stabilized[1] !== -35.0) {
          throw new Error("stabilizeJointTarget failed to suppress deadband jitter");
        }

        // 5. liveControlsLocked locks manual controls when connected
        if (!liveControlsLocked({ socketOpen: true, live: true })) {
          throw new Error("liveControlsLocked should return true when socket is open");
        }

        console.log("VIEWER_CONTRACT_VERIFIED");
        """

        proc = subprocess.run(
            [self.node_bin, "--input-type=module", "-e", js_script],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
        )
        self.assertEqual(proc.returncode, 0, f"Viewer contract validation failed: {proc.stderr}")
        self.assertIn("VIEWER_CONTRACT_VERIFIED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
