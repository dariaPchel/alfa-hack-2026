"""CSV schema inspection and import for the anonymized hackathon data."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .db import Database
from .models import CompanyProfile, ImportFileSummary, ImportSummary


COMPANY_FIELDS = (
    "SYNTHETIC_U",
    "ORG_TYPE",
    "OKFS_NAME",
    "COMPANY_AGE_YEARS_GRADATION",
    "ECO_MARK_LABEL",
    "MAINOKVED_CODE",
    "MAINOKVED_NAME",
    "NEGATIVEMARK",
    "AMOUNT_WORKERS_FNS_GRADATION",
    "AMOUNT_WORKERS_SPARK_GRADATION",
    "CL_TYPE",
    "CL_PRODUCT_RKO_MARK",
    "CL_PRODUCT_GAR_MARK",
    "CL_PRODUCT_LOA_MARK",
    "CL_PRODUCT_LEA_MARK",
    "CL_PRODUCT_DEP_MARK",
    "CL_PRODUCT_ZPP_MARK",
    "FTS_FLAG",
    "FTS_COUNTRY_NAME",
    "FACTORING_MARK",
    "REVENUE_COMPANY",
    "GROUP_ID",
    "CITY",
    "REGION",
)
COMPANY_MODEL_FIELDS = tuple(
    "synthetic_id" if field == "SYNTHETIC_U" else field.lower() for field in COMPANY_FIELDS
)
RELATION_FIELDS = {"SYNTHETIC_F", "CITY_NAME", "RC_NAME", "SYNTHETIC_U"}
PAYMENT_FIELDS = {"BENEFICIARY", "PAYER", "PAY_AMT", "PAY_CNT"}


class DatasetImportError(ValueError):
    """Raised when an input file cannot be interpreted safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str | None]]]:
    if not path.is_file():
        raise DatasetImportError(f"CSV file does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        if not reader.fieldnames:
            raise DatasetImportError(f"CSV has no header row: {path}")
        headers = [str(header).strip().lstrip("\ufeff") for header in reader.fieldnames]
        duplicate_headers = sorted({header for header in headers if headers.count(header) > 1})
        normalized_duplicates = sorted(
            {header.upper() for header in headers if [item.upper() for item in headers].count(header.upper()) > 1}
        )
        if duplicate_headers or normalized_duplicates:
            duplicates = sorted(set(duplicate_headers) | set(normalized_duplicates))
            raise DatasetImportError(f"CSV has duplicate column names in {path.name}: {duplicates}")
        rows: list[dict[str, str | None]] = []
        for raw_row in reader:
            row: dict[str, str | None] = {}
            for original_key, value in raw_row.items():
                if original_key is None:
                    continue
                key = str(original_key).strip().lstrip("\ufeff")
                cleaned = value.strip() if isinstance(value, str) else None
                row[key] = cleaned or None
            rows.append(row)
    return headers, rows


def _uppercase_row(row: dict[str, str | None]) -> dict[str, str | None]:
    return {key.strip().upper(): value for key, value in row.items()}


def _is_mock_input(company_path: Path, relation_path: Path) -> bool:
    markers = {"mock", "mocks", "demo", "fixture", "fixtures"}
    paths = (company_path, relation_path)
    return any(part.casefold() in markers for path in paths for part in path.parts)


def _warning(
    warnings: list[dict[str, Any]],
    filename: str,
    warning_code: str,
    message: str,
    row_number: int | None = None,
    column_name: str | None = None,
) -> None:
    warnings.append(
        {
            "filename": filename,
            "row_number": row_number,
            "column_name": column_name,
            "warning_code": warning_code,
            "message": message,
            "created_at": _utc_now(),
        }
    )


def load_hackathon_data(
    company_csv: str | Path,
    links_csv: str | Path,
    db: Database,
    *,
    mock_data: bool | None = None,
) -> ImportSummary:
    """Validate and import both hackathon CSVs as one immutable dataset batch.

    The latest successful batch is activated transactionally. Older batches
    remain in SQLite so replacing generated fixtures with supplied source CSVs
    does not destroy the earlier import record or source data.
    """

    company_path = Path(company_csv).expanduser().resolve()
    relation_path = Path(links_csv).expanduser().resolve()
    started_at = _utc_now()
    warnings: list[dict[str, Any]] = []

    company_headers, company_rows = _read_rows(company_path)
    normalized_company_headers = {header.upper() for header in company_headers}
    if "SYNTHETIC_U" not in normalized_company_headers:
        raise DatasetImportError(f"Company CSV must contain SYNTHETIC_U: {company_path.name}")

    relation_headers, relation_rows = _read_rows(relation_path)
    normalized_relation_headers = {header.upper() for header in relation_headers}
    if not normalized_relation_headers.intersection(RELATION_FIELDS | PAYMENT_FIELDS):
        raise DatasetImportError(
            "Relation CSV must contain person-company fields or PAYER/BENEFICIARY payment fields"
        )
    relation_optional = sorted((RELATION_FIELDS | PAYMENT_FIELDS) - normalized_relation_headers)
    unexpected_relation = sorted(normalized_relation_headers - RELATION_FIELDS - PAYMENT_FIELDS)
    for name in unexpected_relation:
        _warning(
            warnings,
            relation_path.name,
            "unexpected_column",
            "Unknown relation column retained in source_row_json",
            column_name=name,
        )

    expected_company = set(COMPANY_FIELDS)
    company_optional = sorted(expected_company - {"SYNTHETIC_U"} - normalized_company_headers)
    unexpected_company = sorted(normalized_company_headers - expected_company)
    for name in unexpected_company:
        _warning(warnings, company_path.name, "unexpected_column", "Unknown company column retained in source_row_json", column_name=name)

    company_records: list[tuple[str, dict[str, str | None], dict[str, Any]]] = []
    seen_ids: set[str] = set()
    skipped_company_rows = 0
    for row_number, raw_row in enumerate(company_rows, start=2):
        row = _uppercase_row(raw_row)
        synthetic_id = row.get("SYNTHETIC_U")
        if not synthetic_id:
            skipped_company_rows += 1
            _warning(warnings, company_path.name, "missing_synthetic_id", "Row skipped: SYNTHETIC_U is empty", row_number)
            continue
        if synthetic_id in seen_ids:
            raise DatasetImportError(
                f"Duplicate SYNTHETIC_U {synthetic_id!r} in {company_path.name} at CSV row {row_number}"
            )
        seen_ids.add(synthetic_id)
        values = {field: row.get(field) for field in COMPANY_FIELDS}
        try:
            profile = CompanyProfile.model_validate(values)
        except Exception as exc:
            raise DatasetImportError(
                f"Invalid company row {row_number} for SYNTHETIC_U {synthetic_id!r}: {exc}"
            ) from exc
        company_records.append(
            (synthetic_id, profile.model_dump(mode="json"), {key: value for key, value in raw_row.items()})
        )

    if not company_records:
        raise DatasetImportError("Company CSV contains no valid rows with SYNTHETIC_U")

    company_ids = {item[0] for item in company_records}
    relation_records: list[dict[str, Any]] = []
    skipped_relation_rows = 0
    imported_relation_rows = 0
    for row_number, raw_row in enumerate(relation_rows, start=2):
        row = _uppercase_row(raw_row)
        has_link = bool(row.get("SYNTHETIC_F") and row.get("SYNTHETIC_U"))
        has_payment = bool(row.get("PAYER") and row.get("BENEFICIARY"))
        if not has_link and not has_payment:
            if any(raw_row.values()):
                _warning(
                    warnings,
                    relation_path.name,
                    "unrecognized_relation_row",
                    "Row skipped: no complete person-company link or payment edge",
                    row_number,
                )
            skipped_relation_rows += 1
            continue

        recognized = False
        if has_link:
            linked_company = row["SYNTHETIC_U"]
            if linked_company not in company_ids:
                _warning(
                    warnings,
                    relation_path.name,
                    "unknown_link_company",
                    f"Person-company link references an ID absent from this company batch: {linked_company}",
                    row_number,
                    "SYNTHETIC_U",
                )
            relation_records.append(
                {
                    "kind": "person_company",
                    "synthetic_f": row["SYNTHETIC_F"],
                    "city_name": row.get("CITY_NAME"),
                    "rc_name": row.get("RC_NAME"),
                    "synthetic_id": linked_company,
                    "source_row_json": raw_row,
                }
            )
            recognized = True

        if has_payment:
            payer = row["PAYER"]
            beneficiary = row["BENEFICIARY"]
            for endpoint, label in ((payer, "PAYER"), (beneficiary, "BENEFICIARY")):
                if endpoint not in company_ids:
                    _warning(
                        warnings,
                        relation_path.name,
                        "unknown_payment_company",
                        f"Payment edge endpoint is absent from this company batch: {endpoint}",
                        row_number,
                        label,
                    )
            amount = row.get("PAY_AMT")
            if amount:
                try:
                    Decimal(amount.replace(",", "."))
                except (InvalidOperation, ValueError):
                    _warning(warnings, relation_path.name, "invalid_payment_amount", "PAY_AMT is preserved as text but is not numeric", row_number, "PAY_AMT")
            count = row.get("PAY_CNT")
            if count:
                try:
                    if int(count) < 0:
                        raise ValueError("negative payment count")
                except ValueError:
                    _warning(warnings, relation_path.name, "invalid_payment_count", "PAY_CNT is preserved as text but is not a non-negative integer", row_number, "PAY_CNT")
            relation_records.append(
                {
                    "kind": "payment",
                    "beneficiary": beneficiary,
                    "payer": payer,
                    "pay_amt": amount,
                    "pay_cnt": count,
                    "source_row_json": raw_row,
                }
            )
            recognized = True

        if recognized:
            imported_relation_rows += 1

    has_mock_data = _is_mock_input(company_path, relation_path) if mock_data is None else mock_data
    db.initialize()
    company_hash = _sha256(company_path)
    relation_hash = _sha256(relation_path)
    finished_at = _utc_now()
    summary_payload: dict[str, Any] = {
        "company_rows_imported": len(company_records),
        "relation_rows_imported": imported_relation_rows,
        "person_company_links": sum(record["kind"] == "person_company" for record in relation_records),
        "payment_edges": sum(record["kind"] == "payment" for record in relation_records),
        "warnings": warnings,
    }

    with db.connect() as connection:
        cursor = connection.execute(
            """INSERT INTO import_batches (
                   company_filename, relations_filename, company_sha256,
                   relations_sha256, mock_data, started_at, completed_at,
                   status, summary_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company_path.name,
                relation_path.name,
                company_hash,
                relation_hash,
                int(has_mock_data),
                started_at,
                finished_at,
                "completed",
                json.dumps(summary_payload, ensure_ascii=False),
            ),
        )
        batch_id = int(cursor.lastrowid)

        company_placeholders = ", ".join("?" for _ in range(len(COMPANY_MODEL_FIELDS) + 2))
        company_columns_sql = ", ".join((*COMPANY_MODEL_FIELDS, "source_row_json", "import_batch_id"))
        insert_company_sql = (
            f"INSERT INTO synthetic_companies ({company_columns_sql}) VALUES ({company_placeholders})"
        )
        for _, values, source_row in company_records:
            connection.execute(
                insert_company_sql,
                (
                    *(values[field] for field in COMPANY_MODEL_FIELDS),
                    json.dumps(source_row, ensure_ascii=False),
                    batch_id,
                ),
            )

        for record in relation_records:
            if record["kind"] == "person_company":
                connection.execute(
                    """INSERT INTO person_company_links (
                           synthetic_f, city_name, rc_name, synthetic_id,
                           source_row_json, import_batch_id
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record["synthetic_f"],
                        record["city_name"],
                        record["rc_name"],
                        record["synthetic_id"],
                        json.dumps(record["source_row_json"], ensure_ascii=False),
                        batch_id,
                    ),
                )
            else:
                connection.execute(
                    """INSERT INTO payment_edges (
                           beneficiary, payer, pay_amt, pay_cnt,
                           source_row_json, import_batch_id
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record["beneficiary"],
                        record["payer"],
                        record["pay_amt"],
                        record["pay_cnt"],
                        json.dumps(record["source_row_json"], ensure_ascii=False),
                        batch_id,
                    ),
                )

        for warning in warnings:
            connection.execute(
                """INSERT INTO schema_warnings (
                       import_batch_id, filename, row_number, column_name,
                       warning_code, message, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    warning["filename"],
                    warning["row_number"],
                    warning["column_name"],
                    warning["warning_code"],
                    warning["message"],
                    warning["created_at"],
                ),
            )

        connection.execute(
            """INSERT INTO active_dataset (singleton_id, import_batch_id, activated_at)
               VALUES (1, ?, ?)
               ON CONFLICT(singleton_id) DO UPDATE SET
                   import_batch_id = excluded.import_batch_id,
                   activated_at = excluded.activated_at""",
            (batch_id, finished_at),
        )

    company_summary = ImportFileSummary(
        filename=company_path.name,
        sha256=company_hash,
        rows_seen=len(company_rows),
        rows_imported=len(company_records),
        rows_skipped=skipped_company_rows,
        missing_optional_fields=company_optional,
        unexpected_fields=unexpected_company,
    )
    relation_summary = ImportFileSummary(
        filename=relation_path.name,
        sha256=relation_hash,
        rows_seen=len(relation_rows),
        rows_imported=imported_relation_rows,
        rows_skipped=skipped_relation_rows,
        missing_optional_fields=relation_optional,
        unexpected_fields=unexpected_relation,
    )
    return ImportSummary(
        batch_id=batch_id,
        mock_data=has_mock_data,
        companies=company_summary,
        relations=relation_summary,
        warnings=[item["message"] for item in warnings],
        started_at=started_at,
        completed_at=finished_at,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the anonymized hackathon CSV files")
    default_data = Path(__file__).resolve().parents[1] / "data" / "mock"
    parser.add_argument("--companies", default=str(default_data / "df_Uid_data_hack.csv"))
    parser.add_argument("--relations", default=str(default_data / "df_Fid_Uid_link_hack.csv"))
    parser.add_argument("--db", default=None, help="SQLite path; defaults to NEWS_ANALYTICS_DB or data/news_analytics.sqlite3")
    parser.add_argument("--mock-data", action="store_true", help="Mark the imported batch as fabricated mock data")
    args = parser.parse_args()

    summary = load_hackathon_data(
        args.companies,
        args.relations,
        Database(args.db),
        mock_data=True if args.mock_data else None,
    )
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
