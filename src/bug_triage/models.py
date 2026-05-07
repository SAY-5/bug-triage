"""SQLAlchemy models. pgvector column for embeddings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bug_triage.embedder import EMBED_DIM


class Base(DeclarativeBase):
    pass


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    bug_report: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    fix_diff: Mapped[str] = mapped_column(Text, nullable=False)
    files_changed: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    component: Mapped[str] = mapped_column(String(16), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TriageResult(Base):
    __tablename__ = "triage_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incoming_bug: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    retrieved_ids: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    suggestion: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    suggested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
