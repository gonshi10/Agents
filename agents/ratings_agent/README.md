# Ratings Agent

Alerts when Wall Street analyst sentiment on a watchlist ticker shifts — an
upgrade/downgrade in the recommendation consensus, or a material move in the
analyst price target. Only tickers with a change get an email, so most runs may
send nothing.

## Run

```bash
# from repo root, with a populated .env
python -m agents.ratings_agent.main

# smoke test (imports, env vars, offline detection logic; exits non-zero on failure)
python -m agents.ratings_agent.tests.test_agent
```

## How detection works

- **Recommendation consensus — stateful.** Finnhub `/stock/recommendation`
  returns *monthly aggregated* analyst counts. The agent computes a weighted
  consensus score `(2*strongBuy + buy - sell - 2*strongSell) / total` for the
  latest and prior months and flags an UPGRADE/DOWNGRADE when the change exceeds
  `REC_SCORE_THRESHOLD` (default 0.15). The last notified alert is stored as
  `lastRecAlert` in the snapshot so the same month-over-month shift is not
  emailed again on every run.
- **Price target — stateful.** Finnhub `/stock/price-target` is a current
  snapshot with no history, so the last-seen mean target is persisted to
  `RATINGS_PT_SNAPSHOT` (default `agents/ratings_agent/data/price_targets.snapshot.json`)
  and compared on the next run. A move of `PT_PCT_THRESHOLD` (default 5%) or more
  flags a RAISED/CUT. The first run for a ticker has no baseline, so it only
  records the snapshot — price-target alerts begin on the second run.

Thresholds live at the top of `agent.py`.

## Requirements / env vars

Same shared config as the earnings agent (see repo `env.example`):

- Required: `FINNHUB_API_KEY`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
- Optional: `OPENAI_API_KEY` / `OPENAI_MODEL` (AI insights; agent runs with
  fallback text when unset), `SMTP_HOST`, `SMTP_PORT`, `TEST_MODE`
- `WATCHLIST_CSV` — defaults to `./common/data/watchlist.csv`
- `RATINGS_PT_SNAPSHOT` — path to the price-target snapshot file

The watchlist CSV uses a single `Symbol` column (read by `common/watchlist.py`).

## Automation

`.github/workflows/ratings-agent.yml` runs daily (cron `0 5 * * *`, Python 3.12).
Because GitHub Actions runners are ephemeral, the snapshot (price targets and
`lastRecAlert` dedup keys) is persisted between runs via **`actions/cache`**. All
config comes from GitHub Actions secrets matching the env var names.
