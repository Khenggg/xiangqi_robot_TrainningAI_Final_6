import assert from "node:assert/strict";
import { inspectBoardPlacementPacket, canSendLiveCommand } from "../../robot-3d-viewer/placement_integrity.mjs";

const cell = 0.04;
const center = [-0.02, 0.3815, 0.0105];
const T = [
  [0, 1, 0, center[0]],
  [-1, 0, 0, center[1]],
  [0, 0, 1, center[2]],
  [0, 0, 0, 1],
];
const corners = {
  R1: [-200, 541.5, 10.5],
  R2: [-200, 221.5, 10.5],
  R3: [160, 221.5, 10.5],
  R4: [160, 541.5, 10.5],
};
assert.deepEqual(inspectBoardPlacementPacket({
  T_robot_from_board: T,
  grid_origin_robot_m: corners.R1.map((v) => v / 1000),
  teaching_points: corners,
}, cell), { ok: true });

// This was observed on the live FR3 telemetry: the matrix maps local R1 to
// another point while the backend advertises R1 as the grid origin.
const conflictingLivePacket = {
  T_robot_from_board: [
    [0.99999, -0.00306, -0.00049, -0.025],
    [0.00306, 0.99999, -0.00054, 0.37794],
    [0.00049, 0.00053, 1, 0.01059],
    [0, 0, 0, 1],
  ],
  grid_origin_robot_m: [-0.209, 0.21015, 0.01049],
  teaching_points: {
    R1: [-209, 210.149, 10.494],
    R2: [-206, 544.595, 10.5],
    R3: [155, 542, 10.849],
    R4: [160, 215, 10.501],
  },
};
const rejected = inspectBoardPlacementPacket(conflictingLivePacket, cell);
assert.equal(rejected.ok, false);
assert.match(rejected.reason, /gốc lưới lệch/);

for (const change of [
  (matrix) => { matrix[0][1] = 2; },
  (matrix) => { matrix[0][1] = -1; },
  (matrix) => { matrix[3][0] = 0.5; },
]) {
  const malformed = structuredClone(T);
  change(malformed);
  assert.equal(inspectBoardPlacementPacket({ T_robot_from_board: malformed,
    grid_origin_robot_m: corners.R1.map((v) => v / 1000) }, cell).ok, false);
}

for (const command of ["MOVE_JOINT", "SET_GRIPPER", "RESET", "EXECUTE_3STAGE", "SET_BOARD_PLACEMENT"]) {
  assert.equal(canSendLiveCommand("PHYSICAL", false, command), false, command);
  assert.equal(canSendLiveCommand("PHYSICAL", null, command), false, command);
}
assert.equal(canSendLiveCommand("PHYSICAL", false, "GET_BOARD_TEACHING_POINTS"), true);
assert.equal(canSendLiveCommand("VIRTUAL", true, "EXECUTE_3STAGE"), true);

console.log("Viewer placement matrix/grid-origin and taught-corner integrity: PASS");
