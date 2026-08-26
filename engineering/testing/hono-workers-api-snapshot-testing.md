# Hono Workers API Snapshot Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

When building REST APIs on Cloudflare Workers with Hono, response shapes evolve across releases. A regression in JSON structure—renamed fields, removed keys, changed status codes, altered error envelopes—often goes undetected until production traffic breaks clients. Snapshot testing captures the exact serialized response at a known-good state and fails loudly when any field changes, acting as a regression gate with minimal per-test maintenance.

## Context

Hono runs as a standard `fetch`-compatible handler, making it trivial to call with `app.request()` in Vitest without spinning up an HTTP server. The `@cloudflare/vitest-pool-workers` pool provides real bindings (KV, D1, R2) so route handlers that touch storage can be tested end-to-end. Vitest's built-in `toMatchInlineSnapshot` and `toMatchSnapshot` work out of the box once the pool is configured.

Snapshots are most valuable for:
- Error response envelopes (status + code + message shapes)
- Paginated list endpoints (meta fields, cursor position)
- Aggregated data endpoints where shape is stable but content varies

## Setup

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
    snapshotOptions: {
      // Normalise dates and IDs before snapshotting
      snapshotSerializers: [],
    },
  },
});
```

```typescript
// src/index.ts — minimal Hono app under test
import { Hono } from 'hono';

type Bindings = { KV: KVNamespace };

const app = new Hono<{ Bindings: Bindings }>();

app.get('/items', async (c) => {
  const cursor = c.req.query('cursor') ?? null;
  return c.json({ items: [], cursor, total: 0 });
});

app.get('/items/:id', async (c) => {
  const item = await c.env.KV.get(`item:${c.req.param('id')}`);
  if (!item) return c.json({ error: { code: 'NOT_FOUND', message: 'Item not found' } }, 404);
  return c.json(JSON.parse(item));
});

export default app;
```

## Basic Response Shape Snapshot

```typescript
// tests/items.snap.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import app from '../src/index';

describe('GET /items', () => {
  it('matches snapshot for empty list response', async () => {
    const res = await app.request('/items', {}, env);
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body).toMatchInlineSnapshot(`
      {
        "cursor": null,
        "items": [],
        "total": 0,
      }
    `);
  });

  it('includes cursor when provided', async () => {
    const res = await app.request('/items?cursor=eyJpZCI6IjEifQ', {}, env);
    const body = await res.json();
    expect(body.cursor).toMatchInlineSnapshot(`"eyJpZCI6IjEifQ"`);
  });
});
```

## Snapshot Testing Error Envelopes

```typescript
describe('GET /items/:id error shapes', () => {
  it('404 envelope matches snapshot', async () => {
    const res = await app.request('/items/missing-id', {}, env);
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body).toMatchInlineSnapshot(`
      {
        "error": {
          "code": "NOT_FOUND",
          "message": "Item not found",
        },
      }
    `);
  });
});
```

## Normalising Dynamic Fields Before Snapshotting

Timestamps and generated IDs must be replaced with stable sentinels to avoid snapshot churn:

```typescript
// tests/helpers/normalise.ts
export function normaliseResponse(body: unknown): unknown {
  return JSON.parse(
    JSON.stringify(body, (_key, value) => {
      if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
        return '__TIMESTAMP__';
      }
      if (
        typeof value === 'string' &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
      ) {
        return '__UUID__';
      }
      return value;
    })
  );
}
```

```typescript
// tests/items.snap.test.ts (continued)
import { normaliseResponse } from './helpers/normalise';

it('created item response shape matches snapshot', async () => {
  const res = await app.request(
    '/items',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Widget' }),
    },
    env
  );
  const body = normaliseResponse(await res.json());
  expect(body).toMatchInlineSnapshot(`
    {
      "createdAt": "__TIMESTAMP__",
      "id": "__UUID__",
      "name": "Widget",
    }
  `);
});
```

## Snapshot Testing Response Headers

```typescript
it('response headers match snapshot', async () => {
  const res = await app.request('/items', {}, env);
  const headers: Record<string, string> = {};
  res.headers.forEach((value, key) => {
    // Exclude volatile headers
    if (!['date', 'cf-ray'].includes(key)) headers[key] = value;
  });
  expect(headers).toMatchInlineSnapshot(`
    {
      "content-type": "application/json; charset=UTF-8",
    }
  `);
});
```

## Updating Snapshots

```bash
# Update all snapshots after an intentional API change
npx vitest run --update-snapshot

# Update a single file's snapshots
npx vitest run tests/items.snap.test.ts --update-snapshot
```

Always review the diff produced by `--update-snapshot` before committing. Treat snapshot updates as code changes requiring PR review.

## Anti-patterns

- **Snapshotting the raw response body without normalisation** – Timestamps and IDs cause snapshot churn on every test run. Always normalise dynamic fields first.
- **Putting every assertion in a snapshot** – Status codes, content-type, and simple boolean fields are better expressed with explicit `expect(x).toBe(y)` assertions; snapshots are for structure, not values.
- **Using external snapshots (`toMatchSnapshot`) for trivial responses** – Inline snapshots (`toMatchInlineSnapshot`) keep the expected value visible next to the assertion, reducing the need to jump between files.
- **Committing auto-updated snapshots without review** – CI should fail on snapshot drift; `--update-snapshot` is a local developer action, not a CI flag.

## Gotchas

- `app.request(path, init, env)` in pool-workers passes the Miniflare `env` as the third argument. Omitting it causes `c.env` to be undefined inside route handlers that access bindings.
- Hono's `c.json()` sets `Content-Type: application/json; charset=UTF-8`. Snapshot the header value exactly as produced; `application/json` without the charset will not match.
- Inline snapshots are auto-written on the first run if the argument is omitted. Run `vitest run` (not `watch`) the first time to generate them without re-running indefinitely.
- `toMatchInlineSnapshot` indentation is significant: Vitest formats with two-space indentation. Manual edits must preserve this.

## Verification

```bash
# First run: generate inline snapshots
npx vitest run tests/items.snap.test.ts

# Subsequent runs: confirm no drift
npx vitest run tests/items.snap.test.ts
# All tests should pass with no "1 snapshot written" messages
```

## Related

- `snapshot-testing-workers-responses.md` — generic Workers response snapshot patterns
- `snapshot-testing-best-practices.md` — when to use snapshots vs explicit assertions
- `vitest-cloudflare-pool-workers.md` — pool-workers Vitest configuration
- `workers-test-patterns.md` — Hono handler unit testing approaches

## Sources

- https://hono.dev/docs/guides/testing
- https://vitest.dev/guide/snapshot.html
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/honojs/hono/tree/main/src/testing
