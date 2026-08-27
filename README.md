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
├── infra/                       # (stretch goal) Terraform for GCS bucket / BQ datasets
├── .github/workflows/           # (stretch goal) CI: lint + test on push
├── requirements.txt
├── .env.example
└── .gitignore
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

## Build phases (progress checklist)

- [x] Phase 1 — Extract: Python script pulling from CoinGecko API
- [x] Phase 2 — Land raw data in Cloud Storage
- [x] Phase 3 — Load into BigQuery raw dataset
- [ ] Phase 4 — SQL transforms (staging + curated)
- [ ] Phase 5 — Orchestrate with Cloud Scheduler + Cloud Run Jobs
- [ ] Phase 6 — Monitoring & data quality checks
- [ ] Phase 7 — Looker Studio dashboard

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
