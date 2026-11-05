# ROBOT CONNECTION — CABLE/ETHERNET IS INTERMITTENT

**Tình trạng thực tế:** dây/đầu nối Ethernet của robot bị lỏng; kết nối có thể
mất tạm thời. Đây là lỗi phần cứng/kết nối, không phải lỗi code. Hãy cắm lại dây
và kiểm tra bằng lệnh ping bên dưới trước khi chạy lại.

> **Known hardware condition:** the robot Ethernet cable/connector is loose.
> Intermittent `192.168.58.2` disconnects are expected and are **not necessarily a
> software regression**. Re-seat the cable first; do not enable motion while the
> link is unstable.

## Network addresses used by this workstation

```text
PC Ethernet 3:  192.168.58.3/24
Robot controller: 192.168.58.2
```

The PC also has Wi-Fi and a disconnected Realtek adapter. Always test the robot
interface explicitly; a plain `ping 192.168.58.2` can use the wrong interface.

```powershell
ping -n 2 -S 192.168.58.3 192.168.58.2
arp -a | findstr 192.168.58.2
```

If `ping -S` succeeds, the link is currently up. If it times out, inspect/reseat
the cable at both the controller and the PC before restarting the app.

## Typical log symptoms

```text
An error occurred during XML-RPC call: GetControllerIP:
controller reply unavailable; outcome unknown, do not resend

ERROR: controller connection failed: Robot SDK not connected
```

Other possible symptoms:

- robot telemetry becomes stale or `robot_state` stops updating;
- camera monitor may still be running even though the robot is unreachable;
- the app falls back to read-only/raw-arm mode;
- `physical_motion_authorized` remains false;
- a reconnect may show old teaching points or `R1-R4 calibration unavailable`.

The camera monitor staying alive does **not** prove the robot link is healthy.

## Recovery checklist

1. Stop the current session; do not retry motion commands.
2. Inspect and re-seat the Ethernet cable at the FR3 controller and the PC.
3. Check the adapter/link LED (`Ethernet 3`, 100 Mbps).
4. Run the explicit ping:
   ```powershell
   ping -n 2 -S 192.168.58.3 192.168.58.2
   ```
5. Read teaching points read-only:
   ```powershell
   .\.venv312\Scripts\python.exe tools\diagnostics\read_teaching_points.py --connect --ip 192.168.58.2
   ```
6. Start the app again with `.\RUN.bat --robot`.
7. Wait for a fresh read-only connection and stable telemetry. Only then consider
   F9/F10; F9/F10 remain explicit operator gates.

## Rules

- Do **not** automatically retry/replay a Cartesian, joint, gripper, or
  calibration command after a lost RPC reply. The outcome may be unknown.
- Do **not** interpret a successful camera frame as proof that the robot link is
  connected.
- Do **not** use a stale teaching-point snapshot after reconnect. Re-read R1-R4
  and WObj/tool frames from the controller.
- A single transient disconnect is not evidence that motion is safe; require a
  stable link and a fresh read-only state first.

## Latest read-only snapshot

See:

```text
reports/r1_r4_current_20261028_192917/teaching_points.json
reports/r1_r4_current_20261028_192917/summary.txt
```

This snapshot is historical evidence, not a live connection.
