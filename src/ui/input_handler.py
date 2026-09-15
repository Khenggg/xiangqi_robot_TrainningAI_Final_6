import time
from src.core import xiangqi  # type: ignore
from src.ui.board_renderer import BoardRenderer, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT, NUM_COLS, NUM_ROWS  # type: ignore

class InputHandler:
    """Manages Pygame Key/Mouse events and bridges them to GameState and HardwareManager."""
    def __init__(self, game_state, hw_manager):
        self.state = game_state
        self.hw = hw_manager

    def handle_mouse_down(self, mx, my):
        # Surrender Button
        if BTN_SURRENDER_RECT.collidepoint(mx, my) and not self.state.game_over:
            print("[GAME] YOU SURRENDER!")
            self.state.handle_game_over("b")
            self.state.api_client.end_match(winner="BLACK", reason="RESIGN")
            return

        # New Game Button
        if BTN_NEW_GAME_RECT.collidepoint(mx, my):
            self.state.reset_game(self.hw)
            return

        # Manual Override (Mouse Drag)
        if (self.state.allow_mouse_move or self.state.manual_override_active) and self.state.turn == "r" and not self.state.game_over:
            c, r = BoardRenderer.pixel_to_grid(mx, my)
            if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                clicked_piece = self.state.board[r][c]
                
                # Select a piece
                if clicked_piece.startswith("r"):
                    self.state.selected_pos = (c, r)
                    
                # Move a selected piece
                elif self.state.selected_pos:
                    src, dst = self.state.selected_pos, (c, r)
                    p_name = self.state.board[src[1]][src[0]]
                    
                    if xiangqi.is_valid_move(src, dst, self.state.board, "r"):
                        print("[UI] 🖱️ Người dùng đi cờ trên màn hình.")
                        self.state.process_human_move(src, dst, p_name)
                        self.state.selected_pos = None
                        self.state.manual_override_active = False
                        
                        # Retake T1 baseline after manual override
                        if self.hw.cam_monitor:
                            print("[UI] 📸 Đang chụp lại T1 baseline sau khi Override...")
                            self.state.set_status("📸 Cập nhật Mắt Camera...", color=(0, 100, 180), duration=2.0)
                            self.hw.capture_baseline_if_needed(force_delay=1.0)
                    else:
                        print(f"Invalid move: {src}->{dst}")
                        self.state.set_status("❌  Invalid move!", color=(180, 0, 0))
                        self.state.set_invalid_flash(dst[0], dst[1])
                        self.state.selected_pos = None

    def handle_keyboard(self, key):
        import pygame  # type: ignore

        # G KEY: Test Gripper Tool DO0 (Bật 3s rồi Tắt)
        if key == pygame.K_g:
            self._handle_gripper_test(do_id=0)
            return

        # H KEY: Test Gripper Tool DO1 (Bật 3s rồi Tắt)
        elif key == pygame.K_h:
            self._handle_gripper_test(do_id=1)
            return

        # I KEY: Lấy dữ liệu & Kiểm tra kết nối từ Robot FR3
        elif key == pygame.K_i:
            self._handle_robot_info()
            return

        if self.state.allow_mouse_move or self.state.game_over or self.state.turn != "r":
            return

        # Z KEY: Rollback
        if key == pygame.K_z:
            self.state.handle_rollback(self.hw)
            
        # SPACE KEY: Trigger YOLO Detection
        elif key == pygame.K_SPACE:
            self._handle_space_key()

    def _handle_gripper_test(self, do_id=0):
        if not self.hw.robot or not self.hw.robot.connected:
            print("[GRIPPER TEST] ❌ Robot chưa kết nối!")
            self.state.set_status("❌ Robot chưa kết nối!", color=(180, 0, 0), duration=3.0)
            return

        import threading
        def _worker():
            print(f"\n[GRIPPER TEST] 🔧 Đang test kích hoạt Tool DO{do_id}...")
            self.state.set_status(f"🔧 Test Tool DO{do_id}: ON (3s)...", color=(0, 150, 0), duration=3.0)
            try:
                print(f"[GRIPPER TEST] 🔴 SetToolDO({do_id}, status=1) - BẬT KẸP")
                err1 = self.hw.robot.robot.SetToolDO(do_id, 1, block=1)
                print(f"[GRIPPER TEST]    Kết quả lệnh: err={err1} (0 là robot đã nhận)")
                time.sleep(3.0)
                print(f"[GRIPPER TEST] 🟢 SetToolDO({do_id}, status=0) - TẮT KẸP")
                err0 = self.hw.robot.robot.SetToolDO(do_id, 0, block=1)
                print(f"[GRIPPER TEST]    Kết quả lệnh: err={err0}")
                self.state.set_status(f"✅ Test Tool DO{do_id} xong!", color=(0, 100, 180), duration=3.0)
            except Exception as e:
                print(f"[GRIPPER TEST] ❌ Lỗi test Tool DO{do_id}: {e}")
                self.state.set_status(f"❌ Lỗi DO{do_id}: {e}", color=(180, 0, 0), duration=3.0)

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_robot_info(self):
        if not self.hw.robot or not self.hw.robot.connected:
            print("[ROBOT INFO] ❌ Robot chưa kết nối!")
            self.state.set_status("❌ Robot chưa kết nối!", color=(180, 0, 0), duration=3.0)
            return

        try:
            r = self.hw.robot.robot
            print("\n" + "="*50)
            print("🤖 [THÔNG TIN TRẠNG THÁI TỪ ROBOT FAIRINO FR3]")
            print(f"  - IP Robot: {self.hw.robot.ip}")
            print(f"  - Trạng thái SDK: {'✅ ĐANG KẾT NỐI TỐT' if self.hw.robot.connected else '❌ MẤT KẾT NỐI'}")
            err, ip = r.GetControllerIP()
            if err == 0:
                print(f"  - Controller IP phản hồi: {ip}")
            err, tp = r.GetRobotTeachingPoint("HOMECHESS")
            if err == 0:
                print(f"  - Tọa độ HOMECHESS đọc từ Controller: X={float(tp[0]):.1f}, Y={float(tp[1]):.1f}, Z={float(tp[2]):.1f}")
            print(f"  - Cổng kẹp đang cấu hình trong code: Tool DO{self.hw.robot.gripper_do_id}")
            print("="*50 + "\n")
            self.state.set_status("✅ Đã lấy thông số từ Robot (Xem Terminal)", color=(0, 100, 180), duration=4.0)
        except Exception as e:
            print(f"[ROBOT INFO] ❌ Lỗi đọc dữ liệu: {e}")
            self.state.set_status(f"❌ Lỗi đọc Robot: {e}", color=(180, 0, 0), duration=3.0)

    def _handle_space_key(self):
        print("\n[SPACE] 🎯 Người chơi bấm SPACE — đang chụp T2 snapshot...")
        self.state.set_status("📸  Đang phân tích YOLO...", color=(0, 100, 180), duration=3.0)
        
        if not self.hw.yolo_detector or not self.hw.cam_monitor:
            self.state.set_status("❌  Hệ thống nhận diện chưa khởi tạo!", color=(180, 0, 0))
            return
            
        frame, detections = self.hw.cam_monitor.get_fresh_snapshot()
        
        # Validate Baseline
        if not self.hw.yolo_detector.has_baseline():
            print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
            if self.hw.yolo_detector.capture_baseline(frame, detections):
                self.state.set_status("📸 Đã làm mới Trạng thái bàn cờ hiện tại", color=(0, 100, 180), duration=5.0)
            else:
                self.state.set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
            return

        # SAVE ROLLBACK STATE TRƯỚC KHI DETECT (để có thể rollback khi lỗi)
        occ = [row[:] for row in self.hw.yolo_detector._baseline_occ]
        b_time = self.hw.yolo_detector._baseline_time
        self.state.save_rollback_state(occ, b_time)

        # Perform Detection
        print("[SPACE] 🔍 Chạy YOLO Detector...")
        src, dst, piece = self.hw.yolo_detector.detect_move(frame, detections, self.state.board)
        
        if src:
            # Note: Vietnamese name resolution skipped here for brevity, handled by detector UI largely
            print(f"[YOLO] 👉 Nhận diện đi từ Cột {src[0]} Hàng {src[1]} đến Cột {dst[0]} Hàng {dst[1]}")
            
        # Verify result
        if src is None:
            print("[SPACE] ❌ YOLO KHÔNG thấy nước đi hợp lệ!")
            self.state.set_status("❌  Không thấy nước đi! Di quân trên màn hình.", color=(180, 0, 0), duration=5.0)
            self.state.manual_override_active = True
            self.hw.clear_yolo_baseline()
            return
            
        if not xiangqi.is_valid_move(src, dst, self.state.board, "r"):
            print(f"[SPACE] ❌ YOLO báo nước đi không hợp lệ: {src}->{dst}")
            self.state.set_status("⚠️  Lỗi nhận diện / Đi sai luật! Dùng chuột kéo thả.", color=(180, 100, 0), duration=60.0)
            self.state.set_invalid_flash(dst[0], dst[1])
            self.state.manual_override_active = True
            self.hw.clear_yolo_baseline()
            return

        # Commit move (state đã được save ở trên rồi)
        self.state.process_human_move(src, dst, piece)
