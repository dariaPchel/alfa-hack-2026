"""Per-synthetic-ID public news query generation."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import CompanyProfile, IndustryExposure


@dataclass(frozen=True)
class SearchQuery:
    synthetic_id: str
    category: str
    query: str
    rationale: str


def build_company_queries(
    synthetic_id: str,
    profile: CompanyProfile,
    exposures: list[IndustryExposure] | None = None,
) -> list[SearchQuery]:
    """Create an ID-scoped plan from public descriptors, never search the ID itself."""

    industry = profile.mainokved_name or profile.mainokved_code or "business industry"
    region = profile.region or ""
    location = f" {region}" if region else ""
    descriptors = [industry]
    for exposure in exposures or []:
        if exposure.industry_name and exposure.industry_name != "Unknown industry":
            descriptors.append(exposure.industry_name)
    unique = list(dict.fromkeys(descriptors))[:4]
    queries = []
    for value in unique:
        queries.extend([
            SearchQuery(synthetic_id, "industry_news", f'"{value}"{location} новости отрасли', "main or counterparty industry"),
            SearchQuery(synthetic_id, "courts_crackdown", f'"{value}"{location} арбитраж суды проверки', "industry legal pressure signals"),
            SearchQuery(synthetic_id, "regulator_action", f'"{value}"{location} регулятор ограничения предписание', "industry regulatory actions"),
            SearchQuery(synthetic_id, "corporate_material_facts", f'"{value}"{location} "существенные факты"', "corporate material-fact signals"),
        ])
    return queries
