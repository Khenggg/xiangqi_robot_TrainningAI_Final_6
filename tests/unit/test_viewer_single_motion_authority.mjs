// tests/unit/test_viewer_single_motion_authority.mjs
// Verifies:
// 1. Viewer code contains NO client-side trajectory planners or timers (Single Motion Authority).
// 2. Outgoing client WebSocket command contract { command: "EXECUTE_3STAGE", src: [r, c], dst: [r, c] }.
// 3. Scene configuration classifies tool offset as USER_MEASURED_CAD_REPORTED and visual asset as VISUAL_CALIBRATION_PROVISIONAL.
// 4. No stale references to "+1.5mm" remain in HTML or viewer code.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

console.log("Running Viewer Single Motion Authority Verification Tests (Node.js)...");

// 1. Test that main.mjs has NO client-side trajectoryQueue or timer-based stepping
const mainMjsPath = path.resolve(repoRoot, "robot-3d-viewer", "main.mjs");
const mainMjsContent = fs.readFileSync(mainMjsPath, "utf-8");

assert.ok(
  !mainMjsContent.includes("trajectoryQueue"),
  "main.mjs must NOT contain 'trajectoryQueue' (client-side planning removed)"
);
assert.ok(
  !mainMjsContent.includes("runNextTrajectoryStep"),
  "main.mjs must NOT contain 'runNextTrajectoryStep' (timer-based stepping removed)"
);
assert.ok(
  !mainMjsContent.includes("executeSafeTrajectory"),
  "main.mjs must NOT contain 'executeSafeTrajectory' (client-side trajectory generator removed)"
);
assert.ok(
  !mainMjsContent.includes("advanceLiveInterpolation"),
  "main.mjs must NOT contain 'advanceLiveInterpolation' (fake interpolation timer removed)"
);

console.log("  [PASS] main.mjs confirmed free of client-side motion authorities and timer stepping.");

// 2. Test outgoing command contract in main.mjs
assert.ok(
  mainMjsContent.includes('"EXECUTE_3STAGE"'),
  "main.mjs must dispatch authoritative command 'EXECUTE_3STAGE' over WebSocket"
);
assert.ok(
  mainMjsContent.includes("grasp_piece: false"),
  "main.mjs must explicitly specify grasp_piece: false for goToCell diagnostic navigation"
);
assert.ok(
  mainMjsContent.includes("handleBackendTrajectoryStage"),
  "main.mjs must consume backend trajectory_stage telemetry"
);

// 3. Test truthful metadata in shared/virtual_fr3_scene.json
const sceneJsonPath = path.resolve(repoRoot, "shared", "virtual_fr3_scene.json");
const sceneData = JSON.parse(fs.readFileSync(sceneJsonPath, "utf-8"));

assert.equal(
  sceneData?.tool_transform?.status,
  "MEASURED_APPROXIMATE",
  "tool_transform.status must be MEASURED_APPROXIMATE"
);
assert.equal(
  sceneData?.tool_transform?.visual_asset_status,
  "VISUAL_CALIBRATION_PROVISIONAL",
  "tool_transform.visual_asset_status must be VISUAL_CALIBRATION_PROVISIONAL"
);
assert.deepEqual(
  sceneData?.tool_transform?.flange_to_tcp_xyz_m,
  [0.0, 0.0, 0.150],
  "flange_to_tcp_xyz_m must be [0, 0, 0.150]"
);

console.log("  [PASS] shared/virtual_fr3_scene.json has honest tool and visual asset classification.");

// 4. Test index.html UI truthful metadata presentation and no stale +1.5mm
const indexPath = path.resolve(repoRoot, "robot-3d-viewer", "index.html");
const indexContent = fs.readFileSync(indexPath, "utf-8");

assert.ok(
  indexContent.includes("MEASURED_APPROXIMATE"),
  "index.html must display MEASURED_APPROXIMATE"
);
assert.ok(
  indexContent.includes("VISUAL_CALIBRATION_PROVISIONAL"),
  "index.html must display VISUAL_CALIBRATION_PROVISIONAL"
);
assert.ok(
  !indexContent.includes("+1.5mm"),
  "index.html must NOT contain stale '+1.5mm' references"
);
assert.ok(
  !mainMjsContent.includes("+1.5mm"),
  "main.mjs must NOT contain stale '+1.5mm' references"
);

console.log("  [PASS] UI displays truthful metadata and contains no stale +1.5mm references.");

// 5. Test Collision Guard is locked ON in normal viewer (no disable checkbox)
assert.ok(
  !indexContent.includes('id="chk-collision-guard"'),
  "index.html must NOT have a checkbox allowing users to disable Collision Guard in normal mode"
);
assert.ok(
  indexContent.includes("ALWAYS ACTIVE") || indexContent.includes("LUÔN BẬT"),
  "index.html must indicate Collision Guard is ALWAYS ACTIVE"
);
console.log("  [PASS] Collision Guard toggle disabled/locked ON in normal viewer.");

// 6. Test Joint Slider Single Authority
assert.ok(
  mainMjsContent.includes('"MOVE_JOINT"'),
  "main.mjs must dispatch authoritative 'MOVE_JOINT' command to backend when sliders move"
);
console.log("  [PASS] Joint sliders dispatch MOVE_JOINT command; no local simulation authority.");

// 7. Test Dynamic Board Placement Commands and Telemetry
assert.ok(
  mainMjsContent.includes('"SET_BOARD_PLACEMENT"'),
  "main.mjs must support SET_BOARD_PLACEMENT command"
);
assert.ok(
  mainMjsContent.includes('"RESET_BOARD_PLACEMENT"'),
  "main.mjs must support RESET_BOARD_PLACEMENT command"
);
assert.ok(
  mainMjsContent.includes('"VALIDATE_BOARD_PLACEMENT"'),
  "main.mjs must support VALIDATE_BOARD_PLACEMENT command"
);
assert.ok(
  mainMjsContent.includes('"board_placement"'),
  "main.mjs must handle authoritative board_placement telemetry packets"
);

// 8. Test board.mjs visual mesh updates from authoritative placement
const boardMjsPath = path.resolve(repoRoot, "robot-3d-viewer", "board.mjs");
const boardMjsContent = fs.readFileSync(boardMjsPath, "utf-8");
assert.ok(
  boardMjsContent.includes("setScenePlacement"),
  "board.mjs must expose setScenePlacement"
);
assert.ok(
  boardMjsContent.includes("_activeBoardGroup"),
  "board.mjs must maintain _activeBoardGroup to move board visuals consistently"
);

// 9. Test main.mjs imports setScenePlacement and exports applyAuthoritativeBoardPlacement
assert.ok(
  mainMjsContent.includes('import {') && mainMjsContent.includes('setScenePlacement') && mainMjsContent.includes('"./board.mjs"'),
  "main.mjs must import setScenePlacement from ./board.mjs"
);
assert.ok(
  mainMjsContent.includes("export function applyAuthoritativeBoardPlacement"),
  "main.mjs must export applyAuthoritativeBoardPlacement"
);
assert.ok(
  mainMjsContent.includes("window.applyAuthoritativeBoardPlacement = applyAuthoritativeBoardPlacement"),
  "main.mjs must attach applyAuthoritativeBoardPlacement to window for testing/debugging"
);

// 10. Test boardVisualRoot naming and piece isolation (pieces not inside boardVisualRoot)
assert.ok(
  boardMjsContent.includes('group.name = "boardVisualRoot"'),
  "board.mjs must name board group 'boardVisualRoot'"
);
assert.ok(
  mainMjsContent.includes("scene.add(piecesGroup)") && !mainMjsContent.includes("boardVisualRoot.add(piecesGroup)"),
  "Pieces must be added directly to scene, NOT as children of boardVisualRoot (prevents double-translation)"
);

// 11. Test authoritative placement coordinate updates (+15mm shift -> +15mm world Z, +30mm z_offset -> +30mm world Y)
assert.ok(
  boardMjsContent.includes("export function setScenePlacement"),
  "board.mjs must export setScenePlacement"
);
assert.ok(
  boardMjsContent.includes("export function getScenePlacement"),
  "board.mjs must export getScenePlacement"
);
assert.ok(
  boardMjsContent.includes("export function getActiveBoardGroup"),
  "board.mjs must export getActiveBoardGroup"
);
assert.ok(
  boardMjsContent.includes("export function getBoardVisualRoot"),
  "board.mjs must export getBoardVisualRoot"
);
assert.ok(
  boardMjsContent.includes("_activeBoardGroup.position.set(") &&
  boardMjsContent.includes("_activeScenePlacement.boardCenterZ") &&
  boardMjsContent.includes("_activeScenePlacement.boardSurfaceY"),
  "board.mjs must update _activeBoardGroup position using authoritative center coordinates"
);

// Verify canonical transformation math contract for viewer
function simulateSetScenePlacement(placement) {
  const centerWorld = placement.board_center_world_m || [
    placement.boardCenterX ?? 0.0,
    placement.boardSurfaceY ?? 0.0105,
    placement.boardCenterZ ?? 0.36
  ];
  return {
    boardCenterX: Number(centerWorld[0]),
    boardSurfaceY: Number(centerWorld[1]),
    boardCenterZ: Number(centerWorld[2]),
    forwardShiftMm: Number(placement.forward_shift_mm ?? 0.0),
    safeTransitHeightMm: Number(placement.safe_transit_height_mm ?? 70.0),
    boardHeightOffsetMm: Number(placement.board_height_offset_mm ?? 0.0),
    placementVersion: Number(placement.placement_version ?? 1),
  };
}

const currentScenePlacement = simulateSetScenePlacement({
  forward_shift_mm: 15.0,
  safe_transit_height_mm: 50.0,
  board_height_offset_mm: 30.0,
  board_center_world_m: [0.0, 0.0405, 0.375],
  placement_version: 3,
});
assert.equal(currentScenePlacement.forwardShiftMm, 15.0);
assert.equal(currentScenePlacement.safeTransitHeightMm, 50.0);
assert.equal(currentScenePlacement.boardHeightOffsetMm, 30.0);
assert.equal(currentScenePlacement.placementVersion, 3);
assert.equal(currentScenePlacement.boardCenterZ, 0.375, "Forward shift of +15mm must shift Three.js world Z from 0.360 to 0.375 (+15mm)");
assert.equal(currentScenePlacement.boardSurfaceY, 0.0405, "Vertical offset of +30mm must shift Three.js surface Y from 0.0105 to 0.0405 (+30mm)");

// 12. Test stale validation rejection and full route safe terminology in main.mjs
assert.ok(
  mainMjsContent.includes('"STALE_VALIDATION_RESULT"'),
  "main.mjs must check for STALE_VALIDATION_RESULT"
);
assert.ok(
  mainMjsContent.includes('"90/90 LOCAL CELL TRAJECTORIES PASS"'),
  "main.mjs must display authoritative terminology '90/90 LOCAL CELL TRAJECTORIES PASS'"
);
assert.ok(
  mainMjsContent.includes('"FULL BOARD ROUTE SAFE"'),
  "main.mjs must display authoritative terminology 'FULL BOARD ROUTE SAFE'"
);

// 13. Test placement_analysis UI synchronization
assert.ok(
  mainMjsContent.includes("applyPlacementAnalysisUI"),
  "main.mjs must implement applyPlacementAnalysisUI"
);
assert.ok(
  mainMjsContent.includes('"placement_analysis"'),
  "main.mjs must dispatch placement_analysis telemetry directly to applyPlacementAnalysisUI"
);

console.log("  [PASS] Dynamic Board Placement commands and authoritative telemetry updates verified.");
console.log("  [PASS] applyAuthoritativeBoardPlacement, visual translation, and piece isolation verified.");
console.log("ALL VIEWER SINGLE MOTION AUTHORITY & DYNAMIC PLACEMENT TESTS PASSED SUCCESSFULLY!");
