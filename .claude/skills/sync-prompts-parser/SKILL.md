---
name: sync-prompts-parser
description: Validate (and on request fix) that the structured-output section headers declared in an agent's prompts.py exactly match the hand-written parse_structured_insights branches in agent.py. Use when editing prompt headers, after a header rename, or to audit prompt/parser drift across agents.
---

# Sync prompts.py headers with the parser

In each agent, the AI returns labeled sections whose **header strings are declared in
`agents/<name>/prompts.py`** and **parsed by hand in `<Name>Agent.parse_structured_insights`**
(in `agent.py`). If a header is renamed in one place but not the other, the parser silently
drops that section — no error, just missing content in the email. This skill detects that drift
and fixes the parser in lockstep.

The headers genuinely differ per agent — do not assume a single canonical set:
- **earnings**: `EXECUTIVE SUMMARY`, `STRATEGIC ANALYSIS`, `RISK FACTORS`, `INVESTMENT RECOMMENDATION`, `EXPERT RECOMMENDATION`
- **ratings**: `EXECUTIVE SUMMARY`, `RATING RATIONALE`, `RISK FACTORS`, `INVESTMENT RECOMMENDATION`, `EXPERT RECOMMENDATION`
- **flights**: `DEAL SUMMARY`, `PRICE CONTEXT`, `BOOKING TIP`

## Steps

1. **Resolve target agent(s).** Use the agent named/implied by the request, the agent of the
   file currently being edited, or — if auditing — every directory under `agents/*/` that has a
   `prompts.py`.

2. **Extract declared headers from `prompts.py`.** Collect the `UPPERCASE LABEL:` headers from
   the `Format:` block(s) and from the module docstring's header list at the top of the file
   (e.g. `agents/ratings_agent/prompts.py:3-6`). Normalize to upper case.

3. **Extract handled headers from the parser.** In `agent.py`, read
   `parse_structured_insights` and collect every string literal tested with `in line.upper()`
   (e.g. `agents/ratings_agent/agent.py:252-287`). Treat `or`-ed variants (e.g.
   `"RISK FACTORS" in line.upper() or "RISK FACTOR" in line.upper()`) as covering the same
   logical header.

4. **Diff the two sets and report.**
   - Declared in `prompts.py` but **missing from the parser** → silent-drop risk (the important
     case). Flag loudly.
   - Handled in the parser but **no longer declared** in `prompts.py` → dead branch. Flag as
     cleanup.
   - If they match, report "in sync" and stop.

5. **Fix on request only.** When the user wants it synced, edit `parse_structured_insights` so
   its branches match the declared headers. Also update, in lockstep:
   - the `result` dict keys initialized at the top of the parser and returned at the bottom,
   - the matching keys in `_disabled_insights` (the AI-off fallback),
   - any consumer of those keys (HTML/plain-text email builder) in the same `agent.py`,
   - the **header list in the `prompts.py` module docstring**.
   Keep each agent's own key naming convention (ratings uses `rating_rationale`, flights uses
   its own keys) — do not unify them across agents.

6. **Note the existing hook.** A PostToolUse hook (`.claude/hooks/prompts-parser-reminder.sh`)
   already fires a reminder when any `agents/*/prompts.py` is edited. This skill complements it
   by actually checking/fixing; leave the hook in place.

## Verification

- Run against the ratings agent with no changes → reports "in sync".
- After any fix, re-run the extract/diff to confirm the sets now match, and confirm
  `python -c "import agents.<name>.agent"` still imports clean.
