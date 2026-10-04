import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import * as THREE from "three";
import {
  applyBoardRootPlacement, boardPointToXYZ, getScenePlacement,
  setBoardGeometry, setScenePlacement, fetchScenePlacement,
} from "../../robot-3d-viewer/board.mjs";
import { parsePhysicalGeometry } from "../../robot-3d-viewer/geometry.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const geom = parsePhysicalGeometry(JSON.parse(fs.readFileSync(path.join(root, "shared", "physical_geometry.json"))));
setBoardGeometry(geom);

const center = [-0.3815, 0.0105, 0.02];
const T = [
  [0, 1, 0, -0.02],
  [-1, 0, 0, 0.3815],
  [0, 0, 1, 0.0105],
  [0, 0, 0, 1],
];

function checkParity(label) {
  const group = new THREE.Group();
  applyBoardRootPlacement(group, getScenePlacement());
  group.updateMatrixWorld(true);
  for (const [row, col] of [[0, 0], [0, 8], [9, 0], [9, 8], [2, 7]]) {
    // Board mesh local axes are (row, up, col).
    const local = new THREE.Vector3((row - 4.5) * geom.rowSpacingM, 0,
      (col - 4) * geom.cellM).applyMatrix4(group.matrixWorld);
    const cell = boardPointToXYZ(row, col, geom);
    assert.ok(local.distanceTo(cell) < 1e-6,
      `${label}: mesh/cell mismatch at (${row},${col}): ${local.distanceTo(cell)} m`);
  }
}

setScenePlacement({ board_center_world_m: center, board_yaw_deg: 180 });
checkParity("nominal yaw180");

// T must dominate stale teaching points and stale yaw for both mesh and cells.
setScenePlacement({
  board_center_world_m: center,
  board_yaw_deg: 0,
  T_robot_from_board: T,
  teaching_points: {
    R1: [-209, 210, 10.5], R2: [-206, 545, 10.5],
    R3: [155, 542, 10.5], R4: [160, 215, 10.5],
  },
});
checkParity("authoritative rigid transform");

// The actual nominal scene must already match Python's first Connect packet.
const sceneData = JSON.parse(fs.readFileSync(path.join(root, "shared/virtual_fr3_scene.json")));
globalThis.fetch = async () => ({ ok: true, json: async () => sceneData });
await fetchScenePlacement();
const beforeCells = Array.from({ length: 90 }, (_, i) => boardPointToXYZ(Math.floor(i / 9), i % 9, geom));
const beforeGroup = new THREE.Group();
applyBoardRootPlacement(beforeGroup, getScenePlacement());
const packet = JSON.parse(execFileSync("python", ["-c",
  "import json; from src.domain.board_pose import BoardPlacementState; print(json.dumps(BoardPlacementState.compute(0.0).to_dict()))"],
  { cwd: root, encoding: "utf8", env: { ...process.env, ROBOT_BACKEND: "VIRTUAL", DRY_RUN: "1" } }));
setScenePlacement(packet);
const afterGroup = new THREE.Group();
applyBoardRootPlacement(afterGroup, getScenePlacement());
assert.ok(beforeGroup.quaternion.angleTo(afterGroup.quaternion) < 1e-7, "Connect rotates nominal board");
assert.ok(beforeGroup.position.distanceTo(afterGroup.position) < 1e-7, "Connect translates nominal board");
for (let i = 0; i < 90; i++) {
  assert.ok(beforeCells[i].distanceTo(boardPointToXYZ(Math.floor(i / 9), i % 9, geom)) < 1e-7,
    `Connect changed cell ${i}`);
}
checkParity("nominal preview/live parity");
console.log("Viewer board mesh/cell parity for yaw and rigid T: PASS");
