"""Job handlers executed by the worker.

process   (fast lane): vision analysis + OCR + rules + QR + validation -> status `ocr_ready`
interpret (vlm lane) : multimodal model + merge + grounding + validation  -> `completed` / `partial`
chat      (vlm lane) : visual question answering with streaming
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from PIL import Image
from sqlalchemy import select

from ..clients import ollama
from ..clients import vision
from ..core import runtime
from ..core.config import get_settings
from ..core.errors import ServiceUnavailable, Unprocessable
from ..db.models import Alert, Asset, ChatMessage, Job, Observation
from ..db.session import session_scope
from ..doc_schemas.registry import DOCUMENT_TYPE_LABELS, get_schema, schema_for_document_type
from ..inference import prompts
from ..inference.vlm import interpret, options, prepare_image
from ..jobs import queue
from ..jobs.events import emit
from ..models.result import ObservationResult, TextLine
from ..storage.filestore import get_store
from .compose import PageAnalysis, compose
from .revalidate import apply_human_edits

log = logging.getLogger("vie.pipeline")


class Retryable(Exception):
    pass


async def _find_duplicates(session, obs: Observation, issuer_ruc: str | None, serie_numero: str | None) -> list[dict]:
    if not issuer_ruc or not serie_numero:
        return []
    rows = (await session.execute(
        select(Observation.id, Observation.created_at).where(
            Observation.issuer_ruc == issuer_ruc, Observation.serie_numero == serie_numero,
            Observation.id != obs.id, Observation.deleted_at.is_(None)).limit(10))).all()
    return [{"id": str(r.id), "created_at": r.created_at.isoformat()} for r in rows]


def _title(result: ObservationResult) -> str | None:
    dt = DOCUMENT_TYPE_LABELS.get(result.document_type or "", None)
    sn = result.fields.get("serie_numero")
    if dt and sn and sn.value:
        return f"{dt} {sn.value}"
    return dt


def _apply_result(obs: Observation, result: ObservationResult, search_text: str) -> None:
    obs.result = result.model_dump(mode="json")
    obs.document_type = result.document_type
    obs.title = _title(result)
    obs.description = result.description
    obs.language = result.language
    obs.validation_status = result.validation.status
    obs.needs_review_count = len(result.validation.needs_review)
    obs.warnings_count = len(result.validation.warnings)
    obs.schema_id = result.metadata.schema_id

    def v(name):
        fv = result.fields.get(name)
        return None if fv is None else fv.value

    obs.issuer_ruc = v("issuer_ruc") if v("issuer_ruc") and len(str(v("issuer_ruc"))) == 11 else None
    obs.serie_numero = (str(v("serie_numero"))[:30] if v("serie_numero") else None)
    try:
        obs.issue_date = datetime.fromisoformat(v("issue_date")).date() if v("issue_date") else None
    except ValueError:
        obs.issue_date = None
    try:
        obs.total = Decimal(str(v("total"))) if v("total") is not None else None
    except Exception:  # noqa: BLE001
        obs.total = None
    obs.currency = v("currency") if v("currency") in ("PEN", "USD", "EUR") else None
    obs.search_text = search_text


async def _load_pages(obs_id: uuid.UUID, page_count: int, assets: list[Asset]) -> list[PageAnalysis]:
    store = get_store()
    pages = []
    for i in range(page_count):
        try:
            analysis = json.loads(store.read(f"derived/{obs_id}/analysis_p{i}.json"))
        except FileNotFoundError:
            continue
        work = next((a for a in assets if a.kind == "work" and a.page_index == i), None)
        proc = next((a for a in assets if a.kind == "processed" and a.page_index == i), None)
        pages.append(PageAnalysis(index=i, analysis=analysis, work_asset_id=str(work.id) if work else None,
                                  processed_asset_id=str(proc.id) if proc else None))
    return pages


def _thumbnail(jpeg: bytes) -> tuple[bytes, int, int]:
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    img.thumbnail((360, 360), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue(), img.width, img.height


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------
async def handle_process(job: Job) -> None:
    s = get_settings()
    store = get_store()
    t_start = time.perf_counter()
    async with session_scope() as session:
        obs = await session.get(Observation, job.observation_id)
        if obs is None or obs.deleted_at is not None:
            return
        original = (await session.execute(select(Asset).where(Asset.observation_id == obs.id,
                                                              Asset.kind == "original"))).scalars().first()
        if original is None:
            raise Unprocessable("missing_original", "No se encontró el archivo original.")
        obs.status, obs.stage = "processing", "vision"
        obs_id, source, mode = obs.id, obs.source, obs.mode
        original_path = original.path
    await emit("observation.processing", "Analizando imagen (preprocesamiento y OCR)…", observation_id=obs_id)

    data = store.read(original_path)
    try:
        info = await vision.inspect(data)
    except ServiceUnavailable as exc:
        raise Retryable(exc.message) from exc
    page_count = min(int(info.get("page_count", 1)), s.max_pdf_pages)
    pages: list[PageAnalysis] = []
    timings = {}
    for i in range(page_count):
        try:
            a = await vision.analyze(data, page=i)
        except ServiceUnavailable as exc:
            raise Retryable(exc.message) from exc
        images = a.pop("images", {}) or {}
        for k, v in (a.get("timings") or {}).items():
            timings[f"vision_{k}"] = timings.get(f"vision_{k}", 0) + int(v)
        work_bytes = base64.b64decode(images["work_jpeg_b64"])
        proc_bytes = base64.b64decode(images["processed_jpeg_b64"]) if images.get("processed_jpeg_b64") else None
        async with session_scope() as session:
            await session.execute(Asset.__table__.delete().where(
                Asset.observation_id == obs_id, Asset.page_index == i, Asset.kind.in_(("work", "processed", "thumbnail"))))
            rel, sha, size = store.save_derived(str(obs_id), f"work_p{i}.jpg", work_bytes)
            wa = Asset(observation_id=obs_id, kind="work", page_index=i, sha256=sha, mime="image/jpeg",
                       width=a["work_size"][0], height=a["work_size"][1], size_bytes=size, path=rel)
            session.add(wa)
            pa = None
            if proc_bytes:
                rel, sha, size = store.save_derived(str(obs_id), f"processed_p{i}.jpg", proc_bytes)
                pa = Asset(observation_id=obs_id, kind="processed", page_index=i, sha256=sha, mime="image/jpeg",
                           width=a["processed_size"][0], height=a["processed_size"][1], size_bytes=size, path=rel)
                session.add(pa)
            if i == 0:
                tb, tw, th = _thumbnail(proc_bytes or work_bytes)
                rel, sha, size = store.save_derived(str(obs_id), "thumb_p0.jpg", tb)
                session.add(Asset(observation_id=obs_id, kind="thumbnail", page_index=0, sha256=sha,
                                  mime="image/jpeg", width=tw, height=th, size_bytes=size, path=rel))
            await session.flush()
            store.save_derived(str(obs_id), f"analysis_p{i}.json", json.dumps(a, ensure_ascii=False).encode())
            pages.append(PageAnalysis(index=i, analysis=a, work_asset_id=str(wa.id),
                                      processed_asset_id=str(pa.id) if pa else None))
        if page_count > 1:
            await emit("observation.progress", f"Página {i + 1} de {page_count} analizada", observation_id=obs_id,
                       data={"page": i + 1, "pages": page_count}, persist=False)

    ocr_engine = next((p.analysis.get("ocr", {}).get("engine") for p in pages if p.analysis.get("ocr", {}).get("engine")),
                      None)
    will_interpret = mode == "full" and s.vlm_enabled
    async with session_scope() as session:
        obs = await session.get(Observation, obs_id)
        if obs is None or obs.deleted_at is not None:
            return
        c = compose(str(obs_id), source, pages, ocr_engine=ocr_engine, schema_id=obs.schema_id)
        dups = await _find_duplicates(session, obs, *_key_fields(c.result))
        if dups:
            c = compose(str(obs_id), source, pages, ocr_engine=ocr_engine, schema_id=obs.schema_id, duplicates=dups)
            session.add(Alert(observation_id=obs_id, severity="warning", code="duplicate_document",
                              message=f"Documento posiblemente duplicado ({len(dups)} registro(s) previos)."))
        result = apply_human_edits(c.result, obs.result)
        result.metadata.vlm_status = "pending" if will_interpret else "not_requested"
        result.metadata.timings = {**timings, "stage1_ms": round((time.perf_counter() - t_start) * 1000)}
        result.metadata.processing_time_ms = result.metadata.timings["stage1_ms"]
        _apply_result(obs, result, c.search_text)
        obs.page_count = page_count
        obs.ocr_engine = ocr_engine
        obs.pipeline_version = result.metadata.pipeline_version
        obs.processing_ms = result.metadata.processing_time_ms
        obs.status = "ocr_ready" if will_interpret else "completed"
        obs.stage = "awaiting_model" if will_interpret else None
        if will_interpret:
            await queue.enqueue(session, "interpret", observation_id=obs_id,
                                priority=queue.PRIORITY["camera" if source == "camera" else "upload"], max_attempts=2)
    await emit("observation.ocr_ready" if will_interpret else "observation.completed",
               f"OCR listo: {len(c.lines)} líneas, tipo {result.document_type or 'desconocido'}, "
               f"validación {result.validation.status}", observation_id=obs_id,
               data={"status": "ocr_ready" if will_interpret else "completed", "document_type": result.document_type,
                     "validation": result.validation.status, "lines": len(c.lines)})


def _key_fields(result: ObservationResult) -> tuple[str | None, str | None]:
    ruc = result.fields.get("issuer_ruc")
    sn = result.fields.get("serie_numero")
    return (ruc.value if ruc else None), (sn.value if sn else None)


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------
async def handle_interpret(job: Job) -> None:
    store = get_store()
    t0 = time.perf_counter()
    async with session_scope() as session:
        obs = await session.get(Observation, job.observation_id)
        if obs is None or obs.deleted_at is not None:
            return
        assets = (await session.execute(select(Asset).where(Asset.observation_id == obs.id))).scalars().all()
        model = job.payload.get("model") or await runtime.active_model(session)
        obs.status, obs.stage = "interpreting", "model"
        obs_id, source, page_count = obs.id, obs.source, obs.page_count
        schema_override = job.payload.get("schema_id") or obs.schema_id
        previous = dict(obs.result or {})
    await emit("observation.interpreting", f"Interpretando con {model}…", observation_id=obs_id,
               data={"model": model})

    pages = await _load_pages(obs_id, page_count, list(assets))
    if not pages:
        raise Unprocessable("missing_analysis", "Falta el análisis visual; reprocese la observación.")
    base = compose(str(obs_id), source, pages, schema_id=schema_override)
    display = next((a for a in assets if a.kind == "processed" and a.page_index == 0), None) or \
        next((a for a in assets if a.kind == "work" and a.page_index == 0), None)
    jpeg = store.read(display.path)
    schema = get_schema(schema_override) or base.schema
    vlm_out, meta = await interpret(model, schema, base.lines, jpeg, camera=source == "camera",
                                    doc_type_hint=base.result.document_type)
    vlm_ms = meta.get("vlm_ms", 0)
    async with session_scope() as session:
        obs = await session.get(Observation, obs_id)
        if obs is None or obs.deleted_at is not None:
            return
        # If the model recognised a known type that rules missed, use its schema next time it is reprocessed
        c = compose(str(obs_id), source, pages, vlm=vlm_out, vlm_meta=_meta_fields(meta), schema_id=schema.id,
                    ocr_engine=obs.ocr_engine)
        dups = await _find_duplicates(session, obs, *_key_fields(c.result))
        if dups:
            c = compose(str(obs_id), source, pages, vlm=vlm_out, vlm_meta=_meta_fields(meta), schema_id=schema.id,
                        ocr_engine=obs.ocr_engine, duplicates=dups)
        result = apply_human_edits(c.result, previous)
        prev_timings = (previous.get("metadata") or {}).get("timings") or {}
        result.metadata.timings = {**prev_timings, "vlm_ms": vlm_ms,
                                   "stage2_ms": round((time.perf_counter() - t0) * 1000)}
        result.metadata.processing_time_ms = (prev_timings.get("stage1_ms") or 0) + result.metadata.timings["stage2_ms"]
        _apply_result(obs, result, c.search_text)
        obs.model_name, obs.model_digest = model, meta.get("model_digest")
        obs.processing_ms = result.metadata.processing_time_ms
        ok = vlm_out is not None
        obs.status = "completed" if ok else "partial"
        obs.stage = None
        obs.error = None if ok else {"code": meta.get("vlm_status"), "message": meta.get("vlm_error")}
    await emit("observation.completed" if ok else "observation.partial",
               (f"Interpretación lista en {vlm_ms / 1000:.1f} s: {result.document_type or 'sin tipo'}, validación "
                f"{result.validation.status}") if ok else f"Interpretación no disponible: {meta.get('vlm_error')}",
               observation_id=obs_id, level="info" if ok else "warning",
               data={"status": "completed" if ok else "partial", "model": model, "vlm_ms": vlm_ms,
                     "document_type": result.document_type, "validation": result.validation.status,
                     "tokens": meta.get("vlm_tokens")})


def _meta_fields(meta: dict) -> dict:
    allowed = {"model", "model_digest", "vlm_tokens", "vlm_status", "vlm_error", "prompt_version",
               "ocr_truncated_in_prompt", "vlm_ms"}
    return {k: v for k, v in meta.items() if k in allowed}


# ---------------------------------------------------------------------------
# Visual question answering
# ---------------------------------------------------------------------------
def _facts(result: dict) -> str:
    fields = {k: (v or {}).get("value") for k, v in (result.get("fields") or {}).items() if v and v.get("value")}
    review = (result.get("validation") or {}).get("needs_review") or []
    return json.dumps({"tipo": result.get("document_type"), "campos": fields,
                       "validacion": (result.get("validation") or {}).get("status"),
                       "requieren_revision": review, "items": len(result.get("items") or [])},
                      ensure_ascii=False)[:2500]


async def handle_chat(job: Job) -> None:
    store = get_store()
    message_id = uuid.UUID(job.payload["message_id"])
    async with session_scope() as session:
        obs = await session.get(Observation, job.observation_id)
        msg = await session.get(ChatMessage, message_id)
        if obs is None or msg is None:
            return
        model = await runtime.active_model(session)
        assets = (await session.execute(select(Asset).where(Asset.observation_id == obs.id))).scalars().all()
        history_rows = (await session.execute(
            select(ChatMessage).where(ChatMessage.observation_id == obs.id, ChatMessage.status == "done",
                                      ChatMessage.id != message_id).order_by(ChatMessage.created_at))).scalars().all()
        question = job.payload.get("question", "")
        history = [{"role": h.role, "content": h.content} for h in history_rows
                   if str(h.id) != job.payload.get("question_id")]
        msg.status, msg.model_name = "streaming", model
        result = dict(obs.result or {})
        obs_id = obs.id
    region = job.payload.get("region")
    page = int((region or {}).get("page", 0))
    display = next((a for a in assets if a.kind == "processed" and a.page_index == page), None) or \
        next((a for a in assets if a.kind == "work" and a.page_index == page), None)
    if display is None:
        raise Unprocessable("no_image", "La observación no tiene imagen procesada.")
    s = get_settings()
    lines = [TextLine.model_validate(ln) for ln in (result.get("text") or {}).get("lines", [])]
    crop = None
    region_note = None
    if region and region.get("bbox"):
        crop = region["bbox"]
        x0, y0, x1, y1 = crop
        lines = [ln for ln in lines if ln.page == page and ln.bbox[0] < x1 and ln.bbox[2] > x0
                 and ln.bbox[1] < y1 and ln.bbox[3] > y0]
        region_note = "La imagen es un RECORTE: la pregunta se refiere solo a esa región seleccionada por el usuario."
    image_b64 = prepare_image(store.read(display.path), s.vlm_max_side_document, crop=crop)
    messages = prompts.chat_messages(question, lines, image_b64, _facts(result), history, s.vlm_max_ocr_chars,
                                     region_note)
    body = {"model": model, "messages": messages, "think": False, "keep_alive": "30m",
            "options": options(num_predict=512)}
    t0 = time.perf_counter()
    content, buffer, last_flush = "", "", time.monotonic()
    try:
        async for chunk in ollama.chat_stream(body):
            delta = (chunk.get("message") or {}).get("content") or ""
            content += delta
            buffer += delta
            if buffer and (time.monotonic() - last_flush > 0.35 or chunk.get("done")):
                await emit("chat.delta", "", observation_id=obs_id, persist=False,
                           data={"message_id": str(message_id), "delta": buffer})
                buffer, last_flush = "", time.monotonic()
        status = "done"
    except ServiceUnavailable as exc:
        status = "error"
        content = content or f"No se pudo obtener respuesta del modelo: {exc.message}"
    valid_ids = {ln.id for ln in lines} | {ln["id"] for ln in (result.get("text") or {}).get("lines", [])}
    evidence = sorted({m for m in re.findall(r"\[(r_\d{4})\]", content) if m in valid_ids})
    async with session_scope() as session:
        msg = await session.get(ChatMessage, message_id)
        if msg is not None:
            msg.content = content[:20000]
            msg.status = status
            msg.evidence_ids = evidence
            msg.duration_ms = round((time.perf_counter() - t0) * 1000)
    await emit("chat.done" if status == "done" else "chat.error",
               "Respuesta generada" if status == "done" else "Error al responder", observation_id=obs_id,
               level="info" if status == "done" else "warning",
               data={"message_id": str(message_id), "evidence_ids": evidence,
                     "duration_ms": round((time.perf_counter() - t0) * 1000)})


HANDLERS = {"process": handle_process, "interpret": handle_interpret, "chat": handle_chat}


async def mark_failed(job: Job, error: str) -> None:
    """Called when a job will not be retried: leave the observation in a clear state."""
    if job.observation_id is None:
        return
    async with session_scope() as session:
        obs = await session.get(Observation, job.observation_id)
        if obs is None:
            return
        if job.type == "process":
            obs.status, obs.stage = "failed", None
            obs.error = {"code": "processing_failed", "message": error[:500]}
        elif job.type == "interpret":
            obs.status, obs.stage = "partial", None
            res = dict(obs.result or {})
            res.setdefault("metadata", {})["vlm_status"] = "failed"
            res["metadata"]["vlm_error"] = error[:300]
            obs.result = res
            obs.error = {"code": "interpretation_failed", "message": error[:500]}
        elif job.type == "chat":
            msg_id = job.payload.get("message_id")
            if msg_id:
                msg = await session.get(ChatMessage, uuid.UUID(msg_id))
                if msg is not None:
                    msg.status, msg.content = "error", f"No se pudo responder: {error[:300]}"
    await emit("observation.failed" if job.type == "process" else f"{job.type}.failed", error[:300],
               observation_id=job.observation_id, level="error")


async def sleep_backoff(seconds: float) -> None:
    await asyncio.sleep(seconds)


def now() -> datetime:
    return datetime.now(UTC)
