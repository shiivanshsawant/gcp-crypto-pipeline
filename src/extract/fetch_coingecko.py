"""
Phase 1 — Extract

Pulls the top N coins by market cap from the CoinGecko public API
(no API key required) and writes the raw JSON response to:
  1. a local file (data/raw/YYYY-MM-DD/coingecko_markets.json)
  2. a GCS bucket, under the same date-partitioned path

Run directly:
    python -m src.extract.fetch_coingecko
"""

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.utils.gcs_helpers import upload_file_to_gcs

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
TOP_N = int(os.getenv("COINGECKO_TOP_N", "100"))
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

MAX_RETRIES = 3
BACKOFF_SECONDS = 5


def fetch_market_data(top_n: int = TOP_N) -> list[dict]:
    """
    Call the CoinGecko /coins/markets endpoint and return the parsed JSON.

    Retries on transient failures (network errors, 5xx, and 429 rate limits)
    with simple linear backoff — CoinGecko's free tier rate-limits aggressively,
    so this matters more than it might for a paid API.
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": min(top_n, 250),  # API max per page is 250
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Fetching CoinGecko market data (attempt %d/%d)", attempt, MAX_RETRIES)
            response = requests.get(COINGECKO_URL, params=params, timeout=15)

            if response.status_code == 429:
                logger.warning("Rate limited by CoinGecko, backing off...")
                time.sleep(BACKOFF_SECONDS * attempt)
                continue

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("CoinGecko returned an empty or unexpected payload")

            logger.info("Fetched %d coin records", len(data))
            return data

        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning("Fetch attempt %d failed: %s", attempt, exc)
            time.sleep(BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"Failed to fetch CoinGecko data after {MAX_RETRIES} attempts") from last_error


def save_local(data: list[dict], run_date: date) -> Path:
    """Write raw JSON to a date-partitioned local path, mirroring the GCS layout."""
    out_dir = Path("data/raw") / run_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "coingecko_markets.json"

    payload = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "source": "coingecko",
        "record_count": len(data),
        "records": data,
    }

    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info("Saved raw data locally to %s", out_path)
    return out_path


def run(top_n: int = TOP_N, upload: bool = True) -> Path:
    """Full Phase 1 flow: fetch -> save locally -> upload to GCS."""
    run_date = date.today()
    data = fetch_market_data(top_n)
    local_path = save_local(data, run_date)

    if upload:
        if not GCS_BUCKET_NAME:
            raise EnvironmentError("GCS_BUCKET_NAME is not set — check your .env file")
        gcs_blob_path = f"raw/crypto/{run_date.isoformat()}/coingecko_markets.json"
        upload_file_to_gcs(local_path, GCS_BUCKET_NAME, gcs_blob_path)

    return local_path


if __name__ == "__main__":
    run()
