import * as THREE from "three";

export const CELL = 0.05; // Khoảng cách giữa 2 đường kẻ
export const BOARD_ORIGIN = new THREE.Vector3(0.32, 0.001, -0.18);

export function boardPointToXYZ(col, row) {
  return new THREE.Vector3(
    BOARD_ORIGIN.x + col * CELL,
    BOARD_ORIGIN.y,
    BOARD_ORIGIN.z + row * CELL
  );
}

// ---------------------------------------------------------------------------
// 1. VẼ LƯỚI BÀN CỜ LÊN CANVAS
// ---------------------------------------------------------------------------
function createBoardTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1152;
  const ctx = canvas.getContext("2d");

  // Nền gỗ sáng
  ctx.fillStyle = "#e3c796";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.strokeStyle = "#1a1a1a";
  ctx.lineWidth = 6;

  const paddingX = 64;
  const paddingY = 64;

  // Chia 8 cột bằng nhau
  const stepX = (canvas.width - paddingX * 2) / 8;
  
  // Tỷ lệ chuẩn: 8 hàng cờ là các ô vuông (chiều cao = stepX)
  // Chiều cao sông = khoảng còn lại ở giữa
  const squareHeight = stepX;
  const riverHeight = (canvas.height - paddingY * 2) - (8 * squareHeight);

  const getX = (col) => paddingX + col * stepX;
  
  // Tính tọa độ Y cho 10 đường ngang (4 hàng bên dưới, 1 Sông, 4 hàng bên trên)
  const getY = (row) => {
    if (row <= 4) {
      return paddingY + row * squareHeight; // Hàng 0 đến 4 (bên dưới)
    } else {
      return paddingY + 4 * squareHeight + riverHeight + (row - 5) * squareHeight; // Hàng 5 đến 9 (bên trên)
    }
  };

  // 1. Vẽ 10 đường ngang
  for (let r = 0; r < 10; r++) {
    ctx.beginPath();
    ctx.moveTo(getX(0), getY(r));
    ctx.lineTo(getX(8), getY(r));
    ctx.stroke();
  }

  // 2. Vẽ 9 đường dọc (2 đường biên kéo dài, các đường bên trong ngắt ở Sông)
  for (let c = 0; c < 9; c++) {
    if (c === 0 || c === 8) {
      // 2 đường biên (cột a và i) kéo dài qua Sông
      ctx.beginPath();
      ctx.moveTo(getX(c), getY(0));
      ctx.lineTo(getX(c), getY(9));
      ctx.stroke();
    } else {
      // Các đường bên trong: Ngắt ở Sông (row 4 -> row 5)
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

  // 3. Đường chéo Cung Tướng - Cung dưới (Hàng 0 đến 2, Cột 3 đến 5)
  ctx.beginPath();
  ctx.moveTo(getX(3), getY(0));
  ctx.lineTo(getX(5), getY(2));
  ctx.moveTo(getX(5), getY(0));
  ctx.lineTo(getX(3), getY(2));
  ctx.stroke();

  // 4. Đường chéo Cung Tướng - Cung trên (Hàng 7 đến 9, Cột 3 đến 5)
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
// 2. DỰNG BÀN CỜ 3D (ĐÃ SỬA LỖI Z-FIGHTING & BÓNG ĐỔ)
// ---------------------------------------------------------------------------
export function buildBoardGrid() {
  const group = new THREE.Group();
  group.name = "xiangqi-board";

  const boardWidth = 8 * CELL + CELL * 1.2;
  const boardDepth = 9 * CELL + CELL * 1.2;
  const boardThickness = 0.02;

  // Material dùng MeshLambertMaterial thay vì Standard để tránh bị nhiễu bóng bẩn
  const boardMaterial = new THREE.MeshLambertMaterial({
    map: createBoardTexture(),
  });

  const frameMaterial = new THREE.MeshLambertMaterial({
    color: 0x5c3317,
  });

  const center = boardPointToXYZ(4, 4.5);

  // 1. Khung viền ngoài (Cho nằm thấp hơn hẳn mặt bàn)
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
  boardTop.receiveShadow = true; // Nhận bóng đổ từ quân cờ
  group.add(boardTop);

  return group;
}

// ---------------------------------------------------------------------------
// 3. DỰNG QUÂN CỜ
// ---------------------------------------------------------------------------
const LABEL_RED = { k: "帥", a: "仕", b: "相", n: "馬", r: "車", c: "砲", p: "兵" };
const LABEL_BLACK = { k: "將", a: "士", b: "象", n: "馬", r: "車", c: "炮", p: "卒" };

const START_LAYOUT = [
  [0, 0, "r", "r"], [1, 0, "n", "r"], [2, 0, "b", "r"], [3, 0, "a", "r"],
  [4, 0, "k", "r"], [5, 0, "a", "r"], [6, 0, "b", "r"], [7, 0, "n", "r"],
  [8, 0, "r", "r"], [1, 2, "c", "r"], [7, 2, "c", "r"],
  [0, 3, "p", "r"], [2, 3, "p", "r"], [4, 3, "p", "r"], [6, 3, "p", "r"], [8, 3, "p", "r"],

  [0, 9, "r", "b"], [1, 9, "n", "b"], [2, 9, "b", "b"], [3, 9, "a", "b"],
  [4, 9, "k", "b"], [5, 9, "a", "b"], [6, 9, "b", "b"], [7, 9, "n", "b"],
  [8, 9, "r", "b"], [1, 7, "c", "b"], [7, 7, "c", "b"],
  [0, 6, "p", "b"], [2, 6, "p", "b"], [4, 6, "p", "b"], [6, 6, "p", "b"], [8, 6, "p", "b"],
];

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

  // --- XOAY CHỮ DỌC ---
  ctx.save();
  ctx.translate(128, 128); // Di chuyển gốc tọa độ về tâm quân cờ
  
  // Xoay 90 độ (Math.PI / 2) để chữ nằm dọc
  // Nếu chữ bị ngược hướng bạn mong muốn, đổi thành (-Math.PI / 2)
  ctx.rotate(Math.PI / 2); 

  ctx.fillStyle = side === "r" ? "#c4210b" : "#1f4a28";
  ctx.font = "bold 130px KaiTi, STKaiti, SimHei, serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  
  // Vẽ chữ tại tâm mới (0, 10)
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

export function buildPieces(layout = START_LAYOUT) {
  const group = new THREE.Group();
  group.name = "xiangqi-pieces";
  const pieces = {};
  const radius = CELL * 0.42;
  const height = 0.015;

  const geometry = new THREE.CylinderGeometry(radius, radius, height, 32);

  layout.forEach(([col, row, type, side], index) => {
    const label = side === "r" ? LABEL_RED[type] : LABEL_BLACK[type];
    const mesh = new THREE.Mesh(geometry, makePieceMaterials(label, side));
    const pos = boardPointToXYZ(col, row);

    mesh.position.set(pos.x, pos.y + height / 2, pos.z);
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

export function movePieceTo(mesh, col, row) {
  const pos = boardPointToXYZ(col, row);
  mesh.position.set(pos.x, mesh.position.y, pos.z);
  mesh.userData.col = col;
  mesh.userData.row = row;
}