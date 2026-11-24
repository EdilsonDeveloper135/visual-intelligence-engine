"""Security behaviour of the public API (through nginx)."""

from __future__ import annotations

import io

import httpx
from PIL import Image

from .conftest import BASE, ORIGIN, new_client, upload


def test_requires_session():
    c = new_client(login=False)
    assert c.get("/observations").status_code == 401
    assert c.get("/system/status").status_code == 401
    assert c.get("/health/live").status_code == 200


def test_wrong_access_key_is_rejected():
    c = new_client(login=False)
    r = c.post("/auth/login", json={"access_key": "no-es-la-clave"})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_key"


def test_foreign_origin_cannot_change_state(client):
    r = client.post("/observations", headers={"Origin": "http://evil.example"},
                    files=[("files", ("a.png", b"\x89PNG\r\n\x1a\n", "image/png"))])
    assert r.status_code == 403
    assert r.json()["code"] == "bad_origin"
    r = client.post("/observations", headers={"Origin": "http://127.0.0.1:9999"},
                    files=[("files", ("a.png", b"\x89PNG\r\n\x1a\n", "image/png"))])
    assert r.status_code == 403  # another local app on a different port


def test_cross_site_fetch_metadata_is_rejected(client):
    r = client.post("/auth/logout", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_unknown_host_is_dropped():
    with httpx.Client(timeout=5) as c:
        try:
            r = c.get(f"{BASE}/", headers={"Host": "attacker.example"})
            assert r.status_code >= 400
        except httpx.RemoteProtocolError:
            pass  # nginx closes the connection (444)


def test_security_headers():
    r = httpx.get(f"{BASE}/", timeout=5)
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "http:" not in csp.replace("ws://", "")  # no external origins allowed
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "camera=(self)" in r.headers["permissions-policy"]


def test_rejects_svg_html_and_unknown_types(client):
    for name, data in [("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
                       ("x.html", b"<html><script>alert(1)</script></html>"),
                       ("x.gif", b"GIF89a\x01\x00\x01\x00"), ("x.exe", b"MZ\x90\x00")]:
        r = client.post("/observations", files=[("files", (name, data, "image/png"))])
        assert r.status_code == 422, (name, r.text)


def test_rejects_extension_mismatch(client):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buf, "PNG")
    r = client.post("/observations", files=[("files", ("factura.pdf", buf.getvalue(), "application/pdf"))])
    assert r.status_code == 422
    assert r.json()["code"] == "extension_mismatch"


def test_rejects_oversized_upload(client):
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * (21 * 1024 * 1024)
    r = client.post("/observations", files=[("files", ("big.png", data, "image/png"))])
    assert r.status_code == 413


def test_decompression_bomb_is_rejected(client):
    # 30000 x 30000 px PNG header (900 MP) — tiny file, enormous image
    buf = io.BytesIO()
    img = Image.new("1", (12000, 12000), 0)
    img.save(buf, "PNG", optimize=True)
    r = client.post("/observations", files=[("files", ("bomba.png", buf.getvalue(), "image/png"))], data={"mode": "ocr_only"})
    assert r.status_code == 202
    obs_id = r.json()["observations"][0]["id"]
    import time

    for _ in range(60):
        d = client.get(f"/observations/{obs_id}").json()
        if d["status"] in ("failed", "completed"):
            break
        time.sleep(1)
    assert d["status"] == "failed"
    assert "píxeles" in (d["error"] or {}).get("message", "") or "límite" in (d["error"] or {}).get("message", "")


def test_filename_path_traversal_is_neutralised(client):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    r = client.post("/observations", files=[("files", ("../../../etc/passwd.png", buf.getvalue(), "image/png"))],
                    data={"mode": "ocr_only"})
    assert r.status_code == 202
    assert r.json()["observations"][0]["filename"] == "passwd.png"


def test_delete_requires_confirmation(client):
    obs = upload(client, "pagina_en_blanco.png", mode="ocr_only")
    assert client.delete(f"/observations/{obs}").status_code == 422  # missing token
    assert client.delete(f"/observations/{obs}", params={"confirm_token": "123.bad"}).status_code == 403
    tok = client.post(f"/observations/{obs}/delete-request").json()["confirm_token"]
    other = upload(client, "pagina_en_blanco.png", mode="ocr_only")
    assert client.delete(f"/observations/{other}", params={"confirm_token": tok}).status_code == 403  # token bound to id
    assert client.delete(f"/observations/{obs}", params={"confirm_token": tok}).status_code == 200
    assert client.get(f"/observations/{obs}").status_code == 404
    assert client.post(f"/observations/{obs}/restore").status_code == 200
    assert client.get(f"/observations/{obs}").status_code == 200


def test_only_allowlisted_actions(client):
    names = {a["name"] for a in client.get("/actions").json()}
    assert "save_record" in names and "run_command" not in names
    r = client.post("/actions/run_command", json={"params": {"cmd": "id"}})
    assert r.status_code == 404
    r = client.post("/actions/search_records", json={"params": {"query": "x", "extra": "no"}})
    assert r.status_code == 422  # strict parameters


def test_strict_input_validation(client):
    r = client.patch("/observations/00000000-0000-0000-0000-000000000000/fields",
                     json={"changes": [{"field": "../x", "value": "1"}]})
    assert r.status_code == 422
    r = client.post("/observations/not-a-uuid/chat", json={"question": "hola"})
    assert r.status_code == 422


def test_audit_log_records_operations(client):
    actions = {a["action"] for a in client.get("/audit", params={"limit": 500}).json()}
    assert {"auth.login", "observation.upload"} <= actions


def test_openapi_documented(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    for p in ("/api/v1/observations", "/api/v1/observations/{obs_id}/chat", "/api/v1/exports", "/api/v1/models",
              "/api/v1/system/status", "/api/v1/events/stream"):
        assert p in paths
    assert httpx.get(f"{BASE}/docs/", timeout=5).status_code == 200


def test_assets_original_is_attachment(client):
    obs = upload(client, "factura_ok.png", mode="ocr_only")
    from .conftest import wait

    d = wait(client, obs, {"completed"}, 120)
    original = next(a for a in d["assets"] if a["kind"] == "original")
    work = next(a for a in d["assets"] if a["kind"] == "work")
    r = client.get(f"/assets/{original['id']}")
    assert r.headers["content-disposition"].startswith("attachment")
    r = client.get(f"/assets/{work['id']}")
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.content[:3] == b"\xff\xd8\xff"  # re-encoded JPEG
    assert b"Exif" not in r.content[:200]  # metadata stripped from derived copies


def _unused():
    return ORIGIN
