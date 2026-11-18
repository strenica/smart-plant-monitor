"""Shared camera settings and capture.

Both the preview server and the leaf scanner read `config/camera.json`, so what
you frame in the browser is exactly what the scanner analyses. Changing the
rotation or zoom in one place changes it for both.

The sensor mode matters more than it looks. The Camera Module 3 offers three:

    (1536, 864)   crop (784, 456, 3072, 1728)   centre crop, looks zoomed in
    (2304, 1296)  crop (16, 24, 4608, 2592)     whole sensor, 2x2 binned
    (4608, 2592)  crop (16, 24, 4608, 2592)     whole sensor, full resolution

picamera2 picks the first by default because it is the fastest, which is why
the preview looked zoomed in. We ask for the second explicitly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# pi/common/camera.py -> pi/common -> pi -> project root
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "camera.json"


@dataclass
class CameraSettings:
    size: tuple[int, int] = (1024, 768)
    sensor_mode: tuple[int, int] = (2304, 1296)
    rotation: int = 0
    zoom: float = 1.0
    preview: bool = True
    preview_port: int = 8080
    preview_fps: int = 15

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CameraSettings":
        """Read the config file, falling back to defaults if it is missing."""
        config_path = Path(path) if path else DEFAULT_PATH
        if not config_path.exists():
            return cls()

        data = json.loads(config_path.read_text())
        return cls(
            size=tuple(data.get("size", (1024, 768))),
            sensor_mode=tuple(data.get("sensor_mode", (2304, 1296))),
            rotation=int(data.get("rotation", 0)),
            zoom=float(data.get("zoom", 1.0)),
            preview=bool(data.get("preview", True)),
            preview_port=int(data.get("preview_port", 8080)),
            preview_fps=int(data.get("preview_fps", 15)),
        )


def apply_transform(frame: np.ndarray, rotation: int = 0, zoom: float = 1.0) -> np.ndarray:
    """Rotate and digitally zoom a frame, keeping the output size unchanged.

    Zoom crops the centre and scales back up, so `zoom=2.0` shows the middle
    half of the frame at the same output resolution. `zoom=1.0` is a no-op.
    """
    if zoom and zoom > 1.0:
        height, width = frame.shape[:2]
        crop_w, crop_h = int(width / zoom), int(height / zoom)
        x0 = (width - crop_w) // 2
        y0 = (height - crop_h) // 2
        frame = frame[y0 : y0 + crop_h, x0 : x0 + crop_w]
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)

    rotation %= 360
    if rotation == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return frame


def open_camera(settings: CameraSettings):
    """Create and start a Picamera2 configured from `settings`."""
    from picamera2 import Picamera2

    try:
        cam = Picamera2()
    except RuntimeError as exc:
        # Only one process can hold the camera. The usual cause is the preview
        # server still running in the background.
        raise RuntimeError(
            "cannot open the camera: another process is using it. "
            "Stop the preview with:  fuser -k 8080/tcp"
        ) from exc

    cam.configure(
        cam.create_video_configuration(
            main={"size": settings.size, "format": "BGR888"},
            sensor={"output_size": settings.sensor_mode, "bit_depth": 10},
        )
    )
    cam.start()
    return cam


def capture(settings: CameraSettings, settle: float = 2.0) -> np.ndarray:
    """Grab one transformed frame and release the camera.

    The settle delay is for auto-exposure. Without it the first frame is often
    dark and every colour fraction is meaningless.
    """
    cam = open_camera(settings)
    try:
        time.sleep(settle)
        frame = cam.capture_array("main")
    finally:
        cam.stop()
        cam.close()

    return apply_transform(frame, settings.rotation, settings.zoom)
