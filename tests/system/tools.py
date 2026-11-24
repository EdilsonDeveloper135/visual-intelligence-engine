"""Small CLI used by the shell test scripts (recovery, persistence, offline).

    python -m system.tools upload factura_ok.png full
    python -m system.tools wait <id> completed,partial 300
    python -m system.tools analyze <id>
    python -m system.tools count
    python -m system.tools show <id>
"""

from __future__ import annotations

import json
import sys
import time

from .conftest import new_client, upload


def main(argv: list[str]) -> int:
    c = new_client()
    cmd = argv[0]
    if cmd == "upload":
        print(upload(c, argv[1], argv[2] if len(argv) > 2 else "full"))
    elif cmd == "wait":
        obs, statuses, timeout = argv[1], set(argv[2].split(",")), float(argv[3])
        t0, last = time.time(), None
        while time.time() - t0 < timeout:
            d = c.get(f"/observations/{obs}").json()
            if d["status"] != last:
                print(f"{time.time() - t0:6.1f}s {d['status']}", file=sys.stderr)
                last = d["status"]
            if d["status"] in statuses:
                print(d["status"])
                return 0
            time.sleep(2)
        print(f"TIMEOUT last={last}")
        return 1
    elif cmd == "analyze":
        r = c.post(f"/observations/{argv[1]}/analyze", json={"stages": "interpret"})
        print(r.status_code)
        return 0 if r.status_code == 202 else 1
    elif cmd == "count":
        print(c.get("/observations", params={"page_size": 1}).json()["total"])
    elif cmd == "show":
        d = c.get(f"/observations/{argv[1]}").json()
        f = d["result"]["fields"]
        print(json.dumps({"status": d["status"], "document_type": d["document_type"],
                          "validation": d["validation_status"], "model": d["model_name"],
                          "vlm_status": d["result"]["metadata"].get("vlm_status"),
                          "vlm_error": d["result"]["metadata"].get("vlm_error"),
                          "issuer_ruc": (f.get("issuer_ruc") or {}).get("value"),
                          "total": (f.get("total") or {}).get("value"),
                          "assets": len(d["assets"])}, ensure_ascii=False))
        for a in d["assets"]:
            r = c.get(f"/assets/{a['id']}")
            assert r.status_code == 200, a
    else:
        print(f"unknown command {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
