# Git Worktree Parallel Wrangler Environments

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A example project developer needs to test a feature branch against the staging Workers environment while simultaneously keeping a production hotfix running on `main` — both served by `wrangler dev` on separate ports. Switching branches with `git checkout` tears down the running dev server and forces a full restart. Using git worktrees gives each branch its own working directory, letting both `wrangler dev` instances run in parallel without interference.

## Context

Wrangler dev servers are stateful processes: they watch the filesystem for changes and hold open connections to Cloudflare's remote service proxy or local miniflare instance. Git worktrees create independent directory trees that share the same `.git` object store but have separate working copies, HEAD refs, and — critically — separate `node_modules` and `.wrangler` state when pnpm workspaces are configured per-directory.

## Creating Worktrees for Each Environment

Establish a naming convention that maps worktree directory names to Wrangler environments. Keep worktrees outside the main checkout to avoid confusing build tools.

```bash
# From the main repo root
GIT_ROOT=$(git rev-parse --show-toplevel)
WORKTREES_DIR="$GIT_ROOT/../example project-worktrees"
mkdir -p "$WORKTREES_DIR"

# Worktree for the feature branch (staging environment)
git worktree add "$WORKTREES_DIR/feature-auth-rework" feature/auth-rework

# Worktree for main (production hotfix)
git worktree add "$WORKTREES_DIR/main-hotfix" main

# List active worktrees
git worktree list
```

Each worktree needs its own pnpm install because node_modules are not shared across separate filesystem paths.

```bash
# Install deps in each worktree
(cd "$WORKTREES_DIR/feature-auth-rework" && pnpm install --frozen-lockfile)
(cd "$WORKTREES_DIR/main-hotfix" && pnpm install --frozen-lockfile)
```

## Running Parallel Wrangler Dev Servers

Start each server on a different port, bound to the appropriate Wrangler environment. Use separate terminal sessions or a process manager.

```bash
# Terminal 1 — feature branch on staging, port 8787
cd "$WORKTREES_DIR/feature-auth-rework/packages/workers-api"
wrangler dev --env staging --port 8787 --local

# Terminal 2 — main branch on production config, port 8788
cd "$WORKTREES_DIR/main-hotfix/packages/workers-api"
wrangler dev --env production --port 8788 --local
```

Use a `Procfile` or `tmux` script for one-command startup:

```bash
#!/usr/bin/env bash
# scripts/dev-parallel.sh
set -euo pipefail

WORKTREES_DIR="$(git rev-parse --show-toplevel)/../example project-worktrees"

tmux new-session -d -s example project-dev -n feature \
  "cd $WORKTREES_DIR/feature-auth-rework/packages/workers-api && wrangler dev --env staging --port 8787 --local"

tmux new-window -t example project-dev -n hotfix \
  "cd $WORKTREES_DIR/main-hotfix/packages/workers-api && wrangler dev --env production --port 8788 --local"

tmux attach -t example project-dev
```

## Keeping Wrangler State Isolated

Wrangler stores local state (D1 SQLite databases, KV stores, R2 buckets) in a `.wrangler/state` directory relative to the `wrangler.toml`. Because each worktree has its own `wrangler.toml` location, state is automatically isolated — editing a local D1 table in one worktree does not affect the other.

Confirm isolation explicitly:

```bash
# Each worktree has its own .wrangler directory
ls "$WORKTREES_DIR/feature-auth-rework/packages/workers-api/.wrangler/state/v3/d1/"
ls "$WORKTREES_DIR/main-hotfix/packages/workers-api/.wrangler/state/v3/d1/"
# Should show different sqlite files
```

If you need shared local state (e.g. a seeded D1 database), point both wrangler configs to the same state directory via the `--persist-to` flag:

```bash
SHARED_STATE="$HOME/.example project-shared-dev-state"
wrangler dev --env staging --port 8787 --persist-to "$SHARED_STATE" --local
wrangler dev --env production --port 8788 --persist-to "$SHARED_STATE" --local
```

## Syncing and Removing Worktrees

Fetch upstream changes into a worktree without switching to it:

```bash
# Pull latest main into the hotfix worktree
git -C "$WORKTREES_DIR/main-hotfix" pull --rebase origin main

# Rebase the feature worktree on top of updated main
git -C "$WORKTREES_DIR/feature-auth-rework" rebase origin/main
```

When work is done, remove the worktree cleanly:

```bash
# Remove feature worktree after PR is merged
git worktree remove "$WORKTREES_DIR/feature-auth-rework" --force
git worktree prune
```

## Anti-patterns

- Running both `wrangler dev` instances on the same port — the second will fail to bind and exit silently.
- Sharing `node_modules` via a symlink between worktrees — Wrangler's bundler resolves paths relative to the worktree root; a shared symlinked `node_modules` causes incorrect module resolution in the second worktree.
- Editing `wrangler.toml` in one worktree expecting it to apply to the other — each worktree has its own checkout of all tracked files.
- Not running `pnpm install` after creating a worktree — the worktree directory has no `node_modules` until install runs.
- Leaving stale worktrees around after feature branches are deleted — `git worktree prune` cleans up orphaned metadata; run it after bulk branch deletes.

## Gotchas

- `wrangler dev --remote` in a worktree uses the same Cloudflare account credentials. Running two remote dev sessions simultaneously can cause preview URL conflicts if both use the same Worker name and environment. Use `--name` to differentiate: `wrangler dev --remote --name example project-api-feature --env staging`.
- The `.wrangler` directory is gitignored by default. Worktree-specific `.wrangler` state will not interfere with the main checkout, but if you accidentally add a worktree path inside the main repo root (not a sibling directory), `.wrangler` state from the inner worktree may be tracked.
- pnpm workspace catalogs defined in the root `pnpm-workspace.yaml` are resolved relative to the root of the worktree — which for a linked worktree is the worktree root, not the original checkout root. Ensure the workspace yaml is present in every worktree (it will be, since it's a tracked file).
- `wrangler.toml` `compatibility_flags` may differ between environments. Running `--env production` in a worktree that was intended for staging tests may activate flags not yet tested on that branch.

## Verification

With both servers running, send requests to each port and confirm they respond with code from different branches:

```bash
# Feature branch (staging): should show new auth header
curl -i http://127.0.0.1:8787/api/auth/me

# Main (production): should show old auth behaviour
curl -i http://127.0.0.1:8788/api/auth/me
```

Check that `git worktree list` shows both paths with their respective HEADs, and that `.wrangler/state` directories are separate.

## Related

- git-worktree-2026.md
- git-worktree-parallel-ci-patterns.md
- git-worktree-lockfile-isolation.md
- wrangler-environments-staging-production.md
- git-worktree-parallel-hotfix-development.md

## Sources

- https://git-scm.com/docs/git-worktree
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/wrangler/configuration/#local-development-settings
