"""Pull China's exports to selected African partners from UN Comtrade and load them into BigQuery.

Data source: UN Comtrade public preview API (no API key required, max 500 records per call).
One call is made per partner-year, which returns ~80-100 HS 2-digit chapter rows.

Usage:
    python ingest/comtrade_to_bq.py --dry-run          # fetch + save JSON to data/raw/ only
    python ingest/comtrade_to_bq.py                    # fetch + load to BigQuery
    python ingest/comtrade_to_bq.py --from-cache       # load previously saved JSON, no API calls

Configuration (env vars, see .env.example):
    GCP_PROJECT_ID   GCP project to load into (default: china-africa-trade)
    BQ_RAW_DATASET   raw dataset name (default: comtrade_raw)
    BQ_LOCATION      dataset location (default: EU)
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
PREVIEW_MAX_RECORDS = 500

REPORTER_CHINA = 156
PARTNERS = {504: "Morocco", 686: "Senegal", 384: "Cote d'Ivoire"}

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW_TABLE = "comtrade_exports"

# Subset of the API response kept in the raw table (descriptions are null in the preview API,
# names come from dbt seeds instead).
FIELDS = {
    "refYear": "INTEGER",
    "reporterCode": "INTEGER",
    "partnerCode": "INTEGER",
    "partner2Code": "INTEGER",
    "flowCode": "STRING",
    "classificationCode": "STRING",
    "cmdCode": "STRING",
    "customsCode": "STRING",
    "motCode": "INTEGER",
    "primaryValue": "FLOAT",
    "fobvalue": "FLOAT",
    "cifvalue": "FLOAT",
    "netWgt": "FLOAT",
    "isReported": "BOOLEAN",
    "isAggregate": "BOOLEAN",
}

log = logging.getLogger("comtrade")


def fetch_partner_year(partner_code: int, year: int, retries: int = 4) -> list[dict]:
    """Return China -> partner export rows by HS chapter for one year."""
    params = {
        "reporterCode": REPORTER_CHINA,
        "partnerCode": partner_code,
        "period": year,
        "cmdCode": "AG2",  # all HS 2-digit chapters
        "flowCode": "X",
        # Keep only the totals: no second partner, all customs procedures, all transport modes.
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=60)
            if resp.status_code == 429:
                raise requests.HTTPError("rate limited (429)")
            resp.raise_for_status()
            body = resp.json()
            if body.get("error"):
                raise RuntimeError(body["error"])
            rows = body.get("data")
            if rows is None:  # the API sometimes answers {} under load
                raise RuntimeError("empty response")
            if len(rows) >= PREVIEW_MAX_RECORDS:
                log.warning("partner %s year %s hit the %s-record cap; data may be truncated",
                            partner_code, year, PREVIEW_MAX_RECORDS)
            return rows
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            wait = 5 * attempt
            log.warning("partner %s year %s attempt %s failed (%s); retrying in %ss",
                        partner_code, year, attempt, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"giving up on partner {partner_code} year {year}")


def raw_path(partner_code: int, year: int) -> Path:
    return RAW_DIR / f"china_to_{partner_code}_{year}.json"


def fetch_all(years: range, pause: float) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for partner_code, name in PARTNERS.items():
        for year in years:
            rows = fetch_partner_year(partner_code, year)
            raw_path(partner_code, year).write_text(json.dumps(rows), encoding="utf-8")
            log.info("%-14s %s: %3d chapters", name, year, len(rows))
            time.sleep(pause)


def read_cache(years: range) -> list[dict]:
    ingested_at = datetime.now(timezone.utc).isoformat()
    records = []
    for partner_code in PARTNERS:
        for year in years:
            path = raw_path(partner_code, year)
            if not path.exists():
                raise FileNotFoundError(f"{path} missing; run without --from-cache first")
            for row in json.loads(path.read_text(encoding="utf-8")):
                record = {field: row.get(field) for field in FIELDS}
                record["_ingested_at"] = ingested_at
                records.append(record)
    return records


def load_to_bigquery(records: list[dict], project: str, dataset: str, location: str) -> None:
    from google.cloud import bigquery  # imported here so --dry-run works without GCP libs

    client = bigquery.Client(project=project, location=location)
    client.create_dataset(bigquery.Dataset(f"{project}.{dataset}"), exists_ok=True)

    schema = [bigquery.SchemaField(name, type_) for name, type_ in FIELDS.items()]
    schema.append(bigquery.SchemaField("_ingested_at", "TIMESTAMP"))
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        # Full refresh: the dataset is small and this keeps reruns idempotent
        # (and works in the BigQuery sandbox, which has no DML).
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    table_id = f"{project}.{dataset}.{RAW_TABLE}"
    client.load_table_from_json(records, table_id, job_config=job_config).result()
    log.info("loaded %d rows into %s", client.get_table(table_id).num_rows, table_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between API calls")
    parser.add_argument("--dry-run", action="store_true", help="fetch and save JSON, skip BigQuery")
    parser.add_argument("--from-cache", action="store_true", help="skip the API, load saved JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    years = range(args.start_year, args.end_year + 1)

    if not args.from_cache:
        fetch_all(years, args.pause)
    records = read_cache(years)
    log.info("%d rows ready", len(records))
    if args.dry_run:
        return

    project = os.environ.get("GCP_PROJECT_ID", "china-africa-trade")
    load_to_bigquery(
        records,
        project=project,
        dataset=os.environ.get("BQ_RAW_DATASET", "comtrade_raw"),
        location=os.environ.get("BQ_LOCATION", "EU"),
    )


if __name__ == "__main__":
    main()
