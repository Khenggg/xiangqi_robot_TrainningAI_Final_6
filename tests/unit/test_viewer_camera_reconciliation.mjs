import assert from 'node:assert/strict';
import * as THREE from 'three';
import { applyBoardRootPlacement, updatePiecesFromWorldState } from '../../robot-3d-viewer/board.mjs';

const root = new THREE.Group();
const tilt = new THREE.Matrix4().makeRotationX(0.04);
const rotation = new THREE.Matrix4().makeRotationZ(0.6).multiply(tilt);
const e = rotation.elements;
const T = [[e[0], e[4], e[8], -0.4], [e[1], e[5], e[9], 0.2], [e[2], e[6], e[10], 0.1], [0, 0, 0, 1]];
applyBoardRootPlacement(root, { boardCenterX: -0.2, boardSurfaceY: 0.1, boardCenterZ: 0.4, TRobotFromBoard: T });
const u = 0.08, v = -0.12;
const rendered = new THREE.Vector3(v, 0, u).applyQuaternion(root.quaternion).add(root.position);
const robot = new THREE.Vector3(u, v, 0).applyMatrix4(rotation).add(new THREE.Vector3(-0.4, 0.2, 0.1));
assert.ok(rendered.distanceTo(new THREE.Vector3(-robot.y, robot.z, -robot.x)) < 1e-10);

const moving = new THREE.Object3D(); moving.userData.id = 'red_cannon_0';
const captured = new THREE.Object3D(); captured.userData.id = 'black_knight_0';
const pieces = { red_cannon_0: moving, black_knight_0: captured };
updatePiecesFromWorldState(null, pieces, [{ id: 'red_cannon_0', pose_world: [1, 2, 3],
  orientation_quat_world: [0, 0, 0, 1], status: 'RESTING', nearest_row: 0,
  nearest_col: 1, distance_to_nearest_intersection_m: 0, is_grasped: false }]);
assert.deepEqual(moving.position.toArray(), [1, 2, 3]);
assert.equal(captured.visible, false);
assert.equal(captured.userData.row, null);
updatePiecesFromWorldState(null, pieces, [{ id: 'black_knight_0', pose_world: [4, 5, 6],
  status: 'RESTING', nearest_row: 0, nearest_col: 1, distance_to_nearest_intersection_m: 0 }]);
assert.equal(captured.visible, true);
assert.equal(moving.visible, false);
console.log('PASS: calibrated board tilt, captured-piece removal, and full snapshot restoration');
