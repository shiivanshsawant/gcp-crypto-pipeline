"""
Phase 3 — Load into BigQuery

Takes the raw JSON pulled by fetch_coingecko.py, reshapes it into
newline-delimited JSON (the format BigQuery load jobs want), stages that
in GCS, then runs a BigQuery load job against the explicit schema in
schemas/raw_crypto_schema.json.

Run directly (loads today's local raw file by default):
    python -m src.load.load_to_bq
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from src.utils.gcs_helpers import upload_file_to_gcs

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
BQ_DATASET_RAW = os.getenv("BQ_DATASET_RAW", "raw_crypto")
BQ_TABLE_RAW = os.getenv("BQ_TABLE_RAW", "crypto_prices")
BQ_LOCATION = os.getenv("BQ_LOCATION", "US")

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "raw_crypto_schema.json"

# Fields we keep from each CoinGecko record — must match schemas/raw_crypto_schema.json
KEEP_FIELDS = [
    "id", "symbol", "name", "current_price", "market_cap", "market_cap_rank",
    "total_volume", "high_24h", "low_24h", "price_change_24h",
    "price_change_percentage_24h", "price_change_percentage_7d_in_currency",
    "circulating_supply", "total_supply", "ath", "ath_date", "last_updated",
]


def load_local_raw(run_date: date) -> dict:
    local_path = Path("data/raw") / run_date.isoformat() / "coingecko_markets.json"
    if not local_path.exists():
        raise FileNotFoundError(
            f"No local raw file at {local_path} — run fetch_coingecko.py first, "
            "or pass a different run_date."
        )
    with open(local_path) as f:
        return json.load(f)


def to_ndjson_rows(raw_payload: dict, run_date: date) -> list[dict]:
    """Flatten CoinGecko records to just the fields we care about and add pipeline metadata."""
    extracted_at = raw_payload.get("extracted_at", datetime.now(timezone.utc).isoformat())
    rows = []
    for record in raw_payload["records"]:
        row = {field: record.get(field) for field in KEEP_FIELDS}
        row["_extracted_at"] = extracted_at
        row["_load_date"] = run_date.isoformat()
        rows.append(row)
    return rows


def write_ndjson(rows: list[dict], run_date: date) -> Path:
    out_dir = Path("data/processed") / run_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "coingecko_markets.ndjson"

    with open(out_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    logger.info("Wrote %d NDJSON rows to %s", len(rows), out_path)
    return out_path


def load_ndjson_to_bigquery(gcs_uri: str) -> None:
    client = bigquery.Client(project=GCP_PROJECT_ID)

    dataset_ref = bigquery.DatasetReference(GCP_PROJECT_ID, BQ_DATASET_RAW)
    client.create_dataset(dataset_ref, exists_ok=True)  # no-op if it already exists
    table_ref = dataset_ref.table(BQ_TABLE_RAW)

    with open(SCHEMA_PATH) as f:
        schema = [
            bigquery.SchemaField(field["name"], field["type"], mode=field.get("mode", "NULLABLE"))
            for field in json.load(f)
        ]

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    logger.info("Starting BigQuery load job: %s -> %s.%s", gcs_uri, BQ_DATASET_RAW, BQ_TABLE_RAW)
    load_job = client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config, location=BQ_LOCATION)
    load_job.result()  # blocks until the job finishes (or raises on failure)

    table = client.get_table(table_ref)
    logger.info("Load complete. Table %s now has %d rows.", BQ_TABLE_RAW, table.num_rows)


def run(run_date: date | None = None) -> None:
    run_date = run_date or date.today()

    if not GCP_PROJECT_ID or not GCS_BUCKET_NAME:
        raise EnvironmentError("GCP_PROJECT_ID and GCS_BUCKET_NAME must be set in .env")

    raw_payload = load_local_raw(run_date)
    rows = to_ndjson_rows(raw_payload, run_date)
    ndjson_path = write_ndjson(rows, run_date)

    gcs_blob_path = f"processed/crypto/{run_date.isoformat()}/coingecko_markets.ndjson"
    gcs_uri = upload_file_to_gcs(ndjson_path, GCS_BUCKET_NAME, gcs_blob_path)

    load_ndjson_to_bigquery(gcs_uri)


if __name__ == "__main__":
    run()
