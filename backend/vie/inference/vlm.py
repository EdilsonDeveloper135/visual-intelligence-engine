"""Multimodal interpretation call (layer D)."""

from __future__ import annotations

import base64
import io
import json
import logging
import time

from PIL import Image

from ..clients import ollama
from ..core.config import get_settings
from ..doc_schemas.registry import DocSchema, vlm_json_schema
from ..models.result import TextLine
from .prompts import extract_messages

log = logging.getLogger("vie.vlm")


def prepare_image(jpeg: bytes, max_side: int, crop: list[int] | None = None) -> str:
    """Images here were already re-encoded by the vision engine (trusted format)."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    if crop:
        x0, y0, x1, y1 = (max(0, int(v)) for v in crop)
        x1, y1 = min(img.width, x1), min(img.height, y1)
        if x1 - x0 > 8 and y1 - y0 > 8:
            img = img.crop((x0, y0, x1, y1))
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def options(num_predict: int | None = None) -> dict:
    s = get_settings()
    return {"temperature": s.vlm_temperature, "seed": s.vlm_seed, "num_ctx": s.vlm_num_ctx,
            "num_predict": num_predict or s.vlm_num_predict}


async def interpret(model: str, schema: DocSchema, lines: list[TextLine], jpeg: bytes, *, camera: bool = False,
                    doc_type_hint: str | None = None) -> tuple[dict | None, dict]:
    """Returns (parsed_output | None, metadata). Never raises for model-side problems
    (they are reported in metadata so the observation can be marked `partial`)."""
    s = get_settings()
    image_b64 = prepare_image(jpeg, s.vlm_max_side_camera if camera else s.vlm_max_side_document)
    messages, pmeta = extract_messages(schema, lines, image_b64, s.vlm_max_ocr_chars, doc_type_hint)
    body = {"model": model, "messages": messages, "format": vlm_json_schema(schema), "think": False,
            "keep_alive": "30m", "options": options()}
    t0 = time.perf_counter()
    meta: dict = {"model": model, "model_digest": await ollama.digest(model), "prompt_version": pmeta["prompt_version"],
                  "ocr_truncated_in_prompt": pmeta["ocr_truncated"]}
    try:
        data = await ollama.chat(body)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        meta.update(vlm_status="failed", vlm_error=getattr(exc, "message", str(exc))[:300],
                    vlm_ms=round((time.perf_counter() - t0) * 1000))
        return None, meta
    meta["vlm_ms"] = round((time.perf_counter() - t0) * 1000)
    meta["vlm_tokens"] = {"prompt": data.get("prompt_eval_count"), "output": data.get("eval_count"),
                          "load_ms": round((data.get("load_duration") or 0) / 1e6),
                          "prompt_ms": round((data.get("prompt_eval_duration") or 0) / 1e6),
                          "eval_ms": round((data.get("eval_duration") or 0) / 1e6),
                          "done_reason": data.get("done_reason")}
    prompt_tokens = data.get("prompt_eval_count") or 0
    if data.get("done_reason") == "length" or prompt_tokens >= s.vlm_num_ctx:
        meta.update(vlm_status="truncated", vlm_error="La respuesta del modelo se truncó (contexto o longitud).")
        return None, meta
    content = (data.get("message") or {}).get("content") or ""
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except (json.JSONDecodeError, ValueError):
        meta.update(vlm_status="failed", vlm_error="El modelo no devolvió JSON válido.")
        log.warning("invalid JSON from model: %s", content[:200])
        return None, meta
    meta["vlm_status"] = "done"
    return parsed, meta
