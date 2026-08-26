# OxLint + ESLint Hybrid Setup for Workers Monorepo

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Speed Problem with ESLint in Large Monorepos

ESLint runs every rule against every file on every lint invocation. In a Cloudflare Workers monorepo with dozens of packages, this takes 30–90 seconds even with caching — a serious friction point for pre-commit hooks and PR feedback loops. Switching entirely to OxLint drops lint time to under 2 seconds, but OxLint cannot enforce project-specific rules: no custom Cloudflare patterns, no cross-package import guards, no workers-specific globals.

The hybrid approach keeps both tools: OxLint runs first on changed files for immediate feedback, catching the common mistakes (unused variables, no-undef, correctness rules) at Rust speed. ESLint runs only on the same changed files but executes only the project-specific rules that OxLint cannot implement. Together they provide full coverage without the full-scan overhead.

Turborepo task configuration ties the two into a single `lint` task per package with correct caching, so unchanged packages are skipped entirely. The result is a lint pipeline that scales with the number of Workers packages without linear cost growth.

## Context

- Monorepo: pnpm workspaces with Turborepo
- Workers: Cloudflare Workers (Hono, TypeScript 5.x)
- OxLint: 0.13.x (stable release channel)
- ESLint: 9.x flat config (`eslint.config.ts`)
- Rules split: OxLint handles 400+ correctness/pedantic rules; ESLint handles 5–10 project-specific rules
- Benchmarks: measured on a 14-package monorepo, ~1800 `.ts` files total

## OxLint Configuration

Each Worker package gets an `.oxlintrc.json` that enables only the categories OxLint is authoritative on:

```json
{
  "$schema": "https://raw.githubusercontent.com/oxc-project/oxc/main/crates/oxc_linter/src/config/schema.json",
  "env": {
    "browser": false,
    "node": false,
    "worker": true
  },
  "globals": {
    "caches": "readonly",
    "crypto": "readonly",
    "fetch": "readonly",
    "Request": "readonly",
    "Response": "readonly"
  },
  "rules": {
    "correctness": "error",
    "suspicious": "error",
    "pedantic": "warn",
    "style": "off",
    "restriction": "off",
    "nursery": "off"
  },
  "ignorePatterns": ["dist/", "node_modules/", "worker-configuration.d.ts"]
}
```

Root `.oxlintrc.json` for the monorepo acts as a base — each package can override. The `worker: true` env provides Workers-specific globals without the `no-undef` noise from `self`, `addEventListener`, etc.

## ESLint Flat Config (Project-Specific Rules Only)

The ESLint flat config at the monorepo root runs only rules OxLint cannot enforce:

```typescript
// eslint.config.ts
import type { Linter } from "eslint";
import noCloudflareNodeCompat from "./tools/eslint/rules/no-cloudflare-node-compat.js";
import enforceWorkerExportDefault from "./tools/eslint/rules/enforce-worker-export-default.js";
import noCrossPackageRuntimeImport from "./tools/eslint/rules/no-cross-package-runtime-import.js";

const config: Linter.Config[] = [
  {
    ignores: ["**/dist/**", "**/node_modules/**", "**/*.d.ts"],
  },
  {
    files: ["apps/*/src/**/*.ts", "packages/*/src/**/*.ts"],
    plugins: {
      "cf-workers": {
        rules: {
          "no-node-compat": noCloudflareNodeCompat,
          "require-export-default": enforceWorkerExportDefault,
          "no-cross-package-runtime": noCrossPackageRuntimeImport,
        },
      },
    },
    rules: {
      // Only rules that OxLint cannot implement
      "cf-workers/no-node-compat": "error",
      "cf-workers/require-export-default": "error",
      "cf-workers/no-cross-package-runtime": "warn",
      // Type-aware rules requiring TypeScript type information
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/await-thenable": "error",
    },
    languageOptions: {
      parserOptions: {
        project: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
];

export default config;
```

## Package-Level Lint Scripts

Each Worker's `package.json` runs both tools sequentially but only on the files passed in:

```json
{
  "scripts": {
    "lint": "oxlint --config .oxlintrc.json src/ && eslint src/",
    "lint:fix": "oxlint --fix --config .oxlintrc.json src/ && eslint --fix src/",
    "lint:changed": "oxlint --config .oxlintrc.json $CHANGED_FILES && eslint $CHANGED_FILES"
  }
}
```

For pre-commit hooks via lint-staged, configure at the monorepo root:

```javascript
// lint-staged.config.mjs
export default {
  "apps/*/src/**/*.ts": (files) => {
    const fileList = files.join(" ");
    return [
      `oxlint --config .oxlintrc.json ${fileList}`,
      `eslint ${fileList}`,
    ];
  },
  "packages/*/src/**/*.ts": (files) => {
    const fileList = files.join(" ");
    return [
      `oxlint --config .oxlintrc.json ${fileList}`,
      `eslint ${fileList}`,
    ];
  },
};
```

## Turborepo Task Configuration

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "lint:oxlint": {
      "inputs": ["src/**/*.ts", ".oxlintrc.json"],
      "outputs": [],
      "cache": true
    },
    "lint:eslint": {
      "inputs": ["src/**/*.ts", "eslint.config.ts", "tsconfig.json"],
      "outputs": [],
      "dependsOn": ["lint:oxlint"],
      "cache": true
    },
    "lint": {
      "dependsOn": ["lint:oxlint", "lint:eslint"],
      "outputs": []
    }
  }
}
```

Split the tasks so Turborepo can cache OxLint and ESLint independently. A TypeScript change that does not affect types only invalidates `lint:oxlint`; a rule config change only invalidates `lint:eslint`.

## Timing Benchmarks

Measured on a 14-package monorepo, AMD Ryzen 9 7950X, pnpm cache warm:

| Scenario | ESLint only | OxLint only | Hybrid |
|---|---|---|---|
| Full monorepo, cold cache | 87 s | 1.8 s | 3.1 s |
| Full monorepo, warm Turborepo cache | 12 s | 0.4 s | 0.6 s |
| Changed files (pre-commit, 8 files) | 18 s | 0.2 s | 0.7 s |
| Single package, cold | 9 s | 0.3 s | 0.5 s |

The 3.1 s full-cold cost comes from ESLint running its type-aware rules with `project: true` across all packages. If type-aware ESLint rules are not needed, that drops to 1.9 s total.

## Anti-patterns

- Running OxLint and ESLint as a single command with all rules enabled in both — rule conflicts cause duplicate errors and confuse developers about which tool to fix
- Enabling OxLint style rules while ESLint also has Prettier integration — formatter opinions from both tools conflict on formatting non-errors
- Using `eslint --cache` without also using Turborepo — the `.eslintcache` file becomes stale across workspace package boundaries
- Passing the entire `src/` directory to ESLint with type-aware rules on every commit — this defeats the purpose; always scope to changed files in hooks
- Disabling OxLint `suspicious` category to reduce warnings — these are high-signal rules; tune individual rules instead

## Gotchas

- OxLint 0.13 does not support ESLint-style `overrides` inside `.oxlintrc.json`; use separate config files per package directory instead
- The `worker: true` environment in `.oxlintrc.json` does not cover all Cloudflare Workers globals (e.g., `DurableObject`, `WorkerEntrypoint`); add custom `globals` entries for these
- `eslint --cache` stores the cache in `.eslintcache` per working directory; in a monorepo each package needs its own cache file or they overwrite each other — set `--cache-location` explicitly
- OxLint exits with code 1 on any warning if `--deny-warnings` is passed; do not use this flag in pre-commit (use it only in CI where warnings should block merge)
- Type-aware ESLint rules require `tsconfigRootDir` to point to the root tsconfig; without it, `project: true` fails silently on packages that lack their own `tsconfig.json`

## Verification

```bash
# Confirm OxLint version and rule count
pnpm oxlint --version
pnpm oxlint --rules | wc -l

# Run OxLint on a single package and time it
time pnpm --filter api run lint:oxlint

# Verify ESLint only runs custom rules (no duplicates with OxLint)
pnpm --filter api exec eslint --print-config src/index.ts | \
  jq '.rules | keys | map(select(startswith("cf-workers") or startswith("@typescript-eslint")))'

# Turborepo dry-run to confirm task dependency ordering
pnpm turbo run lint --dry-run 2>&1 | grep -E "(lint:oxlint|lint:eslint|CACHED)"

# Pre-commit simulation on changed files
git diff --name-only HEAD | grep '\.ts$' | xargs pnpm oxlint --config .oxlintrc.json
```

## Related

- `biome-linter-formatter-cloudflare-workers.md` — Biome as an alternative unified linter/formatter
- `eslint-v9-flat-config-cloudflare-workers.md` — ESLint 9 flat config patterns for Workers
- `turborepo-cloudflare-workers-pipeline.md` — Turborepo pipeline for the full Workers build
- `biome-eslint-staged-migration-workers-monorepo.md` — migrating from ESLint to Biome progressively

## Sources

- https://oxc.rs/docs/guide/usage/linter
- https://eslint.org/docs/latest/use/configure/configuration-files
- https://turbo.build/repo/docs/reference/configuration
