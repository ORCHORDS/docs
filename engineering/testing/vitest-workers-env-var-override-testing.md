# Vitest Workers Environment Variable Override Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker reads secrets and feature-flag values from `env` bindings
at runtime. In unit tests you need to verify branching logic that depends on those
values (e.g. `env.ENVIRONMENT === 'staging'`, `env.FEATURE_NEW_CHECKOUT === 'true'`,
`env.STRIPE_SECRET_KEY`). Without a structured override mechanism each test file
either hard-codes values or leaks state between suites, making the suite brittle
and order-dependent.

---

## Context

Cloudflare Workers receive environment bindings through the `Env` object passed as
the second argument to `fetch()`. The `@cloudflare/vitest-pool-workers` pool
exposes `env` via `SELF` and through the `cloudflare:test` helper. Two distinct
override strategies exist:

| Strategy | Scope | Use-case |
|---|---|---|
| `wrangler.toml` `[vars]` override per test project | Build-time | Stable per-environment values |
| `defineWorkersConfig` `miniflare.bindings` | Config-time | Per-suite overrides |
| Manual `createExecutionContext` + partial `Env` | Test-time | Per-test granular overrides |

This article focuses on the third strategy — per-test granular overrides — because
it gives the finest control with zero test pollution.

---

## Project Layout

```
src/
  worker.ts
  worker.test.ts
wrangler.toml
vitest.config.ts
```

---

## Worker Under Test

```ts
// src/worker.ts
export interface Env {
  ENVIRONMENT: string;
  FEATURE_NEW_CHECKOUT: string;
  STRIPE_SECRET_KEY: string;
  API_TIMEOUT_MS: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!env.STRIPE_SECRET_KEY) {
      return new Response('Missing Stripe key', { status: 500 });
    }

    const timeout = parseInt(env.API_TIMEOUT_MS ?? '5000', 10);

    const body: Record<string, unknown> = {
      environment: env.ENVIRONMENT,
      newCheckout: env.FEATURE_NEW_CHECKOUT === 'true',
      timeout,
    };

    return Response.json(body);
  },
};
```

---

## Vitest Config

```ts
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          // baseline bindings — individual tests may override
          bindings: {
            ENVIRONMENT: 'test',
            FEATURE_NEW_CHECKOUT: 'false',
            STRIPE_SECRET_KEY: 'sk_test_baseline',
            API_TIMEOUT_MS: '3000',
          },
        },
      },
    },
  },
});
```

---

## Test Helper: `withEnv`

Create a small helper that merges overrides onto the baseline `env` and invokes
the worker's `fetch` handler directly, bypassing the HTTP stack entirely.

```ts
// src/test-utils/withEnv.ts
import worker, { type Env } from '../worker';

const BASELINE_ENV: Env = {
  ENVIRONMENT: 'test',
  FEATURE_NEW_CHECKOUT: 'false',
  STRIPE_SECRET_KEY: 'sk_test_baseline',
  API_TIMEOUT_MS: '3000',
};

export async function withEnv(
  overrides: Partial<Env>,
  request: Request = new Request('https://example.com/')
): Promise<Response> {
  const env: Env = { ...BASELINE_ENV, ...overrides };
  const ctx = {
    waitUntil: () => {},
    passThroughOnException: () => {},
  } as unknown as ExecutionContext;
  return worker.fetch(request, env, ctx);
}
```

---

## Test Suite

```ts
// src/worker.test.ts
import { describe, it, expect } from 'vitest';
import { withEnv } from './test-utils/withEnv';

describe('STRIPE_SECRET_KEY guard', () => {
  it('returns 500 when key is missing', async () => {
    const res = await withEnv({ STRIPE_SECRET_KEY: '' });
    expect(res.status).toBe(500);
    expect(await res.text()).toBe('Missing Stripe key');
  });

  it('returns 200 when key is present', async () => {
    const res = await withEnv({ STRIPE_SECRET_KEY: 'sk_test_abc123' });
    expect(res.status).toBe(200);
  });
});

describe('FEATURE_NEW_CHECKOUT flag', () => {
  it('reflects false when flag is "false"', async () => {
    const res = await withEnv({ FEATURE_NEW_CHECKOUT: 'false' });
    const json = await res.json<{ newCheckout: boolean }>();
    expect(json.newCheckout).toBe(false);
  });

  it('reflects true when flag is "true"', async () => {
    const res = await withEnv({ FEATURE_NEW_CHECKOUT: 'true' });
    const json = await res.json<{ newCheckout: boolean }>();
    expect(json.newCheckout).toBe(true);
  });

  it('treats any value other than "true" as false', async () => {
    for (const val of ['1', 'yes', 'TRUE', 'enabled']) {
      const res = await withEnv({ FEATURE_NEW_CHECKOUT: val });
      const json = await res.json<{ newCheckout: boolean }>();
      expect(json.newCheckout, `expected false for "${val}"`).toBe(false);
    }
  });
});

describe('ENVIRONMENT propagation', () => {
  it('surfaces "staging" correctly', async () => {
    const res = await withEnv({ ENVIRONMENT: 'staging' });
    const json = await res.json<{ environment: string }>();
    expect(json.environment).toBe('staging');
  });

  it('surfaces "production" correctly', async () => {
    const res = await withEnv({ ENVIRONMENT: 'production' });
    const json = await res.json<{ environment: string }>();
    expect(json.environment).toBe('production');
  });
});

describe('API_TIMEOUT_MS parsing', () => {
  it('defaults to 3000 when unset (baseline)', async () => {
    const res = await withEnv({});
    const json = await res.json<{ timeout: number }>();
    expect(json.timeout).toBe(3000);
  });

  it('parses a custom numeric string', async () => {
    const res = await withEnv({ API_TIMEOUT_MS: '8000' });
    const json = await res.json<{ timeout: number }>();
    expect(json.timeout).toBe(8000);
  });

  it('falls back to 5000 for unparseable values', async () => {
    const res = await withEnv({ API_TIMEOUT_MS: 'NaN' });
    const json = await res.json<{ timeout: number }>();
    // NaN propagates — test documents current behaviour
    expect(Number.isNaN(json.timeout)).toBe(true);
  });
});
```

---

## Overriding via `SELF` (Integration Style)

When you need to exercise the full Worker dispatch pipeline (middleware, scheduled
handlers, error boundaries) use `SELF` with `getMiniflareBindings` to swap KV/D1
in addition to plain vars.

```ts
// src/integration.test.ts
import { SELF, env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';

// `env` is the live miniflare env — mutating it affects subsequent SELF requests
// within the same test worker process.

describe('integration overrides via env mutation', () => {
  const original = { ...env } as Record<string, string>;

  beforeEach(() => {
    // restore baseline after each test
    Object.assign(env, original);
  });

  it('returns 500 when STRIPE_SECRET_KEY cleared', async () => {
    (env as Record<string, string>).STRIPE_SECRET_KEY = '';
    const res = await SELF.fetch('https://example.com/');
    expect(res.status).toBe(500);
  });

  it('enables new checkout via flag', async () => {
    (env as Record<string, string>).FEATURE_NEW_CHECKOUT = 'true';
    const res = await SELF.fetch('https://example.com/');
    const json = await res.json<{ newCheckout: boolean }>();
    expect(json.newCheckout).toBe(true);
  });
});
```

> **Warning**: Mutating `env` is process-global within a worker pool thread. Use
> `beforeEach` + restore, or isolate to a dedicated test project with its own
> `miniflare.bindings`.

---

## Per-Suite Isolation via Multiple Vitest Projects

For truly independent env setups, declare separate Vitest projects in
`vitest.config.ts`:

```ts
// vitest.config.ts (multi-project)
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    projects: [
      {
        name: 'staging-env',
        include: ['src/**/*.staging.test.ts'],
        poolOptions: {
          workers: {
            wrangler: { configPath: './wrangler.toml' },
            miniflare: {
              bindings: {
                ENVIRONMENT: 'staging',
                FEATURE_NEW_CHECKOUT: 'true',
                STRIPE_SECRET_KEY: 'sk_test_staging_key',
                API_TIMEOUT_MS: '5000',
              },
            },
          },
        },
      },
      {
        name: 'prod-env',
        include: ['src/**/*.prod.test.ts'],
        poolOptions: {
          workers: {
            wrangler: { configPath: './wrangler.toml' },
            miniflare: {
              bindings: {
                ENVIRONMENT: 'production',
                FEATURE_NEW_CHECKOUT: 'false',
                STRIPE_SECRET_KEY: 'sk_live_prod_key',
                API_TIMEOUT_MS: '3000',
              },
            },
          },
        },
      },
    ],
  },
});
```

Each project runs in a separate Worker pool with no shared state.

---

## Anti-patterns

- **Reading `process.env` inside the Worker** — Workers run in the V8 isolate,
  not Node. `process.env` is always `{}`. Override via `Env` bindings only.
- **Mutating `env` without `beforeEach` restore** — bleeds overrides into
  subsequent tests within the same thread.
- **Hard-coding secrets in test files** — use placeholder strings like
  `'sk_test_placeholder'` and exclude real secrets from the repo entirely.
- **Sharing a single `withEnv` baseline across multiple files without importing**
  — each file should import from a shared module, not re-declare the baseline.

---

## Gotchas

- `wrangler.toml` `[vars]` values are strings. Any numeric or boolean env binding
  must be parsed inside the Worker.
- `miniflare.bindings` set in `defineWorkersConfig` are merged on top of
  `wrangler.toml` `[vars]`, so they take precedence.
- `cloudflare:test`'s `env` object is typed as the Env from your Worker's
  TypeScript type. Casting to `Record<string, string>` for dynamic mutation
  satisfies the compiler but bypasses type safety — use sparingly.
- In `--pool=threads` mode (the default), Miniflare pools share one Worker
  process per project. Mutations to `env` within a test affect concurrently
  running tests in the same thread. Use `--pool=forks` or project isolation if
  parallelism is enabled.

---

## Verification

```bash
# run the env-override suite in isolation
npx vitest run src/worker.test.ts --reporter=verbose

# run all projects
npx vitest run --reporter=verbose

# confirm no leakage with random seed
npx vitest run --sequence.shuffle --sequence.seed=42
```

Expected output: all tests pass regardless of execution order.

---

## Related

- `vitest-workers-kv-namespace-isolation.md`
- `vitest-workers-geolocation-cf-object-mocking.md`
- `vitest-workers-scheduled-cron-trigger-testing.md`
- `miniflare-multi-worker-environment-setup.md`
- `vitest-projects-isolation-and-configuration-boundaries.md`

---

## Sources

- Cloudflare Workers Testing docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- `@cloudflare/vitest-pool-workers` README
- Miniflare `MiniflareOptions.bindings` API reference
- Vitest Projects configuration: https://vitest.dev/guide/workspace
