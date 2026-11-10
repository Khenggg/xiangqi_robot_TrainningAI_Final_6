"""Donor API adapter; all hardware IO uses the current driver and fixed profile."""
import math
import numpy as np
from src.modes.vsc_v3 import config
from src.hardware.robot_VIP import FR5Robot as CurrentFR5Robot
from src.hardware.robot_VIP import RobotCommandError, GripperCommandError, robot_sdk_core
from src.vision.pick_consensus import PickTargetUnavailable as CurrentPickUnavailable
from src.modes.vsc_v3.vision.pick_consensus import PickTargetUnavailable as DonorPickUnavailable

class FR5Robot(CurrentFR5Robot):
    def _outside_grid_margin_limits_mm(self):
        return config.VISUAL_PICK_OUTSIDE_MARGIN_MM, 10.0

    def move_piece(self, *args, require_visual_target=False, **kwargs):
        for name in ('refresh_moving_visual_target', 'verify_capture_cleared'):
            callback = kwargs.get(name)
            if callback is not None:
                def translated(callback=callback):
                    try:
                        return callback()
                    except DonorPickUnavailable as exc:
                        raise CurrentPickUnavailable(exc.reason, stage=exc.stage) from exc
                kwargs[name] = translated
        result = super().move_piece(*args, require_visual_target=require_visual_target, **kwargs)
        if not getattr(result, 'success', False):
            retry_stage = getattr(result, 'metadata', {}).get('visual_retry_stage')
            if retry_stage:
                raise DonorPickUnavailable(getattr(result, 'message', 'Visual target unavailable'), stage=retry_stage)
            raise RobotCommandError(getattr(result, 'message', 'Physical move failed'),
                                    backend_code=getattr(result, 'backend_code', None))
        return result

    execute_piece_move = move_piece

    def _move_piece_sequence(self, s_col, s_row, d_col, d_row, is_capture,
                   moving_visual_target=None, captured_visual_target=None,
                   refresh_moving_visual_target=None, verify_capture_cleared=None,
                   require_visual_target=False):
        """Quy trình di chuyển hoàn chỉnh, bao gồm xử lý ăn quân.
        
        Args:
            s_col, s_row: ô nguồn
            d_col, d_row: ô đích
            is_capture:   True nếu ăn quân đối phương
            moving_visual_target: GridTarget camera cho quân đang di chuyển, hoặc None
            captured_visual_target: GridTarget camera cho quân bị ăn, hoặc None
            refresh_moving_visual_target: callback chụp lại bàn thật ngay trước
                khi gắp quân di chuyển. Trả về GridTarget hoặc None để hủy an toàn.
        """
        self._require_actuation()
        self.board_to_pose(s_col,s_row,config.PICK_Z)
        self.board_to_pose(d_col,d_row,config.PLACE_Z)
        if is_capture:
            if "R_Trash" not in self.teaching_points:
                raise RobotCommandError("Validated R_Trash teaching point unavailable")
            self._validate_pose(self.teaching_points["R_Trash"]["pose"])
            trash = self.teaching_points['R_Trash']
            if (trash.get('tool'), trash.get('user')) != (self.tool_num, self.user_num):
                raise RobotCommandError('R_Trash tool/user frame differs from R1-R4')
            joints = self.teaching_points["R_Trash"]["joints"]
            if len(joints) != 6 or not all(math.isfinite(float(v)) for v in joints):
                raise ValueError("Capture-bin joint target is invalid")
        if not self.dry:
            code, home = self.read_teaching_point('HOMECHESS')
            if code != 0:
                raise RobotCommandError('HOMECHESS unavailable before motion', code)
            self._verify_waypoint_frame(home, 'HOMECHESS')

        print(f"[ROBOT] ♟️ Di chuyển: ({s_col},{s_row}) → ({d_col},{d_row})"
              + (" [ĂN QUÂN]" if is_capture else ""))
        print(f"[ROBOT] 🔍 DEBUG: s_col={s_col}, s_row={s_row}, d_col={d_col}, d_row={d_row}")

        def require_target(target, label):
            if target is None or not np.isfinite([target.col, target.row]).all():
                raise RuntimeError(f"Missing/nonfinite {label} visual target; pick cancelled")

        if require_visual_target:
            # Validate BEFORE connect/approach/close. A capture source is measured
            # after removal, but its callback must exist before removing anything.
            if is_capture:
                require_target(captured_visual_target, "capture")
                if refresh_moving_visual_target is None or verify_capture_cleared is None:
                    raise RuntimeError("Visual capture requires fresh source and cleared-square verification")
            else:
                if refresh_moving_visual_target is not None:
                    moving_visual_target = refresh_moving_visual_target()
                    refresh_moving_visual_target = None
                require_target(moving_visual_target, "source")

        # Tính khoảng cách di chuyển để quyết định có cần nâng cao hơn không
        distance = abs(d_col - s_col) + abs(d_row - s_row)
        use_extra_safe = distance >= 4  # Nếu di chuyển >= 4 ô, dùng độ cao an toàn

        # 1. Nếu ăn quân: gắp quân địch → thả vào bãi thải
        if is_capture:
            print(f"[ROBOT] 🎯 Gắp quân địch tại đích ({d_col},{d_row})")
            self.pick_at(d_col, d_row, visual_target=captured_visual_target)
            
            # Nâng lên độ cao an toàn (SAFE_Z)
            print(f"[ROBOT] ⬆️ Nâng lên SAFE_Z={config.SAFE_Z}mm")
            self.move_to_extra_safe(d_col, d_row, visual_target=captured_visual_target)
            
            # Bay thẳng đến bãi thải ở độ cao SAFE_Z (giữ nguyên Z)
            self.place_in_capture_bin(current_z=config.SAFE_Z)
            if verify_capture_cleared is not None and not verify_capture_cleared():
                raise RuntimeError("Capture square is not visually clear after removal")

        # A capture changes the physical board.  Do not reuse a target measured
        # before that operation for the next pick; ask vision for a fresh pose.
        if refresh_moving_visual_target is not None:
            moving_visual_target = refresh_moving_visual_target()
            if moving_visual_target is None:
                if require_visual_target:
                    raise RuntimeError("Source refresh failed; no stale/logical pick fallback")
                print("[ROBOT] Visual correction unavailable after refresh; picking logical cell centre.")

        if require_visual_target:
            require_target(moving_visual_target, "source")

        # 2. Gắp quân mình ở nguồn
        print(f"[ROBOT] 🤏 Gắp quân mình tại nguồn ({s_col},{s_row})")
        self.pick_at(s_col, s_row, visual_target=moving_visual_target)
        
        # Nâng lên độ cao an toàn nếu di chuyển xa
        if use_extra_safe:
            print(f"[ROBOT] 🛡️ Di chuyển xa ({distance} ô), sử dụng độ cao an toàn")
            self.move_to_extra_safe(s_col, s_row, visual_target=moving_visual_target)

        # 3. Đặt quân mình vào đích
        print(f"[ROBOT] 📍 Đặt quân mình tại đích ({d_col},{d_row})")
        self.place_at(d_col, d_row)

        # 4. Về vị trí chờ
        self.go_to_home_chess()

        print("[ROBOT] ✅ Hoàn tất di chuyển.")

