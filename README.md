# gcp-crypto-pipeline

An end-to-end **batch data pipeline** on Google Cloud Platform that pulls daily
cryptocurrency market data from the public [CoinGecko API](https://www.coingecko.com/en/api),
lands it in Cloud Storage, loads it into BigQuery, and transforms it with SQL
into analytics-ready tables — orchestrated by Cloud Scheduler + Cloud Run Jobs.

Built as a learning project to practice GCP tooling, Python, and SQL.

## Architecture

```
CoinGecko API
      │  (Python: requests)
      ▼
Cloud Storage (raw/crypto/YYYY-MM-DD/data.json)   <- immutable landing zone
      │  (Python: google-cloud-bigquery load job)
      ▼
BigQuery: raw dataset (raw_crypto_prices)
      │  (SQL: staging transforms — cast, dedupe, clean)
      ▼
BigQuery: staging dataset (stg_crypto_prices)
      │  (SQL: curated transforms — daily aggregates, % change, moving avg)
      ▼
BigQuery: curated dataset (curated_crypto_daily)
      │
      ▼
Looker Studio dashboard

Orchestration: Cloud Scheduler → triggers → Cloud Run Job (daily)
Monitoring: Cloud Logging + Cloud Monitoring alert on job failure
```

## Repo structure

```
├── src/
│   ├── extract/
│   │   └── fetch_coingecko.py   # pulls market data from CoinGecko, uploads raw JSON to GCS
│   ├── load/
│   │   └── load_to_bq.py        # loads raw JSON from GCS into BigQuery raw table
│   └── utils/
│       └── gcs_helpers.py       # shared GCS upload/download helpers
├── sql/
│   ├── staging/
│   │   └── stg_crypto_prices.sql
│   └── curated/
│       └── curated_crypto_daily.sql
├── schemas/
│   └── raw_crypto_schema.json   # explicit BigQuery schema for the raw table
├── tests/
│   └── test_fetch_coingecko.py
├── src/run_pipeline.py          # combined extract+load entrypoint, used by the container
├── Dockerfile                   # containerizes the pipeline for Cloud Run Jobs
├── .dockerignore
├── env-vars.yaml                # env vars for `gcloud run jobs update --env-vars-file`
├── infra/                       # (stretch goal) Terraform for GCS bucket / BQ datasets
├── .github/workflows/           # (stretch goal) CI: lint + test on push
├── requirements.txt
├── .env.example
├── .gitignore
└── LEARNINGS.md                 # debugging log — what broke, why, and the fix
```

## Setup

1. Create a GCP project, enable Cloud Storage + BigQuery APIs.
2. Create a GCS bucket and a BigQuery dataset (see `infra/` once added, or do it manually in console for now).
3. Copy `.env.example` to `.env` and fill in your project ID, bucket name, and dataset IDs.
4. `pip install -r requirements.txt`
5. Authenticate locally: `gcloud auth application-default login`
6. Run the extract script: `python src/extract/fetch_coingecko.py`
7. Run the load script: `python src/load/load_to_bq.py`
8. Run the SQL transforms in `sql/staging/` then `sql/curated/` (via BigQuery console, `bq` CLI, or a scheduled query).

## Deployment (Phase 5 — automated daily runs)

The pipeline runs automatically once a day with no manual steps, via Cloud
Run Jobs + Cloud Scheduler:

```bash
# Build and push the container image (via Cloud Build — no local Docker needed)
gcloud builds submit --tag us-docker.pkg.dev/<PROJECT_ID>/crypto-pipeline-repo/crypto-pipeline:latest .

# Create the Cloud Run Job
gcloud run jobs create crypto-pipeline-job \
  --image us-docker.pkg.dev/<PROJECT_ID>/crypto-pipeline-repo/crypto-pipeline:latest \
  --region us-central1 \
  --env-vars-file env-vars.yaml

# Schedule it to run daily at 1pm UTC
gcloud scheduler jobs create http crypto-pipeline-daily \
  --location us-central1 \
  --schedule="0 13 * * *" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/<PROJECT_ID>/jobs/crypto-pipeline-job:run" \
  --http-method=POST \
  --oauth-service-account-email="<PROJECT_NUMBER>-compute@developer.gserviceaccount.com"
```

The job's service account needs `roles/storage.objectAdmin`,
`roles/bigquery.dataEditor`, and `roles/bigquery.jobUser` to read/write GCS
and BigQuery.

## Build phases (progress checklist)

- [x] Phase 1 — Extract: Python script pulling from CoinGecko API
- [x] Phase 2 — Land raw data in Cloud Storage
- [x] Phase 3 — Load into BigQuery raw dataset
- [x] Phase 4 — SQL transforms (staging + curated), including dedup with
      `ROW_NUMBER()`, a trailing moving average with `AVG() OVER (...)`,
      and daily volume ranking with `RANK()`
- [x] Phase 5 — Containerized with Docker, deployed as a Cloud Run Job,
      scheduled daily with Cloud Scheduler — pipeline now runs fully
      automated with no manual steps
- [ ] Phase 6 — Monitoring & data quality checks
- [ ] Phase 7 — Looker Studio dashboard

See [LEARNINGS.md](./LEARNINGS.md) for a running log of what broke, why, and
what I learned fixing it along the way — real debugging notes, not a
retrospective cleanup.

## Why these tool choices

- **Cloud Storage before BigQuery**: keeps a raw, immutable copy of every day's
  pull. If a transform bug corrupts curated data, you can always replay from
  raw — this is standard data-lake practice.
- **Cloud Run Jobs over Cloud Functions**: Cloud Run Jobs are built for batch/
  scheduled work (no HTTP trigger needed, can run longer, easy to containerize
  the same code you test locally).
- **Cloud Scheduler over Airflow/Composer**: Composer is expensive to keep
  running for a single daily job. Cloud Scheduler + Cloud Run Jobs gets you
  real orchestration experience without the cost — Airflow is a good stretch
  goal once this is working end-to-end.
