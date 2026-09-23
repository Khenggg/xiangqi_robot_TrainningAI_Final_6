import time
from src.core import xiangqi  # type: ignore
from src.ui.board_renderer import BoardRenderer, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT, NUM_COLS, NUM_ROWS  # type: ignore
from src.vision.move_observation import MoveObservation, derive_move_observation

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
        if self.hw.gripper_driver is not None:
            import threading
            def _driver_worker():
                action_name = "CLOSE" if do_id == 0 else "OPEN"
                print(f"\n[GRIPPER TEST] 🔧 Đang test kích hoạt GripperDriver: {action_name}...")
                self.state.set_status(f"🔧 Test Gripper: {action_name}...", color=(0, 150, 0), duration=2.0)
                try:
                    if do_id == 0:
                        ok = self.hw.gripper_driver.close()
                    else:
                        ok = self.hw.gripper_driver.open()
                    msg = "✅ Thành công!" if ok else "⚠️ Thất bại!"
                    self.state.set_status(f"Gripper {action_name}: {msg}", color=(0, 100, 180), duration=2.0)
                except Exception as e:
                    print(f"[GRIPPER TEST] ❌ Lỗi test Gripper: {e}")
                    self.state.set_status(f"❌ Lỗi: {e}", color=(180, 0, 0), duration=3.0)

            threading.Thread(target=_driver_worker, daemon=True).start()
            return

        if not self.hw.gripper_driver:
            print("[GRIPPER TEST] ❌ GripperDriver chưa được cấu hình!")
            self.state.set_status("❌ GripperDriver chưa cấu hình!", color=(180, 0, 0), duration=3.0)
            return

    def _handle_robot_info(self):
        if self.hw.backend is not None:
            snap = self.hw.backend.get_state_snapshot()
            print("\n" + "="*50)
            print("🤖 [THÔNG TIN TRẠNG THÁI ROBOT FR3 - UNIFIED BACKEND]")
            print(f"  - Robot Model: {snap.robot_model}")
            print(f"  - Kết nối: {'✅ ĐANG KẾT NỐI' if snap.connected else '❌ MẤT KẾT NỐI'}")
            print(f"  - Trạng thái Motion: {snap.motion_state}")
            print(f"  - Khớp Joints (deg): {[round(q, 2) for q in snap.joints_deg]}")
            print(f"  - TCP Pose (mm, deg): {[round(p, 2) for p in snap.tcp_pose_mm_deg]}")
            print(f"  - Flange Pose (mm, deg): {[round(p, 2) for p in snap.flange_pose_mm_deg]}")
            flange_src = getattr(snap, "flange_pose_source", "UNAVAILABLE")
            print(f"    Source: {flange_src}")
            print(f"  - Kẹp Closed: {snap.gripper_closed}")
            print(f"  - Motion Authorized: {getattr(self.hw, 'physical_motion_authorized', False)}")
            print(f"  - Robot Ready: {self.hw.is_robot_ready}")
            if self.hw.board_pose_provider is not None:
                cal = getattr(self.hw.board_pose_provider, "is_calibrated", False)
                print(f"  - Board Calibrated: {'✅ YES' if cal else '❌ NO'}")
            print("="*50 + "\n")
            self.state.set_status("✅ Đã lấy thông số từ Backend (Xem Terminal)", color=(0, 100, 180), duration=4.0)
            return

        if not self.hw.robot or not self.hw.robot.connected:
            print("[ROBOT INFO] ❌ Robot chưa kết nối!")
            self.state.set_status("❌ Robot chưa kết nối!", color=(180, 0, 0), duration=3.0)
            return

        try:
            r = self.hw.robot.robot
            print("\n" + "="*50)
            print("🤖 [THÔNG TIN TRẠNG THÁI TỪ ROBOT FAIRINO FR3 (LEGACY)]")
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

    def _handle_space_key(self, auto_retry=False) -> bool:
        print("\n[SPACE] 🎯 Người chơi bấm SPACE — đang chụp T2 snapshot...")
        self.state.set_status("📸 Đang phân tích bàn cờ...", color=(0, 100, 180), duration=3.0)

        if self.state.turn != "r" or self.state.game_over:
            print("[SPACE] ⚠️ Chưa đến lượt Đỏ hoặc ván đấu đã kết thúc.")
            return False

        if not self.hw.cam_monitor:
            self.state.set_status("❌ Hệ thống Camera chưa khởi tạo!", color=(180, 0, 0))
            return False

        frame, detections = self.hw.cam_monitor.get_fresh_snapshot()
        if frame is None:
            print("[SPACE] ❌ Không lấy được camera frame!")
            if not auto_retry:
                self.state.set_status("❌ Không lấy được hình ảnh từ Camera!", color=(180, 0, 0))
            return False

        # Validate / Capture YOLO baseline if detector is active
        if self.hw.yolo_detector and not self.hw.yolo_detector.has_baseline():
            print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
            if self.hw.yolo_detector.capture_baseline(frame, detections):
                self.state.set_status("📸 Đã làm mới Trạng thái bàn cờ hiện tại", color=(0, 100, 180), duration=5.0)
            else:
                self.state.set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
            return False

        # SAVE ROLLBACK STATE TRƯỚC KHI DETECT (để có thể rollback khi lỗi)
        if self.hw.yolo_detector and self.hw.yolo_detector.has_baseline():
            occ = [row[:] for row in self.hw.yolo_detector._baseline_occ]
            b_time = self.hw.yolo_detector._baseline_time
            self.state.save_rollback_state(occ, b_time)

        obs = None
        cchess_result = None

        # ---------------------------------------------------------------------
        # 1. PRIMARY: CChess full-board recognition + quality gate + MoveObservation
        # ---------------------------------------------------------------------
        if hasattr(self.hw, "recognize_board_state") and self.hw.cchess_recognizer is not None:
            try:
                print("[SPACE] 🔍 Chạy CChess Full-Board Recognizer (Primary)...")
                cchess_result = self.hw.recognize_board_state(frame)
                if cchess_result and cchess_result.get("success") and cchess_result.get("quality_ok", True):
                    rec_board = cchess_result.get("board")
                    confs = cchess_result.get("confidence")
                    obs = derive_move_observation(
                        before_board=self.state.board,
                        after_board=rec_board,
                        player_color="r",
                        confidence_grid=confs,
                    )
                    print(f"[SPACE] 🎯 CChess observation: success={obs.success}, move={obs.src}→{obs.dst}, error={obs.error}")
                else:
                    q_err = cchess_result.get("error") if cchess_result else "CChess result empty"
                    print(f"[SPACE] ⚠️ CChess quality gate không đạt: {q_err}")
            except Exception as e:
                print(f"[SPACE] ⚠️ CChess recognizer error: {e}")

        # ---------------------------------------------------------------------
        # 2. SENSOR FUSION & FALLBACK: YOLO Occupancy detector
        # ---------------------------------------------------------------------
        if self.hw.yolo_detector and self.hw.yolo_detector.has_baseline():
            yolo_obs = self.hw.yolo_detector.detect_move_observation(
                frame, detections, self.state.board, cchess_result=cchess_result
            )
            if obs is not None and obs.success:
                # Primary CChess succeeded; use YOLO as secondary verification if YOLO also detected a move
                if yolo_obs.success:
                    if (yolo_obs.src, yolo_obs.dst) != (obs.src, obs.dst):
                        print(f"[SPACE] ⚠️ Xung đột cảm biến: CChess={obs.src}→{obs.dst} vs YOLO={yolo_obs.src}→{yolo_obs.dst}. Fail closed.")
                        obs = MoveObservation(
                            success=False,
                            is_ambiguous=True,
                            error=f"Xung đột cảm biến: CChess ({obs.src}→{obs.dst}) != YOLO ({yolo_obs.src}→{yolo_obs.dst})",
                        )
                    else:
                        print(f"[SPACE] ✅ Cảm biến đồng thuận: CChess và YOLO đều xác nhận {obs.src}→{obs.dst}")
            elif obs is None or (not obs.success and not obs.is_ambiguous):
                # CChess was unavailable or could not detect a change, fallback to YOLO
                print("[SPACE] 🔄 Thử YOLO Snapshot Detector (Fallback)...")
                obs = yolo_obs

        if obs is None:
            obs = MoveObservation(success=False, error="Không có hệ thống nhận diện khả dụng")

        # ---------------------------------------------------------------------
        # 3. VERIFY & COMMIT STRUCTURED OBSERVATION
        # ---------------------------------------------------------------------
        if not obs.success:
            if obs.is_ambiguous:
                print(f"[SPACE] ⚠️ Nước đi mơ hồ / không thể xác định duy nhất: {obs.error}")
                if not auto_retry:
                    self.state.set_status(f"⚠️ Nước đi mơ hồ: {obs.error}", color=(180, 100, 0), duration=10.0)
                    self.state.manual_override_active = True
                    self.hw.clear_yolo_baseline()
            else:
                print(f"[SPACE] ❌ Nhận diện thất bại: {obs.error}")
                if not auto_retry:
                    self.state.set_status(f"❌ {obs.error or 'Không thấy nước đi hợp lệ!'}", color=(180, 0, 0), duration=5.0)
                    if obs.dst:
                        self.state.set_invalid_flash(obs.dst[0], obs.dst[1])
                    self.state.manual_override_active = True
                    self.hw.clear_yolo_baseline()
            return False

        # Additional Xiangqi rule verification on logical board
        if not xiangqi.is_valid_move(obs.src, obs.dst, self.state.board, "r"):
            print(f"[SPACE] ❌ Nước đi vi phạm luật cờ: {obs.piece} {obs.src}->{obs.dst}")
            if not auto_retry:
                self.state.set_status("⚠️ Lỗi nhận diện / Đi sai luật! Dùng chuột kéo thả.", color=(180, 100, 0), duration=60.0)
                self.state.set_invalid_flash(obs.dst[0], obs.dst[1])
                self.state.manual_override_active = True
                self.hw.clear_yolo_baseline()
            return False

        # Commit move
        move_type_str = "Ăn quân" if obs.is_capture else "Di chuyển"
        cap_str = f" (ăn {obs.captured_piece})" if obs.is_capture and obs.captured_piece else ""
        print(f"[SPACE] ✅ Xác nhận nước đi ({move_type_str}{cap_str}): {obs.piece} {obs.src}→{obs.dst} (conf={obs.confidence:.2f})")
        self.state.process_human_move(obs.src, obs.dst, obs.piece)

        # Cập nhật baseline YOLO với frame mới sau khi đi nước hợp lệ
        if self.hw.yolo_detector:
            self.hw.yolo_detector.capture_baseline(frame, detections)
        return True

    def try_auto_confirm_move(self, retries=10, retry_seconds=0.2) -> bool:
        """Reuse the existing rule-validated snapshot flow after hand exit."""
        import time
        if self.state.turn != "r" or self.state.game_over:
            return False
        if not self.hw.yolo_detector or not self.hw.yolo_detector.has_baseline():
            self.hw.reset_hand_interaction_monitor()
            self.state.set_status("⚠️ Chưa có baseline. Hãy nhấn SPACE để xác minh.", color=(180, 100, 0), duration=12.0)
            return False
        self.state.set_status("✋ Hand left board — verifying move...", color=(0, 100, 180), duration=3.0)
        for attempt in range(1, int(retries) + 1):
            if self._handle_space_key(auto_retry=True):
                self.hw.reset_hand_interaction_monitor()
                return True
            if attempt < retries:
                time.sleep(float(retry_seconds))
        self.state.manual_override_active = False
        self.hw.reset_hand_interaction_monitor()
        self.state.set_status("⚠️ Không xác minh được nước đi. Hãy nhấn SPACE.", color=(180, 100, 0), duration=12.0)
        print("[AUTO CONFIRM] Failed after retry limit; waiting for SPACE fallback.")
        return False
