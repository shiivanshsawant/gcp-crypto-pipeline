-- Phase 4b — Curated transform
--
-- Builds the analytics-ready table: adds a 7-day moving average of price,
-- ranks coins by daily volume, and flags top gainers/losers.
-- This is the table Looker Studio (Phase 7) will read from.
--
-- Replace `your_project` with your actual GCP project id.

CREATE OR REPLACE TABLE `your_project.curated_crypto.curated_crypto_daily` AS

SELECT
  coin_id,
  symbol,
  coin_name,
  load_date,
  price_usd,
  market_cap_usd,
  market_cap_rank,
  volume_24h_usd,
  price_change_pct_24h,
  price_change_pct_7d,

  -- 7-day moving average of price, per coin, ordered by date.
  -- ROWS BETWEEN gives a true trailing window rather than a full-partition average.
  AVG(price_usd) OVER (
    PARTITION BY coin_id
    ORDER BY UNIX_DATE(load_date)
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ) AS price_7d_moving_avg,

  -- Daily rank by trading volume — highest volume = rank 1.
  RANK() OVER (
    PARTITION BY load_date
    ORDER BY volume_24h_usd DESC
  ) AS volume_rank_for_day,

  -- Simple gainer/loser flag for quick dashboard filtering.
  CASE
    WHEN price_change_pct_24h >= 5  THEN 'strong_gainer'
    WHEN price_change_pct_24h <= -5 THEN 'strong_loser'
    ELSE 'stable'
  END AS daily_movement_flag

FROM `your_project.staging_crypto.stg_crypto_prices`
QUALIFY volume_rank_for_day <= 100  -- keep it to top 100 by volume per day
ORDER BY load_date DESC, volume_rank_for_day ASC;
