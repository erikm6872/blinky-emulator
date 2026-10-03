"""Blinky 2350 badge emulator.

Runs a real badgeware app's source (unmodified) against stubbed badge
globals (stubs.py) and device-only modules (sys_modules.py), rendering
each frame to a PNG served over a tiny local web page - no physical
hardware needed.

Usage:
    python3 server.py --app /path/to/your/app/__init__.py
    then open http://localhost:8765/ in a browser
    (--port to use a different port)

Known limitation: text is rendered with a real system font, size-fit
against the *measured* width/height for known strings per rom_font entry
(see font_metrics.py) - not the device's actual bitmap glyphs, which we
don't have. Only the strings that have actually been measured live on
hardware get exact layout; anything else is interpolated/approximate. See
README.md for the full fidelity breakdown.
"""

import argparse
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sys_modules  # noqa: E402
import stubs  # noqa: E402

FRAME_HZ = 20

HTML_PAGE = """<!doctype html>
<html>
<head>
<title>Blinky emulator - {app_name}</title>
<style>
  body {{ background: #111; color: #ddd; font-family: sans-serif; text-align: center; }}
  img {{ image-rendering: pixelated; margin-top: 20px; border: 2px solid #444; }}
  button {{ font-size: 16px; padding: 8px 16px; margin: 6px; cursor: pointer; }}
  #online.off {{ background: #622; color: #fff; }}
</style>
</head>
<body>
  <h2>Blinky emulator &mdash; {app_name}</h2>
  <img id="frame" src="/frame.png" width="{width}" height="{height}">
  <div>
    <button onclick="press('A')">Button A</button>
    <button onclick="press('B')">Button B</button>
    <button onclick="press('C')">Button C</button>
  </div>
  <div>
    <button id="online" onclick="toggleOnline()">Online/Offline</button>
  </div>
  <p id="status">-</p>
<script>
function press(btn) {{ fetch('/press?btn=' + btn); }}
function toggleOnline() {{ fetch('/toggle_online'); }}
setInterval(() => {{
  document.getElementById('frame').src = '/frame.png?t=' + Date.now();
  fetch('/status').then(r => r.json()).then(s => {{
    document.getElementById('status').textContent =
      'ticks=' + s.ticks + '  online=' + s.online;
    document.getElementById('online').className = s.online ? '' : 'off';
  }});
}}, 150);
</script>
</body>
</html>
"""


def load_app(app_path, device):
    with open(app_path) as f:
        source = f.read()
    ns, runner = stubs.build_globals(device)
    exec(compile(source, app_path, "exec"), ns)
    if runner.update_fn is None:
        raise RuntimeError("app never called run(update) - nothing to drive")
    return runner.update_fn


def simulation_loop(device, update_fn):
    frame_time = 1.0 / FRAME_HZ
    while True:
        start = time.monotonic()
        device.begin_frame()
        try:
            update_fn()
        except Exception as e:
            print("emulator: update() raised:", repr(e))
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, frame_time - elapsed))


class Handler(BaseHTTPRequestHandler):
    device = None  # set by main()
    app_name = ""  # set by main()

    def log_message(self, fmt, *args):
        pass  # quiet - the auto-polling page would otherwise spam the console

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            body = HTML_PAGE.format(
                app_name=self.app_name, width=stubs.SCREEN_W * 12, height=stubs.SCREEN_H * 12
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/frame.png"):
            buf = io.BytesIO()
            self.device.to_image().save(buf, format="PNG")
            body = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/press"):
            btn = self.path.split("btn=")[-1].strip().upper()
            if btn in ("A", "B", "C"):
                self.device.press_button(btn)
            self._empty_ok()
        elif self.path.startswith("/toggle_online"):
            sys_modules.connectivity.online = not sys_modules.connectivity.online
            self._empty_ok()
        elif self.path.startswith("/status"):
            body = json.dumps(
                {"ticks": self.device.ticks(), "online": sys_modules.connectivity.online}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def _empty_ok(self):
        self.send_response(204)
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="path to the app's __init__.py")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app_path = os.path.abspath(args.app)
    if not os.path.isfile(app_path):
        parser.error("no such file: {}".format(app_path))

    # State persists alongside the app being emulated (mirrors /state/ on
    # the real device), not inside this tool's own checkout - so multiple
    # projects using the same emulator install don't share/collide state.
    state_dir = os.path.join(os.path.dirname(app_path), ".emulator_state")
    sys_modules.set_state_dir(state_dir)
    sys_modules.install()

    device = stubs.Device()
    update_fn = load_app(app_path, device)

    thread = threading.Thread(target=simulation_loop, args=(device, update_fn), daemon=True)
    thread.start()

    Handler.device = device
    Handler.app_name = os.path.basename(os.path.dirname(app_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Blinky emulator running at http://localhost:{}/  (app: {})".format(
        args.port, app_path
    ))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
