// A live board matrix must place the same grid origin and taught corners that
// the backend advertises. A mismatch must not silently rotate the 3D board.
export function inspectBoardPlacementPacket(packet, cellM = 0.04) {
  const T = packet?.T_robot_from_board;
  if (T == null) return { ok: true };
  if (!Array.isArray(T) || T.length !== 4 ||
      T.some((row) => !Array.isArray(row) || row.length !== 4 ||
        row.some((value) => !Number.isFinite(value)))) {
    return { ok: false, reason: "Ma trận bàn cờ không hợp lệ" };
  }
  if (!Number.isFinite(cellM) || cellM <= 0) {
    return { ok: false, reason: "Bước ô bàn cờ không hợp lệ" };
  }
  if (T[3].some((value, i) => Math.abs(value - (i === 3 ? 1 : 0)) > 1e-8)) {
    return { ok: false, reason: "Ma trận bàn cờ thiếu hàng đồng nhất chuẩn" };
  }
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      const dot = T[0][i] * T[0][j] + T[1][i] * T[1][j] + T[2][i] * T[2][j];
      if (Math.abs(dot - (i === j ? 1 : 0)) > 1e-4) {
        return { ok: false, reason: "Ma trận bàn cờ không phải phép quay cứng" };
      }
    }
  }
  const det = T[0][0] * (T[1][1] * T[2][2] - T[1][2] * T[2][1])
    - T[0][1] * (T[1][0] * T[2][2] - T[1][2] * T[2][0])
    + T[0][2] * (T[1][0] * T[2][1] - T[1][1] * T[2][0]);
  if (Math.abs(det - 1) > 1e-4) {
    return { ok: false, reason: "Ma trận bàn cờ đảo chiều hệ tọa độ" };
  }
  const point = (u, v) => [0, 1, 2].map((i) => T[i][0] * u + T[i][1] * v + T[i][3]);
  const distanceMm = (a, b) => Math.hypot(...a.map((v, i) => v - b[i])) * 1000;
  const origin = packet.grid_origin_robot_m;
  if (!Array.isArray(origin) || origin.length !== 3 || !origin.every(Number.isFinite)) {
    return { ok: false, reason: "Thiếu gốc lưới robot_base để kiểm tra ma trận" };
  }
  const originErrorMm = distanceMm(point(-4 * cellM, -4.5 * cellM), origin);
  if (originErrorMm > 2) {
    return { ok: false, reason: `Ma trận và gốc lưới lệch ${originErrorMm.toFixed(1)} mm` };
  }
  const corners = packet.teaching_points;
  if (corners) {
    const local = {
      R1: [-4 * cellM, -4.5 * cellM],
      R2: [4 * cellM, -4.5 * cellM],
      R3: [4 * cellM, 4.5 * cellM],
      R4: [-4 * cellM, 4.5 * cellM],
    };
    for (const [name, [u, v]] of Object.entries(local)) {
      const measuredMm = corners[name];
      if (!Array.isArray(measuredMm) || measuredMm.length !== 3 || !measuredMm.every(Number.isFinite)) {
        return { ok: false, reason: `Thiếu điểm dạy ${name}` };
      }
      const errorMm = distanceMm(point(u, v), measuredMm.map((value) => value / 1000));
      if (errorMm > 5) {
        return { ok: false, reason: `${name} lệch ${errorMm.toFixed(1)} mm so với ma trận` };
      }
    }
  }
  return { ok: true };
}

export function canSendLiveCommand(source, placementValid, command) {
  return source !== "PHYSICAL" || placementValid === true ||
    command === "GET_BOARD_TEACHING_POINTS";
}
