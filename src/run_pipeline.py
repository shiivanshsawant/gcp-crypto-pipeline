"""
Combined pipeline entrypoint for Cloud Run Jobs.

Cloud Run Jobs run one container to completion for one command — they don't
give you a shell to run two scripts back to back interactively. So instead of
calling fetch_coingecko.py and load_to_bq.py separately (like we do locally),
this module imports both and runs them in sequence.

Run directly:
    python -m src.run_pipeline
"""

import logging

from src.extract import fetch_coingecko
from src.load import load_to_bq
from src import validate

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=== Starting daily crypto pipeline run ===")

    logger.info("--- Phase 1-2: Extract + land in GCS ---")
    fetch_coingecko.run()

    logger.info("--- Phase 3: Load into BigQuery ---")
    load_to_bq.run()

    logger.info("--- Phase 6: Data quality checks ---")
    validate.run()  # raises DataQualityError on failure, which exits non-zero

    logger.info("=== Pipeline run complete ===")


if __name__ == "__main__":
    main()
