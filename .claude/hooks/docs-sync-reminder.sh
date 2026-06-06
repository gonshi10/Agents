#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): when a structural (doc-relevant) file is edited,
# remind to keep the docs in lockstep — the root README.md, .claude/CLAUDE.md,
# and, for edits inside an agent, that agent's README.md. To honour "only if they
# haven't been updated", it checks git and stays SILENT when the relevant doc has
# already been changed in the working tree. Non-blocking: only surfaces context,
# never stops or undoes the edit.
set -uo pipefail

payload="$(cat)"

# Without jq we can't reliably parse the payload; fail open (matches sibling hooks).
command -v jq >/dev/null 2>&1 || exit 0

path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"
[ -n "$path" ] || exit 0

# Never nag about editing the docs themselves.
case "$path" in
  */README.md|*/CLAUDE.md) exit 0 ;;
esac

# Classify the edit: only structural files that the docs actually describe.
case "$path" in
  */agents/*/agent.py|*/agents/*/main.py|*/agents/*/prompts.py|*/agents/*/__main__.py) ;;
  */common/config.py|*/common/*.py|*/common/*/*.py) ;;
  */env.example|*/requirements.txt) ;;
  */.github/workflows/*.yml|*/.github/workflows/*.yaml) ;;
  *) exit 0 ;;
esac

# A doc counts as "in sync" if it shows as changed in the working tree.
is_dirty() {
  git -C "$CLAUDE_PROJECT_DIR" status --porcelain -- "$1" 2>/dev/null | grep -q .
}

root_synced=false
if is_dirty "README.md" || is_dirty ".claude/CLAUDE.md"; then
  root_synced=true
fi

# Derive agents/<name>/README.md when the edit lives under an agent folder.
agent_readme=""
agent_synced=false
case "$path" in
  */agents/*/*)
    rel="${path##*/agents/}"          # e.g. earnings_agent/agent.py
    agent_name="${rel%%/*}"           # e.g. earnings_agent
    agent_readme="agents/${agent_name}/README.md"
    if is_dirty "$agent_readme"; then
      agent_synced=true
    fi
    ;;
esac

emit() {
  # Single JSON object on stdout is how a PostToolUse hook injects context.
  jq -cn --arg ctx "$1" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$ctx}}'
}

if [ -n "$agent_readme" ]; then
  # Edit inside an agent: silent only if BOTH that agent's README and the root
  # docs already reflect a change.
  if [ "$agent_synced" = true ] && [ "$root_synced" = true ]; then
    exit 0
  fi
  emit "Docs-sync reminder: ${path} is a structural file documented in the repo's docs, but they don't look updated this session. Review ${agent_readme} (this agent's README) and the repo's root README.md / .claude/CLAUDE.md, and update whichever describe what you changed. Skip if the docs already cover it."
  exit 0
fi

# Shared/config/workflow edit: only root docs apply.
if [ "$root_synced" = true ]; then
  exit 0
fi
emit "Docs-sync reminder: ${path} is a structural file described by the repo's docs, but neither root README.md nor .claude/CLAUDE.md look updated this session. Review both and update whichever describes what you changed. Skip if the docs already cover it."
exit 0
