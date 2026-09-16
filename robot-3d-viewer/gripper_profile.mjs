// robot-3d-viewer/gripper_profile.mjs
// Single source of truth loader for virtual gripper profile in 3D viewer.
// Canonical source: shared/virtual_gripper_profile.json

export function parseGripperProfile(data) {
  if (!data || typeof data !== "object") {
    throw new Error("Invalid gripper profile payload: must be an object");
  }

  const version = Number(data.schema_version);
  if (!Number.isInteger(version) || version < 1) {
    throw new Error(`Invalid schema_version: must be an integer >= 1, got ${data.schema_version}`);
  }

  if (!data.palm || !Array.isArray(data.palm.dimensions_m) || data.palm.dimensions_m.length !== 3) {
    throw new Error("Invalid palm.dimensions_m: expected array of 3 numbers");
  }
  const palmDims = data.palm.dimensions_m.map(Number);
  if (palmDims.some((v) => !Number.isFinite(v) || v <= 0)) {
    throw new Error(`Invalid palm dimensions: ${JSON.stringify(palmDims)}`);
  }

  if (!data.jaw || !Array.isArray(data.jaw.dimensions_m) || data.jaw.dimensions_m.length !== 3) {
    throw new Error("Invalid jaw.dimensions_m: expected array of 3 numbers");
  }
  const jawDims = data.jaw.dimensions_m.map(Number);
  if (jawDims.some((v) => !Number.isFinite(v) || v <= 0)) {
    throw new Error(`Invalid jaw dimensions: ${JSON.stringify(jawDims)}`);
  }

  if (!data.stroke || typeof data.stroke !== "object") {
    throw new Error("Missing stroke configuration in gripper profile");
  }
  const openWidth = Number(data.stroke.open_width_m);
  const closedWidth = Number(data.stroke.closed_width_m);
  if (!Number.isFinite(openWidth) || openWidth <= 0) {
    throw new Error(`Invalid stroke.open_width_m: ${data.stroke.open_width_m}`);
  }
  if (!Number.isFinite(closedWidth) || closedWidth <= 0 || closedWidth >= openWidth) {
    throw new Error(`Invalid stroke.closed_width_m: ${data.stroke.closed_width_m} (must be > 0 and < open_width_m)`);
  }
  const travelAxis = String(data.stroke.travel_axis || "X").toUpperCase();

  const visual = data.visual || {};
  const colorHex = visual.color_hex || "#556070";
  const jawColorHex = visual.jaw_color_hex || "#2a3240";

  return Object.freeze({
    schemaVersion: version,
    gripperModel: data.gripper_model || "PROCEDURAL_2JAW_V1",
    palmDimensionsM: Object.freeze(palmDims),
    jawDimensionsM: Object.freeze(jawDims),
    openWidthM: openWidth,
    closedWidthM: closedWidth,
    travelAxis,
    tcpToGraspCenterM: Object.freeze((data.tcp_to_grasp_center_m || [0, 0, 0.035]).map(Number)),
    captureVolume: Object.freeze({
      xyRadiusM: Number(data.capture_volume?.xy_radius_m || 0.016),
      zHalfHeightM: Number(data.capture_volume?.z_half_height_m || 0.012),
    }),
    colorHex,
    jawColorHex,
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
