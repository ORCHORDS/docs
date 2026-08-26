# WIP Stashing Workflow for Rapid Context Switching Across Workers Features

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You are mid-way through implementing a new Workers route when a teammate posts a Slack alert:
the rate-limiting middleware on the `hotfix/rate-limit` branch has a production bug. You need to
switch branches immediately, fix the bug, deploy it, and return to your feature work without
losing any of your in-progress edits. Your changes are not ready to commit.

---

## Context

`git stash` saves the current working tree state (tracked modifications and, optionally,
untracked files) onto a stack, restoring a clean working tree so you can check out another
branch. It is lighter than a worktree for brief, single-context switches but becomes unwieldy
when you are juggling three or more long-lived workstreams simultaneously.

Key concepts:
- The stash stack is per-repository and shared across all worktrees.
- Stash entries have an auto-generated name (`stash@{0}`) but can be given a description with
  `--message` or `-m`.
- `wrangler dev` does not survive a branch switch; it must be restarted after `git stash pop`.
- Untracked files (new files not yet staged) are excluded from stash by default; use `-u` to
  include them.

---

## Solution

### 1. Stash WIP with a descriptive message

```bash
# Save everything including untracked files
git stash push -u --message "feat/route-handler: wip auth middleware integration"
```

Convention for stash message format:

```
<branch-short-name>: <one-line description of current state>
```

Examples:
```
feat/rate-limit-v2: wip — half-refactored middleware, tests broken
feat/kv-cache: wip — new cache key schema, needs KV binding
hotfix/cors: wip — untested header normalization
```

### 2. Switch branch and do the urgent work

```bash
git checkout hotfix/rate-limit

# ... make the fix ...
npx wrangler deploy --env production

git checkout -   # return to previous branch (the one you stashed from)
```

### 3. Restore the stash

```bash
# List the stack first to confirm which entry to apply
git stash list
# stash@{0}: On feat/route-handler: feat/route-handler: wip auth middleware integration
# stash@{1}: On feat/kv-cache: wip — new cache key schema, needs KV binding

# Pop the top entry (applies and removes from stack)
git stash pop

# Or apply without removing (safer if you might need to re-apply)
git stash apply stash@{0}
```

### 4. Restart wrangler dev after pop

Wrangler dev does not survive a stash/checkout cycle because its child process holds file
descriptors and in-memory state tied to the old branch. After `git stash pop`, restart it:

```bash
# Kill any running wrangler dev process
pkill -f 'wrangler dev' 2>/dev/null || true

# Restart for the restored branch
npx wrangler dev --port 8787 --local
```

Automate this with a shell function in your `.bashrc` / `.zshrc`:

```bash
wstash-pop() {
  git stash pop "$@"
  local exit_code=$?
  if [ $exit_code -eq 0 ]; then
    pkill -f 'wrangler dev' 2>/dev/null || true
    echo "[wstash] stash popped — restart wrangler dev manually or run: npx wrangler dev --local"
  fi
  return $exit_code
}
```

### 5. TypeScript helper — stash manager

```typescript
// scripts/stash-manager.ts
import { execSync } from 'node:child_process';

interface StashEntry {
  index: number;
  ref: string;
  branch: string;
  message: string;
}

function listStash(): StashEntry[] {
  const raw = execSync('git stash list', { encoding: 'utf8' }).trim();
  if (!raw) return [];

  return raw.split('\n').map((line, i) => {
    // stash@{0}: On branch-name: message
    const match = line.match(/^(stash@\{(\d+)\}): On ([^:]+): (.+)$/);
    if (!match) return { index: i, ref: `stash@{${i}}`, branch: 'unknown', message: line };
    return {
      index: parseInt(match[2], 10),
      ref: match[1],
      branch: match[3],
      message: match[4],
    };
  });
}

function pushStash(message: string, includeUntracked = true): void {
  const flags = includeUntracked ? '-u' : '';
  execSync(`git stash push ${flags} --message "${message}"`, { stdio: 'inherit' });
}

function popStash(ref = 'stash@{0}'): void {
  execSync(`git stash pop ${ref}`, { stdio: 'inherit' });
  try {
    execSync('pkill -f "wrangler dev"', { stdio: 'ignore' });
  } catch {
    // No running wrangler dev process — that is fine
  }
  console.log('Stash popped. Run: npx wrangler dev --local');
}

// CLI usage: npx ts-node scripts/stash-manager.ts list
const [, , command, ...args] = process.argv;
switch (command) {
  case 'list':
    console.table(listStash());
    break;
  case 'push':
    pushStash(args.join(' '));
    break;
  case 'pop':
    popStash(args[0]);
    break;
  default:
    console.log('Usage: stash-manager.ts list | push <message> | pop [ref]');
}
```

---

## Implementation Details

### Stash naming conventions

Adopt a consistent format across your team:

| Pattern | Example |
|---------|---------|
| `<branch>: wip — <state>` | `feat/auth: wip — token validation half done` |
| `<ticket>: <description>` | `JIRA-1234: partial cache refactor` |
| `<date> <branch>: <state>` | `2026-08-24 feat/kv: broken tests` |

Document the convention in `CONTRIBUTING.md`.

### Stash vs. worktree decision matrix

| Scenario | Use stash | Use worktree |
|----------|-----------|-------------|
| Single urgent fix, < 30 min | Yes | No |
| Two features running simultaneously | No | Yes |
| Need parallel `wrangler dev` instances | No | Yes |
| WIP not ready to commit | Yes | Either |
| Different `wrangler.toml` configs per branch | No | Yes |
| Long-running feature, days of work | No | Yes |

### Stash stack hygiene

```bash
# Drop a specific stash entry that is no longer needed
git stash drop stash@{2}

# Clear the entire stash stack (destructive — cannot be undone)
git stash clear

# Show the diff of a stash entry before applying
git stash show -p stash@{1}
```

---

## Anti-patterns

- **Not using `-u` when new files exist.** Without `-u`, new (untracked) files are left in the
  working tree after the stash and will appear to belong to the branch you switch to.
- **Stashing without a message.** Auto-generated stash names (`WIP on branch: abc1234 commit
  message`) are cryptic. Always use `--message`.
- **Using stash for work that spans multiple days.** Long-lived stash entries accumulate and
  become difficult to apply cleanly as the base diverges. Use a draft branch or worktree instead.
- **Forgetting to restart `wrangler dev` after pop.** The running dev server retains the old
  branch's bundle in memory. Changes from the popped stash are not reflected until restart.

---

## Gotchas

- `git stash pop` is equivalent to `git stash apply` followed by `git stash drop`. If the apply
  fails due to a conflict, the stash entry is NOT dropped, so your changes are not lost.
- Stash entries survive `git worktree` operations. A stash created in a worktree is visible
  from the primary tree and vice versa.
- `wrangler dev` in `--remote` mode holds an open connection to Cloudflare's preview
  infrastructure. Stashing and switching branches does not close that connection; kill the
  process explicitly.

---

## Verification

```bash
# Confirm the stash was created
git stash list | head -3

# Confirm the working tree is clean before switching
git status --short

# After pop, confirm all files are restored
git diff HEAD --name-only

# Confirm wrangler picks up the restored changes
npx wrangler dev --local --port 8787 &
sleep 3 && curl -s http://localhost:8787/health
```

---

## Related

- `workers-worktree-parallel-wrangler-dev.md` — worktree approach for concurrent dev sessions
- `workers-bisect-regression-isolation.md` — stash your WIP before starting a bisect
- `workers-gitops-auto-deploy-main-branch.md` — ensure stashed changes are not accidentally
  deployed

---

## Sources

- https://git-scm.com/docs/git-stash
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://git-scm.com/book/en/v2/Git-Tools-Stashing-and-Cleaning
