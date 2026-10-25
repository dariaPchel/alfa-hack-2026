"""Deterministic, non-temporal summaries of anonymized payment edges."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from .db import Database
from .models import IndustryExposure


Direction = Literal["payer", "beneficiary"]


def _active_batch_id(db: Database) -> int | None:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT import_batch_id FROM active_dataset WHERE singleton_id = 1"
        ).fetchone()
    return int(row["import_batch_id"]) if row else None


def _to_decimal(raw_value: Any) -> Decimal | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _to_nonnegative_int(raw_value: Any) -> int | None:
    if raw_value is None or str(raw_value).strip() == "":
        return None
    try:
        result = int(str(raw_value).strip())
    except ValueError:
        return None
    return result if result >= 0 else None


def get_counterparty_industries(
    synthetic_id: str,
    db: Database,
    limit: int = 10,
) -> list[IndustryExposure]:
    """Aggregate payer/beneficiary counterparties by their main OKVED.

    A `payer` exposure means the selected company is the payer and the
    beneficiary is the counterparty; `beneficiary` reverses that direction.
    The source has no dates, so these aggregates are never presented as trends.
    """

    batch_id = _active_batch_id(db)
    if batch_id is None or limit <= 0:
        return []

    exposures: list[IndustryExposure] = []
    for direction, focal_column, counterparty_column in (
        ("payer", "p.payer", "p.beneficiary"),
        ("beneficiary", "p.beneficiary", "p.payer"),
    ):
        with db.connect() as connection:
            rows = connection.execute(
                f"""SELECT p.{counterparty_column.split('.')[-1]} AS counterparty_id,
                           p.pay_amt, p.pay_cnt, c.mainokved_code, c.mainokved_name
                    FROM payment_edges AS p
                    LEFT JOIN synthetic_companies AS c
                      ON c.synthetic_id = p.{counterparty_column.split('.')[-1]}
                     AND c.import_batch_id = p.import_batch_id
                    WHERE p.import_batch_id = ? AND {focal_column} = ?""",
                (batch_id, synthetic_id),
            ).fetchall()

        grouped: dict[tuple[str | None, str | None], dict[str, Any]] = defaultdict(
            lambda: {
                "amount": Decimal("0"),
                "amount_rows": 0,
                "count": 0,
                "count_rows": 0,
                "counterparties": set(),
            }
        )
        for row in rows:
            industry_code = row["mainokved_code"]
            industry_name = row["mainokved_name"] or "Unknown industry"
            bucket = grouped[(industry_code, industry_name)]
            counterparty_id = row["counterparty_id"]
            if counterparty_id:
                bucket["counterparties"].add(counterparty_id)
            amount = _to_decimal(row["pay_amt"])
            if amount is not None:
                bucket["amount"] += amount
                bucket["amount_rows"] += 1
            payment_count = _to_nonnegative_int(row["pay_cnt"])
            if payment_count is not None:
                bucket["count"] += payment_count
                bucket["count_rows"] += 1

        total_amount = sum((bucket["amount"] for bucket in grouped.values()), Decimal("0"))
        total_count = sum(bucket["count"] for bucket in grouped.values())
        sorted_groups = sorted(
            grouped.items(),
            key=lambda item: (item[1]["amount"], item[1]["count"], item[0][1] or ""),
            reverse=True,
        )
        for (industry_code, industry_name), bucket in sorted_groups[:limit]:
            amount_share = (
                float(bucket["amount"] / total_amount)
                if total_amount > 0 and bucket["amount_rows"]
                else None
            )
            count_share = (
                bucket["count"] / total_count
                if total_count > 0 and bucket["count_rows"]
                else None
            )
            exposures.append(
                IndustryExposure(
                    synthetic_id=synthetic_id,
                    direction=direction,  # type: ignore[arg-type]
                    industry_code=industry_code,
                    industry_name=industry_name or "Unknown industry",
                    payment_amount_total=bucket["amount"] if bucket["amount_rows"] else None,
                    payment_count_total=bucket["count"] if bucket["count_rows"] else None,
                    distinct_counterparty_count=len(bucket["counterparties"]),
                    amount_share=amount_share,
                    count_share=count_share,
                    contributing_synthetic_ids=sorted(bucket["counterparties"]),
                    calculation_basis=(
                        "Aggregated values in active anonymized dataset by counterparty MAINOKVED_CODE/MAINOKVED_NAME; "
                        "source rows do not include payment dates."
                    ),
                )
            )
    return exposures


def _counterparty_rollup(
    db: Database,
    batch_id: int,
    synthetic_id: str,
    direction: Direction,
) -> list[dict[str, Any]]:
    focal_column = "payer" if direction == "payer" else "beneficiary"
    counterparty_column = "beneficiary" if direction == "payer" else "payer"
    with db.connect() as connection:
        rows = connection.execute(
            f"""SELECT {counterparty_column} AS counterparty_id, pay_amt, pay_cnt
                FROM payment_edges
                WHERE import_batch_id = ? AND {focal_column} = ?""",
            (batch_id, synthetic_id),
        ).fetchall()

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"amount": Decimal("0"), "amount_rows": 0, "count": 0, "count_rows": 0}
    )
    for row in rows:
        counterparty = row["counterparty_id"]
        if not counterparty:
            continue
        amount = _to_decimal(row["pay_amt"])
        if amount is not None:
            grouped[counterparty]["amount"] += amount
            grouped[counterparty]["amount_rows"] += 1
        count = _to_nonnegative_int(row["pay_cnt"])
        if count is not None:
            grouped[counterparty]["count"] += count
            grouped[counterparty]["count_rows"] += 1
    total_amount = sum((item["amount"] for item in grouped.values()), Decimal("0"))
    result = []
    for counterparty, values in sorted(
        grouped.items(), key=lambda item: (item[1]["amount"], item[1]["count"], item[0]), reverse=True
    ):
        result.append(
            {
                "synthetic_id": counterparty,
                "payment_amount_total": str(values["amount"]) if values["amount_rows"] else None,
                "payment_count_total": values["count"] if values["count_rows"] else None,
                "amount_share": float(values["amount"] / total_amount) if total_amount > 0 and values["amount_rows"] else None,
            }
        )
    return result


def get_payment_network_summary(synthetic_id: str, db: Database, limit: int = 10) -> dict[str, Any]:
    """Return structural concentration and region/group context without trends."""

    batch_id = _active_batch_id(db)
    if batch_id is None:
        return {"available": False, "warning": "No imported company dataset is active."}

    with db.connect() as connection:
        target = connection.execute(
            """SELECT c.group_id, c.city, c.region, b.mock_data
               FROM synthetic_companies AS c
               JOIN import_batches AS b ON b.id = c.import_batch_id
               WHERE c.import_batch_id = ? AND c.synthetic_id = ?""",
            (batch_id, synthetic_id),
        ).fetchone()
        if not target:
            return {"available": False, "warning": f"Unknown synthetic ID: {synthetic_id}"}
        group_members = []
        if target["group_id"]:
            group_members = [
                row["synthetic_id"]
                for row in connection.execute(
                    """SELECT synthetic_id FROM synthetic_companies
                       WHERE import_batch_id = ? AND group_id = ? AND synthetic_id <> ?
                       ORDER BY synthetic_id""",
                    (batch_id, target["group_id"], synthetic_id),
                ).fetchall()
            ]
        counterparties = connection.execute(
            """SELECT p.payer, p.beneficiary,
                      COALESCE(p.pay_amt, '') AS pay_amt,
                      cp.region AS payer_region,
                      cb.region AS beneficiary_region
               FROM payment_edges AS p
               LEFT JOIN synthetic_companies AS cp
                 ON cp.import_batch_id = p.import_batch_id AND cp.synthetic_id = p.payer
               LEFT JOIN synthetic_companies AS cb
                 ON cb.import_batch_id = p.import_batch_id AND cb.synthetic_id = p.beneficiary
               WHERE p.import_batch_id = ? AND (p.payer = ? OR p.beneficiary = ?)""",
            (batch_id, synthetic_id, synthetic_id),
        ).fetchall()

    region_totals: dict[str, dict[str, Any]] = {
        "same_region": {"edge_count": 0, "amount": Decimal("0")},
        "other_region": {"edge_count": 0, "amount": Decimal("0")},
        "unknown_region": {"edge_count": 0, "amount": Decimal("0")},
    }
    for row in counterparties:
        other_region = row["beneficiary_region"] if row["payer"] == synthetic_id else row["payer_region"]
        if not other_region:
            region_bucket = "unknown_region"
        elif target["region"] and other_region == target["region"]:
            region_bucket = "same_region"
        else:
            region_bucket = "other_region"
        region_totals[region_bucket]["edge_count"] += 1
        amount = _to_decimal(row["pay_amt"])
        if amount is not None:
            region_totals[region_bucket]["amount"] += amount

    outgoing = _counterparty_rollup(db, batch_id, synthetic_id, "payer")
    incoming = _counterparty_rollup(db, batch_id, synthetic_id, "beneficiary")
    top_outgoing = outgoing[:limit]
    top_incoming = incoming[:limit]
    outgoing_top5_share = sum(item["amount_share"] or 0 for item in outgoing[:5])
    incoming_top5_share = sum(item["amount_share"] or 0 for item in incoming[:5])

    return {
        "available": True,
        "dataset_batch_id": batch_id,
        "mock_data": bool(target["mock_data"]),
        "group_id": target["group_id"],
        "group_members": group_members,
        "region": {"city": target["city"], "name": target["region"]},
        "region_counterparty_exposure": {
            key: {"edge_count": value["edge_count"], "payment_amount_total": str(value["amount"])}
            for key, value in region_totals.items()
        },
        "top_payers": top_incoming,
        "top_beneficiaries": top_outgoing,
        "concentration": {
            "top_five_beneficiary_amount_share": min(outgoing_top5_share, 1.0),
            "top_five_payer_amount_share": min(incoming_top5_share, 1.0),
            "basis": "Share of summed PAY_AMT among observed counterparties; absent dates prevent a time trend.",
        },
        "exposure_flags": [
            flag
            for flag, share in (
                ("beneficiary_top_five_share_over_80pct", outgoing_top5_share),
                ("payer_top_five_share_over_80pct", incoming_top5_share),
            )
            if share >= 0.8
        ],
        "temporal_trend": None,
        "time_period": None,
    }
