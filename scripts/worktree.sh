#!/usr/bin/env bash
# Spin up a sibling git worktree for parallel Claude Code sessions.
#
#   scripts/worktree.sh <branch> [base-ref]
#
# Creates ../Agents-<branch>/ checked out on <branch> (created from [base-ref],
# default: current HEAD), then bootstraps it the way this repo expects: a local
# venv with requirements installed and a copy of .env (which is gitignored and
# therefore NOT carried into the new tree by git).
#
# Why per-worktree venv/.env: each tree relies on a local `venv/` and `.env`;
# both are gitignored, so a fresh worktree starts without them.
set -euo pipefail

branch="${1:-}"
base_ref="${2:-HEAD}"

if [[ -z "$branch" ]]; then
  echo "usage: scripts/worktree.sh <branch> [base-ref]" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

dest="${repo_root}-${branch//\//-}"
if [[ -e "$dest" ]]; then
  echo "✗ $dest already exists — pick another branch name or remove it." >&2
  exit 1
fi

# Reuse an existing local branch if present; otherwise create it from base_ref.
if git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "→ Adding worktree on existing branch '$branch'"
  git worktree add "$dest" "$branch"
else
  echo "→ Creating branch '$branch' from '$base_ref' in a new worktree"
  git worktree add -b "$branch" "$dest" "$base_ref"
fi

# Bootstrap venv.
echo "→ Creating venv and installing requirements (this can take a minute)…"
python -m venv "$dest/venv"
"$dest/venv/bin/pip" install --quiet --upgrade pip
"$dest/venv/bin/pip" install --quiet -r "$dest/requirements.txt"

# Carry over secrets (gitignored, so not in the new tree).
if [[ -f "$repo_root/.env" ]]; then
  cp "$repo_root/.env" "$dest/.env"
  echo "→ Copied .env into the worktree"
else
  echo "⚠ No .env in the main tree — copy env.example to $dest/.env and fill it in."
fi

cat <<EOF

✓ Worktree ready: $dest

Next steps:
  cd "$dest"
  source venv/bin/activate
  claude                      # start a session scoped to this branch

When finished:
  git worktree remove "$dest"
EOF
