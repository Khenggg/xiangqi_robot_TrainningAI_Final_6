# Bàn giao: bàn cờ ở phía X− của viewer, đường ngang giữa bàn hướng về FR3

Ngày ghi nhận: 2026-09-25. Đây là trạng thái của **bản mô phỏng thử nghiệm**, chưa phải calibration cho FR3 thật.

## 1. Yêu cầu đã chốt với người dùng

- Giữ tâm bàn cờ ở **phía X− trong hệ 3D world của viewer**, cách gốc đế robot 360 mm theo trục X.
- "Đường trung lộ" theo cách người dùng gọi là **đường nằm ngang ở giữa mặt bàn cờ** (đường chạy qua chiều 9 cột/qua vùng sông). Không được hiểu là đường dọc nối hai Tướng.
- Đường ngang này phải nằm theo phương nối bàn cờ với robot, giống cách cạnh ngang của bàn cờ ở vị trí cũ hướng về robot. Giữ **cột 0 gần đế robot hơn cột 8**, như bố trí cũ.
- Mục đích trước mắt là xem và xác nhận hình dáng trong viewer. Chưa có phép đo/calibration cho vị trí bàn mới; không điều khiển FR3 thật.

Lần trước chỉ dời **tâm** bàn sang X− và giữ yaw 90°; vì vậy chiều dài 10 hàng lại hướng về robot. Người dùng chỉ ra đó là sai ý. Đã sửa bằng cách quay mặt bàn 90° quanh tâm, từ yaw 90° sang yaw 0°; góc camera mặc định đã được đưa về như cũ.

## 2. Nơi làm việc và trạng thái Git

- Repository chính: `D:\OJT\xiangqi_robot_TrainningAI_Final_6`.
- Worktree thử nghiệm: `D:\OJT\_fr3_gripper_ground_20260925`.
- Worktree đang ở detached HEAD `fab750a918c1457ae14bfda900572fb16f846e26` (mốc nhánh tích hợp). **Các thay đổi dưới đây chưa commit.**
- `.git` trong worktree là file trỏ vào `.git/worktrees/_fr3_gripper_ground_20260925` của repository chính. Trong sandbox của agent có cảnh báo ownership; có thể dùng `git -c safe.directory=D:/OJT/_fr3_gripper_ground_20260925 -C D:/OJT/_fr3_gripper_ground_20260925 status --short` cho lệnh chỉ đọc, thay vì sửa Git config toàn cục.
- Khi tạo tài liệu, `git status --short` báo 7 file sửa: `robot-3d-viewer/board.mjs`, `robot-3d-viewer/main.mjs`, `shared/gripper_visual_asset.json`, `shared/robot_profiles/fr3.json`, `shared/virtual_fr3_scene.json`, `shared/virtual_gripper_profile.json`, `src/simulation/runtime.py`. Xem bổ sung ở mục 9 cho trạng thái về sau.
- Những thay đổi ở `shared/gripper_visual_asset.json`, `shared/robot_profiles/fr3.json`, `shared/virtual_gripper_profile.json` và nhiều phần gripper trong `main.mjs` **đã có từ công việc chỉnh chiều dài đầu kẹp trước đó**. Giữ nguyên chúng. `shared/virtual_fr3_scene.json` cũng chứa thay đổi TCP/gripper có trước bước xoay bàn; không phục hồi cả file về HEAD.
- Chưa sửa repository chính, chưa gửi lệnh tới `192.168.58.2`, chưa ra lệnh chuyển động vật lý.

## 3. Quy ước hình học hiện tại

Đơn vị trong `shared/virtual_fr3_scene.json` và Three.js là **mét**. Chiều vật lý bàn lấy từ `shared/physical_geometry.json`: rộng 367 mm theo trục cột `u`, dài 410 mm theo trục hàng `v`, mặt bàn ở cao 10.5 mm so với sàn mô phỏng. Khoảng cách ô là 40 mm.

Đổi hệ robot base sang 3D world:

```text
X_world = -Y_robot
Y_world = +Z_robot
Z_world = -X_robot
u = (col - 4) * 0.040 m
v = (row - 4.5) * 0.040 m
```

`BoardPlacementState` dùng `R_robot_from_board = Rz(board_yaw_deg) @ R0`, với `R0` là yaw 0°. Bố trí đang cần là:

| Đại lượng | Vị trí cũ | Bố trí X− hiện tại |
|---|---:|---:|
| Tâm mặt bàn trong robot base | `(-0.36, 0, 0.0105)` m | `(0, +0.36, 0.0105)` m |
| Tâm mặt bàn trong 3D world | `(0, 0.0105, +0.36)` m | `(-0.36, 0.0105, 0)` m |
| `board_yaw_deg` | `90°` | `0°` |
| Trục cột `+u` trong world | `+Z_world` | `−X_world` |
| Trục hàng `+v` trong world | `+X_world` | `+Z_world` |
| Cột 0 ở đường ngang giữa bàn | `Z_world ≈ +0.20` m | `X_world ≈ −0.20` m, **gần robot** |
| Cột 8 ở đường ngang giữa bàn | `Z_world ≈ +0.52` m | `X_world ≈ −0.52` m, **xa robot** |

Tọa độ giao điểm `(row=0, col=0)` mới: robot base `(0.18, 0.20, 0.0105)` m; world `(-0.20, 0.0105, -0.18)` m. Cạnh vật lý gần robot của bàn ở `X_world ≈ −0.1765` m, cạnh xa ở `X_world ≈ −0.5435` m. Theo chiều dài 10 hàng, bàn trải từ `Z_world = −0.205` đến `+0.205` m.

Các con số này mô tả **hình học mô phỏng**. Chưa có phép đo ngoại chuẩn camera → bàn → đế robot cho cách đặt mới.

## 4. Thay đổi đã làm cho bản xem trước

1. `shared/virtual_fr3_scene.json`: tâm world/robot như bảng trên; yaw `0.0`; gốc ô `(0,0)` và nhãn các trục hàng/cột cập nhật đồng bộ. Trạng thái file vẫn là `SIMULATION_ONLY_PROVISIONAL`.
2. `robot-3d-viewer/board.mjs`: `fetchScenePlacement()` nay đọc `board_yaw_deg` từ JSON. `buildBoardGrid()` áp dụng `group.rotation.y = (boardYawDeg - 90)°` ngay lúc tạo bàn. Với yaw 0°, mesh quay `−90°` quanh Y; trước đó đường tải JSON chỉ đọc tâm và mesh khởi tạo ở rotation 0 bất kể yaw.
3. `boardPointToXYZ()` vốn đã tính vị trí quân cờ theo yaw hoặc `T_robot_from_board`; nhờ (1)–(2), quân cờ và texture/mesh bàn khớp nhau ở chế độ offline.
4. `src/simulation/runtime.py`: `_load_scene_config()` nay lấy yaw và tâm nominal từ cùng JSON, rồi truyền vào `BoardPlacementState.compute()`. Trước sửa, runtime mặc định yaw 90° dù PyBullet world đã đọc yaw từ JSON, nên kết nối live có thể làm lệch trạng thái giữa hai bên.
5. `robot-3d-viewer/main.mjs`: đưa camera về góc mặc định trước đó (`position=(0.75,0.75,0.75)`, `target=(0,0.15,0.25)`); phần hiển thị tọa độ ô khi nhận placement dùng phép đổi world → robot từ điểm thật thay cho công thức cố định yaw 90°. Nhãn yaw không còn in cứng `col=-X, row=-Y`.

**Không đồng nhất diff toàn file với phần sửa bàn:** `main.mjs` còn nhiều thay đổi về hình CAD gripper từ trước. Hãy đọc diff theo từng hunk và giữ lại.

## 5. Đường đi dữ liệu cần nắm

```text
shared/virtual_fr3_scene.json
  ├─ viewer: fetchScenePlacement → setScenePlacement
  │    ├─ buildBoardGrid → group pose/yaw, texture mặt bàn
  │    └─ boardPointToXYZ → vị trí quân cờ/ô được chọn
  ├─ simulator: VirtualPhysicalWorld.__init__ → BoardPlacementState
  │    ├─ _spawn_board → collider PyBullet
  │    └─ _spawn_pieces / reset_pieces → rigid bodies theo ô
  └─ runtime: VirtualXiangqiSimulation._load_scene_config → placement_state
       └─ telemetry board_placement/world_state → applyAuthoritativeBoardPlacement
```

Viewer static do `robot-3d-viewer/serve.mjs` phục vụ. Trang mặc định `/`, **không phải** `/robot-3d-viewer/`. `index.html` tải Three.js và OCCT từ CDN, nên HTTP 200 của server local chưa chứng minh trang render thành công nếu browser thiếu mạng/CDN.

## 6. Trạng thái xác minh tại thời điểm bàn giao

- `node --check robot-3d-viewer/board.mjs`: exit code **0**.
- `node --check robot-3d-viewer/main.mjs`: exit code **0**.
- `git diff --check` trong worktree: exit code **0** (Git chỉ cảnh báo chuyển LF/CRLF).
- Đọc JSON và tính độc lập phép đổi tọa độ cho `(row=0,col=0)`: sai khác `robot/world ≈ 2.78e-17 m` do số thực; cột 0 ở `X_world = −0.20 m`, cột 8 ở `−0.52 m`.
- `GET http://127.0.0.1:8085/`: HTTP **200**. `GET /shared/virtual_fr3_scene.json`: HTTP **200**, yaw trả về `0`.
- `127.0.0.1:8765`: **ECONNREFUSED** khi kiểm tra; simulation WebSocket live chưa chạy tại thời điểm này. Nút **Connect live** không được coi là đã kiểm chứng.
- Không có browser/app đang mở qua công cụ UI của agent; **chưa có ảnh chụp xác nhận trực quan** từ màn hình người dùng.
- Môi trường thực thi của agent này có `py.exe` nhưng `py -0p` trả `No installed Pythons found!`; `py -3 --version` exit **112**. **Chưa chạy pytest/PyBullet** cho yaw 0°. Không diễn giải các phép kiểm tra Node là kiểm chứng vật lý.
- `codebase-memory-mcp detect_changes` trên linked worktree báo hơn 200 file dù `git status` chỉ có 7 file sửa; kết quả blast-radius đó không đáng dùng làm danh sách diff thực tế.

Nếu server HTTP không còn chạy trong phiên tiếp theo, từ thư mục worktree chạy:

```powershell
node .\robot-3d-viewer\serve.mjs 8085
```

Sau đó mở `http://127.0.0.1:8085/` và tải cứng trang (`Ctrl+F5`). Đây là **preview offline**; không cần bấm Connect live để xem bàn và quân cờ ở trạng thái ban đầu. Nếu có Python/đầy đủ dependency và muốn thử *VirtualFR3Backend* (không phải FR3 thật), lệnh dự án là `python .\tools\simulation\run_simulation_server.py` để mở `ws://127.0.0.1:8765`; phải xác minh đúng interpreter/môi trường trước khi chạy.

## 7. Những vấn đề còn mở, theo độ ưu tiên

### P0 — Chặn suy luận an toàn sai trước khi cho phép chuyển động mô phỏng

1. `shared/cell_reachability_dataset.json` vẫn ghi trong metadata: `board_yaw_deg=90`, `forward_shift_mm=25`, `gripper_length_m=0.15`, 90 ô. Bộ dữ liệu này **không khớp** yaw 0° và chiều TCP hiện tại 0.1683 m trong cấu hình; runtime vẫn đọc dataset và có thể dùng joint seeds cũ. Cần tạm gắn trạng thái `STALE/UNVALIDATED`, chặn hoặc bỏ qua seed cũ cho placement mới, rồi tái sinh/kiểm định nếu thực sự dùng chuyển động. Đừng dùng badge reachability cũ như bằng chứng an toàn.
2. `robot-3d-viewer/main.mjs::computeGeometricPrecheck` khoảng dòng 859–872 còn tâm robot cứng `X=−(360+d) mm, Y=0` và tool dài `150 mm`; `updateGeometricPrecheckUI` mặc định yaw 90°. Badge `GEOMETRIC PASS` hiện tại không có giá trị cho bàn X−. Nên lấy tâm, yaw, tool length từ placement/profile hiện hành và phân biệt **ước lượng tầm với** với kiểm tra quỹ đạo/collision.
3. `src/simulation/runtime.py::set_board_placement` khoảng dòng 1259–1285 khi tái tạo placement có truyền yaw hiện tại, nhưng `compute_geometric_precheck()` không nhận yaw hiện tại. Logic `forward_shift_mm` của `BoardPlacementState.compute()` luôn dời theo `−X_robot`, trong khi tâm bàn mới nằm trên `+Y_robot`; slider dịch chuyển có thể làm bàn trượt ngang thay vì dọc hướng robot. Chưa dùng thao tác dời bàn động ở cấu hình này cho đến khi thống nhất lại trục dịch chuyển và toàn bộ telemetry.
4. Khi mở live, đảm bảo gói `board_placement` đầu tiên, collider PyBullet, 32 quân và mesh viewer cùng tâm/yaw/placement_version. Nếu nguồn live đang chạy từ process Python cũ, phải khởi động lại **simulator ảo** để nhận mã mới; không kết nối nhầm backend phần cứng.

### P1 — Hoàn thiện viewer và kiểm chứng parity

5. `robot-3d-viewer/ruler.mjs` khoảng dòng 343–347 và 500–603 còn mốc cột theo trục Z ở vị trí cũ; cạnh bàn/hit proxies cũng cố định tâm `(0,0.0105,0.36)` và chỉ cập nhật `Z`. Với bố trí X−, click thước/mép bàn có thể chỉ sai. Chuyển chúng sang dữ liệu `board_center_world_m`, `board_yaw_deg`/transform và hình học 367 × 410 mm; test click ở bốn cạnh.
6. `robot-3d-viewer/main.mjs::applyAuthoritativeBoardPlacement` quanh dòng 1057 còn fallback `Z_world=0.36+d`; dùng đúng center từ packet, và xử lý rõ trường hợp packet thiếu center. Rà tất cả nhãn/điểm chọn ô còn giả định yaw 90°.
7. Mở viewer thật, chụp từ phía đế robot và từ trên cao. Kiểm tra đường ngang giữa bàn chạy theo **X_world**, cột 0 gần robot, quân đen/đỏ và chữ trên texture đúng vị trí, không đảo/mirror. Đây là gate trả lời câu hỏi của người dùng; xác nhận với họ trước khi thay đổi tiếp bố trí.

### P2 — Thử nghiệm hệ thống chỉ sau P0/P1

8. Trong môi trường có Python, chạy test mục tiêu theo `.agents/skills/fast-testing/SKILL.md`, ví dụ các file `test_phase3_board_orientation_90.py`, `test_phase3_dynamic_board_placement.py`, `test_world_coordinate_parity.py`, `test_virtual_physical_world.py`, cộng test viewer `test_viewer_coordinate_contract.mjs`. Các test cố định yaw 90° có thể cần fixture mới cho yaw 0°; không sửa kỳ vọng cũ để ép pass. Có thể dùng `./tools/test_fast.ps1 -Workers 2 -Tests ...` cho Python theo hướng dẫn dự án.
9. Kiểm tra thế giới PyBullet tại yaw 0°: tâm mặt bàn, quaternion/collider, bốn góc, `(row=0,col=0)`, `(row=9,col=8)`, cả 90 ô, trạng thái reset và gói world_state. Nếu chuyển động ảo được dự tính, kiểm tra toàn quỹ đạo và collision guard với tool hiện tại; dừng nếu placement, tool hoặc dataset version không khớp.
10. Việc đặt bàn thật cần chuỗi đo riêng camera → mặt bàn/lưới → robot base → flange/TCP, cùng kiểm tra payload, tầm với, khoảng hở và nút dừng khẩn. Không suy ra tọa độ an toàn của FR3 thật từ hình viewer hay từ việc gripper đang chạm sàn. Người dùng chưa ủy quyền chuyển động FR3 thật trong chuỗi làm việc này.

## 8. Chỉ dẫn cho AI tiếp theo

- Đọc `AGENTS.md` trong repository và `PROJECT_CONTEXT.md`; lưu ý `PROJECT_CONTEXT.md` có mô tả hướng bàn cũ, cần ưu tiên kiểm tra mã/cấu hình thực tế, không âm thầm coi tài liệu cũ là phép đo mới.
- Trước khi sửa mã, theo quy tắc `D:\OJT\AGENTS.md`: dùng `codebase-memory-mcp` (`index_repository` nếu chưa index, `get_architecture`, `search_graph`, `trace_path`), sau sửa dùng `detect_changes`, và luôn đọc file chính xác trước khi sửa. Project graph đã được index với tên `D-OJT-_fr3_gripper_ground_20260925` tại thời điểm bàn giao; kiểm tra lại trạng thái index nếu phiên khác.
- Làm trong worktree riêng/hiện tại khi chạy mô phỏng; không lấy thay đổi chưa commit làm bằng chứng của HEAD. Giữ nguyên các chỉnh sửa gripper có sẵn. Nếu cần tạo commit, chỉ stage các hunk đã được người dùng chấp nhận.
- Đừng tự bật chế độ `--disable-collision-guard`. Không dùng các script trong `tools/hardware_tests/` hoặc IP `192.168.58.2` để di chuyển FR3 nếu chưa có ủy quyền rõ ràng cho tác vụ phần cứng hiện tại.
- Ưu tiên câu trả lời ngắn, đúng câu hỏi người dùng; sau khi họ xem bố trí bàn, hỏi họ xác nhận chiều đường ngang/cột gần robot trước khi chuyển sang thiết kế calibration hay điều khiển.

## 9. Bổ sung cùng ngày: gripper nâng cấp biến mất và đã khôi phục

Người dùng báo gripper nâng cấp không còn thấy trên viewer. Kiểm tra mã trong worktree sau khi tạo tài liệu này thấy `shared/gripper_visual_asset.json` vẫn giữ mục tiêu flange → tip `0.168058 m`, nhưng `robot-3d-viewer/main.mjs::buildRobotArm` không còn đoạn mesh nối từ J6 đến CAD gripper và nhánh STEP lỗi đặt procedural gripper ngay tại gốc wrist, không dùng datum flange. Đây là nguyên nhân mã có thể giải thích việc phần kéo dài không xuất hiện; chưa có ảnh browser để khẳng định nhánh STEP hay fallback thực tế đã chạy.

Đã sửa `robot-3d-viewer/main.mjs`:

- CAD branch: tính lại mount từ `flange_target_offset_m`, thêm `fr3-gripper-adapter-collar` dài `0.050058 m` từ datum J6 `z=0.1 m` đến CAD flange `z=0.150058 m`. Chiều CAD sau scale là `147.5 mm × 0.0008 = 0.118 m`; tổng flange → tip `0.050058 + 0.118 = 0.168058 m`.
- Fallback branch: đặt procedural gripper tại `robot_flange_origin_m` và scale chiều Z tới `target_flange_to_tip_m`, để nó vẫn xuất hiện ở đúng vùng J6 khi thư viện STEP/CDN không tải được.
- Giữ các thay đổi bàn cờ xuất hiện trong `main.mjs` sau bản bàn giao đầu tiên; không hoàn nguyên file.

Kiểm tra sau sửa: `node --check main.mjs` exit 0; `git diff --check` exit 0; asset STEP, config và `main.mjs` đều HTTP 200 qua server 8085; `node tests/unit/test_viewer_gripper_and_telemetry.mjs` exit 0. Chrome headless trong sandbox thoát lỗi GPU/sandbox và không tạo screenshot; CUA không có browser, Playwright CLI không có trong cache. Do đó **chưa xác nhận hình ảnh cuối cùng bằng screenshot**. Người dùng cần tải cứng viewer và báo nếu vẫn không thấy; lúc đó cần console log `[VIEWER] Using procedural gripper fallback:` hoặc ảnh từ browser của họ.

Sau tài liệu ban đầu, `git status` còn xuất hiện sửa đổi ở `robot-3d-viewer/ruler.mjs`, `shared/cell_reachability_dataset.json`, `src/domain/board_pose.py`. Chúng không thuộc sửa gripper này; đọc diff và bảo toàn các hunk đó khi làm tiếp.
