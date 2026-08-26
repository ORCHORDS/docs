# Git Worktree — Parallel Feature Development

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to work on two independent feature branches simultaneously — `feat/payments` and `feat/auth` — without stashing or switching branches. Both features require running `wrangler dev` servers locally, and context-switching costs time.

---

## Context

`git worktree` allows multiple working trees to be checked out from the same repository at the same time. Each worktree has its own `HEAD`, index, and working directory, but they all share the same `.git` object store. This means you get full branch isolation without cloning the repo twice. Workers projects benefit particularly because you can run `wrangler dev` on different ports in each worktree simultaneously, keeping both feature servers live. When work is done, merging is conflict-free relative to stash because each branch has been independently committed throughout.

---

## Section 1 — Creating the Worktrees

```bash
# From the main repository root
git worktree add ../feat-payments feat/payments
git worktree add ../feat-auth feat/auth

# If the branches do not yet exist, create them at the same time
git worktree add -b feat/payments ../feat-payments origin/main
git worktree add -b feat/auth ../feat-auth origin/main

# Verify all worktrees
git worktree list
# /path/to/project         abc1234 [main]
# /path/to/project   def5678 [feat/payments]
# /path/to/project       ghi9012 [feat/auth]
```

---

## Section 2 — Running wrangler dev in Each Worktree

Open two terminal sessions (or use a multiplexer like `tmux`).

**Terminal A — payments feature:**
```bash
cd ../feat-payments
npm install          # install deps if package.json changed
npx wrangler dev --port 8788 --local
```

**Terminal B — auth feature:**
```bash
cd ../feat-auth
npm install
npx wrangler dev --port 8789 --local
```

Each `wrangler dev` process binds to its own port and reads the `wrangler.toml` in its own worktree directory. D1 databases, KV namespaces, and R2 bindings are all isolated per process.

```typescript
// feat-payments/src/index.ts — example Worker entry point
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/charge') {
      // Payment processing logic
      return new Response('Payment processed', { status: 200 });
    }
    return new Response('Not found', { status: 404 });
  },
};

interface Env {
  PAYMENTS_KV: KVNamespace;
  PAYMENTS_DB: D1Database;
}
```

---

## Section 3 — Merging and Cleanup

```bash
# Commit work in each worktree independently
cd ../feat-payments
git add -A && git commit -m "feat(payments): implement charge endpoint"
git push origin feat/payments

cd ../feat-auth
git add -A && git commit -m "feat(auth): implement JWT validation"
git push origin feat/auth

# Back in the main repo — merge both features
cd /path/to/project
git fetch origin
git merge origin/feat/payments
git merge origin/feat/auth

# Remove the worktrees when done
git worktree remove ../feat-payments
git worktree remove ../feat-auth

# Prune stale worktree refs (if a worktree was deleted manually)
git worktree prune

# Delete the remote feature branches after merge
git push origin --delete feat/payments
git push origin --delete feat/auth
```

---

## Anti-patterns

- **Sharing a wrangler.toml port across worktrees** — If both `wrangler.toml` files specify the same `dev.port`, both `wrangler dev` processes will fight for the same port. Always override with `--port` on the CLI or set distinct ports per worktree.
- **Running `npm install` in the main repo and expecting it to apply to worktrees** — Each worktree has its own `node_modules` unless you use a package manager workspace. Run `npm install` inside each worktree after checking it out.
- **Forgetting `git worktree prune`** — Manually deleting a worktree directory leaves a stale ref in `.git/worktrees/`. Always use `git worktree remove` or run `prune` afterwards.
- **Creating a worktree on a branch that is already checked out** — Git prevents checking out the same branch in two worktrees simultaneously. Use a separate branch or create a new one with `-b`.

---

## Gotchas

- Worktree paths must be outside the main repository directory; placing them inside causes nested-repo confusion.
- `.env` files and `wrangler.toml` secrets are NOT shared between worktrees — copy or symlink them deliberately.
- If your project uses Husky git hooks, hooks run from `.git/hooks` and apply to all worktrees equally.
- `wrangler dev` D1 local state is stored in `.wrangler/state` inside each worktree — they do not share local DB state.
- `git stash` in one worktree is visible in all worktrees (stash is global to the repo), but the working-tree changes are isolated.

---

## Verification

```bash
# Confirm both dev servers respond
curl http://localhost:8788/charge
curl http://localhost:8789/login

# Confirm worktree list is clean after removal
git worktree list
# Should show only the main worktree

# Confirm no stale worktree dirs
git worktree prune -v
```

---

## Related

- `git-worktree-release-branch-cherry-pick.md`
- `git-submodule-shared-workers-library.md`

---

## Sources

- Git Worktree Documentation — https://git-scm.com/docs/git-worktree
- Wrangler Dev CLI Reference — https://developers.cloudflare.com/workers/wrangler/commands/#dev
