// tests/unit/test_viewer_coordinate_contract.mjs
// Verifies:
// 1. BoardCell (row, col) normalization: boardPointToXYZ accepts both (row, col) and { row, col }.
// 2. Canonical 90° orientation math: +col -> -X_robot (+Z_world), +row -> -Y_robot (+X_world).
// 3. Asymmetric cell (2, 7) non-transpose check vs (7, 2).
// 4. Parity of all 90 cells with authoritative BoardPose transform.
// 5. Parity of all 32 start layout pieces.
// 6. Dynamic board placement forward shift (d) and height offset (zOff) translation invariance.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

// Mock minimal DOM document with proxy context for Node environment
if (typeof globalThis.document === "undefined") {
  const dummyCtx = new Proxy({}, {
    get: (target, prop) => {
      if (prop in target) return target[prop];
      return (...args) => {};
    },
    set: (target, prop, value) => {
      target[prop] = value;
      return true;
    },
  });
  globalThis.document = {
    createElement: () => ({
      getContext: () => dummyCtx,
      width: 128,
      height: 128,
    }),
  };
}

// Import viewer modules
const boardMjsPath = path.resolve(repoRoot, "robot-3d-viewer", "board.mjs");
const layoutMjsPath = path.resolve(repoRoot, "robot-3d-viewer", "layout.mjs");
const geometryMjsPath = path.resolve(repoRoot, "robot-3d-viewer", "geometry.mjs");

const {
  boardPointToXYZ,
  buildPieces,
  movePieceTo,
  setScenePlacement,
  setBoardGeometry,
} = await import(pathToFileURL(boardMjsPath).href);

const {
  parseStartLayout,
} = await import(pathToFileURL(layoutMjsPath).href);

const {
  parsePhysicalGeometry,
} = await import(pathToFileURL(geometryMjsPath).href);

console.log("Running Viewer Coordinate Contract Verification Tests (Node.js)...");

// Initialize geometry and placement from canonical sources
const geomJson = JSON.parse(fs.readFileSync(path.resolve(repoRoot, "shared", "physical_geometry.json"), "utf-8"));
const geometry = parsePhysicalGeometry(geomJson);
setBoardGeometry(geometry);

const sceneJson = JSON.parse(fs.readFileSync(path.resolve(repoRoot, "shared", "virtual_fr3_scene.json"), "utf-8"));
const defaultCenter = sceneJson.virtual_board_placement.board_center_in_3d_world_m;
setScenePlacement({
  boardCenterX: defaultCenter[0],
  boardSurfaceY: defaultCenter[1],
  boardCenterZ: defaultCenter[2],
  board_yaw_deg: sceneJson.virtual_board_placement.board_yaw_deg,
  forward_shift_mm: 0.0,
  safe_transit_height_mm: 70.0,
  board_height_offset_mm: 0.0,
  placement_version: 1,
});

// 1. Signature overloading and equivalence: (row, col) vs { row, col }
for (let r = 0; r < 10; r++) {
  for (let c = 0; c < 9; c++) {
    const p1 = boardPointToXYZ(r, c, geometry);
    const p2 = boardPointToXYZ({ row: r, col: c }, geometry);
    assert.equal(p1.x, p2.x, `X mismatch at (${r}, ${c})`);
    assert.equal(p1.y, p2.y, `Y mismatch at (${r}, ${c})`);
    assert.equal(p1.z, p2.z, `Z mismatch at (${r}, ${c})`);
  }
}
console.log("  [PASS] boardPointToXYZ(row, col) and boardPointToXYZ({ row, col }) produce identical coordinates for all 90 cells.");

// Test input validation
assert.throws(() => boardPointToXYZ(NaN, 0), /Invalid board coordinates/);
assert.throws(() => boardPointToXYZ(0, undefined), /Invalid board coordinates/);

// Asymmetric cells are derived from the current canonical scene, never an old placement.
function expectedWorld(row, col) {
  const center = sceneJson.virtual_board_placement.board_center_in_robot_base_m;
  const theta = sceneJson.virtual_board_placement.board_yaw_deg * Math.PI / 180;
  const u = (col - (geometry.columns - 1)/2) * geometry.cellM;
  const v = (row - (geometry.rows - 1)/2) * geometry.rowSpacingM;
  return { x: -(center[1] + Math.cos(theta)*u - Math.sin(theta)*v),
    y: center[2], z: -(center[0] - Math.sin(theta)*u - Math.cos(theta)*v) };
}
const p27 = boardPointToXYZ(2, 7, geometry);
const p72 = boardPointToXYZ(7, 2, geometry);
for (const [actual, expected] of [[p27, expectedWorld(2,7)], [p72, expectedWorld(7,2)]]) {
  for (const axis of ['x','y','z']) assert.ok(Math.abs(actual[axis]-expected[axis]) < 1e-6);
}
assert.notEqual(p27.x, p72.x, "p27.x and p72.x must not be equal");
assert.notEqual(p27.z, p72.z, "p27.z and p72.z must not be equal");
console.log("  [PASS] Asymmetric cell (2, 7) verifies non-transposed row/col mapping.");

// 3. Complete 90-cell parity with authoritative BoardPose transform
// Transformation from robot base to 3D world:
//   X_world = -Y_robot
//   Y_world = +Z_robot
//   Z_world = -X_robot
for (let r = 0; r < 10; r++) {
  for (let c = 0; c < 9; c++) {
    const ptWorld = boardPointToXYZ(r, c, geometry);

    const u = (c - (geometry.columns-1)/2) * geometry.cellM;
    const v = (r - (geometry.rows-1)/2) * geometry.rowSpacingM;
    const theta = sceneJson.virtual_board_placement.board_yaw_deg * Math.PI / 180;
    const center = sceneJson.virtual_board_placement.board_center_in_robot_base_m;
    const robX = center[0] - Math.sin(theta) * u - Math.cos(theta) * v;
    const robY = center[1] + Math.cos(theta) * u - Math.sin(theta) * v;
    const robZ = center[2];

    // Check transformation identity:
    const expectedX_world = -robY;
    const expectedY_world = robZ;
    const expectedZ_world = -robX;

    assert.ok(
      Math.abs(ptWorld.x - expectedX_world) < 1e-6,
      `Cell (${r}, ${c}) X_world mismatch: got ${ptWorld.x}, expected ${expectedX_world}`
    );
    assert.ok(
      Math.abs(ptWorld.y - expectedY_world) < 1e-6,
      `Cell (${r}, ${c}) Y_world mismatch: got ${ptWorld.y}, expected ${expectedY_world}`
    );
    assert.ok(
      Math.abs(ptWorld.z - expectedZ_world) < 1e-6,
      `Cell (${r}, ${c}) Z_world mismatch: got ${ptWorld.z}, expected ${expectedZ_world}`
    );
  }
}
console.log("  [PASS] All 90 cells satisfy exact BoardPose transformation parity.");

// 4. Parity across 32 pieces in start layout
const layoutJson = JSON.parse(fs.readFileSync(path.resolve(repoRoot, "shared", "xiangqi_start_layout.json"), "utf-8"));
const piecesList = parseStartLayout(layoutJson);
assert.equal(piecesList.length, 32, "Must load exactly 32 pieces");

const { pieces } = buildPieces(geometry, piecesList);
assert.equal(Object.keys(pieces).length >= 32, true);

for (const p of piecesList) {
  const mesh = pieces[p.id];
  assert.ok(mesh, `Mesh for piece ${p.id} must exist`);
  assert.equal(mesh.userData.row, p.row, `userData.row mismatch for ${p.id}`);
  assert.equal(mesh.userData.col, p.col, `userData.col mismatch for ${p.id}`);

  const expectedPos = boardPointToXYZ(p.row, p.col, geometry);
  const expectedY = expectedPos.y + geometry.pieceHeightM / 2.0;

  assert.ok(
    Math.abs(mesh.position.x - expectedPos.x) < 1e-5,
    `Piece ${p.id} mesh X mismatch: got ${mesh.position.x}, expected ${expectedPos.x}`
  );
  assert.ok(
    Math.abs(mesh.position.y - expectedY) < 1e-5,
    `Piece ${p.id} mesh Y mismatch: got ${mesh.position.y}, expected ${expectedY}`
  );
  assert.ok(
    Math.abs(mesh.position.z - expectedPos.z) < 1e-5,
    `Piece ${p.id} mesh Z mismatch: got ${mesh.position.z}, expected ${expectedPos.z}`
  );
}
console.log("  [PASS] All 32 pieces instantiated at exact authoritative 3D cell positions.");

// 5. movePieceTo updates position and userData consistently
const testMesh = pieces[piecesList[0].id];
movePieceTo(testMesh, 2, 7, geometry);
assert.equal(testMesh.userData.row, 2);
assert.equal(testMesh.userData.col, 7);
assert.ok(Math.abs(testMesh.position.x - p27.x) < 1e-6);
assert.ok(Math.abs(testMesh.position.z - p27.z) < 1e-6);

// Test with object argument
movePieceTo(testMesh, { row: 7, col: 2 }, geometry);
assert.equal(testMesh.userData.row, 7);
assert.equal(testMesh.userData.col, 2);
assert.ok(Math.abs(testMesh.position.x - p72.x) < 1e-6);
assert.ok(Math.abs(testMesh.position.z - p72.z) < 1e-6);
console.log("  [PASS] movePieceTo supports both (row, col) and { row, col } contracts.");

// 6. Dynamic board placement shift translation invariance
// Apply forward shift d = +15 mm and vertical offset zOff = +30 mm
setScenePlacement({
  boardCenterX: defaultCenter[0],
  boardSurfaceY: defaultCenter[1] + 0.030,
  boardCenterZ: defaultCenter[2] + 0.015,
  board_yaw_deg: sceneJson.virtual_board_placement.board_yaw_deg,
  forward_shift_mm: 15.0,
  safe_transit_height_mm: 50.0,
  board_height_offset_mm: 30.0,
  placement_version: 2,
});

const shiftedP27 = boardPointToXYZ(2, 7, geometry);
assert.ok(Math.abs(shiftedP27.x - p27.x) < 1e-6, "Shift along Z must not alter X");
assert.ok(Math.abs(shiftedP27.y - (defaultCenter[1] + 0.030)) < 1e-6, "Shift Y must reflect +30mm offset");
assert.ok(Math.abs(shiftedP27.z - (p27.z + 0.015)) < 1e-6, "Shift Z must reflect +15mm forward shift");

console.log("  [PASS] Dynamic board placement shift is translation-invariant across axes.");

// 7. Direct authoritative T_robot_from_board matrix consumption
const customT = [
  [-1.0,  0.0, 0.0, -0.375],
  [ 0.0, -1.0, 0.0,  0.0  ],
  [ 0.0,  0.0, 1.0,  0.0105],
  [ 0.0,  0.0, 0.0,  1.0  ],
];
setScenePlacement({
  boardCenterX: 0.0,
  boardSurfaceY: 0.0105,
  boardCenterZ: 0.375,
  forward_shift_mm: 15.0,
  safe_transit_height_mm: 50.0,
  board_height_offset_mm: 0.0,
  placement_version: 3,
  T_robot_from_board: customT,
});

const tP27 = boardPointToXYZ(2, 7, geometry);
// u = +0.120, v = -0.100
// robX = -1.0*(0.120) - 0.375 = -0.495
// robY = -1.0*(-0.100) = +0.100
// robZ = 0.0105
// World: X = -robY = -0.100, Y = 0.0105, Z = -robX = 0.495
assert.ok(Math.abs(tP27.x - (-0.100)) < 1e-6);
assert.ok(Math.abs(tP27.y - 0.0105) < 1e-6);
assert.ok(Math.abs(tP27.z - 0.495) < 1e-6);
console.log("  [PASS] Direct T_robot_from_board 4x4 matrix correctly transforms board points.");

// 8. Arbitrary board yaw perturbation (89.0 deg)
setScenePlacement({
  boardCenterX: 0.0,
  boardSurfaceY: 0.0105,
  boardCenterZ: 0.360,
  board_yaw_deg: 89.0,
  forward_shift_mm: 0.0,
  safe_transit_height_mm: 70.0,
  board_height_offset_mm: 0.0,
  placement_version: 4,
});
const yaw89P44 = boardPointToXYZ(4.5, 4.0, geometry); // Board center
assert.ok(Math.abs(yaw89P44.x - 0.0) < 1e-6);
assert.ok(Math.abs(yaw89P44.z - 0.360) < 1e-6);
console.log("  [PASS] Perturbed yaw respects SE(3) transformation mathematics.");

console.log("ALL VIEWER COORDINATE CONTRACT TESTS PASSED SUCCESSFULLY!");
