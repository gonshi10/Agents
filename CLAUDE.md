# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the earnings agent (from repo root; needs a populated .env)
python -m agents.earnings_agent.main

# Run the smoke test suite (plain script, not pytest — exits non-zero on failure)
python -m agents.earnings_agent.tests.test_agent

# Manual debug scripts that hit live APIs (require valid keys in .env)
python -m agents.earnings_agent.tests.test_ai_insights
python -m agents.earnings_agent.tests.debug_insights
python -m agents.earnings_agent.tests.debug_ai_insights
```

There is no linter or pytest configured. Tests are standalone scripts with a `main()` that returns an exit code; they do not use a test framework, so run them as modules (not `pytest`).

Setup: copy `env.example` to `.env` and fill in the values. `get_settings()` raises at startup if `FINNHUB_API_KEY`, `SMTP_USER`, `SMTP_PASS`, or `EMAIL_TO` are missing.

## Architecture

This is a **monorepo of autonomous agents**. The hard rule: agent-specific business logic lives under `agents/<name>/`; all shared integration code lives under `common/`. Always import shared components rather than copying them into an agent.

### Layout
- `common/config.py` — single `Settings` dataclass loaded once via `get_settings()` (`lru_cache`). All env access goes through here; agents never call `os.getenv` directly.
- `common/clients/` — API wrappers (`FinnhubClient`, `OpenAIClient`), each with its own built-in rate limiting.
- `common/email/sender.py` — `EmailSender`, SMTP multipart (plain + HTML).
- `common/watchlist.py` — `load_tickers()` reads the `Symbol` column from the watchlist CSV.
- `agents/earnings_agent/` — the only runnable agent. `agent.py` holds `EarningsAgent`; `prompts.py` holds the LLM templates; `main.py`/`__main__.py` are the entrypoints.

### Earnings agent flow (`EarningsAgent.run`)
1. Compute `target_date` — yesterday normally, 3 days ago when `TEST_MODE=true` (wider window so local runs find data).
2. For each watchlist ticker: fetch earnings calendar + filtered company news from Finnhub. Tickers with no earnings on the date are skipped.
3. Generate AI insights via `generate_batched_ai_insights` — one batched OpenAI call for all tickers, falling back to per-ticker calls (`run_with_fallback`) on failure.
4. Build HTML + plain-text email per ticker and send one email each.

### Key design points
- **AI is optional.** When `OPENAI_API_KEY` is unset, `OpenAIClient.is_enabled` is `False` and the agent still runs with non-AI fallback text. Guard any new OpenAI use behind `is_enabled`.
- **Rate limiting is client-side and stateful.** `FinnhubClient` (50/min) and `OpenAIClient` (3/min) self-throttle with `time.sleep`. `generate_individual_insights` also sleeps 10–15s between tickers. Long runtimes are expected by design.
- **AI output is unstructured text parsed by hand.** The model returns labeled sections (`EXECUTIVE SUMMARY`, `STRATEGIC ANALYSIS`, `RISK FACTORS`, `INVESTMENT RECOMMENDATION`, `EXPERT RECOMMENDATION`); `parse_structured_insights` splits on those headers. Changing the prompt headers in `prompts.py` requires updating that parser in lockstep.
- **Sector-aware prompting.** `get_company_sector` maps a ticker's Finnhub industry (with a hardcoded ticker fallback) to an "expert" persona injected into the prompt. Results cached per-run in `sector_cache`; insights cached in `insights_cache`.
- **Failures are swallowed, not raised.** Client methods catch exceptions, print a message, and return empty/`None`; callers check for falsy results. Preserve this so one bad ticker doesn't abort the run.

### Automation
`.github/workflows/earnings-agent.yml` runs the agent daily (cron `0 5 * * *`, ~midnight ET) on Python 3.12. All config comes from GitHub Actions secrets matching the env var names.

## Adding a new agent
Create `agents/<new_agent>/` with `agent.py`, `prompts.py`, `main.py`, and `README.md`; reuse `common/` modules; add a workflow under `.github/workflows/` if it needs scheduling. The `scaffold-new-agent` skill (see below) automates this scaffold.

## Claude Code infrastructure
Shared, team-checked-in config lives under `.claude/` (personal overrides go in the gitignored `.claude/settings.local.json`):
- **`.claude/settings.json`** — permission allowlist (the smoke test + read-only git) and a `deny` rule for reading `.env`. Wires the hooks below.
- **`.claude/hooks/protect-secrets.sh`** — PreToolUse guard that blocks editing/printing/`git add`-ing `.env` (defense-in-depth for the `deny` rule). `env.example` stays readable.
- **`.claude/hooks/prompts-parser-reminder.sh`** — PostToolUse reminder, on edits to any `agents/*/prompts.py`, that the section headers are parsed by hand and must change in lockstep with `parse_structured_insights`.
- **`.claude/skills/scaffold-new-agent/`** — skill that scaffolds a new agent per the convention above, reusing `common/`.
- **Worktrees** — `scripts/worktree.sh <branch>` creates a bootstrapped sibling worktree (own `venv` + copied `.env`) for parallel sessions; see `.claude/WORKTREES.md`.
