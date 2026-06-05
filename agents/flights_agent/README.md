# Flights Agent

Watches a watchlist of flight routes and emails **one digest** when a fare is worth knowing about.

## What It Does
- Loads routes from a CSV (`Origin, Destination, DepartMonth`, plus optional `ReturnMonth, MaxPrice, OneWay`).
- Fetches the current cheapest fare per route from the free Travelpayouts / Aviasales Data API.
- Alerts when **either** trigger fires:
  - **Target price** — the fare is at or below the route's `MaxPrice`.
  - **Price drop** — the fare fell by ≥ `FLIGHTS_PRICE_DROP_PCT` vs the last-seen price (persisted in a JSON snapshot between runs).
- Sends a single consolidated digest email (optional AI deal commentary per route).

## Run
```bash
# from repo root, with a populated .env
python -m agents.flights_agent.main

# offline smoke test (no network)
python -m agents.flights_agent.tests.test_agent
```

## Requirements
- Python 3.12
- `FLIGHTS_API_TOKEN` — free token from a [Travelpayouts](https://www.travelpayouts.com/) account (Profile → API tokens).
- SMTP credentials + `EMAIL_TO` (shared with the other agents).
- `OPENAI_API_KEY` is **optional** — without it the agent still runs and emails plain deal info (no AI commentary).
- A `FINNHUB_API_KEY` must be present in the environment because `get_settings()` requires it, even though this agent does not use Finnhub.

## Environment Variables
| Var | Default | Notes |
|-----|---------|-------|
| `FLIGHTS_API_TOKEN` | _(unset)_ | Required for live runs; if unset the agent is a no-op. |
| `FLIGHTS_WATCHLIST_CSV` | `./agents/flights_agent/data/routes.csv` | Route watchlist. |
| `FLIGHTS_PRICE_SNAPSHOT` | `./agents/flights_agent/data/prices.snapshot.json` | Last-seen prices for drop detection. |
| `FLIGHTS_PRICE_DROP_PCT` | `10` | Min % drop vs snapshot to alert. |
| `FLIGHTS_CURRENCY` | `usd` | Fare currency. |

## Watchlist Format
```
Origin,Destination,DepartMonth,ReturnMonth,MaxPrice,OneWay
TLV,JFK,2026-09,2026-09,650,false
TLV,LON,2026-08,,200,true
```
`DepartMonth`/`ReturnMonth` use `YYYY-MM` (whole-month cheapest) or `YYYY-MM-DD`. Leave `ReturnMonth` blank for one-way.

## Runtime Notes
- **Price-drop alerts begin on a route's second run** (the first run only seeds the snapshot). Target-price alerts work on the first run.
- Failures are swallowed per route — one bad route never aborts the run.
- The Travelpayouts data reflects the cheapest fares users found in the last ~48h.

## Automation
`.github/workflows/flights-agent.yml` runs daily (cron `0 5 * * *`). An `actions/cache` step persists the price snapshot across ephemeral runners. All config comes from GitHub Actions secrets matching the env var names.
