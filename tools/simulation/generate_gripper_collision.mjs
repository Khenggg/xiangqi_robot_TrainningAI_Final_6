// Regenerate the conservative PyBullet envelope from the exact STEP rendered by
// robot-3d-viewer/main.mjs. Install once: npm install --prefix .cad_tools --no-save occt-import-js@0.0.23
// Run at repository root: node tools/simulation/generate_gripper_collision.mjs
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const require = createRequire(import.meta.url);
const occtPath = require.resolve("occt-import-js", {
  paths: [root, join(root, ".cad_tools")],
});
const initOcct = require(occtPath);
const visualPath = join(root, "shared/gripper_visual_asset.json");
const profilePath = join(root, "shared/robot_profiles/fr3.json");
const gripperProfilePath = join(root, "shared/virtual_gripper_profile.json");
const visualBytes = readFileSync(visualPath);
const profileBytes = readFileSync(profilePath);
const gripperProfileBytes = readFileSync(gripperProfilePath);
const visual = JSON.parse(visualBytes);
const profile = JSON.parse(profileBytes);
const cfg = visual.profiles.fr3;
const stepPath = join(root, "robot-3d-viewer/assets/fr3_v6", visual.asset_file);
const stepBytes = readFileSync(stepPath);
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
if (visual.cad_units !== "millimeter" || Math.abs(cfg.mount_rotation_euler_rad[0] - Math.PI) > 1e-6 ||
    cfg.mount_rotation_euler_rad.slice(1).some((v) => Math.abs(v) > 1e-9) || cfg.mount_roll_rad !== 0) {
  throw new Error("Unsupported CAD mount transform; update generator before regenerating");
}
const scale = visual.scale_to_m;
const tcpLinkZ = cfg.robot_flange_origin_m[2] + profile.tool.canonical_tcp.flange_to_tcp_xyz_m[2];
const origin = visual.cad_flange_origin;
const target = cfg.flange_target_offset_m;
const occt = await initOcct();
const result = occt.ReadStepFile(new Uint8Array(stepBytes), {
  linearUnit: visual.cad_units,
  linearDeflectionType: "bounding_box_ratio",
  linearDeflection: 0.001,
  angularDeflection: 0.5,
});
if (!result.success || result.meshes.length < 3) throw new Error("STEP tessellation failed");

function transformPoint(values, i) {
  return [
    target[0] + (values[i] - origin[0]) * scale,
    target[1] - (values[i + 1] - origin[1]) * scale,
    target[2] - (values[i + 2] - origin[2]) * scale - tcpLinkZ,
  ];
}

function boxFor(mesh) {
  const values = mesh.attributes.position.array;
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < values.length; i += 3) {
    const point = transformPoint(values, i);
    for (let k = 0; k < 3; k++) {
      min[k] = Math.min(min[k], point[k]);
      max[k] = Math.max(max[k], point[k]);
    }
  }
  // Outward rounding ensures every tessellated triangle lies inside the box.
  const low = min.map((v) => Math.floor(v * 1e6) / 1e6);
  const high = max.map((v) => Math.ceil(v * 1e6) / 1e6);
  return {
    name: mesh.name,
    center_m: low.map((v, k) => (v + high[k]) / 2),
    half_extents_m: low.map((v, k) => (high[k] - v) / 2),
  };
}

const fixed = [], fingers = [];
for (const mesh of result.meshes) {
  const box = boxFor(mesh);
  if (mesh.name === "pinza") {
    const values = mesh.attributes.position.array;
    const vertices = [];
    const seen = new Set();
    for (let i = 0; i < values.length; i += 3) {
      const point = transformPoint(values, i);
      const key = point.map((v) => v.toFixed(9)).join(",");
      if (!seen.has(key)) {
        seen.add(key);
        vertices.push(point);
      }
    }
    fingers.push({ ...box, vertices_m: vertices });
  } else {
    fixed.push(box);
  }
}
if (fingers.length !== 2) throw new Error(`Expected two pinza meshes, got ${fingers.length}`);
fingers.sort((a, b) => a.center_m[0] - b.center_m[0]);
const collarHeight = target[2] - cfg.robot_flange_origin_m[2];
if (collarHeight <= 0) throw new Error("Adapter collar height must be positive");
fixed.push({
  name: "viewer_adapter_collar",
  center_m: [0, 0, cfg.robot_flange_origin_m[2] + collarHeight / 2 - tcpLinkZ],
  half_extents_m: [0.033, 0.033, collarHeight / 2],
});
const output = {
  schema_version: 2,
  source_step_sha256: sha(stepBytes),
  source_visual_sha256: sha(visualBytes),
  source_profile_sha256: sha(profileBytes),
  source_gripper_profile_sha256: sha(gripperProfileBytes),
  reference_frame: "canonical_tcp_at_open_jaws",
  generation_note: "Outward rounded component AABBs for fixed parts; convex hulls of exact STEP vertices for moving fingers. Both enclose tessellated visual geometry.",
  finger_travel_m: visual.finger_travel_mm * scale,
  fixed_boxes: fixed,
  finger_boxes: fingers,
};
writeFileSync(join(root, "shared/gripper_collision_asset.json"), `${JSON.stringify(output, null, 2)}\n`);
console.log(`wrote ${fixed.length} fixed boxes and ${fingers.length} moving finger boxes`);
