// tests/unit/test_viewer_single_motion_authority.mjs
// Verifies:
// 1. Viewer code contains NO client-side trajectory planners or timers (Single Motion Authority).
// 2. Outgoing client WebSocket command contract { command: "EXECUTE_3STAGE", src: [r, c], dst: [r, c] }.
// 3. Scene configuration classifies tool offset as USER_MEASURED_CAD_REPORTED and visual asset as VISUAL_CALIBRATION_PROVISIONAL.
// 4. No stale references to "+1.5mm" remain in HTML or viewer code.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

console.log("Running Viewer Single Motion Authority Verification Tests (Node.js)...");

// 1. Test that main.mjs has NO client-side trajectoryQueue or timer-based stepping
const mainMjsPath = path.resolve(repoRoot, "robot-3d-viewer", "main.mjs");
const mainMjsContent = fs.readFileSync(mainMjsPath, "utf-8");

assert.ok(
  !mainMjsContent.includes("trajectoryQueue"),
  "main.mjs must NOT contain 'trajectoryQueue' (client-side planning removed)"
);
assert.ok(
  !mainMjsContent.includes("runNextTrajectoryStep"),
  "main.mjs must NOT contain 'runNextTrajectoryStep' (timer-based stepping removed)"
);
assert.ok(
  !mainMjsContent.includes("executeSafeTrajectory"),
  "main.mjs must NOT contain 'executeSafeTrajectory' (client-side trajectory generator removed)"
);
assert.ok(
  !mainMjsContent.includes("advanceLiveInterpolation"),
  "main.mjs must NOT contain 'advanceLiveInterpolation' (fake interpolation timer removed)"
);

console.log("  [PASS] main.mjs confirmed free of client-side motion authorities and timer stepping.");

// 2. Test outgoing command contract in main.mjs
assert.ok(
  mainMjsContent.includes('"EXECUTE_3STAGE"'),
  "main.mjs must dispatch authoritative command 'EXECUTE_3STAGE' over WebSocket"
);
assert.ok(
  mainMjsContent.includes("handleBackendTrajectoryStage"),
  "main.mjs must consume backend trajectory_stage telemetry"
);

// 3. Test truthful metadata in shared/virtual_fr3_scene.json
const sceneJsonPath = path.resolve(repoRoot, "shared", "virtual_fr3_scene.json");
const sceneData = JSON.parse(fs.readFileSync(sceneJsonPath, "utf-8"));

assert.equal(
  sceneData?.tool_transform?.status,
  "USER_MEASURED_CAD_REPORTED",
  "tool_transform.status must be USER_MEASURED_CAD_REPORTED"
);
assert.equal(
  sceneData?.tool_transform?.visual_asset_status,
  "VISUAL_CALIBRATION_PROVISIONAL",
  "tool_transform.visual_asset_status must be VISUAL_CALIBRATION_PROVISIONAL"
);
assert.deepEqual(
  sceneData?.tool_transform?.flange_to_tcp_xyz_m,
  [0.0, 0.0, 0.218],
  "flange_to_tcp_xyz_m must be [0, 0, 0.218]"
);

console.log("  [PASS] shared/virtual_fr3_scene.json has honest tool and visual asset classification.");

// 4. Test index.html UI truthful metadata presentation and no stale +1.5mm
const indexPath = path.resolve(repoRoot, "robot-3d-viewer", "index.html");
const indexContent = fs.readFileSync(indexPath, "utf-8");

assert.ok(
  indexContent.includes("USER_MEASURED_CAD_REPORTED"),
  "index.html must display USER_MEASURED_CAD_REPORTED"
);
assert.ok(
  indexContent.includes("VISUAL_CALIBRATION_PROVISIONAL"),
  "index.html must display VISUAL_CALIBRATION_PROVISIONAL"
);
assert.ok(
  !indexContent.includes("+1.5mm"),
  "index.html must NOT contain stale '+1.5mm' references"
);
assert.ok(
  !mainMjsContent.includes("+1.5mm"),
  "main.mjs must NOT contain stale '+1.5mm' references"
);

console.log("  [PASS] UI displays truthful metadata and contains no stale +1.5mm references.");
console.log("ALL VIEWER SINGLE MOTION AUTHORITY TESTS PASSED SUCCESSFULLY!");
