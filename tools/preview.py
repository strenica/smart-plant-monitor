#!/usr/bin/env python3
"""Live MJPEG preview from the Pi camera, viewable in any browser.

The Pi is headless, so a local preview window is no use. This serves the camera
as a multipart JPEG stream instead: open the URL on your laptop and position
the camera while watching.

Settings come from `config/camera.json`, the same file the leaf scanner reads,
so what you frame here is what gets analysed. Rotation and zoom can be
overridden on the command line for a quick experiment.

    python3 preview.py
    python3 preview.py --rotation 90 --zoom 1.5
    python3 preview.py --port 9000

Endpoints:
    /        the viewer page
    /stream  multipart MJPEG
    /snap    one JPEG, useful for scripting
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2


def _find_pi_root() -> Path | None:
    """Locate the `pi` package whether this runs from tools/ or from ~/plant."""
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "pi" / "common" / "camera.py").exists():
            return candidate / "pi"
    return None


_pi_root = _find_pi_root()
if _pi_root is not None:
    sys.path.insert(0, str(_pi_root))

from common.camera import CameraSettings, apply_transform, open_camera  # noqa: E402

_frame: bytes | None = None
_lock = threading.Lock()
_stop = threading.Event()

PAGE = """<!doctype html>
<html><head><title>Pi camera preview</title>
<style>
  body {{ margin:0; background:#111; color:#ddd; font:14px system-ui,sans-serif }}
  header {{ padding:8px 12px; background:#1b1b1b }}
  img {{ display:block; width:100%; height:auto }}
</style></head>
<body>
<header>{size} &middot; {fps} fps &middot; rot {rotation} &middot; zoom {zoom:g}
&middot; <a href="/snap" style="color:#7cf">snapshot</a></header>
<img src="/stream" alt="camera stream">
</body></html>
"""


def capture_loop(settings: CameraSettings, fps: int, quality: int) -> None:
    """Grab frames continuously and keep the newest JPEG in memory."""
    global _frame

    cam = open_camera(settings)
    time.sleep(1.0)   # let auto-exposure settle before the first frame

    interval = 1.0 / fps
    try:
        while not _stop.is_set():
            started = time.monotonic()
            array = cam.capture_array("main")
            array = apply_transform(array, settings.rotation, settings.zoom)
            ok, buffer = cv2.imencode(
                ".jpg", array, [cv2.IMWRITE_JPEG_QUALITY, quality]
            )
            if ok:
                with _lock:
                    _frame = buffer.tobytes()
            # Pace the loop so a fast sensor does not saturate the CPU.
            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        cam.stop()
        cam.close()


def make_handler(settings: CameraSettings, fps: int):
    page = PAGE.format(
        size=f"{settings.size[0]}x{settings.size[1]}",
        fps=fps,
        rotation=settings.rotation,
        zoom=settings.zoom,
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:   # keep the console quiet
            pass

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            elif self.path == "/snap":
                with _lock:
                    frame = _frame
                if frame is None:
                    self.send_error(503, "no frame yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)

            elif self.path == "/stream":
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.end_headers()
                try:
                    while not _stop.is_set():
                        with _lock:
                            frame = _frame
                        if frame is None:
                            time.sleep(0.05)
                            continue
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(frame)}\r\n\r\n".encode()
                        )
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        time.sleep(1.0 / fps)
                except (BrokenPipeError, ConnectionResetError):
                    pass   # browser tab closed; nothing to do

            else:
                self.send_error(404)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", help="path to camera.json")
    ap.add_argument("--port", type=int, help="override preview_port")
    ap.add_argument("--fps", type=int, help="override preview_fps")
    ap.add_argument("--rotation", type=int, choices=[0, 90, 180, 270])
    ap.add_argument("--zoom", type=float)
    ap.add_argument("--quality", type=int, default=80, help="JPEG quality 1-100")
    args = ap.parse_args()

    settings = CameraSettings.load(args.config)
    if args.port is not None:
        settings.preview_port = args.port
    if args.fps is not None:
        settings.preview_fps = args.fps
    if args.rotation is not None:
        settings.rotation = args.rotation
    if args.zoom is not None:
        settings.zoom = args.zoom

    if not settings.preview:
        print("preview is disabled in camera.json (set \"preview\": true to enable)")
        return

    thread = threading.Thread(
        target=capture_loop,
        args=(settings, settings.preview_fps, args.quality),
        daemon=True,
    )
    thread.start()

    server = ThreadingHTTPServer(
        ("0.0.0.0", settings.preview_port), make_handler(settings, settings.preview_fps)
    )
    print(
        f"preview on http://<pi-address>:{settings.preview_port}/  "
        f"({settings.size[0]}x{settings.size[1]}, {settings.preview_fps} fps, "
        f"rot {settings.rotation}, zoom {settings.zoom:g})"
    )
    print("ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        _stop.set()
        server.shutdown()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
