import test from "node:test";
import assert from "node:assert/strict";

import { isFingerPartName } from "../../robot-3d-viewer/gripper_asset.mjs";

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
