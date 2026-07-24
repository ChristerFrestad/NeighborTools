#!/usr/bin/env python3
"""Smoke tests for NeighborTools API. Start server first, then:
   DATA_DIR=/tmp/nt PORT=9876 python3 server.py
   python3 tests/api_test.py http://127.0.0.1:9876
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"


def req(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    code, h = req("GET", "/api/health")
    assert code == 200 and h.get("ok"), h
    print("OK health")

    code, d = req("GET", "/api/data")
    assert code == 200
    print("OK get data")

    if d.get("data") is not None:
        print("SKIP write tests (data already present)")
        print("ALL PASSED (read-only)")
        return

    payload = {
        "rev": 0,
        "data": {
            "v": 1,
            "people": [
                {"id": "p1", "name": "Ada", "address": "A", "color": "#2E52D0"},
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
        },
    }
    code, d = req("POST", "/api/data", payload)
    assert code == 200 and d["data"]["rev"] == 1
    print("OK create")

    data = d["data"]
    data["tools"][0]["holderId"] = "p2"
    code, d2 = req("POST", "/api/data", {"rev": 1, "data": data})
    assert code == 200 and d2["data"]["tools"][0]["holderId"] == "p2"
    print("OK update")

    code, err = req("POST", "/api/data", {"rev": 1, "data": data})
    assert code == 409 and err.get("error") == "stale"
    print("OK conflict")

    for path in ["/", "/manifest.webmanifest", "/sw.js"]:
        urllib.request.urlopen(BASE + path)
    print("OK static")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
