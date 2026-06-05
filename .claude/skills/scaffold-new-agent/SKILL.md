---
name: scaffold-new-agent
description: Scaffold a new agent under agents/<name>/ following the monorepo convention — reuses common/ integration code, mirrors the earnings_agent layout, and guards optional AI behind OpenAIClient.is_enabled. Use when the user wants to create/add a new agent in this repo.
---

# Scaffold a new agent

Create a new autonomous agent under `agents/<name>/` that follows this repo's hard rule:
**agent-specific business logic lives under `agents/<name>/`; all shared integration code
is imported from `common/` — never copied.**

## Steps

1. **Get the agent name.** Ask the user for a snake_case name (e.g. `dividend_agent`) if
   not given. Refuse names that collide with an existing dir under `agents/`.

2. **Create the package layout**, mirroring `agents/earnings_agent/`:

   ```
   agents/<name>/
     __init__.py        # empty (package marker)
     agent.py           # the <Name>Agent class
     prompts.py         # LLM templates + section headers (if the agent uses AI)
     main.py            # main() entrypoint: load settings, build agent, run
     __main__.py        # `from .main import main` so `python -m agents.<name>` works
     README.md          # what it does / how to run / requirements
     tests/
       __init__.py
       test_agent.py    # standalone smoke test with main() returning an exit code
   ```

3. **Reuse `common/` — do not reimplement.** Import the shared pieces the agent needs:

   ```python
   from common.config import Settings, get_settings   # never call os.getenv directly
   from common.clients.finnhub import FinnhubClient    # built-in 50/min rate limiting
   from common.clients.openai_client import OpenAIClient  # built-in 3/min rate limiting
   from common.email.sender import EmailSender         # SMTP multipart (plain + HTML)
   from common.watchlist import load_tickers           # reads Symbol column from CSV
   ```

   Construct clients from `Settings` exactly as `agents/earnings_agent/agent.py:21-35`
   does (pass `settings.finnhub_api_key`, `settings.openai_api_key`, SMTP fields, etc.).

4. **Make AI optional.** Guard every OpenAI call behind `self.openai.is_enabled`
   (pattern at `agents/earnings_agent/agent.py:42`). When the key is unset the agent must
   still run with non-AI fallback text — never crash because AI is off.

5. **Swallow per-item failures.** Follow the repo norm: client/agent methods catch
   exceptions, print a message, and return empty/`None`; callers check for falsy results
   so one bad ticker never aborts the whole run. Do not let a single failure raise out of
   `run()`.

6. **If the agent uses structured AI output**, keep the prompt section headers in
   `prompts.py` and any hand-written parser in lockstep (see the earnings agent's
   `parse_structured_insights`). A repo hook reminds you on edits to `prompts.py`.

7. **`main.py` entrypoint** mirrors `agents/earnings_agent/main.py`:

   ```python
   from __future__ import annotations
   import sys
   from common.config import get_settings
   from .agent import <Name>Agent

   def main() -> None:
       try:
           settings = get_settings()
           agent = <Name>Agent(settings)
           agent.run(test_mode=settings.test_mode)
       except Exception as exc:
           print(f"❌ Fatal error: {exc}")
           sys.exit(1)

   if __name__ == "__main__":
       main()
   ```

8. **Scheduling (optional).** If the agent should run on a schedule, add
   `.github/workflows/<name>.yml` modeled on `.github/workflows/earnings-agent.yml`
   (Python 3.12, cron, config from GitHub Actions secrets matching the env var names). If
   the agent needs new config, add the field to the `Settings` dataclass in
   `common/config.py` and to `env.example` — do not read env vars directly in the agent.

9. **Verify** the skeleton imports cleanly before handing back:

   ```bash
   python -c "import agents.<name>.agent"
   python -m agents.<name>.tests.test_agent   # standalone script; exits non-zero on fail
   ```

## Notes
- Tests are plain scripts (no pytest); run them as modules, not via `pytest`.
- Update the repo `README.md` / `CLAUDE.md` only if the user wants the new agent
  documented at the top level.
