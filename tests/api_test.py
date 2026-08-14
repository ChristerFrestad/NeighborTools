#!/usr/bin/env python3
"""Smoke tests for the NeighborTools API. Start a server on an EMPTY data dir:
   DATA_DIR=/tmp/nt PORT=9876 python3 server.py
   DATA_DIR=/tmp/nt python3 tests/api_test.py http://127.0.0.1:9876
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"


def req(method, path, body=None, pin=None, grant=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if pin is not None:
        r.add_header("X-Pin", pin)
    if grant is not None:
        r.add_header("X-Grant", grant)
    try:
        with urllib.request.urlopen(r) as res:
            payload = res.read()
            if raw:
                return res.status, payload
            return res.status, json.loads(payload.decode())
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload.decode())
        except Exception:
            return e.code, payload


def sample_data(name="Ada"):
    return {
        "v": 1,
        "people": [
            {"id": "p1", "name": name, "address": "A", "color": "#B85C2A"},
            {"id": "p2", "name": "Bo", "address": "B", "color": "#256B43"},
        ],
        "tools": [
            {
                "id": "t1",
                "name": "Drill",
                "type": "Drill & drive",
                "ownerId": "p1",
                "holderId": "p1",
                "notes": "",
                "since": "2026-07-01T00:00:00Z",
                "created": "2026-07-01T00:00:00Z",
            }
        ],
        "log": [],
    }


def main():
    code, h = req("GET", "/api/health")
    assert code == 200 and h.get("ok"), h
    print("OK health")

    code, g = req("GET", "/api/groups")
    assert code == 200 and isinstance(g.get("groups"), list), g
    if g["groups"]:
        print("SKIP write tests (groups already present – use an empty DATA_DIR)")
        print("ALL PASSED (read-only)")
        return
    print("OK empty group list")

    # PIN length is enforced: 4-32 characters
    for bad in ["123", "x" * 33]:
        code, err = req("POST", "/api/groups", {"pin": bad, "data": sample_data()})
        assert code == 400 and err.get("error") == "pin length", (bad, code, err)
    print("OK pin length")

    code, d = req("POST", "/api/groups", {"pin": "123456", "data": sample_data()})
    assert code == 201 and d["data"]["rev"] == 1 and d.get("id"), d
    assert d["data"]["people"][0].get("admin") is True, d
    assert not d["data"]["people"][1].get("admin"), d
    gid = d["id"]
    print("OK create group")
    print("OK first person is admin")

    # A PIN belongs to exactly one group
    code, err = req("POST", "/api/groups", {"pin": "123456", "data": sample_data("Cyd")})
    assert code == 409 and err.get("error") == "pin in use", (code, err)
    print("OK duplicate pin rejected")

    # Reading requires the PIN
    code, _ = req("GET", f"/api/groups/{gid}/data")
    assert code == 401, code
    code, _ = req("GET", f"/api/groups/{gid}/data", pin="000000")
    assert code == 401, code
    code, d = req("GET", f"/api/groups/{gid}/data", pin="123456")
    assert code == 200 and d["data"]["people"][0]["name"] == "Ada", d
    print("OK pin required to read")

    # Opening by PIN finds the group
    code, o = req("POST", "/api/groups/open", {"pin": "123456"})
    assert code == 200 and o["id"] == gid, o
    code, _ = req("POST", "/api/groups/open", {"pin": "654321"})
    assert code == 404, code
    print("OK open by pin")

    # Writing: needs the PIN, and rev must match
    data = d["data"]
    data["tools"][0]["holderId"] = "p2"
    code, _ = req("POST", f"/api/groups/{gid}/data", {"rev": 1, "data": data})
    assert code == 401, code
    code, d2 = req("POST", f"/api/groups/{gid}/data", {"rev": 1, "data": data}, pin="123456")
    assert code == 200 and d2["data"]["tools"][0]["holderId"] == "p2", d2
    print("OK update")

    code, err = req("POST", f"/api/groups/{gid}/data", {"rev": 1, "data": data}, pin="123456")
    assert code == 409 and err.get("error") == "stale", err
    print("OK conflict")

    # A second group with its own PIN is fully separate
    code, d3 = req("POST", "/api/groups", {"pin": "4321", "data": sample_data("Cyd")})
    assert code == 201 and d3["id"] != gid, d3
    gid2 = d3["id"]
    code, _ = req("GET", f"/api/groups/{gid2}/data", pin="123456")
    assert code == 401, "group 2 must not open with group 1's PIN"
    code, d4 = req("GET", f"/api/groups/{gid2}/data", pin="4321")
    assert code == 200 and d4["data"]["people"][0]["name"] == "Cyd", d4
    print("OK groups are separate")

    # PINs may contain letters and special characters; the client URI-encodes
    # the X-Pin header, so the test does the same.
    fancy = "Wain/a@y"
    code, d5 = req("POST", "/api/groups", {"pin": fancy, "data": sample_data("Eli")})
    assert code == 201 and d5.get("id"), d5
    code, o2 = req("POST", "/api/groups/open", {"pin": fancy})
    assert code == 200 and o2["id"] == d5["id"], o2
    code, d6 = req("GET", f"/api/groups/{d5['id']}/data",
                   pin=urllib.parse.quote(fancy, safe=""))
    assert code == 200 and d6["data"]["people"][0]["name"] == "Eli", d6
    print("OK special-character pin")

    # The group list leaks no names or contents
    code, g = req("GET", "/api/groups")
    assert code == 200 and len(g["groups"]) == 3, g
    assert set(g["groups"][0]) == {"id", "people", "tools", "created"}, g
    print("OK group list has no contents")

    # Unknown group and path traversal
    code, _ = req("GET", "/api/groups/deadbeef99/data", pin="123456")
    assert code == 404, code
    code, _ = req("GET", "/api/groups/..%2F..%2Fserver/data", pin="123456")
    assert code == 404, code
    print("OK unknown group / traversal")

    # ---- Neighborhood requests -------------------------------------------
    # Group 1 (Kristiansand) asks within 10 km; group 2 (also Kristiansand)
    # opts in and replies; a group that has not opted in sees nothing.

    # Validation first
    code, err = req("POST", f"/api/groups/{gid}/requests",
                    {"text": "Tile cutter", "name": "Ada", "postnr": "9999",
                     "radiusKm": 10}, pin="123456")
    assert code == 400 and err.get("error") == "unknown postnr", (code, err)
    code, err = req("POST", f"/api/groups/{gid}/requests",
                    {"text": "Tile cutter", "name": "Ada", "postnr": "4630",
                     "radiusKm": 7}, pin="123456")
    assert code == 400 and err.get("error") == "invalid radius", (code, err)
    code, _ = req("POST", f"/api/groups/{gid}/requests",
                  {"text": "x", "name": "Ada", "postnr": "4630", "radiusKm": 10})
    assert code == 401, code
    print("OK request validation")

    code, cr = req("POST", f"/api/groups/{gid}/requests",
                   {"text": "Tile cutter for the weekend", "name": "Ada",
                    "postnr": "4630", "radiusKm": 10}, pin="123456")
    assert code == 201 and cr["request"]["id"], cr
    assert "lat" not in cr["request"] and "gid" not in cr["request"], cr
    rid = cr["request"]["id"]
    print("OK create request")

    # Group 2 has not opted in: sees nothing
    code, lst = req("GET", f"/api/groups/{gid2}/requests", pin="4321")
    assert code == 200 and lst["nearby"] == [] and lst["mine"] == [], lst
    print("OK neighborhood is opt-in")

    # Group 2 opts in with a member postal code ~2 km away
    code, d4 = req("GET", f"/api/groups/{gid2}/data", pin="4321")
    g2 = d4["data"]
    g2["people"][0]["postnr"] = "4633"
    g2["settings"] = {"neighborhood": True}
    code, _ = req("POST", f"/api/groups/{gid2}/data",
                  {"rev": g2["rev"], "data": g2}, pin="4321")
    assert code == 200, code
    code, lst = req("GET", f"/api/groups/{gid2}/requests", pin="4321")
    assert code == 200 and len(lst["nearby"]) == 1, lst
    seen = lst["nearby"][0]
    assert seen["id"] == rid and "gid" not in seen and "lat" not in seen, seen
    assert seen["distKm"] <= 10 and seen["place"], seen
    print("OK nearby matching within radius")

    # Replying: own group is rejected, out-of-range is rejected
    code, err = req("POST", f"/api/groups/{gid}/requests/{rid}/respond",
                    {"note": "I have one", "name": "Bo", "postnr": "4630"},
                    pin="123456")
    assert code == 400 and err.get("error") == "own request", (code, err)
    code, err = req("POST", f"/api/groups/{gid2}/requests/{rid}/respond",
                    {"note": "Too far away", "name": "Cyd", "postnr": "0150"},
                    pin="4321")
    assert code == 403 and err.get("error") == "out of range", (code, err)
    code, _ = req("POST", f"/api/groups/{gid2}/requests/{rid}/respond",
                  {"note": "I have one – call 900 00 000", "name": "Cyd",
                   "postnr": "4633", "tool": "Bosch tile cutter"}, pin="4321")
    assert code == 201, code
    print("OK reply")

    # The requester's group sees the reply, including the offered tool
    code, lst = req("GET", f"/api/groups/{gid}/requests", pin="123456")
    assert code == 200 and len(lst["mine"]) == 1, lst
    resp = lst["mine"][0]["responses"]
    assert len(resp) == 1 and resp[0]["name"] == "Cyd" and resp[0]["distKm"] <= 10, resp
    assert resp[0]["tool"] == "Bosch tile cutter", resp
    print("OK reply visible to requester")

    # Closing: only the origin group may close
    code, _ = req("POST", f"/api/groups/{gid2}/requests/{rid}/close", pin="4321")
    assert code == 403, code
    code, _ = req("POST", f"/api/groups/{gid}/requests/{rid}/close", pin="123456")
    assert code == 200, code
    code, lst = req("GET", f"/api/groups/{gid2}/requests", pin="4321")
    assert code == 200 and lst["nearby"] == [], lst
    print("OK close request")

    for path in ["/", "/manifest.webmanifest", "/sw.js"]:
        urllib.request.urlopen(BASE + path)
    print("OK static")

    # ---- Push / invite / recover / images --------------------------------
    code, vapid = req("GET", "/api/push/vapid")
    assert code == 200 and "available" in vapid and "publicKey" in vapid, vapid
    print("OK vapid endpoint")

    code, inv = req("POST", f"/api/groups/{gid}/invite", {"maxUses": 5}, pin="123456")
    assert code == 201 and inv.get("token"), inv
    token = inv["token"]
    code, info = req("GET", f"/api/invite/{token}")
    assert code == 200 and info.get("ok") and info.get("people") >= 2, info
    code, joined = req("POST", f"/api/invite/{token}/join", {"name": "New neighbour"})
    assert code == 201 and joined.get("grant") and joined["id"] == gid, joined
    grant = joined["grant"]
    code, _ = req("GET", f"/api/groups/{gid}/data")
    assert code == 401, code
    code, dg = req("GET", f"/api/groups/{gid}/data", grant=grant)
    assert code == 200 and any(p["name"] == "New neighbour" for p in dg["data"]["people"]), dg
    print("OK invite + grant auth")

    code, rec = req("POST", "/api/recover", {"email": "nobody@example.com"})
    assert code == 200 and rec.get("ok"), rec
    code, rec2 = req("POST", "/api/recover/reset",
                     {"token": "ab" * 16, "pin": "999999"})
    assert code == 404, rec2
    print("OK recover stubs")

    # Grant from group 1 cannot open group 2
    code, _ = req("GET", f"/api/groups/{gid2}/data", grant=grant)
    assert code == 401, "invite grant must not open another group"
    print("OK grant is scoped to its group")

    # Last remaining admin cannot be stripped
    code, cur = req("GET", f"/api/groups/{gid}/data", pin="123456")
    data = cur["data"]
    for p in data["people"]:
        p["admin"] = False
    code, saved = req("POST", f"/api/groups/{gid}/data",
                      {"rev": data["rev"], "data": data}, pin="123456")
    assert code == 200 and saved["data"]["people"][0].get("admin") is True, saved
    print("OK last admin is restored")

    # Invite tokens are stored hashed
    data_dir = Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else None
    if data_dir and (data_dir / "invites.json").is_file():
        stored = json.loads((data_dir / "invites.json").read_text(encoding="utf-8"))
        blob = json.dumps(stored)
        assert token not in blob, stored
        print("OK invite token is hashed on disk")

    # Recover happy path when DATA_DIR is shared with the test process
    pin_now = "123456"
    code, cur = req("GET", f"/api/groups/{gid}/data", pin=pin_now)
    data = cur["data"]
    data["people"][0]["email"] = "ada@example.com"
    code, saved = req("POST", f"/api/groups/{gid}/data",
                      {"rev": data["rev"], "data": data}, pin=pin_now)
    assert code == 200, saved
    code, rec3 = req("POST", "/api/recover", {"email": "ada@example.com"})
    assert code == 200 and rec3.get("ok"), rec3
    if data_dir and (data_dir / "mail-queue.json").is_file():
        queue = json.loads((data_dir / "mail-queue.json").read_text(encoding="utf-8"))
        text = (queue[-1].get("text") or "") if queue else ""
        m = re.search(r"[?&]reset=([a-f0-9]{16,80})", text)
        assert m, queue
        reset_token = m.group(1)
        code, reset = req("POST", "/api/recover/reset",
                          {"token": reset_token, "pin": "654321"})
        assert code == 200 and reset.get("ok"), reset
        code, _ = req("POST", "/api/groups/open", {"pin": "123456"})
        assert code == 404, "old PIN must stop working"
        code, opened = req("POST", "/api/groups/open", {"pin": "654321"})
        assert code == 200 and opened["id"] == gid, opened
        pin_now = "654321"
        print("OK recover resets the PIN")
    else:
        print("SKIP recover happy path (set DATA_DIR to enable)")

    # 1×1 JPEG – extracted to a file and served only with the PIN
    tiny = base64.b64encode(bytes.fromhex(
        "ffd8ffdb0043000302020202030202020303030304060404040404080606"
        "050609080a0a090809090a0c0f0c0a0b0e0b09090d110d0e0f101011100a"
        "0c12131210130f101010ffc9000b080001000101011100ffcc0006001010"
        "05ffda0008010100003f00d2cf20ffd9"
    )).decode("ascii")
    code, cur = req("GET", f"/api/groups/{gid}/data", pin=pin_now)
    assert code == 200, cur
    data = cur["data"]
    data["tools"][0]["img"] = "data:image/jpeg;base64," + tiny
    code, saved = req("POST", f"/api/groups/{gid}/data",
                      {"rev": data["rev"], "data": data}, pin=pin_now)
    assert code == 200 and saved["data"]["tools"][0].get("img") == "file", saved
    tid = saved["data"]["tools"][0]["id"]
    code, raw = req("GET", f"/api/groups/{gid}/img/{tid}", pin=pin_now, raw=True)
    assert code == 200 and raw[:2] == b"\xff\xd8", (code, raw[:20])
    code, _ = req("GET", f"/api/groups/{gid}/img/{tid}", raw=True)
    assert code == 401, code
    # A broken replacement must not delete the file already on disk
    data = saved["data"]
    data["tools"][0]["img"] = "data:image/jpeg;base64,&&&&"
    code, kept = req("POST", f"/api/groups/{gid}/data",
                     {"rev": data["rev"], "data": data}, pin=pin_now)
    assert code == 200 and kept["data"]["tools"][0].get("img") == "file", kept
    code, raw2 = req("GET", f"/api/groups/{gid}/img/{tid}", pin=pin_now, raw=True)
    assert code == 200 and raw2[:2] == b"\xff\xd8", (code, raw2[:20])
    print("OK image files")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
