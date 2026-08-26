# pnpm Catalog Protocol for Monorepo Dependency Alignment

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your monorepo has 12 packages. Package A depends on `zod@3.22.4`, package B depends on `zod@3.23.0`, and package C depends on `zod@3.21.0`. Three different versions of the same library install into `node_modules`, TypeScript types from one version break inference in another, and Renovate opens 12 separate PRs when a new Zod version releases. Keeping shared dependencies aligned across packages requires manual coordination that breaks constantly.

---

## Context

pnpm 9.0 introduced the **catalog protocol**, a first-class mechanism for declaring canonical version ranges for dependencies at the workspace root. Instead of hardcoding a version specifier inside each package's `package.json`, a package declares `"zod": "catalog:"` and pnpm resolves it against the workspace root's `pnpm-workspace.yaml` catalog. The catalog entry is the single source of truth for the version. Updating one catalog entry updates every package that references it.

This solves the problem of version drift in monorepos without the complexity of Changesets or a shared `dependencies` package. It is particularly useful in Cloudflare Workers monorepos where `wrangler`, `@cloudflare/workers-types`, and testing libraries like `vitest` must stay aligned across all Worker packages.

---

## Section 1: Catalog Configuration

Define catalogs in `pnpm-workspace.yaml` at the monorepo root:

```yaml
# pnpm-workspace.yaml
packages:
  - "packages/*"
  - "apps/*"

# Default catalog — referenced as "catalog:" in package.json
catalog:
  # Cloudflare
  wrangler: "^3.78.0"
  "@cloudflare/workers-types": "^4.20260101.0"
  "@cloudflare/vitest-pool-workers": "^0.5.0"

  # Testing
  vitest: "^2.1.0"
  "@vitest/coverage-v8": "^2.1.0"

  # Utilities
  zod: "^3.23.0"
  hono: "^4.5.0"
  itty-router: "^5.0.0"

  # TypeScript
  typescript: "^5.6.0"
  "@types/node": "^22.0.0"

# Named catalogs — referenced as "catalog:<name>" in package.json
catalogs:
  react18:
    react: "^18.3.0"
    react-dom: "^18.3.0"
    "@types/react": "^18.3.0"
    "@types/react-dom": "^18.3.0"

  react19:
    react: "^19.0.0"
    react-dom: "^19.0.0"
    "@types/react": "^19.0.0"
    "@types/react-dom": "^19.0.0"
```

---

## Section 2: Using Catalogs in package.json

In each package's `package.json`, replace hardcoded version specifiers with catalog references:

```jsonc
// packages/api-worker/package.json  — BEFORE
{
  "name": "@acme/api-worker",
  "devDependencies": {
    "wrangler": "^3.75.0",
    "@cloudflare/workers-types": "^4.20240101.0",
    "@cloudflare/vitest-pool-workers": "^0.4.0",
    "vitest": "^2.0.0",
    "typescript": "^5.5.0",
    "zod": "^3.22.4"
  }
}
```

```jsonc
// packages/api-worker/package.json  — AFTER
{
  "name": "@acme/api-worker",
  "devDependencies": {
    "wrangler": "catalog:",
    "@cloudflare/workers-types": "catalog:",
    "@cloudflare/vitest-pool-workers": "catalog:",
    "vitest": "catalog:",
    "typescript": "catalog:",
    "zod": "catalog:"
  }
}
```

```jsonc
// packages/admin-ui/package.json  — using a named catalog
{
  "name": "@acme/admin-ui",
  "dependencies": {
    "react": "catalog:react19",
    "react-dom": "catalog:react19",
    "zod": "catalog:"
  },
  "devDependencies": {
    "@types/react": "catalog:react19",
    "@types/react-dom": "catalog:react19",
    "typescript": "catalog:"
  }
}
```

Named catalogs allow controlled migration: `packages/legacy-app` can stay on `catalog:react18` while `packages/admin-ui` moves to `catalog:react19`, making the migration incremental.

---

## Section 3: Verifying Catalog Resolution

After updating `pnpm-workspace.yaml`, run:

```bash
# Install resolves catalog: references to real versions
pnpm install

# Check what version was resolved for a catalog entry
pnpm why zod --filter api-worker
# Output shows: zod@3.23.0 (from catalog: → ^3.23.0)

# List all packages using the catalog (shows resolved versions)
cat pnpm-lock.yaml | grep -A2 "catalog:"
```

The lock file records the resolved version alongside the `catalog:` specifier:

```yaml
# pnpm-lock.yaml (excerpt)
importers:
  packages/api-worker:
    devDependencies:
      zod:
        specifier: catalog:
        version: 3.23.0
```

---

## Section 4: Automating Updates with Renovate

Configure Renovate to update catalog entries in `pnpm-workspace.yaml` rather than individual `package.json` files:

```json
// .renovaterc.json
{
  "extends": ["config:base"],
  "pnpmCatalogs": true,        // Enable pnpm catalog support (Renovate 38+)
  "packageRules": [
    {
      "description": "Cloudflare toolchain — group all updates into one PR",
      "matchManagers": ["pnpm"],
      "matchPackageNames": [
        "wrangler",
        "@cloudflare/workers-types",
        "@cloudflare/vitest-pool-workers"
      ],
      "groupName": "Cloudflare toolchain",
      "groupSlug": "cloudflare-toolchain",
      "schedule": ["every weekend"]
    },
    {
      "description": "TypeScript — pin major, allow minor/patch",
      "matchManagers": ["pnpm"],
      "matchPackageNames": ["typescript"],
      "separateMajorMinor": true,
      "groupName": "TypeScript"
    },
    {
      "description": "React catalogs — one PR per named catalog",
      "matchManagers": ["pnpm"],
      "matchPackageNames": ["react", "react-dom", "@types/react", "@types/react-dom"],
      "groupName": "React {{currentValue major}}",
      "versioning": "semver"
    }
  ]
}
```

With `pnpmCatalogs: true`, Renovate opens **one PR** to update `zod` in `pnpm-workspace.yaml` instead of 12 PRs for each package. All packages referencing `catalog:` automatically receive the update.

---

## Section 5: Enforcing Catalog Usage

Prevent developers from adding hardcoded version specifiers for cataloged dependencies. Add an ESLint-style check with `sherif`:

```bash
pnpm add -D -w sherif
```

```json
// package.json (root)
{
  "scripts": {
    "lint:deps": "sherif"
  }
}
```

```json
// sherif.json
{
  "rules": {
    "packages-without-package-json": "error",
    "root-package-manager-field": "error",
    "non-existant-packages": "error",
    "duplicated-dependencies": {
      "severity": "error",
      // These packages MUST use catalog:
      "fix": false
    }
  }
}
```

Or write a simpler custom check:

```bash
#!/usr/bin/env bash
# scripts/check-catalog-usage.sh
# Fails if any package.json contains a hardcoded version for a catalog entry

CATALOG_PKGS=$(python3 -c "
import yaml, sys
with open('pnpm-workspace.yaml') as f:
    ws = yaml.safe_load(f)
pkgs = list(ws.get('catalog', {}).keys())
for cat in ws.get('catalogs', {}).values():
    pkgs.extend(cat.keys())
print('\n'.join(set(pkgs)))
")

FAIL=0
while IFS= read -r pkg; do
  # Check for hardcoded version (not "catalog:") in any package.json
  results=$(grep -rn "\"$pkg\": \"[^c]" packages/*/package.json apps/*/package.json 2>/dev/null || true)
  if [[ -n "$results" ]]; then
    echo "ERROR: Hardcoded version for cataloged package '$pkg':"
    echo "$results"
    FAIL=1
  fi
done <<< "$CATALOG_PKGS"

exit $FAIL
```

Add to CI and as a pre-commit hook:

```yaml
# .github/workflows/lint.yml
- name: Check catalog usage
  run: bash scripts/check-catalog-usage.sh
```

---

## Section 6: Migrating an Existing Monorepo to Catalogs

Use the official `@pnpm/codemod` tool to automate migration:

```bash
# Dry-run first
npx @pnpm/codemod use-catalogs --dry-run

# Apply migration — rewrites package.json files and pnpm-workspace.yaml
npx @pnpm/codemod use-catalogs

# Review changes
git diff

# Re-install to validate
pnpm install

# Verify lock file is consistent
pnpm install --frozen-lockfile
```

The codemod:
1. Scans all `package.json` files for shared dependencies
2. Picks the highest version seen across packages as the catalog entry
3. Replaces all occurrences with `catalog:` or `catalog:<name>`
4. Writes the catalog stanza to `pnpm-workspace.yaml`

After migration, run tests across all packages to confirm the resolved versions are compatible:

```bash
pnpm -r run test
pnpm -r run typecheck
```

---

## Anti-patterns

- **Mixing catalog: and hardcoded versions for the same package.** If `api-worker` uses `catalog:` for `zod` and `auth-worker` hardcodes `"zod": "^3.21.0"`, they will resolve different versions and deduplication fails. Enforce one or the other.
- **Adding every package to the catalog.** Internal packages (`@acme/shared-utils`) do not belong in the catalog. Catalog is for external npm packages only.
- **Using exact versions in the catalog (`"zod": "3.23.0"` instead of `"^3.23.0"`).** Exact pinning means no patch updates apply automatically. Use semver ranges in the catalog; pnpm deduplicates within the range.
- **Forking the catalog per-package.** Overriding a catalog version in a specific `package.json` (`"zod": "3.21.0"` alongside other packages using `catalog:`) defeats the purpose. Use named catalogs (`catalog:legacy`) for intentional divergence.
- **Not updating the lock file in CI after catalog changes.** If `pnpm-workspace.yaml` changes but `pnpm-lock.yaml` is not re-generated, `--frozen-lockfile` will fail with a cryptic error about mismatched specifiers.

---

## Gotchas

- `catalog:` syntax requires pnpm >= 9.0. Verify with `pnpm --version` in CI.
- The `catalog:` specifier appears literally in `pnpm-lock.yaml`. Do not try to read the lock file to determine the resolved version — use `pnpm why <package>` instead.
- Named catalogs (`catalog:react19`) are available from pnpm 9.2+. The default catalog (`catalog:`) is available from pnpm 9.0.
- Renovate's pnpm catalog support (`pnpmCatalogs: true`) requires Renovate >= 38. Self-hosted Renovate instances may lag behind.
- `pnpm dedupe` still applies within catalog-managed installations. Run `pnpm dedupe` after major updates to consolidate versions.
- If a package listed in the catalog is not installed in any workspace package, pnpm emits a warning but does not fail. Clean up unused catalog entries periodically.

---

## Verification

```bash
# After migration: confirm all catalog entries resolve correctly
pnpm install --frozen-lockfile

# No version should appear twice for the same package
pnpm why zod
# Output should show a single version across all workspace packages

# Confirm CI enforcement
bash scripts/check-catalog-usage.sh

# Simulate a catalog update
# 1. Update catalog entry in pnpm-workspace.yaml
# 2. Run pnpm install — all packages get the new version
# 3. Check lock file
grep "zod" pnpm-lock.yaml | grep "version:"
# Should show only one version
```

---

## Related

- `monorepo-pnpm-turborepo-2026.md` — pnpm workspaces and Turborepo pipeline setup
- `dependency-update-automation-renovate.md` — Renovate configuration for monorepos
- `conventional-commits-monorepo-changesets-2026.md` — versioning internal packages alongside external catalogs
- `monorepo-wrangler-selective-deploy.md` — deploying only changed Workers packages
- `dependabot-renovate-2026.md` — choosing between Dependabot and Renovate for catalog updates

---

## Sources

- pnpm Catalogs documentation — https://pnpm.io/catalogs
- pnpm 9.0 release notes — https://github.com/pnpm/pnpm/releases/tag/v9.0.0
- `@pnpm/codemod` — https://github.com/pnpm/pnpm/tree/main/packages/codemod
- Renovate pnpm catalog support — https://docs.renovatebot.com/modules/manager/pnpm/
- sherif monorepo linter — https://github.com/nicolo-ribaudo/sherif
