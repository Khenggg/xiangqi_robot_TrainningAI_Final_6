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
    fingerTravelMm: Number(data.finger_travel_mm || 16.0),
    animationDurationMs: Number(data.animation_duration_ms || 220),
    cadFlangeOrigin: data.cad_flange_origin.map(Number),
    fingerSourceColorHex: data.finger_source_color_hex || "#694d3b",
    profiles: data.profiles,
  };
}
