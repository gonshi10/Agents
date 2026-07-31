# Earnings Agent

The earnings agent monitors watchlist tickers for recent earnings events, enriches each report with company news and Wall Street context, generates senior-analyst-style AI insights, and sends email reports.

## What It Does

- Fetches earnings calendar data from Finnhub for the target date.
- Pulls and filters earnings-relevant company news.
- Enriches context with EPS/revenue surprise percentages, analyst recommendation trends, and price targets.
- Generates structured AI analysis with executive summary, strategic analysis, guidance outlook, risks, analyst conclusion, and investment recommendation.
- Sends one email report per ticker with earnings activity.

## Report Sections

Each email is structured top-down for quick reading:

1. **Verdict** — investment recommendation, expert type, and analyst conclusion
2. **Financial Results** — EPS and revenue with beat/miss badges and surprise vs estimate
3. **Analysis** — executive summary, strategic analysis, guidance outlook, risk factors
4. **Wall Street View** — factual analyst breakdown and price target range (when available)
5. **Recent News** — linked headlines from the earnings date

## Run

From repository root:

```bash
python -m agents.earnings_agent.main
```

## Requirements

- Python 3.8+
- Finnhub API key
- SMTP credentials for email delivery
- Optional OpenAI API key for AI insights

## Environment Variables

Copy `env.example` to `.env` and configure:

- `FINNHUB_API_KEY` (required)
- `OPENAI_API_KEY` (optional; AI is disabled when missing)
- `OPENAI_MODEL` (default: `gpt-4.1-mini`)
- `SMTP_HOST` (default: `smtp.gmail.com`)
- `SMTP_PORT` (default: `587`)
- `SMTP_USER` (required)
- `SMTP_PASS` (required)
- `EMAIL_TO` (required)
- `WATCHLIST_CSV` (default: `./common/data/watchlist.csv`)
- `TEST_MODE` (`true`/`false`, default: `false`)

## Watchlist Format

`WATCHLIST_CSV` should point to a CSV with a `Symbol` column:

```csv
Symbol
AAPL
MSFT
NVDA
```

Default location in this repo: `common/data/watchlist.csv`.

## Runtime Notes

- `TEST_MODE=true` checks a wider historical offset to make local verification easier.
- If `OPENAI_API_KEY` is missing, emails are still sent using non-AI fallback text.
- Shared rate limiting for Finnhub and OpenAI is handled via `common/clients`.
- AI context includes up to 5 full news headlines, analyst consensus, and price targets per ticker.

## Automation

GitHub Actions workflow: `.github/workflows/earnings-agent.yml`

It runs:

```bash
python -m agents.earnings_agent.main
```

## Troubleshooting

- Missing env vars: verify `.env` matches keys listed above.
- SMTP failures: validate host/port/user/password and provider app-password settings.
- No reports sent: verify the watchlist path and whether the target date had earnings events.

## Local Assets

- `agents/earnings_agent/data/email_preview.html`: static preview sample for the earnings email template.
- `common/data/watchlist.csv`: shared watchlist used by earnings and ratings agents by default.
