# Parallel Package Development in a Workers Monorepo Using Git Worktrees

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers monorepo contains multiple packages under `packages/` that are developed independently by different team members. Running all packages from a single working tree means one developer's unstaged changes can affect another's local preview, and a single `wrangler dev` command cannot serve multiple workers on the same port. Git worktrees combined with port-mapped `wrangler dev` processes and a VS Code multi-root workspace solve all three problems simultaneously.

---

## Context

A Workers monorepo managed by Turborepo or npm workspaces compiles each package independently but shares a single lock file and `node_modules` hoist. When two developers need to iterate on different packages simultaneously, git worktrees let each developer (or CI agent) materialise the packages they care about in separate directories with separate branches. The `npm link` technique or Turborepo's remote cache allows the shared build artefacts to be reused across worktrees without duplicating gigabytes of dependencies. Each `wrangler dev` instance is assigned a unique local port so requests can be routed to the correct package during integration testing.

---

## Section 1 — Monorepo Layout and Worktree Setup

```bash
# Monorepo root structure
# my-monorepo/
#   packages/
#     api-gateway/    wrangler.toml  src/
#     auth-service/   wrangler.toml  src/
#     media-worker/   wrangler.toml  src/
#   turbo.json
#   package.json
#   package-lock.json

git fetch origin

# Worktree for api-gateway feature
git worktree add ../wt-api-gateway -b feat/api-gateway-v2 origin/main

# Worktree for auth-service refactor
git worktree add ../wt-auth-service -b feat/auth-service-tokens origin/main

# Worktree for media-worker bugfix
git worktree add ../wt-media-worker -b fix/media-worker-timeout origin/main

git worktree list
# /path/to/project     abc1234 [main]
# /path/to/project  abc1234 [feat/api-gateway-v2]
# /path/to/project abc1234 [feat/auth-service-tokens]
# /path/to/project abc1234 [fix/media-worker-timeout]
```

```bash
# Install dependencies in each worktree (hoisted node_modules per worktree)
npm ci --prefix /path/to/project
npm ci --prefix /path/to/project
npm ci --prefix /path/to/project

# Or use npm link to avoid reinstalling shared packages
cd /path/to/project
npm link ./packages/shared-utils
cd /path/to/project
npm link shared-utils
```

---

## Section 2 — Wrangler Dev on Separate Ports and Turborepo Caching

```toml
# packages/api-gateway/wrangler.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[dev]
port = 8787
local_protocol = "http"
```

```toml
# packages/auth-service/wrangler.toml
name = "auth-service"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[dev]
port = 8788
local_protocol = "http"
```

```toml
# packages/media-worker/wrangler.toml
name = "media-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[dev]
port = 8789
local_protocol = "http"
```

```bash
# Start each package in its own terminal from its worktree
# Terminal 1
cd /path/to/project
npx wrangler dev
# Listening on http://localhost:8787

# Terminal 2
cd /path/to/project
npx wrangler dev
# Listening on http://localhost:8788

# Terminal 3
cd /path/to/project
npx wrangler dev
# Listening on http://localhost:8789
```

```json
// turbo.json — enable remote caching across worktrees
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true
  },
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".wrangler/tmp/**"]
    },
    "test": {
      "dependsOn": ["build"],
      "cache": true
    },
    "dev": {
      "persistent": true,
      "cache": false
    }
  }
}
```

---

## Section 3 — VS Code Multi-Root Workspace

```json
// my-monorepo.code-workspace
{
  "folders": [
    {
      "name": "main (my-monorepo)",
      "path": "/path/to/project
    },
    {
      "name": "feat: api-gateway-v2",
      "path": "/path/to/project
    },
    {
      "name": "feat: auth-service-tokens",
      "path": "/path/to/project
    },
    {
      "name": "fix: media-worker-timeout",
      "path": "/path/to/project
    }
  ],
  "settings": {
    "editor.formatOnSave": true,
    "typescript.tsdk": "my-monorepo/node_modules/typescript/lib",
    "eslint.workingDirectories": [
      { "pattern": "/path/to/project },
      { "pattern": "/path/to/project },
      { "pattern": "/path/to/project }
    ]
  },
  "extensions": {
    "recommendations": [
      "dbaeumer.vscode-eslint",
      "esbenp.prettier-vscode",
      "cloudflare.cloudflare-workers-bindings"
    ]
  }
}
```

```bash
# Open the multi-root workspace
code /path/to/project

# Integration test: verify all three workers respond
curl -s http://localhost:8787/health | jq '.service'
curl -s http://localhost:8788/health | jq '.service'
curl -s http://localhost:8789/health | jq '.service'
```

---

## Anti-patterns

- **Sharing a single `node_modules` between worktrees via symlinks** — Turborepo and npm hoisting assume the `node_modules` root is a sibling of `package.json`; a symlinked shared store breaks path resolution for native modules.
- **Using the same `wrangler dev` port in multiple worktrees** — the second `wrangler dev` silently fails or picks a random port; always set explicit ports in `wrangler.toml` `[dev]` section.
- **Committing the `.code-workspace` file with absolute paths** — absolute paths break the workspace for teammates with different home directories; use relative paths or `${workspaceFolder}` variables where VS Code supports them.
- **Forgetting to rebase worktrees before opening a PR** — each worktree branch can fall behind `main` independently; automate a daily rebase via a cron script or GitHub Actions schedule.

---

## Gotchas

- TypeScript's language server resolves types from the `tsconfig.json` nearest to the open file; point `typescript.tsdk` in the workspace settings to the single shared `node_modules/typescript/lib` to avoid version mismatches.
- `npx wrangler dev` reads `wrangler.toml` from the current working directory; always `cd` into the specific package directory before starting the dev server, not the monorepo root.
- Turborepo's file-system hash-based cache is keyed to the absolute path; builds in worktrees at different paths will not share the local cache, but the remote cache (keyed by inputs) will still be shared.
- Each worktree has its own `.wrangler/` directory; local KV and D1 data created in one worktree's dev session is not visible to another worktree's dev session.
- Removing a worktree with `git worktree remove` does not delete the branch; delete the branch separately with `git branch -d` and `git push origin --delete`.

---

## Verification

```bash
# Confirm all three dev servers are listening
ss -tlnp | grep -E '8787|8788|8789'

# Confirm each worker returns its service name
for port in 8787 8788 8789; do
  echo -n "Port $port: "
  curl -sf "http://localhost:$port/health" | jq -r '.service'
done

# Confirm worktree branches are clean
for dir in wt-api-gateway wt-auth-service wt-media-worker; do
  echo "=== $dir ==="
  git -C "/path/to/project status --short
done
```

---

## Related

- `git-worktree-long-running-refactor-isolation.md`
- `changesets-workers-monorepo-versioning.md`

---

## Sources

- Git Worktrees Documentation — https://git-scm.com/docs/git-worktree
- Turborepo Remote Caching — https://turbo.build/repo/docs/core-concepts/remote-caching
- VS Code Multi-Root Workspaces — https://code.visualstudio.com/docs/editor/multi-root-workspaces
- Wrangler Dev Reference — https://developers.cloudflare.com/workers/wrangler/commands/#dev
