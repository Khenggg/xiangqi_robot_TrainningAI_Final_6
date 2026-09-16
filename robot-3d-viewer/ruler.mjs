import * as THREE from "three";

/**
 * Tạo một Text Sprite 2D nhỏ gọn, sắc nét theo chuẩn CAD kỹ thuật.
 * Bật depthTest: true để có thể bị vật thể (robot, quân cờ, bàn cờ) che khuất tự nhiên.
 */
export function createTextSprite(text, options = {}) {
  const {
    fontSize = 13,
    fontColor = "#ffffff",
    bgColor = "rgba(15, 23, 42, 0.85)",
    borderColor = "rgba(148, 163, 184, 0.4)",
    paddingX = 4,
    paddingY = 1.5,
    scale = 0.009,
    depthTest = true,
  } = options;

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const font = `bold ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const textWidth = Math.ceil(metrics.width);
  const textHeight = Math.ceil(fontSize * 1.15);

  canvas.width = Math.max(24, textWidth + paddingX * 2);
  canvas.height = textHeight + paddingY * 2;

  ctx.font = font;

  // Bo góc siêu nhỏ gọn
  const r = 2.5;
  const w = canvas.width;
  const h = canvas.height;
  ctx.beginPath();
  ctx.moveTo(r, 0);
  ctx.lineTo(w - r, 0);
  ctx.quadraticCurveTo(w, 0, w, r);
  ctx.lineTo(w, h - r);
  ctx.quadraticCurveTo(w, h, w - r, h);
  ctx.lineTo(r, h);
  ctx.quadraticCurveTo(0, h, 0, h - r);
  ctx.lineTo(0, r);
  ctx.quadraticCurveTo(0, 0, r, 0);
  ctx.closePath();

  ctx.fillStyle = bgColor;
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = borderColor;
  ctx.stroke();

  ctx.fillStyle = fontColor;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, w / 2, h / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;

  const material = new THREE.SpriteMaterial({
    map: texture,
    depthTest: depthTest,
    depthWrite: false,
    transparent: true,
  });

  const sprite = new THREE.Sprite(material);
  const aspect = canvas.width / canvas.height;
  sprite.scale.set(scale * aspect, scale, 1);
  return sprite;
}

/**
 * Dựng hệ trục tọa độ 3D có thước đo chia vạch và nhãn milimet (mm) tương tác:
 * - Khi click vào trục hoặc cạnh bàn cờ mới hiện nhãn hệ số tọa độ (On-Demand / Click-to-Show).
 * - Có hỗ trợ che khuất chiều sâu 3D (depthTest: true).
 */
export function buildCoordinateRulerGroup(options = {}) {
  const group = new THREE.Group();
  group.name = "coordinate-ruler-group";

  const {
    showFineTicks = true,
    initialLabelsVisible = false, // Mặc định ẩn nhãn cho tới khi click vào cạnh
  } = options;

  const yFloor = 0.001; // Sát sàn để khớp với mặt phẳng làm việc

  // Nhóm lưu trữ nhãn của từng trục riêng biệt để bật/tắt độc lập khi click
  const labelsX = new THREE.Group();
  labelsX.name = "labels-x";
  labelsX.visible = initialLabelsVisible;

  const labelsY = new THREE.Group();
  labelsY.name = "labels-y";
  labelsY.visible = initialLabelsVisible;

  const labelsZ = new THREE.Group();
  labelsZ.name = "labels-z";
  labelsZ.visible = initialLabelsVisible;

  const labelsBoard = new THREE.Group();
  labelsBoard.name = "labels-board";
  labelsBoard.visible = initialLabelsVisible;

  const pinsGroup = new THREE.Group();
  pinsGroup.name = "measurement-pins";

  group.add(labelsX);
  group.add(labelsY);
  group.add(labelsZ);
  group.add(labelsBoard);
  group.add(pinsGroup);

  // Màu sắc chuẩn hệ trục
  const colorX = 0xef4444; // Đỏ (Ox)
  const colorY = 0x22c55e; // Xanh lá (Oy)
  const colorZ = 0x3b82f6; // Xanh dương (Oz)

  const lineMatX = new THREE.LineBasicMaterial({ color: colorX, linewidth: 1.5, depthTest: true });
  const lineMatY = new THREE.LineBasicMaterial({ color: colorY, linewidth: 1.5, depthTest: true });
  const lineMatZ = new THREE.LineBasicMaterial({ color: colorZ, linewidth: 1.5, depthTest: true });

  const tickMatMajor = new THREE.LineBasicMaterial({ color: 0xcbd5e1, linewidth: 1.5, depthTest: true });
  const tickMatMinor = new THREE.LineBasicMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.5, depthTest: true });
  const tickMatFine = new THREE.LineBasicMaterial({ color: 0x64748b, transparent: true, opacity: 0.3, depthTest: true });

  // Material trong suốt làm vùng cảm ứng click (Hit Proxy)
  const hitProxyMat = new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0.0,
    depthWrite: false,
  });

  // -------------------------------------------------------------------------
  // 1. TRỤC OX (NGANG: -400mm -> +400mm)
  // -------------------------------------------------------------------------
  const xMin = -0.40;
  const xMax = 0.40;
  const xPoints = [
    new THREE.Vector3(xMin, yFloor, 0),
    new THREE.Vector3(xMax, yFloor, 0),
  ];
  const xGeo = new THREE.BufferGeometry().setFromPoints(xPoints);
  const xLine = new THREE.Line(xGeo, lineMatX);
  group.add(xLine);

  // Mũi tên trục Ox
  const xArrow = new THREE.ArrowHelper(
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(xMax, yFloor, 0),
    0.015,
    colorX,
    0.008,
    0.004
  );
  group.add(xArrow);

  // Hit proxy cho trục Ox (ống trụ vô hình bán kính 22mm giúp dễ click chuột)
  const hitGeoX = new THREE.CylinderGeometry(0.022, 0.022, xMax - xMin, 12);
  hitGeoX.rotateZ(Math.PI / 2);
  const hitProxyX = new THREE.Mesh(hitGeoX, hitProxyMat);
  hitProxyX.position.set((xMin + xMax) / 2, yFloor + 0.005, 0);
  hitProxyX.name = "hit-proxy-x";
  hitProxyX.userData = { isRulerProxy: true, axis: "X" };
  group.add(hitProxyX);

  // Nhãn trục Ox
  const labelX = createTextSprite("+X (Ngang)", {
    fontSize: 14,
    fontColor: "#fca5a5",
    bgColor: "rgba(220, 38, 38, 0.85)",
    borderColor: "#f87171",
    scale: 0.012,
    depthTest: true,
  });
  labelX.position.set(xMax + 0.018, yFloor + 0.005, 0);
  labelsX.add(labelX);

  const labelXNeg = createTextSprite("-X", {
    fontSize: 13,
    fontColor: "#fca5a5",
    bgColor: "rgba(220, 38, 38, 0.85)",
    borderColor: "#f87171",
    scale: 0.010,
    depthTest: true,
  });
  labelXNeg.position.set(xMin - 0.014, yFloor + 0.005, 0);
  labelsX.add(labelXNeg);

  // Vạch chia trục Ox
  const xTickMajorPoints = [];
  const xTickMinorPoints = [];
  const xTickFinePoints = [];

  for (let mm = -400; mm <= 400; mm += 1) {
    const x = mm / 1000.0;
    if (mm % 100 === 0) {
      const tickLen = 0.009;
      xTickMajorPoints.push(
        new THREE.Vector3(x, yFloor, -tickLen / 2),
        new THREE.Vector3(x, yFloor, tickLen / 2)
      );

      if (mm !== 0) {
        const sign = mm > 0 ? `+${mm}` : `${mm}`;
        const sprite = createTextSprite(`${sign}mm`, {
          fontSize: 12,
          fontColor: "#fecaca",
          bgColor: "rgba(15, 23, 42, 0.8)",
          scale: 0.0085,
          depthTest: true,
        });
        sprite.position.set(x, yFloor + 0.004, 0.010);
        labelsX.add(sprite);
      }
    } else if (mm % 50 === 0) {
      const tickLen = 0.006;
      xTickMinorPoints.push(
        new THREE.Vector3(x, yFloor, -tickLen / 2),
        new THREE.Vector3(x, yFloor, tickLen / 2)
      );
    } else if (mm % 10 === 0) {
      const tickLen = 0.004;
      xTickMinorPoints.push(
        new THREE.Vector3(x, yFloor, -tickLen / 2),
        new THREE.Vector3(x, yFloor, tickLen / 2)
      );
    } else if (showFineTicks && (mm % 2 === 0)) {
      const tickLen = 0.002;
      xTickFinePoints.push(
        new THREE.Vector3(x, yFloor, -tickLen / 2),
        new THREE.Vector3(x, yFloor, tickLen / 2)
      );
    }
  }

  if (xTickMajorPoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(xTickMajorPoints);
    group.add(new THREE.LineSegments(geo, tickMatMajor));
  }
  if (xTickMinorPoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(xTickMinorPoints);
    group.add(new THREE.LineSegments(geo, tickMatMinor));
  }
  if (xTickFinePoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(xTickFinePoints);
    group.add(new THREE.LineSegments(geo, tickMatFine));
  }

  // -------------------------------------------------------------------------
  // 2. TRỤC OZ (DỌC HƯỚNG BÀN CỜ: 0mm -> +650mm)
  // -------------------------------------------------------------------------
  const zMin = 0.0;
  const zMax = 0.65;
  const zPoints = [
    new THREE.Vector3(0, yFloor, zMin),
    new THREE.Vector3(0, yFloor, zMax),
  ];
  const zGeo = new THREE.BufferGeometry().setFromPoints(zPoints);
  const zLine = new THREE.Line(zGeo, lineMatZ);
  group.add(zLine);

  const zArrow = new THREE.ArrowHelper(
    new THREE.Vector3(0, 0, 1),
    new THREE.Vector3(0, yFloor, zMax),
    0.015,
    colorZ,
    0.008,
    0.004
  );
  group.add(zArrow);

  // Hit proxy cho trục Oz
  const hitGeoZ = new THREE.CylinderGeometry(0.022, 0.022, zMax - zMin, 12);
  hitGeoZ.rotateX(Math.PI / 2);
  const hitProxyZ = new THREE.Mesh(hitGeoZ, hitProxyMat);
  hitProxyZ.position.set(0, yFloor + 0.005, (zMin + zMax) / 2);
  hitProxyZ.name = "hit-proxy-z";
  hitProxyZ.userData = { isRulerProxy: true, axis: "Z" };
  group.add(hitProxyZ);

  // Nhãn trục Oz
  const labelZ = createTextSprite("+Z (Dọc / Bàn Cờ)", {
    fontSize: 14,
    fontColor: "#93c5fd",
    bgColor: "rgba(37, 99, 235, 0.85)",
    borderColor: "#60a5fa",
    scale: 0.012,
    depthTest: true,
  });
  labelZ.position.set(0, yFloor + 0.005, zMax + 0.018);
  labelsZ.add(labelZ);

  const zTickMajorPoints = [];
  const zTickMinorPoints = [];
  const zTickFinePoints = [];

  for (let mm = 0; mm <= 650; mm += 1) {
    const z = mm / 1000.0;
    if (mm % 100 === 0) {
      const tickLen = 0.009;
      zTickMajorPoints.push(
        new THREE.Vector3(-tickLen / 2, yFloor, z),
        new THREE.Vector3(tickLen / 2, yFloor, z)
      );

      if (mm > 0) {
        const sprite = createTextSprite(`Z: ${mm}mm`, {
          fontSize: 12,
          fontColor: "#bfdbfe",
          bgColor: "rgba(15, 23, 42, 0.8)",
          scale: 0.0085,
          depthTest: true,
        });
        sprite.position.set(-0.012, yFloor + 0.004, z);
        labelsZ.add(sprite);
      }
    } else if (mm % 50 === 0) {
      const tickLen = 0.006;
      zTickMinorPoints.push(
        new THREE.Vector3(-tickLen / 2, yFloor, z),
        new THREE.Vector3(tickLen / 2, yFloor, z)
      );
    } else if (mm % 10 === 0) {
      const tickLen = 0.004;
      zTickMinorPoints.push(
        new THREE.Vector3(-tickLen / 2, yFloor, z),
        new THREE.Vector3(tickLen / 2, yFloor, z)
      );
    } else if (showFineTicks && (mm % 2 === 0)) {
      const tickLen = 0.002;
      zTickFinePoints.push(
        new THREE.Vector3(-tickLen / 2, yFloor, z),
        new THREE.Vector3(tickLen / 2, yFloor, z)
      );
    }
  }

  // Các mốc đặc biệt trên trục Z
  const specialZMarkers = [
    { z: 0.18, label: "H0: 180mm", color: "#38bdf8" },
    { z: 0.36, label: "Tâm: 360mm", color: "#fbbf24" },
    { z: 0.54, label: "H9: 540mm", color: "#f87171" },
  ];
  specialZMarkers.forEach((m) => {
    const sprite = createTextSprite(`📍 ${m.label}`, {
      fontSize: 12,
      fontColor: m.color,
      bgColor: "rgba(15, 23, 42, 0.85)",
      borderColor: m.color,
      scale: 0.0095,
      depthTest: true,
    });
    sprite.position.set(0.018, yFloor + 0.005, m.z);
    labelsZ.add(sprite);
  });

  if (zTickMajorPoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(zTickMajorPoints);
    group.add(new THREE.LineSegments(geo, tickMatMajor));
  }
  if (zTickMinorPoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(zTickMinorPoints);
    group.add(new THREE.LineSegments(geo, tickMatMinor));
  }
  if (zTickFinePoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(zTickFinePoints);
    group.add(new THREE.LineSegments(geo, tickMatFine));
  }

  // -------------------------------------------------------------------------
  // 3. TRỤC OY (THẲNG ĐỨNG / CAO ĐỘ: 0mm -> +500mm)
  // -------------------------------------------------------------------------
  const yMax = 0.50;
  const yPoints = [
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0, yMax, 0),
  ];
  const yGeo = new THREE.BufferGeometry().setFromPoints(yPoints);
  const yLine = new THREE.Line(yGeo, lineMatY);
  group.add(yLine);

  const yArrow = new THREE.ArrowHelper(
    new THREE.Vector3(0, 1, 0),
    new THREE.Vector3(0, yMax, 0),
    0.015,
    colorY,
    0.008,
    0.004
  );
  group.add(yArrow);

  // Hit proxy cho trục Oy
  const hitGeoY = new THREE.CylinderGeometry(0.022, 0.022, yMax, 12);
  const hitProxyY = new THREE.Mesh(hitGeoY, hitProxyMat);
  hitProxyY.position.set(0, yMax / 2, 0);
  hitProxyY.name = "hit-proxy-y";
  hitProxyY.userData = { isRulerProxy: true, axis: "Y" };
  group.add(hitProxyY);

  // Nhãn trục Oy
  const labelY = createTextSprite("+Y (Cao độ / Up)", {
    fontSize: 14,
    fontColor: "#86efac",
    bgColor: "rgba(22, 163, 74, 0.85)",
    borderColor: "#4ade80",
    scale: 0.012,
    depthTest: true,
  });
  labelY.position.set(0, yMax + 0.015, 0);
  labelsY.add(labelY);

  const yTickMajorPoints = [];
  const yTickMinorPoints = [];

  for (let mm = 0; mm <= 500; mm += 1) {
    const y = mm / 1000.0;
    if (mm % 100 === 0) {
      const tickLen = 0.009;
      yTickMajorPoints.push(
        new THREE.Vector3(-tickLen / 2, y, 0),
        new THREE.Vector3(tickLen / 2, y, 0)
      );

      if (mm > 0) {
        const sprite = createTextSprite(`Y: ${mm}mm`, {
          fontSize: 12,
          fontColor: "#bbf7d0",
          bgColor: "rgba(15, 23, 42, 0.8)",
          scale: 0.0085,
          depthTest: true,
        });
        sprite.position.set(-0.014, y, 0);
        labelsY.add(sprite);
      }
    } else if (mm % 50 === 0) {
      const tickLen = 0.006;
      yTickMinorPoints.push(
        new THREE.Vector3(-tickLen / 2, y, 0),
        new THREE.Vector3(tickLen / 2, y, 0)
      );
    } else if (mm % 10 === 0) {
      const tickLen = 0.004;
      yTickMinorPoints.push(
        new THREE.Vector3(-tickLen / 2, y, 0),
        new THREE.Vector3(tickLen / 2, y, 0)
      );
    }
  }

  // Các mốc cao độ kỹ thuật
  const specialYMarkers = [
    { y: 0.0105, label: "Mặt Bàn: 10.5mm", color: "#e3a857" },
    { y: 0.0152, label: "Tâm Cờ: 15.2mm", color: "#4ade80" },
    { y: 0.0805, label: "Safe Z: 80.5mm", color: "#38bdf8" },
  ];
  specialYMarkers.forEach((m) => {
    const sprite = createTextSprite(`📏 ${m.label}`, {
      fontSize: 11,
      fontColor: m.color,
      bgColor: "rgba(15, 23, 42, 0.85)",
      borderColor: m.color,
      scale: 0.009,
      depthTest: true,
    });
    sprite.position.set(0.018, m.y, 0);
    labelsY.add(sprite);
  });

  if (yTickMajorPoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(yTickMajorPoints);
    group.add(new THREE.LineSegments(geo, tickMatMajor));
  }
  if (yTickMinorPoints.length > 0) {
    const geo = new THREE.BufferGeometry().setFromPoints(yTickMinorPoints);
    group.add(new THREE.LineSegments(geo, tickMatMinor));
  }

  // -------------------------------------------------------------------------
  // 4. GỐC TỌA ĐỘ (0, 0, 0)
  // -------------------------------------------------------------------------
  const originLabel = createTextSprite("Gốc (0, 0, 0)", {
    fontSize: 12,
    fontColor: "#ffffff",
    bgColor: "rgba(15, 23, 42, 0.85)",
    borderColor: "#94a3b8",
    scale: 0.009,
    depthTest: true,
  });
  originLabel.position.set(0.010, yFloor + 0.005, -0.010);
  labelsX.add(originLabel);

  // -------------------------------------------------------------------------
  // 5. HIT PROXIES CHO 4 CẠNH BÀN CỜ (BOARD EDGES)
  // -------------------------------------------------------------------------
  // Bàn cờ đặt tại tâm (0, 0.0105, 0.36), kích thước: 0.367m x 0.410m
  const boardEdgesGroup = new THREE.Group();
  boardEdgesGroup.name = "board-edges-group";
  group.add(boardEdgesGroup);

  const boardCenterZ = 0.36;
  const boardHalfW = 0.367 / 2; // 0.1835m
  const boardHalfL = 0.410 / 2; // 0.205m

  const makeEdgeProxy = (w, h, d, x, y, z, edgeName) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), hitProxyMat);
    mesh.position.set(x, y, z);
    mesh.name = `hit-proxy-edge-${edgeName}`;
    mesh.userData = { isRulerProxy: true, axis: "BOARD", edge: edgeName };
    boardEdgesGroup.add(mesh);
  };

  // Cạnh trước (Near - Hàng 0)
  makeEdgeProxy(0.38, 0.025, 0.03, 0, yFloor + 0.01, boardCenterZ - boardHalfL, "NEAR");
  // Cạnh sau (Far - Hàng 9)
  makeEdgeProxy(0.38, 0.025, 0.03, 0, yFloor + 0.01, boardCenterZ + boardHalfL, "FAR");
  // Cạnh trái (Col 8)
  makeEdgeProxy(0.03, 0.025, 0.42, -boardHalfW, yFloor + 0.01, boardCenterZ, "LEFT");
  // Cạnh phải (Col 0)
  makeEdgeProxy(0.03, 0.025, 0.42, boardHalfW, yFloor + 0.01, boardCenterZ, "RIGHT");

  // -------------------------------------------------------------------------
  // CÁC HÀM TIỆN ÍCH QUẢN LÝ HIỂN THỊ TỌA ĐỘ KHI CLICK (API)
  // -------------------------------------------------------------------------

  /**
   * Bật / tắt nhãn hệ số tọa độ của trục chỉ định hoặc toàn bộ.
   */
  group.toggleAxis = function (axisName, clickPoint = null) {
    if (axisName === "X") {
      labelsX.visible = !labelsX.visible;
      if (labelsX.visible && clickPoint) {
        group.showMeasurementPin(clickPoint, `X = ${(clickPoint.x * 1000).toFixed(0)}mm`, colorX);
      }
      return labelsX.visible;
    }
    if (axisName === "Y") {
      labelsY.visible = !labelsY.visible;
      if (labelsY.visible && clickPoint) {
        group.showMeasurementPin(clickPoint, `Y = ${(clickPoint.y * 1000).toFixed(0)}mm`, colorY);
      }
      return labelsY.visible;
    }
    if (axisName === "Z") {
      labelsZ.visible = !labelsZ.visible;
      if (labelsZ.visible && clickPoint) {
        group.showMeasurementPin(clickPoint, `Z = ${(clickPoint.z * 1000).toFixed(0)}mm`, colorZ);
      }
      return labelsZ.visible;
    }
    if (axisName === "BOARD") {
      labelsBoard.visible = !labelsBoard.visible;
      if (clickPoint) {
        const xMm = (clickPoint.x * 1000).toFixed(0);
        const zMm = (clickPoint.z * 1000).toFixed(0);
        group.showMeasurementPin(clickPoint, `Mép bàn: X=${xMm}mm | Z=${zMm}mm`, 0xf59e0b);
      }
      return labelsBoard.visible;
    }
    return false;
  };

  /**
   * Đặt trạng thái hiển thị cho toàn bộ hoặc từng trục.
   */
  group.toggleAll = function (forceVisible = null) {
    const nextState = forceVisible !== null ? forceVisible : !labelsX.visible;
    labelsX.visible = nextState;
    labelsY.visible = nextState;
    labelsZ.visible = nextState;
    labelsBoard.visible = nextState;
    if (!nextState) {
      group.clearPins();
    }
    return nextState;
  };

  group.isAnyLabelsVisible = function () {
    return labelsX.visible || labelsY.visible || labelsZ.visible || labelsBoard.visible;
  };

  /**
   * Cập nhật vị trí các hit proxies cạnh bàn cờ theo authoritative runtime placement.
   */
  group.updateBoardPlacement = function (boardCenterZ, boardSurfaceY) {
    if (boardCenterZ !== undefined && boardCenterZ !== null) {
      const dz = Number(boardCenterZ) - 0.36;
      boardEdgesGroup.position.z = dz;
      labelsBoard.position.z = dz;
    }
    if (boardSurfaceY !== undefined && boardSurfaceY !== null) {
      const dy = Number(boardSurfaceY) - 0.0105;
      boardEdgesGroup.position.y = dy;
      labelsBoard.position.y = dy;
    }
  };

  /**
   * Cắm một ghim đo khoảng cách tương tác tại vị trí click.
   */
  group.showMeasurementPin = function (point, text, colorHex = 0x58a6ff) {
    group.clearPins();

    const pinGroup = new THREE.Group();
    pinGroup.name = "active-pin";

    // Cột ghim nhỏ
    const pinGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(point.x, point.y, point.z),
      new THREE.Vector3(point.x, point.y + 0.025, point.z),
    ]);
    const pinLine = new THREE.Line(pinGeo, new THREE.LineBasicMaterial({ color: colorHex, depthTest: true }));
    pinGroup.add(pinLine);

    // Điểm chấm tròn tiếp xúc
    const dotGeo = new THREE.SphereGeometry(0.003, 12, 12);
    const dotMat = new THREE.MeshBasicMaterial({ color: colorHex, depthTest: true });
    const dot = new THREE.Mesh(dotGeo, dotMat);
    dot.position.set(point.x, point.y, point.z);
    pinGroup.add(dot);

    // Huy hiệu nhãn số tọa độ
    const sprite = createTextSprite(`📍 ${text}`, {
      fontSize: 13,
      fontColor: "#ffffff",
      bgColor: "rgba(15, 23, 42, 0.92)",
      borderColor: `#${colorHex.toString(16).padStart(6, "0")}`,
      scale: 0.011,
      depthTest: true,
    });
    sprite.position.set(point.x, point.y + 0.030, point.z);
    pinGroup.add(sprite);

    pinsGroup.add(pinGroup);
  };

  group.clearPins = function () {
    while (pinsGroup.children.length > 0) {
      const child = pinsGroup.children.pop();
      child.traverse?.((o) => {
        o.geometry?.dispose?.();
        o.material?.dispose?.();
      });
    }
  };

  return group;
}

/**
 * Tạo đường dóng đo khoảng cách động (Dynamic Dimension Tape)
 * từ gốc hoặc giữa 2 điểm (p1 -> p2) trong không gian 3D.
 * Bật depthTest: true để bị che khuất tự nhiên bởi cánh tay robot.
 */
export function createDimensionTape(start, end, labelText = "") {
  const group = new THREE.Group();
  group.name = "dimension-tape";

  const pts = [start.clone(), end.clone()];
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = new THREE.LineDashedMaterial({
    color: 0xf59e0b,
    dashSize: 0.01,
    gapSize: 0.005,
    depthTest: true,
  });
  const line = new THREE.Line(geo, mat);
  line.computeLineDistances();
  group.add(line);

  const mid = start.clone().lerp(end, 0.5);
  const distMm = (start.distanceTo(end) * 1000).toFixed(0);
  const text = labelText || `R = ${distMm}mm`;

  const sprite = createTextSprite(text, {
    fontSize: 12,
    fontColor: "#fef3c7",
    bgColor: "rgba(217, 119, 6, 0.85)",
    borderColor: "#fbbf24",
    scale: 0.0095,
    depthTest: true,
  });
  sprite.position.copy(mid).add(new THREE.Vector3(0, 0.008, 0));
  group.add(sprite);

  return group;
}
