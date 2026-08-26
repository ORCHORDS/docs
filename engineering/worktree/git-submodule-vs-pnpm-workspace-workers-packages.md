# Git Submodules vs pnpm Workspaces for Shared Workers Packages

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your team maintains shared TypeScript utilities—KV helpers, D1 query builders, error types—consumed by multiple Cloudflare Workers. You need to decide whether to version and share these packages as git submodules pinned to specific SHAs or as pnpm workspace packages inside a monorepo. The wrong choice leads to either version drift across Workers or an unworkable build graph in CI.

## Context

Git submodules embed a pointer (commit SHA) to a foreign repository inside a parent repository. They work well for vendoring large external codebases at a fixed version, but they introduce significant friction for shared internal packages that change frequently: every consumer repo must manually run `git submodule update` after each change, CI pipelines need recursive clone flags, and cross-package refactors require multiple coordinated PRs across repos. pnpm workspaces, by contrast, keep all packages in a single repository tree with symlinked `node_modules`, enabling atomic cross-package changes, single-pass CI, and automatic change detection via tools like Turborepo. For Cloudflare Workers monorepos in particular, `wrangler` builds each Worker in isolation but can consume workspace packages through standard `node_modules` resolution, making the workspace model the dominant pattern in production teams as of 2026.

## Git Submodule Workflow for Shared Workers Packages

```bash
# Add a shared utilities repo as a submodule
git submodule add \
  https://github.com/org/workers-shared-utils \
  packages/shared-utils

# Pin to a specific release tag
cd packages/shared-utils
git checkout v2.1.0
cd ../..
git add .gitmodules packages/shared-utils
git commit -m "chore: pin shared-utils submodule to v2.1.0"

# Clone with submodules in CI
git clone --recurse-submodules https://github.com/org/workers-monorepo

# Update a submodule to a newer commit
git submodule update --remote packages/shared-utils
git add packages/shared-utils
git commit -m "chore: bump shared-utils submodule to HEAD"

# Check which commit each submodule is pinned to
git submodule status

# Run a command inside each submodule (e.g. build)
git submodule foreach 'pnpm build'
```

## pnpm Workspace Workflow for Shared Workers Packages

```bash
# pnpm-workspace.yaml at repo root
cat > pnpm-workspace.yaml << 'EOF'
packages:
  - 'packages/*'
  - 'workers/*'
EOF

# packages/shared-utils/package.json
cat > packages/shared-utils/package.json << 'EOF'
{
  "name": "@monorepo/shared-utils",
  "version": "2.1.0",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc -p tsconfig.json"
  }
}
EOF

# Declare workspace dependency in a Worker
# workers/api-gateway/package.json
cat > workers/api-gateway/package.json << 'EOF'
{
  "name": "@monorepo/api-gateway",
  "dependencies": {
    "@monorepo/shared-utils": "workspace:*"
  }
}
EOF

# Install — pnpm creates a symlink in node_modules
pnpm install

# Build only affected packages (Turborepo change detection)
pnpm turbo run build --filter=...[origin/main]

# Publish a workspace package to npm if external consumers exist
pnpm --filter @monorepo/shared-utils publish --access public
```

## Side-by-Side Comparison

```bash
# --- Cross-package refactor ---

# Submodule: requires 2 PRs and 2 CI pipelines
# 1. PR in workers-shared-utils repo: rename KVHelper → KvClient
# 2. PR in workers-monorepo repo: update submodule SHA + fix import sites

# Workspace: atomic — single PR touches both files
# sed -i 's/KVHelper/KvClient/g' \
#   packages/shared-utils/src/index.ts \
#   workers/api-gateway/src/handler.ts
# git add -p && git commit -m "refactor: rename KVHelper to KvClient"

# --- CI clone time ---

# Submodule (recursive clone adds each sub-repo's history):
git clone --recurse-submodules --depth 1 https://github.com/org/workers-monorepo
# Workspace (single shallow clone):
git clone --depth 1 https://github.com/org/workers-monorepo
pnpm install --frozen-lockfile

# --- Dependency version drift across Workers ---

# Submodule: each consuming repo pins its own SHA — drift is intentional
git -C workers/legacy-worker/packages/shared-utils log --oneline -1
# workspace:* — all Workers in the monorepo always use the same local source
pnpm list --filter @monorepo/api-gateway @monorepo/shared-utils
```

## Migrating from Submodules to pnpm Workspaces

```bash
# Step 1: de-initialize the submodule
git submodule deinit packages/shared-utils
git rm packages/shared-utils
rm -rf .git/modules/packages/shared-utils
git commit -m "chore: remove shared-utils submodule"

# Step 2: copy source files into the monorepo tree
cp -r /path/to/workers-shared-utils/src packages/shared-utils/src
cp /path/to/workers-shared-utils/package.json packages/shared-utils/

# Step 3: add the workspace to pnpm-workspace.yaml (if not already)
echo "  - 'packages/*'" >> pnpm-workspace.yaml

# Step 4: update dependency declarations to workspace protocol
sed -i 's/"@monorepo\/shared-utils": "[^"]*"/"@monorepo\/shared-utils": "workspace:*"/g' \
  workers/*/package.json

# Step 5: reinstall and verify
pnpm install
pnpm turbo run build test
```

## Anti-patterns

- Using git submodules for packages that change more than once per sprint—the constant `git submodule update` + commit churn in the parent repo is a significant drag on developer velocity.
- Using `workspace:*` for packages that genuinely need independent versioning consumed by external teams—in that case pnpm `workspace:^` with Changesets is more appropriate than pinning to the live source.
- Mixing both approaches in the same monorepo for similar package types—developers cannot predict which `import` path resolution mechanism applies without checking `package.json` each time.
- Shallow-cloning (`--depth 1`) a repo with submodules without also passing `--recurse-submodules --shallow-submodules`; the submodule directories will be present but empty, causing silent build failures.

## Gotchas

- `wrangler build` does not traverse `node_modules` symlinks by default in some older versions; ensure `wrangler.toml` does not set `no_bundle = true` when consuming workspace packages via symlinks.
- pnpm's `shamefully-hoist` option should stay `false` in Workers projects; Workers runtimes mirror Node's module resolution only partially and hoisted phantom deps cause runtime errors that don't surface in local dev.
- When running `git submodule foreach` in CI, the subcommand runs in each submodule's working directory—relative paths in scripts break unless you use absolute paths or `$toplevel`.

## Verification

```bash
# Submodule: confirm all submodules are at expected SHAs
git submodule status | grep -v "^-"  # lines starting with - are uninitialized

# Workspace: confirm symlinks resolve correctly
ls -la node_modules/@monorepo/shared-utils
pnpm list --depth 0 --filter @monorepo/api-gateway

# Build all Workers and confirm no missing-module errors
pnpm turbo run build 2>&1 | grep -E "ERROR|error TS"

# Run wrangler dev against a Worker that consumes the workspace package
pnpm --filter @monorepo/api-gateway exec wrangler dev --local
```

## Related

- `worktree/git-submodules-vs-subtrees.md`
- `worktree/monorepo-workspace-cloudflare-workers.md`
- `worktree/pnpm-catalog-monorepo-dependency-alignment.md`
- `worktree/monorepo-pnpm-turborepo-2026.md`

## Sources

- https://git-scm.com/book/en/v2/Git-Tools-Submodules
- https://pnpm.io/workspaces
- https://developers.cloudflare.com/workers/wrangler/configuration/
