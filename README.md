# Agents Monorepo

This repository hosts multiple autonomous solutions as separate agents.

Each agent is isolated under `agents/<agent_name>/`, while all reusable infrastructure is centralized under `common/`.

## Repository Map

```text
Agents/
├── common/                       # shared config, clients, email, helpers, data
│   └── data/
│       └── watchlist.csv
├── agents/
│   ├── earnings_agent/           # earnings-specific logic, docs, and data
│   │   └── data/
│   │       └── email_preview.html
│   └── ratings_agent/            # analyst rating-change logic, docs, and state
│       └── data/                 # price_targets.snapshot.json (gitignored)
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

## Add A New Agent

1. Create `agents/<new_agent>/`.
2. Add:
   - `agent.py`
   - `prompts.py`
   - `main.py`
   - `README.md`
3. Reuse shared modules from `common/`.
4. Add an optional workflow in `.github/workflows/` if scheduled execution is needed.

## Quick Start

Current runnable agents:

```bash
python -m agents.earnings_agent.main
python -m agents.ratings_agent.main
```
