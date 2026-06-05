# Git worktrees for parallel Claude Code sessions

A git worktree is a second checkout of this repo in a separate directory that shares the
same `.git` history but has its own working files and its own checked-out branch. It lets
you run **two Claude Code sessions in parallel** — one per branch — without them stepping
on each other's files.

## When to use

- Running a long task (or a background agent) on one branch while you keep working on
  another.
- Reviewing/testing a branch without stashing or disturbing your current work.
- Comparing two approaches side by side.

For a quick edit on the same branch, you don't need a worktree — just work in place.

## Create one

```bash
scripts/worktree.sh <branch> [base-ref]
```

This creates a sibling directory `../Agents-<branch>/` on `<branch>` (created from
`base-ref`, default current `HEAD`), then bootstraps it.

## The venv / .env caveat

Each tree relies on a **local `venv/` and `.env`**, and both are gitignored — so a fresh
worktree starts without them. `scripts/worktree.sh` handles this for you: it creates a new
`venv`, installs `requirements.txt`, and copies your `.env` over. If you create a worktree
by hand (`git worktree add …`), do that bootstrap yourself:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../Agents/.env .env        # or: cp env.example .env && edit it
```

## Clean up

```bash
git worktree remove ../Agents-<branch>     # from any tree
git worktree list                          # see active worktrees
```

`git worktree remove` refuses if the tree has uncommitted changes — commit/discard first,
or pass `--force` if you're sure.
