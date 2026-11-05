// Explicit display-only mapping. No rigid calibration or motion authority.
export function inspectPhysicalBoardDisplay(packet) {
  if (packet?.calibration_space !== "TAUGHT_XY_DISPLAY_ONLY") return null;
  if (packet.motion_authority !== false || packet.coordinate_frame !== "robot_base" ||
      packet.position_unit !== "mm" || packet.T_robot_from_board != null ||
      !Number.isFinite(packet.board_surface_z_m)) {
    return { ok: false, reason: "Thiếu hợp đồng hiển thị R1–R4 chỉ đọc" };
  }
  const pts = ["R1", "R2", "R3", "R4"].map(n => packet.display_teaching_points_mm?.[n]);
  if (pts.some(p => !Array.isArray(p) || p.length !== 3 || !p.every(Number.isFinite))) {
    return { ok: false, reason: "Thiếu tọa độ R1–R4 hữu hạn" };
  }
  const crosses = pts.map((p, i) => {
    const b = pts[(i+1)%4], c = pts[(i+2)%4];
    return (b[0]-p[0])*(c[1]-b[1])-(b[1]-p[1])*(c[0]-b[0]);
  });
  if (!(crosses.every(c => c > 1e-6) || crosses.every(c => c < -1e-6))) {
    return { ok: false, reason: "Thứ tự R1–R4 bị chéo hoặc suy biến" };
  }
  return { ok: true };
}

export function displayCellWorld(points, surfaceZ, row, col) {
  const u = col/8, v = row/9;
  const {R1:a, R2:b, R3:c, R4:d} = points;
  const xy = [0,1].map(i => ((1-v)*((1-u)*a[i]+u*b[i])+v*((1-u)*d[i]+u*c[i]))/1000);
  return [-xy[1], surfaceZ, -xy[0]];
}
