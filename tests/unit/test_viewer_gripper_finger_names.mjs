import test from "node:test";
import assert from "node:assert/strict";

import {
  VIRTUAL_CLOSED_CONTACT_CAD_MM,
  fingerClosedShift,
  fingerDirection,
  fingerOffsetCadMm,
  fingerOpenShift,
  heldContactCadMm,
  isFingerPartName,
  parseGripperVisualAsset,
  pieceDiameterCadMm,
} from "../../robot-3d-viewer/gripper_asset.mjs";
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

test("virtual clamp lands on the contact gap, not on a 0.34 mm stroke", () => {
  // Two symmetric jaws around the assembly centre, as occt reports them.
  const halfWidth = 5;
  const midX = 0;
  const leftCenter = -22;
  const rightCenter = 22;
  const leftSide = fingerDirection(leftCenter, midX);
  const rightSide = fingerDirection(rightCenter, midX);
  const leftShift = fingerClosedShift({ localCenterX: leftCenter, halfWidth, side: leftSide, midX });
  const rightShift = fingerClosedShift({ localCenterX: rightCenter, halfWidth, side: rightSide, midX });

  const leftInnerFace = leftCenter + leftShift + halfWidth;
  const rightInnerFace = rightCenter + rightShift - halfWidth;
  const gap = rightInnerFace - leftInnerFace;

  assert.ok(Math.abs(gap - 2 * VIRTUAL_CLOSED_CONTACT_CAD_MM) < 1e-9,
    `inner faces must end ${2 * VIRTUAL_CLOSED_CONTACT_CAD_MM} CAD mm apart, got ${gap}`);
  assert.ok(gap < 2 * Math.abs(leftCenter),
    "the clamped gap must be much smaller than the CAD separation");
});

test("virtual open shift spreads the fingers outward", () => {
  assert.equal(fingerOpenShift(visualAsset, -1), -visualAsset.fingerOpenInsetMm);
  assert.equal(fingerOpenShift(visualAsset, 1), visualAsset.fingerOpenInsetMm);
});

test("a held piece stops the jaws on its surface instead of inside it", () => {
  const scaleToM = visualAsset.scaleToM;
  const pieceCad = pieceDiameterCadMm(22.5, scaleToM);          // shared/physical_geometry.json
  assert.ok(Math.abs(pieceCad - 28.125) < 1e-9, `piece is ${pieceCad} CAD units`);
  const contact = heldContactCadMm(22.5, scaleToM);
  const gapWithPiece = contact * 2;
  assert.ok(gapWithPiece > pieceCad,
    `jaws must clear the piece: gap ${gapWithPiece} > piece ${pieceCad}`);
  assert.ok(gapWithPiece - pieceCad < 2,
    "the jaws should touch the piece, not hover far from it");
  assert.ok(gapWithPiece > VIRTUAL_CLOSED_CONTACT_CAD_MM * 2,
    "gripping a piece must open wider than an empty clamp");
});
