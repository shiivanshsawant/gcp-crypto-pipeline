"""
Shared Cloud Storage helpers.

Uses Application Default Credentials — run `gcloud auth application-default login`
locally, or rely on the attached service account when running on Cloud Run.
"""

import logging
from pathlib import Path

from google.cloud import storage

logger = logging.getLogger(__name__)


def upload_file_to_gcs(local_path: Path, bucket_name: str, blob_path: str) -> str:
    """
    Upload a local file to GCS and return the gs:// URI.

    blob_path is the destination path *within* the bucket, e.g.
    'raw/crypto/2026-08-27/coingecko_markets.json'
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    blob.upload_from_filename(str(local_path))

    gcs_uri = f"gs://{bucket_name}/{blob_path}"
    logger.info("Uploaded %s -> %s", local_path, gcs_uri)
    return gcs_uri


def download_blob_to_file(bucket_name: str, blob_path: str, local_path: Path) -> Path:
    """Download a GCS blob to a local path. Useful for debugging/reprocessing."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(local_path))

    logger.info("Downloaded gs://%s/%s -> %s", bucket_name, blob_path, local_path)
    return local_path
