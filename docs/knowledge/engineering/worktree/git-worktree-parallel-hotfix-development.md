# Parallel Hotfix Development Using Git Worktrees in Workers Monorepos

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Production is down: a KV namespace race condition in your rate-limiter Worker is causing 503s, and simultaneously a D1 query timeout in the auth Worker needs patching. Two engineers must work on separate hotfixes in parallel without stashing work, switching branches, or rebuilding the entire monorepo from scratch on each context switch.

## Context

`git worktree add` creates an additional checked-out working tree linked to the same repository object store. Each worktree has its own `HEAD`, index, and working directory but shares the `.git` object database and packed refs, so a `git fetch` in one worktree is immediately visible in all others without any additional network calls. In a Cloudflare Workers monorepo this is a significant advantage during parallel hotfix work: engineer A can have `hotfix/rate-limiter-kv-race` checked out in `/worktrees/hotfix-rate-limiter` with `wrangler dev` running against the live KV namespace while engineer B (or the same engineer in a second terminal) works on `hotfix/auth-d1-timeout` in `/worktrees/hotfix-auth` without either tree interfering with the other's wrangler state, lock files, or `node_modules/.cache`.

## Setting Up Worktrees for Parallel Hotfixes

```bash
# Working directory: /path/to/project (main worktree, on main branch)

# Fetch the latest remote state once — shared across all worktrees
git fetch origin

# Create worktree for the rate-limiter hotfix from production tag
git worktree add \
  ../monorepo-hotfix-rate-limiter \
  -b hotfix/rate-limiter-kv-race \
  origin/main

# Create a second worktree for the auth Worker hotfix
git worktree add \
  ../monorepo-hotfix-auth \
  -b hotfix/auth-d1-timeout \
  origin/main

# Confirm both worktrees are registered
git worktree list

# Each worktree needs its own node_modules install because pnpm
# symlinks are path-specific
cd ../monorepo-hotfix-rate-limiter && pnpm install --frozen-lockfile &
cd ../monorepo-hotfix-auth         && pnpm install --frozen-lockfile &
wait
```

## Developing and Testing Each Hotfix in Isolation

```bash
# --- Terminal 1: rate-limiter hotfix ---
cd /path/to/project

# Apply the fix to the rate-limiter Worker
$EDITOR packages/rate-limiter/src/kv.ts

# Run only the affected package's tests
pnpm --filter @monorepo/rate-limiter test

# Start wrangler dev bound to the staging KV namespace to reproduce the race
pnpm --filter @monorepo/rate-limiter exec wrangler dev \
  --env staging \
  --local false

# --- Terminal 2: auth hotfix ---
cd /path/to/project

# Apply the D1 query timeout fix
$EDITOR workers/auth/src/db/queries.ts

# Run auth Worker tests
pnpm --filter @monorepo/auth test

# Start wrangler dev for auth on a different local port
pnpm --filter @monorepo/auth exec wrangler dev \
  --env staging \
  --port 8788 \
  --local false
```

## Committing and Deploying the Hotfixes

```bash
# --- Commit rate-limiter fix ---
cd /path/to/project
git add packages/rate-limiter/src/kv.ts
git commit -m "fix(rate-limiter): guard KV put with exponential backoff to prevent race"

# Push and open PR immediately (hotfix SLA: 30 min from detect to deploy)
git push origin hotfix/rate-limiter-kv-race
gh pr create \
  --title "hotfix: rate-limiter KV race condition causing 503s" \
  --base main \
  --label hotfix \
  --reviewer @on-call-team

# --- Commit auth fix (concurrently in Terminal 2) ---
cd /path/to/project
git add workers/auth/src/db/queries.ts
git commit -m "fix(auth): increase D1 query timeout and add retry for slow reads"

git push origin hotfix/auth-d1-timeout
gh pr create \
  --title "hotfix: auth D1 timeout causing login failures" \
  --base main \
  --label hotfix \
  --reviewer @on-call-team

# Emergency deploy directly from worktree while PR review happens
# (Only if your incident runbook permits pre-merge emergency deploys)
cd /path/to/project
pnpm --filter @monorepo/rate-limiter exec wrangler deploy \
  --env production \
  --message "HOTFIX: rate-limiter KV race — see hotfix/rate-limiter-kv-race"
```

## Merging and Cleaning Up Worktrees

```bash
# After both PRs are merged to main, sync the main worktree
cd /path/to/project
git pull origin main

# Remove the hotfix worktrees — they are fully merged
git worktree remove ../monorepo-hotfix-rate-limiter
git worktree remove ../monorepo-hotfix-auth

# Prune stale worktree references (e.g. if the directory was manually deleted)
git worktree prune

# Delete the remote hotfix branches once merged
git push origin --delete hotfix/rate-limiter-kv-race
git push origin --delete hotfix/auth-d1-timeout

# Verify no worktrees remain
git worktree list
```

## Anti-patterns

- Sharing a single `node_modules` directory between worktrees via a symlink—pnpm workspace symlinks embed absolute paths, so a worktree at a different filesystem location resolves imports incorrectly.
- Creating the worktree on the same branch that another worktree already has checked out—`git worktree add` will refuse it with `already checked out`; always use `-b` to create a new branch.
- Running `wrangler deploy` from the main worktree while a hotfix worktree is mid-edit on a different branch—the deploy will pick up main's code, not the hotfix; always `cd` into the specific worktree before deploying.
- Forgetting to run `git worktree prune` after manually deleting worktree directories—stale locks in `.git/worktrees/` prevent creating new worktrees with the same name.

## Gotchas

- Each worktree has its own `.env` and `wrangler.toml` is read from the worktree's directory, but the actual file is the same on-disk file (symlinked from the repo root). Changes to `wrangler.toml` in one worktree are immediately visible in all others.
- `pnpm install` in a new worktree can conflict with the lock file if the main worktree has pending lock file changes; commit or stash lock file changes in all worktrees before installing in a new one.
- The `.git/worktrees/<name>/locked` file prevents worktree removal; if a previous crash left a lock, run `git worktree unlock <path>` before `git worktree remove`.

## Verification

```bash
# Confirm worktrees are on the correct branches
git worktree list --porcelain | grep -E "worktree|HEAD|branch"

# Confirm each hotfix only touches expected packages
git -C ../monorepo-hotfix-rate-limiter diff main -- packages/
git -C ../monorepo-hotfix-auth diff main -- workers/

# Run full CI locally against both hotfix branches before merging
pnpm -C ../monorepo-hotfix-rate-limiter turbo run test build \
  --filter=...[origin/main]
pnpm -C ../monorepo-hotfix-auth turbo run test build \
  --filter=...[origin/main]
```

## Related

- `worktree/git-worktree-2026.md`
- `worktree/git-worktree-parallel-ci-patterns.md`
- `worktree/hotfix-process.md`
- `worktree/github-actions-wrangler-deploy-pipeline.md`
- `worktree/rollback-strategy.md`

## Sources

- https://git-scm.com/docs/git-worktree
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://pnpm.io/workspaces
