# PR Readiness Checklist for Cloudflare Workers + Next.js Projects

Date:   2026-08-22
Author: example.com
Status: stable

## Symptom

PRs merge with TypeScript errors that were never caught, Miniflare tests
were skipped because they "take too long", a D1 migration was committed
without a rollback path, and the bundle breached the 1 MB Workers limit
without anyone noticing. The deploy succeeds but production breaks within
minutes.

## Context

A Cloudflare Workers + Next.js monorepo has at least two distinct runtime
targets (the Workers V8 isolate and the Node.js/edge Next.js runtime) and
a persistent data layer (D1). Each target imposes its own constraints:
Workers have a 1 MB compressed bundle limit, no Node.js built-ins by
default, and CPU time caps. Next.js Pages add Playwright-testable UI.

This checklist is designed to be enforced in CI (PR workflow) and can also
be run locally before opening a PR. Items are ordered from fastest to
slowest so developers get signal early.

---

## 1. Checklist Overview

```
┌────┬──────────────────────────────────────┬────────────┬─────────┐
│  # │ Check                                │ Tool       │ Target  │
├────┼──────────────────────────────────────┼────────────┼─────────┤
│  1 │ TypeScript type check                │ tsc        │ both    │
│  2 │ ESLint (with Workers plugin)         │ eslint     │ both    │
│  3 │ Unit tests                           │ vitest     │ both    │
│  4 │ Miniflare integration tests          │ vitest+mf  │ worker  │
│  5 │ Bundle size check                    │ wrangler   │ worker  │
│  6 │ D1 migration dry-run                 │ wrangler   │ worker  │
│  7 │ Playwright smoke test (preview URL)  │ playwright │ pages   │
└────┴──────────────────────────────────────┴────────────┴─────────┘
```

---

## 2. Type Check

Run `tsc --noEmit` for every TypeScript package. Configure each package's
`tsconfig.json` to `"strict": true` and reference the shared types package:

```jsonc
// worker/tsconfig.json
{
  "extends": "../packages/types/tsconfig.json",
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "noEmit": true,
    "strict": true
  },
  "include": ["src/**/*.ts"]
}
```

```bash
# Local: check all packages at once via Turborepo
pnpm exec turbo run typecheck

# CI: fail fast on the first error
pnpm --filter worker exec tsc --noEmit
pnpm --filter frontend exec tsc --noEmit
```

Common Worker-specific type errors to watch for:
- Using `Buffer` (Node.js) instead of `Uint8Array` (Workers runtime).
- Importing Node built-ins without the `nodejs_compat` compatibility flag.
- Missing env bindings in the `Env` interface that are defined in
  `wrangler.toml`.

---

## 3. ESLint with Workers Plugin

Install the Cloudflare Workers ESLint plugin to catch runtime-incompatible
patterns before they reach production:

```bash
pnpm add -D eslint-plugin-no-unsupported-browser-features \
             @cloudflare/eslint-plugin-next-on-pages
```

`eslint.config.mjs` (flat config):

```js
import cfNextOnPages from '@cloudflare/eslint-plugin-next-on-pages';

export default [
  cfNextOnPages.configs.recommended,
  {
    rules: {
      'no-restricted-globals': [
        'error',
        { name: 'process', message: 'Use env bindings, not process.env' },
        { name: 'Buffer',  message: 'Use Uint8Array in Workers runtime'  },
      ],
    },
  },
];
```

---

## 4. Unit Tests with Vitest

Unit tests should run without any Cloudflare runtime. Mock bindings where
needed:

```ts
// worker/src/__tests__/handler.test.ts
import { describe, it, expect, vi } from 'vitest';
import { handleRequest } from '../handler';

const env = {
  DB: { prepare: vi.fn() },
  KV: { get: vi.fn(), put: vi.fn() },
  RELEASE_VERSION: '1.0.0',
} satisfies Partial<Env>;

describe('handleRequest', () => {
  it('returns 200 for /health', async () => {
    const req = new Request('https://example.com/health');
    const res = await handleRequest(req, env as Env, {} as ExecutionContext);
    expect(res.status).toBe(200);
  });
});
```

```bash
pnpm --filter worker exec vitest run --reporter=verbose
```

---

## 5. Miniflare Integration Tests

Miniflare emulates the Workers runtime locally, including D1, KV, R2, and
Durable Objects. Use `@cloudflare/vitest-pool-workers` for seamless
Vitest integration:

```bash
pnpm add -D @cloudflare/vitest-pool-workers
```

`vitest.integration.config.ts`:

```ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    include: ['src/**/*.integration.test.ts'],
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          d1Databases: { DB: 'test-db' },
          kvNamespaces:  { KV: 'test-kv' },
        },
      },
    },
  },
});
```

Integration test:

```ts
// worker/src/__tests__/users.integration.test.ts
import { SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('GET /users/:id', () => {
  it('returns 404 for unknown user', async () => {
    const res = await SELF.fetch('https://example.com/users/99999');
    expect(res.status).toBe(404);
  });
});
```

---

## 6. Bundle Size Check

Cloudflare Workers enforces a **1 MB compressed** bundle limit. Check this
before every PR merge to catch accidental heavy dependencies:

```bash
# Dry-run deploy prints bundle size without deploying.
pnpm exec wrangler deploy --dry-run --outdir dist/

# Parse the size from stdout (fails CI if > 800 KB uncompressed):
BUNDLE_SIZE=$(cat dist/*.js | wc -c)
LIMIT=$((800 * 1024))
if [ "$BUNDLE_SIZE" -gt "$LIMIT" ]; then
  echo "Bundle too large: ${BUNDLE_SIZE} bytes (limit ${LIMIT})"
  exit 1
fi
```

Use `wrangler deploy --dry-run` output to inspect which modules are
largest. Common culprits: `date-fns` (use `temporal`), `lodash` (use
native), large JSON files imported as constants.

---

## 7. D1 Migration Dry-Run

Every PR that adds a `migrations/` file must pass a local migration
dry-run before merging. This catches SQL syntax errors and missing indexes.

```bash
# Creates a fresh local SQLite DB and runs all pending migrations.
pnpm exec wrangler d1 migrations apply LOCAL_DB \
  --local \
  --persist-to .wrangler/state/v3/d1

# List applied migrations to confirm the new one appears:
pnpm exec wrangler d1 migrations list LOCAL_DB --local
```

PRs that modify existing migration files (rather than adding new ones)
must be flagged for manual review. Wrangler migration files are immutable
once applied to a remote database.

D1 migration naming convention:

```
migrations/
  0001_create_users.sql
  0002_add_sessions.sql
  0003_index_sessions_user_id.sql   ← always add index in same migration
```

---

## 8. Playwright Smoke Test (Preview URL)

For PRs, Cloudflare Pages generates a preview URL automatically. Run
a fast Playwright smoke suite against it rather than against production.

`playwright.config.ts` (smoke project only):

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  projects: [
    {
      name: 'smoke',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.PREVIEW_URL ?? 'http://localhost:3000',
      },
      testMatch: 'tests/smoke/**/*.spec.ts',
      retries: 2,
    },
  ],
  timeout: 20_000,
});
```

Resolve the preview URL from the Cloudflare Pages deploy response:

```bash
PREVIEW_URL=$(pnpm exec wrangler pages deploy .next/standalone \
  --project-name=my-project \
  --branch="${GITHUB_HEAD_REF}" \
  2>&1 | grep -oP 'https://[a-z0-9-]+\.my-project\.pages\.dev')

PREVIEW_URL="$PREVIEW_URL" pnpm exec playwright test --project=smoke
```

---

## Anti-patterns

- Running `tsc --build` instead of `tsc --noEmit` in CI. The build flag
  emits output and may succeed even when there are type errors under strict
  mode if project references are misconfigured.
- Skipping Miniflare tests on the grounds that "they're slow". They are
  the only gate that catches Workers-runtime-specific failures.
- Writing migration SQL that assumes a transaction around schema changes.
  D1 does not support transactional DDL; `ALTER TABLE` cannot be rolled
  back.
- Checking bundle size only at deploy time. By then the PR is already
  merged. Size checks belong in the PR workflow.
- Running Playwright against `localhost` in CI instead of the real preview
  URL. Next.js dev server behaviour diverges from the Workers/Pages runtime.

---

## Gotchas

- `@cloudflare/workers-types` and `typescript` must be compatible. Workers
  types newer than TS 5.0 require strict mode enabled.
- Miniflare's D1 emulation runs SQLite locally. Some SQLite-specific
  pragmas that D1 blocks (e.g. `PRAGMA foreign_keys`) will succeed locally
  but fail in production.
- Playwright's `--retries` flag retries on failure but does not retry on
  network timeout at the `baseURL`. Set `expect.timeout` and
  `navigationTimeout` explicitly for preview URLs that may be cold.
- `wrangler d1 migrations apply --local` creates the DB file in the current
  working directory unless `--persist-to` is set. Running from different
  directories creates duplicate state files.

---

## Verification

```bash
# Run the full local checklist in one command via Turborepo:
pnpm exec turbo run typecheck lint test test:integration bundle-check

# Confirm D1 local state is clean before the dry-run:
ls .wrangler/state/v3/d1/

# List Playwright test results from the last run:
npx playwright show-report
```

---

## Related

- documentation/docs/policies/worktree/github-actions-wrangler-deploy-pipeline.md
- documentation/docs/policies/worktree/conventional-commits-automated-changelog.md
- documentation/docs/policies/worktree/monorepo-workspace-cloudflare-workers.md
- documentation/docs/policies/worktree/git-branching-cloudflare-preview-environments.md

---

## Source URLs

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://playwright.dev/docs/test-configuration
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
