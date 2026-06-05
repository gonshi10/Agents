---
name: add-agent-config
description: Add a new configuration variable end-to-end across common/config.py, env.example, and the relevant GitHub Actions workflow so the files that must agree never drift. Use when an agent needs a new env var / setting, or when wiring config for a newly scaffolded agent.
---

# Add a config variable end-to-end

All environment access in this repo goes through the single `Settings` dataclass — **agents
never call `os.getenv` directly**. Adding a setting therefore means editing several files that
must stay in agreement; miss one and it fails silently (a `KeyError`/`AttributeError` at runtime,
or a value that's simply never set in CI). This skill keeps them in sync.

## Files that must stay in sync

- **`common/config.py`** — two edits:
  - add a typed field to the frozen `Settings` dataclass (`config.py:20-37`), and
  - add a matching line in `get_settings()` (`config.py:57-83`).
- **`env.example`** — document the var with a placeholder and a comment, in the right section.
- **`.github/workflows/<agent>.yml`** — make the var available to scheduled runs.

## Steps

1. **Gather the details** (ask if not given):
   - name in `UPPER_SNAKE_CASE`;
   - type: `str` / `int` / `float` / `bool`;
   - **required or optional** — required vars abort startup if unset;
   - default value (for optional vars);
   - which agent(s)/workflow(s) consume it;
   - is it a **secret** (API key, password) or a **fixed value** (a path)?

2. **Edit `common/config.py`.**
   - Add the field to `Settings` with the right type (use `| None` for optional).
   - In `get_settings()`, read it:
     - **Required**: add it to the `required` dict and the `missing` check
       (`config.py:47-55`), mirroring `FINNHUB_API_KEY`/`SMTP_USER`.
     - **Optional**: add an `os.getenv("VAR", default)` line. Follow the `flights_api_token`
       precedent (`config.py:70-73`) for optional-with-comment.
   - **Cast non-strings** exactly like the existing lines: `int(os.getenv(...))`,
     `float(os.getenv(...))`, or `_as_bool(os.getenv(...), default=...)`.

3. **Edit `env.example`.** Add the var with a placeholder and a one-line comment, under the
   matching section header (API keys / Email / File Paths / per-agent / Runtime).

4. **Edit the workflow(s) `.github/workflows/<agent>.yml`.** Under the run step's `env:` block
   (`ratings-agent.yml:38-53`):
   - **Secret** → `VAR: ${{ secrets.VAR }}` (and tell the user to add the GitHub Actions secret).
   - **Fixed value** (e.g. a path) → hardcode it inline.
   - **Persisted snapshot path** → also add an `actions/cache` step modeled on
     `ratings-agent.yml:27-36` so the file survives ephemeral runners.

5. **Remember the cross-agent constraint.** `get_settings()` is `lru_cache`d and requires
   `FINNHUB_API_KEY` for *all* agents — so even non-Finnhub agents (e.g. flights) must keep that
   secret in their workflow. Don't add a new required var unless every agent's workflow can supply
   it; prefer optional-with-default otherwise.

## Verification

- `python -c "from common.config import get_settings"` imports clean.
- The new field appears in the `Settings` dataclass, in `env.example`, and in each named
  workflow's `env:` block (with a cache step if it's a snapshot path).
