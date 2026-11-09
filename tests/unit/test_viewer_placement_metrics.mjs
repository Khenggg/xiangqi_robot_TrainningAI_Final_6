import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as THREE from 'three';
import { parsePhysicalGeometry } from '../../robot-3d-viewer/geometry.mjs';
import { setBoardGeometry, setScenePlacement, getScenePlacement, boardPointToXYZ,
  buildBoardGrid } from '../../robot-3d-viewer/board.mjs';
import { computePlacementMetrics, placementAxisLabel, formatMetric,
  placementCellWorld } from '../../robot-3d-viewer/placement_metrics.mjs';
import { buildCoordinateRulerGroup } from '../../robot-3d-viewer/ruler.mjs';

// No renderer, sockets, camera, robot runtime, or live telemetry is created.
const context = new Proxy({}, {
  get: (target, key) => target[key] ?? (key === 'measureText' ? text => ({width: text.length * 7}) : () => {}),
  set: (target, key, value) => (target[key] = value, true),
});
globalThis.document = { createElement: () => ({getContext: () => context, width: 128, height: 128}) };
const scene = JSON.parse(fs.readFileSync('shared/virtual_fr3_scene.json', 'utf8'));
const geo = parsePhysicalGeometry(JSON.parse(fs.readFileSync('shared/physical_geometry.json', 'utf8')));
const nominal = scene.virtual_board_placement;
const tool = scene.tool_transform.flange_to_tcp_distance_m;
setBoardGeometry(geo);
const close = (a, b, message, tolerance = 1e-7) => assert.ok(Math.abs(a-b) < tolerance, `${message}: ${a} != ${b}`);

function packet(yaw, d, heightOffset = 0, H = 70) {
  const theta = yaw * Math.PI / 180;
  const R = [[-Math.sin(theta), -Math.cos(theta), 0], [Math.cos(theta), -Math.sin(theta), 0], [0, 0, 1]];
  const center = nominal.board_center_in_robot_base_m.map((value, i) => value + R[i][0] * d / 1000);
  center[2] += heightOffset / 1000;
  return {T_robot_from_board: R.map((row, i) => [...row, center[i]]).concat([[0,0,0,1]]),
    board_yaw_deg: yaw, forward_shift_mm: d, board_height_offset_mm: heightOffset,
    safe_transit_height_mm: H, board_surface_z_m: center[2]};
}

function point(T, row, col) {
  const u = (col - (geo.columns-1)/2) * geo.cellM;
  const v = (row - (geo.rows-1)/2) * geo.rowSpacingM;
  return T.slice(0,3).map(axis => axis[0]*u + axis[1]*v + axis[3]);
}

function expected(T, H) {
  const cells = Array.from({length: geo.rows}, (_, row) =>
    Array.from({length: geo.columns}, (_, col) => point(T,row,col))).flat();
  const x = cells.map(p => Math.abs(p[0])*1000);
  return {cells, near: Math.min(...x), far: Math.max(...x),
    approach: Math.max(...cells.map(p => Math.hypot(p[0],p[1],p[2]+H/1000+tool)*1000)),
    grasp: Math.max(...cells.map(p => Math.hypot(p[0],p[1],p[2]+geo.pieceHeightM/2+tool)*1000))};
}

// The regression uses the checked-in yaw180/translated scene, rather than an
// assumed symmetric yaw90 board centred at robot[-360,0]mm.
const current = {...nominal, forward_shift_mm: 0, safe_transit_height_mm: 70};
const currentMetrics = computePlacementMetrics(current, geo, tool);
assert.equal(currentMetrics.known, true);
close(currentMetrics.board_center_distance_mm, 23.8, 'actual centre |X_robot|');
close(currentMetrics.near_grid_depth_mm, 3.8, 'actual minimum grid |X_robot|');
close(currentMetrics.far_grid_depth_mm, 203.8, 'actual maximum grid |X_robot|');
close(currentMetrics.D_far_app, 625.9431923106122, 'measured-tool approach distance');
assert.equal(placementAxisLabel(current), 'col=-Y_robot, row=+X_robot');

let checkedCells = 0;
const ruler = buildCoordinateRulerGroup({geometry: geo, placement: current});
for (const yaw of [0, 90, 180, 37]) for (const d of [-10, 0, 15]) {
  const applied = packet(yaw, d, 7, 50);
  const original = JSON.stringify(applied);
  setScenePlacement(applied);
  const board = buildBoardGrid(geo);
  board.updateMatrixWorld(true);
  const truth = expected(applied.T_robot_from_board, 50);
  const metrics = computePlacementMetrics(getScenePlacement(), geo, tool);
  close(metrics.near_grid_depth_mm, truth.near, `yaw${yaw} shift${d} near`);
  close(metrics.far_grid_depth_mm, truth.far, `yaw${yaw} shift${d} far`);
  close(metrics.D_far_app, truth.approach, `yaw${yaw} shift${d} approach`);
  close(metrics.D_far_grasp, truth.grasp, `yaw${yaw} shift${d} grasp`);
  assert.equal(JSON.stringify(applied), original, 'metrics must not mutate a placement');
  for (let row=0;row<geo.rows;row++) for(let col=0;col<geo.columns;col++) {
    const p = point(applied.T_robot_from_board,row,col);
    const world = new THREE.Vector3(-p[1],p[2],-p[0]);
    const rendered = board.localToWorld(new THREE.Vector3((row-4.5)*geo.rowSpacingM,0,(col-4)*geo.cellM));
    assert.ok(rendered.distanceTo(world) < 1e-9, `mesh transform ${yaw}:${row},${col}`);
    assert.ok(boardPointToXYZ(row,col,geo).distanceTo(world) < 1e-9, `cell transform ${yaw}:${row},${col}`);
    checkedCells++;
  }
  assert.ok(boardPointToXYZ(2,7,geo).distanceTo(boardPointToXYZ(7,2,geo)) > 0.1, 'asymmetric indices must not transpose');
  // Previewing +5mm must remove the already-applied d, then follow the actual
  // column axis, including +Y at yaw0 and -Y at yaw180.
  const preview = computePlacementMetrics(getScenePlacement(),geo,tool,{forwardShiftMm:d+5});
  close(preview.D_far_app, expected(packet(yaw,d+5,7,50).T_robot_from_board,50).approach, 'shift preview');
  const atMax = computePlacementMetrics(getScenePlacement(),geo,tool,{forwardShiftMm:metrics.d_max});
  close(atMax.D_far_app,650,'column-axis d_max boundary',1e-6);
  assert.ok(computePlacementMetrics(getScenePlacement(),geo,tool,{forwardShiftMm:metrics.d_max+.01}).D_far_app>650);
  if (metrics.H_max === null) assert.ok(metrics.D_far_grasp > 650, 'no transit height repairs an unreachable grasp');
  else close(computePlacementMetrics(getScenePlacement(),geo,tool,{safeTransitHeightMm:metrics.H_max}).D_far_app,650,'H_max boundary',1e-6);
  ruler.updateBoardPlacement(applied);
  const labels = ruler.getObjectByName('labels-board');
  assert.equal(labels.children.length,5);
  for (const marker of labels.children) {
    const p = boardPointToXYZ(marker.userData.row,marker.userData.col,geo);
    close(marker.position.x,p.x,'ruler marker x');close(marker.position.z,p.z,'ruler marker z');
    assert.ok(marker.userData.text.includes((p.x*1000).toFixed(1)));
  }
  close(ruler.getObjectByName('board-height-transit').position.y,applied.board_surface_z_m+.05,'ruler transit height');
}

// Unknown geometry cannot silently become a green geometric pass.
for (const [placement, geometry, length] of [[null,geo,tool],[current,null,tool],[current,geo,null],
  [current,{...geo,rows:0},tool]]) {
  const result = computePlacementMetrics(placement,geometry,length);
  assert.equal(result.known,false);assert.equal(result.pass,false);assert.equal(result.D_far_app,null);
}
const reflected=structuredClone(current);reflected.T_robot_from_board[2][2]=-1;
assert.equal(computePlacementMetrics(reflected,geo,tool).known,false);
assert.equal(formatMetric(null),'—');assert.equal(formatMetric(NaN),'—');

// Physical four-corner XY display stays an explicit nonrigid display path, with
// no reach/safety claims; its markers use the actual displayed points.
const taught={calibration_space:'TAUGHT_XY_DISPLAY_ONLY',motion_authority:false,
  display_teaching_points_mm:{R1:[-220,200,0],R2:[-210,540,0],R3:[170,530,0],R4:[160,210,0]},
  board_surface_z_m:.02};
assert.equal(computePlacementMetrics(taught,geo,tool).known,false);
ruler.updateBoardPlacement(taught);
const marker=ruler.getObjectByName('board-marker-col0');
const taughtWorld=placementCellWorld(taught,geo,4.5,0);
close(marker.position.x,taughtWorld[0],'taught marker x');close(marker.position.z,taughtWorld[2],'taught marker z');
assert.equal(ruler.getObjectByName('board-height-transit'),undefined,'unknown transit height has no marker');

// Exercise the actual main-module wrapper without creating WebGL or a live app.
const main=fs.readFileSync('robot-3d-viewer/main.mjs','utf8');
const wrapper=main.slice(main.indexOf('export function computeGeometricPrecheck('),main.indexOf('function updateGeometricPrecheckUI('));
const computeFromMain=new Function('computePlacementMetrics','getScenePlacement','physicalGeometryRef','sceneToolLengthM',
  wrapper.replace('export function','function')+';return computeGeometricPrecheck;')(
    computePlacementMetrics,()=>current,geo,tool);
close(computeFromMain(0,70,10.5,180).D_far_app,currentMetrics.D_far_app,'main wrapper uses active pose/tool');
// Execute both real UI update functions with a lightweight DOM. In particular,
// an authoritative UNKNOWN packet must not become green via local fallbacks.
setScenePlacement(current);
const elements = new Map();
const documentMock = {getElementById(id) {
  if (!elements.has(id)) elements.set(id,{textContent:'',className:''});
  return elements.get(id);
}};
const uiSource=main.slice(main.indexOf('function updateGeometricPrecheckUI('),main.indexOf('export function applyAuthoritativeBoardPlacement('));
const analysisSource=main.slice(main.indexOf('export function applyPlacementAnalysisUI('),main.indexOf('export function updateFullRouteValidationResultUI('));
const ui=new Function('getScenePlacement','computeGeometricPrecheck','formatMetric','placementAxisLabel','document',
  uiSource+analysisSource.replace('export function','function')+';return {updateGeometricPrecheckUI,applyPlacementAnalysisUI};')(
    getScenePlacement,computeFromMain,formatMetric,placementAxisLabel,documentMock);
ui.updateGeometricPrecheckUI(0,70,0,180);
assert.equal(elements.get('readoutNearGridDepth').textContent,'3.8 mm');
assert.equal(elements.get('readoutCenterDist').textContent,'23.8 mm');
assert.equal(elements.get('geomPrecheckBadge').textContent,'GEOMETRIC PASS');
assert.ok(elements.get('readoutBoardYaw').textContent.includes('col=-Y_robot, row=+X_robot'));
ui.applyPlacementAnalysisUI({is_geometric_known:false,is_geometric_pass:false});
assert.equal(elements.get('geomPrecheckBadge').textContent,'GEOMETRIC UNKNOWN');
assert.equal(elements.get('readoutNearGridDepth').textContent,'—');
ui.applyPlacementAnalysisUI({d_max_for_current_h_mm:null});
assert.equal(elements.get('readoutDMax').textContent,'—','explicit no-solution must not use local fallback');
console.log(`Viewer placement metrics/ruler: ${checkedCells} mesh/cell comparisons, yaw/shift/limits/unknown/taught/main parity PASS`);
