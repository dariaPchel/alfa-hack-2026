"""Typed contracts for the anonymized hackathon company dataset."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class CompanyProfile(BaseModel):
    """One synthetic company row, preserving the source CSV's string values."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    synthetic_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("SYNTHETIC_U", "synthetic_id"),
    )
    org_type: str | None = Field(default=None, validation_alias=AliasChoices("ORG_TYPE", "org_type"))
    okfs_name: str | None = Field(default=None, validation_alias=AliasChoices("OKFS_NAME", "okfs_name"))
    company_age_years_gradation: str | None = Field(
        default=None,
        validation_alias=AliasChoices("COMPANY_AGE_YEARS_GRADATION", "company_age_years_gradation"),
    )
    eco_mark_label: str | None = Field(default=None, validation_alias=AliasChoices("ECO_MARK_LABEL", "eco_mark_label"))
    mainokved_code: str | None = Field(default=None, validation_alias=AliasChoices("MAINOKVED_CODE", "mainokved_code"))
    mainokved_name: str | None = Field(default=None, validation_alias=AliasChoices("MAINOKVED_NAME", "mainokved_name"))
    negativemark: str | None = Field(default=None, validation_alias=AliasChoices("NEGATIVEMARK", "negativemark"))
    amount_workers_fns_gradation: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AMOUNT_WORKERS_FNS_GRADATION", "amount_workers_fns_gradation"),
    )
    amount_workers_spark_gradation: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AMOUNT_WORKERS_SPARK_GRADATION", "amount_workers_spark_gradation"),
    )
    cl_type: str | None = Field(default=None, validation_alias=AliasChoices("CL_TYPE", "cl_type"))
    cl_product_rko_mark: str | None = Field(default=None, validation_alias=AliasChoices("CL_PRODUCT_RKO_MARK", "cl_product_rko_mark"))
    cl_product_gar_mark: str | None = Field(default=None, validation_alias=AliasChoices("CL_PRODUCT_GAR_MARK", "cl_product_gar_mark"))
    cl_product_loa_mark: str | None = Field(default=None, validation_alias=AliasChoices("CL_PRODUCT_LOA_MARK", "cl_product_loa_mark"))
    cl_product_lea_mark: str | None = Field(default=None, validation_alias=AliasChoices("CL_PRODUCT_LEA_MARK", "cl_product_lea_mark"))
    cl_product_dep_mark: str | None = Field(default=None, validation_alias=AliasChoices("CL_PRODUCT_DEP_MARK", "cl_product_dep_mark"))
    cl_product_zpp_mark: str | None = Field(default=None, validation_alias=AliasChoices("CL_PRODUCT_ZPP_MARK", "cl_product_zpp_mark"))
    fts_flag: str | None = Field(default=None, validation_alias=AliasChoices("FTS_FLAG", "fts_flag"))
    fts_country_name: str | None = Field(default=None, validation_alias=AliasChoices("FTS_COUNTRY_NAME", "fts_country_name"))
    factoring_mark: str | None = Field(default=None, validation_alias=AliasChoices("FACTORING_MARK", "factoring_mark"))
    revenue_company: str | None = Field(default=None, validation_alias=AliasChoices("REVENUE_COMPANY", "revenue_company"))
    group_id: str | None = Field(default=None, validation_alias=AliasChoices("GROUP_ID", "group_id"))
    city: str | None = Field(default=None, validation_alias=AliasChoices("CITY", "city"))
    region: str | None = Field(default=None, validation_alias=AliasChoices("REGION", "region"))
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class PeerProfile(CompanyProfile):
    """A synthetic peer with deterministic, explainable similarity scores."""

    similarity_score: float = Field(ge=0.0, le=1.0)
    feature_scores: dict[str, float | None] = Field(default_factory=dict)
    matched_features: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    score_explanation: dict[str, Any] = Field(default_factory=dict)


class IndustryExposure(BaseModel):
    """Payment-network exposure grouped by counterparty industry."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    synthetic_id: str
    direction: Literal["payer", "beneficiary"]
    industry_code: str | None = None
    industry_name: str
    payment_amount_total: Decimal | None = None
    payment_count_total: int | None = None
    distinct_counterparty_count: int = Field(ge=0)
    amount_share: float | None = Field(default=None, ge=0.0, le=1.0)
    count_share: float | None = Field(default=None, ge=0.0, le=1.0)
    contributing_synthetic_ids: list[str] = Field(default_factory=list)
    calculation_basis: str
    period_start: str | None = None
    period_end: str | None = None
    has_temporal_coverage: bool = False


class ImportFileSummary(BaseModel):
    """Per-file import counts and schema observations."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    sha256: str | None = None
    rows_seen: int = Field(ge=0)
    rows_imported: int = Field(ge=0)
    rows_skipped: int = Field(ge=0)
    missing_optional_fields: list[str] = Field(default_factory=list)
    unexpected_fields: list[str] = Field(default_factory=list)


class ImportSummary(BaseModel):
    """Outcome and provenance for one dataset import batch."""

    model_config = ConfigDict(extra="forbid")

    batch_id: int | None = None
    mock_data: bool = False
    companies: ImportFileSummary
    relations: ImportFileSummary
    warnings: list[str] = Field(default_factory=list)
    started_at: str
    completed_at: str | None = None


class CompanyRelation(BaseModel):
    """An anonymized person-to-company link from the relation CSV."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)

    synthetic_f: str = Field(validation_alias=AliasChoices("SYNTHETIC_F", "synthetic_f"))
    city_name: str | None = Field(default=None, validation_alias=AliasChoices("CITY_NAME", "city_name"))
    rc_name: str | None = Field(default=None, validation_alias=AliasChoices("RC_NAME", "rc_name"))
    synthetic_id: str = Field(validation_alias=AliasChoices("SYNTHETIC_U", "synthetic_id"))


class PaymentEdge(BaseModel):
    """An anonymized payment edge; raw numeric values remain representable."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)

    beneficiary: str = Field(validation_alias=AliasChoices("BENEFICIARY", "beneficiary"))
    payer: str = Field(validation_alias=AliasChoices("PAYER", "payer"))
    payment_amount: Decimal | None = Field(default=None, validation_alias=AliasChoices("PAY_AMT", "payment_amount"))
    payment_count: int | None = Field(default=None, validation_alias=AliasChoices("PAY_CNT", "payment_count"))
