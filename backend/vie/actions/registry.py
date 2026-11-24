"""Controlled action engine (layer H).

Only the actions declared here exist. Each one has a strict Pydantic parameter
model and a handler that works exclusively on the local database/files. There
is no generic "run command" action, no network access and the multimodal model
can never trigger an action: actions are invoked only by the user (API/UI).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFound
from ..db.models import Observation
from ..doc_schemas.registry import DOCUMENT_TYPES
from ..exports.exporters import FORMATS

Strict = ConfigDict(extra="forbid")


class ObservationRef(BaseModel):
    model_config = Strict
    observation_id: uuid.UUID


class ObservationList(BaseModel):
    model_config = Strict
    observation_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class ClassifyParams(BaseModel):
    model_config = Strict
    observation_id: uuid.UUID
    document_type: Literal[tuple(DOCUMENT_TYPES)]  # type: ignore[valid-type]


class CompareParams(BaseModel):
    model_config = Strict
    a: uuid.UUID
    b: uuid.UUID


class SearchParams(BaseModel):
    model_config = Strict
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)


class AlertParams(BaseModel):
    model_config = Strict
    observation_id: uuid.UUID | None = None
    severity: Literal["info", "warning", "error"] = "warning"
    message: str = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[[AsyncSession, Any], Awaitable[dict]]
    irreversible: bool = False


async def _load(session: AsyncSession, ids: list[uuid.UUID]) -> list[Observation]:
    rows = (await session.execute(select(Observation).where(Observation.id.in_(ids),
                                                            Observation.deleted_at.is_(None)))).scalars().all()
    if not rows:
        raise NotFound("not_found", "No se encontraron las observaciones indicadas.")
    return list(rows)


async def save_record(session: AsyncSession, p: ObservationRef) -> dict:
    obs = await session.get(Observation, p.observation_id)
    if obs is None or obs.deleted_at is not None:
        raise NotFound("not_found", "Observación no encontrada.")
    res = dict(obs.result or {})
    res.setdefault("metadata", {})["confirmed_by_human"] = True
    obs.result = res
    return {"observation_id": str(obs.id), "confirmed": True}


def _export(fmt: str):
    async def handler(session: AsyncSession, p: ObservationList) -> dict:
        rows = await _load(session, p.observation_ids)
        fn, mime, ext = FORMATS[fmt]
        return {"__file__": (fn(rows), mime, f"vie-export.{ext}"), "count": len(rows)}
    return handler


async def classify_document(session: AsyncSession, p: ClassifyParams) -> dict:
    from ..api.schemas import FieldsPatch
    from ..api.services import edit_fields

    obs = await session.get(Observation, p.observation_id)
    if obs is None or obs.deleted_at is not None:
        raise NotFound("not_found", "Observación no encontrada.")
    result, _ = await edit_fields(session, obs, FieldsPatch(document_type=p.document_type,
                                                            reason="Clasificación manual (acción)"))
    return {"observation_id": str(obs.id), "document_type": result.document_type,
            "validation": result.validation.status}


async def generate_report(session: AsyncSession, p: ObservationList) -> dict:
    return await _export("html")(session, p)


async def compare_documents(session: AsyncSession, p: CompareParams) -> dict:
    from ..api.services import compare

    return await compare(session, p.a, p.b)


async def search_records(session: AsyncSession, p: SearchParams) -> dict:
    from ..api.schemas import ObservationFilters
    from ..api.services import list_observations

    items, total = await list_observations(session, ObservationFilters(q=p.query), 1, p.limit)
    return {"total": total, "items": [i.model_dump(mode="json") for i in items]}


async def create_alert(session: AsyncSession, p: AlertParams) -> dict:
    from ..api.services import create_alert as _create

    alert = await _create(session, p.observation_id, p.severity, "manual", p.message)
    return {"alert_id": str(alert.id)}


ACTIONS: dict[str, Action] = {a.name: a for a in [
    Action("save_record", "Confirmar/guardar un registro revisado por una persona.", ObservationRef, save_record),
    Action("export_json", "Exportar observaciones a JSON.", ObservationList, _export("json")),
    Action("export_csv", "Exportar observaciones a CSV.", ObservationList, _export("csv")),
    Action("export_xlsx", "Exportar observaciones a Excel (XLSX).", ObservationList, _export("xlsx")),
    Action("classify_document", "Clasificar manualmente un documento.", ClassifyParams, classify_document),
    Action("generate_report", "Generar un informe HTML de observaciones.", ObservationList, generate_report),
    Action("compare_documents", "Comparar los campos de dos documentos.", CompareParams, compare_documents),
    Action("search_records", "Buscar registros anteriores.", SearchParams, search_records),
    Action("create_alert", "Crear una alerta manual.", AlertParams, create_alert),
]}


def describe() -> list[dict]:
    return [{"name": a.name, "description": a.description, "irreversible": a.irreversible,
             "params_schema": a.params.model_json_schema()} for a in ACTIONS.values()]
