#!/usr/bin/env python3
"""Live MJPEG preview with framing controls, viewable in any browser.

The Pi is headless, so a local preview window is no use. This serves the camera
as a multipart JPEG stream and lets you adjust rotation, zoom and capture size
while watching. "Save and apply" writes those settings to config/camera.json
and shuts the server down, so the camera is free for the leaf scanner.

Settings are shared with the scanner, so what you frame here is what gets
analysed.

    python3 preview.py
    python3 preview.py --port 9000
    python3 preview.py --rotation 90 --zoom 1.5

Endpoints:
    GET  /          the viewer page
    GET  /stream    multipart MJPEG
    GET  /snap      one JPEG
    GET  /settings  current settings as JSON
    POST /settings  update rotation, zoom or size live
    POST /save      write config/camera.json and stop the server
"""

from __future__ import annotations

import argparse
import json
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

SIZE_CHOICES = [(640, 480), (800, 600), (1024, 768), (1280, 720), (1280, 960), (1920, 1080)]


class LiveState:
    """Settings shared between the HTTP handler and the capture thread."""

    def __init__(self, settings: CameraSettings):
        self.lock = threading.Lock()
        self.settings = settings
        self.reconfigure = False     # set when `size` changes
        self.stop = threading.Event()
        self.frame: bytes | None = None

    def update(self, rotation=None, zoom=None, size=None) -> None:
        with self.lock:
            if rotation is not None:
                self.settings.rotation = int(rotation) % 360
            if zoom is not None:
                self.settings.zoom = max(1.0, min(4.0, float(zoom)))
            if size is not None:
                new_size = (int(size[0]), int(size[1]))
                if new_size != self.settings.size:
                    self.settings.size = new_size
                    self.reconfigure = True

    def snapshot(self) -> dict:
        with self.lock:
            s = self.settings
            return {
                "size": list(s.size),
                "rotation": s.rotation,
                "zoom": s.zoom,
                "preview": s.preview,
                "preview_port": s.preview_port,
                "preview_fps": s.preview_fps,
            }


def capture_loop(state: LiveState, quality: int) -> None:
    """Grab frames continuously, reconfiguring when the size changes."""
    cam = open_camera(state.settings)
    time.sleep(1.0)   # let auto-exposure settle before the first frame

    try:
        while not state.stop.is_set():
            with state.lock:
                if state.reconfigure:
                    state.reconfigure = False
                    cam.stop()
                    cam.close()
                    cam = open_camera(state.settings)
                    time.sleep(0.5)
                rotation = state.settings.rotation
                zoom = state.settings.zoom
                fps = state.settings.preview_fps

            started = time.monotonic()
            array = cam.capture_array("main")
            array = apply_transform(array, rotation, zoom)
            ok, buffer = cv2.imencode(
                ".jpg", array, [cv2.IMWRITE_JPEG_QUALITY, quality]
            )
            if ok:
                with state.lock:
                    state.frame = buffer.tobytes()

            remaining = (1.0 / fps) - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        cam.stop()
        cam.close()


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Pi camera preview</title>
<style>
  html, body { height:100%; margin:0; }
  body { background:#111; color:#ddd; font:14px system-ui,sans-serif;
         display:flex; flex-direction:column; }
  header { flex:0 0 auto; padding:10px 14px; background:#1b1b1b;
           display:flex; gap:18px; align-items:center; flex-wrap:wrap }
  header b { color:#fff; font-weight:600 }
  /* The image gets whatever vertical space the header leaves and is letterboxed
     inside it, so it never overflows the window whatever the aspect ratio. */
  main { flex:1 1 auto; min-height:0; display:flex; align-items:center;
         justify-content:center; background:#000 }
  img { max-width:100%; max-height:100%; object-fit:contain; display:block }
  button, select { background:#2a2a2a; color:#ddd; border:1px solid #444;
                   border-radius:5px; padding:5px 10px; font:inherit; cursor:pointer }
  button:hover, select:hover { background:#333 }
  button.on { background:#2d6cdf; border-color:#2d6cdf; color:#fff }
  input[type=range] { width:130px; vertical-align:middle }
  #save { background:#1f7a3d; border-color:#1f7a3d; color:#fff; font-weight:600 }
  #save:hover { background:#26914a }
  #status { color:#8c8; min-width:180px }
  label { display:flex; gap:6px; align-items:center }
</style></head>
<body>
<header>
  <b>Preview</b>

  <label>Rotate
    <button data-rot="0" class="rot">0</button>
    <button data-rot="90" class="rot">90</button>
    <button data-rot="180" class="rot">180</button>
    <button data-rot="270" class="rot">270</button>
  </label>

  <label>Zoom <input id="zoom" type="range" min="1" max="3" step="0.1" value="1">
    <span id="zoomval">1.0</span></label>

  <label>Size <select id="size"></select></label>

  <label><input id="disable" type="checkbox" checked> disable preview after saving</label>

  <button id="save">Save and apply</button>
  <span id="status"></span>
</header>
<main><img id="stream" src="/stream" alt="camera stream"></main>

<script>
const SIZES = __SIZES__;
let state = __STATE__;

const sizeSel = document.getElementById('size');
for (const [w,h] of SIZES) {
  const o = document.createElement('option');
  o.value = w + 'x' + h; o.textContent = w + 'x' + h;
  sizeSel.appendChild(o);
}

function paint() {
  document.querySelectorAll('.rot').forEach(b =>
    b.classList.toggle('on', Number(b.dataset.rot) === state.rotation));
  document.getElementById('zoom').value = state.zoom;
  document.getElementById('zoomval').textContent = Number(state.zoom).toFixed(1);
  sizeSel.value = state.size[0] + 'x' + state.size[1];
}

async function push(patch) {
  const r = await fetch('/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(patch)
  });
  state = await r.json();
  paint();
}

document.querySelectorAll('.rot').forEach(b =>
  b.onclick = () => push({rotation: Number(b.dataset.rot)}));

document.getElementById('zoom').oninput = e => {
  document.getElementById('zoomval').textContent = Number(e.target.value).toFixed(1);
};
document.getElementById('zoom').onchange = e => push({zoom: Number(e.target.value)});

sizeSel.onchange = e => {
  const [w,h] = e.target.value.split('x').map(Number);
  push({size: [w,h]});
};

document.getElementById('save').onclick = async () => {
  const status = document.getElementById('status');
  status.textContent = 'saving...';
  const r = await fetch('/save', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({disable_preview: document.getElementById('disable').checked})
  });
  const out = await r.json();
  status.textContent = out.message;
  document.getElementById('stream').src = '';
};

paint();
</script>
</body></html>
"""


def make_handler(state: LiveState):
    page = (
        PAGE.replace("__SIZES__", json.dumps([list(s) for s in SIZE_CHOICES]))
        .replace("__STATE__", json.dumps(state.snapshot()))
        .encode()
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:   # keep the console quiet
            pass

        def _json(self, payload: dict, code: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            elif self.path == "/settings":
                self._json(state.snapshot())

            elif self.path == "/snap":
                with state.lock:
                    frame = state.frame
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
                    while not state.stop.is_set():
                        with state.lock:
                            frame = state.frame
                            fps = state.settings.preview_fps
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

        def do_POST(self) -> None:
            body = self._body()

            if self.path == "/settings":
                state.update(
                    rotation=body.get("rotation"),
                    zoom=body.get("zoom"),
                    size=body.get("size"),
                )
                self._json(state.snapshot())

            elif self.path == "/save":
                with state.lock:
                    if body.get("disable_preview"):
                        state.settings.preview = False
                    saved = state.settings

                path = CameraSettings.write(saved)
                message = f"saved to {path.name}"
                if not saved.preview:
                    message += ", preview disabled"
                self._json({"message": message, "settings": state.snapshot()})

                # Give the response time to reach the browser, then stop.
                threading.Timer(0.6, state.stop.set).start()
                threading.Timer(0.8, self.server.shutdown).start()

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
    ap.add_argument(
        "--force",
        action="store_true",
        help="run even when preview is disabled in the config",
    )
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

    if not settings.preview and not args.force:
        print('preview is disabled in camera.json (set "preview": true, or pass --force)')
        return

    state = LiveState(settings)
    thread = threading.Thread(target=capture_loop, args=(state, args.quality), daemon=True)
    thread.start()

    server = ThreadingHTTPServer(("0.0.0.0", settings.preview_port), make_handler(state))
    print(
        f"preview on http://<pi-address>:{settings.preview_port}/  "
        f"({settings.size[0]}x{settings.size[1]}, {settings.preview_fps} fps)"
    )
    print("ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        state.stop.set()
        server.shutdown()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
