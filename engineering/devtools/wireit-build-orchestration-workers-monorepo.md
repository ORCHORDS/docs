# Wireit Build Orchestration for Cloudflare Workers Monorepos

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
In a large Cloudflare Workers monorepo with shared libraries, plain npm/pnpm scripts run sequentially or require manual topological ordering. Wireit adds dependency graphs, incremental caching, and parallelism to existing `package.json` scripts without adopting a full monorepo build tool like Turborepo or Nx.

## Context
Wireit is a Google-maintained tool that augments npm/pnpm/yarn scripts by reading a `wireit` key in `package.json`. It tracks input/output file fingerprints and re-runs scripts only when inputs change. For Cloudflare Workers projects this means `wrangler build` only fires when source files change, and shared library builds are guaranteed to complete before Worker builds that depend on them. Wireit integrates with GitHub Actions caching via `WIREIT_CACHE=github` without any plugin installation.

## Installation and Root Configuration

Install wireit once at the workspace root:

```bash
pnpm add -Dw wireit
```

Root `package.json` — define the aggregate build target:

```json
{
  "name": "my-workers-monorepo",
  "private": true,
  "scripts": {
    "build": "wireit",
    "test": "wireit",
    "typecheck": "wireit"
  },
  "wireit": {
    "build": {
      "dependencies": [
        "./packages/utils:build",
        "./packages/auth:build",
        "./apps/api-worker:build",
        "./apps/edge-worker:build"
      ]
    },
    "test": {
      "dependencies": [
        "./packages/utils:test",
        "./packages/auth:test",
        "./apps/api-worker:test",
        "./apps/edge-worker:test"
      ]
    },
    "typecheck": {
      "dependencies": [
        "./packages/utils:typecheck",
        "./packages/auth:typecheck",
        "./apps/api-worker:typecheck",
        "./apps/edge-worker:typecheck"
      ]
    }
  }
}
```

## Package-Level Wireit Configuration

Shared utility library `packages/utils/package.json`:

```json
{
  "name": "@repo/utils",
  "scripts": {
    "build": "wireit",
    "typecheck": "wireit",
    "test": "wireit"
  },
  "wireit": {
    "build": {
      "command": "tsup src/index.ts --format esm --dts --out-dir dist",
      "files": ["src/**/*.ts", "tsconfig.json", "tsup.config.ts"],
      "output": ["dist/**"]
    },
    "typecheck": {
      "command": "tsc --noEmit",
      "files": ["src/**/*.ts", "tsconfig.json"],
      "output": []
    },
    "test": {
      "command": "vitest run",
      "dependencies": ["build"],
      "files": ["src/**/*.ts", "test/**/*.ts", "vitest.config.ts"],
      "output": ["coverage/**"]
    }
  }
}
```

Cloudflare Worker app `apps/api-worker/package.json`:

```json
{
  "name": "@repo/api-worker",
  "scripts": {
    "build": "wireit",
    "typecheck": "wireit",
    "test": "wireit",
    "deploy": "wireit"
  },
  "wireit": {
    "build": {
      "command": "wrangler deploy --dry-run --outdir dist",
      "dependencies": [
        "../packages/utils:build",
        "../packages/auth:build"
      ],
      "files": [
        "src/**/*.ts",
        "wrangler.toml",
        "tsconfig.json"
      ],
      "output": ["dist/**"]
    },
    "typecheck": {
      "command": "tsc --noEmit",
      "dependencies": [
        "../packages/utils:typecheck",
        "../packages/auth:typecheck"
      ],
      "files": ["src/**/*.ts", "tsconfig.json"],
      "output": []
    },
    "test": {
      "command": "vitest run --pool=workers",
      "dependencies": [
        "build",
        "../packages/utils:build"
      ],
      "files": [
        "src/**/*.ts",
        "test/**/*.ts",
        "vitest.config.ts"
      ],
      "output": ["coverage/**"]
    },
    "deploy": {
      "command": "wrangler deploy",
      "dependencies": ["build", "test"],
      "files": [],
      "output": []
    }
  }
}
```

## GitHub Actions Integration with Cache

Wireit supports GitHub Actions cache natively via the `WIREIT_CACHE=github` environment variable. Inputs are hashed and cache keys are stored under the `wireit` prefix.

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: write  # required for wireit GitHub cache

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

      - name: Build all packages
        run: pnpm build
        env:
          WIREIT_CACHE: github

      - name: Run all tests
        run: pnpm test
        env:
          WIREIT_CACHE: github

      - name: Typecheck
        run: pnpm typecheck
        env:
          WIREIT_CACHE: github
```

## Parallelism Control and Output Cleaning

By default wireit runs as many scripts in parallel as CPU count allows. Constrain parallelism with `WIREIT_PARALLELISM` or mark scripts as `"service": true` for persistent processes.

```json
{
  "wireit": {
    "dev": {
      "command": "wrangler dev",
      "service": true,
      "dependencies": ["../packages/utils:build"]
    },
    "build": {
      "command": "tsup src/index.ts --format esm --dts",
      "files": ["src/**/*.ts"],
      "output": ["dist/**"],
      "clean": "if-file-deleted"
    }
  }
}
```

The `"clean": "if-file-deleted"` option removes stale output files when a source file is deleted. Use `"clean": true` to always wipe outputs before running (safer but slower).

Run with limited parallelism:

```bash
WIREIT_PARALLELISM=4 pnpm build
```

## Watch Mode for Local Development

Wireit watch mode re-runs scripts when inputs change, respecting the dependency graph:

```bash
# Watch the utils library and rebuild dependents automatically
pnpm --filter @repo/utils run build --watch
# wireit detects --watch and enables watch mode for that script + dependents
```

Or use the wireit watch flag directly:

```bash
cd packages/utils && npx wireit watch build
```

## Anti-patterns

- **Omitting `output` arrays** — Wireit cannot cache a script whose outputs are not declared; it silently re-runs every time, defeating the point.
- **Using `WIREIT_CACHE=github` without `actions: write` permission** — The cache API requires write access; missing it causes silent cache misses with no error in older wireit versions.
- **Declaring `"service": true` on build scripts** — Service mode keeps the process alive; use it only for dev servers, not one-shot builds.
- **Mixing wireit and turborepo in the same monorepo** — Both intercept script execution; they conflict and produce duplicate cache writes.
- **Not setting `"files": []` on scripts with no meaningful inputs** (e.g., `wrangler deploy`) — Without an explicit `files` declaration, wireit treats all repository files as inputs and invalidates on every change.

## Gotchas

- Wireit requires Node 18+; it does not run in Bun or Deno natively.
- `WIREIT_CACHE=github` only works inside GitHub Actions runners — it reads `ACTIONS_CACHE_URL` and `ACTIONS_RUNTIME_TOKEN` from the environment.
- Scripts that write to the same output directory from two packages will cause cache collisions; always use distinct `output` paths.
- Wireit watch mode does not restart service scripts that exit — use a process manager or `--restart-on-failure` for long-running dev servers.
- The `clean` option removes files matching the `output` glob patterns, which can delete hand-placed assets if globs are too broad.

## Verification

```bash
# First run builds everything
pnpm build

# Second run should skip all scripts (cache hit)
pnpm build
# Expected: "Skipped (fresh)" for all scripts

# Touch a source file and confirm only affected packages rebuild
touch packages/utils/src/index.ts
pnpm build
# Expected: utils builds, auth skips, api-worker and edge-worker rebuild

# Confirm GitHub Actions cache is written
# Check Actions tab > Caches for keys prefixed with "wireit:"
```

## Related
- `turborepo-cloudflare-workers-pipeline.md`
- `nx-monorepo-setup.md`
- `pnpm-workspace-setup.md`
- `wrangler-config-validation-ci.md`
- `tsup-workers-library-publishing.md`

## Sources
- https://github.com/google/wireit
- https://github.com/google/wireit/blob/main/README.md#github-actions-caching
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
