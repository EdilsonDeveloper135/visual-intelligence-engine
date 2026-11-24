"""Spike S1 — feasibility of the multimodal model on CPU inside the memory limit.

Runs inside the vie-tests image attached to the internal `vie_ml` network:
    docker run --rm --network vie_ml -v $PWD/examples/generated:/samples:ro \
      -v $PWD/scripts/spikes:/spikes vie-tests:dev python /spikes/s1_vlm.py

Measures, per image and resolution: load / prompt-eval / eval durations, token
counts, JSON validity against the schema and a few extracted values vs ground truth.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("VIE_VLM_MODEL", "qwen3-vl:2b-instruct")
NUM_CTX = int(os.environ.get("NUM_CTX", "4096"))
SIDES = [int(s) for s in os.environ.get("SIDES", "768,1024,1280").split(",")]
SAMPLES = os.environ.get(
    "SAMPLES", "factura_ok.png,boleta_ok.png,factura_foto_perspectiva.jpg,escena_sin_documento.jpg,pagina_en_blanco.png"
).split(",")

SCHEMA = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean"},
        "document_type": {"type": "string", "enum": [
            "factura", "boleta", "nota_credito", "guia_remision", "recibo", "orden_compra",
            "cotizacion", "comprobante_pago", "otro_documento", "no_documento"]},
        "description": {"type": "string"},
        "issuer_name": {"type": ["string", "null"]},
        "issuer_ruc": {"type": ["string", "null"]},
        "serie_numero": {"type": ["string", "null"]},
        "issue_date": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "subtotal": {"type": ["string", "null"]},
        "tax": {"type": ["string", "null"]},
        "total": {"type": ["string", "null"]},
        "items": {"type": "array", "maxItems": 15, "items": {
            "type": "object",
            "properties": {"description": {"type": "string"}, "quantity": {"type": ["string", "null"]},
                           "unit_price": {"type": ["string", "null"]}, "amount": {"type": ["string", "null"]}},
            "required": ["description", "quantity", "unit_price", "amount"]}},
        "unreadable": {"type": "array", "maxItems": 10, "items": {"type": "string"}},
    },
    "required": ["is_document", "document_type", "description", "issuer_name", "issuer_ruc", "serie_numero",
                 "issue_date", "currency", "subtotal", "tax", "total", "items", "unreadable"],
}

SYSTEM = (
    "Eres un sistema de extracción de datos de documentos. Responde SOLO con JSON válido según el esquema. "
    "Copia los valores exactamente como aparecen en la imagen. Si un dato no es visible o no es legible, usa null. "
    "No inventes datos. Si la imagen no es un documento, usa is_document=false, document_type='no_documento' "
    "y deja todos los campos del documento en null."
)
USER = (
    "Analiza la imagen. Campos: is_document, document_type, description (1 frase en español), issuer_name, "
    "issuer_ruc, serie_numero, issue_date, currency (PEN/USD), subtotal, tax, total, items "
    "(description, quantity, unit_price, amount), unreadable."
)


def encode(path: Path, max_side: int) -> tuple[str, tuple[int, int]]:
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), img.size


def main() -> int:
    client = httpx.Client(base_url=OLLAMA, timeout=600)
    print(f"model={MODEL} num_ctx={NUM_CTX} version={client.get('/api/version').json()}", flush=True)
    results = []
    for name in SAMPLES:
        path = Path("/samples") / name
        truth_path = path.with_suffix(".json")
        truth = json.loads(truth_path.read_text()) if truth_path.exists() else {}
        for side in SIDES:
            b64, size = encode(path, side)
            body = {
                "model": MODEL, "stream": False, "think": False, "format": SCHEMA, "keep_alive": "30m",
                "options": {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX, "num_predict": 768},
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": USER, "images": [b64]}],
            }
            t0 = time.time()
            try:
                r = client.post("/api/chat", json=body)
                r.raise_for_status()
                data = r.json()
            except Exception as exc:  # noqa: BLE001 - spike: record every failure
                results.append({"sample": name, "side": side, "error": str(exc)[:300]})
                print(f"{name} @{side}: ERROR {exc}", flush=True)
                continue
            wall = time.time() - t0
            content = data["message"]["content"]
            try:
                parsed = json.loads(content)
                valid = True
            except json.JSONDecodeError:
                parsed, valid = {}, False
            row = {
                "sample": name, "side": side, "image_px": size, "wall_s": round(wall, 1),
                "load_s": round(data.get("load_duration", 0) / 1e9, 1),
                "prompt_tokens": data.get("prompt_eval_count"),
                "prompt_s": round(data.get("prompt_eval_duration", 0) / 1e9, 1),
                "eval_tokens": data.get("eval_count"),
                "eval_s": round(data.get("eval_duration", 0) / 1e9, 1),
                "json_valid": valid,
                "truncated": (data.get("prompt_eval_count") or 0) >= NUM_CTX,
                "doc_type": parsed.get("document_type"),
                "ruc_ok": truth.get("issuer_ruc") is not None and parsed.get("issuer_ruc") == truth.get("issuer_ruc"),
                "total_ok": truth.get("total") is not None and (parsed.get("total") or "").replace("S/", "").replace(",", "").strip() == truth.get("total"),
                "serie_ok": truth.get("serie_numero") is not None and parsed.get("serie_numero") == truth.get("serie_numero"),
                "non_null_fields": sum(1 for k in ("issuer_name", "issuer_ruc", "serie_numero", "issue_date", "total") if parsed.get(k)),
                "extracted": {k: parsed.get(k) for k in ("issuer_ruc", "serie_numero", "issue_date", "total", "description")},
            }
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    out = Path("/spikes/output")
    out.mkdir(exist_ok=True)
    (out / f"s1_{MODEL.replace(':', '_')}_ctx{NUM_CTX}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
