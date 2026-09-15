import * as THREE from "three";
import { fetchPhysicalGeometry, parsePhysicalGeometry } from "./geometry.mjs";
import { START_LAYOUT, LABEL_RED, LABEL_BLACK } from "./layout.mjs";

// Re-export layout for convenience
export { START_LAYOUT, LABEL_RED, LABEL_BLACK };

// ---------------------------------------------------------------------------
// SIMULATION SCENE PLACEMENT (NOT INTRINSIC PHYSICAL GEOMETRY)
// ---------------------------------------------------------------------------
// Center of the board in Three.js scene coordinates (meters) relative to virtual robot base.
export const SIM_BOARD_CENTER_X = 0.48;
export const SIM_BOARD_CENTER_Z = 0.0;

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
  return new THREE.Vector3(
    SIM_BOARD_CENTER_X - geo.playableWidthM / 2.0,
    0.001,
    SIM_BOARD_CENTER_Z - geo.playableDepthM / 2.0
  );
}

export function boardPointToXYZ(col, row, geometry = null) {
  const geo = geometry || getActiveGeometry();
  const origin = computeBoardOrigin(geo);
  return new THREE.Vector3(
    origin.x + col * geo.cellM,
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

  const getX = (col) => paddingX + col * stepX;
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
  const boardThickness = 0.02;

  const boardMaterial = new THREE.MeshLambertMaterial({
    map: createBoardTexture(geo),
  });

  const frameMaterial = new THREE.MeshLambertMaterial({
    color: 0x5c3317,
  });

  const center = boardPointToXYZ(4, 4.5, geo);

  // 1. Khung viền ngoài
  const outerFrame = new THREE.Mesh(
    new THREE.BoxGeometry(boardWidth + 0.02, boardThickness - 0.002, boardDepth + 0.02),
    frameMaterial
  );
  outerFrame.position.set(center.x, center.y - boardThickness / 2 - 0.001, center.z);
  group.add(outerFrame);

  // 2. Mặt bàn cờ chính
  const boardTop = new THREE.Mesh(
    new THREE.BoxGeometry(boardWidth, boardThickness, boardDepth),
    boardMaterial
  );
  boardTop.position.set(center.x, center.y - boardThickness / 2, center.z);
  boardTop.receiveShadow = true;
  group.add(boardTop);

  return group;
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

export function buildPieces(geometry = null, layout = START_LAYOUT) {
  const geo = geometry || getActiveGeometry();
  const group = new THREE.Group();
  group.name = "xiangqi-pieces";
  const pieces = {};
  const radius = geo.pieceRadiusM;
  const height = geo.pieceHeightM;

  const cylinderGeometry = new THREE.CylinderGeometry(radius, radius, height, 32);

  layout.forEach(([col, row, type, side], index) => {
    const label = side === "r" ? LABEL_RED[type] : LABEL_BLACK[type];
    const mesh = new THREE.Mesh(cylinderGeometry, makePieceMaterials(label, side));
    const pos = boardPointToXYZ(col, row, geo);

    mesh.position.set(pos.x, pos.y + height / 2.0, pos.z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    const id = `${side}_${type}_${index}`;
    mesh.name = id;
    mesh.userData = { col, row, type, side };
    pieces[id] = mesh;
    group.add(mesh);
  });

  return { group, pieces };
}

export function movePieceTo(mesh, col, row, geometry = null) {
  const geo = geometry || getActiveGeometry();
  const pos = boardPointToXYZ(col, row, geo);
  mesh.position.set(pos.x, mesh.position.y, pos.z);
  mesh.userData.col = col;
  mesh.userData.row = row;
}