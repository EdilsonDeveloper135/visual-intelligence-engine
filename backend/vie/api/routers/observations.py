from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from ...core.config import get_settings
from ...core.errors import NotFound, TooLarge, Unprocessable
from ...db.models import Asset, ChatMessage, Observation, Revision
from ...db.session import session_scope
from ...doc_schemas.registry import get_schema
from ...jobs import queue
from ...jobs.events import emit
from ...storage.filestore import get_store
from .. import services
from ..schemas import (AnalyzeIn, AssetOut, ChatIn, ExtractIn, FieldsPatch, ObservationDetail, ObservationFilters,
                       ObservationPage, UploadAccepted)
from ..security import audit, make_confirmation, require_auth, verify_confirmation

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/observations", response_model=UploadAccepted, status_code=202, tags=["observations"],
             summary="Cargar imágenes o documentos (PNG, JPEG, WEBP, PDF) y ponerlos en cola")
async def upload(request: Request):
    s = get_settings()
    max_part = max(s.max_image_mb, s.max_pdf_mb, s.max_video_mb) * 1024 * 1024
    form = await request.form(max_files=s.max_files_per_request, max_fields=10, max_part_size=1024 * 1024)
    files = [v for k, v in form.multi_items() if k == "files" and hasattr(v, "read")]
    if not files:
        raise Unprocessable("no_files", "No se recibió ningún archivo (campo 'files').")
    mode = str(form.get("mode") or "full")
    if mode not in ("full", "ocr_only"):
        raise Unprocessable("invalid_mode", "mode debe ser 'full' u 'ocr_only'.")
    schema_id = form.get("schema_id") or None
    if schema_id and get_schema(str(schema_id)) is None:
        raise Unprocessable("unknown_schema", "Esquema de extracción desconocido.")
    sequence = str(form.get("sequence") or "false").lower() == "true"
    payloads = []
    total = 0
    for f in files:
        data = await f.read(max_part + 1)
        if len(data) > max_part:
            raise TooLarge("too_large", "Archivo demasiado grande.")
        mime = services.check_upload(data, f.filename)
        total += len(data)
        payloads.append((data, mime, f.filename))
    await services.check_quota(total)
    seq_id = str(uuid.uuid4()) if sequence and len(payloads) > 1 else None
    created = []
    async with session_scope() as session:
        for i, (data, mime, name) in enumerate(payloads):
            obs = await services.create_observation(
                session, data, mime, source="video" if mime.startswith("video/") else ("sequence" if seq_id else "upload"),
                filename=name, mode=mode,
                schema_id=schema_id, extra_detail={"sequence_id": seq_id, "sequence_index": i} if seq_id else None)
            created.append({"id": str(obs.id), "filename": obs.source_detail.get("original_filename"), "mime": mime,
                            "status": obs.status})
    for c in created:
        await emit("observation.queued", f"Archivo recibido: {c['filename']}", observation_id=c["id"])
    await audit("observation.upload", target_type="observation", target_id=",".join(c["id"] for c in created)[:64],
                details={"count": len(created), "bytes": total, "mode": mode})
    return {"observations": created}


@router.get("/observations", response_model=ObservationPage, tags=["observations"],
            summary="Consultar observaciones (historial, búsqueda y filtros)")
async def list_observations(filters: ObservationFilters = Depends(), page: int = Query(1, ge=1, le=10000),
                            page_size: int = Query(30, ge=1, le=200)):
    async with session_scope() as session:
        items, total = await services.list_observations(session, filters, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/observations/{obs_id}", response_model=ObservationDetail, tags=["observations"])
async def get_observation(obs_id: uuid.UUID, include_deleted: bool = False):
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id, include_deleted)
        assets = (await session.execute(select(Asset).where(Asset.observation_id == obs.id)
                                        .order_by(Asset.page_index, Asset.kind))).scalars().all()
        revs = (await session.execute(select(func.count()).select_from(Revision)
                                      .where(Revision.observation_id == obs.id))).scalar_one()
        thumb = next((a.id for a in assets if a.kind == "thumbnail"), None)
        base = services.summary(obs, thumb).model_dump()
        return ObservationDetail(**base, mode=obs.mode, error=obs.error, result=obs.result or {},
                                 assets=[AssetOut(id=a.id, kind=a.kind, page_index=a.page_index, mime=a.mime,
                                                  width=a.width, height=a.height, size_bytes=a.size_bytes)
                                         for a in assets],
                                 model_digest=obs.model_digest, ocr_engine=obs.ocr_engine,
                                 pipeline_version=obs.pipeline_version, schema_id=obs.schema_id,
                                 original_mime=obs.original_mime, original_sha256=obs.original_sha256,
                                 revisions=revs)


@router.get("/observations/{obs_id}/regions", tags=["observations"],
            summary="Regiones reconocidas (texto, códigos, campos) con coordenadas")
async def regions(obs_id: uuid.UUID):
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id)
    res = obs.result or {}
    fields = [{"field": k, "value": v.get("value"), "bbox": v.get("bounding_box"), "page": v.get("page"),
               "evidence_ids": v.get("evidence_ids"), "needs_review": v.get("needs_review")}
              for k, v in (res.get("fields") or {}).items() if v and v.get("bounding_box")]
    return {"pages": res.get("pages", []), "lines": (res.get("text") or {}).get("lines", []),
            "codes": res.get("codes", []), "fields": fields}


@router.get("/observations/{obs_id}/history", tags=["observations"], summary="Revisiones humanas y eventos")
async def history(obs_id: uuid.UUID):
    from ...db.models import EventLog

    async with session_scope() as session:
        await services.get_observation(session, obs_id, include_deleted=True)
        revs = (await session.execute(select(Revision).where(Revision.observation_id == obs_id)
                                      .order_by(Revision.created_at.desc()))).scalars().all()
        events = (await session.execute(select(EventLog).where(EventLog.observation_id == obs_id)
                                        .order_by(EventLog.id.desc()).limit(200))).scalars().all()
    return {"revisions": [{"id": str(r.id), "created_at": r.created_at.isoformat(), "actor": r.actor,
                           "changes": r.changes, "reason": r.reason} for r in revs],
            "events": [{"id": e.id, "ts": e.ts.isoformat(), "type": e.type, "level": e.level,
                        "message": e.message} for e in events]}


@router.post("/observations/{obs_id}/analyze", status_code=202, tags=["observations"],
             summary="Re-analizar (todo el pipeline o solo la interpretación del modelo)")
async def analyze(obs_id: uuid.UUID, body: AnalyzeIn):
    if body.schema_id and get_schema(body.schema_id) is None:
        raise Unprocessable("unknown_schema", "Esquema de extracción desconocido.")
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id)
        if obs.status in ("queued", "processing", "interpreting"):
            raise Unprocessable("busy", "La observación ya está en proceso.")
        if body.schema_id:
            obs.schema_id = body.schema_id
        if body.stages == "all":
            obs.status, obs.mode = "queued", "full"
            await queue.enqueue(session, "process", observation_id=obs.id, priority=queue.PRIORITY["reprocess"])
        else:
            obs.status, obs.stage = "ocr_ready", "awaiting_model"
            await queue.enqueue(session, "interpret", observation_id=obs.id, priority=queue.PRIORITY["reprocess"],
                                payload={"model": body.model, "schema_id": body.schema_id}, max_attempts=2)
    await audit("observation.analyze", target_type="observation", target_id=str(obs_id), details=body.model_dump())
    await emit("observation.queued", "Re-análisis solicitado", observation_id=obs_id)
    return {"id": str(obs_id), "queued": body.stages}


@router.post("/observations/{obs_id}/extract", status_code=202, tags=["observations"],
             summary="Extraer datos con un esquema concreto (re-interpretación con el modelo)")
async def extract(obs_id: uuid.UUID, body: ExtractIn):
    return await analyze(obs_id, AnalyzeIn(stages="interpret", schema_id=body.schema_id))


@router.post("/observations/{obs_id}/validate", tags=["observations"],
             summary="Re-ejecutar la validación independiente sobre los datos actuales")
async def validate(obs_id: uuid.UUID):
    from ...models.result import ObservationResult
    from ...pipeline.orchestrator import _apply_result
    from ...pipeline.revalidate import revalidate

    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id)
        result = ObservationResult.model_validate(obs.result)
        result = revalidate(result, await services.duplicates_for(session, obs, result))
        _apply_result(obs, result, obs.search_text)
    return result.validation.model_dump()


@router.patch("/observations/{obs_id}/fields", tags=["observations"],
              summary="Editar datos extraídos (queda una revisión auditable y se revalida)")
async def patch_fields(obs_id: uuid.UUID, body: FieldsPatch):
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id, lock=True)
        result, changes = await services.edit_fields(session, obs, body)
    await audit("observation.edit", target_type="observation", target_id=str(obs_id),
                details={"fields": [c["field"] for c in changes], "reason": body.reason})
    await emit("observation.edited", f"{len(changes)} cambio(s) guardado(s)", observation_id=obs_id)
    return {"validation": result.validation.model_dump(), "changes": len(changes)}


@router.post("/observations/{obs_id}/delete-request", tags=["observations"],
             summary="Paso 1 de 2 para eliminar: devuelve un token de confirmación de corta duración")
async def delete_request(obs_id: uuid.UUID):
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id)
    token, exp = make_confirmation("delete", str(obs_id))
    return {"confirm_token": token, "expires_at": datetime.fromtimestamp(exp, UTC).isoformat(),
            "summary": {"id": str(obs.id), "title": obs.title, "created_at": obs.created_at.isoformat()},
            "note": "La observación irá a la papelera y podrá restaurarse hasta que se vacíe la papelera."}


@router.delete("/observations/{obs_id}", tags=["observations"], summary="Paso 2 de 2: mover a la papelera")
async def delete(obs_id: uuid.UUID, confirm_token: str = Query(..., max_length=100)):
    verify_confirmation("delete", str(obs_id), confirm_token)
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id)
        obs.deleted_at = datetime.now(UTC)
    await audit("observation.delete", target_type="observation", target_id=str(obs_id))
    await emit("observation.deleted", "Movida a la papelera", observation_id=obs_id)
    return {"id": str(obs_id), "deleted": True, "restorable": True}


@router.post("/observations/{obs_id}/restore", tags=["observations"])
async def restore(obs_id: uuid.UUID):
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id, include_deleted=True)
        obs.deleted_at = None
    await audit("observation.restore", target_type="observation", target_id=str(obs_id))
    return {"id": str(obs_id), "restored": True}


@router.post("/trash/purge-request", tags=["observations"],
             summary="Paso 1 de 2 para vaciar la papelera (eliminación permanente)")
async def purge_request():
    async with session_scope() as session:
        n = (await session.execute(select(func.count()).select_from(Observation)
                                   .where(Observation.deleted_at.is_not(None)))).scalar_one()
    token, exp = make_confirmation("purge", "trash")
    return {"confirm_token": token, "expires_at": datetime.fromtimestamp(exp, UTC).isoformat(), "items": n,
            "note": "La eliminación es permanente y no se puede deshacer."}


@router.delete("/trash", tags=["observations"], summary="Paso 2 de 2: vaciar la papelera (permanente)")
async def purge(confirm_token: str = Query(..., max_length=100)):
    verify_confirmation("purge", "trash", confirm_token)
    store = get_store()
    purged = 0
    async with session_scope() as session:
        rows = (await session.execute(select(Observation).where(Observation.deleted_at.is_not(None)))).scalars().all()
        for obs in rows:
            originals = [a.path for a in (await session.execute(
                select(Asset).where(Asset.observation_id == obs.id, Asset.kind == "original"))).scalars().all()]
            store.delete_derived(str(obs.id))
            await session.delete(obs)
            await session.flush()
            for path in originals:
                if (await session.execute(select(Asset.id).where(Asset.path == path).limit(1))).first() is None:
                    store.delete_original(path)
            purged += 1
    await audit("trash.purge", details={"purged": purged})
    return {"purged": purged}


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
@router.get("/assets/{asset_id}", tags=["assets"], summary="Descargar/visualizar un archivo (copias re-codificadas)")
async def get_asset(asset_id: uuid.UUID, download: bool = False):
    async with session_scope() as session:
        asset = await session.get(Asset, asset_id)
        if asset is None:
            raise NotFound("not_found", "Archivo no encontrado.")
        obs = await session.get(Observation, asset.observation_id)
    path = get_store().resolve(asset.path)
    if not path.exists():
        raise NotFound("missing_file", "El archivo ya no existe en el almacenamiento.")
    # Originals are never rendered inline (they are untrusted as uploaded); derived images are safe re-encodings.
    attachment = download or asset.kind == "original"
    name = (obs.source_detail or {}).get("original_filename") if obs else None
    filename = name if asset.kind == "original" and name else f"{asset.kind}_p{asset.page_index}.{path.suffix[1:]}"
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'; img-src 'self'; sandbox"}
    return FileResponse(path, media_type=asset.mime, headers=headers,
                        content_disposition_type="attachment" if attachment else "inline", filename=filename)


# ---------------------------------------------------------------------------
# Visual questions
# ---------------------------------------------------------------------------
@router.post("/observations/{obs_id}/chat", status_code=202, tags=["chat"],
             summary="Hacer una pregunta sobre la imagen (respuesta en streaming por /events/stream)")
async def ask(obs_id: uuid.UUID, body: ChatIn):
    async with session_scope() as session:
        obs = await services.get_observation(session, obs_id)
        if obs.status in ("queued", "processing"):
            raise Unprocessable("busy", "Espere a que termine el análisis de la imagen.")
        q = ChatMessage(observation_id=obs.id, role="user", content=body.question, status="done",
                        region=body.region.model_dump() if body.region else None)
        a = ChatMessage(observation_id=obs.id, role="assistant", content="", status="queued")
        session.add_all([q, a])
        await session.flush()
        await queue.enqueue(session, "chat", observation_id=obs.id, priority=queue.PRIORITY["chat"], max_attempts=1,
                            payload={"message_id": str(a.id), "question_id": str(q.id), "question": body.question,
                                     "region": body.region.model_dump() if body.region else None})
        ids = {"question_id": str(q.id), "message_id": str(a.id)}
    await audit("chat.question", target_type="observation", target_id=str(obs_id))
    return ids


@router.get("/observations/{obs_id}/chat", tags=["chat"])
async def chat_history(obs_id: uuid.UUID):
    async with session_scope() as session:
        await services.get_observation(session, obs_id)
        rows = (await session.execute(select(ChatMessage).where(ChatMessage.observation_id == obs_id)
                                      .order_by(ChatMessage.created_at))).scalars().all()
    return [{"id": str(m.id), "role": m.role, "content": m.content, "status": m.status, "region": m.region,
             "evidence_ids": m.evidence_ids, "model": m.model_name, "duration_ms": m.duration_ms,
             "created_at": m.created_at.isoformat()} for m in rows]
