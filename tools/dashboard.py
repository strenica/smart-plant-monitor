#!/usr/bin/env python3
"""A small web dashboard for the plant monitor.

Three things you actually want while the thing is running: what the sensors
last said, what the log recorded, and a way to edit configuration.txt without
SSH.

It deliberately does not stream the camera. Only one process can hold it, and
the variant loop needs it for its periodic captures, so a live stream would
fight the scanner. Instead it shows the last frame the scanner analysed, which
is the frame that produced the verdict on screen.

    python3 tools/dashboard.py
    python3 tools/dashboard.py --port 8081
    python3 tools/dashboard.py --log logs/events_log.txt
"""

from __future__ import annotations

import argparse
import html
import json
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


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

from common.config import parse_config, parse_timing  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

FIELDS = ("air_humidity", "air_temperature", "soil_humidity")

MONITOR_UNIT = "plant-monitor.service"
PREVIEW_PORT = 8080


def preview_running() -> bool:
    """True while the setup preview holds the camera.

    The preview runs under the monitor unit, so restarting the monitor would
    kill a framing session the user is in the middle of.
    """
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", PREVIEW_PORT)) == 0


def restart_monitor() -> str:
    """Apply a saved config by restarting the monitoring service.

    The variant loops read configuration.txt once at startup, so a saved file
    does nothing until the process is replaced. The dashboard unit runs as
    root, which is what makes this possible without a password.
    """
    try:
        result = subprocess.run(
            ["systemctl", "restart", MONITOR_UNIT],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"monitor not restarted: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return f"monitor not restarted: {detail or result.returncode}"
    return "monitor restarted"


STYLE = """
  :root { color-scheme: dark; }
  body { background:#111; color:#ddd; font:14px/1.5 system-ui,sans-serif;
         margin:0; padding:0 1.5rem 3rem; }
  nav { display:flex; gap:1.25rem; padding:1rem 0; border-bottom:1px solid #2a2a2a;
        margin-bottom:1.5rem; }
  nav a { color:#8ab4f8; text-decoration:none; }
  nav a.on { color:#fff; font-weight:600; }
  h1 { font-size:1.15rem; font-weight:600; margin:0 0 1rem; }
  h2 { font-size:.95rem; font-weight:600; margin:1.75rem 0 .5rem; color:#aaa; }
  table { border-collapse:collapse; width:100%; max-width:60rem; }
  td, th { text-align:left; padding:.3rem .75rem .3rem 0; vertical-align:top; }
  th { color:#888; font-weight:500; }
  .cards { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:.5rem; }
  .card { background:#1a1a1a; border:1px solid #2a2a2a; border-radius:8px;
          padding:.75rem 1.1rem; min-width:9rem; }
  .card .k { color:#888; font-size:.8rem; text-transform:uppercase;
             letter-spacing:.04em; }
  .card .v { font-size:1.5rem; font-variant-numeric:tabular-nums; }
  pre { background:#1a1a1a; border:1px solid #2a2a2a; border-radius:8px;
        padding:.75rem 1rem; overflow:auto; max-height:32rem; font-size:12.5px; }
  textarea { width:100%; max-width:60rem; min-height:26rem; background:#1a1a1a;
             color:#ddd; border:1px solid #2a2a2a; border-radius:8px;
             padding:.75rem 1rem; font:12.5px/1.6 ui-monospace,monospace; }
  button { background:#2d5bd7; color:#fff; border:0; border-radius:6px;
           padding:.5rem 1.1rem; font:inherit; cursor:pointer; margin-top:.75rem; }
  .ok { color:#7bd88f; } .err { color:#ff8a80; }
  .muted { color:#777; }
  img.shot { max-width:100%; border-radius:8px; border:1px solid #2a2a2a; }
  .shots { display:flex; gap:1rem; flex-wrap:wrap; }
  .shots figure { margin:0; flex:1 1 20rem; min-width:0; }
  .shots figcaption { color:#888; font-size:.8rem; margin-top:.35rem; }
"""


def read_lines(path: Path, limit: int) -> list[str]:
    """Last `limit` lines of a file, or an empty list if it is not there yet."""
    if not path.exists():
        return []
    return path.read_text(errors="replace").splitlines()[-limit:]


def latest_values(lines: list[str]) -> dict[str, str]:
    """Most recent value of each sensor field, scanning backwards."""
    found: dict[str, str] = {}
    for line in reversed(lines):
        _, sep, rhs = line.partition(": ")
        if not sep or " = " not in rhs:
            continue
        field, _, value = rhs.partition(" = ")
        field = field.strip()
        if field in FIELDS and field not in found:
            found[field] = value.strip()
        if len(found) == len(FIELDS):
            break
    return found


def page(title: str, body: str, active: str) -> bytes:
    def link(href: str, label: str, key: str) -> str:
        cls = ' class="on"' if key == active else ""
        return f'<a href="{href}"{cls}>{label}</a>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{STYLE}</style></head><body>
<nav>{link("/", "status", "status")}{link("/log", "log", "log")}\
{link("/config", "config", "config")}{link("/vision", "vision", "vision")}</nav>
{body}
</body></html>""".encode()


def validate_vision(text: str) -> dict:
    """Parse and check config/vision.json. Raises ValueError with a reason.

    Checked here rather than in leafs.py because a bad band that parses but
    makes no sense — a hue range of 200, say — would silently classify nothing
    and the verdict would just say "borderline" with no clue why.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")

    for name in ("green", "yellow", "brown"):
        band = data.get(name)
        if not isinstance(band, dict):
            raise ValueError(f"missing band {name!r}")

        hue = band.get("hue")
        if not (isinstance(hue, list) and len(hue) == 2):
            raise ValueError(f"{name}.hue must be [low, high]")
        low, high = hue
        if not (isinstance(low, int) and isinstance(high, int)):
            raise ValueError(f"{name}.hue must be two integers")
        if not 0 <= low <= high <= 179:
            raise ValueError(f"{name}.hue must satisfy 0 <= low <= high <= 179")

        for key in ("sat", "val", "val_max"):
            if key in band and not isinstance(band[key], int):
                raise ValueError(f"{name}.{key} must be an integer")
    return data


def make_handler(log_path: Path, config_path: Path, capture_path: Path,
                 analysis_path: Path, vision_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass   # quiet; the variant loop owns the console

        def _send(self, body: bytes, status: int = 200,
                  content_type: str = "text/html; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            # Match on the path alone. The status page appends a cache-busting
            # query string to the image URL, and comparing self.path directly
            # would 404 on it.
            path = urlparse(self.path).path
            if path == "/":
                self._status()
            elif path == "/log":
                self._log()
            elif path == "/config":
                self._config()
            elif path == "/vision":
                self._vision()
            elif path == "/capture.jpg":
                self._image(capture_path, "no capture yet")
            elif path == "/analysis.jpg":
                self._image(analysis_path, "no analysis yet")
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in ("/config", "/vision"):
                self.send_error(404)
                return

            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode(errors="replace"))
            text = form.get("text", [""])[0]

            if path == "/vision":
                try:
                    validate_vision(text)
                except ValueError as exc:
                    self._vision(text=text, error=str(exc))
                    return
                vision_path.write_text(text)
                self._vision(
                    text=text,
                    saved="saved; applies to the next capture, no restart needed",
                )
                return

            # Validate before writing. A config that parses is the only thing
            # that gets saved, so a typo cannot take the monitor down.
            try:
                rules = parse_config(text)
                timing = parse_timing(text)
            except ValueError as exc:
                self._config(text=text, error=str(exc))
                return

            config_path.write_text(text)

            restart = not preview_running()
            note = (
                "monitor restarting"
                if restart
                else "preview is running, monitor left alone"
            )
            self._config(
                text=text,
                saved=f"saved: {len(rules)} rules, "
                f"{sum(v is not None for v in vars(timing).values())} timing keys; "
                f"{note}",
            )

            if restart:
                # After the response, so a restart that halts the Pi cannot cut
                # the reply off halfway.
                print(restart_monitor(), flush=True)

        def _status(self) -> None:
            lines = read_lines(log_path, 400)
            values = latest_values(lines)

            cards = "".join(
                f'<div class="card"><div class="k">{html.escape(f)}</div>'
                f'<div class="v">{html.escape(values.get(f, "—"))}</div></div>'
                for f in FIELDS
            )

            # Newest first: the interesting end of a log is the end.
            recent = "".join(
                f"<tr><td>{html.escape(line)}</td></tr>"
                for line in reversed(lines[-25:])
            ) or '<tr><td class="muted">no log yet</td></tr>'

            shots = ""
            if capture_path.exists() or analysis_path.exists():
                figures = ""
                for source, url, caption in (
                    (capture_path, "/capture.jpg", "as captured"),
                    (analysis_path, "/analysis.jpg",
                     "leaf regions the model found"),
                ):
                    if not source.exists():
                        continue
                    stamp = int(source.stat().st_mtime)
                    figures += (
                        f'<figure><img class="shot" src="{url}?{stamp}" '
                        f'alt="{caption}">'
                        f"<figcaption>{caption}</figcaption></figure>"
                    )
                shots = (
                    '<h2>last analysed frame</h2>'
                    f'<div class="shots">{figures}</div>'
                )

            body = f"""<h1>Plant monitor</h1>
<div class="cards">{cards}</div>
{shots}
<h2>recent events</h2>
<table>{recent}</table>"""
            self._send(page("Plant monitor", body, "status"))

        def _log(self) -> None:
            lines = read_lines(log_path, 500)
            text = "\n".join(lines) if lines else "no log yet"
            body = (
                f"<h1>events_log.txt</h1>"
                f"<p class=\"muted\">{len(lines)} lines, newest last</p>"
                f"<pre>{html.escape(text)}</pre>"
            )
            self._send(page("Log", body, "log"))

        def _config(self, text: str | None = None, error: str = "",
                    saved: str = "") -> None:
            if text is None:
                text = config_path.read_text() if config_path.exists() else ""

            banner = ""
            if error:
                banner = f'<p class="err">not saved: {html.escape(error)}</p>'
            elif saved:
                banner = f'<p class="ok">{html.escape(saved)}</p>'

            body = f"""<h1>configuration.txt</h1>
<p class="muted">Rules are <code>N: field op threshold</code>. Timing is
<code>key = value</code> in seconds. The file is validated before it is
written, so a typo is reported instead of saved.</p>
{banner}
<form method="post" action="/config">
<textarea name="text" spellcheck="false">{html.escape(text)}</textarea>
<button type="submit">save</button>
</form>"""
            self._send(page("Config", body, "config"))

        def _vision(self, text: str | None = None, error: str = "",
                    saved: str = "") -> None:
            if text is None:
                text = vision_path.read_text() if vision_path.exists() else "{}"

            banner = ""
            if error:
                banner = f'<p class="err">not saved: {html.escape(error)}</p>'
            elif saved:
                banner = f'<p class="ok">{html.escape(saved)}</p>'

            body = f"""<h1>vision.json</h1>
<p class="muted">Hue bands for the colour rule, on OpenCV's 0..179 scale, so
30 is 60 degrees. Saturation and value are 0..255. Ranges are inclusive.
<code>val_max</code> is an optional upper bound on brightness, which is how
"brown" is told apart from "orange".</p>
<p class="muted">Tune these against the numbers in the event log: each leaf
logs its measured <code>H</code>, <code>S</code> and <code>V</code>. If a leaf
scores zero on all three bands, its hue is outside every range.</p>
{banner}
<form method="post" action="/vision">
<textarea name="text" spellcheck="false">{html.escape(text)}</textarea>
<button type="submit">save</button>
</form>"""
            self._send(page("Vision", body, "vision"))

        def _image(self, source: Path, missing: str) -> None:
            if not source.exists():
                self.send_error(404, missing)
                return
            self._send(source.read_bytes(), content_type="image/jpeg")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--log", default=str(ROOT / "logs" / "events_log.txt"))
    ap.add_argument("--config", default=str(ROOT / "config" / "configuration.txt"))
    ap.add_argument("--capture", default=str(ROOT / "logs" / "last_capture.jpg"))
    ap.add_argument("--analysis", default=str(ROOT / "logs" / "last_analysis.jpg"))
    ap.add_argument("--vision", default=str(ROOT / "config" / "vision.json"))
    args = ap.parse_args()

    handler = make_handler(
        Path(args.log),
        Path(args.config),
        Path(args.capture),
        Path(args.analysis),
        Path(args.vision),
    )
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    print(f"dashboard on http://<pi-address>:{args.port}/")
    print("ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
