"""Receive state and query FK only. No activation, reset, motion or output RPCs.

Run from repository root with its Python environment. This is an incident
artifact, not a production state-packet compatibility layer.
"""
import ctypes
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import socket
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.hardware.robot_sdk_core import RobotStatePkg
from src.hardware.rpc_transport import BoundedRPCProxy

OUT = Path(__file__).resolve().parent
ALLOW = {"GetControllerIP", "GetRobotErrorCode", "GetSoftwareVersion",
         "GetActualJointPosDegree", "GetActualTCPPose", "GetActualTCPNum",
         "GetActualWObjNum", "GetTCPOffset", "GetWObjOffset", "GetForwardKin"}


def probe():
    result = {"started_at": datetime.now().astimezone().isoformat(),
              "mode": "READ_ONLY", "queries": [], "frames": [],
              "checksum_bad": 0, "sdk_struct_bytes": ctypes.sizeof(RobotStatePkg)}
    proxy = BoundedRPCProxy("http://192.168.58.2:20003", timeout_s=2)

    def query(name, *args):
        assert name in ALLOW
        record = {"name": name, "args": args,
                  "at": datetime.now().astimezone().isoformat()}
        try:
            record["result"] = getattr(proxy, name)(*args)
        except Exception as exc:
            record["error"] = type(exc).__name__ + ": " + str(exc)
        result["queries"].append(record)
        return record.get("result")

    query("GetControllerIP")
    query("GetRobotErrorCode")
    query("GetSoftwareVersion")
    buf = bytearray()
    raw_frames = []
    deadline = time.monotonic() + 6
    first = None
    # Read only the stable SDK prefix through enable-state. Later fields in
    # this controller's shorter protocol are deliberately not zero-padded.
    prefix_end = RobotStatePkg.rbtEnableState.offset + ctypes.sizeof(ctypes.c_int)
    fields = [(n, t) for n, t in RobotStatePkg._fields_
              if getattr(RobotStatePkg, n).offset + ctypes.sizeof(t) <= prefix_end]

    class Prefix(ctypes.Structure):
        _pack_ = 1
        _fields_ = fields

    with socket.create_connection(("192.168.58.2", 20004), timeout=2) as state:
        state.settimeout(.5)
        while time.monotonic() < deadline:
            try:
                data = state.recv(65536)
            except socket.timeout:
                continue
            if not data:
                break
            buf.extend(data)
            while len(buf) >= 5:
                head = buf.find(b"\x5a\x5a")
                if head < 0:
                    buf[:] = buf[-1:]
                    break
                if head:
                    del buf[:head]
                size = struct.unpack_from("<H", buf, 3)[0] + 7
                if not 20 <= size <= 20000:
                    del buf[0]
                    continue
                if len(buf) < size:
                    break
                raw = bytes(buf[:size])
                del buf[:size]
                if (sum(raw[:-2]) & 65535) != struct.unpack_from("<H", raw, size-2)[0]:
                    result["checksum_bad"] += 1
                    continue
                if size - 2 < prefix_end:
                    raise RuntimeError("State prefix too short; no pose accepted")
                p = Prefix.from_buffer_copy(raw[:prefix_end])
                frame = {n: getattr(p, n) for n in (
                    "frame_cnt", "data_len", "program_state", "robot_state",
                    "main_code", "sub_code", "robot_mode", "tool", "user",
                    "EmergencyStop", "motion_done", "collisionState",
                    "safety_stop0_state", "safety_stop1_state", "rbtEnableState",
                    "mc_queue_len")}
                frame.update(received_at=datetime.now().astimezone().isoformat(),
                             frame_size=size, checksum_valid=True,
                             joints=list(p.jt_cur_pos), tcp=list(p.tl_cur_pos),
                             flange=list(p.flange_cur_pos), joint_velocity=list(p.actual_qd))
                assert all(math.isfinite(v) for key in ("joints", "tcp", "flange") for v in frame[key])
                result["frames"].append(frame)
                raw_frames.append(raw)
                if first is None:
                    first = time.monotonic()
            if first is not None and time.monotonic() - first >= 2:
                break

    if len(result["frames"]) < 5:
        raise RuntimeError("Insufficient fresh packets; no state conclusion")
    last = result["frames"][-1]
    fk = query("GetForwardKin", last["joints"])
    assert isinstance(fk, list) and len(fk) == 7 and fk[0] == 0
    result["fk_tcp_max_component_error"] = max(abs(a-b) for a, b in zip(fk[1:], last["tcp"]))
    assert result["fk_tcp_max_component_error"] < .05
    for name in ("GetActualJointPosDegree", "GetActualTCPPose", "GetActualTCPNum",
                 "GetActualWObjNum", "GetTCPOffset", "GetWObjOffset"):
        query(name, 0)
    query("GetRobotErrorCode")
    profile_path = ROOT / "calibration/physical_teaching_points_user0.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    home = profile["points"]["HOMECHESS"]
    home_fk = query("GetForwardKin", home["joints"])
    result["fixed_profile"] = {"id": profile["profile_id"], "tool": home["tool"],
                               "user": home["user"], "home": home,
                               "sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest()}
    previous = json.loads((ROOT / "reports/live-pose-20261030/latest-verified-state.json").read_text(encoding="utf-8"))
    result["previous_snapshot_structure"] = type(previous).__name__
    result["joint_spread_deg"] = [max(f["joints"][j] for f in result["frames"]) -
                                  min(f["joints"][j] for f in result["frames"]) for j in range(6)]
    result["tcp_to_flange_distance_mm"] = math.dist(last["tcp"][:3], last["flange"][:3])
    result["finished_at"] = datetime.now().astimezone().isoformat()
    result["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [ROOT / "src/hardware/robot_VIP.py",
                                         ROOT / "src/hardware/robot_sdk_core.py", profile_path]}
    (OUT / "state-frames.bin").write_bytes(b"".join(raw_frames))
    result["raw_sha256"] = hashlib.sha256(b"".join(raw_frames)).hexdigest()
    (OUT / "live-probe.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"started_at": result["started_at"], "finished_at": result["finished_at"],
                      "frames": len(result["frames"]), "checksum_bad": result["checksum_bad"],
                      "last": last, "joint_spread_deg": result["joint_spread_deg"],
                      "fk_tcp_max_component_error": result["fk_tcp_max_component_error"],
                      "tcp_to_flange_distance_mm": result["tcp_to_flange_distance_mm"],
                      "queries": result["queries"]}, indent=2))


if __name__ == "__main__":
    probe()
