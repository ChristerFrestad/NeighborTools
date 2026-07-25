#!/usr/bin/env python3
# ============================================================
#  NeighborTools – simple server
#  Runs in Docker / Portainer.
#  Each tool-sharing group is stored as /data/groups/<id>.json
#  The PIN is the key to a group and is stored hashed (PBKDF2).
# ============================================================
import hashlib
import hmac
import json
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent
GROUPS_DIR = DATA_DIR / "groups"
SALT_FILE = DATA_DIR / "pin-salt"
LOCK = threading.Lock()
MAX_SIZE = 8_000_000  # 8 MB – room for a few images
MAX_GROUPS = 200
MIN_PIN = 4
MAX_PIN = 32
PBKDF2_ROUNDS = 100_000
GID_RE = re.compile(r"^[a-f0-9]{6,32}$")

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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- PIN hashing ----------
# One salt per installation (not per group): identical PINs then hash alike,
# which is exactly what the "PIN must be unique" rule needs, and it lets us
# look a group up from a PIN with a single hash computation.
_salt_cache = None
_hash_cache = {}


def get_salt():
    global _salt_cache
    if _salt_cache is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if SALT_FILE.exists():
            _salt_cache = SALT_FILE.read_text(encoding="utf-8").strip()
        else:
            _salt_cache = uuid.uuid4().hex + uuid.uuid4().hex
            SALT_FILE.write_text(_salt_cache, encoding="utf-8")
    return _salt_cache


def hash_pin(pin):
    pin = str(pin)
    cached = _hash_cache.get(pin)
    if cached:
        return cached
    h = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"),
        bytes.fromhex(get_salt()), PBKDF2_ROUNDS,
    ).hex()
    if len(_hash_cache) > 500:
        _hash_cache.clear()
    _hash_cache[pin] = h
    return h


# ---------- Group storage ----------
def group_file(gid):
    return GROUPS_DIR / (gid + ".json")


def read_group(gid):
    if not GID_RE.match(gid or ""):
        return None
    p = group_file(gid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_group(g):
    # Atomic write: temp file then replace (safe on power loss)
    GROUPS_DIR.mkdir(parents=True, exist_ok=True)
    p = group_file(g["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def all_groups():
    if not GROUPS_DIR.exists():
        return []
    out = []
    for f in sorted(GROUPS_DIR.glob("*.json")):
        try:
            g = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(g, dict) and g.get("id"):
                out.append(g)
        except Exception:
            pass
    return out


def find_group_by_pin(pin):
    want = hash_pin(pin)
    for g in all_groups():
        stored = g.get("pinHash")
        if stored and hmac.compare_digest(str(stored), want):
            return g
    return None


def group_summary(g):
    d = g.get("data") or {}
    return {
        "id": g.get("id"),
        "people": len(d.get("people") or []),
        "tools": len(d.get("tools") or []),
        "created": g.get("created"),
    }


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

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_SIZE:
            raise ValueError("size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _auth(self, gid):
        """Returns (group, error). The group is None when access is denied."""
        g = read_group(gid)
        if g is None:
            return None, (404, {"error": "no such group"})
        # The client URI-encodes the PIN so special characters survive the header
        pin = unquote(str(self.headers.get("X-Pin", ""))).strip()
        stored = str(g.get("pinHash") or "")
        if not stored or not pin or not hmac.compare_digest(stored, hash_pin(pin)):
            time.sleep(0.4)  # slow down PIN guessing
            return None, (401, {"error": "wrong pin"})
        return g, None

    # ---------- GET ----------
    def do_GET(self):
        path = unquote(self.path.split("?")[0])

        if path == "/api/health":
            return self._reply(200, {"ok": True, "service": "neighbortools"})

        if path == "/api/groups":
            # Ids and counts only – never names or tools, since this is unauthenticated
            with LOCK:
                groups = [group_summary(g) for g in all_groups()]
            return self._reply(200, {"groups": groups})

        m = re.match(r"^/api/groups/([^/]+)/data$", path)
        if m:
            with LOCK:
                g, err = self._auth(m.group(1))
                if err:
                    return self._reply(*err)
                return self._reply(200, {"data": g.get("data")})

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

    # ---------- POST ----------
    def do_POST(self):
        path = unquote(self.path.split("?")[0])

        if path == "/api/groups":
            return self.create_group()
        if path == "/api/groups/open":
            return self.open_by_pin()

        m = re.match(r"^/api/groups/([^/]+)/data$", path)
        if m:
            return self.save_data(m.group(1))

        self._reply(404, {"error": "not found"})

    def create_group(self):
        try:
            body = self._body()
            data = body["data"]
            pin = str(body.get("pin", "")).strip()
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            return self._reply(400, {"error": "invalid request"})

        if not (MIN_PIN <= len(pin) <= MAX_PIN):
            return self._reply(400, {"error": "pin length",
                                     "minLength": MIN_PIN, "maxLength": MAX_PIN})

        with LOCK:
            if len(all_groups()) >= MAX_GROUPS:
                return self._reply(507, {"error": "too many groups"})
            # A PIN identifies a group, so it can only belong to one.
            if find_group_by_pin(pin) is not None:
                return self._reply(409, {"error": "pin in use"})
            data["rev"] = 1
            g = {
                "id": uuid.uuid4().hex[:12],
                "pinHash": hash_pin(pin),
                "created": now_iso(),
                "data": data,
            }
            write_group(g)
        self._reply(201, {"id": g["id"], "data": g["data"]})

    def open_by_pin(self):
        try:
            pin = str(self._body().get("pin", "")).strip()
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        if not pin:
            return self._reply(400, {"error": "missing pin"})

        with LOCK:
            g = find_group_by_pin(pin)
        if g is None:
            time.sleep(0.4)  # slow down PIN guessing
            return self._reply(404, {"error": "no such group"})
        self._reply(200, {"id": g["id"], "data": g.get("data")})

    def save_data(self, gid):
        try:
            body = self._body()
            new_data = body["data"]
            based_on = body.get("rev", 0)
            if not isinstance(new_data, dict):
                raise ValueError
        except Exception:
            return self._reply(400, {"error": "invalid request"})

        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            current = g.get("data") or {}
            current_rev = current.get("rev", 0)
            if current and based_on != current_rev:
                return self._reply(409, {"error": "stale", "data": current})
            new_data["rev"] = current_rev + 1
            g["data"] = new_data
            write_group(g)
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
    print(f"  Data: {GROUPS_DIR}")
    print(f"  Groups: {len(all_groups())}")
    print(f"  Local: http://localhost:{PORT}")
    print(f"  Network: http://{local_ip()}:{PORT}")
    print("  Stop with Ctrl+C")
    print("=" * 52)
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
