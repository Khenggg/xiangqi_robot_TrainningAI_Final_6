export function validateLivePacket(payload, jointLimits, expectedModel = "FR5") {
  if (!payload || payload.type !== "robot_state") {
    return { ok: false, reason: "not a robot_state packet" };
  }
  if (payload.robot_model !== expectedModel) {
    return { ok: false, reason: `expected robot_model ${expectedModel}` };
  }
  if (!Array.isArray(payload.joints) || payload.joints.length < 6) {
    return { ok: false, reason: "six joint values are required" };
  }
  const joints = payload.joints.slice(0, 6).map(Number);
  if (
    joints.some(
      (value, index) =>
        !Number.isFinite(value) ||
        value < jointLimits[index][0] ||
        value > jointLimits[index][1],
    )
  ) {
    return { ok: false, reason: "joint value outside finite limits" };
  }
  const tcp = Array.isArray(payload.tcp) ? payload.tcp.slice(0, 6).map(Number) : null;
  if (tcp && (tcp.length < 6 || tcp.some((value) => !Number.isFinite(value)))) {
    return { ok: false, reason: "TCP values are not finite" };
  }
  return { ok: true, joints, tcp };
}

export function validateWorldStatePacket(payload) {
  if (!payload || payload.type !== "world_state") {
    return { ok: false, reason: "not a world_state packet" };
  }
  if (!Array.isArray(payload.pieces)) {
    return { ok: false, reason: "missing pieces array" };
  }
  for (const piece of payload.pieces) {
    if (!piece || typeof piece.id !== "string") {
      return { ok: false, reason: "invalid piece in pieces list: missing id" };
    }
    const pose = piece.pose_world || piece.pose_robot;
    if (!Array.isArray(pose) || pose.length < 3 || pose.some((v) => !Number.isFinite(v))) {
      return { ok: false, reason: `piece ${piece.id} has non-finite 3D coordinates` };
    }
  }
  let gripper = null;
  if (payload.gripper && typeof payload.gripper === "object") {
    const closed = payload.gripper.closed !== undefined
      ? Boolean(payload.gripper.closed)
      : Boolean(payload.gripper.is_closed);
    gripper = { ...payload.gripper, closed, is_closed: closed };
  }
  return { ok: true, pieces: payload.pieces, gripper };
}

export function liveControlsLocked({ socketOpen = false, live = false, connecting = false } = {}) {
  return Boolean(socketOpen || live || connecting);
}

export function isLiveStale(now, lastReceipt, timeoutMs = 2000) {
  return Number.isFinite(lastReceipt) && now - lastReceipt > timeoutMs;
}

// Encoder packets can differ by a few thousandths of a degree while the
// physical arm is stationary. Hold those tiny changes so the visual model
// does not restart its easing animation every telemetry tick.
export function stabilizeJointTarget(nextJoints, previousJoints, deadbandDeg = 0.02) {
  if (!Array.isArray(nextJoints) || nextJoints.length !== 6) return null;
  if (!Array.isArray(previousJoints) || previousJoints.length !== 6) {
    return [...nextJoints];
  }
  return nextJoints.map((value, index) =>
    Math.abs(value - previousJoints[index]) < deadbandDeg
      ? previousJoints[index]
      : value,
  );
}
