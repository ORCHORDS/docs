# Git Worktree: Apply a Production Hotfix Without Stashing In-Progress Work

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are deep in a feature branch with uncommitted work spread across a dozen files. Production is broken. You need to cut a hotfix from `origin/main` right now — but you cannot stash (the diff is too noisy), cannot commit a half-baked WIP, and cannot afford to lose your working state by switching branches.

## Context

`git worktree` lets you check out a second branch into a sibling directory while the original working tree stays completely untouched. The two trees share the same `.git` database, so history, remotes, and hooks are common — but the file-system state is fully independent. No stash, no WIP commit, no branch switching required.

This pattern is especially clean for Cloudflare Workers projects: you `cd` into the worktree directory, run `wrangler deploy`, and the hotfix goes live without any of your feature-branch files ever being in play.

---

## Applying the Hotfix in a Linked Worktree

```bash
# 1. You are on feature/new-billing, with dirty working tree
git status
# On branch feature/new-billing
# Changes not staged for commit: ...

# 2. Add a linked worktree based on origin/main
#    The directory is created outside the repo root to avoid confusion
git worktree add ../hotfix-production origin/main
# Preparing worktree (new branch 'hotfix-production')
# Branch 'hotfix-production' set up to track 'origin/main'.
# HEAD is now at a3f9c12 chore: update deps

# 3. Jump into the worktree — your feature branch files are gone from view
cd ../hotfix-production
git branch
# * hotfix-production
#   feature/new-billing   ← still safe in the original tree

# 4. Make the fix
cat >> src/index.ts <<'EOF'
// HOTFIX 2026-08-24: guard against null user on /health
EOF
# ... edit the file properly with your editor

# 5. Commit inside the worktree
git add src/index.ts
git commit -m "fix: guard null user on /health endpoint"

# 6. Deploy directly from the worktree directory
#    wrangler reads wrangler.toml that lives here — no path tricks needed
npx wrangler deploy
# Total Upload: 142 kB / gzip: 38 kB
# Uploaded my-worker (1.23 sec)
# Published my-worker (0.45 sec)
#   https://my-worker.example.workers.dev

# 7. Push the hotfix branch and open a PR
git push origin hotfix-production
# (open PR on GitHub targeting main)

# 8. Return to feature work — original tree is pristine
cd ../my-repo
git status
# On branch feature/new-billing
# Changes not staged for commit: (everything exactly as you left it)

# 9. Clean up after the PR merges
git worktree remove ../hotfix-production
git branch -d hotfix-production
git remote prune origin
```

---

## Worktree Lifecycle Commands

```bash
# List all worktrees for this repo
git worktree list
# /path/to/project          a3f9c12 [feature/new-billing]
# /path/to/project a3f9c12 [hotfix-production]

# Prune stale worktree metadata (e.g. if you deleted the dir manually)
git worktree prune

# Lock a worktree so it cannot be accidentally removed
git worktree lock ../hotfix-production --reason "active hotfix deploy"

# Unlock before removal
git worktree unlock ../hotfix-production
git worktree remove ../hotfix-production
```

---

## Wrangler-Specific Considerations

When running `wrangler deploy` from a worktree:

- `wrangler.toml` is resolved relative to the **current working directory**, so `cd` into the worktree root first.
- Environment variables and secrets are scoped to your Cloudflare account, not the directory — they are always available regardless of which worktree you deploy from.
- If your Worker uses **local KV or D1 bindings** (`--local` flag), the `.wrangler/state/` directory is per-worktree, which is usually desirable for isolation.
- If you use `wrangler dev` in two worktrees simultaneously, pick different `--port` values to avoid conflicts.

```bash
# Deploy to production environment from the hotfix worktree
cd ../hotfix-production
npx wrangler deploy --env production

# Verify the deployment is live
curl -s https://my-worker.example.workers.dev/health | jq .status
# "ok"
```

---

## Anti-patterns

- **Stashing then switching** — `git stash` loses context, IDE state, and `.env` edits that are intentionally unstaged. Worktrees avoid all of this.
- **Creating the worktree inside the repo root** — placing `../hotfix-production` inside the monitored directory confuses file watchers (TypeScript server, Vite, Wrangler dev). Always use a sibling path.
- **Leaving worktrees around after the fix** — orphaned worktrees hold a branch lock; `git branch -d` will refuse until the worktree is removed. Run `git worktree list` after each release cycle and prune stale entries.
- **Running `npm install` in the worktree only** — if the hotfix bumps a dependency, install in the worktree but remember to run it again in the main tree after you pull the merged change.

---

## Gotchas

- A branch cannot be checked out in more than one worktree at a time. If you try `git worktree add ../hotfix main` when `main` is already checked out somewhere, Git returns `fatal: 'main' is already checked out`.
- `git worktree remove` requires the worktree to be clean (no uncommitted changes). Use `--force` only if you are certain those changes are disposable.
- Node.js `node_modules` are **not** shared between worktrees — run `npm ci` (or `pnpm install --frozen-lockfile`) inside the new worktree if you need dependencies.
- If your monorepo uses pnpm workspaces, run `pnpm install` from the worktree root; pnpm will reuse the content-addressable store, so the install is nearly instant.

---

## Verification

```bash
# Confirm worktrees are independent
echo "worktrees:"
git worktree list

# Confirm main tree is unchanged
git -C /path/to/project diff --stat
# (should show only your feature-branch changes, nothing from hotfix)

# Confirm hotfix was deployed
curl -I https://my-worker.example.workers.dev/health
# HTTP/2 200

# Confirm worktree cleanup
git worktree list
# /path/to/project  abc1234 [feature/new-billing]
```

---

## Related

- `changesets-monorepo-workers-package-versioning.md`
- `github-actions-path-filter-selective-deploy-workers.md`
- [Git worktree documentation](https://git-scm.com/docs/git-worktree)
- [Wrangler deploy reference](https://developers.cloudflare.com/workers/wrangler/commands/#deploy)

## Sources

- Git SCM documentation — `git worktree` (2024)
- Cloudflare Workers Wrangler CLI documentation (2026)
- example.com internal runbook: "Zero-downtime hotfix on Cloudflare Workers" (2025)
