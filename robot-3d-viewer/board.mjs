import * as THREE from "three";
import { fetchPhysicalGeometry, parsePhysicalGeometry } from "./geometry.mjs";
import { fetchStartLayout, parseStartLayout, START_LAYOUT, LABEL_RED, LABEL_BLACK, PIECE_TYPE_NAMES } from "./layout.mjs";

// Re-export layout for convenience
export { fetchStartLayout, parseStartLayout, START_LAYOUT, LABEL_RED, LABEL_BLACK, PIECE_TYPE_NAMES };

// ---------------------------------------------------------------------------
// SIMULATION SCENE PLACEMENT (NOT INTRINSIC PHYSICAL GEOMETRY)
// Canonical source: shared/virtual_fr3_scene.json
// ---------------------------------------------------------------------------
let _activeScenePlacement = {
  boardCenterX: 0.0,
  boardSurfaceY: 0.0105,
  boardCenterZ: 0.36,
};

export async function fetchScenePlacement(url = "/shared/virtual_fr3_scene.json") {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch scene placement from ${url}: HTTP ${response.status}`);
  }
  const data = await response.json();
  const worldCenter = data?.virtual_board_placement?.board_center_in_3d_world_m;
  if (!Array.isArray(worldCenter) || worldCenter.length !== 3) {
    throw new Error("Invalid virtual_board_placement.board_center_in_3d_world_m in scene config");
  }
  const placement = {
    boardCenterX: Number(worldCenter[0]),
    boardSurfaceY: Number(worldCenter[1]),
    boardCenterZ: Number(worldCenter[2]),
  };
  setScenePlacement(placement);
  return placement;
}

let _activeBoardGroup = null;

export function setScenePlacement(placement) {
  if (!placement) throw new Error("placement cannot be null or undefined");
  const centerWorld = placement.board_center_world_m || [
    placement.boardCenterX ?? 0.0,
    placement.boardSurfaceY ?? 0.0105,
    placement.boardCenterZ ?? 0.36
  ];
  _activeScenePlacement = {
    boardCenterX: Number(centerWorld[0]),
    boardSurfaceY: Number(centerWorld[1]),
    boardCenterZ: Number(centerWorld[2]),
    forwardShiftMm: Number(placement.forward_shift_mm ?? 0.0),
    safeTransitHeightMm: Number(placement.safe_transit_height_mm ?? 70.0),
    boardHeightOffsetMm: Number(placement.board_height_offset_mm ?? 0.0),
    placementVersion: Number(placement.placement_version ?? 1),
  };

  if (_activeBoardGroup) {
    _activeBoardGroup.position.set(
      _activeScenePlacement.boardCenterX,
      _activeScenePlacement.boardSurfaceY,
      _activeScenePlacement.boardCenterZ
    );
  }
}

export function getActiveBoardGroup() {
  return _activeBoardGroup;
}

export function getBoardVisualRoot() {
  return _activeBoardGroup;
}

export function getScenePlacement() {
  return _activeScenePlacement;
}

let _activeGeometry = null;

export function setBoardGeometry(geometry) {
  if (!geometry) throw new Error("geometry cannot be null or undefined");
  _activeGeometry = geometry;
}

export function getActiveGeometry() {
  if (!_activeGeometry) {
    throw new Error("Active geometry not set. Call setBoardGeometry() first.");
  }
  return _activeGeometry;
}

export function boardPointToXYZ(col, row, geometry = null) {
  const geo = geometry || getActiveGeometry();
  const placement = getScenePlacement();
  const colM = geo.cellM || 0.040;
  const rowM = geo.rowSpacingM || 0.040;
  // Under canonical 90 deg orientation:
  // Column axis (span -160mm to +160mm) -> +Z_world (-X_robot)
  // Row axis (span -180mm to +180mm)    -> +X_world (-Y_robot)
  const u = (Number(col) - 4.0) * colM;
  const v = (Number(row) - 4.5) * rowM;
  return new THREE.Vector3(
    placement.boardCenterX + v,
    placement.boardSurfaceY,
    placement.boardCenterZ + u
  );
}

export function computeBoardOrigin(geometry = null) {
  return boardPointToXYZ(0, 0, geometry);
}

// ---------------------------------------------------------------------------
// 1. VẼ LƯỚI BÀN CỜ LÊN CANVAS
// ---------------------------------------------------------------------------
function createBoardTexture(geometry = null) {
  const geo = geometry || getActiveGeometry();
  const canvas = document.createElement("canvas");
  // Canvas width maps along world X (row axis, 410 mm)
  // Canvas height maps along world Z (col axis, 367 mm)
  canvas.width = Math.round(1024 * (geo.outerLengthMm / geo.outerWidthMm)); // 1144 px
  canvas.height = 1024;
  const ctx = canvas.getContext("2d");

  // Nền gỗ sáng
  ctx.fillStyle = "#e3c796";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = "#1a1a1a";
  ctx.lineWidth = 5;

  // Lề dọc (dọc theo hàng, canvas width) & lề ngang (ngang theo cột, canvas height)
  const paddingX = Math.round(canvas.width * (geo.marginVerticalMm / geo.outerLengthMm));
  const paddingY = Math.round(canvas.height * (geo.marginHorizontalMm / geo.outerWidthMm));

  // Chia 9 khoảng hàng (10 hàng) và 8 khoảng cột (9 cột)
  const stepX = (canvas.width - paddingX * 2) / (geo.rows - 1);
  const stepY = (canvas.height - paddingY * 2) / (geo.columns - 1);

  const getX = (row) => paddingX + row * stepX;
  const getY = (col) => paddingY + col * stepY;

  // 1. Vẽ 10 đường hàng (nối col 0 đến col 8 ở mỗi row r)
  for (let r = 0; r < 10; r++) {
    ctx.beginPath();
    ctx.moveTo(getX(r), getY(0));
    ctx.lineTo(getX(r), getY(8));
    ctx.stroke();
  }

  // 2. Vẽ 9 đường cột (2 đường biên kéo dài, các đường bên trong ngắt ở Sông row 4 -> row 5)
  for (let c = 0; c < 9; c++) {
    if (c === 0 || c === 8) {
      ctx.beginPath();
      ctx.moveTo(getX(0), getY(c));
      ctx.lineTo(getX(9), getY(c));
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(getX(0), getY(c));
      ctx.lineTo(getX(4), getY(c));
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(getX(5), getY(c));
      ctx.lineTo(getX(9), getY(c));
      ctx.stroke();
    }
  }

  // 3. Đường chéo Cung Tướng Phe Đen (Hàng 0 đến 2, Cột 3 đến 5)
  ctx.beginPath();
  ctx.moveTo(getX(0), getY(3));
  ctx.lineTo(getX(2), getY(5));
  ctx.moveTo(getX(0), getY(5));
  ctx.lineTo(getX(2), getY(3));
  ctx.stroke();

  // 4. Đường chéo Cung Tướng Phe Đỏ (Hàng 7 đến 9, Cột 3 đến 5)
  ctx.beginPath();
  ctx.moveTo(getX(7), getY(3));
  ctx.lineTo(getX(9), getY(5));
  ctx.moveTo(getX(7), getY(5));
  ctx.lineTo(getX(9), getY(3));
  ctx.stroke();

  // Viền ngoài đôi bao quanh bàn cờ
  ctx.lineWidth = 10;
  ctx.strokeRect(
    paddingX - 12,
    paddingY - 12,
    canvas.width - paddingX * 2 + 24,
    canvas.height - paddingY * 2 + 24
  );

  // 5. Thước đo chia vạch milimet (mm) trên lề bàn cờ
  ctx.save();
  ctx.strokeStyle = "#4a2e18";
  ctx.fillStyle = "#3e2410";
  ctx.font = "bold 13px 'Segoe UI', Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  const playableW = geo.playableWidthMm || 320;
  const playableL = geo.playableLengthMm || 360;
  const pxPerMmX = (canvas.width - paddingX * 2) / playableL;
  const pxPerMmY = (canvas.height - paddingY * 2) / playableW;

  // Thước ngang dọc theo row (0 đến 360mm): biên trên & biên dưới canvas
  for (let mm = 0; mm <= playableL; mm += 1) {
    const x = paddingX + mm * pxPerMmX;
    if (mm % 40 === 0) {
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(x, paddingY - 12);
      ctx.lineTo(x, paddingY - 26);
      ctx.moveTo(x, canvas.height - paddingY + 12);
      ctx.lineTo(x, canvas.height - paddingY + 26);
      ctx.stroke();

      ctx.fillText(`${mm}mm`, x, paddingY - 34);
      ctx.fillText(`${mm}mm`, x, canvas.height - paddingY + 34);
    } else if (mm % 10 === 0) {
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, paddingY - 12);
      ctx.lineTo(x, paddingY - 21);
      ctx.moveTo(x, canvas.height - paddingY + 12);
      ctx.lineTo(x, canvas.height - paddingY + 21);
      ctx.stroke();
    } else if (mm % 2 === 0) {
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(x, paddingY - 12);
      ctx.lineTo(x, paddingY - 17);
      ctx.moveTo(x, canvas.height - paddingY + 12);
      ctx.lineTo(x, canvas.height - paddingY + 17);
      ctx.stroke();
    }
  }

  // Thước dọc dọc theo col (0 đến 320mm): biên trái & biên phải canvas
  for (let mm = 0; mm <= playableW; mm += 1) {
    const y = paddingY + mm * pxPerMmY;
    if (mm % 40 === 0) {
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(paddingX - 12, y);
      ctx.lineTo(paddingX - 26, y);
      ctx.moveTo(canvas.width - paddingX + 12, y);
      ctx.lineTo(canvas.width - paddingX + 26, y);
      ctx.stroke();

      ctx.textAlign = "right";
      ctx.fillText(`${mm}`, paddingX - 30, y);
      ctx.textAlign = "left";
      ctx.fillText(`${mm}`, canvas.width - paddingX + 30, y);
    } else if (mm % 10 === 0) {
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(paddingX - 12, y);
      ctx.lineTo(paddingX - 21);
      ctx.moveTo(canvas.width - paddingX + 12, y);
      ctx.lineTo(canvas.width - paddingX + 21);
      ctx.stroke();
    } else if (mm % 2 === 0) {
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(paddingX - 12, y);
      ctx.lineTo(paddingX - 17);
      ctx.moveTo(canvas.width - paddingX + 12, y);
      ctx.lineTo(canvas.width - paddingX + 17);
      ctx.stroke();
    }
  }
  ctx.restore();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

// ---------------------------------------------------------------------------
// 2. DỰNG BÀN CỜ 3D
// ---------------------------------------------------------------------------
export function buildBoardGrid(geometry = null) {
  const geo = geometry || getActiveGeometry();
  const group = new THREE.Group();
  group.name = "boardVisualRoot";
  group.userData = { isBoardVisualRoot: true, legacyName: "xiangqi-board" };

  // Under 90 deg orientation:
  // Length (410 mm) is along X_world; Width (367 mm) is along Z_world
  const meshWidth = geo.boardDepthM || 0.410;  // Length along X_world
  const meshDepth = geo.boardWidthM || 0.367;  // Width along Z_world
  const boardThickness = geo.boardThicknessM || 0.0105;

  const boardMaterial = new THREE.MeshLambertMaterial({
    map: createBoardTexture(geo),
  });

  const frameMaterial = new THREE.MeshLambertMaterial({
    color: 0x5c3317,
  });

  const placement = getScenePlacement();
  const center = new THREE.Vector3(
    placement.boardCenterX,
    placement.boardSurfaceY,
    placement.boardCenterZ
  );

  // 1. Khung viền ngoài (tọa độ local tương đối với tâm group)
  const outerFrame = new THREE.Mesh(
    new THREE.BoxGeometry(meshWidth + 0.02, boardThickness - 0.001, meshDepth + 0.02),
    frameMaterial
  );
  outerFrame.position.set(0, -boardThickness / 2 - 0.0005, 0);
  group.add(outerFrame);

  // 2. Mặt bàn cờ chính (tọa độ local tương đối với tâm group)
  const boardTop = new THREE.Mesh(
    new THREE.BoxGeometry(meshWidth, boardThickness, meshDepth),
    boardMaterial
  );
  boardTop.position.set(0, -boardThickness / 2, 0);
  boardTop.receiveShadow = true;
  group.add(boardTop);

  group.position.set(center.x, center.y, center.z);
  _activeBoardGroup = group;
  return group;
}

export function buildBoardSupport() {
  // Không dựng bệ đỡ nhân tạo, bàn cờ nằm sát sàn 1.05cm
  const supportGroup = new THREE.Group();
  supportGroup.name = "xiangqi-board-support";
  return supportGroup;
}

// ---------------------------------------------------------------------------
// 3. DỰNG QUÂN CỜ (BLACK ROW 0..4, RED ROW 5..9)
// ---------------------------------------------------------------------------
function makePieceTexture(label, side) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");

  // Nền gỗ của quân cờ
  ctx.fillStyle = "#ebd0a7";
  ctx.fillRect(0, 0, 256, 256);

  // Vòng viền tròn
  ctx.strokeStyle = side === "r" ? "#b82411" : "#24522e";
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.arc(128, 128, 110, 0, Math.PI * 2);
  ctx.stroke();

  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(128, 128, 102, 0, Math.PI * 2);
  ctx.stroke();

  // Xoay chữ dọc
  ctx.save();
  ctx.translate(128, 128);
  ctx.rotate(Math.PI / 2);

  ctx.fillStyle = side === "r" ? "#c4210b" : "#1f4a28";
  ctx.font = "bold 130px KaiTi, STKaiti, SimHei, serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, 0, 10);
  ctx.restore();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function makePieceMaterials(label, side) {
  const woodSideMaterial = new THREE.MeshLambertMaterial({
    color: 0xd6b383,
  });

  const topMaterial = new THREE.MeshLambertMaterial({
    map: makePieceTexture(label, side),
  });

  return [woodSideMaterial, topMaterial, woodSideMaterial];
}

export function buildPieces(geometry = null, layoutOrPieces = START_LAYOUT) {
  const geo = geometry || getActiveGeometry();
  const group = new THREE.Group();
  group.name = "xiangqi-pieces";
  const pieces = {};
  const radius = geo.pieceRadiusM;
  const height = geo.pieceHeightM;

  // Align cylinder axis with local Z to match PyBullet convention
  const cylinderGeometry = new THREE.CylinderGeometry(radius, radius, height, 32);
  cylinderGeometry.rotateX(Math.PI / 2);

  const counts = {};
  const list = layoutOrPieces || [];

  list.forEach((item, index) => {
    let col, row, type, side, canonicalId;
    if (Array.isArray(item)) {
      [col, row, type, side] = item;
      const sideName = side === "r" ? "red" : "black";
      const typeName = PIECE_TYPE_NAMES[type] || type;
      const key = `${sideName}_${typeName}`;
      const countIdx = counts[key] || 0;
      counts[key] = countIdx + 1;
      canonicalId = `${key}_${countIdx}`;
    } else {
      col = item.col;
      row = item.row;
      type = item.type;
      side = item.side;
      canonicalId = item.id;
    }

    const label = side === "r" ? LABEL_RED[type] : LABEL_BLACK[type];
    const mesh = new THREE.Mesh(cylinderGeometry, makePieceMaterials(label, side));
    const pos = boardPointToXYZ(col, row, geo);

    mesh.position.set(pos.x, pos.y + height / 2.0, pos.z);
    // Canonical upright piece orientation in 3d_world
    mesh.quaternion.set(-0.5, 0.5, 0.5, 0.5);
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    mesh.name = canonicalId;
    mesh.userData = { col, row, type, side, id: canonicalId };
    pieces[canonicalId] = mesh;
    // Also record legacy index alias for compatibility
    pieces[`${side}_${type}_${index}`] = mesh;
    group.add(mesh);
  });

  return { group, pieces };
}

export function updatePiecesFromWorldState(piecesGroup, piecesDict, piecesList) {
  if (!piecesDict || !Array.isArray(piecesList)) return;

  for (const p of piecesList) {
    const mesh = piecesDict[p.id];
    if (!mesh) continue;

    if (Array.isArray(p.pose_world) && p.pose_world.length >= 3) {
      mesh.position.set(p.pose_world[0], p.pose_world[1], p.pose_world[2]);
    }

    if (Array.isArray(p.orientation_quat_world) && p.orientation_quat_world.length >= 4) {
      mesh.quaternion.set(
        p.orientation_quat_world[0],
        p.orientation_quat_world[1],
        p.orientation_quat_world[2],
        p.orientation_quat_world[3]
      );
    }

    if (p.status === "OUT_OF_BOUNDS") {
      mesh.visible = false;
    } else {
      mesh.visible = true;
    }

    mesh.userData.status = p.status;
    mesh.userData.is_grasped = p.is_grasped;
    mesh.userData.board_col = p.board_col;
    mesh.userData.board_row = p.board_row;
  }
}

export function movePieceTo(mesh, col, row, geometry = null) {
  const geo = geometry || getActiveGeometry();
  const pos = boardPointToXYZ(col, row, geo);
  mesh.position.set(pos.x, mesh.position.y, pos.z);
  mesh.userData.col = col;
  mesh.userData.row = row;
}