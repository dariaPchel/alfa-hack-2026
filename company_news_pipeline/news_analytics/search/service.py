"""Service facade for the three rolling company-news windows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..company_profiles import get_company_profile
from ..db import Database
from ..peer_matching import find_peers
from .models import SearchWindow
from .refresh import get_company_news


class CompanyNewsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic_id: str
    generated_at: datetime
    windows: dict[str, SearchWindow]
    warnings: list[str]
    profile: dict[str, Any] | None = None


def company_news_response(synthetic_id: str, db: Database, refresh_24h: bool = True) -> CompanyNewsResponse:
    windows = get_company_news(synthetic_id, db, refresh_24h=refresh_24h)
    profile = get_company_profile(synthetic_id, db)
    if profile is None:
        raise KeyError(f"Unknown synthetic company ID: {synthetic_id}")
    peers = find_peers(synthetic_id, db, limit=8)
    profile_data = profile.model_dump(mode="json")
    profile_data["peer_basis"] = [peer.model_dump(mode="json") for peer in peers]
    warnings = [warning for window in windows.values() for warning in window.warnings]
    return CompanyNewsResponse(synthetic_id=synthetic_id, generated_at=datetime.now(timezone.utc),
                               windows=windows, profile=profile_data,
                               warnings=list(dict.fromkeys(warnings)))
