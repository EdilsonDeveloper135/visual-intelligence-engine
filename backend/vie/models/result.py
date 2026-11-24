"""Structured output of an observation (extensible).

Conventions:
- Money and decimals are serialised as strings ("128.62") to avoid float errors.
- `score` is only present when an engine produced it, always with its `source`,
  and it is never a calibrated probability.
- `provenance`: observed (read in the image), computed (derived arithmetically),
  inferred (interpretation without direct visual evidence).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Provenance = Literal["observed", "computed", "inferred"]
SourceName = Literal["qr", "ocr_rules", "vlm", "pdf_text", "human", "validator"]


class Score(BaseModel):
    value: float
    source: str
    note: str = "engine confidence, not a calibrated probability"


class TextLine(BaseModel):
    id: str  # evidence id, e.g. "r_0012"
    page: int
    text: str
    bbox: list[int]
    polygon: list[list[int]] | None = None
    score: Score | None = None
    source: Literal["ocr", "pdf_text"] = "ocr"


class FieldSource(BaseModel):
    source: SourceName
    value: Any = None
    raw: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: Any = None  # normalised value (str for money/decimal, ISO date, ...)
    raw: str | None = None  # text as observed
    type: str = "string"
    unit: str | None = None
    currency: str | None = None
    provenance: Provenance = "observed"
    source: SourceName | None = None  # source of the chosen value
    sources: list[FieldSource] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    bounding_box: list[int] | None = None
    page: int | None = None
    score: Score | None = None
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    edited_by_human: bool = False


class Item(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str | None = None
    quantity: str | None = None
    unit: str | None = None
    unit_price: str | None = None
    amount: str | None = None
    provenance: Provenance = "observed"
    source: SourceName | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    bounding_box: list[int] | None = None
    page: int | None = None
    needs_review: bool = False


class Entity(BaseModel):
    type: str  # organization | person | tax_id | date | amount | address | ...
    value: str
    normalized: str | None = None
    role: str | None = None  # issuer | customer | ...
    bounding_box: list[int] | None = None
    page: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = "observed"
    source: SourceName = "ocr_rules"


class Relationship(BaseModel):
    type: str  # identifies | issued_to | sum_of | tax_of | references | ...
    source: str
    target: str
    description: str | None = None
    derived_by: str = "rules"


class Code(BaseModel):
    format: str
    text: str
    page: int
    bbox: list[int] | None = None
    parsed: dict[str, Any] | None = None
    source: str


class CheckResult(BaseModel):
    id: str
    rule: str
    status: Literal["pass", "fail", "warn", "skipped"]
    severity: Literal["info", "warning", "error"] = "info"
    message: str
    fields: list[str] = Field(default_factory=list)
    expected: Any = None
    observed: Any = None
    tolerance: str | None = None


class ValidationReport(BaseModel):
    status: Literal["pending", "valid", "valid_with_warnings", "invalid", "insufficient_data"] = "pending"
    checks: list[CheckResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    needs_review: list[str] = Field(default_factory=list)
    validator: str = "vie.validation (deterministic, independent of the model)"


class PageInfo(BaseModel):
    index: int
    width: int
    height: int
    source_size: list[int] | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    preprocessing: list[dict[str, Any]] = Field(default_factory=list)
    document_quad: list[list[int]] | None = None
    transform: list[list[float]] | None = None
    work_asset_id: str | None = None
    processed_asset_id: str | None = None
    display_asset_id: str | None = None
    text_source: Literal["ocr", "pdf_text", "none"] = "ocr"


class Unreadable(BaseModel):
    element: str
    reason: str | None = None
    source: SourceName = "vlm"


class Inference(BaseModel):
    statement: str
    basis: str | None = None
    source: SourceName = "vlm"


class DocumentTypeInfo(BaseModel):
    final: str | None = None
    rules: str | None = None
    vlm: str | None = None
    qr: str | None = None
    human: bool = False


class Metadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str | None = None
    model_digest: str | None = None
    ocr_engine: str | None = None
    pipeline_version: str | None = None
    processing_time_ms: int | None = None
    timings: dict[str, int] = Field(default_factory=dict)
    schema_id: str | None = None
    profile: str | None = None
    vlm_tokens: dict[str, Any] | None = None
    vlm_status: Literal["not_requested", "pending", "done", "failed", "truncated", "skipped"] = "pending"
    vlm_error: str | None = None


class ObservationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    observation_id: str
    source: str
    document_type: str | None = None
    document_type_info: DocumentTypeInfo = Field(default_factory=DocumentTypeInfo)
    is_document: bool | None = None
    description: str | None = None
    language: str | None = None
    pages: list[PageInfo] = Field(default_factory=list)
    text: dict[str, Any] = Field(default_factory=lambda: {"full_text": "", "lines": []})
    entities: list[Entity] = Field(default_factory=list)
    objects: list[dict[str, Any]] = Field(default_factory=list)
    codes: list[Code] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    fields: dict[str, FieldValue | None] = Field(default_factory=dict)
    dynamic_fields: list[dict[str, Any]] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    unreadable: list[Unreadable] = Field(default_factory=list)
    inferences: list[Inference] = Field(default_factory=list)
    validation: ValidationReport = Field(default_factory=ValidationReport)
    metadata: Metadata = Field(default_factory=Metadata)
