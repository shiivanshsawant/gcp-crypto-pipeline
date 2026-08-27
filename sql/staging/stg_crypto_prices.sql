-- Phase 4a — Staging transform
--
-- Cleans the raw table: dedupes (in case a job reran for the same day),
-- filters out junk records, and casts to consistent types.
-- Run this as a scheduled query, or manually via `bq query` / BQ console.
--
-- Replace `your_project` with your actual GCP project id.

CREATE OR REPLACE TABLE `your_project.staging_crypto.stg_crypto_prices` AS

WITH deduped AS (
  SELECT
    *,
    -- If the same coin+load_date appears more than once (e.g. a rerun),
    -- keep only the most recently extracted version.
    ROW_NUMBER() OVER (
      PARTITION BY id, _load_date
      ORDER BY _extracted_at DESC
    ) AS row_num
  FROM `your_project.raw_crypto.crypto_prices`
)

SELECT
  id                                          AS coin_id,
  UPPER(symbol)                               AS symbol,
  name                                        AS coin_name,
  current_price                               AS price_usd,
  market_cap                                  AS market_cap_usd,
  market_cap_rank,
  total_volume                                AS volume_24h_usd,
  high_24h                                    AS high_24h_usd,
  low_24h                                     AS low_24h_usd,
  price_change_24h                            AS price_change_24h_usd,
  ROUND(price_change_percentage_24h, 4)       AS price_change_pct_24h,
  ROUND(price_change_percentage_7d_in_currency, 4) AS price_change_pct_7d,
  circulating_supply,
  total_supply,
  ath                                         AS all_time_high_usd,
  ath_date,
  last_updated,
  _load_date                                  AS load_date
FROM deduped
WHERE row_num = 1
  AND current_price IS NOT NULL
  AND market_cap_rank IS NOT NULL;
