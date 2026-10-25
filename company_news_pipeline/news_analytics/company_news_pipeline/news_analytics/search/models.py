"""Typed contracts for provider results and rolling news windows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NewsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    title: str
    url: str
    snippet: str = ""
    publisher: str | None = None
    provider_published_at: str | None = None
    published_at: datetime | None = None
    date_status: Literal["parsed", "undated", "unparseable"] = "undated"
    image_url: str | None = None
    provider_rank: int | None = None
    query: str
    retrieved_at: datetime
    provider: str = "serper_news"


class ProviderSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    provider: str
    results: list[NewsEvent] = Field(default_factory=list)
    retrieved_at: datetime
    error_code: str | None = None
    warning: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class SearchWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic_id: str
    window: Literal["90d", "7d", "24h"]
    requested_limit: int
    actual_count: int
    updated_at: datetime | None = None
    events: list[NewsEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
