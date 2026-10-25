"""Common request/result envelopes for server-side agent tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyIdRequest(StrictRequest):
    synthetic_id: str = Field(min_length=1, max_length=128)


class PeerRequest(CompanyIdRequest):
    limit: int = Field(default=10, ge=1, le=50)


class PaymentExposureRequest(CompanyIdRequest):
    limit: int = Field(default=10, ge=1, le=50)


class RusprofileSearchRequest(CompanyIdRequest):
    pass


class RusprofileProfileRequest(StrictRequest):
    rusprofile_id: str = Field(pattern=r"^\d{5,20}$")


class NewsSearchRequest(StrictRequest):
    synthetic_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=500)
    window: Literal["90d", "7d", "24h"] = "24h"
    limit: int = Field(default=10, ge=1, le=20)


class WebSearchRequest(StrictRequest):
    query: str = Field(min_length=1, max_length=500)
    provider: Literal["serper", "tavily"] = "serper"
    limit: int = Field(default=5, ge=1, le=10)


class OpenSourceRequest(StrictRequest):
    url: str = Field(min_length=1, max_length=2048)
    render_js: bool = False


class KnowledgeSearchRequest(StrictRequest):
    query: str = Field(min_length=1, max_length=2000)
    topic: str | None = None
    limit: int = Field(default=5, ge=1, le=25)


class CitationLookupRequest(StrictRequest):
    store: Literal["alfa_research", "risk_methodology"]
    chunk_ids: list[str] = Field(min_length=1, max_length=100)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial", "error"]
    data: Any = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    request_id: str
    elapsed_ms: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorEnvelope(BaseModel):
    error_code: str
    message: str
