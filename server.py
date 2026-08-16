#!/usr/bin/env python3
# ============================================================
#  NeighborTools – simple server
#  Runs in Docker / Portainer.
#  Each tool-sharing group is stored as /data/groups/<id>.json
#  The PIN is the key to a group and is stored hashed (PBKDF2).
# ============================================================
import base64
import hashlib
import hmac
import json
import math
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent))
BASE = Path(__file__).resolve().parent
GROUPS_DIR = DATA_DIR / "groups"
IMG_DIR = DATA_DIR / "img"
PUSH_DIR = DATA_DIR / "push"
SALT_FILE = DATA_DIR / "pin-salt"
REQUESTS_FILE = DATA_DIR / "requests.json"
INVITES_FILE = DATA_DIR / "invites.json"
GRANTS_FILE = DATA_DIR / "grants.json"
RECOVER_FILE = DATA_DIR / "recover.json"
MAIL_QUEUE_FILE = DATA_DIR / "mail-queue.json"
VAPID_FILE = DATA_DIR / "vapid.json"
POSTNR_FILE = BASE / "postnummer.json"
LOCK = threading.Lock()
MAX_SIZE = 12_000_000  # JSON payload; photos live as files under /data/img
MAX_GROUPS = 200
MIN_PIN = 4
MAX_PIN = 32
PBKDF2_ROUNDS = 100_000
GID_RE = re.compile(r"^[a-f0-9]{6,32}$")
TID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,24}$")
TOKEN_RE = re.compile(r"^[a-f0-9]{16,80}$")
# v1 photo cap. The layout scales toward 2000; raise MAX_IMAGES when ready.
MAX_IMAGES = 500
MAX_IMAGE_BYTES = 450_000
MAX_PUSH_SUBS = 80
INVITE_TTL_DAYS = 30
RECOVER_TTL_SEC = 2 * 3600
RECOVER_PER_EMAIL_HOUR = 3
GRANT_TTL_DAYS = 400

# Neighborhood requests ("etterlysninger" across groups on the same server)
REQUEST_TTL_DAYS = 30      # open requests vanish after this
MAX_REQUESTS = 500         # server-wide cap on the shared request board
MAX_REQ_TEXT = 280
MAX_REQ_NOTE = 500
MAX_REQ_NAME = 60
MAX_REQ_TOOL = 80          # optional "here is the tool I can lend" label
MAX_RESPONSES = 20         # per request
RADII_KM = (5, 10, 25, 50)  # choices for "how far will you travel?"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
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


# ---------- Neighborhood requests ----------
# All groups on one server share /data/requests.json. A request carries only
# what the requester chose to share (first name, postal code, text); matching
# uses postal-code centroids bundled in postnummer.json, so no external
# service is ever called. Groups only see requests within the requester's
# own travel radius, and never learn which group a request came from.
_postnr_cache = None


def postnr_table():
    global _postnr_cache
    if _postnr_cache is None:
        try:
            _postnr_cache = json.loads(POSTNR_FILE.read_text(encoding="utf-8"))
        except Exception:
            _postnr_cache = {}
    return _postnr_cache


def postnr_info(nr):
    """[lat, lon, place] for a Norwegian postal code, or None."""
    return postnr_table().get(str(nr or "").strip())


def haversine_km(lat1, lon1, lat2, lon2):
    rad = math.radians
    a = (math.sin(rad(lat2 - lat1) / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2))
         * math.sin(rad(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def read_requests():
    try:
        r = json.loads(REQUESTS_FILE.read_text(encoding="utf-8"))
        return r if isinstance(r, list) else []
    except Exception:
        return []


def write_requests(lst):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REQUESTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(lst, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, REQUESTS_FILE)


def prune_requests(lst):
    cutoff = time.time() - REQUEST_TTL_DAYS * 86400
    out = []
    for r in lst:
        try:
            ts = datetime.fromisoformat(r["created"]).timestamp()
        except Exception:
            continue
        if ts >= cutoff:
            out.append(r)
    return out


def load_requests_pruned():
    """Call under LOCK. Reads the board and persists any expiry pruning."""
    lst = read_requests()
    pruned = prune_requests(lst)
    if len(pruned) != len(lst):
        write_requests(pruned)
    return pruned


def group_coords(g):
    """Coordinates for every member postal code in a group."""
    out = []
    for p in (g.get("data") or {}).get("people") or []:
        info = postnr_info(p.get("postnr"))
        if info:
            out.append(info)
    return out


def request_public(r, dist_km):
    """What another group is allowed to see: never the origin group id."""
    return {
        "id": r["id"], "text": r["text"], "name": r["name"],
        "postnr": r["postnr"], "place": r["place"],
        "radiusKm": r["radiusKm"], "distKm": dist_km,
        "created": r["created"], "responses": len(r.get("responses") or []),
    }


def request_own(r):
    out = {k: r[k] for k in ("id", "text", "name", "postnr", "place",
                             "radiusKm", "created")}
    out["responses"] = r.get("responses") or []
    return out


def group_summary(g):
    d = g.get("data") or {}
    return {
        "id": g.get("id"),
        "people": len(d.get("people") or []),
        "tools": len(d.get("tools") or []),
        "created": g.get("created"),
    }


def read_json_list(path):
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
        return r if isinstance(r, list) else []
    except Exception:
        return []


def write_json(path, obj):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def token_hash(token):
    return hashlib.sha256((get_salt() + ":" + str(token)).encode("utf-8")).hexdigest()


def ensure_admin(data):
    """First person is admin. Legacy groups with nobody flagged get person 0."""
    people = data.get("people") if isinstance(data, dict) else None
    if not people:
        return data
    if not any(p.get("admin") for p in people if isinstance(p, dict)):
        people[0]["admin"] = True
    return data


def admin_count(data):
    return sum(1 for p in (data.get("people") or []) if isinstance(p, dict) and p.get("admin"))


# ---------- Images (files, not JSON) ----------
def _sniff_ext(raw):
    if raw[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def image_path(gid, tid):
    d = IMG_DIR / gid
    if not d.is_dir():
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = d / (tid + ext)
        if p.is_file():
            return p
    return None


def _write_tool_image(gid, tid, raw):
    d = IMG_DIR / gid
    d.mkdir(parents=True, exist_ok=True)
    ext = _sniff_ext(raw)
    dest = d / (tid + ext)
    for other in (".jpg", ".jpeg", ".png", ".webp"):
        p = d / (tid + other)
        if p != dest and p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    dest.write_bytes(raw)
    return dest


def extract_tool_images(gid, data):
    """Turn data-URL photos into files. tool.img becomes the token 'file'."""
    tools = data.get("tools") if isinstance(data, dict) else None
    if not tools:
        return data
    img_dir = IMG_DIR / gid
    existing = set()
    if img_dir.is_dir():
        existing = {p.stem for p in img_dir.iterdir() if p.is_file()}
    count = len(existing)
    keep = set()
    for t in tools:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        if not TID_RE.match(tid):
            t.pop("img", None)
            continue
        img = t.get("img")
        if isinstance(img, str) and img.startswith("data:image"):
            comma = img.find(",")
            if comma < 0:
                if tid in existing:
                    t["img"] = "file"
                    keep.add(tid)
                else:
                    t.pop("img", None)
                continue
            try:
                raw = base64.b64decode(img[comma + 1 :], validate=False)
            except Exception:
                raw = b""
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                # Keep the file already on disk rather than deleting it
                # because a too-big or broken replacement arrived.
                if tid in existing:
                    t["img"] = "file"
                    keep.add(tid)
                else:
                    t.pop("img", None)
                continue
            if tid not in existing and count >= MAX_IMAGES:
                t.pop("img", None)
                continue
            _write_tool_image(gid, tid, raw)
            t["img"] = "file"
            if tid not in existing:
                count += 1
                existing.add(tid)
            keep.add(tid)
        elif img == "file" or (isinstance(img, str) and img.startswith("file")):
            t["img"] = "file"
            keep.add(tid)
        else:
            t.pop("img", None)
    if img_dir.is_dir():
        for p in list(img_dir.iterdir()):
            if p.is_file() and p.stem not in keep:
                try:
                    p.unlink()
                except Exception:
                    pass
    return data


def img_cookie_token(gid):
    return hmac.new(get_salt().encode("utf-8"),
                    ("img:" + gid).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


# ---------- Grants (invite join without knowing the PIN) ----------
def issue_grant(gid):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    grants = read_json_list(GRANTS_FILE)
    grants.append({"h": token_hash(token), "gid": gid, "created": now_iso()})
    write_json(GRANTS_FILE, grants[-500:])
    return token


def grant_ok(gid, token):
    if not token or not TOKEN_RE.match(token):
        return False
    want = token_hash(token)
    cutoff = time.time() - GRANT_TTL_DAYS * 86400
    for row in read_json_list(GRANTS_FILE):
        if row.get("gid") != gid:
            continue
        if not hmac.compare_digest(str(row.get("h") or ""), want):
            continue
        try:
            if datetime.fromisoformat(row["created"]).timestamp() < cutoff:
                return False
        except Exception:
            pass
        return True
    return False


# ---------- Invites ----------
def load_invites():
    now = time.time()
    out = []
    for row in read_json_list(INVITES_FILE):
        try:
            ts = datetime.fromisoformat(row["created"]).timestamp()
        except Exception:
            continue
        if now - ts > INVITE_TTL_DAYS * 86400:
            continue
        if int(row.get("uses") or 0) >= int(row.get("maxUses") or 50):
            continue
        out.append(row)
    return out


def find_invite(token):
    if not token or not TOKEN_RE.match(token):
        return None
    want = token_hash(token)
    for row in load_invites():
        stored = str(row.get("h") or "")
        if stored and hmac.compare_digest(stored, want):
            return row
        # Unreleased plaintext rows from the looped draft
        if row.get("token") and hmac.compare_digest(str(row.get("token") or ""), token):
            return row
    return None


# ---------- PIN recovery + mail queue (Resend later) ----------
def mail_configured():
    return bool(os.environ.get("RESEND_API_KEY"))


def find_admin_groups_by_email(email):
    want = (email or "").strip().lower()
    if not want or not EMAIL_RE.match(want):
        return []
    out = []
    for g in all_groups():
        for p in (g.get("data") or {}).get("people") or []:
            if not isinstance(p, dict) or not p.get("admin"):
                continue
            if str(p.get("email") or "").strip().lower() == want:
                out.append(g)
                break
    return out


def recover_rate_ok(email):
    want = (email or "").strip().lower()
    hour_ago = time.time() - 3600
    n = 0
    for row in read_json_list(RECOVER_FILE):
        if str(row.get("email") or "").lower() != want:
            continue
        try:
            if datetime.fromisoformat(row["created"]).timestamp() >= hour_ago:
                n += 1
        except Exception:
            pass
    return n < RECOVER_PER_EMAIL_HOUR


def try_resend(item):
    key = os.environ.get("RESEND_API_KEY") or ""
    if not key:
        return False, "not configured"
    from_addr = os.environ.get("MAIL_FROM", "NeighborTools <noreply@localhost>")
    payload = json.dumps({
        "from": from_addr,
        "to": [item["to"]],
        "subject": item["subject"],
        "html": item.get("html") or "",
        "text": item.get("text") or "",
    }).encode("utf-8")
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as res:
            if 200 <= res.status < 300:
                return True, None
            return False, "http " + str(res.status)
    except Exception as e:
        return False, str(e)[:200]


def queue_mail(to, subject, html, text):
    q = read_json_list(MAIL_QUEUE_FILE)
    item = {
        "id": uuid.uuid4().hex[:12],
        "to": to,
        "subject": subject,
        "html": html,
        "text": text,
        "created": now_iso(),
        "sent": False,
        "error": None,
    }
    ok, err = try_resend(item)
    item["sent"] = bool(ok)
    item["error"] = None if ok else err
    q.append(item)
    write_json(MAIL_QUEUE_FILE, q[-200:])
    return item


# ---------- Web Push ----------
_vapid_cache = None


def vapid_keys():
    """Load or create VAPID keys. None when pywebpush/cryptography is missing."""
    global _vapid_cache
    if _vapid_cache is not None:
        return _vapid_cache or None
    if VAPID_FILE.exists():
        try:
            _vapid_cache = json.loads(VAPID_FILE.read_text(encoding="utf-8"))
            if _vapid_cache.get("publicKey") and _vapid_cache.get("privateKey"):
                return _vapid_cache
        except Exception:
            pass
    try:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid
    except Exception:
        _vapid_cache = {}
        return None
    try:
        v = Vapid()
        v.generate_keys()
        priv = v.private_pem()
        if isinstance(priv, bytes):
            priv = priv.decode("utf-8")
        pub_raw = v.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        pub = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode("ascii")
        keys = {
            "publicKey": pub,
            "privateKey": priv,
            "created": now_iso(),
        }
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        VAPID_FILE.write_text(json.dumps(keys), encoding="utf-8")
        try:
            os.chmod(VAPID_FILE, 0o600)
        except Exception:
            pass
        _vapid_cache = keys
        return keys
    except Exception:
        _vapid_cache = {}
        return None


def push_file(gid):
    return PUSH_DIR / (gid + ".json")


def load_push_subs(gid):
    try:
        r = json.loads(push_file(gid).read_text(encoding="utf-8"))
        return r if isinstance(r, list) else []
    except Exception:
        return []


def save_push_subs(gid, rows):
    PUSH_DIR.mkdir(parents=True, exist_ok=True)
    write_json(push_file(gid), rows)


def send_push(gid, person_ids, title, body, url="/"):
    keys = vapid_keys()
    if not keys:
        return 0
    try:
        from pywebpush import webpush
    except Exception:
        return 0
    want = set(person_ids or [])
    if not want:
        return 0
    claims = {"sub": os.environ.get("VAPID_MAILTO", "mailto:admin@localhost")}
    payload = json.dumps({"title": title, "body": body, "url": url},
                         ensure_ascii=False)
    rows = load_push_subs(gid)
    kept = []
    sent = 0
    for row in rows:
        if row.get("personId") not in want:
            kept.append(row)
            continue
        sub = {
            "endpoint": row.get("endpoint"),
            "keys": row.get("keys") or {},
        }
        if not sub["endpoint"] or not sub["keys"].get("p256dh") or not sub["keys"].get("auth"):
            continue
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=keys["privateKey"],
                vapid_claims=claims,
            )
            sent += 1
            kept.append(row)
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code not in (404, 410):
                kept.append(row)
    if len(kept) != len(rows):
        save_push_subs(gid, kept)
    return sent


def _tool_map(data):
    return {t.get("id"): t for t in (data.get("tools") or []) if isinstance(t, dict) and t.get("id")}


def notify_from_diff(gid, old, new):
    """Push on loan / queue / due change. Best-effort; never blocks the save."""
    try:
        old_t = _tool_map(old or {})
        new_t = _tool_map(new or {})
        for tid, nt in new_t.items():
            ot = old_t.get(tid) or {}
            name = nt.get("name") or "…"
            if nt.get("holderId") != ot.get("holderId"):
                targets = []
                for pid in (nt.get("ownerId"), ot.get("holderId"), ot.get("ownerId")):
                    if pid and pid != nt.get("holderId") and pid != "__ext":
                        targets.append(pid)
                if targets:
                    send_push(gid, targets, "NeighborTools",
                              name + " ble lånt ut / was lent out", "/")
            oq = [q.get("personId") for q in (ot.get("queue") or []) if isinstance(q, dict)]
            nq = [q.get("personId") for q in (nt.get("queue") or []) if isinstance(q, dict)]
            added = [p for p in nq if p not in oq]
            if added and nt.get("ownerId"):
                send_push(gid, [nt["ownerId"]], "NeighborTools",
                          "Kø på " + name + " / Queue for " + name, "/")
            if (nt.get("due") or "") != (ot.get("due") or ""):
                targets = [p for p in (nt.get("holderId"), nt.get("ownerId"))
                           if p and p != "__ext"]
                if targets:
                    due = nt.get("due") or "ubestemt tid / no end date"
                    send_push(gid, targets, "NeighborTools",
                              name + " · " + due, "/")
        maybe_due_pushes(gid, new)
    except Exception:
        pass


def _due_state_path(gid):
    return PUSH_DIR / (gid + "-due.json")


def maybe_due_pushes(gid, data):
    """Remind the holder the day before / on the due date, once per day.

    State lives next to the push subscriptions so a reminder never rewrites
    the group JSON or bumps rev.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        state = json.loads(_due_state_path(gid).read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}
    dirty = False
    for t in data.get("tools") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        due = t.get("due")
        holder = t.get("holderId")
        if not tid or not due or not holder or holder == t.get("ownerId") or holder == "__ext":
            continue
        try:
            days = (datetime.fromisoformat(due).date()
                    - datetime.now(timezone.utc).date()).days
        except Exception:
            continue
        if days > 1 or days < -3:
            continue
        stamp = str(due) + "|" + today
        if state.get(tid) == stamp:
            continue
        name = t.get("name") or "Verktøy / tool"
        body = (name + " skal leveres i dag / due today" if days <= 0
                else name + " skal leveres i morgen / due tomorrow")
        send_push(gid, [holder], "NeighborTools", body, "/")
        state[tid] = stamp
        dirty = True
    if dirty:
        PUSH_DIR.mkdir(parents=True, exist_ok=True)
        write_json(_due_state_path(gid), state)


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(
            body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for cookie in getattr(self, "_cookies", None) or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        # HEAD must send the same headers as GET, but no body. Messenger and
        # other crawlers probe with HEAD and treat 501 as "this URL does not exist".
        if getattr(self, "_omit_body", False):
            return
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _public_origin(self):
        return (os.environ.get("PUBLIC_URL") or "https://neighbor-tools.com").rstrip("/")

    def _serve_index(self, invite_token=""):
        html = (BASE / "index.html").read_text(encoding="utf-8")
        origin = self._public_origin()
        html = html.replace("https://neighbor-tools.com", origin)
        if invite_token:
            html = html.replace(
                'property="og:title" content="NeighborTools"',
                'property="og:title" content="Du er invitert til en verktøygruppe"',
            )
            html = html.replace(
                'property="og:description" content="Shared tools with your neighbors – no login needed."',
                'property="og:description" content="Åpne lenken for å bli med i NeighborTools – uten PIN."',
            )
            html = html.replace(
                'property="og:url" content="%s/"' % origin,
                'property="og:url" content="%s/i/%s"' % (origin, invite_token),
            )
            html = html.replace(
                'rel="canonical" href="%s/"' % origin,
                'rel="canonical" href="%s/i/%s"' % (origin, invite_token),
            )
        return self._reply(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _add_cookie(self, cookie):
        self._cookies = list(getattr(self, "_cookies", None) or [])
        self._cookies.append(cookie)

    def _cookie_flags(self):
        flags = "; HttpOnly; SameSite=Lax; Max-Age=2592000"
        proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if proto == "https":
            flags += "; Secure"
        return flags

    def _set_img_cookie(self, gid):
        token = img_cookie_token(gid)
        self._add_cookie(
            "nt_img_%s=%s; Path=/api/groups/%s/img%s"
            % (gid, token, gid, self._cookie_flags())
        )

    def _img_cookie_ok(self, gid):
        raw = self.headers.get("Cookie") or ""
        want = "nt_img_%s=" % gid
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith(want):
                got = part[len(want):].strip()
                return hmac.compare_digest(got, img_cookie_token(gid))
        return False

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_SIZE:
            raise ValueError("size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _auth(self, gid):
        """Returns (group, error). The group is None when access is denied.

        Accepts the group PIN (X-Pin) or a device grant from an invite join
        (X-Grant). A successful auth also plants an HttpOnly cookie so <img>
        tags can load photos without a custom header.
        """
        g = read_group(gid)
        if g is None:
            return None, (404, {"error": "no such group"})
        # The client URI-encodes the PIN so special characters survive the header
        pin = unquote(str(self.headers.get("X-Pin", ""))).strip()
        stored = str(g.get("pinHash") or "")
        if stored and pin and hmac.compare_digest(stored, hash_pin(pin)):
            self._set_img_cookie(gid)
            return g, None
        grant = unquote(str(self.headers.get("X-Grant", ""))).strip()
        if grant and grant_ok(gid, grant):
            self._set_img_cookie(gid)
            return g, None
        time.sleep(0.4)  # slow down PIN / grant guessing
        return None, (401, {"error": "wrong pin"})

    # ---------- GET ----------
    def do_GET(self):
        path = unquote(self.path.split("?")[0])

        if path == "/api/health":
            return self._reply(200, {
                "ok": True,
                "service": "neighbortools",
                "push": bool(vapid_keys()),
                "mail": mail_configured(),
            })

        if path == "/api/push/vapid":
            keys = vapid_keys()
            return self._reply(200, {
                "publicKey": (keys or {}).get("publicKey"),
                "available": bool(keys),
            })

        if path == "/api/recover/status":
            return self._reply(200, {
                "mailConfigured": mail_configured(),
                "provider": "resend" if mail_configured() else "none",
            })

        m = re.match(r"^/api/invite/([a-f0-9]{16,80})$", path)
        if m:
            return self.invite_info(m.group(1))

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
                data = g.get("data") or {}
                ensure_admin(data)
                gid = g["id"]
            maybe_due_pushes(gid, data)
            return self._reply(200, {"data": data})

        m = re.match(r"^/api/groups/([^/]+)/img/([A-Za-z0-9_-]{1,40})$", path)
        if m:
            return self.serve_image(m.group(1), m.group(2))

        m = re.match(r"^/api/groups/([^/]+)/requests$", path)
        if m:
            return self.list_requests(m.group(1))

        if path == "/robots.txt":
            return self._reply(
                200,
                b"User-agent: *\nAllow: /\n",
                "text/plain; charset=utf-8",
            )

        qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        invite_m = re.match(r"^/i/([a-f0-9]{16,80})$", path)
        invite_q = str((qs.get("invite") or [""])[0])
        invite_token = invite_m.group(1) if invite_m else invite_q
        invite_token = re.sub(r"[^a-f0-9]", "", invite_token)
        if len(invite_token) < 16:
            invite_token = ""

        # App shell + invite short links. Unknown non-API paths fall through
        # to the SPA so crawlers never see a JSON 404 on a shared URL.
        if path in ("/", "/index.html") or invite_m:
            return self._serve_index(invite_token)

        rel = path.lstrip("/")
        if ".." in rel or rel.startswith("/"):
            return self._reply(404, {"error": "not found"})

        file_path = BASE / rel
        if file_path.is_file() and file_path.resolve().is_relative_to(BASE.resolve()):
            ext = file_path.suffix.lower()
            ctype = MIME.get(ext, "application/octet-stream")
            return self._reply(200, file_path.read_bytes(), ctype)

        if not path.startswith("/api/"):
            return self._serve_index(invite_token)

        self._reply(404, {"error": "not found"})

    def do_HEAD(self):
        self._omit_body = True
        return self.do_GET()

    # ---------- POST ----------
    def do_POST(self):
        path = unquote(self.path.split("?")[0])

        if path == "/api/groups":
            return self.create_group()
        if path == "/api/groups/open":
            return self.open_by_pin()
        if path == "/api/recover":
            return self.recover_request()
        if path == "/api/recover/reset":
            return self.recover_reset()

        m = re.match(r"^/api/invite/([a-f0-9]{16,80})/join$", path)
        if m:
            return self.invite_join(m.group(1))

        m = re.match(r"^/api/groups/([^/]+)/data$", path)
        if m:
            return self.save_data(m.group(1))

        m = re.match(r"^/api/groups/([^/]+)/invite$", path)
        if m:
            return self.create_invite(m.group(1))

        m = re.match(r"^/api/groups/([^/]+)/push/subscribe$", path)
        if m:
            return self.push_subscribe(m.group(1))

        m = re.match(r"^/api/groups/([^/]+)/push/unsubscribe$", path)
        if m:
            return self.push_unsubscribe(m.group(1))

        m = re.match(r"^/api/groups/([^/]+)/requests$", path)
        if m:
            return self.create_request(m.group(1))

        m = re.match(r"^/api/groups/([^/]+)/requests/([a-f0-9]{6,32})/respond$", path)
        if m:
            return self.respond_request(m.group(1), m.group(2))

        m = re.match(r"^/api/groups/([^/]+)/requests/([a-f0-9]{6,32})/close$", path)
        if m:
            return self.close_request(m.group(1), m.group(2))

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
            ensure_admin(data)
            g = {
                "id": uuid.uuid4().hex[:12],
                "pinHash": hash_pin(pin),
                "created": now_iso(),
                "data": data,
            }
            extract_tool_images(g["id"], data)
            write_group(g)
        self._set_img_cookie(g["id"])
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
        data = g.get("data") or {}
        ensure_admin(data)
        self._set_img_cookie(g["id"])
        self._reply(200, {"id": g["id"], "data": data})

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
            ensure_admin(new_data)
            extract_tool_images(gid, new_data)
            g["data"] = new_data
            write_group(g)
            old = current
        notify_from_diff(gid, old, new_data)
        self._reply(200, {"data": new_data})

    # ---------- Neighborhood requests ----------
    def list_requests(self, gid):
        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            lst = load_requests_pruned()
            mine = [request_own(r) for r in lst if r.get("gid") == g["id"]]
            nearby = []
            settings = (g.get("data") or {}).get("settings") or {}
            if settings.get("neighborhood"):
                coords = group_coords(g)
                for r in lst:
                    if r.get("gid") == g["id"] or not coords:
                        continue
                    d = min(haversine_km(r["lat"], r["lon"], c[0], c[1])
                            for c in coords)
                    if d <= r["radiusKm"]:
                        nearby.append(request_public(r, max(1, round(d))))
        return self._reply(200, {"mine": mine, "nearby": nearby})

    def create_request(self, gid):
        try:
            body = self._body()
            text = str(body.get("text", "")).strip()
            name = str(body.get("name", "")).strip()
            postnr = str(body.get("postnr", "")).strip()
            radius = int(body.get("radiusKm", 0))
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        if not (0 < len(text) <= MAX_REQ_TEXT) or not (0 < len(name) <= MAX_REQ_NAME):
            return self._reply(400, {"error": "invalid request"})
        if radius not in RADII_KM:
            return self._reply(400, {"error": "invalid radius"})
        info = postnr_info(postnr)
        if not info:
            return self._reply(400, {"error": "unknown postnr"})

        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            lst = load_requests_pruned()
            if len(lst) >= MAX_REQUESTS:
                return self._reply(507, {"error": "too many requests"})
            r = {
                "id": uuid.uuid4().hex[:12], "gid": g["id"],
                "text": text, "name": name,
                "postnr": postnr, "place": info[2],
                "lat": info[0], "lon": info[1],
                "radiusKm": radius, "created": now_iso(), "responses": [],
            }
            lst.append(r)
            write_requests(lst)
        return self._reply(201, {"request": request_own(r)})

    def respond_request(self, gid, rid):
        try:
            body = self._body()
            note = str(body.get("note", "")).strip()
            name = str(body.get("name", "")).strip()
            postnr = str(body.get("postnr", "")).strip()
            tool = str(body.get("tool", "")).strip()[:MAX_REQ_TOOL]
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        if not (0 < len(note) <= MAX_REQ_NOTE) or not (0 < len(name) <= MAX_REQ_NAME):
            return self._reply(400, {"error": "invalid request"})
        info = postnr_info(postnr)
        if not info:
            return self._reply(400, {"error": "unknown postnr"})

        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            lst = load_requests_pruned()
            r = next((x for x in lst if x["id"] == rid), None)
            if r is None:
                return self._reply(404, {"error": "no such request"})
            if r.get("gid") == g["id"]:
                return self._reply(400, {"error": "own request"})
            if len(r.get("responses") or []) >= MAX_RESPONSES:
                return self._reply(409, {"error": "full"})
            d = haversine_km(r["lat"], r["lon"], info[0], info[1])
            if d > r["radiusKm"]:
                return self._reply(403, {"error": "out of range"})
            r.setdefault("responses", []).append({
                "id": uuid.uuid4().hex[:12], "name": name,
                "postnr": postnr, "place": info[2],
                "distKm": max(1, round(d)), "note": note, "tool": tool,
                "created": now_iso(),
            })
            write_requests(lst)
        return self._reply(201, {"ok": True})

    def close_request(self, gid, rid):
        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            lst = load_requests_pruned()
            r = next((x for x in lst if x["id"] == rid), None)
            if r is None:
                return self._reply(404, {"error": "no such request"})
            if r.get("gid") != g["id"]:
                return self._reply(403, {"error": "not yours"})
            write_requests([x for x in lst if x["id"] != rid])
        return self._reply(200, {"ok": True})

    # ---------- Images / invite / push / PIN recovery ----------
    def serve_image(self, gid, tid):
        if not GID_RE.match(gid or "") or not TID_RE.match(tid or ""):
            return self._reply(404, {"error": "not found"})
        with LOCK:
            g = read_group(gid)
            if g is None:
                return self._reply(404, {"error": "not found"})
            allowed = False
            pin = unquote(str(self.headers.get("X-Pin", ""))).strip()
            stored = str(g.get("pinHash") or "")
            if stored and pin and hmac.compare_digest(stored, hash_pin(pin)):
                allowed = True
            grant = unquote(str(self.headers.get("X-Grant", ""))).strip()
            if not allowed and grant and grant_ok(gid, grant):
                allowed = True
            if not allowed and self._img_cookie_ok(gid):
                allowed = True
            if not allowed:
                time.sleep(0.2)
                return self._reply(401, {"error": "wrong pin"})
            p = image_path(gid, tid)
        if p is None:
            return self._reply(404, {"error": "not found"})
        ext = p.suffix.lower()
        return self._reply(200, p.read_bytes(), MIME.get(ext, "application/octet-stream"))

    def create_invite(self, gid):
        try:
            body = self._body() if int(self.headers.get("Content-Length", 0) or 0) else {}
        except Exception:
            body = {}
        try:
            max_uses = int((body or {}).get("maxUses") or 50)
        except Exception:
            max_uses = 50
        max_uses = max(1, min(max_uses, 200))
        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            token = uuid.uuid4().hex
            rows = load_invites()
            rows.append({
                "h": token_hash(token), "gid": g["id"], "created": now_iso(),
                "uses": 0, "maxUses": max_uses,
            })
            write_json(INVITES_FILE, rows[-200:])
        return self._reply(201, {"token": token, "maxUses": max_uses})

    def invite_info(self, token):
        with LOCK:
            row = find_invite(token)
            if row is None:
                return self._reply(404, {"error": "no such invite"})
            g = read_group(row.get("gid"))
        if g is None:
            return self._reply(404, {"error": "no such invite"})
        d = g.get("data") or {}
        return self._reply(200, {
            "ok": True,
            "people": len(d.get("people") or []),
            "tools": len(d.get("tools") or []),
        })

    def invite_join(self, token):
        try:
            body = self._body()
            name = str(body.get("name", "")).strip()[:60]
            address = str(body.get("address", "")).strip()[:80]
            postnr = str(body.get("postnr", "")).strip()[:8]
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        if not name:
            return self._reply(400, {"error": "invalid request"})
        with LOCK:
            row = find_invite(token)
            if row is None:
                return self._reply(404, {"error": "no such invite"})
            g = read_group(row.get("gid"))
            if g is None:
                return self._reply(404, {"error": "no such invite"})
            data = g.get("data") or {}
            people = data.setdefault("people", [])
            person = {
                "id": uuid.uuid4().hex[:10],
                "name": name,
                "address": address,
                "postnr": postnr,
                "color": "#B85C2A",
            }
            people.append(person)
            data["rev"] = int(data.get("rev") or 0) + 1
            log = data.setdefault("log", [])
            log.append({
                "id": uuid.uuid4().hex[:10], "t": "pers",
                "name": name, "date": now_iso(),
            })
            ensure_admin(data)
            g["data"] = data
            write_group(g)
            rows = read_json_list(INVITES_FILE)
            want = token_hash(token)
            for r in rows:
                stored = str(r.get("h") or "")
                if stored and hmac.compare_digest(stored, want):
                    r["uses"] = int(r.get("uses") or 0) + 1
                elif r.get("token") and hmac.compare_digest(str(r.get("token") or ""), token):
                    r["uses"] = int(r.get("uses") or 0) + 1
            write_json(INVITES_FILE, rows)
            grant = issue_grant(g["id"])
        self._set_img_cookie(g["id"])
        return self._reply(201, {
            "id": g["id"], "data": data, "grant": grant, "personId": person["id"],
        })

    def push_subscribe(self, gid):
        try:
            body = self._body()
            person_id = str(body.get("personId") or "").strip()
            sub = body.get("subscription") or {}
            endpoint = str(sub.get("endpoint") or "").strip()
            keys = sub.get("keys") or {}
            p256dh = str(keys.get("p256dh") or "").strip()
            auth = str(keys.get("auth") or "").strip()
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        if not person_id or not endpoint.startswith("https://") or not p256dh or not auth:
            return self._reply(400, {"error": "invalid request"})
        if len(endpoint) > 800 or len(p256dh) > 200 or len(auth) > 80:
            return self._reply(400, {"error": "invalid request"})
        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            people = (g.get("data") or {}).get("people") or []
            if not any(isinstance(p, dict) and p.get("id") == person_id for p in people):
                return self._reply(400, {"error": "unknown person"})
            rows = load_push_subs(gid)
            rows = [r for r in rows if r.get("endpoint") != endpoint]
            rows.append({
                "personId": person_id,
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
                "created": now_iso(),
            })
            save_push_subs(gid, rows[-MAX_PUSH_SUBS:])
        return self._reply(200, {"ok": True, "push": bool(vapid_keys())})

    def push_unsubscribe(self, gid):
        try:
            body = self._body()
            endpoint = str((body.get("endpoint") or
                            (body.get("subscription") or {}).get("endpoint") or "")).strip()
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        with LOCK:
            g, err = self._auth(gid)
            if err:
                return self._reply(*err)
            if endpoint:
                rows = [r for r in load_push_subs(gid) if r.get("endpoint") != endpoint]
                save_push_subs(gid, rows)
        return self._reply(200, {"ok": True})

    def recover_request(self):
        try:
            email = str(self._body().get("email") or "").strip().lower()
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        # Always the same answer – do not leak whether the address exists.
        if not EMAIL_RE.match(email):
            time.sleep(0.3)
            return self._reply(200, {"ok": True, "queued": False})
        with LOCK:
            if not recover_rate_ok(email):
                return self._reply(200, {"ok": True, "queued": True})
            groups = find_admin_groups_by_email(email)
            rows = read_json_list(RECOVER_FILE)
            origin = (os.environ.get("PUBLIC_URL") or "").rstrip("/")
            links = []
            for g in groups:
                raw = uuid.uuid4().hex + uuid.uuid4().hex[:8]
                rows.append({
                    "h": token_hash(raw),
                    "gid": g["id"],
                    "email": email,
                    "created": now_iso(),
                    "used": False,
                })
                path = "/?reset=" + raw
                links.append((origin + path) if origin else path)
            if groups:
                write_json(RECOVER_FILE, rows[-200:])
                text = (
                    "Noen ba om å tilbakestille PIN for NeighborTools.\n\n"
                    "Åpne en av lenkene (gyldig i 2 timer) og velg en ny PIN:\n"
                    + "\n".join(links) +
                    "\n\nHvis du ikke ba om dette, kan du se bort fra e-posten."
                )
                html = (
                    "<p>Noen ba om å tilbakestille PIN for NeighborTools.</p>"
                    "<p>Åpne lenken (gyldig i 2 timer) og velg en ny PIN:</p><ul>"
                    + "".join("<li><a href=\"%s\">%s</a></li>" % (esc_html(u), esc_html(u))
                              for u in links)
                    + "</ul><p>Hvis du ikke ba om dette, kan du se bort fra e-posten.</p>"
                )
                queue_mail(email, "Tilbakestill PIN – NeighborTools", html, text)
        time.sleep(0.3)
        # Always "queued" for a well-formed address so the API cannot be
        # used to probe whether an admin email exists.
        return self._reply(200, {"ok": True, "queued": True})

    def recover_reset(self):
        try:
            body = self._body()
            token = str(body.get("token") or "").strip()
            pin = str(body.get("pin") or "").strip()
        except Exception:
            return self._reply(400, {"error": "invalid request"})
        if not TOKEN_RE.match(token) or not (MIN_PIN <= len(pin) <= MAX_PIN):
            return self._reply(400, {"error": "invalid request"})
        with LOCK:
            rows = read_json_list(RECOVER_FILE)
            want = token_hash(token)
            row = None
            for r in rows:
                if hmac.compare_digest(str(r.get("h") or ""), want):
                    row = r
                    break
            if row is None or row.get("used"):
                time.sleep(0.4)
                return self._reply(404, {"error": "no such token"})
            try:
                age = time.time() - datetime.fromisoformat(row["created"]).timestamp()
            except Exception:
                age = RECOVER_TTL_SEC + 1
            if age > RECOVER_TTL_SEC:
                return self._reply(410, {"error": "expired"})
            if find_group_by_pin(pin) is not None:
                return self._reply(409, {"error": "pin in use"})
            g = read_group(row.get("gid"))
            if g is None:
                return self._reply(404, {"error": "no such group"})
            g["pinHash"] = hash_pin(pin)
            write_group(g)
            row["used"] = True
            write_json(RECOVER_FILE, rows)
        return self._reply(200, {"ok": True, "id": g["id"]})

    def log_message(self, *args):
        pass


def esc_html(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


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
