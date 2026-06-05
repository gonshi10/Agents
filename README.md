# Agents Monorepo

This repository hosts multiple autonomous solutions as separate agents.

Each agent is isolated under `agents/<agent_name>/`, while all reusable infrastructure is centralized under `common/`.

## Repository Map

```text
Agents/
├── common/                       # shared config, clients, email, helpers
├── agents/
│   └── earnings_agent/           # earnings-specific logic, docs, and data
│       └── data/
│           ├── watchlist.csv
│           └── email_preview.html
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

Current runnable agent:

```bash
python -m agents.earnings_agent.main
```
