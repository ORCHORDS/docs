# pnpm Recursive Exec for Cloudflare Workers Monorepo Build Pipelines

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You manage a pnpm workspace with several Cloudflare Workers packages and need reliable, composable build and deploy commands that work both locally and in CI without reaching for a full orchestration layer. Ad-hoc shell loops break on package names with spaces or special characters, and npm scripts duplicated across packages drift over time.

## Context

The `pnpm -r` (recursive) flag runs a lifecycle script or shell command in every workspace package. Combined with `--filter`, `--parallel`, and `--stream`, it covers the majority of monorepo build orchestration needs without Turborepo or Nx. For deployment, `pnpm deploy` (singular, not recursive) creates a pruned, self-contained install of a package and its production dependencies — ideal for containerised Workers deployments. The `workspace:*` protocol links local packages at symlink speed with zero publish friction.

## Workspace Layout

```
repo/
  pnpm-workspace.yaml
  package.json               # root — dev tooling only
  packages/
    api-gateway/
      package.json
      wrangler.toml
      src/
    auth-worker/
      package.json
      wrangler.toml
      src/
    shared-utils/
      package.json           # no wrangler.toml — library only
      src/
```

```yaml
# pnpm-workspace.yaml
packages:
  - 'packages/*'
```

## Recursive Build Commands

```bash
# Build all packages in dependency order (sequential, respects deps)
pnpm -r run build

# Build all packages in parallel — only safe when there are no cross-deps
pnpm -r --parallel run build

# Build only Worker packages (exclude shared libraries)
pnpm -r --filter './packages/api-gateway' --filter './packages/auth-worker' run build

# Build a package and all its local dependencies
pnpm --filter 'api-gateway...' run build

# Build packages that depend on shared-utils (reverse filter)
pnpm --filter '...shared-utils' run build

# Run an arbitrary command in every package (not a script)
pnpm -r exec -- wrangler types

# Stream output with package prefix labels
pnpm -r --stream run build
```

## Selective Deploy with --filter

```bash
# Deploy a single Worker
pnpm --filter api-gateway run deploy

# Deploy all Workers (packages with a wrangler.toml)
pnpm -r --filter './packages/api-gateway' \
     --filter './packages/auth-worker' \
     run deploy

# Deploy packages changed since last commit (git-based filter)
PKGS=$(git diff --name-only HEAD~1 HEAD \
  | grep '^packages/' \
  | cut -d/ -f1-2 \
  | sort -u)
for PKG in $PKGS; do
  pnpm --filter "./$(basename $PKG)" run deploy
done
```

## pnpm deploy for Isolated Package Installs

`pnpm deploy` (without `-r`) copies a single package with its production deps into a target directory, similar to `npm pack` but with a fully resolved `node_modules`:

```bash
# Create a production-only install of api-gateway in /tmp/deploy-api-gateway
pnpm --filter api-gateway deploy --prod /tmp/deploy-api-gateway

# The target is ready for docker build or direct wrangler upload
ls /tmp/deploy-api-gateway
# node_modules/  package.json  src/  wrangler.toml

cd /tmp/deploy-api-gateway
wrangler deploy --env production
```

This is especially useful in Dockerfiles for Workers deployed via Container Instances:

```dockerfile
# Dockerfile (multi-stage)
FROM node:20-slim AS build
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm --filter api-gateway deploy --prod /app

FROM node:20-slim
WORKDIR /app
COPY --from=build /app .
CMD ["node", "src/index.js"]
```

## workspace: Protocol for Service Binding Dependencies

Local packages referenced by Workers should use the `workspace:*` protocol so pnpm links them at build time rather than resolving from the registry:

```json
// packages/api-gateway/package.json
{
  "name": "api-gateway",
  "dependencies": {
    "@repo/shared-utils": "workspace:*",
    "hono": "^4.0.0"
  },
  "scripts": {
    "build": "wrangler build",
    "deploy": "wrangler deploy --env production",
    "types": "wrangler types"
  }
}
```

During `pnpm publish` or `pnpm deploy`, the `workspace:*` specifier is rewritten to the actual version number, preventing broken references in published artifacts.

## Security Scanning

```bash
# Audit all packages recursively
pnpm audit --recursive

# Audit only production deps (skip devDependencies)
pnpm audit --recursive --prod

# Output machine-readable JSON for CI parsing
pnpm audit --recursive --json 2>/dev/null | \
  jq '.advisories | to_entries[] | {id: .key, severity: .value.severity, module: .value.module_name}'

# Fix auto-fixable vulnerabilities
pnpm audit --recursive --fix

# Check for outdated packages across workspace
pnpm -r outdated
```

In CI, gate on non-zero exit codes:

```yaml
# .github/workflows/ci.yml (excerpt)
- name: Security audit
  run: |
    pnpm audit --recursive --prod --audit-level=high
  # exits non-zero if any HIGH or CRITICAL advisories found
```

## Anti-patterns

- **`pnpm -r --parallel run build` when packages share build outputs** — parallel recursive runs can race on shared `dist/` directories or `.wrangler/` caches; use sequential `-r run build` or Turborepo for dependency-aware parallelism.
- **Using `pnpm -r run deploy` without ordering** — Workers with service bindings must deploy in dependency order; recursive parallel deploy can push `worker-b` before `worker-a` is live.
- **Relying on `npm_lifecycle_event` instead of `pnpm_package_name`** — some scripts detect their context via lifecycle variables; in pnpm workspaces use `$npm_package_name` for the current package name.
- **Forgetting `--prod` in `pnpm deploy`** — without it, the target directory includes devDependencies (TypeScript, test frameworks), bloating the upload.
- **Hardcoding package paths in filter flags** — use glob patterns (`'./packages/*'`) so new packages are automatically included without updating CI scripts.

## Gotchas

- `pnpm -r exec` and `pnpm -r run` have different semantics: `exec` runs a binary; `run` runs a `package.json` script.
- `--parallel` in recursive mode ignores the `dependencies` field in `package.json`; packages run concurrently regardless of inter-package dependencies.
- `pnpm deploy` requires `node_modules` to exist at the root level first; run `pnpm install` before `pnpm deploy`.
- `workspace:*` is rewritten only during `pnpm publish` and `pnpm deploy`; checking the literal string in the published `package.json` will show the resolved version.
- `pnpm audit` exit codes: 0 = no issues, 1 = issues below threshold, 2 = issues at or above threshold.

## Verification

```bash
# Confirm workspace packages are linked, not registry-fetched
pnpm list --recursive --depth=0 | grep '@repo/'

# Verify pnpm deploy produces a clean tree
pnpm --filter api-gateway deploy --prod /tmp/test-deploy
ls /tmp/test-deploy/node_modules/ | head -20
grep 'devDependencies' /tmp/test-deploy/package.json || echo 'clean: no devDeps'

# Smoke-test the recursive build
pnpm -r run build 2>&1 | tail -20

# Check audit exit code
pnpm audit --recursive --prod --audit-level=high; echo "Exit: $?"
```

## Related

- `turborepo-affected-package-workers-deploy-gate.md`
- `git-worktree-ci-matrix-parallel-workers-deploy.md`

## Sources

- pnpm recursive flags — https://pnpm.io/cli/recursive
- pnpm deploy command — https://pnpm.io/cli/deploy
- pnpm workspace protocol — https://pnpm.io/workspaces#workspace-protocol-workspace
- pnpm filtering — https://pnpm.io/filtering
- pnpm audit — https://pnpm.io/cli/audit
