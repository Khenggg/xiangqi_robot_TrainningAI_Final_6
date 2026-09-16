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

export function computeBoardOrigin(geometry = null) {
  const geo = geometry || getActiveGeometry();
  const placement = getScenePlacement();
  // Under canonical rotation R, X_world = -Y_robot.
  // Col 0 (Y_robot = -0.16m) maps to X_world = +0.16m (boardCenterX + playableWidthM / 2.0).
  // Row 0 (X_robot = -0.18m) maps to Z_world = +0.18m (boardCenterZ - playableDepthM / 2.0).
  return new THREE.Vector3(
    placement.boardCenterX + geo.playableWidthM / 2.0,
    placement.boardSurfaceY,
    placement.boardCenterZ - geo.playableDepthM / 2.0
  );
}

export function boardPointToXYZ(col, row, geometry = null) {
  const geo = geometry || getActiveGeometry();
  const origin = computeBoardOrigin(geo);
  // col increases (+Y in robot base) -> X_world decreases (-X direction)
  // row increases (-X in robot base) -> Z_world increases (+Z direction)
  return new THREE.Vector3(
    origin.x - col * geo.cellM,
    origin.y,
    origin.z + row * geo.rowSpacingM
  );
}

// ---------------------------------------------------------------------------
// 1. VẼ LƯỚI BÀN CỜ LÊN CANVAS
// ---------------------------------------------------------------------------
function createBoardTexture(geometry = null) {
  const geo = geometry || getActiveGeometry();
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = Math.round(1024 * (geo.outerLengthMm / geo.outerWidthMm)); // 1144 px
  const ctx = canvas.getContext("2d");

  // Nền gỗ sáng
  ctx.fillStyle = "#e3c796";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = "#1a1a1a";
  ctx.lineWidth = 5;

  // Lề ngang & dọc theo tỷ lệ hình học chuẩn (23.5mm ngang, 25.0mm dọc)
  const paddingX = Math.round(canvas.width * (geo.marginHorizontalMm / geo.outerWidthMm));
  const paddingY = Math.round(canvas.height * (geo.marginVerticalMm / geo.outerLengthMm));

  // Chia 8 cột và 9 hàng bằng nhau (bước lưới 40mm x 40mm)
  const stepX = (canvas.width - paddingX * 2) / (geo.columns - 1);
  const stepY = (canvas.height - paddingY * 2) / (geo.rows - 1);

  // Column 0 maps to X_world = +0.16m (right side of canvas, u ~ 1)
  // Column 8 maps to X_world = -0.16m (left side of canvas, u ~ 0)
  const getX = (col) => (canvas.width - paddingX) - col * stepX;
  const getY = (row) => paddingY + row * stepY;

  // 1. Vẽ 10 đường ngang (row 0 = Black side, row 9 = Red side)
  for (let r = 0; r < 10; r++) {
    ctx.beginPath();
    ctx.moveTo(getX(0), getY(r));
    ctx.lineTo(getX(8), getY(r));
    ctx.stroke();
  }

  // 2. Vẽ 9 đường dọc (2 đường biên kéo dài, các đường bên trong ngắt ở Sông row 4 -> row 5)
  for (let c = 0; c < 9; c++) {
    if (c === 0 || c === 8) {
      ctx.beginPath();
      ctx.moveTo(getX(c), getY(0));
      ctx.lineTo(getX(c), getY(9));
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(getX(c), getY(0));
      ctx.lineTo(getX(c), getY(4));
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(getX(c), getY(5));
      ctx.lineTo(getX(c), getY(9));
      ctx.stroke();
    }
  }

  // 3. Đường chéo Cung Tướng Phe Đen (Hàng 0 đến 2, Cột 3 đến 5)
  ctx.beginPath();
  ctx.moveTo(getX(3), getY(0));
  ctx.lineTo(getX(5), getY(2));
  ctx.moveTo(getX(5), getY(0));
  ctx.lineTo(getX(3), getY(2));
  ctx.stroke();

  // 4. Đường chéo Cung Tướng Phe Đỏ (Hàng 7 đến 9, Cột 3 đến 5)
  ctx.beginPath();
  ctx.moveTo(getX(3), getY(7));
  ctx.lineTo(getX(5), getY(9));
  ctx.moveTo(getX(5), getY(7));
  ctx.lineTo(getX(3), getY(9));
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
  const pxPerMmX = (canvas.width - paddingX * 2) / playableW;
  const pxPerMmY = (canvas.height - paddingY * 2) / playableL;

  // Thước ngang (biên trên & biên dưới): col 0 (x max) -> col 8 (x min)
  for (let mm = 0; mm <= playableW; mm += 1) {
    const x = (canvas.width - paddingX) - mm * pxPerMmX;
    if (mm % 40 === 0) {
      // Vạch cột chính (40mm)
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(x, paddingY - 12);
      ctx.lineTo(x, paddingY - 26);
      ctx.moveTo(x, canvas.height - paddingY + 12);
      ctx.lineTo(x, canvas.height - paddingY + 26);
      ctx.stroke();

      // Số đo mm
      ctx.fillText(`${mm}mm`, x, paddingY - 34);
      ctx.fillText(`${mm}mm`, x, canvas.height - paddingY + 34);
    } else if (mm % 10 === 0) {
      // Vạch 10mm
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, paddingY - 12);
      ctx.lineTo(x, paddingY - 21);
      ctx.moveTo(x, canvas.height - paddingY + 12);
      ctx.lineTo(x, canvas.height - paddingY + 21);
      ctx.stroke();
    } else if (mm % 2 === 0) {
      // Vạch 2mm
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(x, paddingY - 12);
      ctx.lineTo(x, paddingY - 17);
      ctx.moveTo(x, canvas.height - paddingY + 12);
      ctx.lineTo(x, canvas.height - paddingY + 17);
      ctx.stroke();
    }
  }

  // Thước dọc (biên trái & biên phải): row 0 -> row 9
  for (let mm = 0; mm <= playableL; mm += 1) {
    const y = paddingY + mm * pxPerMmY;
    if (mm % 40 === 0) {
      // Vạch hàng chính (40mm)
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(paddingX - 12, y);
      ctx.lineTo(paddingX - 26, y);
      ctx.moveTo(canvas.width - paddingX + 12, y);
      ctx.lineTo(canvas.width - paddingX + 26, y);
      ctx.stroke();

      // Số đo mm bên trái & phải
      ctx.textAlign = "right";
      ctx.fillText(`${mm}`, paddingX - 30, y);
      ctx.textAlign = "left";
      ctx.fillText(`${mm}`, canvas.width - paddingX + 30, y);
    } else if (mm % 10 === 0) {
      // Vạch 10mm
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(paddingX - 12, y);
      ctx.lineTo(paddingX - 21, y);
      ctx.moveTo(canvas.width - paddingX + 12, y);
      ctx.lineTo(canvas.width - paddingX + 21, y);
      ctx.stroke();
    } else if (mm % 2 === 0) {
      // Vạch 2mm
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(paddingX - 12, y);
      ctx.lineTo(paddingX - 17, y);
      ctx.moveTo(canvas.width - paddingX + 12, y);
      ctx.lineTo(canvas.width - paddingX + 17, y);
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
  group.name = "xiangqi-board";

  const boardWidth = geo.boardWidthM;
  const boardDepth = geo.boardDepthM;
  // Canonical board thickness derived from physical_geometry.json (0.0105m)
  const boardThickness = geo.boardThicknessM || 0.0105;

  const boardMaterial = new THREE.MeshLambertMaterial({
    map: createBoardTexture(geo),
  });

  const frameMaterial = new THREE.MeshLambertMaterial({
    color: 0x5c3317,
  });

  const center = boardPointToXYZ(4, 4.5, geo);

  // 1. Khung viền ngoài (tọa độ local tương đối với tâm group)
  const outerFrame = new THREE.Mesh(
    new THREE.BoxGeometry(boardWidth + 0.02, boardThickness - 0.001, boardDepth + 0.02),
    frameMaterial
  );
  outerFrame.position.set(0, -boardThickness / 2 - 0.0005, 0);
  group.add(outerFrame);

  // 2. Mặt bàn cờ chính (tọa độ local tương đối với tâm group)
  const boardTop = new THREE.Mesh(
    new THREE.BoxGeometry(boardWidth, boardThickness, boardDepth),
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