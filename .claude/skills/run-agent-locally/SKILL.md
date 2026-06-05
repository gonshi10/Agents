---
name: run-agent-locally
description: Exercise an agent locally the safe way — run its offline smoke test first, then a real or TEST_MODE run only when intended. Use when asked to run, test, or debug earnings_agent / ratings_agent / flights_agent locally.
---

# Run an agent locally

Each agent is run as a module from the repo root and reads config from `.env`. A real run of
`main` **sends real email** via `EmailSender`, so default to the offline smoke test and only do a
live run when the user clearly wants one.

## Key facts

- **Run an agent (live, sends email):** `python -m agents.<name>.main` from the repo root with a
  populated `.env`.
- **`TEST_MODE=true`** widens the earnings window — target date becomes 3 days ago instead of
  yesterday — so local runs actually find data. It's parsed via `_as_bool` (`config.py:82`) and
  passed to `agent.run(test_mode=...)` (`earnings_agent/main.py:16`).
- **Offline smoke tests** (no live APIs, exit non-zero on failure). These are **plain scripts, not
  pytest** — run them as modules:
  - `python -m agents.earnings_agent.tests.test_agent`
  - `python -m agents.ratings_agent.tests.test_agent`
  - `python -m agents.flights_agent.tests.test_agent`
- **Live-API debug scripts** (need valid keys in `.env`) for AI-insight troubleshooting:
  `python -m agents.earnings_agent.tests.test_ai_insights`, `... .debug_insights`,
  `... .debug_ai_insights`.
- **AI is optional.** With `OPENAI_API_KEY` unset, `OpenAIClient.is_enabled` is `False` and the
  agent runs with non-AI fallback text — it does not crash.

## Steps

1. **Resolve which agent** the user means (earnings / ratings / flights).
2. **Default to the safe path:** run that agent's `tests/test_agent` as a module and report the
   exit code. This needs no API keys and sends no email.
3. **Only on explicit request, do a live run:** confirm `.env` is populated, **warn that it will
   send a real email**, then run `python -m agents.<name>.main`. For the earnings agent, suggest
   prefixing `TEST_MODE=true` so it finds recent data.
4. **For AI-insight problems**, point to the live debug scripts above (they require valid keys and
   will hit the OpenAI/Finnhub APIs).

## Verification

- Running this skill against, e.g., the flights agent runs
  `python -m agents.flights_agent.tests.test_agent` and surfaces its pass/fail exit code without
  sending any email.
