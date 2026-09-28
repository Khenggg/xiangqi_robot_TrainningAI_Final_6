// Find the closest playable intersection using the same placement transform
// that renders the board. This works when the board is moved or rotated.
export function nearestBoardIntersection(point, geometry, boardPointToXYZ, maxDistanceM = 0.03) {
  if (!point || !geometry || typeof boardPointToXYZ !== "function") return null;
  let closest = null;
  let bestDistanceSq = maxDistanceM * maxDistanceM;
  for (let row = 0; row < geometry.rows; row += 1) {
    for (let col = 0; col < geometry.columns; col += 1) {
      const cell = boardPointToXYZ(row, col, geometry);
      const dx = point.x - cell.x;
      const dz = point.z - cell.z;
      const distanceSq = dx * dx + dz * dz;
      if (distanceSq < bestDistanceSq) {
        bestDistanceSq = distanceSq;
        closest = { row, col };
      }
    }
  }
  return closest;
}

export function settledPieceCell(piece) {
  if (!piece) return null;
  // A carried, out-of-bounds, or grasped piece has no selectable board cell
  if (piece.status === "OUT_OF_BOUNDS" || piece.status === "ATTACHED" || piece.is_grasped) return null;
  const row = piece.nearest_row;
  const col = piece.nearest_col;
  const distance = piece.distance_to_nearest_intersection_m;
  if (!Number.isInteger(row) || !Number.isInteger(col)) return null;
  if (Number.isFinite(distance) && distance > 0.035) return null;
  return { row, col };
}
