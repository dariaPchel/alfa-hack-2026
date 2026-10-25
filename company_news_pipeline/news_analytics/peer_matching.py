"""Deterministic and explainable peer matching for synthetic company profiles."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from .config import get_peer_weights
from .db import Database
from .models import CompanyProfile, PeerProfile


_PRODUCT_FIELDS = (
    "cl_product_rko_mark",
    "cl_product_gar_mark",
    "cl_product_loa_mark",
    "cl_product_lea_mark",
    "cl_product_dep_mark",
    "cl_product_zpp_mark",
)
_TRADE_FIELDS = ("fts_flag", "fts_country_name", "factoring_mark")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _normalize(value: Any) -> str | None:
    if not _present(value):
        return None
    return " ".join(str(value).casefold().strip().split())


def _categorical_similarity(left: Any, right: Any) -> float | None:
    left_value, right_value = _normalize(left), _normalize(right)
    if left_value is None or right_value is None:
        return None
    return 1.0 if left_value == right_value else 0.0


def _ordinal_value(value: Any, dimension: str) -> float | None:
    normalized = _normalize(value)
    if normalized is None:
        return None

    if dimension == "age":
        age_terms = {"up to 3 years": 1.5, "3-5 years": 4.0, "5-10 years": 7.5, "over 10 years": 15.0}
        if normalized in age_terms:
            return age_terms[normalized]

    if dimension == "revenue":
        money_ranges = re.findall(r"(\d+(?:[.,]\d+)?)\s*(bln|mln|thousand)", normalized)
        if money_ranges:
            multipliers = {"bln": 1_000_000_000, "mln": 1_000_000, "thousand": 1_000}
            values = [float(number.replace(",", ".")) * multipliers[unit] for number, unit in money_ranges]
            return sum(values) / len(values)

    numbers = [float(token.replace(",", ".")) for token in _NUMBER.findall(normalized)]
    if not numbers:
        return {"small": 1.0, "medium": 2.0, "large": 3.0}.get(normalized)

    if len(numbers) >= 2:
        return (numbers[0] + numbers[1]) / 2
    value_number = numbers[0]
    if normalized.startswith("up to "):
        return value_number / 2
    if normalized.startswith(("over ", "above ", "from ")):
        return value_number * 1.5

    return value_number


def _ordinal_similarity(left: Any, right: Any, dimension: str) -> float | None:
    if not _present(left) or not _present(right):
        return None
    if _normalize(left) == _normalize(right):
        return 1.0
    left_value = _ordinal_value(left, dimension)
    right_value = _ordinal_value(right, dimension)
    if left_value is None or right_value is None:
        return None
    distance = abs(math.log1p(max(left_value, 0.0)) - math.log1p(max(right_value, 0.0)))
    return max(0.0, 1.0 - distance / 4.0)


def _okved_similarity(left: CompanyProfile, right: CompanyProfile) -> tuple[float | None, dict[str, Any]]:
    left_code, right_code = _normalize(left.mainokved_code), _normalize(right.mainokved_code)
    if left_code and right_code:
        left_digits = re.sub(r"\D", "", left_code)
        right_digits = re.sub(r"\D", "", right_code)
        if left_digits == right_digits:
            return 1.0, {"basis": "exact_code", "left": left.mainokved_code, "right": right.mainokved_code}
        if left_digits and right_digits and left_digits[:2] == right_digits[:2]:
            similarity = 0.75 if left_digits[:4] == right_digits[:4] else 0.55
            return similarity, {"basis": "shared_okved_class", "left": left.mainokved_code, "right": right.mainokved_code}
        if left_digits and right_digits and left_digits[0] == right_digits[0]:
            return 0.25, {"basis": "shared_okved_section", "left": left.mainokved_code, "right": right.mainokved_code}
        return 0.0, {"basis": "different_okved_section", "left": left.mainokved_code, "right": right.mainokved_code}

    left_name, right_name = _normalize(left.mainokved_name), _normalize(right.mainokved_name)
    if left_name and right_name:
        return SequenceMatcher(None, left_name, right_name).ratio(), {
            "basis": "activity_name_similarity",
            "left": left.mainokved_name,
            "right": right.mainokved_name,
        }
    return None, {"basis": "unavailable"}


def _average_available(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    if not available:
        return None
    return sum(available) / len(available)


def _ownership_similarity(left: CompanyProfile, right: CompanyProfile) -> tuple[float | None, dict[str, Any]]:
    parts = {
        "org_type": _categorical_similarity(left.org_type, right.org_type),
        "okfs_name": _categorical_similarity(left.okfs_name, right.okfs_name),
    }
    return _average_available(list(parts.values())), {"fields": parts}


def _scale_similarity(left: CompanyProfile, right: CompanyProfile) -> tuple[float | None, dict[str, Any]]:
    parts = {
        "revenue_company": _ordinal_similarity(left.revenue_company, right.revenue_company, "revenue"),
        "workers_fns": _ordinal_similarity(
            left.amount_workers_fns_gradation, right.amount_workers_fns_gradation, "workers"
        ),
        "workers_spark": _ordinal_similarity(
            left.amount_workers_spark_gradation, right.amount_workers_spark_gradation, "workers"
        ),
    }
    return _average_available(list(parts.values())), {"fields": parts}


def _region_similarity(left: CompanyProfile, right: CompanyProfile) -> tuple[float | None, dict[str, Any]]:
    region_left, region_right = _normalize(left.region), _normalize(right.region)
    city_left, city_right = _normalize(left.city), _normalize(right.city)
    if region_left and region_right:
        score = 1.0 if region_left == region_right else 0.0
        if city_left and city_right and city_left == city_right:
            score = 1.0
        return score, {"region_match": region_left == region_right, "city_match": city_left == city_right if city_left and city_right else None}
    if city_left and city_right:
        return (1.0 if city_left == city_right else 0.0), {"region_match": None, "city_match": city_left == city_right}
    return None, {"basis": "unavailable"}


def _age_stage_similarity(left: CompanyProfile, right: CompanyProfile) -> tuple[float | None, dict[str, Any]]:
    parts = {
        "company_age": _ordinal_similarity(
            left.company_age_years_gradation, right.company_age_years_gradation, "age"
        ),
        "business_stage": _categorical_similarity(left.eco_mark_label, right.eco_mark_label),
    }
    return _average_available(list(parts.values())), {"fields": parts}


def _product_trade_network_similarity(
    left: CompanyProfile,
    right: CompanyProfile,
    left_network: set[str] | None,
    right_network: set[str] | None,
) -> tuple[float | None, dict[str, Any]]:
    product_values = [
        _categorical_similarity(getattr(left, name), getattr(right, name)) for name in _PRODUCT_FIELDS
    ]
    trade_values = [
        _categorical_similarity(getattr(left, name), getattr(right, name)) for name in _TRADE_FIELDS
    ]
    product_trade = _average_available(product_values + trade_values)
    network: float | None = None
    if left_network and right_network:
        union = left_network | right_network
        network = len(left_network & right_network) / len(union) if union else None
    parts = {"product_trade_similarity": product_trade, "network_industry_jaccard": network}
    return _average_available(list(parts.values())), {"fields": parts}


def _load_active_profiles(db: Database) -> tuple[int | None, list[CompanyProfile], dict[str, set[str] | None]]:
    with db.connect() as connection:
        active = connection.execute(
            "SELECT import_batch_id FROM active_dataset WHERE singleton_id = 1"
        ).fetchone()
        if not active:
            return None, [], {}
        batch_id = int(active["import_batch_id"])
        rows = connection.execute(
            "SELECT * FROM synthetic_companies WHERE import_batch_id = ? ORDER BY synthetic_id",
            (batch_id,),
        ).fetchall()


    profiles = [CompanyProfile.model_validate(dict(row)) for row in rows]
    profile_ids = {profile.synthetic_id for profile in profiles}
    network_codes: dict[str, set[str] | None] = {synthetic_id: None for synthetic_id in profile_ids}
    industry_by_id: dict[str, set[str]] = {synthetic_id: set() for synthetic_id in profile_ids}
    # The edge's counterparty is the other endpoint relative to each focal ID.
    with db.connect() as connection:
        payment_rows = connection.execute(
            """SELECT p.payer, p.beneficiary,
                      payer.mainokved_code AS payer_okved,
                      beneficiary.mainokved_code AS beneficiary_okved
               FROM payment_edges AS p
               LEFT JOIN synthetic_companies AS payer
                 ON payer.import_batch_id = p.import_batch_id AND payer.synthetic_id = p.payer
               LEFT JOIN synthetic_companies AS beneficiary
                 ON beneficiary.import_batch_id = p.import_batch_id AND beneficiary.synthetic_id = p.beneficiary
               WHERE p.import_batch_id = ?""",
            (batch_id,),
        ).fetchall()
    for row in payment_rows:
        payer, beneficiary = row["payer"], row["beneficiary"]
        if payer in profile_ids and row["beneficiary_okved"]:
            industry_by_id[payer].add(row["beneficiary_okved"])
        if beneficiary in profile_ids and row["payer_okved"]:
            industry_by_id[beneficiary].add(row["payer_okved"])
    for synthetic_id, codes in industry_by_id.items():
        if codes:
            network_codes[synthetic_id] = codes
    return batch_id, profiles, network_codes


def find_peers(
    synthetic_id: str,
    db: Database,
    limit: int = 10,
    *,
    weights: dict[str, float] | None = None,
) -> list[PeerProfile]:
    """Rank active-dataset peers with stable ties and feature-level rationale."""

    if limit <= 0:
        return []
    batch_id, profiles, network_codes = _load_active_profiles(db)
    if batch_id is None:
        return []
    target = next((profile for profile in profiles if profile.synthetic_id == synthetic_id), None)
    if target is None:
        return []
    dimensions = get_peer_weights(weights)
    ranked: list[tuple[float, str, CompanyProfile, dict[str, float | None], dict[str, Any], list[str]]] = []

    for candidate in profiles:
        if candidate.synthetic_id == synthetic_id:
            continue
        score_results = {
            "okved": _okved_similarity(target, candidate),
            "ownership_type": _ownership_similarity(target, candidate),
            "scale": _scale_similarity(target, candidate),
            "region": _region_similarity(target, candidate),
            "age_stage": _age_stage_similarity(target, candidate),
            "product_trade_network": _product_trade_network_similarity(
                target,
                candidate,
                network_codes.get(target.synthetic_id),
                network_codes.get(candidate.synthetic_id),
            ),
        }
        feature_scores = {name: result[0] for name, result in score_results.items()}
        available_weight = sum(dimensions[name] for name, score in feature_scores.items() if score is not None)
        if available_weight <= 0:
            continue
        score = sum(
            dimensions[name] * value
            for name, value in feature_scores.items()
            if value is not None
        ) / available_weight
        explanation = {
            name: {
                "weight": dimensions[name],
                "score": feature_scores[name],
                "normalized_contribution": (
                    dimensions[name] * feature_scores[name] / available_weight
                    if feature_scores[name] is not None
                    else None
                ),
                "details": score_results[name][1],
            }
            for name in dimensions
        }
        matched = [name for name, value in feature_scores.items() if value is not None and value > 0]
        missing = [name for name, value in feature_scores.items() if value is None]
        ranked.append((score, candidate.synthetic_id, candidate, feature_scores, explanation, missing))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = ranked[:limit]
    now = datetime.now(timezone.utc).isoformat()
    if selected:
        with db.connect() as connection:
            connection.execute(
                "DELETE FROM peer_scores WHERE dataset_batch_id = ? AND target_synthetic_id = ?",
                (batch_id, synthetic_id),
            )
            for score, peer_id, _, feature_scores, explanation, _ in selected:
                connection.execute(
                    """INSERT INTO peer_scores (
                           dataset_batch_id, target_synthetic_id, peer_synthetic_id,
                           similarity_score, feature_scores_json, calculated_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        batch_id,
                        synthetic_id,
                        peer_id,
                        score,
                        json.dumps(explanation, ensure_ascii=False),
                        now,
                    ),
                )

    peers: list[PeerProfile] = []
    for score, _, profile, feature_scores, explanation, missing in selected:
        payload = profile.model_dump()
        payload.update(
            {
                "similarity_score": score,
                "feature_scores": feature_scores,
                "matched_features": [name for name, value in feature_scores.items() if value is not None and value > 0],
                "missing_features": missing,
                "score_explanation": explanation,
            }
        )
        peers.append(PeerProfile.model_validate(payload))
    return peers
