# Enforcing Package Boundary Constraints in a Cloudflare Workers Monorepo

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers monorepo has grown to dozens of packages and developers are importing internal utilities directly across workers, bypassing the intended shared-library layer. This creates accidental tight coupling, breaks `wrangler` bundle isolation, and causes CI to rebuild all workers when a single utility changes.

## Context

Package boundaries define which packages may import from which others. In a Workers monorepo the typical layering is: `workers/*` (edge runtime code) may import from `packages/shared-*` (shared utilities) but never from each other, and `packages/shared-*` must not import from `workers/*`. Enforcing this at lint time — before CI even runs wrangler — catches violations early and keeps the module graph clean for affected-build tools like Turborepo. The primary tools are `eslint-plugin-boundaries` for TypeScript import enforcement and a Turborepo `pipeline` task graph that mirrors the allowed dependency direction.

## Defining Boundary Rules with eslint-plugin-boundaries

Install the plugin and configure element types that map to directory patterns:

```bash
pnpm add -D eslint-plugin-boundaries -w
```

```typescript
// eslint.config.mjs (root, flat config)
import boundaries from "eslint-plugin-boundaries";

export default [
  {
    plugins: { boundaries },
    settings: {
      "boundaries/elements": [
        { type: "worker", pattern: "workers/*", capture: ["workerName"] },
        { type: "shared", pattern: "packages/shared-*", capture: ["libName"] },
        { type: "tooling", pattern: "packages/tooling-*", capture: ["toolName"] },
      ],
      "boundaries/ignore": ["**/*.test.ts", "**/*.spec.ts"],
    },
    rules: {
      // Workers may import from shared libs and tooling only
      "boundaries/element-types": [
        "error",
        {
          default: "disallow",
          rules: [
            { from: "worker", allow: ["shared", "tooling"] },
            { from: "shared", allow: ["shared"] },
            { from: "tooling", allow: ["shared", "tooling"] },
          ],
        },
      ],
      // Workers must not import from sibling workers
      "boundaries/no-private": ["error"],
    },
  },
];
```

Run boundary checks in isolation so they produce a fast, targeted failure:

```bash
pnpm eslint --rule '{"boundaries/element-types": "error"}' 'workers/**/*.ts' 'packages/**/*.ts'
```

## Validating the Wrangler Module Graph

Wrangler resolves Worker entry points with esbuild. Use `wrangler deploy --dry-run --outdir dist-check` to produce a bundle without uploading, then inspect the dependency graph for cross-worker imports:

```bash
#!/usr/bin/env bash
# scripts/check-worker-boundaries.sh
set -euo pipefail

VIOLATIONS=0
for worker_dir in workers/*/; do
  worker_name=$(basename "$worker_dir")
  echo "Checking bundle for $worker_name..."

  # Build to a temporary directory
  tmpdir=$(mktemp -d)
  pnpm wrangler deploy \
    --config "$worker_dir/wrangler.toml" \
    --dry-run \
    --outdir "$tmpdir" 2>/dev/null

  # Scan the bundle metafile for sibling worker paths
  if grep -rE '"workers/[^/]+/' "$tmpdir/"*.js | \
       grep -v "workers/${worker_name}/" > /dev/null 2>&1; then
    echo "VIOLATION: $worker_name imports from a sibling worker"
    VIOLATIONS=$((VIOLATIONS + 1))
  fi
  rm -rf "$tmpdir"
done

if [[ $VIOLATIONS -gt 0 ]]; then
  echo "Found $VIOLATIONS boundary violation(s). Failing build."
  exit 1
fi
echo "All worker boundaries are clean."
```

```yaml
# .github/workflows/boundary-check.yml
name: Package Boundary Enforcement
on:
  pull_request:
    paths:
      - 'workers/**'
      - 'packages/**'

jobs:
  boundaries:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - run: pnpm install --frozen-lockfile
      - name: ESLint boundary rules
        run: pnpm eslint 'workers/**/*.ts' 'packages/**/*.ts'
      - name: Wrangler bundle boundary check
        run: bash scripts/check-worker-boundaries.sh
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## TypeScript Path Aliases Aligned with Boundary Layers

Reinforce boundaries at the TypeScript compiler level using `paths` aliases that make cross-worker imports visually obvious (and easily greppable):

```json
// tsconfig.base.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@shared/*": ["packages/shared-*/src/index.ts"],
      "@tooling/*": ["packages/tooling-*/src/index.ts"]
    }
  }
}
```

Workers reference shared code through the alias, never via relative `../../` paths that could escape the package boundary:

```typescript
// workers/api/src/handler.ts — CORRECT
import { rateLimiter } from "@shared/rate-limiter";
import { buildSchema } from "@tooling/schema-builder";

// workers/api/src/handler.ts — WRONG (cross-worker import, caught by ESLint)
// import { authMiddleware } from "../../workers/auth/src/middleware";
```

Add a `tsconfig` `include` restriction per worker so the TypeScript project scope never accidentally includes sibling workers:

```json
// workers/api/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "include": ["src/**/*.ts"],
  "exclude": ["../../workers/!(api)/**"]
}
```

## Anti-patterns

- Using relative `../../../` imports across worker directories — they bypass both ESLint boundary rules and TypeScript path alias enforcement.
- Setting `eslint-plugin-boundaries` to `"warn"` instead of `"error"` in CI — warnings do not fail the build and are ignored within weeks.
- Treating `packages/shared-utils` as a catch-all dumping ground — this re-creates the coupling problem inside the shared layer itself; split shared code into focused single-responsibility packages.
- Skipping the `wrangler --dry-run` check and relying only on ESLint — dynamic imports and `require()` calls can evade static import analysis.

## Gotchas

- `eslint-plugin-boundaries` uses glob patterns for element detection; if your directory names don't match the pattern exactly (e.g. `workers/workers-api` vs `workers/api`) the element type is undetected and no rules fire — test patterns with `--debug`.
- Turborepo's `pipeline` `dependsOn` field enforces build-time ordering but does NOT enforce import boundaries at the source level; you still need ESLint for that.
- `wrangler` bundles all `node_modules` transitive deps into the Worker; if a shared package accidentally exports a Node.js-only polyfill it will be included in every worker that imports the shared package even if the export is unused — use `sideEffects: false` in `package.json` to enable tree-shaking.

## Verification

```bash
# Confirm ESLint boundary rules are loaded and active
pnpm eslint --print-config workers/api/src/handler.ts | \
  python3 -c "import sys,json; cfg=json.load(sys.stdin); \
  print([r for r in cfg['rules'] if 'boundaries' in r])"

# Attempt a known violation — should exit non-zero
echo "import x from '../../workers/auth/src/index';" > /tmp/test-violation.ts
pnpm eslint --rulesdir /tmp /tmp/test-violation.ts || echo "Boundary rule fired correctly"

# Run the full boundary check script
bash scripts/check-worker-boundaries.sh
```

## Related

- `worktree/monorepo-workspace-cloudflare-workers.md`
- `worktree/monorepo-affected-builds-2026.md`
- `worktree/monorepo-pnpm-turborepo-2026.md`
- `worktree/git-hooks-pre-commit-frameworks.md`

## Sources

- https://www.npmjs.com/package/eslint-plugin-boundaries
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://turbo.build/repo/docs/crafting-your-repository/structuring-a-repository
