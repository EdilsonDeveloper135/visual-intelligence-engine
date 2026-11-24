"""End-to-end pipeline on the running stack: OCR, model, extraction, validation, memory, export, Q&A."""

from __future__ import annotations

import csv
import io
import json
import time
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from .conftest import SAMPLES, field, truth, upload, wait


def checks(d: dict) -> dict:
    return {c["id"]: c["status"] for c in d["result"]["validation"]["checks"]}


def test_ocr_only_factura_is_fast_and_correct(client):
    t0 = time.time()
    obs = upload(client, "factura_foto_perspectiva.jpg", mode="ocr_only")
    d = wait(client, obs, {"completed"}, 120)
    elapsed = time.time() - t0
    t = truth("factura_foto_perspectiva")
    assert elapsed < 60
    assert d["document_type"] == "factura"
    assert field(d, "issuer_ruc") == t["issuer_ruc"]
    assert Decimal(field(d, "total")) == Decimal(t["total"])
    steps = [s["name"] for s in d["result"]["pages"][0]["preprocessing"] if s["applied"]]
    assert "perspective_correction" in steps
    assert any(a["kind"] == "processed" for a in d["assets"])  # original kept, processed copy stored apart
    assert any(a["kind"] == "original" for a in d["assets"])
    assert d["result"]["metadata"]["vlm_status"] == "not_requested"


@pytest.mark.slow
def test_full_pipeline_with_local_model(client):
    obs = upload(client, "boleta_ok.png")
    first = wait(client, obs, {"ocr_ready", "interpreting", "completed", "partial"}, 120)
    assert first["result"]["text"]["lines"], "OCR result is available before the model finishes"
    d = wait(client, obs, {"completed", "partial"}, 400)
    t = truth("boleta_ok")
    assert d["status"] == "completed", d.get("error")
    meta = d["result"]["metadata"]
    assert meta["model"].startswith("qwen3-vl") and meta["vlm_status"] == "done"
    assert d["result"]["document_type"] == "boleta"
    assert d["result"]["description"]
    assert Decimal(field(d, "total")) == Decimal(t["total"])
    assert field(d, "customer_doc") == t["customer_doc"]
    assert d["validation_status"] in ("valid", "valid_with_warnings")
    # every non-null value is traceable to evidence or flagged for review
    for name, f in d["result"]["fields"].items():
        if f and f["value"] is not None and not f["edited_by_human"]:
            assert f["evidence_ids"] or f["needs_review"] or f["type"] == "currency", name


def test_inconsistent_document_is_flagged(client):
    obs = upload(client, "factura_total_incorrecto.png", mode="ocr_only")
    d = wait(client, obs, {"completed"}, 120)
    assert checks(d)["totals_sum"] == "fail"
    assert d["validation_status"] == "invalid"


def test_prompt_injection_text_is_data(client):
    obs = upload(client, "factura_inyeccion.png", mode="ocr_only")
    d = wait(client, obs, {"completed"}, 120)
    assert checks(d)["prompt_injection"] == "warn"
    assert Decimal(field(d, "total")) == Decimal(truth("factura_inyeccion")["total"])


def test_digital_pdf_uses_embedded_text(client):
    obs = upload(client, "factura_digital.pdf", mode="ocr_only")
    d = wait(client, obs, {"completed"}, 120)
    assert d["result"]["pages"][0]["text_source"] == "pdf_text"
    assert field(d, "issuer_ruc") == truth("factura_digital.pdf")["issuer_ruc"]


@pytest.mark.slow
def test_blank_page_model_does_not_invent(client):
    obs = upload(client, "pagina_en_blanco.png")
    d = wait(client, obs, {"completed", "partial"}, 400)
    assert d["result"]["text"]["lines"] == []
    values = [f["value"] for f in d["result"]["fields"].values() if f]
    assert all(v is None for v in values)
    assert d["result"]["document_type"] in (None, "no_documento", "otro_documento")


def test_duplicate_detection_and_memory_search(client):
    a = upload(client, "nota_credito.png", mode="ocr_only")
    wait(client, a, {"completed"}, 120)
    b = upload(client, "nota_credito.png", mode="ocr_only")
    d = wait(client, b, {"completed"}, 120)
    assert checks(d)["duplicate"] == "warn"
    t = truth("nota_credito")
    res = client.get("/search", params={"q": t["serie_numero"]}).json()
    assert res["total"] >= 2
    res = client.get("/observations", params={"ruc": t["issuer_ruc"][:6]}).json()
    assert res["total"] >= 2
    alerts = client.get("/alerts").json()
    assert any(al["code"] == "duplicate_document" for al in alerts)
    cmp = client.post("/compare", json={"a": a, "b": b}).json()
    assert any("duplicado" in f for f in cmp["findings"])


def test_human_edit_creates_revision_and_revalidates(client):
    obs = upload(client, "factura_total_incorrecto.png", mode="ocr_only")
    d = wait(client, obs, {"completed"}, 120)
    expected = Decimal(d["result"]["fields"]["taxable_amount"]["value"]) + Decimal(d["result"]["fields"]["igv"]["value"])
    r = client.patch(f"/observations/{obs}/fields", json={"changes": [{"field": "total", "value": str(expected)}],
                                                        "reason": "corrección de prueba"})
    assert r.status_code == 200, r.text
    d2 = client.get(f"/observations/{obs}").json()
    f = d2["result"]["fields"]["total"]
    assert f["edited_by_human"] and f["source"] == "human"
    assert checks(d2)["totals_sum"] == "pass"
    hist = client.get(f"/observations/{obs}/history").json()
    assert hist["revisions"][0]["changes"][0]["field"] == "total"
    bad = client.patch(f"/observations/{obs}/fields", json={"changes": [{"field": "issue_date", "value": "no es fecha"}]})
    assert bad.status_code == 422


def test_exports(client):
    obs = upload(client, "factura_ok.png", mode="ocr_only")
    wait(client, obs, {"completed"}, 120)
    t = truth("factura_ok")
    r = client.post("/exports", json={"format": "csv", "observation_ids": [obs]})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0]["issuer_ruc"] == t["issuer_ruc"] and Decimal(rows[0]["total"]) == Decimal(t["total"])
    r = client.post("/exports", json={"format": "xlsx", "observation_ids": [obs]})
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Observaciones", "Items", "Validacion"} <= set(wb.sheetnames)
    assert wb["Items"].max_row == 1 + len(t["items"])
    r = client.post("/exports", json={"format": "json", "observation_ids": [obs]})
    data = json.loads(r.content)
    assert data["observations"][0]["fields"]["issuer_ruc"]["value"] == t["issuer_ruc"]
    r = client.post("/exports", json={"format": "html", "observation_ids": [obs]})
    assert b"<script" not in r.content.lower()


@pytest.mark.slow
def test_visual_question_answering(client):
    obs = upload(client, "factura_ok.png", mode="ocr_only")
    wait(client, obs, {"completed"}, 120)
    r = client.post(f"/observations/{obs}/chat", json={"question": "¿Cuál es el importe total del documento?"})
    assert r.status_code == 202
    msg_id = r.json()["message_id"]
    t0 = time.time()
    while time.time() - t0 < 400:
        msgs = client.get(f"/observations/{obs}/chat").json()
        m = next(x for x in msgs if x["id"] == msg_id)
        if m["status"] in ("done", "error"):
            break
        time.sleep(3)
    assert m["status"] == "done", m["content"]
    assert "128" in m["content"]


def test_models_and_status(client):
    s = client.get("/system/status").json()
    assert s["database"]["status"] == "ok" and s["vision"]["status"] == "ok"
    assert s["llm"]["model_installed"] is True
    models = client.get("/models").json()
    assert models["active"] in [m["name"] for m in models["installed"]]


def test_video_becomes_scene_observations(client):
    r = client.post("/observations", files=[("files", ("video_documentos.mp4",
                                                       (SAMPLES / "video_documentos.mp4").read_bytes(), "video/mp4"))],
                    data={"mode": "ocr_only"})
    assert r.status_code == 202, r.text
    vid = r.json()["observations"][0]["id"]
    d = wait(client, vid, {"completed"}, 180)
    assert d["source"] == "video"
    kf = d["result"]["video"]["keyframes"]
    assert len(kf) == 3
    kids = client.get("/observations", params={"parent_id": vid, "page_size": 10}).json()["items"]
    assert len(kids) == 3
    done = [wait(client, k["id"], {"completed"}, 180) for k in kids]
    types = sorted(x["document_type"] or "-" for x in done)
    assert "factura" in types and "boleta" in types
