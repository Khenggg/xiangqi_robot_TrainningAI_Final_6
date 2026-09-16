// tests/unit/test_viewer_gripper_and_telemetry.mjs
// Node.js functional tests for Phase P3.2:
// 1. Canonical gripper profile parsing & procedural parameter parity
// 2. Strict gripper profile validation & rejection of malformed data
// 3. Strict world_state telemetry validation (no boolean coercion, quaternion checks)
// 4. Robot arm builder profile scoping requirement

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  parseGripperProfile,
  computeProceduralGripperParameters,
} from "../../robot-3d-viewer/gripper_profile.mjs";
import { validateWorldStatePacket } from "../../robot-3d-viewer/live_state.mjs";
import { parseStartLayout } from "../../robot-3d-viewer/layout.mjs";
import { parseGripperVisualAsset } from "../../robot-3d-viewer/gripper_asset.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

console.log("Running Viewer Gripper & Telemetry Functional Tests (Node.js)...");

// ============================================================================
// 1. CANONICAL PROFILE -> PARSED PROFILE -> GEOMETRY PARAMETERS
// ============================================================================
const gripperJsonPath = path.resolve(repoRoot, "shared", "virtual_gripper_profile.json");
const rawGripper = JSON.parse(fs.readFileSync(gripperJsonPath, "utf-8"));

const parsedProfile = parseGripperProfile(rawGripper);
const params = computeProceduralGripperParameters(parsedProfile);

// Parity checks
assert.deepEqual(params.palmDimensionsM, rawGripper.palm.dimensions_m, "Palm dimensions must match JSON");
assert.deepEqual(params.jawDimensionsM, rawGripper.jaw.dimensions_m, "Jaw dimensions must match JSON");
assert.equal(params.openWidthM, rawGripper.stroke.open_width_m, "Open width must match JSON");
assert.equal(params.closedWidthM, rawGripper.stroke.closed_width_m, "Closed width must match JSON");
assert.equal(params.travelAxis, rawGripper.stroke.travel_axis, "Travel axis must match JSON");
assert.deepEqual(params.tcpToGraspCenterM, rawGripper.tcp_to_grasp_center_m, "TCP to grasp center must match JSON");
assert.equal(params.colorHex, rawGripper.visual.color_hex, "Color hex must match JSON");
assert.equal(params.jawColorHex, rawGripper.visual.jaw_color_hex, "Jaw color hex must match JSON");

console.log("  [PASS] Canonical gripper profile binds to procedural parameters without discrepancies.");

// ============================================================================
// 2. STRICT GRIPPER PROFILE NEGATIVE VALIDATIONS
// ============================================================================
function expectProfileError(modifier, expectedSubstr) {
  const clone = JSON.parse(JSON.stringify(rawGripper));
  modifier(clone);
  assert.throws(
    () => parseGripperProfile(clone),
    (err) => err instanceof Error && err.message.includes(expectedSubstr),
    `Expected error containing '${expectedSubstr}'`
  );
}

expectProfileError((c) => { c.schema_version = 2; }, "schema_version");
expectProfileError((c) => { delete c.status; }, "status");
expectProfileError((c) => { c.status = "   "; }, "status");
expectProfileError((c) => { delete c.gripper_model; }, "gripper_model");
expectProfileError((c) => { c.palm.dimensions_m = [0.06, -0.04, 0.03]; }, "palm dimensions");
expectProfileError((c) => { c.jaw.dimensions_m = [0.008, 0.025]; }, "jaw.dimensions_m");
expectProfileError((c) => { c.stroke.open_width_m = -0.04; }, "stroke.open_width_m");
expectProfileError((c) => { c.stroke.closed_width_m = 0.05; }, "open_width_m (0.04) > closed_width_m (0.05)");
expectProfileError((c) => { c.stroke.travel_axis = "W"; }, "travel_axis");
expectProfileError((c) => { c.tcp_to_grasp_center_m = [0, 0, NaN]; }, "tcp_to_grasp_center_m");
expectProfileError((c) => { c.capture_volume.xy_radius_m = 0; }, "capture_volume.xy_radius_m");
expectProfileError((c) => { c.visual.color_hex = "red"; }, "visual.color_hex");
expectProfileError((c) => { c.visual.jaw_color_hex = "invalid-hex"; }, "visual.jaw_color_hex");

console.log("  [PASS] All 13 negative gripper profile test cases correctly rejected.");

// ============================================================================
// 3. STRICT WORLD_STATE TELEMETRY VALIDATION
// ============================================================================
const layoutJsonPath = path.resolve(repoRoot, "shared", "xiangqi_start_layout.json");
const rawLayout = JSON.parse(fs.readFileSync(layoutJsonPath, "utf-8"));
const canonicalPieces = rawLayout.pieces.map((p) => ({
  id: p.id,
  pose_world: [-0.36, 0.0, 0.05],
  orientation_quat_world: [0, 0, 0, 1],
  status: "RESTING",
  is_grasped: false,
}));

const validWorldState = {
  type: "world_state",
  timestamp: 1699999999.5,
  simulation_time: 12.34,
  pieces: canonicalPieces,
  gripper: {
    closed: false,
    is_closed: false,
    jaw_width_m: 0.040,
    attached_piece_id: null,
    tcp_position_m: [-0.36, 0.0, 0.15],
    grasp_position_m: [-0.36, 0.0, 0.185],
  },
};

// Canonical packet passes
const resOk = validateWorldStatePacket(validWorldState);
assert.equal(resOk.ok, true, `Canonical packet should pass: ${resOk.reason}`);
assert.equal(resOk.gripper.closed, false);
assert.equal(resOk.gripper.is_closed, false);

// Negative cases
function expectWorldStateRejected(modifier, expectedSubstr) {
  const clone = JSON.parse(JSON.stringify(validWorldState));
  modifier(clone);
  const res = validateWorldStatePacket(clone);
  assert.equal(res.ok, false, `Packet should be rejected for ${expectedSubstr}`);
  assert.ok(
    res.reason.toLowerCase().includes(expectedSubstr.toLowerCase()),
    `Expected reason to include '${expectedSubstr}', got '${res.reason}'`
  );
}

// 1. closed: "false" (string coercion rejection)
expectWorldStateRejected((p) => { p.gripper.closed = "false"; delete p.gripper.is_closed; }, "strict boolean");

// 2. closed: 1 (integer coercion rejection)
expectWorldStateRejected((p) => { p.gripper.closed = 1; delete p.gripper.is_closed; }, "strict boolean");

// 3. closed: true, is_closed: false (conflict rejection)
expectWorldStateRejected((p) => { p.gripper.closed = true; p.gripper.is_closed = false; }, "conflict");

// 4. NaN jaw width
expectWorldStateRejected((p) => { p.gripper.jaw_width_m = NaN; }, "finite number >= 0");

// 5. Piece pose contains Infinity
expectWorldStateRejected((p) => { p.pieces[0].pose_world = [0, Infinity, 0]; }, "invalid or non-finite");

// 6. Piece quaternion length != 4
expectWorldStateRejected((p) => { p.pieces[0].orientation_quat_world = [0, 0, 1]; }, "4 finite numbers");

// 7. Zero quaternion
expectWorldStateRejected((p) => { p.pieces[0].orientation_quat_world = [0, 0, 0, 0]; }, "zero-norm");

// 8. Missing piece id
expectWorldStateRejected((p) => { delete p.pieces[0].id; }, "missing non-empty id");

console.log("  [PASS] All 8 negative world_state telemetry test cases correctly rejected.");

// ============================================================================
// 4. ROBOT ARM BUILDER PROFILE SCOPING INVARIANT
// ============================================================================
assert.throws(
  () => computeProceduralGripperParameters(null),
  (err) => err instanceof Error && err.message.includes("Virtual gripper profile is required")
);
assert.throws(
  () => computeProceduralGripperParameters(undefined),
  (err) => err instanceof Error && err.message.includes("Virtual gripper profile is required")
);

console.log("  [PASS] Gripper builder enforces required non-null profile parameter.");

// ============================================================================
// 5. CANONICAL GRIPPER VISUAL ASSET VALIDATION
// ============================================================================
const visualAssetJsonPath = path.resolve(repoRoot, "shared", "gripper_visual_asset.json");
const rawVisualAsset = JSON.parse(fs.readFileSync(visualAssetJsonPath, "utf-8"));
const parsedVisualAsset = parseGripperVisualAsset(rawVisualAsset);

assert.equal(parsedVisualAsset.schemaVersion, 1);
assert.equal(parsedVisualAsset.status, "VISUAL_CALIBRATION_PROVISIONAL");
assert.equal(parsedVisualAsset.scaleToM, 0.0008);
assert.equal(parsedVisualAsset.assetFile, "Assieme_pinza_dita_parallele.stp");
assert.ok(parsedVisualAsset.profiles.fr3);
assert.ok(parsedVisualAsset.profiles.fr5);

function expectVisualAssetError(modifier, expectedSubstr) {
  const clone = JSON.parse(JSON.stringify(rawVisualAsset));
  modifier(clone);
  assert.throws(
    () => parseGripperVisualAsset(clone),
    (err) => err instanceof Error && err.message.includes(expectedSubstr),
    `Expected error containing '${expectedSubstr}'`
  );
}

expectVisualAssetError((c) => { c.schema_version = 2; }, "schema_version");
expectVisualAssetError((c) => { delete c.status; }, "status");
expectVisualAssetError((c) => { c.scale_to_m = -1; }, "scale_to_m");
expectVisualAssetError((c) => { c.cad_flange_origin = [1, 2]; }, "cad_flange_origin");
expectVisualAssetError((c) => { delete c.profiles.fr3; }, "profiles.fr3");

console.log("  [PASS] Canonical gripper visual asset parses and validates correctly.");
console.log("ALL VIEWER GRIPPER & TELEMETRY TESTS PASSED!\n");
