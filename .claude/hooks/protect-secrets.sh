#!/usr/bin/env bash
# PreToolUse hook (Edit|Write|Bash): block any tool call that would read, edit,
# or stage the .env secrets file. Complements the Read(./.env) deny rule in
# settings.json. Reads the hook payload as JSON on stdin and emits a
# permissionDecision of "deny" to stop the call.
#
# Exit 0 with no output => allow. We only ever block; never hard-error, so a
# malformed payload or missing `jq` degrades to "allow" rather than wedging the
# session.
set -uo pipefail

payload="$(cat)"

# Without jq we can't reliably parse the payload; fail open.
command -v jq >/dev/null 2>&1 || exit 0

tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty')"

deny() {
  # JSON object on stdout is the structured way to block a PreToolUse call.
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 0
}

case "$tool" in
  Edit|Write|MultiEdit)
    path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"
    base="$(basename "$path")"
    # Match .env and .env.<anything> but NOT env.example / *.env.example.
    if [[ "$base" == ".env" || "$base" == ".env."* ]]; then
      deny ".env holds secrets and must not be modified by the agent. Edit it manually."
    fi
    ;;
  Bash)
    cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')"
    # Reading/printing the secrets file.
    if printf '%s' "$cmd" | grep -Eq '(^|[[:space:]])(cat|less|more|head|tail|bat|xxd|od|strings)[[:space:]]+([^|;&]*[[:space:]])?\.env([[:space:]]|$)'; then
      deny "Refusing to print .env contents (secrets)."
    fi
    # Staging the secrets file, including bulk 'git add -A' / 'git add .'.
    if printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+add([[:space:]]+[^|;&]*)?[[:space:]]+(\.env|-A|--all|\.)([[:space:]]|$)'; then
      deny "Refusing to 'git add' .env (or a bulk add that would stage it). Stage files explicitly."
    fi
    ;;
esac

exit 0
