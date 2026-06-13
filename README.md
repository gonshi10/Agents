# Agents Monorepo

This repository hosts multiple autonomous solutions as separate agents.

Each agent is isolated under `agents/<agent_name>/`, while all reusable infrastructure is centralized under `common/`.

## Setup

- Python 3.12
- Install dependencies: `pip install -r requirements.txt`
- Copy `env.example` to `.env` and populate values
- Required for all agents: `FINNHUB_API_KEY`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
- Optional by agent:
  - `OPENAI_API_KEY` for AI insights (agents still run with non-AI fallback text)
  - `FLIGHTS_API_TOKEN` for `flights_agent` (unset means no-op)
  - `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` for `techstack_agent` (unset means no-op)
- For full env details, see each agent README under `agents/<name>/README.md`

## Repository Map

```text
Agents/
├── common/                       # shared config, clients, email, helpers, data
│   └── data/
│       └── watchlist.csv
├── scripts/
│   ├── worktree.sh
│   └── generate_sp500_companies.py
├── .claude/                      # shared Claude Code config, hooks, skills
│   ├── CLAUDE.md
│   └── skills/
├── agents/
│   ├── earnings_agent/           # earnings-specific logic, docs, and data
│   │   └── data/
│   │       └── email_preview.html
│   ├── ratings_agent/            # analyst rating-change logic, docs, and state
│   │   └── data/                 # price_targets.snapshot.json (gitignored)
│   ├── flights_agent/            # flight price-drop watcher, docs, and state
│   │   └── data/                 # routes.csv + prices.snapshot.json (gitignored)
│   └── techstack_agent/          # hiring-language technology trend watcher
│       └── data/                 # companies.csv + tech_mentions.snapshot.json (gitignored)
├── env.example
└── .github/workflows/
```

## Design Rules

- Keep business logic inside each agent directory.
- Keep shared integration code in `common/` only.
- Avoid hardcoded repeated values across agents.
- Prefer importing shared components over copying implementation.

## Agents

- `agents/earnings_agent`  
  Detailed docs: [`agents/earnings_agent/README.md`](agents/earnings_agent/README.md)
- `agents/ratings_agent`  
  Alerts on analyst rating-consensus and price-target changes.
  Detailed docs: [`agents/ratings_agent/README.md`](agents/ratings_agent/README.md)
- `agents/flights_agent`  
  Watches a watchlist of flight routes and emails a digest on price drops or target-price hits.
  Detailed docs: [`agents/flights_agent/README.md`](agents/flights_agent/README.md)
- `agents/techstack_agent`  
  Monitors monthly job-posting technology adoption (products + vendors, not languages) and sends one digest on meaningful trends.
  Detailed docs: [`agents/techstack_agent/README.md`](agents/techstack_agent/README.md)

## Scripts

- `scripts/worktree.sh` creates a bootstrapped sibling worktree for parallel sessions; see `.claude/WORKTREES.md`.
- `scripts/generate_sp500_companies.py` merges top-200 S&P 500 companies into `agents/techstack_agent/data/companies.csv`.

## Claude Code Tooling

Shared Claude Code guidance and automation live in `.claude/`.

- Main contributor guide: `.claude/CLAUDE.md`
- Hooks: `protect-secrets.sh`, `prompts-parser-reminder.sh`
- Skills: `scaffold-new-agent`, `run-agent-locally`, `sync-prompts-parser`, `add-agent-config`, `format-agent-email`

## Add A New Agent

1. Create `agents/<new_agent>/`.
2. Add:
   - `agent.py`
   - `prompts.py`
   - `main.py`
   - `__main__.py`
   - `README.md`
   - `tests/test_agent.py`
3. Reuse shared modules from `common/`.
4. Add an optional workflow in `.github/workflows/` if scheduled execution is needed.
5. Prefer using `.claude/skills/scaffold-new-agent/SKILL.md` to scaffold the package consistently.

## Quick Start

Current runnable agents:

```bash
python -m agents.earnings_agent.main
python -m agents.ratings_agent.main
python -m agents.flights_agent.main
python -m agents.techstack_agent.main

# standalone smoke tests (modules, not pytest)
python -m agents.earnings_agent.tests.test_agent
python -m agents.ratings_agent.tests.test_agent
python -m agents.flights_agent.tests.test_agent
python -m agents.techstack_agent.tests.test_agent
```

Tests are standalone scripts with `main()` exit codes; run them as modules, not with `pytest`.
