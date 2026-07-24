#!/usr/bin/env python3
# ============================================================
#  NeighborTools – simple server
#  Runs in Docker / Portainer. Data is stored in /data/data.json
# ============================================================
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent
DATA_FILE = DATA_DIR / "data.json"
LOCK = threading.Lock()
MAX_SIZE = 8_000_000  # 8 MB – room for a few images

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def read_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def write_data(d):
    # Atomic write: temp file then replace (safe on power loss)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(
            body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = unquote(self.path.split("?")[0])

        if path == "/api/data":
            with LOCK:
                d = read_data()
            return self._reply(200, {"data": d})

        if path == "/api/health":
            return self._reply(200, {"ok": True, "service": "neighbortools"})

        # Static files from app directory
        if path in ("/", "/index.html"):
            path = "/index.html"
        rel = path.lstrip("/")
        if ".." in rel or rel.startswith("/"):
            return self._reply(404, {"error": "not found"})

        file_path = BASE / rel
        if file_path.is_file() and file_path.resolve().is_relative_to(BASE.resolve()):
            ext = file_path.suffix.lower()
            ctype = MIME.get(ext, "application/octet-stream")
            return self._reply(200, file_path.read_bytes(), ctype)

        self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/data":
            return self._reply(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_SIZE:
                return self._reply(413, {"error": "request too large"})
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            new_data = body["data"]
            based_on = body.get("rev", 0)
            if not isinstance(new_data, dict):
                raise ValueError
        except Exception:
            return self._reply(400, {"error": "invalid request"})

        with LOCK:
            current = read_data()
            current_rev = (current or {}).get("rev", 0)
            if current is not None and based_on != current_rev:
                return self._reply(409, {"error": "stale", "data": current})
            new_data["rev"] = current_rev + 1
            write_data(new_data)
        self._reply(200, {"data": new_data})

    def log_message(self, *args):
        pass


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    print("=" * 52)
    print("  NeighborTools is running!")
    print(f"  Port: {PORT}")
    print(f"  Data: {DATA_FILE}")
    print(f"  Local: http://localhost:{PORT}")
    print(f"  Network: http://{local_ip()}:{PORT}")
    print("  Stop with Ctrl+C")
    print("=" * 52)
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
