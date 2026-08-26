# Production Hotfix Workflow Using Git Worktrees in Parallel

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A critical bug surfaces in production while a large feature branch is mid-flight in the main working directory. Switching branches to apply the hotfix would destroy local state, stash conflicts, or interrupt a long-running `wrangler dev` session. A git worktree lets you check out the release tag into a sibling directory, apply the fix, and deploy — without touching the main worktree at all.

---

## Context

Git worktrees allow a single repository to have multiple checked-out branches on disk simultaneously. Each worktree shares the same `.git` object store and history but maintains its own `HEAD`, index, and working tree. This is ideal for emergency hotfixes because the production tag is materialised in a separate directory, deployed, and then discarded — the main worktree never changes branches. Cloudflare Workers deployments via `wrangler deploy` are directory-scoped, so running it from the hotfix worktree targets only that build. Cherry-picking the fix back to the main branch ensures the repair is not lost when the hotfix worktree is removed.

---

## Section 1 — Create the Hotfix Worktree

```bash
# From the repo root (main worktree)
git fetch --tags

# Create a new branch from the production tag and check it out
# in a sibling directory outside the repo root
git worktree add ../hotfix-v2.1 -b hotfix/v2.1.1 v2.1.0

# Verify both worktrees are registered
git worktree list
# /path/to/project          abc1234 [main]
# /path/to/project        def5678 [hotfix/v2.1.1]
```

---

## Section 2 — Apply the Fix and Deploy

```bash
# Move into the hotfix worktree — the main worktree is untouched
cd ../hotfix-v2.1

# Install dependencies scoped to this directory
npm ci

# Edit the offending file
nano src/handlers/payments.ts
```

```typescript
// src/handlers/payments.ts — hotfix: guard against null body
export async function handlePayment(request: Request): Promise<Response> {
  const body = await request.json().catch(() => null);
  if (!body) {
    return new Response(JSON.stringify({ error: 'invalid_body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  // ... existing logic
  return new Response(JSON.stringify({ ok: true }), { status: 200 });
}
```

```bash
# Commit the fix inside the hotfix worktree
git add src/handlers/payments.ts
git commit -m "fix(payments): guard null body in handlePayment"

# Run unit tests before deploying
npm test

# Deploy directly to production from this worktree
npx wrangler deploy --env production
# Deployed to https://my-worker.example.workers.dev
```

---

## Section 3 — Cherry-Pick Back and Clean Up

```bash
# Record the fix commit SHA
HOTFIX_SHA=$(git rev-parse HEAD)
echo "Hotfix commit: $HOTFIX_SHA"

# Return to the main worktree
cd ../my-worker

# Cherry-pick the fix onto main (or the active feature branch)
git cherry-pick "$HOTFIX_SHA"

# Push main so CI validates the cherry-pick
git push origin main

# Remove the hotfix worktree and delete its branch
git worktree remove ../hotfix-v2.1
git branch -d hotfix/v2.1.1

# Confirm cleanup
git worktree list
# /path/to/project   <commit> [main]
```

---

## Anti-patterns

- **Deploying from the main worktree on a different branch** — switching the main worktree's branch to apply a hotfix interrupts any running `wrangler dev` process and risks committing experimental code to the production deploy.
- **Forgetting to cherry-pick** — the hotfix lives only in the deleted worktree's branch; once the branch is removed, the fix is gone from history unless it was merged or cherry-picked.
- **Running `npm install` in the hotfix worktree without `--ignore-scripts`** — lifecycle scripts that mutate shared config files can corrupt the main worktree's state.
- **Leaving stale worktrees** — accumulated worktrees consume disk space and create confusing `git status` output; remove them immediately after the deploy.

---

## Gotchas

- Each worktree maintains its own `.env` and `wrangler.toml` overrides only if you copy them; the files are not automatically shared unless they sit in a shared parent directory.
- `git worktree remove` fails if the worktree has uncommitted changes; use `--force` only after verifying there is nothing worth saving.
- Wrangler caches are keyed to the working directory; the hotfix worktree gets its own cache under `../hotfix-v2.1/.wrangler/`, which keeps build artefacts isolated.
- You cannot check out the same branch in two different worktrees — git enforces this. Create a new branch (e.g., `hotfix/v2.1.1`) rather than reusing `main`.
- If your `wrangler.toml` references relative asset paths, double-check them from the new working directory before deploying.

---

## Verification

```bash
# Confirm the production deployment is live
curl -s https://my-worker.example.workers.dev/health | jq .

# Confirm the fix commit appears on main
git log --oneline main | head -5

# Confirm no stale worktrees remain
git worktree list

# Confirm the hotfix branch is deleted
git branch --list 'hotfix/*'
```

---

## Related

- `git-worktree-long-running-refactor-isolation.md`
- `git-worktree-bisect-regression-hunt.md`

---

## Sources

- Git Worktrees Documentation — https://git-scm.com/docs/git-worktree
- Wrangler Deploy Reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Cloudflare Workers Environments — https://developers.cloudflare.com/workers/wrangler/environments/
