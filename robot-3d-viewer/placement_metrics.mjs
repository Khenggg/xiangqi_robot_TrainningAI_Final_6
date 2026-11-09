// Read-only viewer geometry. All lengths at this boundary are metres unless
// explicitly named Mm; robot -> viewer is (-robot_y, robot_z, -robot_x).
import { displayCellWorld } from "./physical_board_display.mjs";

export function placementTransform(placement) {
  const T = placement?.TRobotFromBoard ?? placement?.T_robot_from_board;
  if (!Array.isArray(T) || T.length !== 4 || T.some(row => !Array.isArray(row) || row.length !== 4 || !row.every(Number.isFinite))) return null;
  if (T[3].some((value, i) => Math.abs(value - (i === 3 ? 1 : 0)) > 1e-6)) return null;
  // A scaled/sheared matrix is not a rigid calibration.
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
    const dot = T.slice(0, 3).reduce((sum, row) => sum + row[i] * row[j], 0);
    if (Math.abs(dot - (i === j ? 1 : 0)) > 1e-4) return null;
  }
  const det = T[0][0] * (T[1][1] * T[2][2] - T[1][2] * T[2][1])
    - T[0][1] * (T[1][0] * T[2][2] - T[1][2] * T[2][0])
    + T[0][2] * (T[1][0] * T[2][1] - T[1][1] * T[2][0]);
  if (Math.abs(det - 1) > 1e-4) return null;
  return T.map(row => [...row]);
}

export function placementCellWorld(placement, geometry, row, col) {
  const points = placement?.displayPoints ?? placement?.display_teaching_points_mm;
  const surface = placement?.boardSurfaceY ?? placement?.board_surface_z_m;
  if (points && Number.isFinite(surface)) return displayCellWorld(points, surface, row, col);
  const T = placementTransform(placement);
  if (!T || !geometry) return null;
  const u = (col - (geometry.columns - 1) / 2) * geometry.cellM;
  const v = (row - (geometry.rows - 1) / 2) * geometry.rowSpacingM;
  const robot = T.slice(0, 3).map(axis => axis[0] * u + axis[1] * v + axis[3]);
  return [-robot[1], robot[2], -robot[0]];
}

function axisName(axis) {
  const dominant = axis.findIndex(value => Math.abs(value) > 0.9999);
  if (dominant >= 0) return `${axis[dominant] >= 0 ? "+" : "-"}${"XYZ"[dominant]}_robot`;
  return `(${axis.map(value => value.toFixed(3)).join(", ")})_robot`;
}

export function placementAxisLabel(placement) {
  const T = placementTransform(placement);
  if (!T) return "Hướng trục chưa xác minh";
  return `col=${axisName(T.slice(0, 3).map(row => row[0]))}, row=${axisName(T.slice(0, 3).map(row => row[1]))}`;
}

export function formatMetric(value) {
  return Number.isFinite(value) ? `${value.toFixed(1)} mm` : "—";
}

function unknown(reason) {
  return Object.fromEntries([
    ...["D_far_grasp", "D_far_app", "grasp_margin", "app_margin", "d_max", "H_max",
      "nearest_cell_distance_mm", "farthest_cell_distance_mm", "near_grid_depth_mm",
      "far_grid_depth_mm", "near_board_edge_distance_mm", "far_board_edge_distance_mm",
      "board_center_distance_mm"].map(key => [key, null]),
    ["known", false], ["pass", false], ["reason", reason],
  ]);
}

// Feasible interval for a displacement along an arbitrary unit board axis.
function reachInterval(base, axis, radiusMm) {
  const a = axis.reduce((sum, value) => sum + value * value, 0);
  const b = base.reduce((sum, value, i) => sum + value * axis[i], 0);
  const c = base.reduce((sum, value) => sum + value * value, 0) - radiusMm * radiusMm;
  const discriminant = b * b - a * c;
  if (discriminant < 0 || a <= 0) return null;
  const half = Math.sqrt(discriminant);
  return [(-b - half) / a, (-b + half) / a];
}

export function computePlacementMetrics(placement, geometry, toolLengthM, options = {}) {
  const T = placementTransform(placement);
  if (!T || placement?.displayPoints || placement?.calibration_space === "TAUGHT_XY_DISPLAY_ONLY") return unknown("Rigid board pose unavailable");
  if (!geometry || ![geometry.cellM, geometry.rowSpacingM, geometry.pieceHeightM,
    geometry.boardWidthM, geometry.boardDepthM, toolLengthM].every(value => Number.isFinite(value) && value > 0)) return unknown("Geometry or tool offset unavailable");
  if (![geometry.rows, geometry.columns].every(value => Number.isInteger(value) && value >= 2)) return unknown("Grid dimensions unavailable");
  const d = options.forwardShiftMm ?? placement.forwardShiftMm ?? placement.forward_shift_mm;
  const H = options.safeTransitHeightMm ?? placement.safeTransitHeightMm ?? placement.safe_transit_height_mm;
  const appliedD = placement.forwardShiftMm ?? placement.forward_shift_mm ?? 0;
  const yaw = options.yawDeg ?? placement.boardYawDeg ?? placement.board_yaw_deg;
  const appliedYaw = placement.boardYawDeg ?? placement.board_yaw_deg;
  const radius = options.reachRadiusMm ?? 650;
  if (![d, H, appliedD, yaw, appliedYaw, radius].every(Number.isFinite) || radius <= 0) return unknown("Placement parameters unavailable");
  // Remove the already-applied column-axis shift before previewing another d.
  const nominal = T.slice(0, 3).map(row => row[3] - appliedD / 1000 * row[0]);
  const delta = (yaw - appliedYaw) * Math.PI / 180;
  const cos = Math.cos(delta), sin = Math.sin(delta);
  for (let col = 0; col < 3; col++) {
    const x = T[0][col], y = T[1][col];
    T[0][col] = cos * x - sin * y;
    T[1][col] = sin * x + cos * y;
  }
  for (let axis = 0; axis < 3; axis++) T[axis][3] = nominal[axis] + d / 1000 * T[axis][0];
  if (options.surfaceZMm != null) {
    if (!Number.isFinite(options.surfaceZMm)) return unknown("Board surface unavailable");
    T[2][3] = options.surfaceZMm / 1000;
  }
  const point = (u, v, height = 0) => T.slice(0, 3).map(axis =>
    (axis[0] * u + axis[1] * v + axis[2] * height + axis[3]) * 1000);
  const columnAxis = T.slice(0, 3).map(row => row[0]);
  const normal = T.slice(0, 3).map(row => row[2]);
  let minGrid = Infinity, maxGrid = 0, minDepth = Infinity, maxDepth = 0;
  let maxGrasp = 0, maxApp = 0, nearestCell = null, farthestCell = null;
  let shiftLower = -20, shiftUpper = Infinity, heightLower = -Infinity, heightUpper = Infinity;
  for (let row = 0; row < geometry.rows; row++) for (let col = 0; col < geometry.columns; col++) {
    const u = (col - (geometry.columns - 1) / 2) * geometry.cellM;
    const v = (row - (geometry.rows - 1) / 2) * geometry.rowSpacingM;
    const p = point(u, v);
    const grasp = point(u, v, geometry.pieceHeightM / 2);
    const app = point(u, v, H / 1000);
    grasp[2] += toolLengthM * 1000; app[2] += toolLengthM * 1000;
    const grid = Math.hypot(p[0], p[1]);
    if (grid < minGrid) { minGrid = grid; nearestCell = [row, col]; }
    maxGrid = Math.max(maxGrid, grid);
    minDepth = Math.min(minDepth, Math.abs(p[0])); maxDepth = Math.max(maxDepth, Math.abs(p[0]));
    maxGrasp = Math.max(maxGrasp, Math.hypot(...grasp));
    const appDistance = Math.hypot(...app);
    if (appDistance > maxApp) { maxApp = appDistance; farthestCell = [row, col]; }
    for (const endpoint of [grasp, app]) {
      const shiftRange = reachInterval(endpoint.map((value, i) => value - d * columnAxis[i]), columnAxis, radius);
      if (shiftRange) { shiftLower = Math.max(shiftLower, shiftRange[0]); shiftUpper = Math.min(shiftUpper, shiftRange[1]); }
      else { shiftLower = Infinity; shiftUpper = -Infinity; }
    }
    const heightRange = reachInterval(app.map((value, i) => value - H * normal[i]), normal, radius);
    if (heightRange) { heightLower = Math.max(heightLower, heightRange[0]); heightUpper = Math.min(heightUpper, heightRange[1]); }
    else { heightLower = Infinity; heightUpper = -Infinity; }
  }
  const cornersX = [];
  for (const u of [-geometry.boardWidthM / 2, geometry.boardWidthM / 2])
    for (const v of [-geometry.boardDepthM / 2, geometry.boardDepthM / 2]) cornersX.push(point(u, v)[0]);
  const minX = Math.min(...cornersX), maxX = Math.max(...cornersX);
  return {
    known: true, pass: maxGrasp <= radius && maxApp <= radius && d >= -20,
    D_far_grasp: maxGrasp, D_far_app: maxApp,
    grasp_margin: radius - maxGrasp, app_margin: radius - maxApp,
    d_max: shiftLower <= shiftUpper ? shiftUpper : null,
    H_max: heightLower <= heightUpper && maxGrasp <= radius ? heightUpper : null,
    nearest_cell: nearestCell, farthest_cell: farthestCell,
    nearest_cell_distance_mm: minGrid, farthest_cell_distance_mm: maxGrid,
    near_grid_depth_mm: minDepth, far_grid_depth_mm: maxDepth,
    near_board_edge_distance_mm: minX <= 0 && maxX >= 0 ? 0 : Math.min(Math.abs(minX), Math.abs(maxX)),
    far_board_edge_distance_mm: Math.max(Math.abs(minX), Math.abs(maxX)),
    board_center_distance_mm: Math.abs(T[0][3] * 1000),
  };
}
