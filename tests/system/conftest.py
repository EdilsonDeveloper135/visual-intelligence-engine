"""System tests against the running stack (through nginx, exactly like the browser)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
ORIGIN = BASE
SAMPLES = Path(os.environ.get("SAMPLES_DIR", "/samples"))
KEY = os.environ.get("VIE_ACCESS_KEY", "")


def new_client(login: bool = True) -> httpx.Client:
    c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Origin": ORIGIN}, timeout=120)
    if login:
        r = c.post("/auth/login", json={"access_key": KEY})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    return new_client()


def truth(name: str) -> dict:
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def upload(c: httpx.Client, filename: str, mode: str = "full") -> str:
    path = SAMPLES / filename
    mime = "application/pdf" if filename.endswith(".pdf") else "image/png" if filename.endswith(".png") else "image/jpeg"
    r = c.post("/observations", files=[("files", (filename, path.read_bytes(), mime))], data={"mode": mode})
    assert r.status_code == 202, r.text
    return r.json()["observations"][0]["id"]


def wait(c: httpx.Client, obs_id: str, statuses: set[str], timeout: float = 300) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        d = c.get(f"/observations/{obs_id}").json()
        last = d
        if d["status"] in statuses:
            return d
        if d["status"] == "failed":
            raise AssertionError(f"observation failed: {d.get('error')}")
        time.sleep(1.5)
    raise AssertionError(f"timeout waiting for {statuses}; last status={last and last['status']}")


def field(d: dict, name: str):
    f = d["result"]["fields"].get(name)
    return None if f is None else f["value"]
