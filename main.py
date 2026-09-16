"""QR camera preview by default; --play enables game, --robot opts into FR5."""
import argparse
import json
import math
from pathlib import Path
import queue
import threading
import time

import config


def load_motion_profile(path):
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ("ROBOT_IP MOVE_SPEED ROTATION PICK_Z PLACE_Z SAFE_Z IDLE_X IDLE_Y "
                "IDLE_Z CAPTURE_BIN_X CAPTURE_BIN_Y GRIPPER_OPEN GRIPPER_CLOSE").split()
    if set(values) != set(required):
        raise ValueError("robot_motion.json must contain exactly the fields in the example")
    if not isinstance(values["ROBOT_IP"], str) or not values["ROBOT_IP"].strip():
        raise ValueError("Set the actual ROBOT_IP")
    for name in required:
        if name == "ROBOT_IP":
            continue
        numbers = values[name] if name == "ROTATION" else [values[name]]
        if (name == "ROTATION" and (not isinstance(numbers, list) or len(numbers) != 3)
                or any(not isinstance(x, (float, int)) or isinstance(x, bool) or not math.isfinite(x) for x in numbers)):
            raise ValueError(f"Measured numeric values required: {name}")
    if not 0 < values["MOVE_SPEED"] <= 100 or values["SAFE_Z"] <= max(values["PICK_Z"], values["PLACE_Z"]):
        raise ValueError("Invalid speed / SAFE_Z must be above pick and place Z")
    if {values["GRIPPER_OPEN"], values["GRIPPER_CLOSE"]} != {0, 1}:
        raise ValueError("Gripper open/close must be distinct 0/1 values")
    for key, value in values.items():
        setattr(config, key, value)


def preview():
    import cv2
    from src.vision.camera_source import open_camera
    from src.vision.qr_calibration import BoardGeometry, QRCalibrator
    from src.vision.xiangqi_recognizer import XiangqiRecognizer
    from src.vision.qr_board_monitor import QRBoardMonitor
    geometry = BoardGeometry.load(config.QR_LAYOUT_PATH)
    model = XiangqiRecognizer(config.CCHESS_MODEL_PATH, config.CCHESS_MIN_CONFIDENCE)
    monitor = QRBoardMonitor(open_camera(config.VIDEO_SOURCE), QRCalibrator(geometry), model)
    monitor.start()
    print("QR preview: SPACE prints stable FEN; S saves reference image; Q/ESC exits.")
    try:
        while True:
            key = monitor.update_display() & 0xff
            if key in (27, ord("q")):
                return
            if key == 32:
                try:
                    print(monitor.require_board().fen("r"))
                except (RuntimeError, ValueError) as exc:
                    print(exc)
            if key == ord("s"):
                try:
                    frame, _ = monitor.reference_snapshot()
                    target = config.ROOT / "config" / f"reference_{time.time_ns()}.png"
                    if not cv2.imwrite(str(target), frame):
                        raise RuntimeError("Could not save reference frame")
                    print(f"Reference image saved: {target}")
                except RuntimeError as exc:
                    print(exc)
            time.sleep(.01)
    finally:
        monitor.stop()


def play():
    import pygame
    from src.core import xiangqi
    from src.core.game_state import GameState
    from src.hardware.hardware_manager import HardwareManager
    from src.ui.board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT
    from src.ui.input_handler import InputHandler

    hw = HardwareManager(config, config.ROOT)
    worker = None
    try:
        hw.initialize_all()
        if not config.DRY_RUN and not hw.robot.connected:
            raise RuntimeError("Physical robot did not connect; restart in preview to diagnose")
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Xiangqi QR: SPACE move, Q quit")
        renderer = BoardRenderer(screen)
        state = GameState()
        handler = InputHandler(state, hw)
        results = queue.Queue()
        initialized = False
        pending = None
        running = True
        clock = pygame.time.Clock()

        def ai_job(board):
            try:
                move = hw.ai_ctrl.pick_move(board, "b")
                if move is None or not xiangqi.is_valid_move(*move, board, "b"):
                    raise RuntimeError("Engine did not return a legal move")
                expected, captured = xiangqi.make_temp_move(board, move)
                results.put(("planned", (move, expected, captured)))
            except Exception as exc:
                results.put(("error", str(exc)))

        def motion_job(move, board):
            try:
                # Recheck full-board identity after AI thinking, before dispatch.
                if hw.board_monitor.require_board().board != board:
                    raise RuntimeError("Board changed while AI was thinking")
                src, dst = move
                is_capture = board[dst[1]][dst[0]] != "."
                targets = hw.get_qr_visual_targets(
                    {"moving": src, **({"captured": dst} if is_capture else {})},
                    required=True,
                )
                hw.board_monitor.set_visual_targets(targets)
                hw.robot.move_piece(*src, *dst, is_capture,
                                    moving_visual_target=targets["moving"],
                                    captured_visual_target=targets.get("captured"))
                results.put(("moved", time.monotonic()))
            except Exception as exc:
                results.put(("error", str(exc)))

        while running:
            cam_key = hw.board_monitor.update_display() & 0xff
            events = list(pygame.event.get())
            if cam_key == 32:
                events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
            if cam_key in (27, ord("q")):
                events.append(pygame.event.Event(pygame.QUIT))
            for event in events:
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE)):
                    if state.robot_busy or state.ai_thinking:
                        state.set_status("Wait for robot completion; use physical E-stop for emergency", duration=4)
                    else:
                        running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    if initialized and not state.robot_fault and pending is None:
                        handler.handle_keyboard(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and not state.ai_thinking and not state.robot_fault and pending is None:
                    handler.handle_mouse_down(*event.pos)
                    if state.board == xiangqi.get_board() and state.turn == "r":
                        initialized = False
            if not initialized:
                # Start only when the real board agrees with the known initial state.
                try:
                    if hw.board_monitor.require_board().board == state.board:
                        initialized = True
                        state.set_status("Ready: red moves, then SPACE", color=(0, 120, 0), duration=5)
                    else:
                        state.set_status("Arrange initial board; QR grid must align", duration=1)
                except RuntimeError as exc:
                    state.set_status(str(exc), duration=1)
            if initialized and state.turn == "b" and not state.game_over and not state.robot_fault and not state.ai_thinking and pending is None:
                state.ai_thinking = True
                state.ai_think_start = time.time()
                worker = threading.Thread(target=ai_job, args=([r[:] for r in state.board],), daemon=True)
                worker.start()
            try:
                kind, data = results.get_nowait()
                if kind == "error":
                    state.robot_fault = True
                    state.robot_busy = state.ai_thinking = False
                    state.set_status(data + " — restart after reconciling board", duration=3600)
                elif kind == "planned":
                    state.ai_thinking = False
                    move, expected, captured = data
                    pending = {"move": move, "board": expected, "captured": captured, "after": float("inf")}
                    if config.DRY_RUN:
                        pending["after"] = time.monotonic()
                        state.set_status(f"Move black manually: {move}; camera will verify", duration=3600)
                        print(f"Move BLACK on physical board: {move}")
                    else:
                        state.robot_busy = True
                        worker = threading.Thread(target=motion_job, args=(move, [r[:] for r in state.board]), daemon=True)
                        worker.start()
                elif kind == "moved":
                    state.robot_busy = False
                    pending["after"] = data
                    state.set_status("Checking board after robot move...", duration=3600)
            except queue.Empty:
                pass
            if pending and not state.robot_fault and not state.robot_busy:
                try:
                    obs = hw.board_monitor.require_board()
                    if obs.timestamp > pending["after"] and obs.board == pending["board"]:
                        try:
                            placed = hw.verify_qr_visual_positions({"placed": pending["move"][1]})
                            hw.board_monitor.set_visual_targets(placed)
                        except RuntimeError as exc:
                            state.set_status("Visual correction: " + str(exc), color=(180, 100, 0), duration=5)
                            if not config.DRY_RUN:
                                state.robot_fault = True
                                state.set_status("Placed piece could not be visually verified — inspect board", duration=3600)
                            continue
                        state.board = pending["board"]
                        state.last_move = pending["move"]
                        if pending["captured"] != ".":
                            state.r_captured.append(pending["captured"])
                        state.move_history.append({"turn": "b", "src": state.last_move[0], "dst": state.last_move[1]})
                        state.turn = "r"
                        state.move_number += 1
                        state.update_fen_from_board()
                        state.sync_fen_async(state.current_fen)
                        if xiangqi.get_king_pos("r", state.board) is None:
                            state.handle_game_over("b")
                        pending = None
                        state.set_status("Verified. Red to move", color=(0, 120, 0), duration=5)
                except RuntimeError:
                    pass
            renderer.draw_ui(state.get_render_state())
            renderer.draw_pieces(state.board)
            renderer.draw_highlight(last_move=state.last_move)
            if state.game_over:
                renderer.draw_game_over(state.winner)
            pygame.display.flip()
            clock.tick(30)
    finally:
        # The window does not close during active robot motion. Faults remain
        # latched; automatic retries could duplicate a partially executed move.
        hw.cleanup()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=config.VIDEO_SOURCE)
    parser.add_argument("--layout", type=Path, default=config.QR_LAYOUT_PATH)
    parser.add_argument("--model", type=Path, default=config.CCHESS_MODEL_PATH)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--robot", action="store_true", help="Physical FR5 play; requires measured profiles")
    args = parser.parse_args()
    config.VIDEO_SOURCE, config.QR_LAYOUT_PATH, config.CCHESS_MODEL_PATH = args.camera, args.layout, args.model
    try:
        if args.robot:
            load_motion_profile(config.ROOT / "config" / "robot_motion.json")
            config.DRY_RUN = False
        (play if args.play or args.robot else preview)()
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        parser.exit(1, f"Setup/runtime error: {exc}\nSee docs/QR_INTEGRATION.md\n")


if __name__ == "__main__":
    main()
