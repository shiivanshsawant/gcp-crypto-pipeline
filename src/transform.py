"""
Phase 7 support — Automate the SQL transforms

Runs the staging and curated SQL scripts (sql/staging/, sql/curated/)
directly against BigQuery using the Python client, so the dashboard-facing
curated table refreshes automatically as part of the daily pipeline run
instead of requiring a manual paste into the BigQuery console.

Run directly:
    python -m src.transform
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
BQ_LOCATION = os.getenv("BQ_LOCATION", "US")

# sql/ sits at the repo root, one level up from src/
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def run_sql_file(client: bigquery.Client, sql_path: Path, description: str) -> None:
    sql_text = sql_path.read_text()

    logger.info("Running %s — %s", sql_path.name, description)
    query_job = client.query(sql_text, location=BQ_LOCATION)
    query_job.result()  # blocks until the query finishes (or raises on failure)

    # total_bytes_processed is exactly what BigQuery bills you on — logging
    # it every run makes cost visible instead of invisible, which matters
    # a lot once you're paying for compute instead of using free credits.
    bytes_processed = query_job.total_bytes_processed or 0
    logger.info(
        "%s completed. Bytes processed: %d (%.4f MB)",
        sql_path.name, bytes_processed, bytes_processed / 1_000_000,
    )


def run() -> None:
    if not GCP_PROJECT_ID:
        raise EnvironmentError("GCP_PROJECT_ID must be set")

    client = bigquery.Client(project=GCP_PROJECT_ID)

    run_sql_file(
        client,
        SQL_DIR / "staging" / "stg_crypto_prices.sql",
        "dedupe + cast raw data into staging",
    )
    run_sql_file(
        client,
        SQL_DIR / "curated" / "curated_crypto_daily.sql",
        "build curated analytics table (moving avg, volume rank, movement flag)",
    )


if __name__ == "__main__":
    run()
