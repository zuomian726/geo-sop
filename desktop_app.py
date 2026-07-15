"""
macOS/desktop development launcher.

Starts the existing Flask app on localhost and opens it in a desktop window
when pywebview is available. Falls back to the default browser.
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import TCPServer, ThreadingMixIn

from version import APP_NAME, APP_VERSION


ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB_APP_DIR = ROOT_DIR / "web_app"

# The Windows installer ships Playwright Chromium beside the executable.
# Configure its location before collector modules import Playwright.
if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
    bundled_browsers = Path(sys.executable).resolve().parent / "ms-playwright"
    if bundled_browsers.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled_browsers))

os.environ.setdefault("GEO_DESKTOP_MODE", "1")
os.environ.setdefault("GEO_REQUIRE_LOGIN", "1")
os.environ.setdefault("GEO_CLOUD_SYNC_URL", "https://geo.allgood.cn/api")
os.environ.setdefault("NODE_NO_WARNINGS", "1")
os.environ.setdefault("FLASK_ENV", "production")

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(WEB_APP_DIR))


def _boot_log(message: str):
    if os.environ.get("GEO_DEBUG_BOOT") != "1":
        return
    try:
        log_path = Path(os.environ.get("TEMP") or "/tmp") / "geo_sop_boot.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {message}\n")
    except Exception:
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _init_database():
    from app import app
    from models import db, ensure_local_sync_schema
    from sqlalchemy import inspect

    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        required_tables = {"users", "monitor_tasks", "collection_results"}
        missing_tables = sorted(required_tables - existing_tables)
        if missing_tables:
            db.session.remove()
            db.engine.dispose()
            db.create_all()
            inspector = inspect(db.engine)
            existing_tables = set(inspector.get_table_names())
            missing_tables = sorted(required_tables - existing_tables)
        if missing_tables:
            raise RuntimeError(f"Local database initialization failed, missing tables: {', '.join(missing_tables)}")
        ensure_local_sync_schema()
        _boot_log(f"database initialized tables={len(existing_tables)}")


def _start_remote_worker():
    try:
        from app import app
        from remote_worker import start_remote_task_worker

        started = start_remote_task_worker(app)
        _boot_log(f"remote task worker started={started}")
    except Exception as exc:
        _boot_log(f"remote task worker failed: {type(exc).__name__}: {exc}")


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

    def server_bind(self):
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port
        self.setup_environ()


class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        from app import app

        _boot_log(f"creating wsgi server {host}:{port}")
        self.server = make_server(host, port, app, server_class=ThreadingWSGIServer)
        _boot_log(f"wsgi server created fileno={self.server.fileno()}")

    def run(self):
        _boot_log("server thread entering serve_forever")
        try:
            self.server.serve_forever()
        except Exception as exc:
            _boot_log(f"server thread failed: {type(exc).__name__}: {exc}")
            raise

    def shutdown(self):
        self.server.shutdown()


def _wait_for_server(host: str, port: int, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _startup_path_from_args() -> str:
    for arg in sys.argv[1:]:
        if not str(arg).lower().startswith("geo-sop://"):
            continue
        parsed = urlparse(arg)
        target = (parse_qs(parsed.query).get("target") or ["dashboard"])[0]
        if target in {"dashboard", "login"}:
            return "/dashboard"
        if target == "ai-settings":
            return "/dashboard#sentiment_settings"
        return "/dashboard"
    return "/"


def main():
    os.chdir(ROOT_DIR)
    _init_database()
    _start_remote_worker()

    host = "127.0.0.1"
    port = _free_port()
    startup_path = _startup_path_from_args()
    url = f"http://{host}:{port}{startup_path}"
    server = ServerThread(host, port)
    server.start()
    if not _wait_for_server(host, port):
        raise RuntimeError(f"Local server did not start on {host}:{port}")

    print(f"{APP_NAME} v{APP_VERSION} desktop server: {url}", flush=True)

    if os.environ.get("GEO_FORCE_BROWSER") == "1":
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.shutdown()
            return None

    try:
        import webview

        window = webview.create_window(f"{APP_NAME} v{APP_VERSION}", url, width=1280, height=860, min_size=(1000, 700))
        webview.start()
        server.shutdown()
        return window
    except Exception as exc:
        print(f"pywebview unavailable, opening default browser instead: {exc}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.shutdown()


if __name__ == "__main__":
    main()
