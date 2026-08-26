# Miniflare for Workers Integration Testing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Unit tests that mock `fetch` and stub bindings give false confidence because they bypass the actual Workers runtime dispatch loop. You need end-to-end tests that exercise the full request/response cycle, real KV/D1/R2 semantics, Durable Object coordination, Cron Trigger callbacks, and Queue consumers — all without deploying to Cloudflare.

## Context

Miniflare v3 embeds the `workerd` runtime (the same engine Cloudflare runs in production) inside a Node.js process. Tests invoke real Workers code with real binding implementations backed by in-process SQLite (D1), in-memory storage (KV, R2), and mock queue dispatchers. This is the closest you can get to production parity without an actual deployment.

Miniflare v3 is the foundation of `wrangler dev`; using it directly in tests avoids the HTTP round-trip overhead of talking to `wrangler dev`'s local server.

## Solution

```typescript
// tests/setup.ts  — shared Miniflare factory used across all test files
import { Miniflare, Log, LogLevel } from 'miniflare';
import type { MiniflareOptions } from 'miniflare';

export const TEST_KV_NAMESPACE  = 'MY_KV';
export const TEST_D1_DB         = 'MY_DB';
export const TEST_R2_BUCKET     = 'MY_BUCKET';
export const TEST_QUEUE         = 'MY_QUEUE';

/** Create an isolated Miniflare instance.
 *  Call this in beforeEach / beforeAll depending on test isolation needs. */
export async function createMiniflare(
  overrides: Partial<MiniflareOptions> = {},
): Promise<Miniflare> {
  return new Miniflare({
    // Point at the compiled Worker bundle (produced by your custom build step)
    scriptPath: 'dist/index.js',
    modules: true,            // ESM Worker
    compatibilityDate: '2024-09-23',
    compatibilityFlags: ['nodejs_compat'],

    // ── KV ─────────────────────────────────────────────────────────────
    kvNamespaces: [TEST_KV_NAMESPACE],

    // ── D1 ─────────────────────────────────────────────────────────────
    d1Databases: [TEST_D1_DB],

    // ── R2 ─────────────────────────────────────────────────────────────
    r2Buckets: [TEST_R2_BUCKET],

    // ── Queues ─────────────────────────────────────────────────────────
    queueProducers: { [TEST_QUEUE]: TEST_QUEUE },
    queueConsumers: {

        maxBatchSize:    10,
        maxBatchTimeout: 0,   // process immediately in tests
        maxRetries:      0,
      },
    },

    // ── Vars / Secrets ─────────────────────────────────────────────────
    bindings: {
      ENVIRONMENT: 'test',
      API_SECRET:  'test-secret-value',
    },

    log: new Log(LogLevel.WARN),   // suppress INFO noise in test output
    ...overrides,
  });
}

/** Seed D1 schema from a migrations SQL file. */
export async function seedD1(mf: Miniflare, sqlPath: string): Promise<void> {
  const { readFileSync } = await import('node:fs');
  const db  = await mf.getD1Database(TEST_D1_DB);
  const sql = readFileSync(sqlPath, 'utf8');
  // Split on semicolons so each statement runs individually
  const statements = sql
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => db.prepare(s));
  await db.batch(statements);
}
```

```typescript
// tests/fetch-handler.test.ts  — end-to-end fetch handler tests
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { createMiniflare, seedD1, TEST_KV_NAMESPACE } from './setup';
import type { Miniflare } from 'miniflare';

let mf: Miniflare;

beforeAll(async () => {
  mf = await createMiniflare();
  await seedD1(mf, 'migrations/0001_initial.sql');

  // Pre-populate KV for tests that read from it
  const kv = await mf.getKVNamespace(TEST_KV_NAMESPACE);
  await kv.put('feature:dark-mode', 'true');
});

afterAll(async () => {
  await mf.dispose();
});

describe('GET /api/health', () => {
  it('returns 200 with status body', async () => {
    const res = await mf.dispatchFetch('http://localhost/api/health');
    expect(res.status).toBe(200);
    const body = await res.json<{ status: string }>();
    expect(body.status).toBe('ok');
  });
});

describe('POST /api/items', () => {
  it('inserts a row and returns 201', async () => {
    const res = await mf.dispatchFetch('http://localhost/api/items', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name: 'test-item', value: 42 }),
    });
    expect(res.status).toBe(201);
    const body = await res.json<{ id: number }>();
    expect(typeof body.id).toBe('number');
  });

  it('returns 400 for missing required fields', async () => {
    const res = await mf.dispatchFetch('http://localhost/api/items', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });
});

describe('KV feature flag', () => {
  it('enables dark mode when flag is set', async () => {
    const res = await mf.dispatchFetch('http://localhost/api/features/dark-mode');
    const body = await res.json<{ enabled: boolean }>();
    expect(body.enabled).toBe(true);
  });
});
```

```typescript
// tests/durable-object.test.ts  — testing a counter Durable Object
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMiniflare } from './setup';
import type { Miniflare } from 'miniflare';

let mf: Miniflare;

beforeEach(async () => {
  // Fresh instance per test — complete state isolation
  mf = await createMiniflare({
    durableObjects: {
      COUNTER: { className: 'Counter', scriptName: 'main' },
    },
  });
});

afterEach(async () => {
  await mf.dispose();
});

describe('Counter Durable Object', () => {
  async function getCount(id: string): Promise<number> {
    const res = await mf.dispatchFetch(
      `http://localhost/do/counter/${encodeURIComponent(id)}`,
    );
    const body = await res.json<{ count: number }>();
    return body.count;
  }

  async function increment(id: string): Promise<void> {
    await mf.dispatchFetch(
      `http://localhost/do/counter/${encodeURIComponent(id)}/increment`,
      { method: 'POST' },
    );
  }

  it('starts at zero', async () => {
    expect(await getCount('room-1')).toBe(0);
  });

  it('increments correctly', async () => {
    await increment('room-1');
    await increment('room-1');
    expect(await getCount('room-1')).toBe(2);
  });

  it('isolates state between different IDs', async () => {
    await increment('room-a');
    expect(await getCount('room-b')).toBe(0);
  });
});
```

```typescript
// tests/cron-trigger.test.ts  — invoking a Cron Trigger directly
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { createMiniflare, TEST_D1_DB } from './setup';
import type { Miniflare } from 'miniflare';

let mf: Miniflare;

beforeAll(async () => {
  mf = await createMiniflare();
});

afterAll(async () => {
  await mf.dispose();
});

describe('Scheduled handler (Cron Trigger)', () => {
  it('prunes expired rows when triggered', async () => {
    const db = await mf.getD1Database(TEST_D1_DB);

    // Seed some expired rows
    await db.batch([
      db.prepare(
        `INSERT INTO sessions (token, expires_at) VALUES ('expired-1', datetime('now', '-1 hour'))`,
      ),
      db.prepare(
        `INSERT INTO sessions (token, expires_at) VALUES ('valid-1', datetime('now', '+1 hour'))`,
      ),
    ]);

    // Miniflare exposes scheduledFetch to simulate a cron event
    const result = await mf.dispatchScheduled({
      scheduledTime: Date.now(),
      cron:          '0 * * * *',
    });
    expect(result.outcome).toBe('ok');

    // Confirm the expired row was removed
    const { results } = await db
      .prepare('SELECT token FROM sessions')
      .all<{ token: string }>();
    expect(results.map((r) => r.token)).toEqual(['valid-1']);
  });
});
```

```typescript
// tests/queue-consumer.test.ts  — testing a Queue consumer
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMiniflare, TEST_QUEUE, TEST_D1_DB } from './setup';
import type { Miniflare } from 'miniflare';

let mf: Miniflare;

beforeEach(async () => {
  mf = await createMiniflare();
});

afterEach(async () => {
  await mf.dispose();
});

describe('Queue consumer', () => {
  it('processes a batch of messages and writes to D1', async () => {
    const queue = await mf.getQueue(TEST_QUEUE);
    await queue.send({ type: 'user.signup', userId: 'u_123', plan: 'pro' });
    await queue.send({ type: 'user.signup', userId: 'u_456', plan: 'free' });

    // Flush — Miniflare processes queued messages synchronously when flushed
    await mf.flushQueues();

    const db = await mf.getD1Database(TEST_D1_DB);
    const { results } = await db
      .prepare('SELECT user_id, plan FROM signups ORDER BY user_id')
      .all<{ user_id: string; plan: string }>();

    expect(results).toEqual([
      { user_id: 'u_123', plan: 'pro' },
      { user_id: 'u_456', plan: 'free' },
    ]);
  });

  it('retries a message after a non-terminal error', async () => {
    const queue = await mf.getQueue(TEST_QUEUE);
    await queue.send({ type: 'will.fail.once', attempt: 0 });
    await mf.flushQueues();  // first attempt — consumer throws, message re-queued
    await mf.flushQueues();  // second attempt — succeeds
    // Assert side-effect of successful second attempt
  });
});
```

## Implementation Details

**Per-test vs per-suite isolation.** Creating a Miniflare instance takes ~200–400 ms because `workerd` must start. For a suite of fast fetch-handler tests, one shared instance with `beforeAll`/`afterAll` is fine — seed data once, truncate tables in `afterEach` if needed. For Durable Object tests where state leaks between tests are a risk, create a fresh instance per test (`beforeEach`/`afterEach`).

**D1 schema seeding.** `mf.getD1Database()` returns a D1Database binding identical to what your Worker sees. Run your migration SQL files against it before tests. Wrap each statement in `db.prepare()` and batch them to minimize round-trips.

**Queue flush semantics.** `mf.flushQueues()` drains the in-memory queue and delivers messages to the consumer's `queue()` handler synchronously. If the consumer retries (throws or calls `message.retry()`), the message re-queues and a second `flushQueues()` call is needed.

**`dispatchScheduled`.** Miniflare accepts `{ scheduledTime, cron }` and calls the Worker's `scheduled()` handler directly. Use this to test `addEventListener('scheduled', ...)` without setting up a real cron job.

**Vitest configuration.** Miniflare is a Node.js library; run tests in the `node` environment, not `jsdom`. Set `pool: 'forks'` in vitest config if tests that share a Miniflare instance flake under `threads` mode (workerd's in-process SQLite is not thread-safe).

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    environment: 'node',
    pool:        'forks',
    poolOptions: { forks: { singleFork: false } },
    testTimeout: 15_000,   // workerd startup can be slow on cold machines
  },
});
```

## Anti-patterns

- **Re-using one global Miniflare instance across all test files in parallel.** Vitest runs files in separate worker processes; a singleton in a setup file is not shared across processes. Each worker file gets its own Miniflare instance automatically — which is good for isolation but means you pay the startup cost N times. Group slow integration tests in fewer files.
- **Importing the Worker's source directly into tests.** The Worker must run inside the `workerd` runtime to exercise binding APIs. Importing `src/index.ts` into a Node test bypasses `workerd` entirely and will throw on any `env.MY_KV.get()` call.
- **Using `miniflare` v2 APIs with v3.** The v3 API is a complete rewrite. `MiniflareOptions` keys changed (`kvNamespaces` is now an array of strings, not an object). Check `miniflare@^3` docs specifically.

## Gotchas

- Miniflare v3 requires Node.js ≥ 18.0.0 (uses native `fetch` and `AsyncLocalStorage`).
- The first `new Miniflare(...)` call downloads the `workerd` binary if it is not cached. In CI, cache `~/.cache/miniflare` / the npm cache to avoid repeated downloads.
- `mf.dispatchFetch()` does not go through a real HTTP server; it calls the Worker's `fetch` handler directly. This means network middleware (e.g., a real TLS layer) is not tested. For end-to-end HTTP testing, use `mf.ready` + the `address` getter to talk to the local HTTP server Miniflare starts.
- Durable Object alarm handlers are invoked via `mf.triggerAlarm(doId)` in Miniflare v3, not via `dispatchScheduled`.

## Verification

```bash
# Install
npm install --save-dev miniflare vitest

# Run integration tests
npx vitest run tests/

# Run only queue consumer tests with verbose output
npx vitest run tests/queue-consumer.test.ts --reporter=verbose

# CI — fail fast
npx vitest run --bail 1
```

## Related

- `documentation/categories/devtools/workers-wrangler-custom-builds.md` — producing `dist/index.js` that Miniflare loads
- `documentation/categories/devtools/workers-workerd-local-dev.md` — using `workerd` directly without Miniflare
- Miniflare v3 docs: https://miniflare.dev

## Sources

- https://miniflare.dev/get-started/index
- https://miniflare.dev/core/fetch
- https://miniflare.dev/storage/d1
- https://miniflare.dev/queues
- https://vitest.dev/config/#pool
