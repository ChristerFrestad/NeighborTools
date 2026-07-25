#!/usr/bin/env python3
"""Smoke tests for the NeighborTools API. Start a server on an EMPTY data dir:
   DATA_DIR=/tmp/nt PORT=9876 python3 server.py
   python3 tests/api_test.py http://127.0.0.1:9876
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"


def req(method, path, body=None, pin=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if pin is not None:
        r.add_header("X-Pin", pin)
    try:
        with urllib.request.urlopen(r) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def sample_data(name="Ada"):
    return {
        "v": 1,
        "people": [
            {"id": "p1", "name": name, "address": "A", "color": "#2E52D0"},
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

    # PIN length is enforced: 4-8 characters
    for bad in ["123", "123456789"]:
        code, err = req("POST", "/api/groups", {"pin": bad, "data": sample_data()})
        assert code == 400 and err.get("error") == "pin length", (bad, code, err)
    print("OK pin length")

    code, d = req("POST", "/api/groups", {"pin": "123456", "data": sample_data()})
    assert code == 201 and d["data"]["rev"] == 1 and d.get("id"), d
    gid = d["id"]
    print("OK create group")

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

    # The group list leaks no names or contents
    code, g = req("GET", "/api/groups")
    assert code == 200 and len(g["groups"]) == 2, g
    assert set(g["groups"][0]) == {"id", "people", "tools", "created"}, g
    print("OK group list has no contents")

    # Unknown group and path traversal
    code, _ = req("GET", "/api/groups/deadbeef99/data", pin="123456")
    assert code == 404, code
    code, _ = req("GET", "/api/groups/..%2F..%2Fserver/data", pin="123456")
    assert code == 404, code
    print("OK unknown group / traversal")

    for path in ["/", "/manifest.webmanifest", "/sw.js"]:
        urllib.request.urlopen(BASE + path)
    print("OK static")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
