"""Initialize SQL, import mock fixtures, and index the supplied corpora once."""

from __future__ import annotations

import json
from pathlib import Path

from .company_data import load_hackathon_data
from .db import Database
from .knowledge.ingest_alfa import ingest_alfa_folder
from .knowledge.ingest_methodology import ingest_methodology_sources

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PIPELINE_DIR.parent


def main() -> None:
    database = Database()
    database.initialize()
    companies = PIPELINE_DIR / "data/mock/df_Uid_data_hack.csv"
    relations = PIPELINE_DIR / "data/mock/df_Fid_Uid_link_hack.csv"
    import_summary = load_hackathon_data(companies, relations, database, mock_data=True)
    alpha = ingest_alfa_folder(REPOSITORY_DIR / "data/alfa_research",
                               PIPELINE_DIR / "news_analytics/knowledge/sources.json")
    methodology = ingest_methodology_sources(
        PIPELINE_DIR / "news_analytics/knowledge/methodology_sources.json",
        PIPELINE_DIR / "data/methodology_sources",
    )
    print(json.dumps({"import": import_summary.model_dump(mode="json"),
                      "alfa_research": alpha, "risk_methodology": methodology},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
