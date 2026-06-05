#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): when an agent's prompts.py is changed, remind
# that the labeled section headers are parsed by hand and must be kept in
# lockstep with parse_structured_insights. Non-blocking: this only surfaces
# context, it never stops or undoes the edit.
set -uo pipefail

payload="$(cat)"

command -v jq >/dev/null 2>&1 || exit 0

path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"

# Match any agents/<name>/prompts.py
case "$path" in
  */agents/*/prompts.py)
    cat <<'MSG'
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"Reminder: prompts.py section headers (EXECUTIVE SUMMARY, STRATEGIC ANALYSIS, RISK FACTORS, INVESTMENT RECOMMENDATION, EXPERT RECOMMENDATION) are parsed by hand in parse_structured_insights (agents/earnings_agent/agent.py, header matching ~line 178). If you renamed/added/removed a header, update that parser in lockstep or insights will silently drop."}}
MSG
    ;;
esac

exit 0
