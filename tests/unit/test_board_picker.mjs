import assert from "node:assert/strict";
import { nearestBoardIntersection, settledPieceCell } from "../../robot-3d-viewer/board_picker.mjs";

const geometry = { rows: 10, columns: 9 };
const rotatedBoardPoint = (row, col) => ({
  x: 0.37 + (col - 4) * 0.04,
  z: -0.25 - (row - 4.5) * 0.04,
});

assert.deepEqual(
  nearestBoardIntersection(
    { x: rotatedBoardPoint(4, 4).x + 0.004, z: rotatedBoardPoint(4, 4).z - 0.003 },
    geometry, rotatedBoardPoint,
  ),
  { row: 4, col: 4 },
);
assert.deepEqual(
  nearestBoardIntersection(rotatedBoardPoint(0, 8), geometry, rotatedBoardPoint),
  { row: 0, col: 8 },
);
assert.equal(
  nearestBoardIntersection({ x: 2, z: 2 }, geometry, rotatedBoardPoint),
  null,
);

assert.deepEqual(settledPieceCell({
  status: "RESTING", nearest_row: 4, nearest_col: 4,
  distance_to_nearest_intersection_m: 0.0001,
}), { row: 4, col: 4 });
assert.equal(settledPieceCell({
  status: "ATTACHED_TO_GRIPPER", nearest_row: 0, nearest_col: 0,
  distance_to_nearest_intersection_m: 0.0,
}), null);
assert.equal(settledPieceCell({
  status: "RESTING", nearest_row: 0, nearest_col: 0,
  distance_to_nearest_intersection_m: 0.03,
}), null);
