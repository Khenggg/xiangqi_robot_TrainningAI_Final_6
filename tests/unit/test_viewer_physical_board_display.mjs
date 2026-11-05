import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as THREE from 'three';
import { setScenePlacement, getScenePlacement, setBoardGeometry, boardPointToXYZ, applyBoardRootPlacement } from '../../robot-3d-viewer/board.mjs';
import { parsePhysicalGeometry } from '../../robot-3d-viewer/geometry.mjs';
import { inspectBoardPlacementPacket } from '../../robot-3d-viewer/placement_integrity.mjs';
import { displayCellWorld } from '../../robot-3d-viewer/physical_board_display.mjs';

const geometry = parsePhysicalGeometry(JSON.parse(fs.readFileSync('shared/physical_geometry.json')));
setBoardGeometry(geometry);
const profile = JSON.parse(fs.readFileSync('calibration/physical_teaching_points_user0.json'));
const pts = Object.fromEntries(['R1','R2','R3','R4'].map(n=>[n,profile.points[n].pose.slice(0,3)]));
const center = displayCellWorld(pts,.0105,4.5,4);
const packet = {calibration_space:'TAUGHT_XY_DISPLAY_ONLY', motion_authority:false,
  coordinate_frame:'robot_base',position_unit:'mm',display_teaching_points_mm:pts,
  board_surface_z_m:.0105,board_center_world_m:center,T_robot_from_board:null};
assert.deepEqual(inspectBoardPlacementPacket(packet),{ok:true});
for (const mutate of [p=>p.motion_authority=true,p=>p.coordinate_frame='user1',
    p=>p.display_teaching_points_mm.R2=p.display_teaching_points_mm.R1,
    p=>p.board_surface_z_m=NaN]) {
  const bad=structuredClone(packet);mutate(bad);assert.equal(inspectBoardPlacementPacket(bad).ok,false);
}
setScenePlacement(packet);
const root = new THREE.Group();
const mesh = new THREE.Mesh(new THREE.BoxGeometry(9*geometry.rowSpacingM,.01,8*geometry.cellM,9,1,8));
root.add(mesh);
const original = mesh.geometry.attributes.position.array.slice();
const originalNormals = mesh.geometry.attributes.normal.array.slice();
applyBoardRootPlacement(root,getScenePlacement());root.updateMatrixWorld(true);
for (const [i,row,col] of [[0,0,0],[1,0,8],[2,9,8],[3,9,0]]) {
  const p=boardPointToXYZ(row,col);
  assert.ok(p.distanceTo(new THREE.Vector3(-pts[['R1','R2','R3','R4'][i]][1]/1000,.0105,-pts[['R1','R2','R3','R4'][i]][0]/1000))<1e-10);
}
let checked=0;
for(let i=0;i<original.length;i+=3) {
  if (originalNormals[i+1]<.99) continue;
  const row=Math.round(original[i]/geometry.rowSpacingM+4.5);
  const col=Math.round(original[i+2]/geometry.cellM+4);
  const actual=new THREE.Vector3().fromBufferAttribute(mesh.geometry.attributes.position,i/3).applyMatrix4(root.matrixWorld);
  const expected=boardPointToXYZ(row,col);expected.y+=.005;
  assert.ok(actual.distanceTo(expected)<1e-7,`mesh/cell mismatch ${row},${col}`);
  assert.ok(mesh.geometry.attributes.normal.getY(i/3)>.99,'top normals must face up');
  checked++;
}
assert.ok(checked>=90);
// Repeated packets cannot accumulate warp; returning to virtual restores geometry.
const first=mesh.geometry.attributes.position.array.slice();
applyBoardRootPlacement(root,getScenePlacement());
assert.deepEqual(mesh.geometry.attributes.position.array,first);
setScenePlacement({board_center_world_m:center,board_yaw_deg:180});
applyBoardRootPlacement(root,getScenePlacement());
assert.deepEqual(mesh.geometry.attributes.position.array,original);
console.log('Physical taught four-corner display: all 90 cells/mesh/restore PASS');
