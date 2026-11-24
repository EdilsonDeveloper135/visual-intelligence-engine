"""Spike S2 — OCR accuracy/latency for Spanish documents.

Compares PP-OCRv6 small / medium (multilingual) vs PP-OCRv5 latin, with and
without preprocessing, on the synthetic set. Runs in the vie-tests image on the
internal network:
    docker run --rm --network vie_ml -v $PWD/examples/generated:/samples:ro \
      -v $PWD/scripts/spikes:/spikes vie-tests:dev python /spikes/s2_ocr.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

VISION = os.environ.get("VISION_URL", "http://vision:8000")
SAMPLES = os.environ.get("SAMPLES", "factura_ok.png,boleta_ok.png,factura_rotada_7.jpg,factura_foto_perspectiva.jpg,"
                         "factura_desenfocada.jpg,factura_poca_luz.jpg,factura_ruido_jpeg.jpg").split(",")
CONFIGS = [c.split(":") for c in os.environ.get(
    "CONFIGS", "small:multi_v6:1,medium:multi_v6:1,small:latin_v5:1,small:multi_v6:0").split(",")]

ACCENT_WORDS = ["ELECTRÓNICA", "Emisión", "Señor(es)", "Perú", "Descripción"]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def expected_tokens(truth: dict) -> dict[str, str]:
    tok = {
        "issuer_ruc": truth["issuer_ruc"],
        "customer_doc": truth["customer_doc"],
        "serie_numero": truth["serie_numero"],
        "issue_date": "/".join(reversed(truth["issue_date"].split("-"))),
        "total": f"{float(truth['total']):,.2f}",
        "tax": f"{float(truth['tax']):,.2f}",
    }
    for i, it in enumerate(truth["items"]):
        tok[f"item{i}_amount"] = f"{float(it['amount']):,.2f}"
    return tok


def main() -> int:
    client = httpx.Client(base_url=VISION, timeout=300)
    rows = []
    for name in SAMPLES:
        path = Path("/samples") / name
        truth = json.loads(path.with_suffix(".json").read_text())
        data = path.read_bytes()
        expected = expected_tokens(truth)
        for size, variant, pre in CONFIGS:
            t0 = time.time()
            r = client.post("/v1/analyze", content=data, params={
                "ocr": "always", "ocr_size": size, "ocr_variant": variant, "preprocess_image": pre == "1"})
            wall = time.time() - t0
            if r.status_code != 200:
                rows.append({"sample": name, "config": f"{size}/{variant}/pre={pre}", "error": r.text[:200]})
                continue
            res = r.json()
            text = " ".join(ln["text"] for ln in res["ocr"]["lines"])
            flat = norm(text)
            found = {k: norm(v) in flat for k, v in expected.items()}
            accents = {w: w in text for w in ACCENT_WORDS}
            scores = [ln["score"] for ln in res["ocr"]["lines"]]
            row = {
                "sample": name, "config": f"{size}/{variant}/pre={pre}",
                "tokens_found": f"{sum(found.values())}/{len(found)}",
                "missing": [k for k, v in found.items() if not v],
                "accents_ok": f"{sum(accents.values())}/{len(accents)}",
                "lines": len(scores), "mean_score": round(sum(scores) / max(1, len(scores)), 3),
                "ocr_ms": res["timings"].get("ocr_ms"), "total_ms": res["timings"].get("total_ms"),
                "wall_s": round(wall, 2),
                "preprocess": [s["name"] for s in res["preprocessing"]["steps"] if s.get("applied")],
                "quality_flags": res["quality"]["work"]["flags"],
                "codes": [c["text"][:40] for c in res["codes"]],
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    out = Path("/spikes/output")
    out.mkdir(exist_ok=True)
    (out / "s2_ocr.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
