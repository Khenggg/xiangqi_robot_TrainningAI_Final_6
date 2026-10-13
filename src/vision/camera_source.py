"""Shared camera opening policy for RUN and optical calibration."""
import os
import cv2


def open_camera(index, backend="auto"):
    choices = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}
    names = (["dshow", "msmf", "any"] if os.name == "nt" else ["any"]) if backend == "auto" else [backend]
    for name in names:
        cap = cv2.VideoCapture(index, choices[name])
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                print(f"Camera index={index}, backend={name}, initial preview={frame.shape[1]}x{frame.shape[0]}")
                return cap
        cap.release()
    raise RuntimeError(f"Cannot read camera index {index}. Close Windows Camera, RUN, OBS/Teams; "
                       "check camera index and Windows camera permissions. No other index was selected automatically.")
