# pnpm Workspaces Selective Test Filtering in CI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Running the full example project monorepo test suite on every PR takes 12–18 minutes. Most PRs touch only one or two packages, yet CI spins up Vitest for all packages including unaffected Cloudflare Workers, D1 migration tests, and UI component suites. The fix is to detect which packages changed relative to `main` and run tests only for those packages — plus their dependents — using `pnpm --filter` with a git-diff-driven filter expression.

---

## Context

`pnpm --filter` supports several selector syntaxes: by package name, by directory glob, `...` (dependents), `^...` (dependencies), and `[<git-range>]` (changed since a ref). The `[origin/main]` selector uses `git diff --name-only origin/main...HEAD` internally to detect which `pnpm-workspace.yaml`-declared packages contain changed files. Combined with `...` suffix traversal, this runs tests for changed packages **and every package that depends on them** — the minimal affected set.

---

## Detecting Changed Packages

Verify which packages `pnpm` considers affected before writing CI logic:

```bash
# List packages changed relative to origin/main
pnpm -r --filter "...[origin/main]" exec pwd

# Include dependents (packages that import the changed ones)
pnpm -r --filter "...{packages}[origin/main]..." exec pwd
```

The `...{packages}[origin/main]...` form means:
- `[origin/main]` — changed since the merge-base of origin/main and HEAD
- `{packages}` — scoped to the `packages/` directory (avoids matching Workers apps)
- surrounding `...` — include transitive dependents

---

## pnpm-workspace.yaml Topology

A well-structured workspace declaration makes filter patterns predictable:

```yaml
# pnpm-workspace.yaml
packages:
  - "packages/*"          # Publishable shared libraries
  - "apps/workers/*"      # Cloudflare Workers (not published to npm)
  - "apps/web"            # Next.js / Vite frontend
  - "tools/*"             # Internal tooling
```

Grouping by directory prefix lets you scope `--filter` to just `packages/` when you only want library tests, or `apps/workers/*` when you need Workers integration tests.

---

## GitHub Actions: Selective Test Job

```yaml
# .github/workflows/test-affected.yml
name: Test Affected Packages

on:
  pull_request:
    branches: [main]

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      has_changes: ${{ steps.diff.outputs.has_changes }}
      filter:      ${{ steps.diff.outputs.filter }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # Required for git diff against origin/main

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Compute affected filter
        id: diff
        run: |
          # Count affected packages (dependents included)
          COUNT=$(pnpm -r --filter "...[origin/${{ github.base_ref }}]..." \
                    ls --depth -1 2>/dev/null | grep -c "^@example project" || true)

          if [[ "${COUNT}" -eq 0 ]]; then
            echo "has_changes=false" >> "$GITHUB_OUTPUT"
          else
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
            echo "filter=...[origin/${{ github.base_ref }}]..." >> "$GITHUB_OUTPUT"
          fi

  test:
    needs: detect
    if: needs.detect.outputs.has_changes == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run affected tests
        run: |
          pnpm -r --filter "${{ needs.detect.outputs.filter }}" \
            run test --passWithNoTests
```

---

## TypeScript: Computing the Affected Set Programmatically

When CI filtering alone is insufficient (e.g., for custom reporting), compute the set in a script:

```typescript
// scripts/affected-packages.ts
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const BASE_REF = process.argv[2] ?? "origin/main";

function getChangedFiles(base: string): string[] {
  return execSync(`git diff --name-only ${base}...HEAD`)
    .toString()
    .trim()
    .split("\n")
    .filter(Boolean);
}

function getWorkspacePackages(): Array<{ name: string; dir: string }> {
  const raw = execSync("pnpm -r exec pwd --filter '*'")
    .toString()
    .trim()
    .split("\n");
  return raw.map((dir) => {
    const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
    return { name: pkg.name as string, dir };
  });
}

const changedFiles = getChangedFiles(BASE_REF);
const packages = getWorkspacePackages();

const affected = packages.filter(({ dir }) =>
  changedFiles.some((f) => f.startsWith(dir.replace(process.cwd() + "/", "")))
);

console.log(JSON.stringify(affected.map((p) => p.name), null, 2));
```

```bash
pnpm tsx scripts/affected-packages.ts origin/main
```

---

## Vitest Workspace Integration

Vitest's workspace mode pairs with pnpm filtering. Each package has its own `vitest.config.ts`; the root config aggregates:

```typescript
// vitest.workspace.ts (root)
import { defineWorkspace } from "vitest/config";

export default defineWorkspace([
  "packages/*/vitest.config.ts",
  "apps/web/vitest.config.ts",
  // Workers use Miniflare — separate config
  "apps/workers/*/vitest.config.ts",
]);
```

When `pnpm --filter` scopes the `test` script to affected packages, Vitest only loads the configs for those packages — no root workspace restart needed.

---

## Turbo Integration (Optional Layering)

If the repo uses Turborepo for task orchestration, `turbo run test --filter='...[origin/main]...'` offers the same affected-graph behaviour with remote cache:

```jsonc
// turbo.json
{
  "tasks": {
    "test": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "test/**", "vitest.config.ts"],
      "outputs": ["coverage/**"]
    }
  }
}
```

```bash
# CI command — runs tests only for affected packages, pulls cached results for unchanged
pnpm dlx turbo run test --filter="...[origin/main]..."
```

---

## Anti-patterns

- **Using `--filter "*"` in CI** — this runs all tests unconditionally, defeating the purpose of selective filtering and restoring the 18-minute runtime.
- **Shallow clone with `fetch-depth: 1`** — `git diff origin/main...HEAD` needs the merge-base commit; a depth-1 clone cannot find it, causing the filter to match zero packages and silently skip all tests.
- **Filtering only changed packages without dependents** — if `@example project/shared-types` changes and `@example project/ui` depends on it, only testing `shared-types` misses regressions in the consumer. Always use the `...` suffix.
- **Caching `node_modules` without caching pnpm store** — the pnpm content-addressable store is what makes installs fast; cache `~/.pnpm-store` not `node_modules`.

---

## Gotchas

- `pnpm --filter "[origin/main]"` compares against the remote tracking branch, not a local ref. If the runner has not fetched `origin/main`, the filter returns zero matches. Always run `git fetch origin main --depth=1` before the filter step (or use `fetch-depth: 0` on checkout).
- Changes to root-level files (`pnpm-workspace.yaml`, `turbo.json`, `.eslintrc`) should trigger a full test run because they can affect every package. Add a root-change detector step that falls back to `--filter "*"` when workspace-wide files change.
- The `--passWithNoTests` flag is essential — some affected packages may have no test files matching the runner's Vitest glob, and without it the job fails with "No test files found".
- `pnpm -r --filter` ordering respects the dependency graph; packages are tested in topological order unless `--parallel` is passed.

---

## Verification

```bash
# 1. Manually confirm affected packages on a feature branch
git fetch origin main
pnpm -r --filter "...[origin/main]..." list --depth -1

# 2. Dry-run test command without executing
pnpm -r --filter "...[origin/main]..." run test --dry-run

# 3. Confirm fetch-depth is sufficient in CI
git log --oneline origin/main...HEAD | wc -l
```

---

## Related

- `monorepo-affected-builds-2026.md`
- `monorepo-ci-parallelization.md`
- `monorepo-turborepo-remote-cache-ci.md`
- `pnpm-workspace-protocol-version-resolution.md`
- `pnpm-catalog-monorepo-dependency-alignment.md`
- `cloudflare-workers-vitest-miniflare-testing.md`

---

## Sources

- https://pnpm.io/filtering
- https://pnpm.io/workspaces
- https://vitest.dev/guide/workspace
- https://turbo.build/repo/docs/crafting-your-repository/running-tasks#using-filters
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/storing-workflow-data-as-artifacts
