# Staged Migration from ESLint to Biome in a Cloudflare Workers Monorepo

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers monorepo running ESLint v9 flat config takes 40+ seconds to lint on CI because ESLint spawns per-package processes and Workers-specific plugins (`eslint-plugin-cloudflare`) do not parallelise cleanly under turborepo. Migrating to Biome in a single PR is too risky — thousands of auto-fixable changes land at once and conflict with in-flight feature branches. A staged migration runs both tools in parallel while gradually deprecating ESLint rules already covered by Biome.

## Context

The example project platform monorepo (`apps/`, `packages/`, `workers/`) uses pnpm workspaces and turborepo for task scheduling. ESLint handles Workers-specific rules (no `process.env` access, no Node.js builtins without the `nodejs_compat` flag) that Biome does not yet model. Biome handles formatting (replacing Prettier) and a large subset of stylistic and correctness rules faster than ESLint can. During the transition period both tools run in CI; ESLint is progressively trimmed to only the rules Biome cannot cover, until it can be removed entirely.

## Phase 1 — Add Biome Alongside ESLint

Install Biome at the workspace root. Pin the exact version so all contributors use the same binary from the content-addressable store.

```bash
pnpm add -Dw @biomejs/biome@1.9.4
pnpm exec biome init
```

The generated `biome.json` at the workspace root. Scope Biome to formatting and the rules known-safe for Workers code; leave everything else to ESLint until Phase 2.

```jsonc
// biome.json  (workspace root)
{
  "$schema": "https://biomejs.dev/schemas/1.9.4/schema.json",
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true,
    "defaultBranch": "main"
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100
  },
  "organizeImports": {
    "enabled": true
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": false,
      "correctness": {
        "noUnusedVariables": "error",
        "noUnusedImports": "error",
        "useExhaustiveDependencies": "warn"
      },
      "suspicious": {
        "noExplicitAny": "warn",
        "noConsoleLog": "off"
      },
      "style": {
        "noNonNullAssertion": "warn",
        "useConst": "error"
      },
      "complexity": {
        "noForEach": "off"
      }
    }
  },
  "javascript": {
    "formatter": {
      "quoteStyle": "double",
      "semicolons": "always",
      "trailingCommas": "all"
    },
    "globals": ["caches", "CloudflareDevProxy"]
  },
  "files": {
    "ignore": [
      "node_modules",
      ".wrangler",
      "dist",
      "*.gen.ts",
      "worker-configuration.d.ts"
    ]
  }
}
```

## Phase 2 — Parallel Lint Scripts in pnpm

Add Biome scripts to the root `package.json` without removing ESLint scripts yet. CI runs both; local developers can run either.

```jsonc
// package.json (workspace root, scripts section)
{
  "scripts": {
    "lint": "pnpm lint:eslint && pnpm lint:biome",
    "lint:eslint": "eslint . --max-warnings 0",
    "lint:biome": "biome check --reporter=github .",
    "lint:biome:fix": "biome check --write .",
    "format": "biome format --write .",
    "format:check": "biome format --diagnostic-name=format .",
    "typecheck": "tsc -b --noEmit"
  }
}
```

For turborepo, add a `lint:biome` task that can cache independently of ESLint:

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "lint:eslint": {
      "inputs": ["**/*.ts", "**/*.tsx", "eslint.config.ts", ".eslintignore"],
      "cache": true
    },
    "lint:biome": {
      "inputs": ["**/*.ts", "**/*.tsx", "**/*.json", "biome.json"],
      "cache": true
    },
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".wrangler/**"]
    }
  }
}
```

## Phase 3 — lint-staged Integration

Replace the Prettier + ESLint lint-staged chain with Biome for formatting and style, keeping ESLint only for Workers-specific rules.

Install lint-staged at the workspace root if not already present:

```bash
pnpm add -Dw lint-staged
```

```javascript
// lint-staged.config.mjs
export default {
  // Biome handles formatting + safe lint fixes on staged TS/JS/JSON
  "*.{ts,tsx,js,mjs,cjs,json,jsonc}": [
    "biome check --write --no-errors-on-unmatched --files-ignore-unknown=true",
  ],
  // ESLint runs only for Workers-specific rules not yet in Biome
  "workers/**/*.{ts,tsx}": [
    "eslint --max-warnings 0 --rule 'cloudflare-workers/no-nodejs-compat-v2:error'",
  ],
};
```

Wire it to the `pre-commit` hook via Husky:

```bash
pnpm exec husky init
echo "pnpm exec lint-staged" > .husky/pre-commit
chmod +x .husky/pre-commit
```

## Phase 4 — CI Enforcement During Transition

GitHub Actions workflow that runs both linters with clear failure attribution:

```yaml
# .github/workflows/lint.yml
name: Lint

on:
  pull_request:
  push:
    branches: [main]

jobs:
  biome:
    name: Biome
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Biome check
        run: pnpm exec biome ci --reporter=github .

  eslint:
    name: ESLint (Workers rules)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Generate wrangler types
        run: pnpm --filter './workers/*' exec wrangler types
      - name: ESLint
        run: pnpm lint:eslint
```

## Phase 5 — Tracking Deprecated ESLint Rules

As each ESLint rule is confirmed covered by Biome, annotate it with a comment and set it to `"off"` so the deprecation is tracked in code review rather than silently dropped:

```typescript
// eslint.config.ts
import { defineConfig } from "eslint/config";
import cloudflareWorkers from "eslint-plugin-cloudflare-workers";

export default defineConfig([
  {
    files: ["workers/**/*.ts"],
    plugins: { "cloudflare-workers": cloudflareWorkers },
    rules: {
      // DEPRECATED: covered by biome correctness/noUnusedVariables — remove after Phase 6
      "no-unused-vars": "off",
      // DEPRECATED: covered by biome style/useConst — remove after Phase 6
      "prefer-const": "off",

      // RETAINED: no Biome equivalent yet
      "cloudflare-workers/no-nodejs-compat-v2": "error",
      "cloudflare-workers/no-process-env": "error",
    },
  },
]);
```

## Anti-patterns

- Running `biome check --write` on the entire monorepo as part of a CI lint step — it modifies files and then the diff check fails; use `biome ci` (read-only, exits non-zero on violations) in CI and `biome check --write` locally.
- Configuring Biome's `organizeImports` and ESLint's `import/order` simultaneously — they produce conflicting orderings on each lint run; disable `import/order` in ESLint as soon as Biome's organizer is enabled.
- Adding per-package `biome.json` overrides that widen `files.ignore` to exclude generated files — generated `.d.ts` and `worker-configuration.d.ts` should be excluded at the root config level so no package silently opts out.

## Gotchas

- Biome's `noConsoleLog` under `suspicious` matches `console.log` but not `console.warn` or `console.error`; Workers code often uses `console.error` for structured error logging — confirm the rule scope before enabling `"error"`.
- `biome ci` respects `.gitignore` via the `vcs.useIgnoreFile` setting but does **not** respect `.eslintignore` — any path excluded only in `.eslintignore` must be added to `biome.json`'s `files.ignore` array.
- When turborepo caches `lint:biome`, the cache key must include `biome.json`; if `biome.json` is at the workspace root and not inside the package directory, add it to the `inputs` glob with a relative `../../biome.json` path or use a global dependency declaration.

## Verification

```bash
# Confirm Biome version matches the pinned version in package.json
pnpm exec biome --version

# Dry-run Biome across the whole monorepo without writing changes
pnpm exec biome check --reporter=summary .

# Count remaining ESLint rules that are NOT set to "off" (target: only Workers-specific rules)
grep -E '"error"|"warn"' eslint.config.ts | grep -v '"off"' | grep -v "DEPRECATED" | wc -l

# Run lint-staged against all staged files (simulation)
pnpm exec lint-staged --diff="HEAD~1..HEAD" --verbose

# Confirm CI workflow parses without errors
gh workflow view lint --yaml | head -20
```

## Related

- `devtools/biome-linter-formatter-cloudflare-workers.md`
- `devtools/eslint-v9-flat-config-cloudflare-workers.md`
- `devtools/eslint-concurrency-performance-governance.md`
- `devtools/turborepo-cloudflare-workers-pipeline.md`
- `devtools/git-hooks-husky.md`

## Sources

- https://biomejs.dev/guides/migrate-eslint-prettier/
- https://biomejs.dev/reference/configuration/
- https://developers.cloudflare.com/workers/platform/compatibility-dates/
- https://turbo.build/repo/docs/reference/configuration#inputs
- https://github.com/lint-staged/lint-staged
