"""Open a usable Windows camera, trying alternative capture backends."""
import cv2


def open_camera(index, fallback_indices=()):
    """Return a capture with a readable frame, or raise with diagnostics.

    Try every backend for the requested index before other devices. Failed
    captures are released before trying the next candidate.
    """
    indices = list(dict.fromkeys([index, *fallback_indices]))
    for device in indices:
        for label, backend in (("DSHOW", cv2.CAP_DSHOW),
                               ("MSMF", cv2.CAP_MSMF),
                               ("AUTO", cv2.CAP_ANY)):
            print(f"[CAMERA] Trying index={device}, backend={label}...", flush=True)
            cap = cv2.VideoCapture(device, backend)
            selected = False
            try:
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    for _ in range(5):
                        ok, frame = cap.read()
                        if ok and frame is not None and frame.size:
                            selected = True
                            print(f"[CAMERA] Ready: index={device}, backend={label}, "
                                  f"frame={frame.shape[1]}x{frame.shape[0]}")
                            return cap
            except cv2.error as exc:
                print(f"[CAMERA] index={device}, backend={label}: {exc}")
            finally:
                if not selected:
                    cap.release()
    raise RuntimeError(
        f"Cannot read camera indices {indices} via DSHOW/MSMF/AUTO. "
        "Close Windows Camera, other test scripts, and video apps; "
        "check desktop-app camera permissions and VIDEO_INDEX/--camera."
    )
