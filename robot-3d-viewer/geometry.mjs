// robot-3d-viewer/geometry.mjs
// Single source of truth loader for physical geometry in 3D viewer.

export async function fetchPhysicalGeometry() {
  if (typeof window !== "undefined" && window.fetch) {
    const response = await fetch("/shared/physical_geometry.json");
    if (!response.ok) {
      throw new Error(
        `Failed to fetch /shared/physical_geometry.json: HTTP ${response.status} ${response.statusText}`
      );
    }
    const data = await response.json();
    return parsePhysicalGeometry(data);
  } else {
    // Node.js test or build environment
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dir = path.dirname(fileURLToPath(import.meta.url));
    const filePath = path.resolve(dir, "../shared/physical_geometry.json");
    const raw = fs.readFileSync(filePath, "utf-8");
    return parsePhysicalGeometry(JSON.parse(raw));
  }
}

export function parsePhysicalGeometry(data) {
  if (!data || !data.board || !data.piece) {
    throw new Error("Invalid physical geometry payload: missing 'board' or 'piece'");
  }
  if (data.unit !== "mm") {
    throw new Error(`Expected unit 'mm', found '${data.unit}'`);
  }

  const mmToM = 0.001;
  const outerWidthMm = Number(data.board.outer_width);
  const outerLengthMm = Number(data.board.outer_length);
  const columns = Number(data.board.columns);
  const rows = Number(data.board.rows);
  const columnSpacingMm = Number(data.board.column_spacing);
  const rowSpacingMm = Number(data.board.row_spacing);

  const pieceDiameterMm = Number(data.piece.diameter);
  const pieceHeightMm = Number(data.piece.height);

  // Derived in mm
  const playableGridWidthMm = (columns - 1) * columnSpacingMm; // 320 mm
  const playableGridLengthMm = (rows - 1) * rowSpacingMm;     // 360 mm
  const marginHorizontalMm = (outerWidthMm - playableGridWidthMm) / 2.0; // 23.5 mm
  const marginVerticalMm = (outerLengthMm - playableGridLengthMm) / 2.0;   // 25.0 mm

  return Object.freeze({
    unit: "mm",
    // Raw measured values in mm
    outerWidthMm,
    outerLengthMm,
    columns,
    rows,
    columnSpacingMm,
    rowSpacingMm,
    pieceDiameterMm,
    pieceHeightMm,
    playableGridWidthMm,
    playableGridLengthMm,
    marginHorizontalMm,
    marginVerticalMm,

    // Converted to Three.js scene units (meters)
    boardWidthM: outerWidthMm * mmToM,          // 0.367 m
    boardDepthM: outerLengthMm * mmToM,          // 0.410 m
    cellM: columnSpacingMm * mmToM,              // 0.040 m
    rowSpacingM: rowSpacingMm * mmToM,          // 0.040 m
    playableWidthM: playableGridWidthMm * mmToM, // 0.320 m
    playableDepthM: playableGridLengthMm * mmToM,// 0.360 m
    marginXM: marginHorizontalMm * mmToM,        // 0.0235 m
    marginYM: marginVerticalMm * mmToM,          // 0.0250 m
    pieceRadiusM: (pieceDiameterMm / 2.0) * mmToM, // 0.01125 m
    pieceHeightM: pieceHeightMm * mmToM,           // 0.00943 m
  });
}
