// robot-3d-viewer/gripper_profile.mjs
// Single source of truth loader for virtual gripper profile in 3D viewer.
// Canonical source: shared/virtual_gripper_profile.json

export function parseGripperProfile(data) {
  if (!data || typeof data !== "object") {
    throw new Error("Invalid gripper profile payload: must be an object");
  }

  const version = Number(data.schema_version);
  if (!Number.isInteger(version) || version !== 1) {
    throw new Error(`Invalid schema_version: must be integer 1, got ${data.schema_version}`);
  }

  if (typeof data.status !== "string" || data.status.trim() === "") {
    throw new Error("Missing or empty 'status' in gripper profile");
  }

  if (typeof data.gripper_model !== "string" || data.gripper_model.trim() === "") {
    throw new Error("Missing or empty 'gripper_model' in gripper profile");
  }

  // Palm dimensions
  if (!data.palm || !Array.isArray(data.palm.dimensions_m) || data.palm.dimensions_m.length !== 3) {
    throw new Error("Invalid palm.dimensions_m: expected array of 3 numbers");
  }
  const palmDims = data.palm.dimensions_m.map(Number);
  if (palmDims.some((v) => !Number.isFinite(v) || v <= 0)) {
    throw new Error(`Invalid palm dimensions: ${JSON.stringify(palmDims)} (must be 3 positive finite numbers)`);
  }

  // Jaw dimensions
  if (!data.jaw || !Array.isArray(data.jaw.dimensions_m) || data.jaw.dimensions_m.length !== 3) {
    throw new Error("Invalid jaw.dimensions_m: expected array of 3 numbers");
  }
  const jawDims = data.jaw.dimensions_m.map(Number);
  if (jawDims.some((v) => !Number.isFinite(v) || v <= 0)) {
    throw new Error(`Invalid jaw dimensions: ${JSON.stringify(jawDims)} (must be 3 positive finite numbers)`);
  }

  // Stroke
  if (!data.stroke || typeof data.stroke !== "object") {
    throw new Error("Missing stroke configuration in gripper profile");
  }
  const openWidth = Number(data.stroke.open_width_m);
  const closedWidth = Number(data.stroke.closed_width_m);
  if (!Number.isFinite(openWidth) || openWidth <= 0) {
    throw new Error(`Invalid stroke.open_width_m: ${data.stroke.open_width_m} (must be > 0)`);
  }
  if (!Number.isFinite(closedWidth) || closedWidth <= 0) {
    throw new Error(`Invalid stroke.closed_width_m: ${data.stroke.closed_width_m} (must be > 0)`);
  }
  if (openWidth <= closedWidth) {
    throw new Error(`Gripper stroke requires open_width_m (${openWidth}) > closed_width_m (${closedWidth})`);
  }
  const travelAxis = String(data.stroke.travel_axis || "").trim().toUpperCase();
  if (!["X", "Y", "Z"].includes(travelAxis)) {
    throw new Error(`Invalid stroke.travel_axis: ${data.stroke.travel_axis} (must be 'X', 'Y', or 'Z')`);
  }

  // TCP to grasp center
  if (!Array.isArray(data.tcp_to_grasp_center_m) || data.tcp_to_grasp_center_m.length !== 3) {
    throw new Error("Invalid tcp_to_grasp_center_m: expected array of 3 numbers");
  }
  const tcpToGraspCenter = data.tcp_to_grasp_center_m.map(Number);
  if (tcpToGraspCenter.some((v) => !Number.isFinite(v))) {
    throw new Error(`Invalid tcp_to_grasp_center_m values: ${JSON.stringify(tcpToGraspCenter)}`);
  }

  // Capture volume
  if (!data.capture_volume || typeof data.capture_volume !== "object") {
    throw new Error("Missing capture_volume configuration in gripper profile");
  }
  const xyRadius = Number(data.capture_volume.xy_radius_m);
  const zHalfHeight = Number(data.capture_volume.z_half_height_m);
  if (!Number.isFinite(xyRadius) || xyRadius <= 0) {
    throw new Error(`Invalid capture_volume.xy_radius_m: ${data.capture_volume.xy_radius_m} (must be > 0)`);
  }
  if (!Number.isFinite(zHalfHeight) || zHalfHeight <= 0) {
    throw new Error(`Invalid capture_volume.z_half_height_m: ${data.capture_volume.z_half_height_m} (must be > 0)`);
  }

  // Visual colors
  if (!data.visual || typeof data.visual !== "object") {
    throw new Error("Missing visual configuration in gripper profile");
  }
  const hexColorRegex = /^#[0-9a-fA-F]{6}$/;
  const colorHex = String(data.visual.color_hex || "").trim();
  const jawColorHex = String(data.visual.jaw_color_hex || "").trim();
  if (!hexColorRegex.test(colorHex)) {
    throw new Error(`Invalid visual.color_hex: '${data.visual.color_hex}' (must be valid #RRGGBB hex color)`);
  }
  if (!hexColorRegex.test(jawColorHex)) {
    throw new Error(`Invalid visual.jaw_color_hex: '${data.visual.jaw_color_hex}' (must be valid #RRGGBB hex color)`);
  }

  return Object.freeze({
    schemaVersion: version,
    status: data.status.trim(),
    gripperModel: data.gripper_model.trim(),
    palmDimensionsM: Object.freeze(palmDims),
    jawDimensionsM: Object.freeze(jawDims),
    openWidthM: openWidth,
    closedWidthM: closedWidth,
    travelAxis,
    tcpToGraspCenterM: Object.freeze(tcpToGraspCenter),
    captureVolume: Object.freeze({
      xyRadiusM: xyRadius,
      zHalfHeightM: zHalfHeight,
    }),
    colorHex,
    jawColorHex,
  });
}

export function computeProceduralGripperParameters(profile) {
  if (!profile) {
    throw new Error("Virtual gripper profile is required to compute parameters");
  }
  return Object.freeze({
    palmDimensionsM: profile.palmDimensionsM,
    jawDimensionsM: profile.jawDimensionsM,
    openWidthM: profile.openWidthM,
    closedWidthM: profile.closedWidthM,
    travelAxis: profile.travelAxis,
    tcpToGraspCenterM: profile.tcpToGraspCenterM,
    colorHex: profile.colorHex,
    jawColorHex: profile.jawColorHex,
    palmCenterZ: profile.palmDimensionsM[2] / 2.0,
    jawCenterZ: profile.palmDimensionsM[2] + profile.jawDimensionsM[2] / 2.0,
    halfOpen: profile.openWidthM / 2.0,
    halfClosed: profile.closedWidthM / 2.0,
  });
}

export async function fetchVirtualGripperProfile(url = "/shared/virtual_gripper_profile.json") {
  if (typeof window !== "undefined" && window.fetch) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch ${url}: HTTP ${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    return parseGripperProfile(data);
  } else {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dir = path.dirname(fileURLToPath(import.meta.url));
    const filePath = path.resolve(dir, "../shared/virtual_gripper_profile.json");
    const raw = fs.readFileSync(filePath, "utf-8");
    return parseGripperProfile(JSON.parse(raw));
  }
}
