import test from "node:test";
import assert from "node:assert/strict";

import { fingerDirection, fingerOffsetCadMm, isFingerPartName, parseGripperVisualAsset } from "../../robot-3d-viewer/gripper_asset.mjs";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

test("finger detection accepts the shipped assembly instance names", () => {
  // occt-import-js reports instances, not the bare STEP product name.
  for (const name of ["pinza", "pinza:3", "pinza:4", "  PINZA:12  "]) {
    assert.equal(isFingerPartName(name), true, String(name));
  }
});

test("finger detection rejects the other gripper parts", () => {
  for (const name of ["corpo", "blocco_griffe", "cremagliera:1", "pignone", "pinza_x", "", null, undefined]) {
    assert.equal(isFingerPartName(name), false, String(name));
  }
});

const here = path.dirname(fileURLToPath(import.meta.url));
const visualAsset = parseGripperVisualAsset(JSON.parse(
  readFileSync(path.join(here, "../../shared/gripper_visual_asset.json"), "utf8")));

test("closing the gripper narrows the gap between the two fingers", () => {
  const travelScale = 12; // VIRTUAL_GRIPPER_VISUAL_TRAVEL_SCALE in main.mjs
  const leftCad = -40;
  const rightCad = 40;
  const midX = (leftCad + rightCad) / 2;
  const left = fingerDirection(leftCad, midX);
  const right = fingerDirection(rightCad, midX);
  assert.equal(left, -1, "left finger must point outward");
  assert.equal(right, 1, "right finger must point outward");

  const gap = (closed) =>
    (rightCad + fingerOffsetCadMm(visualAsset, right, closed, travelScale)) -
    (leftCad + fingerOffsetCadMm(visualAsset, left, closed, travelScale));
  const open = gap(false);
  const shut = gap(true);
  assert.ok(shut < open, `closing must narrow the gap: closed ${shut} >= open ${open}`);
  assert.ok(Math.abs(open - shut) > 1, "the visual travel must be visible");
});
