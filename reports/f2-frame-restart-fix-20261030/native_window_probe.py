"""Exercise actual Windows HighGUI ownership with generated pixels, no devices."""
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.vision.camera_monitor import CameraMonitor


def main():
    errors = []
    cap = SimpleNamespace(release=Mock())
    monitor = CameraMonitor(cap, window_name='Xiangqi F2 window test (no camera)', device_preference='cpu')
    monitor._last_frame = np.zeros((180, 360, 3), dtype=np.uint8)
    cv2.putText(monitor._last_frame, 'F2 teardown check - fake camera', (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, .5, (80, 220, 80), 1)
    monitor._draw_overlay = lambda frame, _: frame
    def stop():
        try:
            monitor.stop()
        except Exception as exc:
            errors.append(str(exc))
    try:
        monitor.update_display()
        owner = monitor._display_thread_id
        assert owner == threading.get_ident()
        worker = threading.Thread(target=stop)
        worker.start()
        deadline = time.monotonic() + 3
        while worker.is_alive() and time.monotonic() < deadline:
            cv2.waitKey(1)
        worker.join(.1)
        assert not worker.is_alive() and not errors
        assert monitor._display_close_requested.is_set()
        assert monitor.close_display()
        cv2.waitKey(1)
        assert not monitor._display_open
        cap.release.assert_called_once()
        result = dict(native_highgui=True, stopped_on_worker=True, window_closed_on_gui=True,
                      real_camera_or_robot_calls=0, errors=errors)
        Path(__file__).with_name('native-window-evidence.json').write_text(
            json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        monitor.close_display()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
