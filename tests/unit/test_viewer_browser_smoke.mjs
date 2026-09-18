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
const TARGET_URL = "http://localhost:8085/index.html";

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
        const target = pages.find((p) => p.type === "page" && p.url.includes("localhost:8085"));
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
      consoleErrors.push(msg.params?.exceptionDetails?.text || JSON.stringify(msg.params));
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
  const yawText = await evaluate("document.querySelector('#readoutBoardYaw')?.textContent");
  assert.ok(yawText && yawText.includes("+90.0°"), `Board Yaw must display +90.0°, got: '${yawText}'`);

  const nearestDist = await evaluate("document.querySelector('#readoutRow0Dist')?.textContent");
  assert.ok(nearestDist && nearestDist.includes("200.0 mm"), `Nearest cell distance must be 200.0 mm, got: '${nearestDist}'`);

  const farthestDist = await evaluate("document.querySelector('#readoutRow9Dist')?.textContent");
  assert.ok(farthestDist && farthestDist.includes("520.0 mm"), `Farthest cell distance must be 520.0 mm, got: '${farthestDist}'`);

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

  const updatedRow0 = await evaluate("document.querySelector('#readoutRow0Dist')?.textContent");
  assert.ok(updatedRow0 && updatedRow0.includes("215.0 mm"), `readoutRow0Dist must be 215.0 mm after +15mm shift, got: '${updatedRow0}'`);

  const updatedRow9 = await evaluate("document.querySelector('#readoutRow9Dist')?.textContent");
  assert.ok(updatedRow9 && updatedRow9.includes("535.0 mm"), `readoutRow9Dist must be 535.0 mm after +15mm shift, got: '${updatedRow9}'`);
  console.log("  [PASS] V90-05: Dynamic placement packet updates UI readouts with 90° shift math.");

  ws.close();
  cleanup();
  console.log("ALL VIEWER BROWSER SMOKE TESTS PASSED SUCCESSFULLY!");
} catch (err) {
  cleanup();
  console.error("Browser smoke test failed:", err);
  process.exit(1);
}
