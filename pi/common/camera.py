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
    # Region of interest as (x, y, w, h) in 0..1 fractions of the frame.
    # (0, 0, 1, 1) means the whole frame. Cropping here produces a genuinely
    # smaller output image, which is what saves encoding work.
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    # The lens starts at infinity, which leaves a leaf held close to the camera
    # badly out of focus. Continuous autofocus fixes it but hunts, and hunting
    # costs energy, so it is a setting rather than always-on.
    autofocus: bool = True
    # Auto white balance picks its own gains per capture, and on a dark leaf it
    # picks a large blue gain, which is enough to turn brown into blue. Locking
    # the gains makes the colour stable, which is what the hue bands in
    # config/vision.json are tuned against.
    awb: str = "auto"
    colour_gains: tuple[float, float] = (1.0, 1.0)
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
            crop=tuple(data.get("crop", (0.0, 0.0, 1.0, 1.0))),
            autofocus=bool(data.get("autofocus", True)),
            awb=str(data.get("awb", "auto")),
            colour_gains=tuple(data.get("colour_gains", (1.0, 1.0))),
            preview=bool(data.get("preview", True)),
            preview_port=int(data.get("preview_port", 8080)),
            preview_fps=int(data.get("preview_fps", 15)),
        )

    def to_dict(self) -> dict:
        """Serialise for the config file, keeping the explanatory keys."""
        return {
            "_comment": (
                "Shared by tools/preview.py and pi/vision/leafs.py, so what you "
                "frame in the browser is what the scanner analyses."
            ),
            "size": list(self.size),
            "sensor_mode": list(self.sensor_mode),
            "_sensor_mode_note": (
                "2304x1296 uses the whole sensor. The default 1536x864 mode is a "
                "centre crop and looks zoomed in."
            ),
            "crop": [round(v, 4) for v in self.crop],
            "_crop_note": (
                "Region of interest as [x, y, w, h] in 0..1 fractions. "
                "[0, 0, 1, 1] is the whole frame. Cropping here makes the output "
                "image genuinely smaller, which is the only size change that "
                "saves real work."
            ),
            "rotation": self.rotation,
            "_rotation_note": "0, 90, 180 or 270 degrees clockwise.",
            "zoom": self.zoom,
            "_zoom_note": (
                "1.0 is the full frame. 2.0 crops to the middle half and scales "
                "back up, so it changes framing but not output size."
            ),
            "autofocus": self.autofocus,
            "_autofocus_note": (
                "Continuous autofocus. Without it the lens stays at infinity and "
                "a leaf held close is badly blurred. Hunting costs energy, so "
                "turn it off once the camera is fixed in place."
            ),
            "awb": self.awb,
            "_awb_note": (
                "'auto' lets the camera pick white balance per capture, which on "
                "a dark leaf can pick a large blue gain and turn brown into blue. "
                "'off' locks colour_gains, so the hue is stable and the bands in "
                "vision.json mean something."
            ),
            "colour_gains": list(self.colour_gains),
            "_colour_gains_note": (
                "Only used when awb is 'off'. [red, blue] multipliers. 1.0 is no "
                "correction. Raise red to warm the image, raise blue to cool it."
            ),
            "preview": self.preview,
            "preview_port": self.preview_port,
            "preview_fps": self.preview_fps,
        }

    @classmethod
    def write(cls, settings: "CameraSettings", path: str | Path | None = None) -> Path:
        """Write settings back to the config file. Returns the path written."""
        config_path = Path(path) if path else DEFAULT_PATH
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(settings.to_dict(), indent=2) + "\n")
        return config_path


def apply_transform(
    frame: np.ndarray,
    rotation: int = 0,
    zoom: float = 1.0,
    crop: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """Rotate, crop and zoom a frame.

    Order matters, and it is chosen to match what the user sees. Rotation runs
    first so the crop coordinates refer to the upright image on screen; cropping
    before rotation would make a selection land somewhere else whenever the
    rotation is not zero.

    The crop does **not** scale back up, so a half-width crop really does
    produce a half-width image — that is the only size change that saves
    encoding work. Zoom then crops further and scales back to the cropped size,
    so it changes framing without changing output size.
    """
    rotation %= 360
    if rotation == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    if crop is not None:
        x, y, w, h = crop
        if (x, y, w, h) != (0.0, 0.0, 1.0, 1.0):
            height, width = frame.shape[:2]
            x0 = max(0, min(width - 1, int(x * width)))
            y0 = max(0, min(height - 1, int(y * height)))
            x1 = max(x0 + 1, min(width, int((x + w) * width)))
            y1 = max(y0 + 1, min(height, int((y + h) * height)))
            frame = frame[y0:y1, x0:x1]

    if zoom and zoom > 1.0:
        height, width = frame.shape[:2]
        crop_w, crop_h = int(width / zoom), int(height / zoom)
        x0 = (width - crop_w) // 2
        y0 = (height - crop_h) // 2
        frame = frame[y0 : y0 + crop_h, x0 : x0 + crop_w]
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)

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
    if settings.autofocus and "AfMode" in cam.camera_controls:
        # 2 is continuous. Left alone the lens sits at infinity, which leaves a
        # leaf held close to the camera badly out of focus.
        cam.set_controls({"AfMode": 2, "AfSpeed": 1})
    if settings.awb == "off":
        # Auto white balance re-decides per capture, and on a dark leaf it picks
        # a large blue gain. Locking it keeps the hue comparable between frames,
        # which is the only way the bands in vision.json can be tuned at all.
        cam.set_controls({
            "AwbEnable": False,
            "ColourGains": tuple(settings.colour_gains),
        })
    return cam


def save_last(image: np.ndarray, path: str | Path = "logs/last_capture.jpg") -> None:
    """Keep the frame that was just analysed, for the dashboard to show.

    The dashboard cannot stream the camera: only one process can hold it, and
    the variant loop needs it. Showing the frame that produced the verdict is
    both cheaper and more useful than a live view.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), image)


def capture(settings: CameraSettings, settle: float | None = None) -> np.ndarray:
    """Grab one transformed frame and release the camera.

    The settle delay is for auto-exposure, and for autofocus to hunt to a lock.
    Without it the first frame is often dark and out of focus, and every colour
    fraction is meaningless.
    """
    if settle is None:
        settle = 4.0 if settings.autofocus else 2.0

    cam = open_camera(settings)
    try:
        time.sleep(settle)
        frame = cam.capture_array("main")
    finally:
        cam.stop()
        cam.close()

    return apply_transform(frame, settings.rotation, settings.zoom, settings.crop)
