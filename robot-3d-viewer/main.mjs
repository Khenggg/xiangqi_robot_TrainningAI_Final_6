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
  setScenePlacement,
  getScenePlacement,
  getActiveBoardGroup,
  getBoardVisualRoot,
  boardPointToXYZ,
} from "./board.mjs";
import { buildCoordinateRulerGroup, createDimensionTape } from "./ruler.mjs";

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
window.__camera = camera;
window.__controls = controls;

scene.add(new THREE.HemisphereLight(0xffffff, 0x1a1f27, 1.1));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.4);
keyLight.position.set(1.5, 2.5, 1.2);
scene.add(keyLight);

const grid = new THREE.GridHelper(1.6, 16, 0x2a3140, 0x1c212b);
scene.add(grid);

let xiangqiPieces = null;
let piecesGroupRef = null;
let coordinateRulerGroup = null;
let activeDimensionTape = null;


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
  trajectoryStage: "IDLE",
  gripperClosed: false,
  liveSocket: null,
  placementVersion: 1,
  forwardShiftMm: 0.0,
  safeTransitHeightMm: 70.0,
  boardHeightOffsetMm: 0.0,
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
  // Authoritative joints directly from backend telemetry
  state.jointsDeg = [...validation.joints];
  syncAllJointSliders();
  if (state.currentArm) {
    applyJointsDeg(state.currentArm, state.jointsDeg);
  }
  if (jointsReadoutEl) {
    jointsReadoutEl.textContent = state.jointsDeg.map((v) => v.toFixed(1)).join(", ");
  }

  // Authoritative trajectory stage directly from backend telemetry
  if (payload.trajectory_stage) {
    state.trajectoryStage = payload.trajectory_stage;
    handleBackendTrajectoryStage(payload.trajectory_stage, payload);
  }

  // Backend error / collision rejection notification
  if (payload.motion_state === "COLLISION_REJECTED" || payload.last_error) {
    handleBackendError(payload.last_error || "Chuyển động bị từ chối bởi Collision Guard");
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
        if (data.placement_version !== undefined) {
          state.placementVersion = Number(data.placement_version);
          const verBadge = document.getElementById("placementVersionBadge");
          if (verBadge) verBadge.textContent = `VER: ${data.placement_version}`;
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
      } else if (data.type === "board_placement") {
        // Authoritative runtime placement packet from Python backend
        applyAuthoritativeBoardPlacement(data);
      } else if (data.type === "placement_analysis") {
        applyPlacementAnalysisUI(data);
      } else if (data.type === "placement_validation_result") {
        updatePlacementValidationResultUI(data);
      } else if (data.type === "full_route_validation_result") {
        updateFullRouteValidationResultUI(data);
      } else if (data.type === "trajectory_result") {
        if (data.placement_version !== undefined) {
          state.placementVersion = Number(data.placement_version);
          const verBadge = document.getElementById("placementVersionBadge");
          if (verBadge) verBadge.textContent = `VER: ${data.placement_version}`;
        }
        if (!data.success) {
          handleBackendError(data.error || `Quỹ đạo thất bại ở giai đoạn ${data.failed_stage}`);
        }
      } else if (data.type === "backend_data_reset") {
        const badge = document.getElementById("diagStatusBadge");
        if (badge) {
          badge.className = "badge-safe";
          badge.textContent = "ĐÃ RESET BACKEND";
        }
        const expl = document.getElementById("diagExplanation");
        if (expl) {
          expl.innerHTML = `✅ <strong>Khởi động lại backend thành công:</strong> Toàn bộ dữ liệu backend, vị trí 32 quân cờ, góc khớp robot và vị trí bàn cờ đã được phục hồi về trạng thái ban đầu.`;
        }
        updateStepperUI(null, []);
        state.currentCell = null;
        if (data.placement) {
          applyAuthoritativeBoardPlacement(data.placement);
        }
      } else if (data.type === "operation_state") {
        updateOperationStateUI(data.state);
      } else if (data.type === "error") {
        handleBackendError(data.message || "Lỗi backend");
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

  const slider = document.getElementById(`joint-slider-${index}`);
  const num = document.getElementById(`joint-num-${index}`);
  if (slider) slider.value = clamped;
  if (num) num.value = clamped.toFixed(1);

  if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
    // Single Motion Authority: slider input dispatches intent to backend
    // Backend validates, collision-checks, moves physics, and returns authoritative telemetry
    const targetJoints = [...state.jointsDeg];
    targetJoints[index] = clamped;
    state.liveSocket.send(JSON.stringify({
      command: "MOVE_JOINT",
      joints_deg: targetJoints,
    }));
  } else {
    // Non-authoritative offline preview
    state.jointsDeg[index] = clamped;
    state.currentCell = null;
    updateStepperUI(null, []);
    if (jointsReadoutEl) {
      jointsReadoutEl.textContent = state.jointsDeg.map((v) => v.toFixed(1)).join(", ") + " (PREVIEW)";
    }
    if (state.currentArm) {
      applyJointsDeg(state.currentArm, state.jointsDeg);
    }
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

// ---------------------------------------------------------------------------
// 5.6) PHÂN TÍCH & ĐIỀU KHIỂN VỊ TRÍ BÀN CỜ ĐỘNG (DYNAMIC BOARD PLACEMENT)
// ---------------------------------------------------------------------------
export function computeGeometricPrecheck(d_mm, H_mm, z_board_mm = 10.5, yaw_deg = 90.0) {
  const R = 650.0;
  const L_tool = 150.0; // Canonical measured flange-to-TCP [MEASURED_APPROXIMATE] (CAD: 147.5mm, Legacy 218mm OBSOLETE)
  const piece_h = 9.43;
  const z_tcp_grasp = z_board_mm + piece_h / 2.0;
  const z_flange_grasp = z_tcp_grasp + L_tool;
  const z_flange_app = z_board_mm + H_mm + L_tool;

  const theta = (yaw_deg * Math.PI) / 180.0;
  const sinT = Math.sin(theta);
  const cosT = Math.cos(theta);

  const robCenterX_mm = -(360.0 + d_mm);
  const robCenterY_mm = 0.0;

  // Evaluate all 90 cells to find extrema dynamically via BoardPose
  let maxFlangeAppDist = 0.0;
  let maxFlangeGraspDist = 0.0;
  let maxGridDist = 0.0;
  let minGridDist = Infinity;
  let minGridDepth = Infinity;
  let maxGridDepth = 0.0;
  let farthestCell = [0, 8];
  let nearestCell = [4, 0];
  let farX = -(520.0 + d_mm);
  let farY = 180.0;

  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const u_mm = (c - 4.0) * 40.0;
      const v_mm = (r - 4.5) * 40.0;
      const cellX_mm = -sinT * u_mm - cosT * v_mm + robCenterX_mm;
      const cellY_mm =  cosT * u_mm - sinT * v_mm + robCenterY_mm;

      const gridDist = Math.hypot(cellX_mm, cellY_mm);
      const gridDepth = Math.abs(cellX_mm);
      const flangeGraspDist = Math.hypot(cellX_mm, cellY_mm, z_flange_grasp);
      const flangeAppDist = Math.hypot(cellX_mm, cellY_mm, z_flange_app);

      if (gridDist < minGridDist) {
        minGridDist = gridDist;
        nearestCell = [r, c];
      }
      if (gridDist > maxGridDist) {
        maxGridDist = gridDist;
      }
      if (gridDepth < minGridDepth) {
        minGridDepth = gridDepth;
      }
      if (gridDepth > maxGridDepth) {
        maxGridDepth = gridDepth;
      }
      if (flangeAppDist > maxFlangeAppDist) {
        maxFlangeAppDist = flangeAppDist;
        farthestCell = [r, c];
        farX = cellX_mm;
        farY = cellY_mm;
      }
      if (flangeGraspDist > maxFlangeGraspDist) {
        maxFlangeGraspDist = flangeGraspDist;
      }
    }
  }

  // Physical board corners (width 367mm along u, length 410mm along v)
  const hw_mm = 367.0 / 2.0;
  const hl_mm = 410.0 / 2.0;
  const corners = [
    [-hw_mm, -hl_mm],
    [-hw_mm,  hl_mm],
    [ hw_mm, -hl_mm],
    [ hw_mm,  hl_mm],
  ];
  let nearEdgeDist = Infinity;
  let farEdgeDist = 0.0;
  for (const [cu, cv] of corners) {
    const cx = -sinT * cu - cosT * cv + robCenterX_mm;
    const absX = Math.abs(cx);
    if (absX < nearEdgeDist) nearEdgeDist = absX;
    if (absX > farEdgeDist) farEdgeDist = absX;
  }
  const boardCenterDist = Math.abs(robCenterX_mm);

  // Dynamic d_max and H_max derived from farthest transformed cell
  const rad_d = R * R - farY * farY - z_flange_app * z_flange_app;
  const x_base_far = Math.abs(farX) - d_mm;
  const d_max = rad_d >= 0 ? Math.sqrt(rad_d) - x_base_far : null;

  const rad_h = R * R - farY * farY - farX * farX;
  const H_max = rad_h >= 0 ? Math.sqrt(rad_h) - z_board_mm - L_tool : null;

  const pass = maxFlangeGraspDist <= R && maxFlangeAppDist <= R && d_mm >= -20.0;

  return {
    D_far_grasp: maxFlangeGraspDist,
    D_far_app: maxFlangeAppDist,
    grasp_margin: R - maxFlangeGraspDist,
    app_margin: R - maxFlangeAppDist,
    d_max,
    H_max,
    pass,
    nearest_cell: nearestCell,
    nearest_cell_distance_mm: minGridDist,
    farthest_cell: farthestCell,
    farthest_cell_distance_mm: maxGridDist,
    near_grid_depth_mm: minGridDepth,
    far_grid_depth_mm: maxGridDepth,
    near_board_edge_distance_mm: nearEdgeDist,
    far_board_edge_distance_mm: farEdgeDist,
    board_center_distance_mm: boardCenterDist,
  };
}

function updateGeometricPrecheckUI(d_mm, H_mm, z_off_mm = 0.0, yaw_deg = 90.0) {
  const z_board = 10.5 + z_off_mm;
  const res = computeGeometricPrecheck(d_mm, H_mm, z_board, yaw_deg);
  const elD = document.getElementById("readoutShiftD");
  const elNearGrid = document.getElementById("readoutNearGridDepth") || document.getElementById("readoutRow0Dist");
  const elFarGrid = document.getElementById("readoutFarGridDepth") || document.getElementById("readoutRow9Dist");
  const elNear = document.getElementById("readoutNearEdgeDist");
  const elCenter = document.getElementById("readoutCenterDist");
  const elFar = document.getElementById("readoutFarEdgeDist");
  const elH = document.getElementById("readoutHVal");
  const elFarGrasp = document.getElementById("readoutFarGraspDist");
  const elFarApp = document.getElementById("readoutFarAppDist");
  const elGraspMargin = document.getElementById("readoutGraspMargin");
  const elAppMargin = document.getElementById("readoutAppMargin");
  const elDMax = document.getElementById("readoutDMax");
  const elHMax = document.getElementById("readoutHMax");
  const badge = document.getElementById("geomPrecheckBadge");

  if (elD) elD.textContent = `${d_mm.toFixed(1)} mm`;
  if (elNearGrid) elNearGrid.textContent = `${res.near_grid_depth_mm.toFixed(1)} mm`;
  if (elFarGrid) elFarGrid.textContent = `${res.far_grid_depth_mm.toFixed(1)} mm`;
  if (elNear) elNear.textContent = `${res.near_board_edge_distance_mm.toFixed(1)} mm`;
  if (elCenter) elCenter.textContent = `${res.board_center_distance_mm.toFixed(1)} mm`;
  if (elFar) elFar.textContent = `${res.far_board_edge_distance_mm.toFixed(1)} mm`;
  if (elH) elH.textContent = `${H_mm.toFixed(1)} mm`;

  if (elFarGrasp) elFarGrasp.textContent = `${res.D_far_grasp.toFixed(1)} mm`;
  if (elFarApp) elFarApp.textContent = `${res.D_far_app.toFixed(1)} mm`;
  if (elGraspMargin) elGraspMargin.textContent = `${res.grasp_margin.toFixed(1)} mm`;
  if (elAppMargin) elAppMargin.textContent = `${res.app_margin.toFixed(1)} mm`;
  if (elDMax) elDMax.textContent = res.d_max !== null ? `${res.d_max.toFixed(1)} mm` : "VÔ NGHIỆM";
  if (elHMax) elHMax.textContent = res.H_max !== null ? `${res.H_max.toFixed(1)} mm` : "VÔ NGHIỆM";

  if (badge) {
    badge.className = res.pass ? "badge-safe" : "badge-warn";
    badge.textContent = res.pass ? "GEOMETRIC PASS" : "GEOMETRIC FAIL";
  }
}

export function applyAuthoritativeBoardPlacement(packet) {
  if (!packet) return;

  // 1 & 2. Atomically update board visual root & active scene placement cache
  setScenePlacement(packet);

  // 3, 4, 5, 6. Atomically update authoritative state values
  const d = Number(packet.forward_shift_mm ?? state.forwardShiftMm ?? 0.0);
  const h = Number(packet.safe_transit_height_mm ?? state.safeTransitHeightMm ?? 70.0);
  const zOff = Number(packet.board_height_offset_mm ?? state.boardHeightOffsetMm ?? 0.0);
  const ver = Number(packet.placement_version ?? state.placementVersion ?? 1);

  state.forwardShiftMm = d;
  state.safeTransitHeightMm = h;
  state.boardHeightOffsetMm = zOff;
  state.boardSurfaceHeightM = Number(packet.board_surface_z_m ?? packet.board_surface_z_robot_m ?? (0.0105 + zOff / 1000.0));
  state.placementVersion = ver;

  // Sync placement control UI
  const shiftSlider = document.getElementById("boardShiftSlider");
  const shiftNum = document.getElementById("boardShiftNum");
  const transitSlider = document.getElementById("safeTransitSlider");
  const transitNum = document.getElementById("safeTransitNum");
  const zOffsetNum = document.getElementById("boardZOffsetNum");
  const verBadge = document.getElementById("placementVersionBadge");

  if (shiftSlider) shiftSlider.value = String(d);
  if (shiftNum) shiftNum.value = String(d);
  if (transitSlider) transitSlider.value = String(h);
  if (transitNum) transitNum.value = String(h);
  if (zOffsetNum) zOffsetNum.value = String(zOff);
  if (verBadge) verBadge.textContent = `VER: ${ver}`;

  // Invalidate or reset stale validation badge when placement changes
  const valBadge = document.getElementById("valResultBadge");
  if (valBadge && valBadge.textContent !== "ĐANG KIỂM ĐỊNH 90 Ô...") {
    if (d !== 0.0 || zOff !== 0.0) {
      valBadge.className = "badge-warn";
      valBadge.textContent = `CHƯA KIỂM ĐỊNH CHO VỊ TRÍ d=${d.toFixed(1)}mm, z_off=${zOff.toFixed(1)}mm`;
    }
  }

  // Atomically update geometric precheck UI readouts
  updateGeometricPrecheckUI(d, h, zOff);

  // 7 & 8. Atomically update board coordinate ruler edges and ruler labels
  const centerWorldZ = packet.board_center_world_m?.[2] ?? (0.36 + d / 1000.0);
  const surfaceWorldY = packet.board_center_world_m?.[1] ?? (0.0105 + zOff / 1000.0);
  if (coordinateRulerGroup?.updateBoardPlacement) {
    coordinateRulerGroup.updateBoardPlacement(centerWorldZ, surfaceWorldY);
  }

  // 9, 10, 11, 12. Atomically update target ring, dimension tape, markers, readouts
  if (state.selectedCell) {
    const { row, col } = state.selectedCell;
    const ring = getOrCreateTargetRing();
    const pt = boardPointToXYZ(row, col, physicalGeometryRef);
    ring.position.set(pt.x, pt.y + 0.001, pt.z);

    if (activeDimensionTape) {
      scene.remove(activeDimensionTape);
      activeDimensionTape = null;
    }
    const distMm = (Math.hypot(pt.x, pt.z) * 1000).toFixed(0);
    activeDimensionTape = createDimensionTape(
      new THREE.Vector3(0, 0.002, 0),
      new THREE.Vector3(pt.x, 0.002, pt.z),
      `R = ${distMm}mm (Ô row=${row}, col=${col})`
    );
    if (coordinateRulerGroup) {
      activeDimensionTape.visible = coordinateRulerGroup.visible;
    }
    scene.add(activeDimensionTape);

    const u = (col - 4.0) * 0.040;
    const v = (row - 4.5) * 0.040;
    const robX = -0.360 - (d / 1000.0) - u;
    const robY = -v;
    const robZ = 0.0105 + (zOff / 1000.0);

    const worldX_mm = (pt.x * 1000).toFixed(1);
    const worldY_mm = (pt.y * 1000).toFixed(1);
    const worldZ_mm = (pt.z * 1000).toFixed(1);

    const robX_mm = (robX * 1000).toFixed(1);
    const robY_mm = (robY * 1000).toFixed(1);
    const robZ_mm = (robZ * 1000).toFixed(1);

    const coordReadoutEl = document.getElementById("coordReadout");
    if (coordReadoutEl) {
      coordReadoutEl.textContent = `X: ${worldX_mm}mm | Y: ${worldY_mm}mm | Z: ${worldZ_mm}mm`;
    }
    const diagWorldCoord = document.getElementById("diagWorldCoord");
    if (diagWorldCoord) {
      diagWorldCoord.textContent = `X: ${worldX_mm}mm, Y: ${worldY_mm}mm, Z: ${worldZ_mm}mm`;
    }
    const diagRobotCoord = document.getElementById("diagRobotCoord");
    if (diagRobotCoord) {
      diagRobotCoord.textContent = `X: ${robX_mm}mm, Y: ${robY_mm}mm, Z: ${robZ_mm}mm`;
    }
    const cellLabel = document.getElementById("diagCellLabel");
    if (cellLabel) {
      cellLabel.textContent = `Hàng ${row}, Cột ${col} (X=${robX.toFixed(3)}m, Y=${robY.toFixed(3)}m, Z=${robZ.toFixed(3)}m)`;
    }
  }
}
window.applyAuthoritativeBoardPlacement = applyAuthoritativeBoardPlacement;
window.setScenePlacement = setScenePlacement;
window.applyPlacementAnalysisUI = applyPlacementAnalysisUI;

export function applyPlacementAnalysisUI(data) {
  if (!data) return;
  const d_mm = Number(data.forward_shift_mm ?? 0);
  const H_mm = Number(data.safe_transit_height_mm ?? 70);

  const elD = document.getElementById("readoutShiftD");
  const elNearGrid = document.getElementById("readoutNearGridDepth") || document.getElementById("readoutRow0Dist");
  const elFarGrid = document.getElementById("readoutFarGridDepth") || document.getElementById("readoutRow9Dist");
  const elNear = document.getElementById("readoutNearEdgeDist");
  const elCenter = document.getElementById("readoutCenterDist");
  const elFar = document.getElementById("readoutFarEdgeDist");
  const elH = document.getElementById("readoutHVal");
  const elFarGrasp = document.getElementById("readoutFarGraspDist");
  const elFarApp = document.getElementById("readoutFarAppDist");
  const elGraspMargin = document.getElementById("readoutGraspMargin");
  const elAppMargin = document.getElementById("readoutAppMargin");
  const elDMax = document.getElementById("readoutDMax");
  const elHMax = document.getElementById("readoutHMax");
  const badge = document.getElementById("geomPrecheckBadge");

  const preview = computeGeometricPrecheck(d_mm, H_mm, 10.5 + z_off_mm, data.board_yaw_deg ?? 90.0);
  if (elD) elD.textContent = `${d_mm.toFixed(1)} mm`;
  if (elNearGrid) elNearGrid.textContent = data.near_grid_depth_mm !== undefined ? `${data.near_grid_depth_mm.toFixed(1)} mm` : (data.nearest_cell_distance_mm !== undefined ? `${data.nearest_cell_distance_mm.toFixed(1)} mm` : `${preview.near_grid_depth_mm.toFixed(1)} mm`);
  if (elFarGrid) elFarGrid.textContent = data.far_grid_depth_mm !== undefined ? `${data.far_grid_depth_mm.toFixed(1)} mm` : (data.farthest_cell_distance_mm !== undefined ? `${data.farthest_cell_distance_mm.toFixed(1)} mm` : `${preview.far_grid_depth_mm.toFixed(1)} mm`);
  if (elNear) elNear.textContent = data.near_board_edge_distance_mm !== undefined ? `${data.near_board_edge_distance_mm.toFixed(1)} mm` : `${preview.near_board_edge_distance_mm.toFixed(1)} mm`;
  if (elCenter) elCenter.textContent = data.board_center_distance_mm !== undefined ? `${data.board_center_distance_mm.toFixed(1)} mm` : `${preview.board_center_distance_mm.toFixed(1)} mm`;
  if (elFar) elFar.textContent = data.far_board_edge_distance_mm !== undefined ? `${data.far_board_edge_distance_mm.toFixed(1)} mm` : `${preview.far_board_edge_distance_mm.toFixed(1)} mm`;
  const elYaw = document.getElementById("readoutBoardYaw");
  if (elYaw) elYaw.textContent = `+${Number(data.board_yaw_deg ?? 90.0).toFixed(1)}° (col=-X, row=-Y)`;
  if (elH) elH.textContent = `${H_mm.toFixed(1)} mm`;

  if (elFarGrasp) elFarGrasp.textContent = data.far_grasp_distance_mm !== undefined ? `${data.far_grasp_distance_mm.toFixed(1)} mm` : `${preview.D_far_grasp.toFixed(1)} mm`;
  if (elFarApp) elFarApp.textContent = data.far_approach_distance_mm !== undefined ? `${data.far_approach_distance_mm.toFixed(1)} mm` : `${preview.D_far_app.toFixed(1)} mm`;
  if (elGraspMargin) elGraspMargin.textContent = data.grasp_reach_margin_mm !== undefined ? `${data.grasp_reach_margin_mm.toFixed(1)} mm` : `${preview.grasp_margin.toFixed(1)} mm`;
  if (elAppMargin) elAppMargin.textContent = data.approach_reach_margin_mm !== undefined ? `${data.approach_reach_margin_mm.toFixed(1)} mm` : `${preview.app_margin.toFixed(1)} mm`;
  if (elDMax) elDMax.textContent = data.d_max_for_current_h_mm !== null && data.d_max_for_current_h_mm !== undefined ? `${data.d_max_for_current_h_mm.toFixed(1)} mm` : (preview.d_max !== null ? `${preview.d_max.toFixed(1)} mm` : "VÔ NGHIỆM");
  if (elHMax) elHMax.textContent = data.h_max_for_current_d_mm !== null && data.h_max_for_current_d_mm !== undefined ? `${data.h_max_for_current_d_mm.toFixed(1)} mm` : (preview.H_max !== null ? `${preview.H_max.toFixed(1)} mm` : "VÔ NGHIỆM");

  if (badge) {
    const isPass = Boolean(data.is_geometric_pass !== undefined ? data.is_geometric_pass : preview.pass);
    badge.className = isPass ? "badge-safe" : "badge-warn";
    badge.textContent = isPass ? "GEOMETRIC PASS" : "GEOMETRIC FAIL";
  }
}

export function updateFullRouteValidationResultUI(res) {
  const valBadge = document.getElementById("valResultBadge");
  if (!valBadge) return;
  if (res.all_routes_safe) {
    valBadge.className = "badge-safe";
    valBadge.textContent = res.status || "FULL BOARD ROUTE SAFE";
  } else {
    valBadge.className = "badge-warn";
    valBadge.textContent = `${res.status || "THẤT BẠI"} ${res.failed_routes}/${res.tested_routes || res.total_routes} TUYẾN (${res.worst_route?.stage || "LỖI"})`;
  }
}

export function updatePlacementValidationResultUI(res) {
  const valBadge = document.getElementById("valResultBadge");
  const elGraspIk = document.getElementById("valGraspIkCount");
  const elAppIk = document.getElementById("valAppIkCount");
  const elGraspCol = document.getElementById("valGraspColCount");
  const elAppCol = document.getElementById("valAppColCount");
  const failContainer = document.getElementById("valFailuresContainer");
  const failList = document.getElementById("valFailuresList");

  // Rejection of stale validation result (Section L)
  if (res.status === "STALE_VALIDATION_RESULT" || (res.placement_version !== undefined && res.placement_version !== state.placementVersion)) {
    if (valBadge) {
      valBadge.className = "badge-warn";
      valBadge.textContent = "KẾT QUẢ KIỂM ĐỊNH ĐÃ CŨ (STALE)";
    }
    return;
  }

  if (elGraspIk) elGraspIk.textContent = `${res.grasp_ik_count} / ${res.total_cells}`;
  if (elAppIk) elAppIk.textContent = `${res.approach_ik_count} / ${res.total_cells}`;
  if (elGraspCol) elGraspCol.textContent = `${res.grasp_collision_free_count} / ${res.total_cells}`;
  if (elAppCol) elAppCol.textContent = `${res.approach_collision_free_count} / ${res.total_cells}`;

  if (res.all_passed) {
    if (valBadge) {
      valBadge.className = "badge-safe";
      valBadge.textContent = "90/90 LOCAL CELL TRAJECTORIES PASS";
    }
    if (failContainer) failContainer.style.display = "none";
  } else {
    if (valBadge) {
      valBadge.className = "badge-warn";
      valBadge.textContent = `PHÁT HIỆN ${res.failed_cells?.length || 0} Ô VA CHẠM / LỖI`;
    }
    if (failContainer && failList && res.failed_cells?.length) {
      failContainer.style.display = "block";
      failList.innerHTML = res.failed_cells.slice(0, 10).map((f) => `<div>• Hàng ${f.row}, Cột ${f.col}: ${f.reason}</div>`).join("");
      if (res.failed_cells.length > 10) {
        failList.innerHTML += `<div>...và ${res.failed_cells.length - 10} ô khác</div>`;
      }
    }
  }
}

function updateOperationStateUI(stateName) {
  const badge = document.getElementById("opStateBadge");
  if (!badge) return;
  const s = String(stateName || "IDLE").toUpperCase();
  badge.textContent = s;
  badge.className = "";
  if (s === "IDLE") {
    badge.classList.add("state-idle");
  } else if (s === "MOTION") {
    badge.classList.add("state-motion");
  } else if (s.startsWith("VALIDATING")) {
    badge.classList.add("state-validating");
  } else if (s === "BOARD_ADJUSTMENT") {
    badge.classList.add("state-board");
  } else if (s === "SERVICE_MOVE") {
    badge.classList.add("state-service");
  } else if (s === "RESETTING") {
    badge.classList.add("state-resetting");
  } else {
    badge.classList.add("state-idle");
  }
}

function initServicePanelEvents() {
  const sendCmd = (cmdObj) => {
    if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
      state.liveSocket.send(JSON.stringify(cmdObj));
    } else {
      handleBackendError("Chưa kết nối Backend: Bấm Connect live để gửi lệnh.");
    }
  };

  document.getElementById("btnOpClearError")?.addEventListener("click", () => {
    sendCmd({ command: "CLEAR_ERROR" });
  });

  document.getElementById("btnOpResetRobot")?.addEventListener("click", () => {
    sendCmd({ command: "RESET_ROBOT" });
  });

  document.getElementById("btnOpResetBoard")?.addEventListener("click", () => {
    sendCmd({ command: "RESET_BOARD" });
  });

  document.getElementById("btnOpResetPieces")?.addEventListener("click", () => {
    sendCmd({ command: "RESET_PIECES" });
  });

  document.getElementById("btnOpFullReset")?.addEventListener("click", () => {
    triggerBackendDataReset();
  });

  document.getElementById("btnGoServiceSafe")?.addEventListener("click", () => {
    sendCmd({ command: "GO_SERVICE_SAFE" });
  });

  document.getElementById("btnRetractBoard")?.addEventListener("click", () => {
    sendCmd({ command: "RETRACT_FROM_BOARD" });
  });

  document.getElementById("btnPrepareBoardAdj")?.addEventListener("click", () => {
    sendCmd({ command: "PREPARE_BOARD_ADJUSTMENT" });
  });

  // Cartesian Jog
  document.querySelectorAll(".jog-btn[data-tcp-axis]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const axis = btn.dataset.tcpAxis;
      const stepSel = document.getElementById("tcpJogStepSelect");
      const step = stepSel ? Number(stepSel.value) : 5.0;
      sendCmd({
        command: "JOG_TCP",
        axis: axis,
        step_mm: step,
      });
    });
  });

  // Joint Jog
  document.querySelectorAll(".jog-btn-mini[data-joint-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.jointIdx);
      const dir = Number(btn.dataset.jointDir || 1);
      const stepSel = document.getElementById("jointJogStepSelect");
      const step = stepSel ? Number(stepSel.value) : 5.0;
      sendCmd({
        command: "JOG_JOINT",
        joint_idx: idx,
        delta_deg: dir * step,
      });
    });
  });
}

function initPlacementPanelEvents() {
  const shiftSlider = document.getElementById("boardShiftSlider");
  const shiftNum = document.getElementById("boardShiftNum");
  const transitSlider = document.getElementById("safeTransitSlider");
  const transitNum = document.getElementById("safeTransitNum");
  const zOffsetNum = document.getElementById("boardZOffsetNum");
  const btnApply = document.getElementById("btnApplyPlacement");
  const btnReset = document.getElementById("btnResetPlacement");
  const btnValidate = document.getElementById("btnValidatePlacement");

  const syncPrecheckFromInputs = () => {
    const d = Number(shiftNum?.value ?? 0);
    const h = Number(transitNum?.value ?? 70);
    const zOff = Number(zOffsetNum?.value ?? 0);
    updateGeometricPrecheckUI(d, h, zOff);
  };

  shiftSlider?.addEventListener("input", (e) => {
    if (shiftNum) shiftNum.value = e.target.value;
    syncPrecheckFromInputs();
  });
  shiftNum?.addEventListener("change", (e) => {
    if (shiftSlider) shiftSlider.value = e.target.value;
    syncPrecheckFromInputs();
  });

  transitSlider?.addEventListener("input", (e) => {
    if (transitNum) transitNum.value = e.target.value;
    syncPrecheckFromInputs();
  });
  transitNum?.addEventListener("change", (e) => {
    if (transitSlider) transitSlider.value = e.target.value;
    syncPrecheckFromInputs();
  });

  zOffsetNum?.addEventListener("input", () => {
    syncPrecheckFromInputs();
  });
  zOffsetNum?.addEventListener("change", () => {
    syncPrecheckFromInputs();
  });

  btnApply?.addEventListener("click", () => {
    if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
      const d = Number(shiftNum?.value ?? 0);
      const h = Number(transitNum?.value ?? 70);
      const zOff = Number(zOffsetNum?.value ?? 0);
      state.liveSocket.send(JSON.stringify({
        command: "SET_BOARD_PLACEMENT",
        forward_shift_mm: d,
        safe_transit_height_mm: h,
        board_height_offset_mm: zOff,
      }));
    } else {
      handleBackendError("Chưa kết nối Backend: Bấm Connect live để thay đổi vị trí bàn cờ có thẩm quyền");
    }
  });

  btnReset?.addEventListener("click", () => {
    if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
      state.liveSocket.send(JSON.stringify({
        command: "RESET_BOARD_PLACEMENT",
      }));
    } else {
      if (shiftSlider) shiftSlider.value = "0";
      if (shiftNum) shiftNum.value = "0";
      if (transitSlider) transitSlider.value = "70";
      if (transitNum) transitNum.value = "70";
      if (zOffsetNum) zOffsetNum.value = "0";
      syncPrecheckFromInputs();
    }
  });

  btnValidate?.addEventListener("click", () => {
    if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
      state.liveSocket.send(JSON.stringify({
        command: "VALIDATE_BOARD_PLACEMENT",
      }));
      const valBadge = document.getElementById("valResultBadge");
      if (valBadge) {
        valBadge.className = "badge-warn";
        valBadge.textContent = "ĐANG KIỂM ĐỊNH 90 Ô...";
      }
    } else {
      handleBackendError("Chưa kết nối Backend: Cần kết nối live để kiểm định 90 ô");
    }
  });

  syncPrecheckFromInputs();
}

function initJointControlPanelEvents() {
  const homeBtn = document.getElementById("homeBtn");
  if (homeBtn) {
    homeBtn.addEventListener("click", () => {
      if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
        state.liveSocket.send(JSON.stringify({ command: "RESET" }));
      } else {
        const homeDeg = state.homePoseDeg || [0.0, -45.0, 90.0, -45.0, -90.0, 0.0];
        state.jointsDeg = [...homeDeg];
        syncAllJointSliders();
        if (state.currentArm) {
          applyJointsDeg(state.currentArm, state.jointsDeg);
        }
      }
      state.currentCell = null;
      updateStepperUI(null, []);
      const badge = document.getElementById("diagStatusBadge");
      if (badge) {
        badge.className = "badge-safe";
        badge.textContent = "ĐÃ VỀ HOME";
      }
    });
  }

  const gripperBtn = document.getElementById("gripperBtn");
  if (gripperBtn) {
    gripperBtn.addEventListener("click", () => {
      state.gripperClosed = !state.gripperClosed;
      if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
        state.liveSocket.send(JSON.stringify({ command: "SET_GRIPPER", closed: state.gripperClosed }));
      } else if (state.currentArm?.gripper) {
        state.currentArm.gripper.setClosed(state.gripperClosed);
      }
      gripperBtn.textContent = state.gripperClosed ? "🗜️ Đang Kẹp" : "🗜️ Kẹp / Nhả";
      gripperBtn.style.color = state.gripperClosed ? "#f0883e" : "#c9d1d9";
    });
  }

  function triggerBackendDataReset() {
    if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
      const badge = document.getElementById("diagStatusBadge");
      if (badge) {
        badge.className = "badge-warn";
        badge.textContent = "ĐANG RESET BACKEND...";
      }
      state.liveSocket.send(JSON.stringify({
        command: "RESET_ALL_BACKEND_DATA",
      }));
    } else {
      handleBackendError("Chưa kết nối Backend: Bấm Connect live để khởi động lại dữ liệu backend.");
    }
  }

  const resetBackendBtn = document.getElementById("resetBackendBtn");
  if (resetBackendBtn) {
    resetBackendBtn.addEventListener("click", triggerBackendDataReset);
  }

  const panelResetBackendBtn = document.getElementById("panelResetBackendBtn");
  if (panelResetBackendBtn) {
    panelResetBackendBtn.addEventListener("click", triggerBackendDataReset);
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

  // Tabs switching: J1..J6 | Reach Cells | Board Placement | Service & Recovery
  const tabJointsBtn = document.getElementById("tabJointsBtn");
  const tabReachBtn = document.getElementById("tabReachBtn");
  const tabPlacementBtn = document.getElementById("tabPlacementBtn");
  const tabServiceBtn = document.getElementById("tabServiceBtn");
  const jointsContent = document.getElementById("jointsTabContent");
  const reachContent = document.getElementById("reachTabContent");
  const placementContent = document.getElementById("placementTabContent");
  const serviceContent = document.getElementById("serviceTabContent");

  function switchTab(activeTab, activeContent) {
    [tabJointsBtn, tabReachBtn, tabPlacementBtn, tabServiceBtn].forEach((b) => b?.classList.remove("active"));
    [jointsContent, reachContent, placementContent, serviceContent].forEach((c) => c?.classList.remove("active"));
    activeTab?.classList.add("active");
    activeContent?.classList.add("active");
  }

  tabJointsBtn?.addEventListener("click", () => switchTab(tabJointsBtn, jointsContent));
  tabReachBtn?.addEventListener("click", () => switchTab(tabReachBtn, reachContent));
  tabPlacementBtn?.addEventListener("click", () => switchTab(tabPlacementBtn, placementContent));
  tabServiceBtn?.addEventListener("click", () => switchTab(tabServiceBtn, serviceContent));

  // Reach cell button
  const reachBtn = document.getElementById("reachCellBtn");
  const rowSelect = document.getElementById("cellRowSelect");
  const colSelect = document.getElementById("cellColSelect");
  if (reachBtn && rowSelect && colSelect) {
    reachBtn.addEventListener("click", () => {
      goToCell(Number(rowSelect.value), Number(colSelect.value));
    });
  }

  // Setup dynamic board placement panel handlers
  initPlacementPanelEvents();
  initServicePanelEvents();

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

    // 1. Kiểm tra click vào cạnh thước / trục tọa độ (Click-to-Show)
    for (const hit of hits) {
      if (hit.object?.userData?.isRulerProxy) {
        const axis = hit.object.userData.axis;
        if (coordinateRulerGroup?.toggleAxis) {
          const isVis = coordinateRulerGroup.toggleAxis(axis, hit.point);
          const coordReadoutEl = document.getElementById("coordReadout");
          if (coordReadoutEl) {
            const xMm = (hit.point.x * 1000).toFixed(0);
            const yMm = (hit.point.y * 1000).toFixed(1);
            const zMm = (hit.point.z * 1000).toFixed(0);
            coordReadoutEl.textContent = `📍 Cạnh ${axis}: ${isVis ? "BẬT" : "TẮT"} (X:${xMm}mm Y:${yMm}mm Z:${zMm}mm)`;
          }
          const toggleRulerBtn = document.getElementById("toggleRulerBtn");
          if (toggleRulerBtn && coordinateRulerGroup.isAnyLabelsVisible) {
            toggleRulerBtn.classList.toggle("active", coordinateRulerGroup.isAnyLabelsVisible());
          }
        }
        return;
      }
    }

    // 2. Click vào quân cờ hoặc ô cờ
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

  // Ruler toggle button (HUD)
  const toggleRulerBtn = document.getElementById("toggleRulerBtn");
  if (toggleRulerBtn) {
    toggleRulerBtn.addEventListener("click", () => {
      if (!coordinateRulerGroup) return;
      const isVisible = coordinateRulerGroup.toggleAll();
      if (activeDimensionTape) {
        activeDimensionTape.visible = isVisible;
      }
      toggleRulerBtn.classList.toggle("active", isVisible);
      const coordReadoutEl = document.getElementById("coordReadout");
      if (coordReadoutEl) {
        coordReadoutEl.textContent = isVisible
          ? "Đang hiện toàn bộ thước đo (Click cạnh để bật/tắt từng trục)"
          : "Đã ẩn thước đo (Click vào cạnh trục để hiện)";
      }
    });
  }

  // Keyboard shortcut 'R' to toggle coordinate ruler
  window.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.key === "r" || e.key === "R") {
      if (toggleRulerBtn) toggleRulerBtn.click();
    }
  });

  // Pointer move: update real-time hovered coordinates over board & ruler edges
  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    const hits = raycaster.intersectObjects(scene.children, true);
    let isHoveringInteractive = false;

    for (const hit of hits) {
      if (hit.object?.userData?.isRulerProxy) {
        isHoveringInteractive = true;
        canvas.style.cursor = "pointer";
        const axis = hit.object.userData.axis;
        const x_mm = (hit.point.x * 1000).toFixed(0);
        const y_mm = (hit.point.y * 1000).toFixed(1);
        const z_mm = (hit.point.z * 1000).toFixed(0);
        const coordReadoutEl = document.getElementById("coordReadout");
        if (coordReadoutEl && !state.selectedCell) {
          coordReadoutEl.textContent = `👆 Click cạnh ${axis} để hiện tọa độ (X:${x_mm} Y:${y_mm} Z:${z_mm})`;
        }
        break;
      } else if (hit.object?.userData && (hit.object.userData.col !== undefined || hit.object.userData.row !== undefined)) {
        isHoveringInteractive = true;
        canvas.style.cursor = "pointer";
        break;
      }
    }

    if (!isHoveringInteractive) {
      canvas.style.cursor = "default";
      const expectedY = 0.0105 + (state.boardHeightOffsetMm || 0.0) / 1000.0;
      for (const hit of hits) {
        if (hit.point && Math.abs(hit.point.y - expectedY) < 0.03) {
          const x_mm = (hit.point.x * 1000).toFixed(0);
          const y_mm = (hit.point.y * 1000).toFixed(1);
          const z_mm = (hit.point.z * 1000).toFixed(0);
          const coordReadoutEl = document.getElementById("coordReadout");
          if (coordReadoutEl && !state.selectedCell) {
            coordReadoutEl.textContent = `Cursor: X:${x_mm}mm | Y:${y_mm}mm | Z:${z_mm}mm`;
          }
          break;
        }
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

function handleBackendTrajectoryStage(stage, payload) {
  const badge = document.getElementById("diagStatusBadge");
  const expl = document.getElementById("diagExplanation");
  const j4Val = document.getElementById("diagJ4Val");
  const tiltVal = document.getElementById("diagTiltVal");
  const clearanceVal = document.getElementById("diagClearanceVal");

  if (stage === "PREPOSITION") {
    updateStepperUI(null, []);
    if (badge) {
      badge.className = "badge-warn";
      badge.textContent = "🛫 0. TIẾP CẬN NGUỒN (PREPOSITION)";
    }
    if (expl) {
      expl.innerHTML = `🛫 <strong>Preposition (Tiếp cận nguồn):</strong> Robot di chuyển khớp tới vị trí ô xuất phát trước khi nhấc.`;
    }
  } else if (stage === "LIFT") {
    updateStepperUI("stepLift", []);
    const zBoard_mm = (state.boardSurfaceHeightM ?? (0.0105 + (state.boardHeightOffsetMm ?? 0.0) / 1000.0)) * 1000.0;
    const safeH_mm = state.safeTransitHeightMm ?? 70.0;
    const zSafe_mm = zBoard_mm + safeH_mm;
    const zSafe_m = (zSafe_mm / 1000.0).toFixed(4);
    if (badge) {
      badge.className = "badge-warn";
      badge.textContent = `🛫 1. ĐANG NHẤC LÊN (+${safeH_mm.toFixed(1)}mm)`;
    }
    if (expl) {
      expl.innerHTML = `🛫 <strong>Giai đoạn 1 (Nhấc lên):</strong> Cánh tay nâng thẳng đứng ngàm kẹp lên cao độ an toàn <strong>+${safeH_mm.toFixed(1)}mm</strong> ($Z = ${zSafe_m}\\text{m}$, $\\Delta XY \\le 1.0\\text{mm}$, tilt $\\le 0.5^\\circ$).`;
    }
  } else if (stage === "TRANSIT") {
    updateStepperUI("stepTransit", ["stepLift"]);
    const zBoard_mm = (state.boardSurfaceHeightM ?? (0.0105 + (state.boardHeightOffsetMm ?? 0.0) / 1000.0)) * 1000.0;
    const safeH_mm = state.safeTransitHeightMm ?? 70.0;
    const zSafe_mm = zBoard_mm + safeH_mm;
    const zSafe_m = (zSafe_mm / 1000.0).toFixed(4);
    if (badge) {
      badge.className = "badge-transit";
      badge.textContent = `✈️ 2. ĐANG BAY NGANG (+${safeH_mm.toFixed(1)}mm)`;
    }
    if (expl) {
      expl.innerHTML = `✈️ <strong>Giai đoạn 2 (Bay ngang):</strong> Robot di chuyển ngang trên mặt phẳng an toàn $Z = ${zSafe_m}\\text{m}$ (dung sai $\\pm 1.0\\text{mm}$, tilt $\\le 0.5^\\circ$).`;
    }
  } else if (stage === "LAND") {
    updateStepperUI("stepLand", ["stepLift", "stepTransit"]);
    const zBoard_mm = (state.boardSurfaceHeightM ?? (0.0105 + (state.boardHeightOffsetMm ?? 0.0) / 1000.0)) * 1000.0;
    const pieceH_mm = physicalGeometryRef?.piece_height_mm ?? 9.43;
    const graspRel_mm = pieceH_mm / 2.0;
    const zGrasp_mm = zBoard_mm + graspRel_mm;
    const zGrasp_m = (zGrasp_mm / 1000.0).toFixed(6);
    if (badge) {
      badge.className = "badge-land";
      badge.textContent = `🛬 3. ĐANG HẠ CÁNH (+${graspRel_mm.toFixed(3)}mm)`;
    }
    if (expl) {
      expl.innerHTML = `🛬 <strong>Giai đoạn 3 (Hạ cánh):</strong> Ngàm kẹp hạ cánh thẳng đứng xuống cao độ gắp $Z = ${zGrasp_m}\\text{m}$ ($+${graspRel_mm.toFixed(3)}\\text{mm}$ tâm quân cờ, $\\Delta XY \\le 1.0\\text{mm}$, tilt $\\le 0.5^\\circ$).`;
    }
  } else if (stage === "COMPLETE") {
    updateStepperUI(null, ["stepLift", "stepTransit", "stepLand"]);
    if (badge) {
      badge.className = "badge-safe";
      badge.textContent = "✅ TRAJECTORY COMPLETE (COLLISION-FREE)";
    }
    if (state.targetDestinationCell) {
      state.currentCell = state.targetDestinationCell;
    }
    if (j4Val && state.jointsDeg) {
      j4Val.textContent = `${state.jointsDeg[3].toFixed(1)}° (Authoritative IK)`;
      j4Val.style.color = "#58a6ff";
    }
    if (tiltVal) {
      tiltVal.textContent = `0.0° ✓ Cắm thẳng đứng 90° (DOWNWARD)`;
      tiltVal.style.color = "#3fb950";
    }
    if (clearanceVal) {
      clearanceVal.textContent = `✅ Đầu ngàm kẹp cách mặt bàn +4.715 mm (Tâm quân cờ, COLLISION-FREE)`;
      clearanceVal.style.color = "#3fb950";
    }
    if (expl) {
      expl.innerHTML = `✅ <strong>Đã hoàn thành quỹ đạo 3 giai đoạn:</strong> Robot đã thực thi Lift (+70mm) ➔ Transit ➔ Land bởi backend runtime có thẩm quyền. Trạng thái: <strong>COLLISION-FREE</strong>.`;
    }
  } else if (stage === "RECOVERY_LIFT") {
    updateStepperUI(null, []);
    if (badge) {
      badge.className = "badge-warn";
      badge.textContent = "🧗 TRÁNH VA CHẠM: ĐANG TỰ ĐỘNG NHẤC TAY";
    }
    if (expl) {
      expl.innerHTML = `🧗 <strong>Tự động tránh va chạm (Lift-First Recovery):</strong> Phát hiện vật cản/quân cờ trên đường đi, robot tự động nhấc thẳng đứng cánh tay lên cao độ an toàn (+Z) trước khi xoay chỉnh khớp tới điểm đích.`;
    }
  } else if (stage === "IDLE") {
    if (payload && (payload.last_error || payload.motion_state === "COLLISION_REJECTED")) {
      handleBackendError(payload.last_error || "Chuyển động bị từ chối bởi Collision Guard");
    } else if (badge && badge.textContent === "GỬI LỆNH TỚI BACKEND...") {
      badge.className = "badge-safe";
      badge.textContent = "SẴN SÀNG (IDLE)";
    }
  }
}

function handleBackendError(errMsg) {
  const badge = document.getElementById("diagStatusBadge");
  const expl = document.getElementById("diagExplanation");
  if (badge) {
    badge.className = "badge-warn";
    badge.textContent = "❌ LỖI / COLLISION REJECTED";
  }
  if (expl) {
    expl.innerHTML = `<span style="color:#f85149">❌ <strong>Từ chối chuyển động:</strong> ${errMsg}</span>`;
  }
}

function goToCell(row, col) {
  state.selectedCell = { row, col };

  // Update 3D ring marker & coordinates
  const ring = getOrCreateTargetRing();
  if (physicalGeometryRef) {
    const pt = boardPointToXYZ(row, col, physicalGeometryRef);
    ring.position.set(pt.x, pt.y + 0.001, pt.z);
    ring.material.color.setHex(0x58a6ff);

    // Map Three.js world frame to robot base frame:
    // X_robot = -Z_world, Y_robot = -X_world, Z_robot = +Y_world
    const robX = -pt.z;
    const robY = -pt.x;
    const robZ = pt.y;
    const cell = { row, col, x_m: robX, y_m: robY, z_m: robZ };

    const worldX_mm = (pt.x * 1000).toFixed(1);
    const worldY_mm = (pt.y * 1000).toFixed(1);
    const worldZ_mm = (pt.z * 1000).toFixed(1);

    const robX_mm = (robX * 1000).toFixed(1);
    const robY_mm = (robY * 1000).toFixed(1);
    const robZ_mm = (robZ * 1000).toFixed(1);

    const coordReadoutEl = document.getElementById("coordReadout");
    if (coordReadoutEl) {
      coordReadoutEl.textContent = `X: ${worldX_mm}mm | Y: ${worldY_mm}mm | Z: ${worldZ_mm}mm`;
    }
    const diagWorldCoord = document.getElementById("diagWorldCoord");
    if (diagWorldCoord) {
      diagWorldCoord.textContent = `X: ${worldX_mm}mm, Y: ${worldY_mm}mm, Z: ${worldZ_mm}mm`;
    }
    const diagRobotCoord = document.getElementById("diagRobotCoord");
    if (diagRobotCoord) {
      diagRobotCoord.textContent = `X: ${robX_mm}mm, Y: ${robY_mm}mm, Z: ${robZ_mm}mm`;
    }

    // Dynamic dimension line from origin to cell
    if (activeDimensionTape) {
      scene.remove(activeDimensionTape);
      activeDimensionTape = null;
    }
    const distMm = (Math.hypot(pt.x, pt.z) * 1000).toFixed(0);
    activeDimensionTape = createDimensionTape(
      new THREE.Vector3(0, 0.002, 0),
      new THREE.Vector3(pt.x, 0.002, pt.z),
      `R = ${distMm}mm (Ô row=${row}, col=${col})`
    );
    if (coordinateRulerGroup) {
      activeDimensionTape.visible = coordinateRulerGroup.visible;
    }
    scene.add(activeDimensionTape);
  }

  // Update inputs
  const rowSelect = document.getElementById("cellRowSelect");
  const colSelect = document.getElementById("cellColSelect");
  if (rowSelect) rowSelect.value = String(row);
  if (colSelect) colSelect.value = String(col);

  const cellLabel = document.getElementById("diagCellLabel");
  if (cellLabel) cellLabel.textContent = `Hàng ${row}, Cột ${col} (X=${cell.x_m.toFixed(3)}m, Y=${cell.y_m.toFixed(3)}m, Z=${cell.z_m.toFixed(3)}m)`;

  state.targetDestinationCell = cell;

  // Dispatch authoritative trajectory command to backend via WebSocket
  if (state.liveSocket && state.liveSocket.readyState === WebSocket.OPEN) {
    const srcRow = state.currentCell ? state.currentCell.row : 4;
    const srcCol = state.currentCell ? state.currentCell.col : 4;
    const cmd = {
      command: "EXECUTE_3STAGE",
      src: [srcRow, srcCol],
      dst: [row, col],
      placement_version: state.placementVersion || 1,
      grasp_piece: false,
    };
    state.liveSocket.send(JSON.stringify(cmd));
    const badge = document.getElementById("diagStatusBadge");
    if (badge) {
      badge.className = "badge-warn";
      badge.textContent = "GỬI LỆNH TỚI BACKEND...";
    }
  } else {
    const badge = document.getElementById("diagStatusBadge");
    if (badge) {
      badge.className = "badge-warn";
      badge.textContent = "CHƯA KẾT NỐI WEBSOCKET";
    }
    const expl = document.getElementById("diagExplanation");
    if (expl) {
      expl.innerHTML = `<span style="color:#d29922">⚠️ <strong>Chưa kết nối Backend:</strong> Bấm nút <em>Connect live</em> để kết nối với WebSocket runtime (Single Motion Authority).</span>`;
    }
  }
}

// ---------------------------------------------------------------------------
// 6) VÒNG LẶP RENDER
// ---------------------------------------------------------------------------
function loop() {
  requestAnimationFrame(loop);
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

    coordinateRulerGroup = buildCoordinateRulerGroup({ initialLabelsVisible: false });
    scene.add(coordinateRulerGroup);

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
