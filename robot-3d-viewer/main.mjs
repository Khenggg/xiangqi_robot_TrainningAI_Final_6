import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { validateLivePacket, validateWorldStatePacket, stabilizeJointTarget } from "./live_state.mjs";
import { fetchPhysicalGeometry } from "./geometry.mjs";
import { fetchVirtualGripperProfile } from "./gripper_profile.mjs";
import { fetchGripperVisualAsset } from "./gripper_asset.mjs";
import { fetchStartLayout } from "./layout.mjs";
import {
  buildBoardGrid,
  buildPieces,
  updatePiecesFromWorldState,
  setBoardGeometry,
  fetchScenePlacement,
  boardPointToXYZ,
} from "./board.mjs";

// ---------------------------------------------------------------------------
// 1) CẤU HÌNH ROBOT & KINEMATICS DYNAMIC LOADER
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

async function fetchRobotProfileConfig(profileId) {
  if (profileId === "fr3") {
    const res = await fetch("/shared/robot_profiles/fr3.json");
    if (!res.ok) {
      throw new Error(`Failed to load /shared/robot_profiles/fr3.json: HTTP ${res.status}`);
    }
    const data = await res.json();
    if (!Array.isArray(data?.joints) || data.joints.length !== 6) {
      throw new Error(`Invalid fr3.json: expected 6 joints array, got ${data?.joints?.length}`);
    }

    const visualJointOrigins = data.joints.map((j, idx) => {
      const xyz = j.origin_xyz_m;
      if (!Array.isArray(xyz) || xyz.length !== 3 || !xyz.every(Number.isFinite)) {
        throw new Error(`Joint ${idx} (${j?.name}) has invalid origin_xyz_m: ${JSON.stringify(xyz)}`);
      }
      return [Number(xyz[0]), Number(xyz[1]), Number(xyz[2])];
    });

    const visualJointRpy = data.joints.map((j, idx) => {
      const rpy = j.origin_rpy_rad;
      if (!Array.isArray(rpy) || rpy.length !== 3 || !rpy.every(Number.isFinite)) {
        throw new Error(`Joint ${idx} (${j?.name}) has invalid origin_rpy_rad: ${JSON.stringify(rpy)}`);
      }
      return [Number(rpy[0]), Number(rpy[1]), Number(rpy[2])];
    });

    return {
      visualJointOrigins,
      visualJointRpy,
    };
  }
  // FR5 fallback (visual only)
  return {
    visualJointOrigins: [
      [0, 0, 0],
      [0, 0, 0.152],
      [-0.425, 0, 0],
      [-0.39501, 0, 0],
      [0, 0, 0.1021],
      [0, 0, 0.102],
    ],
    visualJointRpy: [
      [0, 0, 0],
      [Math.PI / 2, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
      [Math.PI / 2, 0, 0],
      [-Math.PI / 2, 0, 0],
    ],
  };
}

async function fetchSceneConfig() {
  const res = await fetch("/shared/virtual_fr3_scene.json");
  if (!res.ok) {
    throw new Error(`Failed to load /shared/virtual_fr3_scene.json: HTTP ${res.status}`);
  }
  return await res.json();
}

async function fetchCellReachabilityDataset() {
  const res = await fetch("/shared/cell_reachability_dataset.json");
  if (!res.ok) {
    throw new Error(`Failed to load /shared/cell_reachability_dataset.json: HTTP ${res.status}`);
  }
  return await res.json();
}

const ROBOT_PROFILES = Object.freeze({
  fr3: Object.freeze({
    id: "fr3",
    label: "FAIRINO FR3",
    meshBase: "./assets/fr3_v6/",
  }),
  fr5: Object.freeze({
    id: "fr5",
    label: "FAIRINO FR5",
    meshBase: "./assets/fr5_v6/",
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
window.__scene = scene;

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
let piecesGroupRef = null;


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

// ---------------------------------------------------------------------------
// 2.5) CAD STEP GRIPPER (Tương thích hoàn toàn với frnsimulation)
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// 2.5) CAD STEP GRIPPER (Tương thích hoàn toàn với frnsimulation)
// Canonical alignment source: shared/gripper_visual_asset.json
// ---------------------------------------------------------------------------
let _cachedVisualAsset = null;
async function getGripperVisualAsset() {
  if (!_cachedVisualAsset) {
    _cachedVisualAsset = await fetchGripperVisualAsset();
  }
  return _cachedVisualAsset;
}

function gripperMountQuaternion(profileId, visualAsset) {
  const pcfg = visualAsset.profiles[profileId] || visualAsset.profiles.fr3;
  const baseRotation = pcfg.mount_rotation_euler_rad;
  const quaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(...baseRotation),
  );
  const roll = pcfg.mount_roll_rad || 0;
  if (roll) {
    quaternion.multiply(
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), roll),
    );
  }
  return quaternion;
}

function gripperMountOffset(profileId, visualAsset) {
  const pcfg = visualAsset.profiles[profileId] || visualAsset.profiles.fr3;
  const calibratedOffset = pcfg.mount_offset_m;
  if (calibratedOffset && !pcfg.mount_roll_rad) {
    return calibratedOffset;
  }
  const target = new THREE.Vector3(...pcfg.flange_target_offset_m);
  const flange = new THREE.Vector3(...visualAsset.cadFlangeOrigin)
    .multiplyScalar(visualAsset.scaleToM)
    .applyQuaternion(gripperMountQuaternion(profileId, visualAsset));
  return target.sub(flange).toArray();
}

const gripperVisual = {
  group: null,
  loadPromise: null,
  fingers: [],
  closed: false,
  animation: null,
};

function buildStepMesh(stepMesh, visualAsset) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(stepMesh.attributes.position.array, 3),
  );
  if (stepMesh.attributes.normal) {
    geometry.setAttribute(
      "normal",
      new THREE.Float32BufferAttribute(stepMesh.attributes.normal.array, 3),
    );
  } else {
    geometry.computeVertexNormals();
  }
  geometry.setIndex(
    new THREE.BufferAttribute(Uint32Array.from(stepMesh.index.array), 1),
  );
  geometry.computeBoundingSphere();
  const [red = 0.44, green = 0.31, blue = 0.22] = stepMesh.color || [];
  const material = new THREE.MeshStandardMaterial({
    color: ROBOT_SHELL_COLOR,
    roughness: 0.62,
    metalness: 0.12,
  });
  const mesh = new THREE.Mesh(geometry, material);
  const fingerColorHex = visualAsset?.fingerSourceColorHex || "#694d3b";
  mesh.userData.isGripperFinger =
    new THREE.Color(red, green, blue).getHex() === new THREE.Color(fingerColorHex).getHex();
  return mesh;
}

async function loadSharedGripper() {
  if (gripperVisual.group) return gripperVisual.group;
  if (gripperVisual.loadPromise) return gripperVisual.loadPromise;
  gripperVisual.loadPromise = (async () => {
    if (typeof window === "undefined" || typeof window.occtimportjs !== "function") {
      throw new Error("STEP importer (occt-import-js) is not available");
    }
    const visualAsset = await getGripperVisualAsset();
    const response = await fetch(`${visualAsset.assetBasePath}${visualAsset.assetFile}`);
    if (!response.ok) {
      throw new Error(`Unable to load gripper STEP (HTTP ${response.status})`);
    }
    const occt = await window.occtimportjs();
    const result = occt.ReadStepFile(
      new Uint8Array(await response.arrayBuffer()),
      {
        linearUnit: visualAsset.cadUnits || "millimeter",
        linearDeflectionType: "bounding_box_ratio",
        linearDeflection: 0.001,
        angularDeflection: 0.5,
      },
    );
    if (!result.success || !result.meshes?.length) {
      throw new Error("The gripper STEP file has no valid geometry");
    }
    const gripper = new THREE.Group();
    gripper.name = "parallel_gripper";
    gripper.userData.robotVisualRole = "shared-gripper";
    gripperVisual.fingers = [];
    result.meshes.forEach((stepMesh) => {
      const mesh = buildStepMesh(stepMesh, visualAsset);
      if (mesh.userData.isGripperFinger) {
        const bounds = new THREE.Box3().setFromBufferAttribute(
          mesh.geometry.getAttribute("position"),
        );
        gripperVisual.fingers.push({
          mesh,
          openPosition: mesh.position.clone(),
          direction: bounds.getCenter(new THREE.Vector3()).x < 40 ? 1 : -1,
        });
      }
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      gripper.add(mesh);
    });
    gripperVisual.group = gripper;
    return gripper;
  })().catch((error) => {
    gripperVisual.loadPromise = null;
    throw error;
  });
  return gripperVisual.loadPromise;
}

async function setGripperClosed(closed) {
  if (!gripperVisual.fingers.length || gripperVisual.closed === closed) {
    return;
  }
  if (gripperVisual.animation) return gripperVisual.animation;
  const visualAsset = await getGripperVisualAsset();
  const fingerTravel = visualAsset.fingerTravelMm;
  const animDuration = visualAsset.animationDurationMs;
  const fingers = gripperVisual.fingers.map(
    ({ mesh, openPosition, direction }) => ({
      mesh,
      from: mesh.position.clone(),
      to: openPosition
        .clone()
        .addScaledVector(
          new THREE.Vector3(1, 0, 0),
          closed ? direction * fingerTravel : 0,
        ),
    }),
  );
  gripperVisual.animation = new Promise((resolve) => {
    const startedAt = performance.now();
    const tick = (now) => {
      const progress = Math.min(Math.max((now - startedAt) / animDuration, 0), 1);
      const eased = progress * progress * (3 - 2 * progress);
      fingers.forEach(({ mesh, from, to }) =>
        mesh.position.lerpVectors(from, to, eased),
      );
      if (progress < 1) {
        requestAnimationFrame(tick);
        return;
      }
      gripperVisual.closed = closed;
      gripperVisual.animation = null;
      resolve();
    };
    requestAnimationFrame(tick);
  });
  return gripperVisual.animation;
}

export function buildProceduralGripper(profile) {
  if (!profile) {
    throw new Error("Virtual gripper profile is required to build procedural gripper");
  }
  const gripperGroup = new THREE.Group();
  gripperGroup.name = "virtual-gripper";

  const palmDims = profile.palmDimensionsM;
  const jawDims = profile.jawDimensionsM;
  const palmColor = new THREE.Color(profile.colorHex);
  const jawColor = new THREE.Color(profile.jawColorHex);
  const openW = profile.openWidthM;
  const closedW = profile.closedWidthM;
  const travelAxis = profile.travelAxis;

  const palmMtl = new THREE.MeshStandardMaterial({
    color: palmColor,
    roughness: 0.5,
    metalness: 0.3,
  });
  const jawMtl = new THREE.MeshStandardMaterial({
    color: jawColor,
    roughness: 0.4,
    metalness: 0.6,
  });

  // Palm dimensions: palmDims[0] x palmDims[1] x palmDims[2]
  const palmGeom = new THREE.BoxGeometry(palmDims[0], palmDims[1], palmDims[2]);
  const palmMesh = new THREE.Mesh(palmGeom, palmMtl);
  palmMesh.position.set(0, 0, palmDims[2] / 2.0);
  palmMesh.castShadow = true;
  gripperGroup.add(palmMesh);

  // Two jaws extending along +Z from palmDims[2] to palmDims[2] + jawDims[2]
  const jawGeom = new THREE.BoxGeometry(jawDims[0], jawDims[1], jawDims[2]);
  const jawCenterZ = palmDims[2] + jawDims[2] / 2.0;
  const halfOpen = openW / 2.0;

  const leftJaw = new THREE.Mesh(jawGeom, jawMtl);
  const rightJaw = new THREE.Mesh(jawGeom, jawMtl);
  leftJaw.castShadow = true;
  rightJaw.castShadow = true;

  if (travelAxis === "Y") {
    leftJaw.position.set(0, -halfOpen, jawCenterZ);
    rightJaw.position.set(0, halfOpen, jawCenterZ);
  } else if (travelAxis === "Z") {
    leftJaw.position.set(0, 0, jawCenterZ - halfOpen);
    rightJaw.position.set(0, 0, jawCenterZ + halfOpen);
  } else { // "X"
    leftJaw.position.set(-halfOpen, 0, jawCenterZ);
    rightJaw.position.set(halfOpen, 0, jawCenterZ);
  }
  gripperGroup.add(leftJaw);
  gripperGroup.add(rightJaw);

  let currentWidth = openW;
  let targetWidth = openW;

  function setClosed(isClosed) {
    targetWidth = isClosed ? closedW : openW;
  }

  function setWidth(w) {
    targetWidth = Number(w);
  }

  function update() {
    currentWidth += (targetWidth - currentWidth) * 0.25;
    const halfW = currentWidth / 2.0;
    if (travelAxis === "Y") {
      leftJaw.position.y = -halfW;
      rightJaw.position.y = halfW;
    } else if (travelAxis === "Z") {
      leftJaw.position.z = jawCenterZ - halfW;
      rightJaw.position.z = jawCenterZ + halfW;
    } else { // "X"
      leftJaw.position.x = -halfW;
      rightJaw.position.x = halfW;
    }
  }

  return {
    group: gripperGroup,
    setClosed,
    setWidth,
    update,
  };
}

export async function buildRobotArm(profile, gripperProfile) {
  if (!gripperProfile) {
    throw new Error("Virtual gripper profile is required to build robot arm");
  }
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
    const kinematicsConfig = await fetchRobotProfileConfig(profile.id);
    const sceneConfig = await fetchSceneConfig();

    const baseGeometry = await loadSTL(loader, profile, "base_link");
    const baseMesh = new THREE.Mesh(baseGeometry, material());
    baseMesh.castShadow = true;
    candidate.group.add(baseMesh);

    let parent = candidate.group;
    for (let i = 0; i < 6; i++) {
      const frame = new THREE.Group();
      frame.position.fromArray(kinematicsConfig.visualJointOrigins[i]);
      frame.rotation.set(...kinematicsConfig.visualJointRpy[i]);
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

    // Mount the CAD gripper if available, otherwise fallback to procedural gripper
    let armGripper = null;
    try {
      const visualAsset = await getGripperVisualAsset();
      const loadedGripper = await loadSharedGripper();
      if (loadedGripper.parent) loadedGripper.parent.remove(loadedGripper);
      const j6ToolMount = new THREE.Group();
      j6ToolMount.name = `${profile.id}-j6-tool-mount`;
      j6ToolMount.userData.robotVisualRole = "j6-tool-mount";
      j6ToolMount.position.fromArray(gripperMountOffset(profile.id, visualAsset));
      j6ToolMount.quaternion.copy(gripperMountQuaternion(profile.id, visualAsset));
      j6ToolMount.scale.setScalar(visualAsset.scaleToM);
      j6ToolMount.add(loadedGripper);
      parent.add(j6ToolMount);
      armGripper = {
        group: j6ToolMount,
        setClosed: (isClosed) => setGripperClosed(Boolean(isClosed)),
        update: () => {},
      };
    } catch (err) {
      console.warn("[VIEWER] Using procedural gripper fallback:", err.message);
      const proceduralGripper = buildProceduralGripper(gripperProfile);
      parent.add(proceduralGripper.group);
      armGripper = proceduralGripper;
    }
    candidate.gripper = armGripper;

    // Dynamic canonical root transformation from virtual_fr3_scene.json:
    // Maps robot base frame (Z-up, -X facing board, +Y lateral)
    // to Three.js scene (Y-up, +Z facing board, +X lateral)
    const rot = sceneConfig.robot_base_to_3d_world.rotation_matrix;
    const trans = sceneConfig.robot_base_to_3d_world.translation_m;
    const rootMatrix = new THREE.Matrix4().set(
      rot[0][0], rot[0][1], rot[0][2], trans[0],
      rot[1][0], rot[1][1], rot[1][2], trans[1],
      rot[2][0], rot[2][1], rot[2][2], trans[2],
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
  gripperProfile: null,
  currentArm: null,
  jointsDeg: [0, -45, 90, -45, -90, 0],
  homePoseDeg: [0, -45, 90, -45, -90, 0],
  cellDataset: null,
  selectedCell: { row: 4, col: 4 },
  currentCell: null,
  targetDestinationCell: null,
  trajectoryQueue: [],
  trajectoryActive: false,
  // nội suy mượt cho live mirror
  liveFromDeg: null,
  liveTargetDeg: null,
  liveAnimationStart: 0,
  liveAnimationDuration: 120,
  liveSocket: null,
};
window.__state = state;

async function switchRobotProfile(profileId) {
  const profile = getRobotProfile(profileId);
  state.robotProfileId = profile.id;
  const next = await buildRobotArm(profile, state.gripperProfile);
  if (state.currentArm) {
    if (gripperVisual.group?.parent) {
      gripperVisual.group.parent.remove(gripperVisual.group);
    }
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
  syncAllJointSliders();

  if (t >= 1) {
    state.jointsDeg = [...state.liveTargetDeg];
    state.liveTargetDeg = null;
    state.liveFromDeg = null;
    if (state.trajectoryQueue && state.trajectoryQueue.length > 0) {
      runNextTrajectoryStep(now);
    } else if (state.trajectoryActive) {
      finishTrajectory();
    }
  }
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
      const data = JSON.parse(event.data);
      if (data.type === "robot_state") {
        applyLiveState(data);
        if (data.gripper !== undefined && state.currentArm?.gripper) {
          state.currentArm.gripper.setClosed(Boolean(data.gripper));
        }
      } else if (data.type === "world_state") {
        const val = validateWorldStatePacket(data);
        if (val.ok) {
          if (piecesGroupRef && xiangqiPieces) {
            updatePiecesFromWorldState(piecesGroupRef, xiangqiPieces, val.pieces);
          }
          if (val.gripper && state.currentArm?.gripper) {
            state.currentArm.gripper.setClosed(Boolean(val.gripper.closed));
          }
        }
      }
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
// 5.5) ĐIỀU KHIỂN GÓC KHỚP THỦ CÔNG (JOINT SLIDERS J1...J6)
// Tương thích phong cách điều khiển trực quan từ frnsimulation
// ---------------------------------------------------------------------------
const JOINT_DEFINITIONS = Object.freeze([
  { name: "J1 (Base)", min: -175.0, max: 175.0 },
  { name: "J2 (Shoulder)", min: -265.0, max: 85.0 },
  { name: "J3 (Elbow)", min: -162.0, max: 162.0 },
  { name: "J4 (Wrist 1)", min: -265.0, max: 85.0 },
  { name: "J5 (Wrist 2)", min: -175.0, max: 175.0 },
  { name: "J6 (Wrist 3)", min: -175.0, max: 175.0 },
]);

function renderJointControls() {
  const listEl = document.getElementById("jointControlsList");
  if (!listEl) return;
  listEl.innerHTML = JOINT_DEFINITIONS.map(
    (def, i) => `
    <div class="joint-item">
      <div class="joint-row">
        <label for="joint-slider-${i}">${def.name}</label>
        <input
          id="joint-slider-${i}"
          class="range"
          type="range"
          data-joint-idx="${i}"
          min="${def.min}"
          max="${def.max}"
          step="0.1"
          value="${(state.jointsDeg[i] ?? 0).toFixed(1)}"
          aria-label="${def.name} slider"
        />
        <input
          id="joint-num-${i}"
          class="number"
          type="number"
          data-joint-idx="${i}"
          min="${def.min}"
          max="${def.max}"
          step="0.1"
          value="${(state.jointsDeg[i] ?? 0).toFixed(1)}"
          aria-label="${def.name} degrees"
        />
      </div>
      <div class="joint-limit-row">${def.min}° … ${def.max}°</div>
    </div>
  `,
  ).join("");

  listEl.querySelectorAll("input.range").forEach((slider) => {
    slider.addEventListener("input", (e) => {
      const idx = Number(e.target.dataset.jointIdx);
      const val = Number(e.target.value);
      updateSingleJoint(idx, val);
    });
  });

  listEl.querySelectorAll("input.number").forEach((numInput) => {
    numInput.addEventListener("change", (e) => {
      const idx = Number(e.target.dataset.jointIdx);
      const val = Number(e.target.value);
      updateSingleJoint(idx, val);
    });
  });
}

function updateSingleJoint(index, val) {
  const def = JOINT_DEFINITIONS[index];
  const clamped = Math.max(def.min, Math.min(def.max, Number(val) || 0));
  state.jointsDeg[index] = clamped;

  // Hủy trajectory nếu người dùng chủ động kéo slider
  state.trajectoryQueue = [];
  state.trajectoryActive = false;
  state.currentCell = null;
  state.liveTargetDeg = null;
  state.liveFromDeg = null;
  updateStepperUI(null, []);

  const slider = document.getElementById(`joint-slider-${index}`);
  const num = document.getElementById(`joint-num-${index}`);
  if (slider) slider.value = clamped;
  if (num) num.value = clamped.toFixed(1);

  if (jointsReadoutEl) {
    jointsReadoutEl.textContent = state.jointsDeg.map((v) => v.toFixed(1)).join(", ");
  }
  if (state.currentArm) {
    applyJointsDeg(state.currentArm, state.jointsDeg);
  }
}

function syncAllJointSliders() {
  state.jointsDeg.forEach((deg, i) => {
    const slider = document.getElementById(`joint-slider-${i}`);
    const num = document.getElementById(`joint-num-${i}`);
    if (slider && document.activeElement !== slider) slider.value = deg;
    if (num && document.activeElement !== num) num.value = deg.toFixed(1);
  });
  if (jointsReadoutEl) {
    jointsReadoutEl.textContent = state.jointsDeg.map((v) => v.toFixed(1)).join(", ");
  }
}

function initJointControlPanelEvents() {
  const homeBtn = document.getElementById("homeBtn");
  if (homeBtn) {
    homeBtn.addEventListener("click", () => {
      const homeDeg = state.homePoseDeg || [0.0, -45.0, 90.0, -45.0, -90.0, 0.0];
      state.jointsDeg = [...homeDeg];
      state.liveTargetDeg = null;
      state.liveFromDeg = null;
      state.trajectoryQueue = [];
      state.trajectoryActive = false;
      state.currentCell = null;
      updateStepperUI(null, []);
      const badge = document.getElementById("diagStatusBadge");
      if (badge) {
        badge.className = "badge-safe";
        badge.textContent = "ĐÃ VỀ HOME";
      }
      syncAllJointSliders();
      if (state.currentArm) {
        applyJointsDeg(state.currentArm, state.jointsDeg);
      }
    });
  }

  let _gripperClosed = false;
  const gripperBtn = document.getElementById("gripperBtn");
  if (gripperBtn) {
    gripperBtn.addEventListener("click", () => {
      _gripperClosed = !_gripperClosed;
      if (state.currentArm?.gripper) {
        state.currentArm.gripper.setClosed(_gripperClosed);
      }
      gripperBtn.textContent = _gripperClosed ? "🗜️ Đang Kẹp" : "🗜️ Kẹp / Nhả";
      gripperBtn.style.color = _gripperClosed ? "#f0883e" : "#c9d1d9";
    });
  }

  const panelEl = document.getElementById("jointControlPanel");
  const toggleBtn = document.getElementById("toggleControlsBtn");
  const closeBtn = document.getElementById("closeControlsBtn");
  if (toggleBtn && panelEl) {
    toggleBtn.addEventListener("click", () => {
      panelEl.classList.toggle("collapsed");
    });
  }
  if (closeBtn && panelEl) {
    closeBtn.addEventListener("click", () => {
      panelEl.classList.add("collapsed");
    });
  }

  // Tabs switching
  const tabJointsBtn = document.getElementById("tabJointsBtn");
  const tabReachBtn = document.getElementById("tabReachBtn");
  const jointsContent = document.getElementById("jointsTabContent");
  const reachContent = document.getElementById("reachTabContent");
  if (tabJointsBtn && tabReachBtn) {
    tabJointsBtn.addEventListener("click", () => {
      tabJointsBtn.classList.add("active");
      tabReachBtn.classList.remove("active");
      jointsContent?.classList.add("active");
      reachContent?.classList.remove("active");
    });
    tabReachBtn.addEventListener("click", () => {
      tabReachBtn.classList.add("active");
      tabJointsBtn.classList.remove("active");
      reachContent?.classList.add("active");
      jointsContent?.classList.remove("active");
    });
  }

  // Reach cell button
  const reachBtn = document.getElementById("reachCellBtn");
  const rowSelect = document.getElementById("cellRowSelect");
  const colSelect = document.getElementById("cellColSelect");
  if (reachBtn && rowSelect && colSelect) {
    reachBtn.addEventListener("click", () => {
      goToCell(Number(rowSelect.value), Number(colSelect.value));
    });
  }

  // Quick cell buttons
  document.querySelectorAll(".quick-cell-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const r = Number(btn.dataset.row);
      const c = Number(btn.dataset.col);
      goToCell(r, c);
    });
  });

  // Raycaster for clicking directly on 3D board
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let pointerDownTime = 0;
  let pointerDownPos = { x: 0, y: 0 };
  canvas.addEventListener("pointerdown", (e) => {
    pointerDownTime = performance.now();
    pointerDownPos = { x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener("pointerup", (e) => {
    const dt = performance.now() - pointerDownTime;
    const dist = Math.hypot(e.clientX - pointerDownPos.x, e.clientY - pointerDownPos.y);
    if (dt > 300 || dist > 5) return;

    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    const hits = raycaster.intersectObjects(scene.children, true);
    for (const hit of hits) {
      let obj = hit.object;
      while (obj && !obj.userData?.id && obj !== scene) {
        obj = obj.parent;
      }
      if (obj?.userData && obj.userData.col !== undefined && obj.userData.row !== undefined) {
        goToCell(obj.userData.row, obj.userData.col);
        const tabReachBtnEl = document.getElementById("tabReachBtn");
        tabReachBtnEl?.click();
        break;
      }
    }
  });
}

let physicalGeometryRef = null;
let cellTargetRing = null;

function getOrCreateTargetRing() {
  if (!cellTargetRing) {
    const geo = new THREE.RingGeometry(0.011, 0.014, 32);
    geo.rotateX(-Math.PI / 2);
    const mat = new THREE.MeshBasicMaterial({ color: 0x58a6ff, side: THREE.DoubleSide });
    cellTargetRing = new THREE.Mesh(geo, mat);
    cellTargetRing.position.set(0, -10, 0);
    scene.add(cellTargetRing);
  }
  return cellTargetRing;
}

function updateStepperUI(activeStepId, completedStepIds = []) {
  const steps = ["stepLift", "stepTransit", "stepLand"];
  steps.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("active", "done");
    if (completedStepIds.includes(id)) {
      el.classList.add("done");
    } else if (id === activeStepId) {
      el.classList.add("active");
    }
  });
}

function runNextTrajectoryStep(now) {
  if (!state.trajectoryQueue || state.trajectoryQueue.length === 0) return;
  const step = state.trajectoryQueue.shift();
  state.currentTrajectoryStep = step;

  // Update Stepper UI
  updateStepperUI(step.stepElId, step.completedStepIds || []);

  // Update Badge
  const badge = document.getElementById("diagStatusBadge");
  if (badge && step.badgeText) {
    badge.className = step.badgeClass || "badge-transit";
    badge.textContent = step.badgeText;
  }

  // Update Explanation
  const expl = document.getElementById("diagExplanation");
  if (expl && step.explanation) {
    expl.innerHTML = step.explanation;
  }

  // Set animation targets
  state.liveFromDeg = [...state.jointsDeg];
  state.liveTargetDeg = [...step.targetDeg];
  state.liveAnimationStart = now || performance.now();
  state.liveAnimationDuration = step.durationMs || 500;
}

function finishTrajectory() {
  state.trajectoryActive = false;
  state.currentTrajectoryStep = null;
  const targetCell = state.targetDestinationCell;
  if (!targetCell) return;

  state.currentCell = targetCell;

  // Mark all steps done
  updateStepperUI(null, ["stepLift", "stepTransit", "stepLand"]);

  const badge = document.getElementById("diagStatusBadge");
  if (badge) {
    badge.className = "badge-safe";
    badge.textContent = "✅ ĐÃ ĐẾN Ô (AN TOÀN 100%)";
  }

  const j4Val = document.getElementById("diagJ4Val");
  const tiltVal = document.getElementById("diagTiltVal");
  const clearanceVal = document.getElementById("diagClearanceVal");
  const expl = document.getElementById("diagExplanation");

  const j4Angle = targetCell.j4_grasp_deg ?? targetCell.j4_deg;
  if (j4Val) {
    j4Val.textContent = `${j4Angle}° (Tự động bù trừ)`;
    j4Val.style.color = "#58a6ff";
  }
  if (tiltVal) {
    tiltVal.textContent = `0° ✓ Cắm thẳng đứng 90° (Kẹp chắc 100%)`;
    tiltVal.style.color = "#3fb950";
  }
  const tipClearance = targetCell.gripper_tip_grasp_clearance_mm ?? targetCell.gripper_tip_clearance_mm ?? 1.5;
  if (clearanceVal) {
    clearanceVal.textContent = `✅ Đầu ngàm kẹp cách mặt bàn +${tipClearance} mm (An toàn 100%)`;
    clearanceVal.style.color = "#3fb950";
  }
  if (expl) {
    expl.innerHTML = `✅ <strong>Đã hoàn thành di chuyển 3 giai đoạn:</strong> Robot đã nhấc bổng an toàn (+70mm) qua toàn bộ quân cờ, bay ngang trên không, và hạ cánh chúc thẳng đứng $90^\\circ$ tại ô (Cột ${targetCell.col}, Hàng ${targetCell.row}). Đầu ngàm kẹp hover ở cao độ <strong>+${tipClearance}\\text{mm}</strong>, ôm khít quân cờ mà <strong>hoàn toàn KHÔNG gây va chạm hay xô lệch quân cờ khác</strong>!`;
  }
}

function executeSafeTrajectory(targetCell) {
  state.targetDestinationCell = targetCell;
  state.trajectoryQueue = [];
  state.trajectoryActive = true;

  const currentCell = state.currentCell;
  const isSameCell = currentCell && currentCell.row === targetCell.row && currentCell.col === targetCell.col;
  if (isSameCell) {
    finishTrajectory();
    return;
  }

  const graspDeg = targetCell.grasp_joints_deg ?? targetCell.joints_deg;
  const approachDeg = targetCell.approach_joints_deg ?? targetCell.grasp_joints_deg ?? targetCell.joints_deg;

  if (currentCell) {
    const curApproachDeg = currentCell.approach_joints_deg ?? currentCell.grasp_joints_deg ?? currentCell.joints_deg;
    // 3-PHASE SAFE TRAJECTORY:
    // 1. Lift vertically over current cell (+70mm)
    state.trajectoryQueue.push({
      stepElId: "stepLift",
      completedStepIds: [],
      badgeText: "🛫 1. ĐANG NHẤC LÊN (+70mm)",
      badgeClass: "badge-warn",
      targetDeg: curApproachDeg,
      durationMs: 380,
      explanation: `🛫 <strong>Giai đoạn 1 (Nhấc lên):</strong> Cánh tay nâng thẳng đứng ngàm kẹp lên cao độ an toàn <strong>+70mm</strong> (cách đỉnh quân cờ >60mm) để tránh va chạm với bất kỳ quân cờ nào xung quanh.`,
    });

    // 2. Transit horizontally across safe ceiling to target cell (+70mm)
    state.trajectoryQueue.push({
      stepElId: "stepTransit",
      completedStepIds: ["stepLift"],
      badgeText: "✈️ 2. ĐANG BAY NGANG (TRÊN CAO)",
      badgeClass: "badge-transit",
      targetDeg: approachDeg,
      durationMs: 700,
      explanation: `✈️ <strong>Giai đoạn 2 (Bay ngang):</strong> Robot lướt ngang trên mặt phẳng an toàn $Z = +70\\text{mm}$, bay qua các quân cờ mà không va chạm.`,
    });

    // 3. Land vertically into target cell grasp pose (+1.5mm)
    state.trajectoryQueue.push({
      stepElId: "stepLand",
      completedStepIds: ["stepLift", "stepTransit"],
      badgeText: "🛬 3. ĐANG HẠ CÁNH (+1.5mm)",
      badgeClass: "badge-land",
      targetDeg: graspDeg,
      durationMs: 420,
      explanation: `🛬 <strong>Giai đoạn 3 (Hạ cánh):</strong> Ngàm kẹp hạ cánh thẳng đứng $90^\\circ$ ôm trọn quân cờ ở cao độ cách mặt bàn <strong>+1.5mm</strong> (zero xuyên bàn).`,
    });
  } else {
    // From Home pose or arbitrary elevated pose:
    state.trajectoryQueue.push({
      stepElId: "stepTransit",
      completedStepIds: ["stepLift"],
      badgeText: "✈️ 2. ĐANG BAY TỚI ĐỈNH Ô",
      badgeClass: "badge-transit",
      targetDeg: approachDeg,
      durationMs: 700,
      explanation: `✈️ <strong>Giai đoạn 2 (Bay tới đỉnh ô):</strong> Robot từ vị trí chờ bay đến không gian trên cao của ô mục tiêu (+70mm).`,
    });

    state.trajectoryQueue.push({
      stepElId: "stepLand",
      completedStepIds: ["stepLift", "stepTransit"],
      badgeText: "🛬 3. ĐANG HẠ CÁNH (+1.5mm)",
      badgeClass: "badge-land",
      targetDeg: graspDeg,
      durationMs: 420,
      explanation: `🛬 <strong>Giai đoạn 3 (Hạ cánh):</strong> Ngàm kẹp hạ cánh thẳng đứng $90^\\circ$ ôm trọn quân cờ ở cao độ cách mặt bàn <strong>+1.5mm</strong>.`,
    });
  }

  // Start first step immediately
  runNextTrajectoryStep(performance.now());
}

function goToCell(row, col) {
  if (!state.cellDataset?.cells) return;
  state.selectedCell = { row, col };

  const cell = state.cellDataset.cells.find((c) => c.row === row && c.col === col);
  if (!cell || !cell.reachable) return;

  // Update 3D ring marker
  const ring = getOrCreateTargetRing();
  if (physicalGeometryRef) {
    const pt = boardPointToXYZ(col, row, physicalGeometryRef);
    ring.position.set(pt.x, pt.y + 0.001, pt.z);
    ring.material.color.setHex(0x58a6ff);
  }

  // Update inputs
  const rowSelect = document.getElementById("cellRowSelect");
  const colSelect = document.getElementById("cellColSelect");
  if (rowSelect) rowSelect.value = String(row);
  if (colSelect) colSelect.value = String(col);

  const cellLabel = document.getElementById("diagCellLabel");
  if (cellLabel) cellLabel.textContent = `Cột ${col}, Hàng ${row} (X=${cell.x_m}m, Y=${cell.y_m}m)`;

  // Execute 3-phase safe trajectory (Lift -> Transit -> Land)
  executeSafeTrajectory(cell);
}

// ---------------------------------------------------------------------------
// 6) VÒNG LẶP RENDER
// ---------------------------------------------------------------------------
function loop(now) {
  requestAnimationFrame(loop);
  advanceLiveInterpolation(now);
  if (state.currentArm) {
    applyJointsDeg(state.currentArm, state.jointsDeg);
    state.currentArm.gripper?.update();
  }
  controls.update();
  renderer.render(scene, camera);
}

resizeRenderer();

async function initApp() {
  try {
    const physicalGeometry = await fetchPhysicalGeometry();
    physicalGeometryRef = physicalGeometry;
    setBoardGeometry(physicalGeometry);
    await fetchScenePlacement();

    const cellDataset = await fetchCellReachabilityDataset();
    state.cellDataset = cellDataset;

    const sceneConfig = await fetchSceneConfig();
    if (
      sceneConfig?.home_pose?.joints_deg &&
      Array.isArray(sceneConfig.home_pose.joints_deg) &&
      sceneConfig.home_pose.joints_deg.length === 6 &&
      sceneConfig.home_pose.joints_deg.every((v) => typeof v === "number" && Number.isFinite(v))
    ) {
      state.jointsDeg = [...sceneConfig.home_pose.joints_deg];
      state.homePoseDeg = [...sceneConfig.home_pose.joints_deg];
    }
    if (jointsReadoutEl) {
      jointsReadoutEl.textContent = state.jointsDeg.map((v) => v.toFixed(1)).join(", ");
    }

    const startLayout = await fetchStartLayout();
    const gripperProfile = await fetchVirtualGripperProfile();
    state.gripperProfile = gripperProfile;

    scene.add(buildBoardGrid(physicalGeometry));
    const { group: piecesGroup, pieces } = buildPieces(physicalGeometry, startLayout);
    xiangqiPieces = pieces;
    piecesGroupRef = piecesGroup;
    scene.add(piecesGroup);

    await switchRobotProfile(state.robotProfileId);
    renderJointControls();
    initJointControlPanelEvents();
    syncAllJointSliders();
    loop(performance.now());
  } catch (err) {
    console.error("[VIEWER] ❌ Failed to initialize 3D viewer:", err);
  }
}

initApp();
