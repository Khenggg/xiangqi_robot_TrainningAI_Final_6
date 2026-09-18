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
assert.deepEqual(boardCenterWorld, [0.0, 0.0105, 0.36]);

const gridOriginRobot = sceneData?.virtual_board_placement?.grid_origin_in_robot_base_m;
assert.ok(
  Array.isArray(gridOriginRobot) && gridOriginRobot.length === 3 && gridOriginRobot.every(Number.isFinite),
  "grid_origin_in_robot_base_m must be array of 3 finite numbers"
);
assert.deepEqual(gridOriginRobot, [-0.2, 0.18, 0.0105]);

const gridOriginWorld = sceneData?.virtual_board_placement?.grid_origin_in_3d_world_m;
assert.ok(
  Array.isArray(gridOriginWorld) && gridOriginWorld.length === 3 && gridOriginWorld.every(Number.isFinite),
  "grid_origin_in_3d_world_m must be array of 3 finite numbers"
);
assert.deepEqual(gridOriginWorld, [-0.18, 0.0105, 0.2]);

// Verify mathematical transformation identity: R * p_robot_origin + t == p_world_origin
const trans = sceneData?.robot_base_to_3d_world?.translation_m || [0.0, 0.0, 0.0];
function transformPoint(p) {
  return [
    rot[0][0] * p[0] + rot[0][1] * p[1] + rot[0][2] * p[2] + trans[0],
    rot[1][0] * p[0] + rot[1][1] * p[1] + rot[1][2] * p[2] + trans[1],
    rot[2][0] * p[0] + rot[2][1] * p[1] + rot[2][2] * p[2] + trans[2],
  ];
}

const computedWorldOrigin = transformPoint(gridOriginRobot);
for (let i = 0; i < 3; i++) {
  assert.ok(
    Math.abs(computedWorldOrigin[i] - gridOriginWorld[i]) < 1e-6,
    `R * grid_origin_in_robot_base_m must equal grid_origin_in_3d_world_m at idx ${i}: computed=${computedWorldOrigin[i]}, expected=${gridOriginWorld[i]}`
  );
}

// 3. Test 4-Corner Robot-to-Viewer Parity (No Column Mirroring)
// Physical geometry: 40mm spacing, 9 cols x 10 rows
const physPath = path.resolve(repoRoot, "shared", "physical_geometry.json");
const physData = JSON.parse(fs.readFileSync(physPath, "utf-8"));
const colSpacingM = physData.board.column_spacing / 1000.0; // 0.04m
const rowSpacingM = physData.board.row_spacing / 1000.0;   // 0.04m
const playableWidthM = (physData.board.columns - 1) * colSpacingM; // 0.32m
const playableDepthM = (physData.board.rows - 1) * rowSpacingM;   // 0.36m

// Viewer formula from board.mjs under 90 deg orientation:
// Column axis (span -160mm to +160mm) -> +Z_world (-X_robot)
// Row axis (span -180mm to +180mm)    -> +X_world (-Y_robot)
function viewerPointToXYZ(col, row) {
  const u = (col - 4.0) * colSpacingM;
  const v = (row - 4.5) * rowSpacingM;
  return [
    boardCenterWorld[0] + v,
    boardCenterWorld[1],
    boardCenterWorld[2] + u,
  ];
}

// Robot base formula under 90 deg orientation:
// col 0..8 along -X: u = (col - 4.0) * 0.04 -> x = boardCenterRobot[0] - u
// row 0..9 along -Y: v = (row - 4.5) * 0.04 -> y = -v
function robotBasePointToXYZ(col, row) {
  const u = (col - 4.0) * colSpacingM;
  const v = (row - 4.5) * rowSpacingM;
  return [
    -0.360 - u,
    -v,
    gridOriginRobot[2],
  ];
}

const fourCorners = [
  { name: "Top-Left (Col 0, Row 0 - Black Left Rook)", col: 0, row: 0 },
  { name: "Top-Right (Col 8, Row 0 - Black Right Rook)", col: 8, row: 0 },
  { name: "Bottom-Left (Col 0, Row 9 - Red Left Rook)", col: 0, row: 9 },
  { name: "Bottom-Right (Col 8, Row 9 - Red Right Rook)", col: 8, row: 9 },
];

for (const corner of fourCorners) {
  const pRobot = robotBasePointToXYZ(corner.col, corner.row);
  const pWorldFromRobot = transformPoint(pRobot);
  const pViewer = viewerPointToXYZ(corner.col, corner.row);

  for (let ax = 0; ax < 3; ax++) {
    const diff = Math.abs(pWorldFromRobot[ax] - pViewer[ax]);
    assert.ok(
      diff < 1e-6,
      `Corner ${corner.name} axis ${ax} mismatch: robot_transformed=${pWorldFromRobot[ax]}, viewer=${pViewer[ax]}, diff=${diff}`
    );
  }
}

// Check all 90 intersections (9 cols x 10 rows)
for (let r = 0; r < 10; r++) {
  for (let c = 0; c < 9; c++) {
    const pRobot = robotBasePointToXYZ(c, r);
    const pWorldFromRobot = transformPoint(pRobot);
    const pViewer = viewerPointToXYZ(c, r);
    for (let ax = 0; ax < 3; ax++) {
      const diff = Math.abs(pWorldFromRobot[ax] - pViewer[ax]);
      assert.ok(
        diff < 1e-6,
        `Cell (col=${c}, row=${r}) axis ${ax} mismatch: diff=${diff}`
      );
    }
  }
}

console.log("  [PASS] 4 corners and all 90 cells match R * p_robot + t == p_viewer (error < 1e-6 m).");
console.log("  [PASS] virtual_fr3_scene.json successfully binds to viewer scene transform.");
console.log("ALL VIEWER INTEGRATION CHECKS PASSED SUCCESSFULLY!");
