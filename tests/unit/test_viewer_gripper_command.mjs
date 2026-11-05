// tests/unit/test_viewer_gripper_command.mjs
// Physical gripper_command packets may drive viewer animation; virtual ones never do.
import assert from "node:assert/strict";
import { gripperCommandApplies } from "../../robot-3d-viewer/live_state.mjs";

const closePacket = {
  type: "gripper_command",
  source: "PHYSICAL",
  phase: "CLOSE",
  piece_id: "black_cannon_0",
  physical_grasp_verified: false,
};

assert.equal(gripperCommandApplies(closePacket, "PHYSICAL"), true);
assert.equal(gripperCommandApplies({ ...closePacket, phase: "OPEN" }, "PHYSICAL"), true);
assert.equal(gripperCommandApplies(closePacket, "VIRTUAL"), false);
assert.equal(gripperCommandApplies(closePacket, undefined), false);
assert.equal(gripperCommandApplies({ ...closePacket, source: "VIRTUAL" }, "PHYSICAL"), false);
assert.equal(gripperCommandApplies({ ...closePacket, phase: "BAD" }, "PHYSICAL"), false);
assert.equal(gripperCommandApplies({ ...closePacket, piece_id: "" }, "PHYSICAL"), false);
assert.equal(gripperCommandApplies({ ...closePacket, type: "world_state" }, "PHYSICAL"), false);

console.log("Viewer gripper_command contract passed");
