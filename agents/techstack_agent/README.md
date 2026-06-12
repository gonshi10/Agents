# Techstack Agent

Tracks technology adoption signals from job postings and emails one monthly digest
when meaningful trends are detected. Focuses on technology products, their vendor
companies, and which tracked employers are adopting them — programming languages
are excluded.

## What It Does
- Loads tracked companies from `companies.csv` (hand-curated rows + top-200 S&P 500 merge).
- Runs on a **monthly** schedule (1st of each month via GitHub Actions).
- Fetches job postings from the last 30 days via Adzuna per company query.
- Extracts technology keyword mentions (frameworks, platforms, infra — not languages).
- Compares mention-share changes against a versioned snapshot to detect rising/falling trends.
- Uses OpenAI at runtime to identify vendor companies and adoption narratives.
- Sends one digest email when meaningful trends are detected.

## Run
```bash
# from repo root, with a populated .env
python -m agents.techstack_agent.main

# offline smoke test (no network)
python -m agents.techstack_agent.tests.test_agent
```

## Requirements
- Python 3.12
- `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` for live posting fetches
- Shared SMTP vars (`SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`)
- `OPENAI_API_KEY` is optional; when unset the agent still sends non-AI fallback text
- `FINNHUB_API_KEY` is still required by global `get_settings()` even though this agent does not use Finnhub

## Environment Variables
| Var | Default | Notes |
|-----|---------|-------|
| `TECHSTACK_WATCHLIST_CSV` | `./agents/techstack_agent/data/companies.csv` | Company watchlist. |
| `TECHSTACK_SNAPSHOT` | `./agents/techstack_agent/data/tech_mentions.snapshot.json` | Versioned snapshot of last-seen technology shares. |
| `TECHSTACK_TREND_THRESHOLD` | `20` | Min share-point delta to flag rising/falling. |
| `TECHSTACK_LOOKBACK_DAYS` | `30` | Job posting lookback window (monthly runs). |
| `ADZUNA_APP_ID` | _(unset)_ | Adzuna API app id. |
| `ADZUNA_APP_KEY` | _(unset)_ | Adzuna API app key. |

## Watchlist Format
```csv
Company,Ticker,SearchQuery,Sector
Apple,AAPL,Apple software engineer,Technology
Microsoft,MSFT,Microsoft software engineer,Technology
Stripe,,Stripe backend engineer,Fintech
Anthropic,,Anthropic machine learning engineer,AI
```

`Ticker` can be blank for private companies. `SearchQuery` is used directly in
the jobs API.

## Snapshot Versioning

The snapshot file includes a `snapshot_version` field. When the version changes
(e.g. after switching from daily to monthly cadence), the first run establishes a
baseline without sending spurious trend alerts.

## Regenerating S&P 500 Top-200 Merge

The watchlist is intentionally merged, not replaced:
- Existing hand-curated rows stay at the top.
- Top-200 S&P 500 companies by market cap are appended.
- Duplicates are skipped by ticker/name.

Generate or refresh the merged file:

```bash
python3 scripts/generate_sp500_companies.py
```

Preview counts without writing:

```bash
python3 scripts/generate_sp500_companies.py --dry-run
```

Quota note: a full run over ~200+ companies can exceed Adzuna free-tier limits
because each company currently fetches two result pages.
