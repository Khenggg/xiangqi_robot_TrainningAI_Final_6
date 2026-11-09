// Validation and loader for CAD STEP gripper visual asset configuration
// Canonical source: shared/gripper_visual_asset.json

export async function fetchGripperVisualAsset(url = "/shared/gripper_visual_asset.json") {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load ${url}: HTTP ${res.status}`);
  }
  const data = await res.json();
  return parseGripperVisualAsset(data);
}

export function parseGripperVisualAsset(data) {
  if (!data || typeof data !== "object") {
    throw new Error("Gripper visual asset config must be an object");
  }
  if (data.schema_version !== 1) {
    throw new Error(`Unsupported schema_version: ${data.schema_version} (expected 1)`);
  }
  if (!data.status || typeof data.status !== "string" || !data.status.trim()) {
    throw new Error("Missing required non-empty 'status'");
  }
  if (!data.asset_file || typeof data.asset_file !== "string" || !data.asset_file.trim()) {
    throw new Error("Missing required non-empty 'asset_file'");
  }
  if (!Number.isFinite(data.scale_to_m) || data.scale_to_m <= 0) {
    throw new Error(`Invalid 'scale_to_m': ${data.scale_to_m} (must be positive finite number)`);
  }
  const openInset = data.finger_open_inset_mm ?? 0;
  const fingerTravel = data.finger_travel_mm ?? 16.0;
  if (!Number.isFinite(openInset) || openInset < 0) {
    throw new Error("Invalid 'finger_open_inset_mm': expected nonnegative finite number");
  }
  if (!Number.isFinite(fingerTravel) || fingerTravel <= 0) {
    throw new Error("Invalid 'finger_travel_mm': expected positive finite number");
  }
  if (
    !Array.isArray(data.cad_flange_origin) ||
    data.cad_flange_origin.length !== 3 ||
    !data.cad_flange_origin.every(Number.isFinite)
  ) {
    throw new Error("Invalid 'cad_flange_origin': must be 3 finite numbers");
  }
  if (!data.profiles || typeof data.profiles !== "object" || !data.profiles.fr3) {
    throw new Error("Missing required 'profiles.fr3' mapping");
  }

  for (const [pid, pdata] of Object.entries(data.profiles)) {
    if (!pdata || typeof pdata !== "object") {
      throw new Error(`Profile '${pid}' entry must be an object`);
    }
    for (const key of ["mount_offset_m", "mount_rotation_euler_rad", "flange_target_offset_m"]) {
      const v = pdata[key];
      if (!Array.isArray(v) || v.length !== 3 || !v.every(Number.isFinite)) {
        throw new Error(`Profile '${pid}' invalid '${key}': must be 3 finite numbers`);
      }
    }
    if (!Number.isFinite(pdata.mount_roll_rad)) {
      throw new Error(`Profile '${pid}' invalid 'mount_roll_rad': must be finite number`);
    }
  }

  return {
    schemaVersion: data.schema_version,
    status: data.status,
    assetFile: data.asset_file,
    assetBasePath: data.asset_base_path || "./assets/fr3_v6/",
    scaleToM: Number(data.scale_to_m),
    cadUnits: data.cad_units || "millimeter",
    fingerOpenInsetMm: openInset,
    fingerTravelMm: fingerTravel,
    animationDurationMs: Number(data.animation_duration_ms || 220),
    cadFlangeOrigin: data.cad_flange_origin.map(Number),
    fingerSourceColorHex: data.finger_source_color_hex || "#694d3b",
    profiles: data.profiles,
  };
}

export function fingerOffsetCadMm(asset, direction, closed, travelScale = 1) {
  const travel = asset.fingerTravelMm * Number(travelScale || 1);
  return direction * (asset.fingerOpenInsetMm + (closed ? -travel : 0));
}

/**
 * True when a STEP mesh is one of the two parallel fingers.
 *
 * occt-import-js reports assembly instance names, not the bare product name:
 * the shipped assembly yields "pinza:3" and "pinza:4", so an exact match on
 * "pinza" finds nothing and the jaws silently stop animating.
 */
export function isFingerPartName(name) {
  return /^pinza(?::\d+)?$/i.test(String(name ?? "").trim());
}

/**
 * Outward unit direction for one finger, given the pair's centre.
 *
 * fingerOffsetCadMm() subtracts the travel when the gripper closes, so the
 * direction must point away from the centre: subtracting then pulls each finger
 * inward and the gap narrows. Pointing inward inverts the animation and the
 * jaws spread apart on a clamp command.
 */
export function fingerDirection(centerX, midX) {
  return Number(centerX) < Number(midX) ? -1 : 1;
}

/**
 * Virtual clamp target: the inner faces stop this far apart (CAD millimetres).
 *
 * The shipped STEP has a real stroke of only 0.344 mm per finger, so animating
 * by travel (even x12) moves the jaws ~6 mm inside a ~40 mm opening and still
 * looks open. The virtual pose therefore targets a gap instead of a stroke.
 */
export const VIRTUAL_CLOSED_CONTACT_CAD_MM = 2;

export function fingerOpenShift(asset, side) {
  return Number(side) * asset.fingerOpenInsetMm;
}

export function fingerClosedShift({ localCenterX, halfWidth, side, midX,
                                    contact = VIRTUAL_CLOSED_CONTACT_CAD_MM }) {
  const innerFace = Number(localCenterX) - Number(side) * Number(halfWidth);
  return (Number(midX) + Number(side) * contact) - innerFace;
}


