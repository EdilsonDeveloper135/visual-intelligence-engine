"""Domain operations used by the API routers and by the action engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import PurePath

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.errors import NotFound, TooLarge, Unprocessable
from ..db.models import Alert, Asset, Observation, Revision
from ..doc_schemas.registry import get_schema, schema_for_document_type
from ..extraction.merge import normalize_value
from ..jobs import queue
from ..models.result import FieldSource, FieldValue, Item, ObservationResult
from ..pipeline.revalidate import revalidate
from ..storage.filestore import get_store
from ..storage.sniff import EXTENSIONS, SUPPORTED_UPLOAD, sniff
from .schemas import FieldsPatch, ObservationFilters, ObservationSummary


def limit_for(mime: str) -> int:
    s = get_settings()
    if mime.startswith("video/"):
        return s.max_video_mb * 1024 * 1024
    return (s.max_pdf_mb if mime == "application/pdf" else s.max_image_mb) * 1024 * 1024


def check_upload(data: bytes, filename: str | None) -> str:
    mime = sniff(data)
    if mime == "image/heic":
        raise Unprocessable("unsupported_type", "HEIC/HEIF no está soportado; exporte la foto como JPEG.")
    if mime == "text/markup":
        raise Unprocessable("unsupported_type", "Los archivos SVG/HTML/XML no se aceptan por seguridad.")
    if mime not in SUPPORTED_UPLOAD:
        raise Unprocessable("unsupported_type", "Tipo no soportado. Se aceptan PNG, JPEG, WEBP, PDF y video MP4/WEBM/MOV.")
    if len(data) > limit_for(mime):
        raise TooLarge("too_large", f"El archivo supera el límite de {limit_for(mime) // (1024 * 1024)} MB.")
    ext = PurePath(filename or "").suffix.lower()
    if ext and ext not in EXTENSIONS[mime]:
        raise Unprocessable("extension_mismatch",
                            f"La extensión {ext} no coincide con el contenido real del archivo ({mime}).")
    return mime


async def check_quota(extra_bytes: int) -> None:
    s = get_settings()
    used = get_store().usage()["total"]
    if used + extra_bytes > s.storage_quota_gb * 1024 ** 3:
        raise TooLarge("quota_exceeded", "Se alcanzó la cuota de almacenamiento configurada.")


async def create_observation(session: AsyncSession, data: bytes, mime: str, *, source: str, filename: str | None,
                             mode: str = "full", schema_id: str | None = None, camera_session_id=None,
                             kind: str = "new", supersedes_id=None, extra_detail: dict | None = None,
                             priority: int | None = None, parent_id=None) -> Observation:
    store = get_store()
    rel, sha, size = store.save_original(data, mime)
    obs = Observation(source=source, mode=mode, status="queued", kind=kind, supersedes_id=supersedes_id,
                      parent_id=parent_id,
                      camera_session_id=camera_session_id, original_sha256=sha, original_mime=mime,
                      schema_id=schema_id,
                      source_detail={"original_filename": store.sanitize_filename(filename) if filename else None,
                                     "size_bytes": size, "mime": mime, **(extra_detail or {})},
                      last_seen_at=datetime.now(UTC))
    session.add(obs)
    await session.flush()
    session.add(Asset(observation_id=obs.id, kind="original", page_index=0, sha256=sha, mime=mime, size_bytes=size,
                      path=rel))
    await queue.enqueue(session, "process", observation_id=obs.id,
                        priority=priority if priority is not None else queue.PRIORITY.get(source, 3))
    return obs


def summary(obs: Observation, thumb_id=None) -> ObservationSummary:
    return ObservationSummary(
        id=obs.id, created_at=obs.created_at, updated_at=obs.updated_at, source=obs.source, status=obs.status,
        stage=obs.stage, kind=obs.kind, document_type=obs.document_type, title=obs.title,
        description=obs.description, validation_status=obs.validation_status,
        needs_review_count=obs.needs_review_count, warnings_count=obs.warnings_count, issuer_ruc=obs.issuer_ruc,
        serie_numero=obs.serie_numero, issue_date=obs.issue_date,
        total=str(obs.total) if obs.total is not None else None, currency=obs.currency,
        original_filename=(obs.source_detail or {}).get("original_filename"), page_count=obs.page_count,
        thumbnail_asset_id=thumb_id, camera_session_id=obs.camera_session_id, supersedes_id=obs.supersedes_id,
        parent_id=obs.parent_id,
        repeat_count=obs.repeat_count, model_name=obs.model_name, processing_ms=obs.processing_ms,
        deleted_at=obs.deleted_at)


def apply_filters(stmt: Select, f: ObservationFilters) -> Select:
    if f.only_deleted:
        stmt = stmt.where(Observation.deleted_at.is_not(None))
    elif not f.include_deleted:
        stmt = stmt.where(Observation.deleted_at.is_(None))
    if f.q:
        like = f"%{f.q}%"
        stmt = stmt.where(or_(Observation.search_tsv.op("@@")(func.websearch_to_tsquery("spanish", f.q)),
                              Observation.title.ilike(like), Observation.serie_numero.ilike(like),
                              Observation.issuer_ruc.ilike(like)))
    if f.document_type:
        stmt = stmt.where(Observation.document_type == f.document_type)
    if f.status:
        stmt = stmt.where(Observation.status == f.status)
    if f.validation_status:
        stmt = stmt.where(Observation.validation_status == f.validation_status)
    if f.source:
        stmt = stmt.where(Observation.source == f.source)
    if f.ruc:
        stmt = stmt.where(Observation.issuer_ruc.like(f"{f.ruc}%"))
    if f.camera_session_id:
        stmt = stmt.where(Observation.camera_session_id == f.camera_session_id)
    if f.parent_id:
        stmt = stmt.where(Observation.parent_id == f.parent_id)
    if f.date_from:
        stmt = stmt.where(Observation.created_at >= datetime.combine(f.date_from, datetime.min.time(), UTC))
    if f.date_to:
        stmt = stmt.where(Observation.created_at < datetime.combine(f.date_to, datetime.min.time(), UTC)
                          + timedelta(days=1))
    if f.needs_review is True:
        stmt = stmt.where(Observation.needs_review_count > 0)
    return stmt


async def list_observations(session: AsyncSession, f: ObservationFilters, page: int, page_size: int):
    base = apply_filters(select(Observation), f)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.order_by(Observation.created_at.desc())
                                  .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    thumbs = await thumbnails(session, [r.id for r in rows])
    return [summary(r, thumbs.get(r.id)) for r in rows], total


async def thumbnails(session: AsyncSession, ids: list[uuid.UUID]) -> dict:
    if not ids:
        return {}
    rows = (await session.execute(select(Asset.observation_id, Asset.id).where(
        Asset.observation_id.in_(ids), Asset.kind == "thumbnail"))).all()
    return {r[0]: r[1] for r in rows}


async def get_observation(session: AsyncSession, obs_id: uuid.UUID, include_deleted: bool = False,
                          lock: bool = False) -> Observation:
    obs = await session.get(Observation, obs_id, with_for_update=lock or None)
    if obs is None or (obs.deleted_at is not None and not include_deleted):
        raise NotFound("not_found", "Observación no encontrada.")
    return obs


async def duplicates_for(session: AsyncSession, obs: Observation, result: ObservationResult) -> list[dict]:
    ruc, sn = result.fields.get("issuer_ruc"), result.fields.get("serie_numero")
    if not ruc or not sn or not ruc.value or not sn.value:
        return []
    rows = (await session.execute(select(Observation.id, Observation.created_at).where(
        Observation.issuer_ruc == str(ruc.value), Observation.serie_numero == str(sn.value),
        Observation.id != obs.id, Observation.deleted_at.is_(None)).limit(10))).all()
    return [{"id": str(r.id), "created_at": r.created_at.isoformat()} for r in rows]


async def edit_fields(session: AsyncSession, obs: Observation, patch: FieldsPatch) -> tuple[ObservationResult, list]:
    if obs.status in ("queued", "processing"):
        raise Unprocessable("busy", "La observación aún se está procesando.")
    result = ObservationResult.model_validate(obs.result)
    schema = get_schema(result.metadata.schema_id) or schema_for_document_type(result.document_type)
    changes = []
    if patch.document_type and patch.document_type != result.document_type:
        changes.append({"field": "document_type", "old": result.document_type, "new": patch.document_type})
        result.document_type = patch.document_type
        result.document_type_info.final = patch.document_type
        result.document_type_info.human = True
    for ch in patch.changes:
        spec = schema.field(ch.field)
        old = result.fields.get(ch.field)
        typ = spec.type if spec else (old.type if old else "string")
        value, extra = normalize_value(typ, ch.value)
        if ch.value not in (None, "") and value is None:
            raise Unprocessable("invalid_value", f"El valor de '{ch.field}' no es válido para el tipo {typ}.")
        new = FieldValue(value=value, raw=ch.value, type=typ, provenance="observed", source="human",
                         sources=([*old.sources] if old else []) + [FieldSource(source="human", value=value,
                                                                                raw=ch.value)],
                         evidence_ids=old.evidence_ids if old else [], bounding_box=old.bounding_box if old else None,
                         page=old.page if old else None, needs_review=False, edited_by_human=True,
                         currency=extra.get("currency") or (old.currency if old else None))
        changes.append({"field": ch.field, "old": old.value if old else None, "new": value})
        result.fields[ch.field] = new if value is not None else None
        if value is None:
            # an explicit null by a human is kept as an edited empty value
            result.fields[ch.field] = FieldValue(value=None, raw=None, type=typ, source="human", edited_by_human=True)
    if patch.items is not None:
        old_items = [i.model_dump() for i in result.items]
        new_items = []
        for it in patch.items:
            norm = {k: normalize_value("money" if k in ("unit_price", "amount") else "decimal" if k == "quantity"
                                       else "string", getattr(it, k))[0] for k in ("quantity", "unit_price", "amount")}
            new_items.append(Item(description=it.description, unit=it.unit, provenance="observed", source="human",
                                  **norm))
        result.items = new_items
        changes.append({"field": "items", "old": old_items, "new": [i.model_dump() for i in new_items]})
    if not changes:
        raise Unprocessable("no_changes", "No se indicaron cambios.")
    result = revalidate(result, await duplicates_for(session, obs, result))
    from ..pipeline.orchestrator import _apply_result  # local import: avoid cycle at module load

    _apply_result(obs, result, obs.search_text + "\n" + " ".join(str(c["new"]) for c in changes if c["new"]))
    session.add(Revision(observation_id=obs.id, changes=_jsonable(changes), reason=patch.reason))
    return result, changes


def _jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


async def compare(session: AsyncSession, a_id: uuid.UUID, b_id: uuid.UUID) -> dict:
    a, b = await get_observation(session, a_id), await get_observation(session, b_id)
    fa, fb = (a.result or {}).get("fields") or {}, (b.result or {}).get("fields") or {}
    rows = []
    for name in sorted(set(fa) | set(fb)):
        va, vb = (fa.get(name) or {}).get("value"), (fb.get(name) or {}).get("value")
        if va is None and vb is None:
            continue
        rows.append({"field": name, "a": va, "b": vb, "equal": va == vb})
    findings = []
    if a.issuer_ruc and a.issuer_ruc == b.issuer_ruc and a.serie_numero and a.serie_numero == b.serie_numero:
        findings.append("Ambos registros tienen el mismo RUC y serie-número (posible duplicado).")
    if a.total is not None and b.total is not None:
        diff = (b.total - a.total)
        findings.append(f"Diferencia de total (B − A): {diff}")
    return {"a": str(a.id), "b": str(b.id), "fields": rows, "findings": findings,
            "same_document_type": a.document_type == b.document_type}


async def create_alert(session: AsyncSession, obs_id: uuid.UUID | None, severity: str, code: str, message: str):
    alert = Alert(observation_id=obs_id, severity=severity, code=code, message=message[:1000])
    session.add(alert)
    await session.flush()
    return alert
