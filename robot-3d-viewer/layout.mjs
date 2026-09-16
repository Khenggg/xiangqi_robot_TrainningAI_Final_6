// robot-3d-viewer/layout.mjs
// Single source of truth loader for start layout in 3D viewer.
// Canonical source: shared/xiangqi_start_layout.json
//
// Project convention:
//   Black (Robot): row 0..4  (row 0 is Black backline)
//   Red (Human):   row 5..9  (row 9 is Red backline)

export const LABEL_RED = Object.freeze({
  k: "帥",
  a: "仕",
  b: "相",
  n: "馬",
  r: "車",
  c: "砲",
  p: "兵",
});

export const LABEL_BLACK = Object.freeze({
  k: "將",
  a: "士",
  b: "象",
  n: "馬",
  r: "車",
  c: "炮",
  p: "卒",
});

export const PIECE_TYPE_NAMES = Object.freeze({
  r: "rook",
  n: "knight",
  b: "elephant",
  a: "advisor",
  k: "king",
  c: "cannon",
  p: "pawn",
});

export function parseStartLayout(data) {
  if (!data || typeof data !== "object") {
    throw new Error("Invalid start layout payload: must be an object");
  }
  const version = Number(data.schema_version);
  if (!Number.isInteger(version) || version < 1) {
    throw new Error(`Invalid schema_version: must be an integer >= 1, got ${data.schema_version}`);
  }
  if (!Array.isArray(data.pieces) || data.pieces.length !== 32) {
    throw new Error(`Start layout must contain exactly 32 pieces, got ${data.pieces?.length}`);
  }

  const pieces = [];
  const tupleLayout = [];
  const seenIds = new Set();
  const seenPositions = new Set();

  for (const p of data.pieces) {
    if (!p || typeof p.id !== "string" || !p.id.trim()) {
      throw new Error(`Piece missing valid id: ${JSON.stringify(p)}`);
    }
    if (seenIds.has(p.id)) {
      throw new Error(`Duplicate piece ID: ${p.id}`);
    }
    seenIds.add(p.id);

    if (p.side !== "b" && p.side !== "r") {
      throw new Error(`Piece ${p.id} has invalid side '${p.side}', expected 'b' or 'r'`);
    }
    if (!LABEL_RED[p.type] && !LABEL_BLACK[p.type]) {
      throw new Error(`Piece ${p.id} has invalid type '${p.type}'`);
    }

    const col = Number(p.col);
    const row = Number(p.row);
    if (!Number.isInteger(col) || col < 0 || col > 8) {
      throw new Error(`Piece ${p.id} col out of range [0, 8]: ${p.col}`);
    }
    if (!Number.isInteger(row) || row < 0 || row > 9) {
      throw new Error(`Piece ${p.id} row out of range [0, 9]: ${p.row}`);
    }

    const posKey = `${col},${row}`;
    if (seenPositions.has(posKey)) {
      throw new Error(`Duplicate piece position at (${col}, ${row}) for ${p.id}`);
    }
    seenPositions.add(posKey);

    pieces.push(Object.freeze({
      id: p.id,
      side: p.side,
      type: p.type,
      col,
      row,
    }));
    tupleLayout.push(Object.freeze([col, row, p.type, p.side]));
  }

  Object.defineProperty(pieces, "tupleLayout", {
    value: Object.freeze(tupleLayout),
    enumerable: false,
  });

  return Object.freeze(pieces);
}

export async function fetchStartLayout(url = "/shared/xiangqi_start_layout.json") {
  if (typeof window !== "undefined" && window.fetch) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch ${url}: HTTP ${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    return parseStartLayout(data);
  } else {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dir = path.dirname(fileURLToPath(import.meta.url));
    const filePath = path.resolve(dir, "../shared/xiangqi_start_layout.json");
    const raw = fs.readFileSync(filePath, "utf-8");
    return parseStartLayout(JSON.parse(raw));
  }
}

// In Node.js environments (such as unit test test_board_layout.py), dynamically load
// START_LAYOUT from shared/xiangqi_start_layout.json without hardcoding it in this file.
let _nodeLayout = null;
let _nodeLayoutError = null;
if (typeof window === "undefined") {
  try {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dir = path.dirname(fileURLToPath(import.meta.url));
    const filePath = path.resolve(dir, "../shared/xiangqi_start_layout.json");
    const raw = fs.readFileSync(filePath, "utf-8");
    const parsed = parseStartLayout(JSON.parse(raw));
    _nodeLayout = parsed.tupleLayout;
  } catch (err) {
    _nodeLayoutError = err;
    console.error("[LAYOUT] Failed to load canonical xiangqi_start_layout.json in Node environment:", err);
    throw err;
  }
}

export const START_LAYOUT = _nodeLayout;
export const NODE_LAYOUT_ERROR = _nodeLayoutError;
