export function validateLivePacket(payload, jointLimits, expectedModel = "FR5") {
  if (!payload || payload.type !== "robot_state") {
    return { ok: false, reason: "not a robot_state packet" };
  }
  if (payload.robot_model !== expectedModel) {
    return { ok: false, reason: `expected robot_model ${expectedModel}` };
  }
  if (payload.connected !== true) {
    return { ok: false, reason: "backend is not connected" };
  }
  if (payload.collision_validated !== true) {
    return { ok: false, reason: "backend pose has not passed collision validation" };
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
  if (!payload || typeof payload !== "object" || payload.type !== "world_state") {
    return { ok: false, reason: "not a world_state packet" };
  }
  if (!Array.isArray(payload.pieces)) {
    return { ok: false, reason: "missing pieces array" };
  }

  for (const piece of payload.pieces) {
    if (!piece || typeof piece !== "object") {
      return { ok: false, reason: "piece must be an object" };
    }
    if (typeof piece.id !== "string" || piece.id.trim() === "") {
      return { ok: false, reason: "invalid piece in pieces list: missing non-empty id" };
    }

    const pose = piece.pose_world || piece.pose_robot;
    if (!Array.isArray(pose) || pose.length < 3 || pose.some((v) => typeof v !== "number" || !Number.isFinite(v))) {
      return { ok: false, reason: `piece ${piece.id} has invalid or non-finite 3D coordinates` };
    }

    const quat = piece.orientation_quat_world || piece.orientation_quat_robot;
    if (quat !== undefined) {
      if (!Array.isArray(quat) || quat.length !== 4 || quat.some((v) => typeof v !== "number" || !Number.isFinite(v))) {
        return { ok: false, reason: `piece ${piece.id} quaternion must have exactly 4 finite numbers` };
      }
      const normSq = quat[0] * quat[0] + quat[1] * quat[1] + quat[2] * quat[2] + quat[3] * quat[3];
      if (normSq < 1e-12) {
        return { ok: false, reason: `piece ${piece.id} has zero-norm quaternion` };
      }
    }

    const status = piece.status || piece.physical_state;
    if (status !== undefined && (typeof status !== "string" || status.trim() === "")) {
      return { ok: false, reason: `piece ${piece.id} has invalid status string` };
    }

    const grasped = piece.is_grasped !== undefined ? piece.is_grasped : piece.attached;
    if (grasped !== undefined && typeof grasped !== "boolean") {
      return { ok: false, reason: `piece ${piece.id} grasp state must be a boolean` };
    }
  }

  let gripper = null;
  if (payload.gripper !== undefined && payload.gripper !== null) {
    if (typeof payload.gripper !== "object" || Array.isArray(payload.gripper)) {
      return { ok: false, reason: "gripper must be an object" };
    }

    const hasClosed = payload.gripper.closed !== undefined;
    const hasIsClosed = payload.gripper.is_closed !== undefined;

    if (!hasClosed && !hasIsClosed) {
      return { ok: false, reason: "gripper missing required 'closed' or 'is_closed' boolean" };
    }

    if (hasClosed && typeof payload.gripper.closed !== "boolean") {
      return { ok: false, reason: "gripper.closed must be a strict boolean (no string or integer coercion)" };
    }
    if (hasIsClosed && typeof payload.gripper.is_closed !== "boolean") {
      return { ok: false, reason: "gripper.is_closed must be a strict boolean (no string or integer coercion)" };
    }

    if (hasClosed && hasIsClosed && payload.gripper.closed !== payload.gripper.is_closed) {
      return { ok: false, reason: "gripper.closed and gripper.is_closed conflict with each other" };
    }

    const closed = hasClosed ? payload.gripper.closed : payload.gripper.is_closed;

    const jawWidth = payload.gripper.jaw_width_m !== undefined
      ? payload.gripper.jaw_width_m
      : payload.gripper.jaw_opening_m;
    if (jawWidth !== undefined && (typeof jawWidth !== "number" || !Number.isFinite(jawWidth) || jawWidth < 0)) {
      return { ok: false, reason: "gripper jaw width must be a finite number >= 0" };
    }

    if (payload.gripper.attached_piece_id !== undefined && payload.gripper.attached_piece_id !== null) {
      if (typeof payload.gripper.attached_piece_id !== "string") {
        return { ok: false, reason: "gripper.attached_piece_id must be a string or null" };
      }
    }

    for (const posKey of ["tcp_position_m", "grasp_position_m"]) {
      const pos = payload.gripper[posKey];
      if (pos !== undefined) {
        if (!Array.isArray(pos) || pos.length !== 3 || pos.some((v) => typeof v !== "number" || !Number.isFinite(v))) {
          return { ok: false, reason: `gripper.${posKey} must be an array of 3 finite numbers` };
        }
      }
    }

    gripper = {
      ...payload.gripper,
      closed,
      is_closed: closed,
    };
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
