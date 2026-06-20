from pathlib import Path
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from streamlit.web import cli as stcli


APP_NAME = "WordCloudGenerator"
CONTROL_PORT = 54873

HEARTBEAT_TIMEOUT_SECONDS = 25
CLOSING_GRACE_SECONDS = 5
NO_HEARTBEAT_STARTUP_TIMEOUT_SECONDS = 120


class AppState:
    def __init__(self):
        self.app_port = None
        self.last_heartbeat = 0.0
        self.seen_heartbeat = False
        self.closing_requested_at = None
        self.started_at = time.time()
        self.lock = threading.Lock()


STATE = AppState()


def resource_path(relative_path: str) -> str:
    """
    Gets the correct path whether running normally or from a PyInstaller bundle.
    """
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    return str(base_path / relative_path)


def find_free_port(start_port: int = 8501) -> int:
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise RuntimeError("Could not find a free port for Streamlit.")


def try_open_existing_instance() -> bool:
    """
    If another copy of the app is already running, ask it to open its browser tab.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{CONTROL_PORT}/open",
            timeout=1.0,
        ) as response:
            return response.status == 200
    except Exception:
        return False


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_response(self, status=200, body=b"OK", content_type="text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_response()

    def do_GET(self):
        if self.path.startswith("/open"):
            with STATE.lock:
                app_port = STATE.app_port

            if app_port:
                webbrowser.open(f"http://127.0.0.1:{app_port}")
                self._send_response()
            else:
                self._send_response(status=503, body=b"App port not ready")

        elif self.path.startswith("/status"):
            with STATE.lock:
                data = {
                    "app": APP_NAME,
                    "app_port": STATE.app_port,
                    "seen_heartbeat": STATE.seen_heartbeat,
                    "last_heartbeat": STATE.last_heartbeat,
                    "closing_requested_at": STATE.closing_requested_at,
                    "started_at": STATE.started_at,
                }

            self._send_response(
                body=json.dumps(data).encode("utf-8"),
                content_type="application/json",
            )

        else:
            self._send_response(status=404, body=b"Not found")

    def do_POST(self):
        now = time.time()

        if self.path.startswith("/heartbeat"):
            with STATE.lock:
                STATE.last_heartbeat = now
                STATE.seen_heartbeat = True
                STATE.closing_requested_at = None

            self._send_response()

        elif self.path.startswith("/closing"):
            with STATE.lock:
                STATE.closing_requested_at = now

            self._send_response()

        else:
            self._send_response(status=404, body=b"Not found")


def start_control_server(app_port: int) -> ThreadingHTTPServer:
    with STATE.lock:
        STATE.app_port = app_port

    server = ThreadingHTTPServer(("127.0.0.1", CONTROL_PORT), ControlHandler)

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    return server


def open_browser_later(port: int) -> None:
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{port}")


def monitor_browser_liveness() -> None:
    """
    Exits the app after the browser tab is closed.

    It uses:
    - a heartbeat while the tab is open
    - a closing signal from the browser
    - a heartbeat timeout as backup
    """
    while True:
        time.sleep(2)
        now = time.time()

        with STATE.lock:
            seen = STATE.seen_heartbeat
            last = STATE.last_heartbeat
            closing = STATE.closing_requested_at
            started_at = STATE.started_at

        if not seen:
            if now - started_at > NO_HEARTBEAT_STARTUP_TIMEOUT_SECONDS:
                os._exit(0)
            continue

        if closing is not None:
            closing_age = now - closing
            heartbeat_age = now - last

            if (
                closing_age >= CLOSING_GRACE_SECONDS
                and heartbeat_age >= CLOSING_GRACE_SECONDS
            ):
                os._exit(0)

        heartbeat_age = now - last

        if heartbeat_age >= HEARTBEAT_TIMEOUT_SECONDS:
            os._exit(0)


def main() -> None:
    # If app is already running, open that existing instance and quit.
    if try_open_existing_instance():
        return

    app_port = find_free_port()
    app_path = resource_path("streamlit_app.py")

    os.environ["WCG_CONTROL_PORT"] = str(CONTROL_PORT)

    try:
        start_control_server(app_port)
    except OSError:
        if try_open_existing_instance():
            return
        raise

    threading.Thread(
        target=open_browser_later,
        args=(app_port,),
        daemon=True,
    ).start()

    threading.Thread(
        target=monitor_browser_liveness,
        daemon=True,
    ).start()

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.port",
        str(app_port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]

    sys.exit(stcli.main())


if __name__ == "__main__":
    main()