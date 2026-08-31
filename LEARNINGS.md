# Build Log & Learnings

A running log of what broke, why, and what I learned fixing it. Kept intentionally
raw — this is meant to show real debugging process, not just a finished product.

---

## Phase 1-3: Extract → GCS → BigQuery

**What I built:** a Python extraction script pulling live crypto market data from
the CoinGecko API, landing raw JSON in Cloud Storage, then loading it into
BigQuery via a load job.

**Key decision — why NDJSON, not raw JSON, for the BigQuery load:**
BigQuery's load jobs read newline-delimited JSON so they can stream and
parallelize reads (one line = one row = one unit of work). A single nested
JSON object (like CoinGecko's actual API response) can't be split or streamed
the same way — the whole structure has to be parsed before you know where one
record ends and the next begins. Reshaping raw → NDJSON is a very common ELT
pattern and now something I actually understand rather than just did.

**Bug — project ID typo:** `.env` had `end-pipeline-506819` instead of
`end-to-end-pipeline-506819`, causing a `404 NotFound` on `create_dataset`.
Good reminder that GCP project IDs are validated server-side with zero fuzzy
matching — a single dropped substring fails loudly, which is actually a
feature, not a bug.

## Phase 4: SQL transforms (staging + curated)

**Key decision — why dedupe with `ROW_NUMBER()` instead of `DISTINCT`:**
`DISTINCT` only removes exact-duplicate rows. Our raw table can have two
non-identical rows for the same coin/day (different `_extracted_at`
timestamps if the pipeline reruns), so `DISTINCT` wouldn't catch it.
`ROW_NUMBER() OVER (PARTITION BY id, _load_date ORDER BY _extracted_at DESC)`
+ `WHERE row_num = 1` explicitly keeps only the freshest version per
coin/day, which is the actual business rule I wanted.

**Real bug this caught:** I accidentally ran the load job for 8/30 twice
(once manually, once via a Cloud Run Job test). Raw table ended up with 200
rows for that date instead of 100. Rather than being a problem, this was a
great forcing function to actually verify the dedup logic works — staging
correctly collapsed it back to 100 rows. This is exactly the failure mode
the staging layer exists to protect against, and now I've seen it happen for
real, not just in theory.

**Window function gotcha — 7-day moving average with sparse dates:**
`AVG() OVER (... ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)` averages the last
7 *rows that exist* per coin, not the last 7 *calendar days*. If the pipeline
skips a day, the average silently treats the data as if it were dense. Fine
for a portfolio project running daily, but in production I'd want to join
against a generated date-spine to make gaps explicit rather than silent.

## Phase 5: Containerize + orchestrate (Cloud Run Jobs + Cloud Scheduler)

**No Docker Desktop locally → used Cloud Build instead:** rather than
install and configure Docker Desktop (WSL2 setup on Windows can be its own
project), used `gcloud builds submit` to build and push the image entirely
in the cloud. Worth knowing both paths exist — Cloud Build is genuinely the
better choice for occasional builds; local Docker pays off more if you're
iterating on the image constantly.

**Bug — env vars silently merged into one variable:**
`gcloud run jobs create ... --set-env-vars KEY1=val1,KEY2=val2,...` looked
correct when typed in PowerShell, but only `KEY1` was actually created — its
value became the entire rest of the comma-separated string, mashed together.
Confirmed via Cloud Logging, which showed the container crashing with
`GCS_BUCKET_NAME is not set` even though it had clearly been "set" in the
command. Root cause: PowerShell's handling of the comma-separated flag didn't
match what `gcloud`'s parser expected.

**Fix:** moved environment variables into a separate `env-vars.yaml` file and
used `--env-vars-file` instead of inline `--set-env-vars`. This sidesteps
shell-specific comma/quoting quirks entirely — a good general lesson: prefer
file-based config over long inline flag strings when a CLI supports both,
especially across different shells.

**IAM — least privilege in practice:** rather than rely on the default
Compute service account's broad `roles/editor`, explicitly granted only
`storage.objectAdmin`, `bigquery.dataEditor`, and `bigquery.jobUser` — the
minimum the pipeline actually needs. In a real production setup I'd go
further and use a dedicated service account instead of the default compute
one, so a compromised pipeline can't touch anything outside its own scope.

## Phase 6: Data quality checks + alerting

**What I built:** three validation checks (`src/validate.py`) that run after
every load — row count, null check on critical fields, and a price sanity
check — wired into `run_pipeline.py` so a failed check raises a
`DataQualityError`, which exits the container non-zero. A Cloud Logging
log-based metric (`pipeline-run-failures`) counts ERROR-severity logs from
the job, and a Cloud Monitoring alert policy emails me when that metric goes
above 0.

**Verified the whole chain fires for real, not just in theory:** temporarily
set `COINGECKO_TOP_N=99999` in `env-vars.yaml` so `check_row_count` would
fail on purpose (100 actual rows vs. ~99994 expected), redeployed, and
triggered a manual execution. Confirmed:

1. The job failed with `DataQualityError` in the logs
2. Cloud Run marked the execution as failed (`0 tasks completed successfully`)
3. An alert email arrived within about a minute, correctly showing the job
   name, project, and the "Crypto pipeline job failed — check Cloud Run Job
   logs" documentation text I'd set on the policy

**Thing I learned reading the alert email:** the metric value shown wasn't a
raw count (e.g. "1 failure") but a rate — `0.0167 ≈ 1/60`, i.e. roughly one
failure event per second averaged over the 60-second alerting window. That's
just how Cloud Monitoring reports log-based counter metrics by default
(rate, not raw count) — good to know so I don't misread it as "1.6% of runs
failed" or something equally wrong.

Reverted `COINGECKO_TOP_N` back to 100 afterward and confirmed a normal run
succeeds again before moving on.

---

## Next up

- [ ] Phase 7 — Looker Studio dashboard on curated data
