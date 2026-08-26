# Running Parallel wrangler dev Instances in Separate Git Worktrees

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You are working on two Workers features simultaneously — say, a new authentication handler and a
refactored KV caching layer — and need to run `wrangler dev` for both at the same time without
constantly stashing changes or switching branches. Each instance must bind to a unique local port
so they do not collide, and each must read its own set of secret variables.

---

## Context

A single git working tree allows only one checked-out branch at a time. Running `wrangler dev`
for two branches in the same directory requires constant branch switching, which interrupts flow
and risks mixing in-progress changes. Git worktrees solve this by projecting additional branches
into separate filesystem paths while sharing the same `.git` object store, so history, objects,
and pack files are never duplicated. Wrangler itself is stateless between runs and reads its
configuration from the directory it is invoked in, making worktrees a natural fit.

Key facts:
- Each worktree maintains its own `HEAD`, index, and working files.
- `node_modules` can be symlinked from the primary tree to avoid redundant installs.
- `.dev.vars` is loaded from the worktree root, so per-worktree secrets are trivially isolated.
- Wrangler's `--port` flag prevents port conflicts between concurrent instances.

---

## Solution

### 1. Create the worktree

```bash
# From the primary working tree root
git worktree add ../workers-auth-feature feature/auth-overhaul
git worktree add ../workers-kv-cache   feature/kv-cache-refactor
```

This creates two sibling directories at the same level as your primary tree, each checked out
on its own branch. The `.git` directory in each worktree is a plain file (not a directory)
containing a `gitdir:` pointer back to the shared object store.

### 2. Symlink node_modules to avoid redundant installs

```bash
PRIMARY="$(pwd)"

for tree in ../workers-auth-feature ../workers-kv-cache; do
  if [ ! -d "${tree}/node_modules" ]; then
    ln -s "${PRIMARY}/node_modules" "${tree}/node_modules"
  fi
done
```

This works as long as both branches share a compatible `package.json`. If the branches diverge in
dependencies, run `npm ci` in the worktree directory instead of symlinking.

### 3. Per-worktree .dev.vars

`wrangler dev` loads `.dev.vars` from the working directory. Place secrets there:

```bash
# ../workers-auth-feature/.dev.vars
AUTH_SECRET=dev-secret-for-auth-branch
JWT_AUDIENCE=https://dev-auth.example.com
```

```bash
# ../workers-kv-cache/.dev.vars
KV_NAMESPACE_PREVIEW_ID=abc123def456
CACHE_TTL_SECONDS=60
```

Because `.dev.vars` is gitignored by convention, these files do not appear in diffs and are not
accidentally committed.

### 4. Start parallel wrangler dev instances with distinct ports

Open two terminal sessions (or use a terminal multiplexer such as tmux):

```bash
# Terminal 1 — auth branch
cd ../workers-auth-feature
npx wrangler dev --port 8787 --local
```

```bash
# Terminal 2 — KV cache branch
cd ../workers-kv-cache
npx wrangler dev --port 8788 --local
```

You can now hit `http://localhost:8787` and `http://localhost:8788` independently.

### 5. TypeScript helper — launch script

For a project using npm scripts, add a root-level orchestration helper:

```typescript
// scripts/dev-parallel.ts
import { spawn } from 'node:child_process';
import path from 'node:path';

interface WorktreeConfig {
  dir: string;
  port: number;
  label: string;
}

const worktrees: WorktreeConfig[] = [
  { dir: '../workers-auth-feature', port: 8787, label: 'auth' },
  { dir: '../workers-kv-cache',     port: 8788, label: 'kv-cache' },
];

for (const wt of worktrees) {
  const cwd = path.resolve(wt.dir);
  const child = spawn(
    'npx',
    ['wrangler', 'dev', '--port', String(wt.port), '--local'],
    { cwd, stdio: 'pipe', shell: false },
  );

  child.stdout.on('data', (d: Buffer) =>
    process.stdout.write(`[${wt.label}] ${d}`),
  );
  child.stderr.on('data', (d: Buffer) =>
    process.stderr.write(`[${wt.label}] ${d}`),
  );

  child.on('exit', (code) =>
    console.log(`[${wt.label}] exited with code ${code}`),
  );
}
```

Run with:

```bash
npx ts-node scripts/dev-parallel.ts
```

---

## Implementation Details

### Listing and inspecting worktrees

```bash
git worktree list
# /path/to/project        abc1234 [main]
# /path/to/project   def5678 [feature/auth-overhaul]
# /path/to/project       9ab0123 [feature/kv-cache-refactor]
```

### Locking a worktree to prevent accidental pruning

```bash
git worktree lock ../workers-auth-feature --reason "active dev session"
```

### Port allocation strategy

Reserve a port range per team convention, for example:

| Worktree purpose | Port  |
|------------------|-------|
| main / trunk     | 8787  |
| feature branch A | 8788  |
| feature branch B | 8789  |
| hotfix           | 8790  |

Document this in your project's `CONTRIBUTING.md` to avoid collisions in shared environments.

### wrangler.toml compatibility

If `wrangler.toml` references environment-specific `[env.dev]` sections, both worktrees share
the same configuration file structure. Changes to `wrangler.toml` on one branch do not affect
the other until merged.

---

## Anti-patterns

- **Checking out the same branch in two worktrees.** Git prevents this by design. If you try,
  you receive: `fatal: '<branch>' is already checked out at '<path>'`. Use separate branches or
  detach HEAD in the second worktree.
- **Sharing `.dev.vars` via symlink.** This defeats the isolation purpose. Keep them separate.
- **Running `npm install` in a symlinked `node_modules` directory.** This can corrupt the
  primary tree's modules. If dependencies diverge, break the symlink and run `npm ci` in the
  worktree.
- **Forgetting to set `--port`.** Both instances will attempt to bind port 8787 and the second
  will fail with `EADDRINUSE`.

---

## Gotchas

- Wrangler's local D1 database file defaults to `.wrangler/state/`. In a worktree this path is
  local to the worktree directory, so each worktree gets its own isolated D1 state — a feature,
  not a bug, but be aware when testing cross-feature migrations.
- Git hooks defined in `.git/hooks/` apply to all worktrees because they share the object store.
  Hooks in `.git/worktrees/<name>/hooks/` are worktree-local if you need differentiation.
- Running `wrangler types` in a worktree writes generated types to that worktree's working
  directory only.

---

## Verification

```bash
# Confirm both dev servers respond
curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/health
curl -s -o /dev/null -w "%{http_code}" http://localhost:8788/health

# Confirm worktrees reference distinct commits
git worktree list --porcelain | grep 'HEAD'
```

---

## Cleaning Up Stale Worktrees

```bash
# Remove the worktree directory and deregister it
git worktree remove ../workers-auth-feature

# If the directory was deleted manually, prune the stale reference
git worktree prune --verbose

# Dry-run to see what prune would remove
git worktree prune --dry-run
```

---

## Related

- `workers-stash-wip-context-switch.md` — alternative for single-file edits
- `workers-monorepo-selective-deploy-changeset.md` — monorepo deployment patterns
- `workers-gitops-auto-deploy-main-branch.md` — CI deployment from main

---

## Sources

- https://git-scm.com/docs/git-worktree
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/configuration/secrets/#local-development-with-secrets
