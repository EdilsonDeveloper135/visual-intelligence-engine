"""Vision engine unit tests on synthetic fixtures (no network)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from vision.assess import assess, dhash
from vision.codes import read_codes
from vision.media import MediaError, decode_image, pdf_page_count, render_pdf_page, sniff, to_bgr
from vision.ocr import get_engine, reading_order
from vision.preprocess import detect_document_quad, estimate_skew, preprocess
from vision.quality import measure

FIX = Path(__file__).parent / "fixtures"
TRUTH = json.loads((FIX / "factura_ok.json").read_text())


def load(name: str) -> np.ndarray:
    return to_bgr(decode_image((FIX / name).read_bytes()).image)


def test_sniff_by_magic_bytes():
    assert sniff((FIX / "factura_ok.png").read_bytes()) == "image/png"
    assert sniff((FIX / "factura_rotada_7.jpg").read_bytes()) == "image/jpeg"
    assert sniff((FIX / "factura_digital.pdf").read_bytes()) == "application/pdf"
    assert sniff(b"<svg></svg>") is None
    assert sniff(b"\x00\x00\x00\x18ftypheic") == "image/heic"


def test_exif_orientation_applied_and_metadata_stripped():
    img = Image.new("RGB", (200, 100), "white")
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90° CW on display
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    page = decode_image(buf.getvalue())
    assert page.image.size == (100, 200)
    assert any("exif_orientation" in n for n in page.notes)
    assert not page.image.getexif()


def test_invalid_and_oversized_images_rejected():
    with pytest.raises(MediaError):
        decode_image(b"\x89PNG\r\n\x1a\nnot really a png")
    buf = io.BytesIO()
    Image.new("1", (12000, 12000), 0).save(buf, "PNG")  # 144 MP > 120 MP limit
    with pytest.raises(MediaError) as e:
        decode_image(buf.getvalue())
    assert e.value.code == "image_too_large"


def test_quality_flags_blur():
    sharp = measure(load("factura_ok.png"))
    blurry = measure(load("factura_desenfocada.jpg"))
    assert sharp["metrics"]["blur_variance"] > 3 * blurry["metrics"]["blur_variance"]
    assert "not a probability" in sharp["method"]


def test_deskew_estimates_rotation():
    angle = estimate_skew(cv2.cvtColor(load("factura_rotada_7.jpg"), cv2.COLOR_BGR2GRAY))
    assert abs(abs(angle) - 7) < 1.5
    assert abs(estimate_skew(cv2.cvtColor(load("factura_ok.png"), cv2.COLOR_BGR2GRAY))) < 0.5


def test_perspective_document_detection_and_correction():
    img = load("factura_foto_perspectiva.jpg")
    quad, ratio = detect_document_quad(img)
    assert quad is not None and 0.2 < ratio < 0.85
    pre = preprocess(img, [])
    applied = {s["name"] for s in pre.steps if s.get("applied")}
    assert "perspective_correction" in applied
    h, w = pre.image.shape[:2]
    assert 1.25 < h / w < 1.6  # A4-like sheet after warping
    assert img.shape == load("factura_foto_perspectiva.jpg").shape  # original untouched


def test_clean_scan_is_not_modified():
    pre = preprocess(load("factura_ok.png"), [])
    assert not pre.changed


def test_ocr_reads_spanish_text_and_key_values():
    lines, _ = get_engine().run(load("factura_ok.png"))
    text = " ".join(ln.text for ln in lines)
    assert TRUTH["issuer_ruc"] in text.replace(" ", "")
    assert "ELECTRÓNICA" in text and "Emisión" in text
    assert all(0 <= ln.score <= 1 for ln in lines)
    rows = reading_order(lines)
    assert sum(len(r) for r in rows) == len(lines)


def test_qr_decoding():
    codes = read_codes(load("factura_ok.png"))
    assert codes and codes[0]["text"].startswith(TRUTH["issuer_ruc"] + "|01|F001|")


def test_pdf_text_layer_and_render():
    data = (FIX / "factura_digital.pdf").read_bytes()
    assert pdf_page_count(data) == 1
    page = render_pdf_page(data, 0)
    joined = " ".join(t["text"] for t in page.text_layer)
    assert TRUTH["issuer_ruc"] in joined
    assert page.image.width > 1000


def test_assess_is_fast_and_stable():
    img = load("factura_ok.png")
    a, b = assess(img), assess(img.copy())
    assert a["dhash"] == b["dhash"] and len(a["dhash"]) == 16
    assert dhash(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)) == a["dhash"]


def test_api_endpoints():
    from vision.app import app

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        r = client.post("/v1/inspect", content=b"<svg onload=alert(1)></svg>")
        assert r.status_code == 422 and r.json()["code"] == "unsupported_type"
        r = client.post("/v1/analyze", content=(FIX / "factura_ok.png").read_bytes())
        body = r.json()
        assert r.status_code == 200
        assert body["ocr"]["lines"] and body["codes"] and body["images"]["work_jpeg_b64"]
        r = client.post("/v1/assess", content=(FIX / "factura_rotada_7.jpg").read_bytes())
        assert r.status_code == 200 and "dhash" in r.json()


def test_video_keyframes_one_per_scene():
    from vision.video import keyframes

    res = keyframes((FIX / "video_documentos.mp4").read_bytes())
    assert 7.5 < res["duration_s"] < 8.5
    # empty desk, factura, boleta -> 3 distinct scenes, each with a sharp keyframe
    assert len(res["keyframes"]) == 3
    ts = [k["t_s"] for k in res["keyframes"]]
    assert ts == sorted(ts) and ts[0] < 2 and 2 <= ts[1] < 5 and ts[2] >= 5
    lines, _ = get_engine().run(cv2.imdecode(np.frombuffer(res["keyframes"][1]["jpeg"], np.uint8), cv2.IMREAD_COLOR))
    assert "FACTURA" in " ".join(ln.text for ln in lines).upper()


def test_video_rejects_non_video():
    from vision.video import keyframes

    with pytest.raises(MediaError):
        keyframes(b"\x00\x00\x00\x18ftypmp42 not a real video")
