# Isolating Long-Running Refactors in a Separate Git Worktree

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A large authentication overhaul touches dozens of files and is expected to take two or more weeks. During that time, production hotfixes and smaller features must ship on `main` without waiting for the refactor to stabilise. Keeping the refactor in a separate git worktree means `main` stays deployable and the refactor branch can rebase onto new commits without context-switching disrupting either stream of work.

---

## Context

Long-running branches are the classic source of merge conflicts because they diverge from `main` silently for days or weeks. A git worktree surfaces the refactor as a real directory on disk, making it easy to run its test suite independently, keep a dedicated terminal session open, and rebase onto `main` on a fixed cadence. The main worktree remains on `main` at all times, so any hotfix can be developed and deployed without ever touching the refactor directory. When the refactor is finally ready, a standard squash-merge or rebase-merge into `main` lands all the changes cleanly.

---

## Section 1 — Setup the Refactor Worktree

```bash
# From the repo root on main
git fetch origin

# Create the long-running refactor branch from the latest main
git worktree add ../refactor-auth -b refactor/auth-overhaul origin/main

# Verify
git worktree list
# /path/to/project       abc1234 [main]
# /path/to/project   abc1234 [refactor/auth-overhaul]

# Open a dedicated terminal in the refactor worktree
cd ../refactor-auth
npm ci
```

---

## Section 2 — Development and Periodic Rebase

```typescript
// refactor-auth/src/auth/session.ts — new session management module
import { Env } from '../types';

export interface Session {
  userId: string;
  expiresAt: number;
  scopes: string[];
}

export async function createSession(
  userId: string,
  scopes: string[],
  env: Env
): Promise<string> {
  const token = crypto.randomUUID();
  const session: Session = {
    userId,
    expiresAt: Date.now() + 3_600_000, // 1 hour
    scopes,
  };
  await env.SESSIONS.put(token, JSON.stringify(session), {
    expirationTtl: 3600,
  });
  return token;
}

export async function resolveSession(
  token: string,
  env: Env
): Promise<Session | null> {
  const raw = await env.SESSIONS.get(token);
  if (!raw) return null;
  const session: Session = JSON.parse(raw);
  if (session.expiresAt < Date.now()) {
    await env.SESSIONS.delete(token);
    return null;
  }
  return session;
}
```

```bash
# Commit progress in the refactor worktree
cd ../refactor-auth
git add src/auth/
git commit -m "refactor(auth): introduce session module with KV backing"

# Push the refactor branch so CI validates it
git push -u origin refactor/auth-overhaul
```

```bash
# Rebase script — run this every morning or after significant main commits
#!/usr/bin/env bash
set -euo pipefail

REFACTOR_DIR="../refactor-auth"

# Update main in the primary worktree
git fetch origin
git merge --ff-only origin/main

# Rebase the refactor branch onto the updated main
pushd "$REFACTOR_DIR"
git rebase origin/main
popd

echo "Rebase complete. Run tests in $REFACTOR_DIR."
```

---

## Section 3 — Running Tests in Both Worktrees Simultaneously

```bash
# Terminal 1 — main worktree tests
cd /path/to/project
npm test -- --watch

# Terminal 2 — refactor worktree tests
cd /path/to/project
npm test -- --watch

# Terminal 3 — wrangler dev on refactor branch (port 8788 to avoid clash)
cd /path/to/project
npx wrangler dev --port 8788

# Smoke test the refactor worker
curl -s http://localhost:8788/auth/session \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_123","scopes":["read","write"]}' | jq .
```

```bash
# Merge strategy when refactor is ready
cd /path/to/project

# Final rebase to minimise conflicts
pushd ../refactor-auth
git rebase origin/main
git push --force-with-lease origin refactor/auth-overhaul
popd

# Squash-merge to keep main history clean
git merge --squash refactor/auth-overhaul
git commit -m "feat(auth): replace legacy session logic with KV-backed sessions"
git push origin main

# Remove the worktree and branch after merge
git worktree remove ../refactor-auth
git branch -d refactor/auth-overhaul
git push origin --delete refactor/auth-overhaul
```

---

## Anti-patterns

- **Rebasing the refactor infrequently** — diverging for more than a few days makes conflicts compound; daily or every-other-day rebases keep delta small.
- **Sharing `node_modules` between worktrees with symlinks** — packages with native bindings or lifecycle hooks can produce inconsistent builds; each worktree should run `npm ci` independently.
- **Merging from the refactor into `main` mid-flight** — partial merges bring half-finished auth changes to production; wait until the refactor is feature-complete and all tests pass.
- **Opening the same `wrangler dev` port in both worktrees** — port conflicts silently fall back to an already-running process, causing test requests to hit the wrong build.

---

## Gotchas

- `git rebase` inside a worktree operates on that worktree's `HEAD` only; it does not affect the main worktree's branch.
- If `npm ci` in the refactor worktree produces a lock-file change, commit it there and keep `package-lock.json` in sync with main via cherry-pick or rebase rather than manual edits.
- VS Code may detect only one `.git` root; open the refactor worktree as a separate window or use a multi-root workspace to get full IDE support in both trees.
- `git stash` is shared across all worktrees because it uses `refs/stash` in the shared `.git` directory — use descriptive stash messages or prefer WIP commits instead.
- After a `--squash` merge, delete the remote refactor branch promptly; leaving it open invites accidental new commits that will not be tracked on `main`.

---

## Verification

```bash
# Confirm both worktrees are clean before merge
git -C /path/to/project status
git -C /path/to/project status

# Confirm refactor tests pass
npm --prefix /path/to/project test

# Confirm main tests pass post-merge
npm --prefix /path/to/project test

# Confirm refactor worktree is gone
git worktree list
```

---

## Related

- `git-worktree-hotfix-production-parallel.md`
- `git-worktree-monorepo-package-parallel-dev.md`

---

## Sources

- Git Worktrees Documentation — https://git-scm.com/docs/git-worktree
- Git Rebase Documentation — https://git-scm.com/docs/git-rebase
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
