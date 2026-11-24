from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from ...actions.registry import ACTIONS, describe
from ...clients import ollama
from ...core import runtime
from ...core.config import get_settings
from ...core.errors import NotFound, Unprocessable, VieError
from ...db.models import Alert, AuditLog, CameraSession, CustomSchema, Observation
from ...db.session import session_scope
from ...doc_schemas import registry
from ...exports.exporters import FORMATS
from ...storage.filestore import get_store
from .. import services
from ..schemas import (ActionIn, CameraSettingsIn, CompareIn, CustomSchemaIn, ExportIn, ModelSelect,
                       ObservationFilters)
from ..security import audit, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])

RECOMMENDED = [
    {"name": "qwen3-vl:2b-instruct", "profile": "lite", "size_gb": 1.9, "license": "Apache-2.0",
     "note": "Por defecto. Cabe en 3,25 GB de RAM; ~30 s por imagen en CPU."},
    {"name": "qwen3-vl:4b-instruct", "profile": "advanced", "size_gb": 3.3, "license": "Apache-2.0",
     "note": "Más preciso; requiere ~5 GB de RAM para el contenedor de Ollama."},
    {"name": "qwen3-vl:8b-instruct", "profile": "advanced", "size_gb": 6.2, "license": "Apache-2.0",
     "note": "Mejor calidad; requiere ≥ 9 GB de RAM y es lento en CPU."},
    {"name": "granite3.2-vision:2b", "profile": "alternative", "size_gb": 2.4, "license": "Apache-2.0",
     "note": "Alternativa orientada a documentos."},
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@router.get("/models", tags=["models"], summary="Modelos instalados, activo y recomendados")
async def models():
    installed = await ollama.tags()
    async with session_scope() as session:
        active = await runtime.active_model(session)
    return {"active": active, "ollama_version": await ollama.version(),
            "installed": [{"name": m.get("name"), "size_bytes": m.get("size"), "digest": m.get("digest"),
                           "modified_at": m.get("modified_at"), "details": m.get("details")} for m in installed],
            "loaded": [m.get("name") for m in await ollama.loaded()], "recommended": RECOMMENDED,
            "install_note": "Descargar modelos requiere Internet y solo se hace en la fase de instalación: "
                            "make pull-model MODEL=<nombre>"}


@router.put("/models/active", tags=["models"])
async def set_active_model(body: ModelSelect):
    names = [m.get("name") for m in await ollama.tags()]
    if body.model not in names:
        raise Unprocessable("model_not_installed", "Ese modelo no está instalado localmente.")
    async with session_scope() as session:
        await runtime.set_value(session, "active_model", body.model)
    await audit("model.activate", details={"model": body.model})
    return {"active": body.model}


# ---------------------------------------------------------------------------
# Extraction schemas
# ---------------------------------------------------------------------------
@router.get("/schemas", tags=["schemas"])
async def list_schemas():
    return [s.to_public() for s in registry.all_schemas()]


@router.get("/schemas/{schema_id}", tags=["schemas"])
async def get_schema(schema_id: str):
    s = registry.get_schema(schema_id)
    if s is None:
        raise NotFound("not_found", "Esquema no encontrado.")
    return {**s.to_public(), "json_schema": registry.vlm_json_schema(s)}


@router.post("/schemas", tags=["schemas"], status_code=201, summary="Crear un esquema de extracción personalizado")
async def create_schema(body: CustomSchemaIn):
    if registry.get_schema(body.id):
        raise Unprocessable("exists", "Ya existe un esquema con ese id.")
    definition = body.model_dump()
    async with session_scope() as session:
        session.add(CustomSchema(id=body.id, definition=definition))
    registry.register_custom(definition)
    await audit("schema.create", target_type="schema", target_id=body.id)
    return registry.get_schema(body.id).to_public()


@router.put("/schemas/{schema_id}", tags=["schemas"])
async def update_schema(schema_id: str, body: CustomSchemaIn):
    if body.id != schema_id:
        raise Unprocessable("id_mismatch", "El id del cuerpo no coincide.")
    async with session_scope() as session:
        row = await session.get(CustomSchema, schema_id)
        if row is None:
            raise NotFound("not_found", "Solo se pueden editar esquemas personalizados.")
        row.definition = body.model_dump()
    registry.register_custom(body.model_dump())
    await audit("schema.update", target_type="schema", target_id=schema_id)
    return registry.get_schema(schema_id).to_public()


@router.delete("/schemas/{schema_id}", tags=["schemas"])
async def delete_schema(schema_id: str):
    async with session_scope() as session:
        row = await session.get(CustomSchema, schema_id)
        if row is None:
            raise NotFound("not_found", "Solo se pueden eliminar esquemas personalizados.")
        await session.delete(row)
    registry.unregister_custom(schema_id)
    await audit("schema.delete", target_type="schema", target_id=schema_id)
    return {"deleted": schema_id}


# ---------------------------------------------------------------------------
# Settings, camera sessions
# ---------------------------------------------------------------------------
@router.get("/settings", tags=["settings"])
async def get_settings_view():
    s = get_settings()
    async with session_scope() as session:
        cam = await runtime.camera_settings(session)
        model = await runtime.active_model(session)
    return {"camera": cam, "active_model": model,
            "limits": {"max_image_mb": s.max_image_mb, "max_pdf_mb": s.max_pdf_mb, "max_pdf_pages": s.max_pdf_pages,
                       "max_files_per_request": s.max_files_per_request, "job_timeout_s": s.job_timeout_s},
            "storage": {"quota_gb": s.storage_quota_gb, "retention_days": s.retention_days},
            "vlm": {"num_ctx": s.vlm_num_ctx, "num_predict": s.vlm_num_predict,
                    "max_side_document": s.vlm_max_side_document, "max_side_camera": s.vlm_max_side_camera,
                    "enabled": s.vlm_enabled}}


@router.put("/settings/camera", tags=["settings"])
async def put_camera_settings(body: CameraSettingsIn):
    async with session_scope() as session:
        await runtime.set_value(session, "camera", body.model_dump())
    await audit("settings.camera", details=body.model_dump())
    return body.model_dump()


@router.get("/camera/sessions", tags=["camera"])
async def camera_sessions(limit: int = Query(20, ge=1, le=100)):
    async with session_scope() as session:
        rows = (await session.execute(select(CameraSession).order_by(CameraSession.started_at.desc())
                                      .limit(limit))).scalars().all()
    return [{"id": str(r.id), "started_at": r.started_at.isoformat(),
             "ended_at": r.ended_at.isoformat() if r.ended_at else None, "stats": r.stats} for r in rows]


# ---------------------------------------------------------------------------
# Export, actions, search/compare, alerts, audit, storage
# ---------------------------------------------------------------------------
async def _select_for_export(session, body: ExportIn) -> list[Observation]:
    if body.observation_ids:
        rows = (await session.execute(select(Observation).where(Observation.id.in_(body.observation_ids),
                                                                Observation.deleted_at.is_(None)))).scalars().all()
    else:
        stmt = services.apply_filters(select(Observation), body.filters or ObservationFilters())
        rows = (await session.execute(stmt.order_by(Observation.created_at.desc()).limit(5000))).scalars().all()
    return list(rows)


@router.post("/exports", tags=["export"], summary="Exportar a JSON, CSV, XLSX o informe HTML")
async def export(body: ExportIn):
    async with session_scope() as session:
        rows = await _select_for_export(session, body)
    if not rows:
        raise NotFound("empty", "No hay observaciones para exportar.")
    fn, mime, ext = FORMATS[body.format]
    data = fn(rows)
    await audit("export", details={"format": body.format, "count": len(rows)})
    name = f"vie-{body.format}-{datetime.now(UTC):%Y%m%d-%H%M%S}.{ext}"
    return Response(content=data, media_type=mime,
                     headers={"Content-Disposition": f'attachment; filename="{name}"',
                              "X-Content-Type-Options": "nosniff"})


@router.get("/actions", tags=["actions"], summary="Lista explícita de acciones permitidas")
async def list_actions():
    return describe()


@router.post("/actions/{name}", tags=["actions"], summary="Ejecutar una acción permitida")
async def run_action(name: str, body: ActionIn):
    action = ACTIONS.get(name)
    if action is None:
        await audit("action.rejected", details={"name": name[:60]}, outcome="denied")
        raise NotFound("unknown_action", "Acción no permitida.")
    params = action.params.model_validate(body.params)
    async with session_scope() as session:
        out = await action.handler(session, params)
    await audit(f"action.{name}", details={"params": params.model_dump(mode="json")})
    if isinstance(out, dict) and "__file__" in out:
        data, mime, filename = out["__file__"]
        return Response(content=data, media_type=mime,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    return out


@router.post("/compare", tags=["memory"], summary="Comparar dos documentos")
async def compare(body: CompareIn):
    async with session_scope() as session:
        return await services.compare(session, body.a, body.b)


@router.get("/search", tags=["memory"], summary="Buscar en registros anteriores (texto completo, RUC, serie)")
async def search(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(20, ge=1, le=100)):
    async with session_scope() as session:
        items, total = await services.list_observations(session, ObservationFilters(q=q), 1, limit)
    return {"total": total, "items": items}


@router.get("/alerts", tags=["memory"])
async def alerts(include_acknowledged: bool = False, limit: int = Query(50, ge=1, le=500)):
    async with session_scope() as session:
        stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
        if not include_acknowledged:
            stmt = stmt.where(Alert.acknowledged_at.is_(None))
        rows = (await session.execute(stmt)).scalars().all()
    return [{"id": str(a.id), "observation_id": str(a.observation_id) if a.observation_id else None,
             "severity": a.severity, "code": a.code, "message": a.message, "created_at": a.created_at.isoformat(),
             "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None} for a in rows]


@router.post("/alerts/{alert_id}/ack", tags=["memory"])
async def ack_alert(alert_id: uuid.UUID):
    async with session_scope() as session:
        a = await session.get(Alert, alert_id)
        if a is None:
            raise NotFound("not_found", "Alerta no encontrada.")
        a.acknowledged_at = datetime.now(UTC)
    return {"acknowledged": str(alert_id)}


@router.get("/audit", tags=["security"], summary="Registro auditable de operaciones")
async def audit_log(limit: int = Query(100, ge=1, le=1000), action: str | None = Query(None, max_length=60)):
    async with session_scope() as session:
        stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if action:
            stmt = stmt.where(AuditLog.action.like(f"{action}%"))
        rows = (await session.execute(stmt)).scalars().all()
    return [{"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor, "action": r.action, "target_type": r.target_type,
             "target_id": r.target_id, "details": r.details, "outcome": r.outcome} for r in rows]


@router.get("/storage", tags=["storage"], summary="Uso de almacenamiento, cuota y retención")
async def storage():
    s = get_settings()
    usage = get_store().usage()
    async with session_scope() as session:
        counts = dict((await session.execute(select(Observation.status, func.count()).group_by(Observation.status)
                                             )).all())
        trash = (await session.execute(select(func.count()).select_from(Observation)
                                       .where(Observation.deleted_at.is_not(None)))).scalar_one()
    return {"usage_bytes": usage, "quota_bytes": int(s.storage_quota_gb * 1024 ** 3),
            "retention_days": s.retention_days, "observations_by_status": counts, "trash": trash}


def _unused():  # keep linters quiet about imported-but-unused names used only in type hints
    return VieError
