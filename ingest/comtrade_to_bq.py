"""Extract China's exports to selected African partners from UN Comtrade and load them into BigQuery.

Data source: UN Comtrade public preview API (no API key required, max 500 records per call).
One call is made per partner-year, which returns ~80-100 HS 2-digit chapter rows.

BigQuery is the system of record for raw data: every record is stored untouched as JSON together
with its extraction timestamp and request parameters, and each extraction is *appended*, so
revisions published by Comtrade are kept. dbt picks the latest extraction per partner-year.
The local data/raw/ folder is only a developer cache (e.g. to reload without calling the API).

Usage:
    python ingest/comtrade_to_bq.py                    # extract from the API and load to BigQuery
    python ingest/comtrade_to_bq.py --dry-run          # extract to data/raw/ only
    python ingest/comtrade_to_bq.py --from-cache       # load data/raw/ without calling the API

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
RAW_TABLE = "comtrade_records"

log = logging.getLogger("comtrade")


def request_params(partner_code: int, year: int) -> dict:
    return {
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


def fetch_partner_year(partner_code: int, year: int, retries: int = 4) -> dict:
    """Return one extraction: China -> partner export rows by HS chapter for one year, with metadata."""
    params = request_params(partner_code, year)
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
            return {
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "source_url": API_URL,
                "request_params": params,
                "records": rows,
            }
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            wait = 5 * attempt
            log.warning("partner %s year %s attempt %s failed (%s); retrying in %ss",
                        partner_code, year, attempt, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"giving up on partner {partner_code} year {year}")


def cache_path(partner_code: int, year: int) -> Path:
    return RAW_DIR / f"china_to_{partner_code}_{year}.json"


def extract_all(years: range, pause: float) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for partner_code, name in PARTNERS.items():
        for year in years:
            extraction = fetch_partner_year(partner_code, year)
            cache_path(partner_code, year).write_text(json.dumps(extraction), encoding="utf-8")
            log.info("%-14s %s: %3d chapters", name, year, len(extraction["records"]))
            time.sleep(pause)


def read_cache(years: range) -> list[dict]:
    """Flatten cached extractions into one BigQuery row per record."""
    rows = []
    for partner_code in PARTNERS:
        for year in years:
            path = cache_path(partner_code, year)
            if not path.exists():
                raise FileNotFoundError(f"{path} missing; run without --from-cache first")
            extraction = json.loads(path.read_text(encoding="utf-8"))
            for record in extraction["records"]:
                rows.append({
                    "extracted_at": extraction["extracted_at"],
                    "source_url": extraction["source_url"],
                    "request_params": extraction["request_params"],
                    "partner_code": partner_code,
                    "period": year,
                    "record": record,
                })
    return rows


def load_to_bigquery(rows: list[dict], project: str, dataset: str, location: str) -> None:
    from google.cloud import bigquery  # imported here so --dry-run works without GCP libs

    client = bigquery.Client(project=project, location=location)
    client.create_dataset(bigquery.Dataset(f"{project}.{dataset}"), exists_ok=True)
    table_id = f"{project}.{dataset}.{RAW_TABLE}"

    # Skip extractions that are already loaded (e.g. re-running --from-cache), so appends stay idempotent.
    try:
        loaded = {
            (r.partner_code, r.period, r.extracted_at)
            for r in client.query(
                f"select distinct partner_code, period, extracted_at from `{table_id}`"
            ).result()
        }
    except Exception as exc:  # table doesn't exist yet
        if "Not found" not in str(exc):
            raise
        loaded = set()
    new_rows = [
        row for row in rows
        if (row["partner_code"], row["period"], datetime.fromisoformat(row["extracted_at"])) not in loaded
    ]
    if not new_rows:
        log.info("nothing new to load into %s", table_id)
        return

    loaded_at = datetime.now(timezone.utc).isoformat()
    for row in new_rows:
        row["loaded_at"] = loaded_at

    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("extracted_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("source_url", "STRING"),
            bigquery.SchemaField("request_params", "JSON"),
            bigquery.SchemaField("partner_code", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("period", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("record", "JSON", description="Untouched Comtrade API record"),
        ],
        # Append-only: load jobs (not DML) also work in the BigQuery sandbox.
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    client.load_table_from_json(new_rows, table_id, job_config=job_config).result()
    log.info("appended %d rows to %s (%d total)",
             len(new_rows), table_id, client.get_table(table_id).num_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between API calls")
    parser.add_argument("--dry-run", action="store_true", help="extract to data/raw/, skip BigQuery")
    parser.add_argument("--from-cache", action="store_true", help="skip the API, load data/raw/")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    years = range(args.start_year, args.end_year + 1)

    if not args.from_cache:
        extract_all(years, args.pause)
    rows = read_cache(years)
    log.info("%d records ready", len(rows))
    if args.dry_run:
        return

    load_to_bigquery(
        rows,
        project=os.environ.get("GCP_PROJECT_ID", "china-africa-trade"),
        dataset=os.environ.get("BQ_RAW_DATASET", "comtrade_raw"),
        location=os.environ.get("BQ_LOCATION", "EU"),
    )


if __name__ == "__main__":
    main()
