"""Strict request/response models of the public API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..doc_schemas.registry import DOCUMENT_TYPES, FIELD_TYPES

Strict = ConfigDict(extra="forbid", str_strip_whitespace=True)
FIELD_NAME = r"^[a-z][a-z0-9_]{0,59}$"


class LoginIn(BaseModel):
    model_config = Strict
    access_key: str = Field(min_length=1, max_length=200)


class ErrorOut(BaseModel):
    code: str
    message: str
    details: Any = None


class ObservationFilters(BaseModel):
    model_config = Strict
    q: str | None = Field(None, max_length=200)
    document_type: str | None = Field(None, max_length=40)
    status: str | None = Field(None, max_length=20)
    validation_status: str | None = Field(None, max_length=30)
    source: Literal["upload", "camera", "sequence", "video", "video_frame"] | None = None
    parent_id: uuid.UUID | None = None
    ruc: str | None = Field(None, pattern=r"^\d{1,11}$")
    camera_session_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    needs_review: bool | None = None
    include_deleted: bool = False
    only_deleted: bool = False


class ObservationSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    source: str
    status: str
    stage: str | None
    kind: str
    document_type: str | None
    title: str | None
    description: str | None
    validation_status: str | None
    needs_review_count: int
    warnings_count: int
    issuer_ruc: str | None
    serie_numero: str | None
    issue_date: date | None
    total: str | None
    currency: str | None
    original_filename: str | None
    page_count: int
    thumbnail_asset_id: uuid.UUID | None
    camera_session_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None
    parent_id: uuid.UUID | None = None
    repeat_count: int
    model_name: str | None
    processing_ms: int | None
    deleted_at: datetime | None


class ObservationPage(BaseModel):
    items: list[ObservationSummary]
    total: int
    page: int
    page_size: int


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    page_index: int
    mime: str
    width: int | None
    height: int | None
    size_bytes: int


class ObservationDetail(ObservationSummary):
    mode: str
    error: dict | None
    result: dict
    assets: list[AssetOut]
    model_digest: str | None
    ocr_engine: str | None
    pipeline_version: str | None
    schema_id: str | None
    original_mime: str | None
    original_sha256: str | None
    revisions: int


class UploadAccepted(BaseModel):
    observations: list[dict]


class FieldEdit(BaseModel):
    model_config = Strict
    field: str = Field(pattern=FIELD_NAME)
    value: str | None = Field(None, max_length=500)


class ItemEdit(BaseModel):
    model_config = Strict
    description: str | None = Field(None, max_length=300)
    quantity: str | None = Field(None, max_length=30)
    unit: str | None = Field(None, max_length=20)
    unit_price: str | None = Field(None, max_length=30)
    amount: str | None = Field(None, max_length=30)


class FieldsPatch(BaseModel):
    model_config = Strict
    changes: list[FieldEdit] = Field(default_factory=list, max_length=60)
    items: list[ItemEdit] | None = Field(None, max_length=200)
    document_type: str | None = None
    reason: str | None = Field(None, max_length=500)

    @field_validator("document_type")
    @classmethod
    def _doc_type(cls, v):
        if v is not None and v not in DOCUMENT_TYPES:
            raise ValueError("tipo de documento desconocido")
        return v


class AnalyzeIn(BaseModel):
    model_config = Strict
    stages: Literal["all", "interpret"] = "all"
    model: str | None = Field(None, max_length=80, pattern=r"^[A-Za-z0-9._:/-]+$")
    schema_id: str | None = Field(None, max_length=60, pattern=r"^[a-z0-9_]+$")


class ExtractIn(BaseModel):
    model_config = Strict
    schema_id: str = Field(max_length=60, pattern=r"^[a-z0-9_]+$")


class Region(BaseModel):
    model_config = Strict
    page: int = Field(0, ge=0, le=999)
    bbox: list[int] = Field(min_length=4, max_length=4)


class ChatIn(BaseModel):
    model_config = Strict
    question: str = Field(min_length=1, max_length=1000)
    region: Region | None = None


class ExportIn(BaseModel):
    model_config = Strict
    format: Literal["json", "csv", "csv_items", "xlsx", "html"]
    observation_ids: list[uuid.UUID] | None = Field(None, max_length=1000)
    filters: ObservationFilters | None = None


class ModelSelect(BaseModel):
    model_config = Strict
    model: str = Field(max_length=80, pattern=r"^[A-Za-z0-9._:/-]+$")


class CameraSettingsIn(BaseModel):
    model_config = Strict
    interval_ms: int = Field(1500, ge=300, le=60000)
    min_ocr_interval_s: float = Field(3, ge=0.5, le=600)
    min_vlm_interval_s: float = Field(60, ge=10, le=3600)
    auto_vlm: bool = False
    repeat_threshold: int = Field(6, ge=1, le=30)
    new_threshold: int = Field(18, ge=5, le=60)


class CustomFieldIn(BaseModel):
    model_config = Strict
    name: str = Field(pattern=FIELD_NAME)
    label: str = Field(min_length=1, max_length=120)
    type: str = "string"
    required: bool = False
    description: str = Field("", max_length=300)

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v not in FIELD_TYPES:
            raise ValueError(f"tipo no soportado; use uno de {sorted(FIELD_TYPES)}")
        return v


class CustomSchemaIn(BaseModel):
    model_config = Strict
    id: str = Field(pattern=r"^custom_[a-z0-9_]{2,50}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=500)
    document_types: list[str] = Field(default_factory=lambda: ["otro_documento"], max_length=10)
    has_items: bool = False
    fields: list[CustomFieldIn] = Field(min_length=1, max_length=60)

    @field_validator("document_types")
    @classmethod
    def _dt(cls, v):
        bad = [x for x in v if x not in DOCUMENT_TYPES]
        if bad:
            raise ValueError(f"tipos desconocidos: {bad}")
        return v


class CompareIn(BaseModel):
    model_config = Strict
    a: uuid.UUID
    b: uuid.UUID


class ActionIn(BaseModel):
    model_config = Strict
    params: dict[str, Any] = Field(default_factory=dict)
