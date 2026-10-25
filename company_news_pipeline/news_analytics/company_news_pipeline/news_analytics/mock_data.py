"""Generate deterministic, explicitly fabricated CSVs for local development."""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


COMPANY_COLUMNS = (
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

RELATION_COLUMNS = (
    "SYNTHETIC_F",
    "CITY_NAME",
    "RC_NAME",
    "SYNTHETIC_U",
    "BENEFICIARY",
    "PAYER",
    "PAY_AMT",
    "PAY_CNT",
)

_INDUSTRIES = (
    ("10.89", "Other food manufacturing"),
    ("25.11", "Manufacture of metal structures"),
    ("46.90", "Non-specialized wholesale trade"),
    ("41.20", "Construction of residential and non-residential buildings"),
    ("62.01", "Computer software development"),
    ("49.41", "Road freight transport"),
)
_LOCATIONS = (
    ("MOCK_CITY_A", "MOCK_REGION_A"),
    ("MOCK_CITY_B", "MOCK_REGION_B"),
    ("MOCK_CITY_C", "MOCK_REGION_C"),
    ("MOCK_CITY_D", "MOCK_REGION_D"),
)
_AGE_GRADES = ("up to 3 years", "3-5 years", "5-10 years", "over 10 years")
_SCALE_GRADES = ("1-5", "6-15", "16-50", "51-100", "101-250")
_REVENUE_GRADES = ("up to 10 mln RUB", "10-50 mln RUB", "50-250 mln RUB", "250 mln-1 bln RUB")


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def generate_mock_data(output_dir: str | Path, company_count: int = 24, seed: int = 20261025) -> tuple[Path, Path]:
    """Create two repeatable CSV fixtures containing synthetic-only values."""

    if company_count < len(_INDUSTRIES) * 2:
        raise ValueError(f"company_count must be at least {len(_INDUSTRIES) * 2} to create peer groups")

    output_dir = Path(output_dir)
    rng = random.Random(seed)
    companies: list[dict[str, str]] = []
    company_ids: list[str] = []
    company_industries: dict[str, tuple[str, str]] = {}

    for index in range(company_count):
        synthetic_id = f"MOCK_U_{index + 1:04d}"
        industry = _INDUSTRIES[index % len(_INDUSTRIES)]
        city, region = _LOCATIONS[index % len(_LOCATIONS)]
        company_ids.append(synthetic_id)
        company_industries[synthetic_id] = industry
        companies.append(
            {
                "SYNTHETIC_U": synthetic_id,
                "ORG_TYPE": "АО" if index % 5 == 0 else "ООО",
                "OKFS_NAME": "Частная собственность",
                "COMPANY_AGE_YEARS_GRADATION": _AGE_GRADES[(index // 2) % len(_AGE_GRADES)],
                "ECO_MARK_LABEL": ("рост", "зрелость", "стабильная деятельность")[index % 3],
                "MAINOKVED_CODE": industry[0],
                "MAINOKVED_NAME": industry[1],
                "NEGATIVEMARK": "1" if index % 13 == 0 else "0",
                "AMOUNT_WORKERS_FNS_GRADATION": _SCALE_GRADES[(index // 3) % len(_SCALE_GRADES)],
                "AMOUNT_WORKERS_SPARK_GRADATION": _SCALE_GRADES[(index // 4) % len(_SCALE_GRADES)],
                "CL_TYPE": "действующий клиент" if index % 4 else "потенциальный клиент",
                "CL_PRODUCT_RKO_MARK": str(index % 2),
                "CL_PRODUCT_GAR_MARK": str((index + 1) % 2),
                "CL_PRODUCT_LOA_MARK": str(index % 3 == 0 and 1 or 0),
                "CL_PRODUCT_LEA_MARK": str(index % 4 == 0 and 1 or 0),
                "CL_PRODUCT_DEP_MARK": str(index % 5 == 0 and 1 or 0),
                "CL_PRODUCT_ZPP_MARK": str(index % 3 == 1 and 1 or 0),
                "FTS_FLAG": str(index % 4 == 2 and 1 or 0),
                "FTS_COUNTRY_NAME": "Казахстан" if index % 4 == 2 else "",
                "FACTORING_MARK": str(index % 6 == 0 and 1 or 0),
                "REVENUE_COMPANY": _REVENUE_GRADES[(index // 2) % len(_REVENUE_GRADES)],
                "GROUP_ID": f"MOCK_GROUP_{index // 3 + 1:03d}" if index % 3 != 2 else "",
                "CITY": city,
                "REGION": region,
            }
        )

    relations: list[dict[str, str]] = []
    for index, synthetic_id in enumerate(company_ids):
        city, region = _LOCATIONS[index % len(_LOCATIONS)]
        for person_offset in range(2):
            relations.append(
                {
                    "SYNTHETIC_F": f"MOCK_F_{index * 2 + person_offset + 1:05d}",
                    "CITY_NAME": city,
                    "RC_NAME": region,
                    "SYNTHETIC_U": synthetic_id,
                    "BENEFICIARY": "",
                    "PAYER": "",
                    "PAY_AMT": "",
                    "PAY_CNT": "",
                }
            )

    payment_pairs: set[tuple[str, str]] = set()
    for index, payer in enumerate(company_ids):
        for offset in (1, 2, 5):
            beneficiary = company_ids[(index + offset) % len(company_ids)]
            if beneficiary == payer:
                continue
            payment_pairs.add((payer, beneficiary))

    for payer, beneficiary in sorted(payment_pairs):
        same_industry = company_industries[payer][0] == company_industries[beneficiary][0]
        amount = rng.randint(150_000, 2_500_000) if same_industry else rng.randint(60_000, 1_200_000)
        relations.append(
            {
                "SYNTHETIC_F": "",
                "CITY_NAME": "",
                "RC_NAME": "",
                "SYNTHETIC_U": "",
                "BENEFICIARY": beneficiary,
                "PAYER": payer,
                "PAY_AMT": str(amount),
                "PAY_CNT": str(rng.randint(1, 40)),
            }
        )

    company_path = output_dir / "df_Uid_data_hack.csv"
    relation_path = output_dir / "df_Fid_Uid_link_hack.csv"
    _write_csv(company_path, COMPANY_COLUMNS, companies)
    _write_csv(relation_path, RELATION_COLUMNS, relations)
    return company_path, relation_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic mock hackathon CSVs")
    default_output = Path(__file__).resolve().parents[1] / "data" / "mock"
    parser.add_argument("--output-dir", default=str(default_output), help="Directory for the mock CSV files")
    parser.add_argument("--company-count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20261025)
    args = parser.parse_args()
    company_path, relation_path = generate_mock_data(args.output_dir, args.company_count, args.seed)
    print(f"Generated mock company CSV: {company_path}")
    print(f"Generated mock relation/payment CSV: {relation_path}")
    print("All company and person identifiers are synthetic; all row values are fabricated.")


if __name__ == "__main__":
    main()
