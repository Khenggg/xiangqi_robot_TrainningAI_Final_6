# Đánh giá kiến trúc Xiangqi Robot FR3 cho MVP vật lý

**Ngày lập:** 2026-09-24  
**Mục tiêu:** một thao tác gắp–đặt quân cờ vật lý đáng tin cậy với độ phức tạp thấp nhất, sau đó mới mở rộng thành ván cờ tự động.  
**Phạm vi bằng chứng:** commit tích hợp `fab750a918c1457ae14bfda900572fb16f846e26` và commit sửa simulator chưa merge `363566773e42336a3542bc1240984152198382c3`. Các thay đổi chưa commit không được dùng để kết luận.  
**Trạng thái phần cứng:** chưa kết nối hoặc điều khiển FR3 thật; không có phép đo vật lý mới trong đánh giá này.

## Kết luận và quyết định kiến trúc

**Giữ đường ứng dụng Python `Observation → Game/AI → Intent → Resolver → Executor → FAIRINO SDK`, nhưng thu hẹp MVP xuống một nước đi không bắt quân, trong vùng bàn nhỏ và có người giám sát.** Giữ PyBullet làm công cụ phát hiện lỗi trong phát triển và Three.js làm lớp quan sát. Chưa cho phép chơi cờ tự động trên FR3 thật chỉ vì unit test hoặc simulator đã xanh. Cần một gate duy nhất trước thực thi vật lý, dùng hình học và calibration đã đo để kiểm toàn bộ quỹ đạo, cùng bước xác nhận kết quả gắp–đặt độc lập.

Không chuyển toàn bộ hệ thống sang ROS 2/Gazebo/MuJoCo ở giai đoạn này. Sau khi chốt geometry, làm một thử nghiệm MoveIt 2 giới hạn trên cùng model và một quỹ đạo; chỉ thay **lớp lập kế hoạch/kiểm va chạm** nếu nó cải thiện bằng chứng an toàn với chi phí tích hợp chấp nhận được. Đây là **một hướng kiến trúc**: ứng dụng và backend hiện tại vẫn là xương sống của MVP; planner là ranh giới có thể thay thế.

## 1. Bằng chứng kiểm tra

Các lệnh dưới đây đã chạy ngày 2026-09-23 trong hai worktree tách biệt theo từng commit. `test_fast.ps1` là test runner của repository; không chạy full suite và không chạy hardware tests.

| Mốc | Lệnh / phạm vi | Kết quả |
|---|---|---|
| `fab750a9` | `.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_phase3b_wiring.py,tests/unit/test_motion_failure_semantics.py,tests/unit/test_physical_board_calibration.py` | Exit `0`; **42 passed**. |
| `fab750a9` | `.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_phase2_vision_and_carryover.py,tests/unit/test_motion_resolver.py,tests/unit/test_motion_executor.py` | Exit `0`; **57 passed**. |
| `3635667` | `.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_simulator_tool_collision_envelope.py` | Exit `0`; **5 passed**. Test đích tái hiện TCP ở trên mặt bàn nhưng thân tool xuyên bàn: [test_simulator_tool_collision_envelope.py:89–146](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/tests/unit/test_simulator_tool_collision_envelope.py#L89-L146). |
| `3635667` | `.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_virtual_fr3_backend.py,tests/unit/test_trajectory_waypoints.py` | Exit `0`; **12 passed**. |
| Cả hai mốc | `node tests/unit/test_viewer_single_motion_authority.mjs`; `node tests/unit/test_viewer_coordinate_contract.mjs` | Từng lệnh exit `0` sau khi cung cấp dependency Three.js cho worktree. |
| `3635667` | `node tests/unit/test_viewer_gripper_and_telemetry.mjs`; `node tests/unit/test_viewer_profile_binding.mjs` | Từng lệnh exit `0`. Kiểm tra profile, telemetry và transform 90 ô; chưa phải kiểm chứng hình học vật lý. |

Thử trực tiếp simulator qua trình duyệt với `node serve.mjs 8086` và `python tools/simulation/run_simulation_server.py --host 127.0.0.1 --port 8765 --speed-factor 25`, collision guard bật:

- Lệnh hợp lệ đổi J1 từ `0°` sang `1°`; telemetry live cập nhật `[1,-45,90,-45,-90,0]`.
- Lệnh đến `[0,-60,110,-105,-120,0]` bị từ chối ở waypoint `14/61`: `Gripper colliding with obstacle piece red_cannon_0 (dist=1.34mm < margin 2.00mm)`. Telemetry giữ `[1,-45,90,-45,-90,0]` và báo `motion_state=COLLISION_REJECTED`.
- Khi **offline**, cùng pose vẫn được vẽ cục bộ, với nhãn `UNVALIDATED PREVIEW`. Khi kết nối lại, viewer trở về pose từ backend. Đây là preview chưa kiểm chứng, không phải bằng chứng backend đã chấp nhận chuyển động nguy hiểm. [Luồng live/offline trong `main.mjs`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/robot-3d-viewer/main.mjs#L785-L828).

Ảnh chụp phiên trình duyệt ở worktree tạm **không còn là artifact được lưu trong repository** tại ngày lập file; kết quả trình duyệt trên dựa vào telemetry và quan sát đã ghi trong phiên đánh giá. Cần lưu ảnh/video, log và calibration version cùng test E2E ở các lần nghiệm thu tiếp theo.

## 2. Phát hiện quan trọng

| ID, nguồn gốc | Nhận định và tác động | Bằng chứng; mức tin cậy; chưa xác minh |
|---|---|---|
| **F1 — tồn tại ở commit tích hợp** | Gate sẵn sàng vật lý có thể thành `true` sau calibration bàn dù profile chiều cao gắp vẫn mang provenance `PROVISIONAL_SIMULATION`; code cảnh báo nhưng vẫn dựng Resolver/Executor. Vì vậy `is_robot_ready` chưa đủ nghĩa là đã sẵn sàng gắp vật lý. | [`config.py:55–60`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/config.py#L55-L60), [`hardware_manager.py:310–340`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/hardware/hardware_manager.py#L310-L340), [`hardware_manager.py:606–628`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/hardware/hardware_manager.py#L606-L628). **Cao** về hành vi mã; **chưa** thử FR3 thật. Cấu hình mặc định `BOARD_CALIBRATION_MODE=None` vẫn fail-closed. |
| **F2 — tồn tại ở commit tích hợp** | Resolver tính waypoint từ ô bàn; Executor kiểm placement version một lần ở đầu plan rồi gửi từng bước tới backend. Đường backend vật lý gửi `MoveJ`/`MoveCart` và kiểm mã trả về, nhưng không thể hiện một kiểm va chạm **toàn quỹ đạo** tương đương với đường simulator. Không suy ra controller FAIRINO không có bảo vệ nội tại; chỉ kết luận ứng dụng chưa chứng minh gate này. | [`resolver.py:146–208`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/motion/resolver.py#L146-L208), [`executor.py:132–169`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/motion/executor.py#L132-L169), [`physical_fr3.py:421–528`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/hardware/backends/physical_fr3.py#L421-L528). **Cao** về đường mã; khả năng controller **chưa xác minh**. |
| **F3 — tồn tại ở commit tích hợp** | Game chỉ cập nhật state sau khi motion trả `success`, là ranh giới tốt. Nhưng physical Executor không có payload verifier ở cấu hình hiện tại; `EXPECTED_ATTACHED`/`EXPECTED_RELEASED` có thể đi qua plan mà không chứng minh quân đã được gắp hoặc đặt. Game có nguy cơ đồng bộ sai với bàn thực. | [`ai_execution.py:102–129`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/core/ai_execution.py#L102-L129), [`hardware_manager.py:336–340`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/hardware/hardware_manager.py#L336-L340), [`executor.py:231–262`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/motion/executor.py#L231-L262). **Cao** về code; tần suất lỗi gắp thực **chưa biết**. |
| **F4 — tồn tại trước; commit simulator cải thiện một phần** | `3635667` thêm proxy `tool_bridge` và kiểm quỹ đạo trước khi commit trạng thái; test bắt được trường hợp TCP ở trên bàn nhưng thân tool xuyên bàn. Viewer live dùng telemetry; offline vẫn chỉnh mesh cục bộ, nay cảnh báo rõ. Chưa chứng minh mesh người dùng thấy, proxy PyBullet và tool thật có cùng envelope. | [`gripper.py:69–89`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/src/simulation/physics/gripper.py#L69-L89), [`virtual_fr3_backend.py:517–538`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/src/simulation/virtual_fr3_backend.py#L517-L538), [`main.mjs:595–624`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/robot-3d-viewer/main.mjs#L595-L624). **Cao** cho simulator đã thử; parity vật lý **chưa xác minh**. |
| **F5 — trôi tài liệu và dư mã** | `PROJECT_CONTEXT.md` ghi mốc xác minh `7ce5e71`, `CURRENT_STATE.md` ghi `e8ac273`, đều cũ hơn commit tích hợp. Trong `3635667`, `VirtualFR3Backend` định nghĩa `get_state_snapshot` hai lần; phương thức sau ghi đè phương thức mới. Đây là chi phí context discovery và dấu hiệu commit chưa khép kín. | [`PROJECT_CONTEXT.md:4`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/PROJECT_CONTEXT.md#L4), [`CURRENT_STATE.md:10`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/CURRENT_STATE.md#L10), [`virtual_fr3_backend.py:223`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/src/simulation/virtual_fr3_backend.py#L223), [`virtual_fr3_backend.py:396`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/363566773e42336a3542bc1240984152198382c3/src/simulation/virtual_fr3_backend.py#L396). **Cao**. |

## 3. Trả lời tám câu hỏi kiến trúc

1. **Có over-engineered?** Có đối với mốc một lần gắp–đặt tin cậy. Giá trị của nhiều abstraction hiện hữu chỉ được chứng minh khi kết nối được với kết quả vật lý. Giữ contract và interlock; giảm các bài toán mô phỏng và tính năng đồng thời.
2. **Tiếp tục custom stack hay chuyển?** Giữ stack hiện tại cho MVP giới hạn. FAIRINO có repository ROS 2 chứa cấu hình MoveIt 2 cho FR3, nhưng điều kiện phiên bản robot, controller, driver, ngàm và môi trường chạy phải được xác nhận; MoveIt hiện hướng dẫn chủ yếu trên Ubuntu 22.04/24.04. Làm một thử nghiệm có thời hạn trước khi thay planner. [FAIRINO ROS 2](https://github.com/FAIR-INNOVATION/frcobot_ros2), [MoveIt Getting Started](https://moveit.picknik.ai/main/doc/tutorials/getting_started/getting_started.html).
3. **Nguồn chân lý cho frame và geometry?** Một hồ sơ geometry/calibration có phiên bản, định nghĩa frame, origin, chiều trục, đơn vị, provenance và ngân sách sai số. `BoardPlacementState` đã có `T_robot_from_board` và `placement_version` ([board_pose.py:173–180](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/src/domain/board_pose.py#L173-L180)); hiện vẫn có dữ liệu vật lý, scene mô phỏng và asset viewer với provenance khác nhau: [physical_geometry.json](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/shared/physical_geometry.json#L1-L27), [fr3.json](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/shared/robot_profiles/fr3.json#L169-L180), [virtual_fr3_scene.json](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/shared/virtual_fr3_scene.json#L1-L55), [gripper_visual_asset.json](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/shared/gripper_visual_asset.json#L1-L9).
4. **Thứ tự calibration?** Chuỗi biến đổi dữ liệu là `pixel → board → robot base → flange/TCP`. Thứ tự thao tác đo có phụ thuộc ngược: phải hiệu chuẩn TCP hoặc offset pointer trước khi dùng FR3 dạy điểm bàn. Phần 4 ghi trình tự khả thi.
5. **Digital Twin chính xác tới mức nào?** Đủ bắt lỗi frame, reachability, tool/bàn/quân và quỹ đạo trong vùng thử. Twin không thay phép đo clearance hoặc xác nhận kết quả thực. Không cần mô phỏng lực gắp hoàn chỉnh trước lần thử vật lý có giám sát đầu tiên.
6. **Acceptance E2E?** Chạy cùng một command qua backend, PyBullet, telemetry và trình duyệt; lưu pose trước/sau, min clearance và lý do từ chối. Thử riêng live/offline, timeout, mất telemetry, mất quân và recovery. Điều kiện cụ thể ở phần 5.
7. **Roadmap mới?** Metrology → một quỹ đạo trên bàn trống → một quân → xác nhận vật lý → camera/game → mở rộng bàn → bắt quân. Dừng thêm tính năng trước khi một bước gắp–đặt được nghiệm thu.
8. **Giảm complexity/coupling và thời gian agent?** Giữ một bộ dữ liệu calibration, một chủ thể quyết định pose live, một script smoke xuyên tầng ngắn; test theo contract bị ảnh hưởng, không lặp full suite sau mỗi sửa nhỏ. Loại mã chết và cập nhật tài liệu ngữ cảnh theo commit.

### Lựa chọn từng thành phần

| Giữ | Hoãn | Bỏ khỏi đường MVP |
|---|---|---|
| `MoveObservation`, game/Intent/Resolver/Executor, `BoardPlacementState`, connect/enable/mode tách biệt, FAIRINO SDK, PyBullet và viewer cho phát triển. | Visual pick offset liên tục; capture bin; quét toàn bộ nước đi; digital twin có động lực học gắp đầy đủ; tích hợp MoveIt 2 sau thử nghiệm giới hạn. | Coi 4,715 mm hay 40 mm mặc định là ngưỡng an toàn đã đo; sao chép thủ công transform/TCP; thông điệp “collision-free” chỉ dựa trên hình ảnh hoặc một endpoint. |

MoveIt [Planning Scene](https://moveit.picknik.ai/main/doc/examples/planning_scene/planning_scene_tutorial.html) cung cấp kiểm va chạm/ràng buộc và theo dõi scene, nên đáng thử ở ranh giới planner. [tf2](https://github.com/ros2/geometry2) là công cụ chuẩn cho cây frame nếu sử dụng ROS, nhưng quy ước frame chặt có thể áp dụng ngay không cần ROS. [Gazebo](https://gazebosim.org/docs/harmonic/ros2_integration/) cần bridge ROS–simulator bổ sung. Chuyển sang [MuJoCo](https://mujoco.readthedocs.io/en/3.3.7/XMLreference.html) không tự giải quyết parity: mesh hiển thị và hình học dùng cho collision có thể khác nhau.

## 4. Calibration và nguồn dữ liệu duy nhất

1. **Metrology cơ khí:** đo board ID, khoảng cách lưới, độ phẳng, chiều cao/quy cách quân, vỏ tool và hành trình ngàm; ghi phương pháp, độ không đảm bảo và ảnh/biên bản đo. Các số trong JSON hiện tại là đầu vào để đối chiếu, chưa thay hồ sơ đo có sai số.
2. **Flange/TCP và pointer:** đo `T_flange_from_tcp` hoặc phép nghịch đảo theo quy ước đã chọn; xác nhận tool ID/user frame trên controller. TCP danh định 150 mm đang ghi `MEASURED_APPROXIMATE`, cần độ không đảm bảo, orientation và kiểm tra tại nhiều pose. Nếu dùng pointer dạy bàn, xác lập offset pointer trước.
3. **Camera → board:** hiệu chỉnh intrinsics/distortion, homography từ pixel sang giao điểm bàn và đánh giá trên điểm giữ lại không dùng khi fit. Với MVP quan sát *ô rời rạc*, chưa cần áp dụng visual pick offset liên tục; nếu dùng offset, phải đo lỗi pixel→mm tại vùng gắp.
4. **Board → robot base:** dùng điểm R1–R4 với pointer/TCP đã biết, fit `T_robot_from_board`, kiểm điểm giữ lại, độ nghiêng và sự cố định của bàn. Mỗi lần bàn, tool hoặc camera dịch chuyển phải làm mất hiệu lực calibration liên quan.
5. **Ghép chuỗi:** kiểm `image → board → base → TCP` trên các điểm vật lý độc lập; xuất cùng một artifact có `schema_version`, `calibration_version`, board/tool/camera ID, timestamp, frame, unit, transform, covariance/sai số và provenance. Dùng **m/rad nội bộ**, chỉ đổi **mm/deg** tại adapter SDK. Viewer nhận pose live từ telemetry của backend; offline phải được nhận diện là preview không có quyền điều khiển.

## 5. Acceptance gates trước commissioning

Các ngưỡng vật lý phải rút từ độ không đảm bảo đo, độ lặp lại và thông số thiết bị; **không** lấy ngưỡng mô phỏng hoặc các `PROPOSED_INITIAL_TEST_VALUE` trong [PHASE4_ACCEPTANCE_MATRIX.md](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/docs/PHASE4_ACCEPTANCE_MATRIX.md#L140-L148) làm chứng nhận an toàn.

| Gate | Bằng chứng cần lưu | Dừng nếu |
|---|---|---|
| **G0 — geometry/calibration** | Biên bản đo bàn/quân/tool/TCP, tool/user ID, đơn vị, frame, độ không đảm bảo và phiên bản. | Đại lượng ảnh hưởng clearance còn `PROVISIONAL`; tổng sai số có thể vượt clearance khả dụng. |
| **G1 — parity frame, pose, envelope** | Điểm góc và điểm giữ lại qua camera, board, base, FK/controller, PyBullet và viewer; kiểm collision envelope bao phủ tool thật trong sai số đo. | Pose vượt ngân sách sai số; bộ phận tool nằm ngoài envelope; calibration/version không khớp. |
| **G2 — toàn quỹ đạo và single motion authority** | Log mọi mẫu quỹ đạo hoặc chứng cứ bảo thủ tương đương, khoảng cách tối thiểu, vật cản, model/calibration hash; live viewer khớp telemetry; ca âm giữ pose cũ và có lý do từ chối. | Có đoạn chưa kiểm; lệnh bị từ chối mà pose live đổi; telemetry mất hoặc khác backend; offline preview không được đánh dấu. |
| **G3 — lỗi, payload và recovery** | Thử timeout, mất kết nối, gripper không kẹp/không nhả, quân rơi, placement stale; có xác nhận độc lập trước game commit và quy trình dừng/khôi phục. | Kết quả vật lý chưa biết mà game commit hoặc hệ thống tự chạy tiếp; recovery không xác định trạng thái quân. |
| **G4 — commissioning phân tầng** | Chỉ sau ủy quyền phần cứng riêng: telemetry read-only; chuyển động chậm trên bàn trống; một quỹ đạo; một quân; rồi mới camera/game. Ghi joint/TCP thực, clearance, ảnh/video, E-stop và can thiệp của người vận hành. | Bất kỳ sai khác vượt giới hạn rút từ G0/G1 và thông số FR3; dấu hiệu chạm bàn/quân ngoài dự kiến; E-stop hoặc recovery không đạt. |

## 6. Tám bước ưu tiên

1. Đóng băng MVP ở một nước đi không bắt quân trong vùng bàn nhỏ, có người giám sát.
2. Đo geometry/TCP và tạo một artifact calibration có phiên bản; phân biệt **đã đo** với **giả định mô phỏng**.
3. Bổ sung gate readiness vật lý cho profile chiều cao, tool geometry và payload verification; không để `PROVISIONAL_SIMULATION` được hiểu là ủy quyền gắp.
4. Tạo smoke test xuyên tầng cho pose hợp lệ, pose xuyên bàn, từ chối giữa quỹ đạo, mất telemetry, offline preview; lưu log và ảnh cùng model/calibration version.
5. Chứng minh parity và full-path collision trong vùng MVP; xử lý `get_state_snapshot` trùng và rà soát commit simulator trước khi xét merge.
6. Thử giới hạn FAIRINO MoveIt 2 bằng cùng model và quỹ đạo; quyết định về planner bằng kết quả đo được, không chuyển cả stack theo kỳ vọng.
7. Sau G0–G3 và ủy quyền riêng, commissioning theo G4: bàn trống → một quân → nhiều vị trí đại diện.
8. Chỉ khi gắp–đặt được xác nhận độc lập mới nối camera/game, mở rộng vùng bàn, rồi triển khai bắt quân.

## Giới hạn của kết luận

- **Đã xác minh:** đường mã tại hai commit, các test được liệt kê và hành vi simulator/trình duyệt trong phiên đánh giá. Mức tin cậy cao cho các kết luận về code và simulator.
- **Chưa xác minh:** sai số camera và transform thực, hình học tool thực so với CAD/proxy, bảo vệ nội tại controller, độ giữ quân của ngàm, min clearance và recovery trên FR3. Mức tin cậy về khả năng chạy vật lý hiện thấp.
- **Không thay thế runbook:** [PHASE4_PHYSICAL_VALIDATION_RUNBOOK.md](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/blob/fab750a918c1457ae14bfda900572fb16f846e26/docs/PHASE4_PHYSICAL_VALIDATION_RUNBOOK.md) mô tả quy trình commissioning chi tiết. Báo cáo này đề xuất **thu hẹp thứ tự thực thi MVP** và chỉ ra nơi code readiness hiện chưa tương ứng với lời hứa nghiệm thu của runbook.
