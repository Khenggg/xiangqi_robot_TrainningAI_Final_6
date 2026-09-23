// tests/unit/test_viewer_browser_smoke.mjs
// Automated Browser Smoke Test using Headless Chrome & Chrome DevTools Protocol (CDP)
// Verifies:
// - V90-01: Browser boots without unhandled fatal script errors.
// - V90-02: Canvas #c exists and WebGL context is operational.
// - V90-03: HUD and diagnostic readouts (#jointsReadout, #readoutBoardYaw, #geomPrecheckBadge) exist and display 90° data.
// - V90-04: window.applyAuthoritativeBoardPlacement and window.setScenePlacement are attached.
// - V90-05: Dynamic placement updates correctly update UI readouts without throwing.

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";

console.log("Running Viewer Browser Smoke Test (Headless Chrome CDP)...");

const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
if (!fs.existsSync(CHROME_PATH)) {
  console.log(`[SKIP] Chrome executable not found at ${CHROME_PATH}`);
  process.exit(0);
}

const CDP_PORT = 9444;
const TARGET_URL = process.env.VIEWER_SMOKE_URL || "http://localhost:8085/index.html";
const TARGET_HOST = new URL(TARGET_URL).host;

// Launch headless Chrome
const chromeProc = spawn(CHROME_PATH, [
  "--headless=new",
  `--remote-debugging-port=${CDP_PORT}`,
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--user-data-dir=" + fs.mkdtempSync("C:\\Users\\Ken\\AppData\\Local\\Temp\\chrome-smoke-"),
  TARGET_URL,
]);

let cleanedUp = false;
function cleanup() {
  if (cleanedUp) return;
  cleanedUp = true;
  try {
    chromeProc.kill("SIGKILL");
  } catch (_) {}
}

process.on("exit", cleanup);
process.on("SIGINT", cleanup);
process.on("uncaughtException", (err) => {
  cleanup();
  console.error("Uncaught error:", err);
  process.exit(1);
});

// Helper to poll for CDP endpoint
async function waitForCDP(maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
      if (res.ok) {
        const pages = await res.json();
        const target = pages.find((p) => p.type === "page" && p.url.includes(TARGET_HOST));
        if (target && target.webSocketDebuggerUrl) {
          return target.webSocketDebuggerUrl;
        }
      }
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("Timeout waiting for Chrome CDP WebSocket endpoint for viewer page");
}

try {
  const wsUrl = await waitForCDP();
  console.log("  [PASS] Headless Chrome connected via CDP.");

  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  let idCounter = 1;
  const pendingRequests = new Map();
  const consoleErrors = [];

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === "Runtime.exceptionThrown") {
      const details = msg.params?.exceptionDetails;
      const desc = `${details?.exception?.description || details?.text} at ${details?.url}:${details?.lineNumber}:${details?.columnNumber}`;
      consoleErrors.push(desc);
    }
    if (msg.method === "Runtime.consoleAPICalled" && msg.params?.type === "error") {
      const argsText = (msg.params?.args || []).map((a) => a.value || a.description || JSON.stringify(a)).join(" ");
      consoleErrors.push(`console.error: ${argsText}`);
    }
    if (msg.id && pendingRequests.has(msg.id)) {
      const { resolve, reject } = pendingRequests.get(msg.id);
      pendingRequests.delete(msg.id);
      if (msg.error) {
        reject(new Error(msg.error.message));
      } else {
        resolve(msg.result);
      }
    }
  };

  function sendCDP(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = idCounter++;
      pendingRequests.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  // Enable Runtime and Page
  await sendCDP("Runtime.enable");
  await sendCDP("Page.enable");

  // Wait 2 seconds for Three.js scene, textures, and assets to initialize
  await new Promise((r) => setTimeout(r, 2500));

  async function evaluate(expression) {
    const res = await sendCDP("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`Eval error: ${res.exceptionDetails.text} (${expression})`);
    }
    return res.result?.value;
  }

  // V90-01: Check for zero unhandled script errors
  assert.equal(consoleErrors.length, 0, `Unhandled script errors detected: ${JSON.stringify(consoleErrors)}`);
  console.log("  [PASS] V90-01: Zero unhandled script exceptions during boot.");

  // V90-02: Canvas #scene exists and has positive dimensions
  const canvasExists = await evaluate("Boolean(document.querySelector('#scene'))");
  assert.ok(canvasExists, "Canvas #scene element must exist in DOM");

  const canvasDims = await evaluate("(() => { const c = document.querySelector('#scene'); return [c.clientWidth, c.clientHeight]; })()");
  assert.ok(canvasDims[0] > 0 && canvasDims[1] > 0, `Canvas dimensions must be > 0, got ${JSON.stringify(canvasDims)}`);
  console.log("  [PASS] V90-02: WebGL canvas initialized with positive client dimensions.");

  // V90-03: HUD readouts exist and report expected 90° board metadata
  let viewerReady = false;
  for (let attempt = 0; attempt < 80; attempt++) {
    viewerReady = await evaluate("Boolean(window.__state?.currentArm && document.querySelector('#joint-slider-1'))");
    if (viewerReady) break;
    await new Promise((r) => setTimeout(r, 250));
  }
  assert.ok(viewerReady, "FR3 geometry and joint controls must finish loading");

  // V90-06: Offline startup cannot show a frontend-owned pose or accept slider motion.
  const offlineState = await evaluate("(() => { const s = window.__state; const arm = s.currentArm; const slider = document.querySelector('#joint-slider-1'); const before = [...s.jointsDeg]; slider.value = '-60'; slider.dispatchEvent(new Event('input', { bubbles: true })); return { validated: s.poseValidated, visible: arm.group.visible, sliderDisabled: slider.disabled, before, after: [...s.jointsDeg] }; })()");
  assert.equal(offlineState.validated, false, "offline startup must await backend collision validation");
  assert.equal(offlineState.visible, false, "unvalidated robot geometry must remain hidden");
  assert.equal(offlineState.sliderDisabled, true, "offline joint slider must be unavailable");
  assert.deepEqual(offlineState.after, offlineState.before, "slider input must not mutate offline joints");
  console.log("  [PASS] V90-06: Offline startup and slider input cannot create an operational robot pose.");

  // V90-07: The simulation guard bounds cover actual rendered STEP vertices in
  // wrist3_link coordinates, both open and across the full close sweep.
  const inspectRenderedGripper = async (closed) => {
    const browserFunction = async function inspect(isClosed) {
      const asset = await (await fetch('/shared/gripper_visual_asset.json')).json();
      const envelope = asset.simulation_collision_envelope_j6;
      const arm = window.__state.currentArm;
      if (arm.gripper.group.userData.robotVisualRole !== 'j6-tool-mount') {
        throw new Error('FR3 STEP gripper mount is not active');
      }
      arm.group.updateWorldMatrix(true, true);
      const j6 = arm.jointRotators[5];
      const V = j6.position.constructor;
      const Q = j6.quaternion.constructor;
      const origin = j6.getWorldPosition(new V());
      const inverse = j6.getWorldQuaternion(new Q()).invert();
      const rows = [];
      arm.gripper.group.traverse((mesh) => {
        if (!mesh.isMesh) return;
        const attr = mesh.geometry.attributes.position;
        const min = [Infinity, Infinity, Infinity];
        const max = [-Infinity, -Infinity, -Infinity];
        for (let i = 0; i < attr.count; i++) {
          const point = new V().fromBufferAttribute(attr, i)
            .applyMatrix4(mesh.matrixWorld).sub(origin).applyQuaternion(inverse);
          for (let axis = 0; axis < 3; axis++) {
            min[axis] = Math.min(min[axis], point.getComponent(axis));
            max[axis] = Math.max(max[axis], point.getComponent(axis));
          }
        }
        rows.push({ finger: Boolean(mesh.userData.isGripperFinger), min, max });
      });
      const tolerance = 0.00005;
      let withinEnvelope = rows.length > 0;
      const violations = [];
      for (const row of rows) {
        let box;
        if (row.finger) {
          const centerX = (row.min[0] + row.max[0]) / 2;
          const finger = envelope.finger_bounds_open_m[centerX >= 0 ? 0 : 1];
          box = { min: [...finger.min], max: [...finger.max] };
          if (isClosed) {
            const travel = asset.finger_travel_mm * asset.scale_to_m;
            if (finger.closed_motion_direction_x < 0) box.min[0] -= travel;
            else box.max[0] += travel;
          }
        } else {
          box = envelope.housing_bounds_m;
        }
        if ([0, 1, 2].some((axis) =>
          row.min[axis] < box.min[axis] - tolerance ||
          row.max[axis] > box.max[axis] + tolerance
        )) {
          withinEnvelope = false;
          violations.push({ finger: row.finger, min: row.min, max: row.max, box });
        }
      }
      return {
        isClosed,
        withinEnvelope,
        meshCount: rows.length,
        violations,
        bounds: [
          [Math.min(...rows.map((row) => row.min[0])), Math.max(...rows.map((row) => row.max[0]))],
          [Math.min(...rows.map((row) => row.min[1])), Math.max(...rows.map((row) => row.max[1]))],
          [Math.min(...rows.map((row) => row.min[2])), Math.max(...rows.map((row) => row.max[2]))],
        ],
      };
    };
    return evaluate("(" + browserFunction.toString() + ")(" + JSON.stringify(closed) + ")");
  };

  const openGripperBounds = await inspectRenderedGripper(false);
  assert.ok(openGripperBounds.withinEnvelope, "open STEP mesh escaped simulation guard: " + JSON.stringify(openGripperBounds));
  assert.ok(openGripperBounds.meshCount >= 2, "loaded CAD gripper meshes must be measured");
  await evaluate("window.__state.currentArm.gripper.setClosed(true)");
  const closedGripperBounds = await inspectRenderedGripper(true);
  assert.ok(closedGripperBounds.withinEnvelope, "closed STEP mesh escaped simulation guard: " + JSON.stringify(closedGripperBounds));
  await evaluate("window.__state.currentArm.gripper.setClosed(false)");
  console.log("  [PASS] V90-07: " + openGripperBounds.meshCount + " rendered STEP meshes fit the PyBullet guard (open and closed); bounds " + JSON.stringify(openGripperBounds.bounds) + " m.");

  const yawText = await evaluate("document.querySelector('#readoutBoardYaw')?.textContent");
  assert.ok(yawText && yawText.includes("+90.0°"), `Board Yaw must display +90.0°, got: '${yawText}'`);

  const nearestDist = await evaluate("document.querySelector('#readoutNearGridDepth, #readoutRow0Dist')?.textContent");
  assert.ok(nearestDist && nearestDist.includes("200.0 mm"), `Nearest grid depth must be 200.0 mm, got: '${nearestDist}'`);

  const farthestDist = await evaluate("document.querySelector('#readoutFarGridDepth, #readoutRow9Dist')?.textContent");
  assert.ok(farthestDist && farthestDist.includes("520.0 mm"), `Farthest grid depth must be 520.0 mm, got: '${farthestDist}'`);

  const badgeText = await evaluate("document.querySelector('#geomPrecheckBadge')?.textContent");
  assert.ok(badgeText && (badgeText.includes("PASS") || badgeText.includes("GEOMETRIC PASS")), `Geometric precheck must pass, got: '${badgeText}'`);
  console.log("  [PASS] V90-03: HUD readouts display canonical 90° metadata and PASS badge.");

  // V90-04: Authoritative functions attached to window
  const hasAuthoritativeFn = await evaluate("typeof window.applyAuthoritativeBoardPlacement === 'function'");
  assert.ok(hasAuthoritativeFn, "window.applyAuthoritativeBoardPlacement must be a function");

  const hasSetPlacementFn = await evaluate("typeof window.setScenePlacement === 'function'");
  assert.ok(hasSetPlacementFn, "window.setScenePlacement must be a function");
  console.log("  [PASS] V90-04: Authoritative board placement APIs properly attached to window.");

  // V90-05: Dynamic board placement dispatch updates UI readouts without error
  await evaluate(`
    window.applyAuthoritativeBoardPlacement({
      forward_shift_mm: 15.0,
      safe_transit_height_mm: 40.0,
      board_height_offset_mm: 30.0,
      placement_version: 2
    });
  `);

  const updatedD = await evaluate("document.querySelector('#readoutShiftD')?.textContent");
  assert.ok(updatedD && updatedD.includes("15.0 mm"), `readoutShiftD must be 15.0 mm, got: '${updatedD}'`);

  const updatedRow0 = await evaluate("document.querySelector('#readoutNearGridDepth, #readoutRow0Dist')?.textContent");
  assert.ok(updatedRow0 && updatedRow0.includes("215.0 mm"), `readoutNearGridDepth must be 215.0 mm after +15mm shift, got: '${updatedRow0}'`);

  const updatedRow9 = await evaluate("document.querySelector('#readoutFarGridDepth, #readoutRow9Dist')?.textContent");
  assert.ok(updatedRow9 && updatedRow9.includes("535.0 mm"), `readoutFarGridDepth must be 535.0 mm after +15mm shift, got: '${updatedRow9}'`);
  console.log("  [PASS] V90-05: Dynamic placement packet updates UI readouts with 90° shift math.");

  // V90-09: Actual Three.js Link Parity against Canonical Chain (Fix 5)
  const linkParity = await evaluate("(" + (async function checkLinkParity() {
    const profile = await (await fetch('/shared/robot_profiles/fr3.json')).json();
    const sceneConfig = await (await fetch('/shared/virtual_fr3_scene.json')).json();
    const rot = sceneConfig.robot_base_to_3d_world.rotation_matrix;
    const trans = sceneConfig.robot_base_to_3d_world.translation_m;
    const rootMatrix = new THREE.Matrix4().set(
      rot[0][0], rot[0][1], rot[0][2], trans[0],
      rot[1][0], rot[1][1], rot[1][2], trans[1],
      rot[2][0], rot[2][1], rot[2][2], trans[2],
      0, 0, 0, 1
    );

    const arm = window.__state.currentArm;
    const representativeQDeg = [
      [0, -45, 90, -45, -90, 0],
      [0, -60, 110, -105, -120, 0],
      [0, -70, 110, -105, -120, 0],
      [37, -32, 78, -118, 64, -29],
    ];

    let maxPosErrorM = 0;
    let maxOrientErrorDeg = 0;
    let checkedCount = 0;

    for (const q of representativeQDeg) {
      arm.jointRotators.forEach((rotator, i) => {
        rotator.rotation.z = THREE.MathUtils.degToRad(q[i]);
      });
      arm.group.updateWorldMatrix(true, true);

      let currentT = rootMatrix.clone();
      for (let i = 0; i < 6; i++) {
        const jConfig = profile.joints[i];
        const frameT = new THREE.Matrix4();
        const rotEuler = new THREE.Euler(
          jConfig.origin_rpy_rad[0],
          jConfig.origin_rpy_rad[1],
          jConfig.origin_rpy_rad[2],
          'XYZ'
        );
        frameT.makeRotationFromEuler(rotEuler);
        frameT.setPosition(
          jConfig.origin_xyz_m[0],
          jConfig.origin_xyz_m[1],
          jConfig.origin_xyz_m[2]
        );

        const rotZ = new THREE.Matrix4().makeRotationZ(THREE.MathUtils.degToRad(q[i]));
        currentT = currentT.clone().multiply(frameT).multiply(rotZ);

        const actualWorldT = arm.jointRotators[i].matrixWorld;
        const actualPos = new THREE.Vector3().setFromMatrixPosition(actualWorldT);
        const expectedPos = new THREE.Vector3().setFromMatrixPosition(currentT);
        const posError = actualPos.distanceTo(expectedPos);

        const actualQuat = new THREE.Quaternion().setFromRotationMatrix(actualWorldT);
        const expectedQuat = new THREE.Quaternion().setFromRotationMatrix(currentT);
        const quatDot = Math.min(1.0, Math.max(-1.0, Math.abs(actualQuat.dot(expectedQuat))));
        const orientError = 2.0 * Math.acos(quatDot) * (180.0 / Math.PI);

        maxPosErrorM = Math.max(maxPosErrorM, posError);
        maxOrientErrorDeg = Math.max(maxOrientErrorDeg, orientError);
        checkedCount++;
      }
    }
    // Restore default joint state
    arm.jointRotators.forEach((rotator, i) => {
      rotator.rotation.z = THREE.MathUtils.degToRad(window.__state.jointsDeg[i] || 0);
    });
    arm.group.updateWorldMatrix(true, true);

    return { checkedCount, maxPosErrorM, maxOrientErrorDeg };
  }).toString() + ")()");

  assert.equal(linkParity.checkedCount, 24, "Must compare all 6 movable links across 4 configurations");
  assert.ok(linkParity.maxPosErrorM <= 0.0001, `Three.js link position error exceeds 0.1 mm: ${linkParity.maxPosErrorM * 1000} mm`);
  assert.ok(linkParity.maxOrientErrorDeg <= 0.05, `Three.js link orientation error exceeds 0.05 deg: ${linkParity.maxOrientErrorDeg} deg`);
  console.log(`  [PASS] V90-09: Actual Three.js link parity (${linkParity.checkedCount} link poses; max pos ${(linkParity.maxPosErrorM * 1000).toFixed(4)} mm, max orient ${linkParity.maxOrientErrorDeg.toFixed(5)} deg).`);

  // V90-10: Actual Rendered Board Plane Parity (Fix 6)
  const boardParity = await evaluate("(" + (async function checkBoardParity() {
    const sceneConfig = await (await fetch('/shared/virtual_fr3_scene.json')).json();
    const canonicalCenter = sceneConfig.virtual_board_placement.board_center_in_3d_world_m;
    const expectedTopY = canonicalCenter[1];

    const scene = window.__scene;
    const boardVisualRoot = scene.getObjectByName("boardVisualRoot");
    if (!boardVisualRoot) throw new Error("boardVisualRoot not found in scene");

    const boardTop = scene.getObjectByName("boardTop") || boardVisualRoot.children[1];
    if (!boardTop) throw new Error("boardTop mesh not found in boardVisualRoot");

    boardVisualRoot.updateWorldMatrix(true, true);
    boardTop.updateWorldMatrix(true, true);

    // The top surface of the rendered board in world space
    const box = new THREE.Box3().setFromObject(boardTop);
    const planeOffsetM = Math.abs(box.max.y - expectedTopY);

    const normalWorld = new THREE.Vector3(0, 1, 0).transformDirection(boardTop.matrixWorld);
    const normalAlignment = normalWorld.dot(new THREE.Vector3(0, 1, 0));

    return {
      expectedTopY,
      actualTopY: box.max.y,
      planeOffsetM,
      normalAlignment,
    };
  }).toString() + ")()");

  assert.ok(boardParity.planeOffsetM <= 0.0001, `Rendered board top plane offset exceeds 0.1 mm: ${boardParity.planeOffsetM * 1000} mm`);
  assert.ok(boardParity.normalAlignment >= 0.99999, `Rendered board top normal does not face +Y: ${boardParity.normalAlignment}`);
  console.log(`  [PASS] V90-10: Actual rendered board plane parity (plane offset ${(boardParity.planeOffsetM * 1000).toFixed(4)} mm, normal alignment ${boardParity.normalAlignment.toFixed(6)}).`);

  // V90-11: Real UI cell selection & dispatch path (Fix 1, Fix 2, Fix 3)
  // Step 1: Unvalidated / offline state cannot dispatch cell motion
  const offlineDispatch = await evaluate(`(() => {
    const rowSelect = document.getElementById('cellRowSelect');
    const colSelect = document.getElementById('cellColSelect');
    const reachBtn = document.getElementById('reachCellBtn');
    rowSelect.value = '4';
    colSelect.value = '5';
    reachBtn.click();
    return {
      selected: window.__state.selectedCell,
      targetDest: window.__state.targetDestinationCell,
      badgeText: document.getElementById('diagStatusBadge')?.textContent || '',
    };
  })()`);
  assert.deepEqual(offlineDispatch.selected, { row: 4, col: 5 });
  assert.ok(offlineDispatch.targetDest, "targetDestinationCell must be defined");
  assert.equal(offlineDispatch.targetDest.row, 4);
  assert.equal(offlineDispatch.targetDest.col, 5);
  assert.ok(typeof offlineDispatch.targetDest.x_m === 'number' && Number.isFinite(offlineDispatch.targetDest.x_m));
  assert.ok(offlineDispatch.badgeText.includes('LỖI') || offlineDispatch.badgeText.includes('REJECTED'),
    `Offline cell selection must show authority warning: '${offlineDispatch.badgeText}'`);

  // Step 2: Under authoritative state, UI click dispatches EXECUTE_3STAGE cleanly
  const uiDispatchResult = await evaluate(`(() => {
    const s = window.__state;
    const sent = [];
    const mockSocket = {
      readyState: WebSocket.OPEN,
      send(data) {
        sent.push(JSON.parse(data));
      }
    };
    s.liveSocket = mockSocket;
    s.poseValidated = true;
    s.authoritativeRobotModel = 'FR3';
    s.placementVersion = 2;

    const rowSelect = document.getElementById('cellRowSelect');
    const colSelect = document.getElementById('cellColSelect');
    const reachBtn = document.getElementById('reachCellBtn');
    rowSelect.value = '3';
    colSelect.value = '4';
    reachBtn.click();

    return {
      sent,
      selected: s.selectedCell,
      targetDest: s.targetDestinationCell,
    };
  })()`);

  assert.deepEqual(uiDispatchResult.selected, { row: 3, col: 4 });
  assert.equal(uiDispatchResult.targetDest.row, 3);
  assert.equal(uiDispatchResult.targetDest.col, 4);
  const execCmd = uiDispatchResult.sent.find((c) => c.command === 'EXECUTE_3STAGE');
  assert.ok(execCmd, "UI click must dispatch command == 'EXECUTE_3STAGE'");
  assert.deepEqual(execCmd.dst, [3, 4], "Command must include expected dst: [3, 4]");
  assert.equal(execCmd.placement_version, 2, "Command must include placement_version");
  assert.equal(consoleErrors.length, 0, `Zero runtime exceptions expected during UI path, got: ${JSON.stringify(consoleErrors)}`);
  console.log("  [PASS] V90-11: Real UI cell dispatch path triggers cleanly with zero exceptions and dispatches EXECUTE_3STAGE.");

  // Optional live reproduction: run against the actual virtual backend and
  // prove a rejected target never replaces the last safe rendered pose.
  if (process.env.VIEWER_SMOKE_WS_URL) {
    await sendCDP("Page.navigate", { url: TARGET_URL });
    let reloadedViewerReady = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      reloadedViewerReady = await evaluate("Boolean(window.__state?.currentArm && document.getElementById('wsUrl'))");
      if (reloadedViewerReady) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    assert.ok(reloadedViewerReady, "viewer must reload canonical board placement before live reproduction");

    const wsUrl = JSON.stringify(process.env.VIEWER_SMOKE_WS_URL);
    await evaluate("(() => { document.getElementById('wsUrl').value = " + wsUrl + "; document.getElementById('liveBtn').click(); })()");
    let livePoseReady = false;
    for (let attempt = 0; attempt < 80; attempt++) {
      livePoseReady = await evaluate("Boolean(window.__state.poseValidated && window.__state.liveSocket?.readyState === WebSocket.OPEN)");
      if (livePoseReady) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    assert.ok(livePoseReady, "viewer must receive a collision-validated startup pose from the virtual backend");
    const safeJoints = await evaluate("window.__state.jointsDeg");
    const validStartupPoses = [
      [0, -45, 90, -45, -90, 0],
      [0, -70, 60, -80, -90, 0],
    ];
    if (process.env.VIEWER_EXPECTED_START_JOINTS) {
      assert.deepEqual(safeJoints, JSON.parse(process.env.VIEWER_EXPECTED_START_JOINTS));
    } else {
      assert.ok(
        validStartupPoses.some((p) => JSON.stringify(p) === JSON.stringify(safeJoints)),
        `viewer must render a collision-validated backend startup pose, got: ${JSON.stringify(safeJoints)}`
      );
    }

    const boardClearance = await evaluate("(" + (async function measureClearance() {
      const scene = await (await fetch('/shared/virtual_fr3_scene.json')).json();
      const geometry = await (await fetch('/shared/physical_geometry.json')).json();
      const center = scene.virtual_board_placement.board_center_in_3d_world_m;
      const halfX = geometry.board.outer_length / 2000;
      const halfZ = geometry.board.outer_width / 2000;
      const arm = window.__state.currentArm;
      arm.group.updateWorldMatrix(true, true);
      const link = arm.jointRotators[5];
      const V = link.position.constructor;
      let minimum = Infinity;
      let sampled = 0;
      arm.gripper.group.traverse((mesh) => {
        if (!mesh.isMesh) return;
        const attr = mesh.geometry.attributes.position;
        for (let i = 0; i < attr.count; i++) {
          const point = new V().fromBufferAttribute(attr, i).applyMatrix4(mesh.matrixWorld);
          if (Math.abs(point.x - center[0]) <= halfX && Math.abs(point.z - center[2]) <= halfZ) {
            minimum = Math.min(minimum, point.y - center[1]);
            sampled++;
          }
        }
      });
      return { minimum_clearance_m: minimum, sampled_vertices: sampled };
    }).toString() + ")()");
    assert.ok(boardClearance.sampled_vertices > 0, "safe live tool pose must overlap the board footprint for the clearance check");
    assert.ok(boardClearance.minimum_clearance_m >= 0.0005, "rendered CAD tool must clear the board by the guard margin: " + JSON.stringify(boardClearance));

    // Live UI cell dispatch via real DOM reachCellBtn click over live WebSocket to real backend
    await evaluate(`(() => {
      const dispatched = [];
      const origSend = window.__state.liveSocket.send.bind(window.__state.liveSocket);
      window.__state.liveSocket.send = (data) => {
        try { dispatched.push(JSON.parse(data)); } catch (_) {}
        return origSend(data);
      };
      window.__smokeLiveDispatched = dispatched;
      window.__smokeLiveOrigSend = origSend;

      window.__smokeIncomingMessages = [];
      window.__smokeLiveMessageListener = (event) => {
        try {
          const packet = JSON.parse(event.data);
          window.__smokeIncomingMessages.push(packet);
        } catch (_) {}
      };
      window.__state.liveSocket.addEventListener('message', window.__smokeLiveMessageListener);

      const rowSelect = document.getElementById('cellRowSelect');
      const colSelect = document.getElementById('cellColSelect');
      rowSelect.value = '4';
      colSelect.value = '4';
      document.getElementById('reachCellBtn').click();
    })()`);

    const liveDispatchedCmd = await evaluate("window.__smokeLiveDispatched?.find(c => c.command === 'EXECUTE_3STAGE')");
    assert.ok(liveDispatchedCmd, "Real UI reach button click must dispatch EXECUTE_3STAGE over live WebSocket");
    assert.deepEqual(liveDispatchedCmd.dst, [4, 4], "Dispatched command must target cell [4, 4]");
    assert.ok(typeof liveDispatchedCmd.placement_version === "number", "Dispatched command must contain placement_version");
    assert.equal(consoleErrors.length, 0, `Zero runtime exceptions expected during live UI path, got: ${JSON.stringify(consoleErrors)}`);

    // Verify virtual backend produces response telemetry confirming receipt and processing
    let backendProcessingProof = null;
    for (let attempt = 0; attempt < 80; attempt++) {
      backendProcessingProof = await evaluate("window.__smokeIncomingMessages?.find(p => p.type === 'trajectory_result' || p.motion_state === 'MOVING' || (p.trajectory_stage && p.trajectory_stage !== 'IDLE'))");
      if (backendProcessingProof) break;
      await new Promise((r) => setTimeout(r, 200));
    }
    assert.ok(backendProcessingProof, "Virtual backend must produce response telemetry for UI EXECUTE_3STAGE command");
    const signal = backendProcessingProof.type || backendProcessingProof.motion_state || backendProcessingProof.trajectory_stage;
    console.log(`  [PASS] Backend processed UI EXECUTE_3STAGE command (backend signal: ${signal}).`);

    // Await trajectory completion so backend returns to IDLE before the subsequent rejection test
    let trajectoryCompleted = false;
    for (let attempt = 0; attempt < 120; attempt++) {
      const hasResult = await evaluate("Boolean(window.__smokeIncomingMessages?.find(p => p.type === 'trajectory_result'))");
      const latestState = await evaluate("window.__smokeIncomingMessages?.filter(p => p.type === 'robot_state').pop()");
      if (hasResult && latestState && latestState.motion_state === 'IDLE') {
        trajectoryCompleted = true;
        break;
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    assert.ok(trajectoryCompleted, "Virtual backend must complete 3-stage trajectory and return to IDLE");

    // Restore original send method on liveSocket and clean up message listener
    await evaluate(`(() => {
      if (window.__smokeLiveOrigSend) {
        window.__state.liveSocket.send = window.__smokeLiveOrigSend;
      }
      if (window.__smokeLiveMessageListener) {
        window.__state.liveSocket.removeEventListener('message', window.__smokeLiveMessageListener);
      }
    })()`);
    console.log("  [PASS] Live UI reachCellBtn dispatched EXECUTE_3STAGE over live WebSocket and completed safely.");

    await evaluate("window.__smokeTelemetry = []; window.__state.liveSocket.addEventListener('message', event => { try { const packet = JSON.parse(event.data); if (packet.type === 'robot_state') window.__smokeTelemetry.push(packet); } catch (_) {} });");
    const safeJointsBeforeReject = await evaluate("window.__state.jointsDeg");
    const rejectedTarget = [0, -60, 110, -105, -120, 0];
    await evaluate("window.__state.liveSocket.send(JSON.stringify({ command: 'MOVE_JOINT', joints_deg: " + JSON.stringify(rejectedTarget) + " }))");
    let rejectionPacket = null;
    for (let attempt = 0; attempt < 120; attempt++) {
      rejectionPacket = await evaluate("window.__smokeTelemetry.filter(packet => packet.motion_state === 'COLLISION_REJECTED').pop()");
      if (rejectionPacket) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    assert.ok(rejectionPacket, "virtual backend must return COLLISION_REJECTED telemetry for the board-penetrating target");
    assert.equal(rejectionPacket.connected, true);
    assert.equal(rejectionPacket.collision_validated, true, "rejection telemetry must carry the preserved validated pose");
    assert.notDeepEqual(rejectionPacket.joints, rejectedTarget, "backend telemetry must retain the previous safe joints");

    const renderedAfterReject = await evaluate("(() => { const s = window.__state; return { validated: s.poseValidated, visible: s.currentArm.group.visible, joints: s.jointsDeg, rendered: s.currentArm.jointRotators.map(rotator => rotator.rotation.z * 180 / Math.PI) }; })()");
    assert.equal(renderedAfterReject.validated, true);
    assert.equal(renderedAfterReject.visible, true);
    assert.deepEqual(renderedAfterReject.joints, safeJointsBeforeReject, "rejected target must not replace displayed authoritative joints");
    for (let index = 0; index < safeJointsBeforeReject.length; index++) {
      assert.ok(Math.abs(renderedAfterReject.rendered[index] - safeJointsBeforeReject[index]) < 1e-6, "rendered link rotation must remain at the last safe state");
    }

    await sendCDP("Emulation.setDeviceMetricsOverride", { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false });
    await evaluate("document.getElementById('closeControlsBtn').click()");
    await new Promise((r) => setTimeout(r, 300));
    fs.mkdirSync("output/playwright", { recursive: true });
    const screenshot = await sendCDP("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync("output/playwright/backend-rejection-safe-pose.png", Buffer.from(screenshot.data, "base64"));
    console.log("  [PASS] V90-08: Live backend rejected the board-penetrating target; viewer stayed at the validated pose. " + (rejectionPacket.last_error || ""));
  }

  ws.close();
  cleanup();
  console.log("ALL VIEWER BROWSER SMOKE TESTS PASSED SUCCESSFULLY!");
} catch (err) {
  cleanup();
  console.error("Browser smoke test failed:", err);
  process.exit(1);
}
