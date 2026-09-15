import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

console.log("Running Viewer Profile & Scene Binding Integration Tests (Node.js)...");

// 1. Test shared/robot_profiles/fr3.json loading and schema parity with main.mjs
const fr3Path = path.resolve(repoRoot, "shared", "robot_profiles", "fr3.json");
assert.ok(fs.existsSync(fr3Path), `fr3.json must exist at ${fr3Path}`);

const fr3Data = JSON.parse(fs.readFileSync(fr3Path, "utf-8"));
assert.equal(fr3Data.robot_model, "FR3");
assert.ok(Array.isArray(fr3Data.joints), "joints must be an array");
assert.equal(fr3Data.joints.length, 6, "FR3 must define exactly 6 joints");

// Replicate main.mjs fetchRobotProfileConfig parsing logic
const visualJointOrigins = fr3Data.joints.map((j, idx) => {
  const xyz = j.origin_xyz_m;
  assert.ok(
    Array.isArray(xyz) && xyz.length === 3 && xyz.every(Number.isFinite),
    `Joint ${idx} (${j.name}) must have valid origin_xyz_m: ${JSON.stringify(xyz)}`
  );
  return [Number(xyz[0]), Number(xyz[1]), Number(xyz[2])];
});

const visualJointRpy = fr3Data.joints.map((j, idx) => {
  const rpy = j.origin_rpy_rad;
  assert.ok(
    Array.isArray(rpy) && rpy.length === 3 && rpy.every(Number.isFinite),
    `Joint ${idx} (${j.name}) must have valid origin_rpy_rad: ${JSON.stringify(rpy)}`
  );
  return [Number(rpy[0]), Number(rpy[1]), Number(rpy[2])];
});

assert.equal(visualJointOrigins.length, 6);
assert.equal(visualJointRpy.length, 6);

// Verify J1 origin is [0, 0, 0]
assert.deepEqual(visualJointOrigins[0], [0, 0, 0]);
// Verify J2 origin is [0, 0, 0.14]
assert.deepEqual(visualJointOrigins[1], [0, 0, 0.14]);
// Verify J3 origin is [-0.28, 0, 0]
assert.deepEqual(visualJointOrigins[2], [-0.28, 0, 0]);
// Verify J4 origin is [-0.24001, 0, 0]
assert.deepEqual(visualJointOrigins[3], [-0.24001, 0, 0]);
// Verify J5 & J6 RPY
assert.deepEqual(visualJointRpy[4], [1.5708, 0, 0]);
assert.deepEqual(visualJointRpy[5], [-1.5708, 0, 0]);

console.log("  [PASS] fr3.json successfully binds to main.mjs schema (no undefined/NaN).");

// 2. Test shared/virtual_fr3_scene.json loading and schema parity
const scenePath = path.resolve(repoRoot, "shared", "virtual_fr3_scene.json");
assert.ok(fs.existsSync(scenePath), `virtual_fr3_scene.json must exist at ${scenePath}`);

const sceneData = JSON.parse(fs.readFileSync(scenePath, "utf-8"));
const rot = sceneData?.robot_base_to_3d_world?.rotation_matrix;
assert.ok(Array.isArray(rot) && rot.length === 3, "rotation_matrix must be 3x3");
for (const row of rot) {
  assert.ok(Array.isArray(row) && row.length === 3 && row.every(Number.isFinite));
}

// Compute 3x3 determinant
const det =
  rot[0][0] * (rot[1][1] * rot[2][2] - rot[1][2] * rot[2][1]) -
  rot[0][1] * (rot[1][0] * rot[2][2] - rot[1][2] * rot[2][0]) +
  rot[0][2] * (rot[1][0] * rot[2][1] - rot[1][1] * rot[2][0]);
assert.ok(Math.abs(det - 1.0) < 1e-6, `Rotation matrix determinant must be 1.0, got ${det}`);

const boardCenterWorld = sceneData?.virtual_board_placement?.board_center_in_3d_world_m;
assert.ok(
  Array.isArray(boardCenterWorld) && boardCenterWorld.length === 3 && boardCenterWorld.every(Number.isFinite),
  "board_center_in_3d_world_m must be array of 3 finite numbers"
);
assert.deepEqual(boardCenterWorld, [0.0, 0.05, 0.36]);

console.log("  [PASS] virtual_fr3_scene.json successfully binds to viewer scene transform.");
console.log("ALL VIEWER INTEGRATION CHECKS PASSED SUCCESSFULLY!");
