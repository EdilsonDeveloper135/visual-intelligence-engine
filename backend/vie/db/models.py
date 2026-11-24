"""SQLAlchemy models: visual memory (layer G), job queue, audit and sessions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, Computed, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        func, text)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    source: Mapped[str] = mapped_column(String(20))  # upload | camera | sequence
    source_detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    mode: Mapped[str] = mapped_column(String(20), default="full")  # full | ocr_only
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(12), default="new")  # new | updated (camera)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id", ondelete="SET NULL"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id", ondelete="SET NULL"))
    camera_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("camera_sessions.id", ondelete="SET NULL"), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repeat_count: Mapped[int] = mapped_column(Integer, default=0)

    original_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    original_mime: Mapped[str | None] = mapped_column(String(40))
    page_count: Mapped[int] = mapped_column(Integer, default=1)

    document_type: Mapped[str | None] = mapped_column(String(40), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    validation_status: Mapped[str | None] = mapped_column(String(30))
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings_count: Mapped[int] = mapped_column(Integer, default=0)

    # Denormalised key fields for search/filters/duplicate detection
    issuer_ruc: Mapped[str | None] = mapped_column(String(11), index=True)
    serie_numero: Mapped[str | None] = mapped_column(String(30), index=True)
    issue_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))

    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column()
    model_name: Mapped[str | None] = mapped_column(String(80))
    model_digest: Mapped[str | None] = mapped_column(String(80))
    ocr_engine: Mapped[str | None] = mapped_column(String(120))
    pipeline_version: Mapped[str | None] = mapped_column(String(20))
    schema_id: Mapped[str | None] = mapped_column(String(60))
    processing_ms: Mapped[int | None] = mapped_column(Integer)

    search_text: Mapped[str] = mapped_column(Text, default="")
    search_tsv = mapped_column(TSVECTOR, Computed("to_tsvector('spanish', coalesce(search_text, ''))",
                                                  persisted=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    assets: Mapped[list["Asset"]] = relationship(back_populates="observation", cascade="all, delete-orphan",
                                                 foreign_keys="Asset.observation_id")

    __table_args__ = (
        Index("ix_observations_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_observations_created_at", "created_at"),
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # original | work | processed | thumbnail
    page_index: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(40))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    path: Mapped[str] = mapped_column(String(300))  # relative to the data dir, never user-controlled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    observation: Mapped[Observation] = relationship(back_populates="assets", foreign_keys=[observation_id])


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(40), default="local-user")
    changes: Mapped[list[Any]] = mapped_column(default=list)
    reason: Mapped[str | None] = mapped_column(Text)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="done")  # queued | streaming | done | error
    region: Mapped[dict[str, Any] | None] = mapped_column()
    evidence_ids: Mapped[list[Any]] = mapped_column(default=list)
    model_name: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(20))  # process | interpret | chat | retention
    lane: Mapped[str] = mapped_column(String(10))  # fast | vlm
    observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"),
                                                             index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # lower = sooner
    status: Mapped[str] = mapped_column(String(12), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(60))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_jobs_claim", "lane", "status", "priority", "run_after"),)


class CameraSession(Base):
    __tablename__ = "camera_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_agent: Mapped[str | None] = mapped_column(String(200))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor: Mapped[str] = mapped_column(String(40), default="local-user")
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    outcome: Mapped[str] = mapped_column(String(12), default="ok")


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")
    type: Mapped[str] = mapped_column(String(40))
    observation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"),
                                                             index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    severity: Mapped[str] = mapped_column(String(10))  # info | warning | error
    code: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class CustomSchema(Base):
    __tablename__ = "custom_schemas"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    definition: Mapped[dict[str, Any]] = mapped_column(default=dict)
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
