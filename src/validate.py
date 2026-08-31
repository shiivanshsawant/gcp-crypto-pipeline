"""
Phase 6 — Data quality validation

Runs a handful of sanity checks against the BigQuery raw table right after
a load completes. Raises an exception if anything looks wrong, which causes
run_pipeline.py to exit non-zero — Cloud Run Jobs treats that as a failed
execution, which is what actually triggers the Cloud Monitoring alert set up
in Phase 6.

Deliberately simple checks. In a larger production pipeline these would
likely be a dedicated tool (e.g. Great Expectations, dbt tests) rather than
hand-rolled SQL, but hand-rolling them here is a good way to actually
understand what "data quality" means in concrete terms.
"""

import logging
import os
from datetime import date

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
BQ_DATASET_RAW = os.getenv("BQ_DATASET_RAW", "raw_crypto")
BQ_TABLE_RAW = os.getenv("BQ_TABLE_RAW", "crypto_prices")
EXPECTED_MIN_ROWS = int(os.getenv("COINGECKO_TOP_N", "100")) - 5  # allow a little slack


class DataQualityError(Exception):
    """Raised when a data quality check fails — deliberately distinct from
    other exceptions so logs/alerts can be filtered specifically for this."""


def check_row_count(client: bigquery.Client, run_date: date) -> int:
    """Fail if today's load has suspiciously few rows (e.g. a partial/failed API response)."""
    query = f"""
        SELECT COUNT(*) AS row_count
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET_RAW}.{BQ_TABLE_RAW}`
        WHERE _load_date = @run_date
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_date", "DATE", run_date.isoformat())]
    )
    result = list(client.query(query, job_config=job_config).result())
    row_count = result[0].row_count

    if row_count < EXPECTED_MIN_ROWS:
        raise DataQualityError(
            f"Row count check failed: got {row_count} rows for {run_date}, "
            f"expected at least {EXPECTED_MIN_ROWS}"
        )

    logger.info("Row count check passed: %d rows for %s", row_count, run_date)
    return row_count


def check_no_null_critical_fields(client: bigquery.Client, run_date: date) -> None:
    """Fail if any row is missing a field we absolutely need (id or price)."""
    query = f"""
        SELECT COUNT(*) AS null_count
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET_RAW}.{BQ_TABLE_RAW}`
        WHERE _load_date = @run_date
          AND (id IS NULL OR current_price IS NULL)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_date", "DATE", run_date.isoformat())]
    )
    result = list(client.query(query, job_config=job_config).result())
    null_count = result[0].null_count

    if null_count > 0:
        raise DataQualityError(
            f"Null check failed: {null_count} rows for {run_date} are missing id or current_price"
        )

    logger.info("Null check passed: no missing id/current_price for %s", run_date)


def check_no_extreme_prices(client: bigquery.Client, run_date: date) -> None:
    """
    Sanity-check against implausible prices (e.g. a parsing bug producing 0
    or a wildly inflated number). Not a precise business rule — just a
    guard against obviously broken data slipping through silently.
    """
    query = f"""
        SELECT COUNT(*) AS bad_price_count
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET_RAW}.{BQ_TABLE_RAW}`
        WHERE _load_date = @run_date
          AND (current_price <= 0 OR current_price > 10000000)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_date", "DATE", run_date.isoformat())]
    )
    result = list(client.query(query, job_config=job_config).result())
    bad_price_count = result[0].bad_price_count

    if bad_price_count > 0:
        raise DataQualityError(
            f"Price sanity check failed: {bad_price_count} rows for {run_date} "
            "have current_price <= 0 or implausibly high"
        )

    logger.info("Price sanity check passed for %s", run_date)


def run(run_date: date | None = None) -> None:
    run_date = run_date or date.today()

    if not GCP_PROJECT_ID:
        raise EnvironmentError("GCP_PROJECT_ID must be set")

    client = bigquery.Client(project=GCP_PROJECT_ID)

    logger.info("Running data quality checks for %s", run_date)
    check_row_count(client, run_date)
    check_no_null_critical_fields(client, run_date)
    check_no_extreme_prices(client, run_date)
    logger.info("All data quality checks passed for %s", run_date)


if __name__ == "__main__":
    run()
