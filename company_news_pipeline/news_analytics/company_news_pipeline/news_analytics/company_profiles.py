"""Company profile lookup enriched with dataset and network provenance."""

from __future__ import annotations

import json
from typing import Any

from .db import Database
from .models import CompanyProfile
from .payment_network import get_counterparty_industries, get_payment_network_summary


def get_company_profile(synthetic_id: str, db: Database) -> CompanyProfile | None:
    """Load the selected company from the active imported dataset batch."""

    with db.connect() as connection:
        row = connection.execute(
            """SELECT c.*, b.mock_data, b.company_filename, b.relations_filename,
                      b.company_sha256, b.relations_sha256, b.completed_at
               FROM active_dataset AS a
               JOIN synthetic_companies AS c
                 ON c.import_batch_id = a.import_batch_id
               JOIN import_batches AS b ON b.id = a.import_batch_id
               WHERE a.singleton_id = 1 AND c.synthetic_id = ?""",
            (synthetic_id,),
        ).fetchone()
    if row is None:
        return None

    values = dict(row)
    source_row = json.loads(values.pop("source_row_json") or "{}")
    mock_data = bool(values.pop("mock_data"))
    company_filename = values.pop("company_filename")
    relations_filename = values.pop("relations_filename")
    company_hash = values.pop("company_sha256")
    relations_hash = values.pop("relations_sha256")
    completed_at = values.pop("completed_at")
    batch_id = values.pop("import_batch_id")
    profile = CompanyProfile.model_validate(values)

    expected_fields = set(type(profile).model_fields)
    expected_fields.discard("synthetic_id")
    expected_fields.discard("source_metadata")
    present_source_fields = {key.lower() for key in source_row}
    missing_fields = sorted(field for field in expected_fields if field.lower() not in present_source_fields)
    exposures = get_counterparty_industries(synthetic_id, db)
    network_summary = get_payment_network_summary(synthetic_id, db)
    profile.source_metadata = {
        "dataset_batch_id": batch_id,
        "mock_data": mock_data,
        "source_files": {
            "company_csv": company_filename,
            "relations_csv": relations_filename,
        },
        "source_hashes": {
            "company_csv_sha256": company_hash,
            "relations_csv_sha256": relations_hash,
        },
        "imported_at": completed_at,
        "missing_optional_fields": missing_fields,
        "network_summary": network_summary,
        "top_counterparty_industries": [item.model_dump(mode="json") for item in exposures],
        "synthetic_person_ids_are_internal_only": True,
    }
    return profile
