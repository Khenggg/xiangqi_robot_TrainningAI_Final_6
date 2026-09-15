import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { validateLivePacket, stabilizeJointTarget } from "./live_state.mjs";
import { fetchPhysicalGeometry } from "./geometry.mjs";
import { buildBoardGrid, buildPieces, setBoardGeometry } from "./board.mjs";
// ---------------------------------------------------------------------------
// 1) CẤU HÌNH ROBOT — copy nguyên từ frnsimulation-main/app.js
// ---------------------------------------------------------------------------
const LINK_FILES = [
  "base_link",
  "shoulder_link",
  "upperarm_link",
  "forearm_link",
  "wrist1_link",
  "wrist2_link",
  "wrist3_link",
];

const FR3_KINEMATIC_ORIGINS = [
  [0, 0, 0],
  [0, 0, 0.14],
  [-0.28, 0, 0],
  [-0.24001, 0, 0],
  [0, 0, 0.102],
  [0, 0, 0.102],
];
const FR3_KINEMATIC_RPY = [
  [0, 0, 0],
  [Math.PI / 2, 0, 0],
  [0, 0, 0],
  [0, 0, 0],
  [Math.PI / 2, 0, 0],
  [-Math.PI / 2, 0, 0],
];
const FR5_KINEMATIC_ORIGINS = [
  [0, 0, 0],
  [0, 0, 0.152],
  [-0.425, 0, 0],
  [-0.39501, 0, 0],
  [0, 0, 0.1021],
  [0, 0, 0.102],
];

const ROBOT_PROFILES = Object.freeze({
  fr3: Object.freeze({
    id: "fr3",
    label: "FAIRINO FR3",
    meshBase: "./assets/fr3_v6/",
    visualJointOrigins: FR3_KINEMATIC_ORIGINS,
    visualJointRpy: FR3_KINEMATIC_RPY,
  }),
  fr5: Object.freeze({
    id: "fr5",
    label: "FAIRINO FR5",
    meshBase: "./assets/fr5_v6/",
    visualJointOrigins: FR5_KINEMATIC_ORIGINS,
    // FR5 dùng chung cấu trúc góc xoay khớp với FR3 (visual only)
    visualJointRpy: FR3_KINEMATIC_RPY,
  }),
});
const getRobotProfile = (id) => ROBOT_PROFILES[id] || ROBOT_PROFILES.fr3;

const ROBOT_SHELL_COLOR = 0xbfc9d4;
// Live telemetry chấp nhận biên độ rộng — vì mục đích chỉ để mirror,
// không dùng để giới hạn an toàn chuyển động thật.
const LIVE_JOINT_LIMITS_DEG = Array.from({ length: 6 }, () => [-360, 360]);
const LIVE_JOINT_DEADBAND_DEG = 0.02;

// ---------------------------------------------------------------------------
// 2) SCENE THREE.JS
// ---------------------------------------------------------------------------
const canvas = document.getElementById("scene");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x11151c);

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 50);
camera.position.set(0.75, 0.75, 0.75);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.15, 0.25);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xffffff, 0x1a1f27, 1.1));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.4);
keyLight.position.set(1.5, 2.5, 1.2);
scene.add(keyLight);

const grid = new THREE.GridHelper(1.6, 16, 0x2a3140, 0x1c212b);
scene.add(grid);

let xiangqiPieces = null;


function resizeRenderer() {
  const { clientWidth, clientHeight } = canvas;
  renderer.setSize(clientWidth, clientHeight, false);
  camera.aspect = clientWidth / clientHeight || 1;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resizeRenderer);

// ---------------------------------------------------------------------------
// 3) DỰNG TAY ROBOT TỪ STL — copy/rút gọn từ buildRobotArm() trong app.js gốc
// ---------------------------------------------------------------------------
function loadSTL(loader, profile, file) {
  return new Promise((resolve, reject) =>
    loader.load(`${profile.meshBase}${file}.STL`, resolve, undefined, reject),
  );
}

function disposeRobotArm(candidate) {
  if (!candidate) return;
  candidate.group.traverse((object) => {
    if (!object.isMesh) return;
    object.geometry?.dispose();
    object.material?.dispose?.();
  });
}

async function buildRobotArm(profile) {
  const loader = new STLLoader();
  const material = () =>
    new THREE.MeshStandardMaterial({
      color: ROBOT_SHELL_COLOR,
      roughness: 0.62,
      metalness: 0.12,
    });
  const candidate = { group: new THREE.Group(), jointRotators: [] };
  candidate.group.name = `robot-arm-${profile.id}`;
  try {
    const baseGeometry = await loadSTL(loader, profile, "base_link");
    const baseMesh = new THREE.Mesh(baseGeometry, material());
    baseMesh.castShadow = true;
    candidate.group.add(baseMesh);

    let parent = candidate.group;
    for (let i = 0; i < 6; i++) {
      const frame = new THREE.Group();
      frame.position.fromArray(profile.visualJointOrigins[i]);
      frame.rotation.set(...profile.visualJointRpy[i]);
      parent.add(frame);

      const rotator = new THREE.Group();
      frame.add(rotator);
      candidate.jointRotators.push(rotator);

      const geometry = await loadSTL(loader, profile, LINK_FILES[i + 1]);
      const mesh = new THREE.Mesh(geometry, material());
      mesh.castShadow = true;
      rotator.add(mesh);
      parent = rotator;
    }

    // Canonical root transformation: robot_base -> 3d_world
    // Maps robot base frame (Z-up, -X facing board, +Y lateral)
    // to Three.js scene (Y-up, +Z facing board, +X lateral)
    const rootMatrix = new THREE.Matrix4().set(
      0, 1, 0, 0,
      0, 0, 1, 0,
     -1, 0, 0, 0,
      0, 0, 0, 1
    );
    candidate.group.applyMatrix4(rootMatrix);

    return candidate;
  } catch (error) {
    disposeRobotArm(candidate);
    throw error;
  }
}

function applyJointsDeg(candidate, jointsDeg) {
  candidate.jointRotators.forEach((rotator, i) => {
    rotator.rotation.z = THREE.MathUtils.degToRad(jointsDeg[i] ?? 0);
  });
}

// ---------------------------------------------------------------------------
// 4) TRẠNG THÁI ỨNG DỤNG + CHUYỂN ĐỔI ROBOT
// ---------------------------------------------------------------------------
const state = {
  robotProfileId: "fr3",
  currentArm: null,
  jointsDeg: [0, 0, 0, 0, 0, 0],
  // nội suy mượt cho live mirror
  liveFromDeg: null,
  liveTargetDeg: null,
  liveAnimationStart: 0,
  liveAnimationDuration: 120,
  liveSocket: null,
};

async function switchRobotProfile(profileId) {
  const profile = getRobotProfile(profileId);
  state.robotProfileId = profile.id;
  const next = await buildRobotArm(profile);
  if (state.currentArm) {
    scene.remove(state.currentArm.group);
    disposeRobotArm(state.currentArm);
  }
  state.currentArm = next;
  scene.add(next.group);
  applyJointsDeg(next, state.jointsDeg);
}

// ---------------------------------------------------------------------------
// 5) LIVE MIRROR QUA WEBSOCKET — tương thích với telemetry_publisher.py
// ---------------------------------------------------------------------------
const liveStateEl = document.getElementById("liveState");
const jointsReadoutEl = document.getElementById("jointsReadout");

function setLiveBadge(text, kind = "") {
  liveStateEl.textContent = text;
  liveStateEl.className = kind;
}

function applyLiveState(payload) {
  const expectedModel = getRobotProfile(state.robotProfileId).label.includes("FR3")
    ? "FR3"
    : "FR5";
  const validation = validateLivePacket(payload, LIVE_JOINT_LIMITS_DEG, expectedModel);
  if (!validation.ok) {
    console.warn("Live packet rejected:", validation.reason);
    return;
  }
  const nextTarget = stabilizeJointTarget(
    validation.joints,
    state.liveTargetDeg,
    LIVE_JOINT_DEADBAND_DEG,
  );
  const now = performance.now();
  if (!state.liveTargetDeg) {
    state.jointsDeg = [...nextTarget];
    state.liveFromDeg = [...nextTarget];
  } else {
    state.liveFromDeg = [...state.jointsDeg];
    state.liveAnimationStart = now;
  }
  state.liveTargetDeg = nextTarget;
  jointsReadoutEl.textContent = nextTarget.map((v) => v.toFixed(1)).join(", ");
}

function advanceLiveInterpolation(now) {
  if (!state.liveTargetDeg || !state.liveFromDeg) return;
  const t = Math.min(
    1,
    (now - state.liveAnimationStart) / state.liveAnimationDuration,
  );
  const eased = t * t * (3 - 2 * t);
  state.jointsDeg = state.liveFromDeg.map(
    (v, i) => v + (state.liveTargetDeg[i] - v) * eased,
  );
}

function connectLive() {
  if (state.liveSocket) {
    state.liveSocket.close();
    return;
  }
  const url = document.getElementById("wsUrl").value.trim();
  let socket;
  try {
    socket = new WebSocket(url);
  } catch (error) {
    setLiveBadge("URL LỖI", "error");
    return;
  }
  state.liveSocket = socket;
  setLiveBadge("ĐANG KẾT NỐI…");
  socket.onopen = () => setLiveBadge("LIVE", "live");
  socket.onmessage = (event) => {
    try {
      applyLiveState(JSON.parse(event.data));
    } catch (error) {
      console.warn("Live message error:", error.message);
    }
  };
  socket.onerror = () => setLiveBadge("LỖI", "error");
  socket.onclose = () => {
    state.liveSocket = null;
    setLiveBadge("OFFLINE");
  };
}

document.getElementById("liveBtn").addEventListener("click", connectLive);
document.getElementById("robotSelect").addEventListener("change", (event) => {
  switchRobotProfile(event.target.value);
});

// ---------------------------------------------------------------------------
// 6) VÒNG LẶP RENDER
// ---------------------------------------------------------------------------
function loop(now) {
  requestAnimationFrame(loop);
  advanceLiveInterpolation(now);
  if (state.currentArm) applyJointsDeg(state.currentArm, state.jointsDeg);
  controls.update();
  renderer.render(scene, camera);
}

resizeRenderer();

async function initApp() {
  try {
    const physicalGeometry = await fetchPhysicalGeometry();
    setBoardGeometry(physicalGeometry);

    scene.add(buildBoardGrid(physicalGeometry));
    const { group: piecesGroup, pieces } = buildPieces(physicalGeometry);
    xiangqiPieces = pieces;
    scene.add(piecesGroup);

    await switchRobotProfile(state.robotProfileId);
    loop(performance.now());
  } catch (err) {
    console.error("[VIEWER] ❌ Failed to initialize 3D viewer:", err);
  }
}

initApp();
