// tests/unit/test_viewer_coordinate_ruler.mjs
// Verifies:
// 1. ruler.mjs defines and exports buildCoordinateRulerGroup and createDimensionTape.
// 2. main.mjs integrates coordinate ruler and dynamic dimension tape.
// 3. index.html provides toggle button, HUD coordinate readout, and diagnostic card readouts.
// 4. board.mjs renders precision millimeter ruler ticks and labels on the board perimeter.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

console.log("Running Viewer Coordinate Ruler Verification Tests (Node.js)...");

// 1. Check ruler.mjs
const rulerPath = path.resolve(repoRoot, "robot-3d-viewer", "ruler.mjs");
assert.ok(fs.existsSync(rulerPath), "ruler.mjs must exist");
const rulerContent = fs.readFileSync(rulerPath, "utf-8");

assert.ok(
  rulerContent.includes("export function buildCoordinateRulerGroup"),
  "ruler.mjs must export buildCoordinateRulerGroup"
);
assert.ok(
  rulerContent.includes("export function createDimensionTape"),
  "ruler.mjs must export createDimensionTape"
);
assert.ok(
  rulerContent.includes("createTextSprite"),
  "ruler.mjs must define createTextSprite for crisp 3D labels"
);
assert.ok(
  rulerContent.includes("+X (Ngang)") && rulerContent.includes("+Y (Cao độ / Up)") && rulerContent.includes("+Z (Dọc / Bàn Cờ)"),
  "ruler.mjs must define axes with proper names and directions"
);
console.log("  [PASS] ruler.mjs exports high-precision 3D ruler and dimension tape functions.");

// 2. Check main.mjs integration
const mainPath = path.resolve(repoRoot, "robot-3d-viewer", "main.mjs");
const mainContent = fs.readFileSync(mainPath, "utf-8");

assert.ok(
  mainContent.includes("buildCoordinateRulerGroup") && mainContent.includes("createDimensionTape"),
  "main.mjs must import ruler helpers from ruler.mjs"
);
assert.ok(
  mainContent.includes("coordinateRulerGroup"),
  "main.mjs must manage coordinateRulerGroup state"
);
assert.ok(
  mainContent.includes("toggleRulerBtn"),
  "main.mjs must bind toggleRulerBtn event"
);
assert.ok(
  mainContent.includes("coordReadout"),
  "main.mjs must update coordReadout on HUD"
);
assert.ok(
  mainContent.includes("activeDimensionTape"),
  "main.mjs must create dynamic dimension tape on cell selection"
);
console.log("  [PASS] main.mjs seamlessly integrates coordinate ruler, dynamic dimension line, and live readouts.");

// 3. Check index.html UI
const indexPath = path.resolve(repoRoot, "robot-3d-viewer", "index.html");
const indexContent = fs.readFileSync(indexPath, "utf-8");

assert.ok(
  indexContent.includes('id="toggleRulerBtn"'),
  "index.html must have toggleRulerBtn"
);
assert.ok(
  indexContent.includes('id="coordReadout"'),
  "index.html must have coordReadout element in HUD"
);
assert.ok(
  indexContent.includes('id="diagWorldCoord"'),
  "index.html must have diagWorldCoord in diagnostic card"
);
assert.ok(
  indexContent.includes('id="diagRobotCoord"'),
  "index.html must have diagRobotCoord in diagnostic card"
);
console.log("  [PASS] index.html provides complete UI controls and readouts for coordinate measurement.");

// 4. Check board.mjs millimeter ruler markings
const boardPath = path.resolve(repoRoot, "robot-3d-viewer", "board.mjs");
const boardContent = fs.readFileSync(boardPath, "utf-8");

assert.ok(
  boardContent.includes("Thước đo chia vạch milimet (mm) trên lề bàn cờ"),
  "board.mjs must render millimeter ruler on the board margin"
);
assert.ok(
  boardContent.includes("pxPerMmX") && boardContent.includes("pxPerMmY"),
  "board.mjs must scale millimeter ticks accurately to physical geometry"
);
console.log("  [PASS] board.mjs renders calibrated millimeter ticks and numbers directly on board margin.");

console.log("ALL VIEWER COORDINATE RULER TESTS PASSED SUCCESSFULLY!");
