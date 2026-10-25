"""Typed provenance contract for knowledge-store retrieval."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


KnowledgeStore = Literal["alfa_research", "risk_methodology"]


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    knowledge_store: KnowledgeStore
    document_id: str
    title: str
    source_url: str | None = None
    publication_date: str | None = None
    version: str | None = None
    content_hash: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    excerpt: str
    jurisdiction: str | None = None
    applicability: str | None = None
    license_scope: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
