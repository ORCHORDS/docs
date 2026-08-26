# API Response Snapshot Testing for Workers with Vitest

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker's JSON response shape quietly changes — a renamed field, an added array wrapper, a removed error code — and no test catches it until a client breaks. Snapshot testing pins the exact response shape and fails loudly when it changes, acting as a structured diff for API contracts.

## Context

Vitest supports two snapshot modes out of the box:
- **Inline snapshots** — the expected value lives next to the assertion in the test file.
- **External snapshots** — written to `__snapshots__/*.snap` files alongside the test.

Both work inside `@cloudflare/vitest-pool-workers` because Miniflare runs the full Worker. D1 query results are plain JS objects and serialise naturally. Dynamic fields (timestamps, auto-increment IDs, request IDs) must be masked before snapshotting.

---

## Solution

### 1. Project setup

```jsonc
// vitest.config.ts (excerpt)
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';
export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
    // Keep snapshots next to test files
    snapshotOptions: { snapshotDir: '__snapshots__' },
    // Fail CI when a snapshot is missing instead of creating it silently
    ci: true,
  },
});
```

### 2. Test helper — fetch the Worker and normalise the response

```typescript
// test/helpers/snapshot.ts
import { SELF } from 'cloudflare:test';

type MaskMap = Record<string, unknown>;

/**
 * Recursively replace fields listed in `mask` with a stable placeholder.
 * Useful for timestamps, UUIDs, and auto-increment IDs.
 */
export function maskDynamic(obj: unknown, mask: MaskMap): unknown {
  if (Array.isArray(obj)) return obj.map((item) => maskDynamic(item, mask));
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k,
        k in mask ? mask[k] : maskDynamic(v, mask),
      ]),
    );
  }
  return obj;
}

/** Fetch a Worker endpoint and return the parsed JSON with dynamic fields masked. */
export async function fetchJSON(
  path: string,
  init: RequestInit = {},
  mask: MaskMap = {},
): Promise<unknown> {
  const res = await SELF.fetch(`http://localhost${path}`, init);
  const body = await res.json();
  return maskDynamic(body, mask);
}

/** Convenience: fetch + status + headers snapshot payload. */
export async function fetchSnapshot(
  path: string,
  init: RequestInit = {},
  mask: MaskMap = {},
) {
  const res = await SELF.fetch(`http://localhost${path}`, init);
  const body = await res.json().catch(() => null);
  return {
    status: res.status,
    contentType: res.headers.get('content-type'),
    body: maskDynamic(body, mask),
  };
}
```

### 3. Inline snapshot testing

```typescript
// test/users.snapshot.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { fetchSnapshot } from './helpers/snapshot';

const MASK = {
  id: '[ID]',
  createdAt: '[TIMESTAMP]',
  updatedAt: '[TIMESTAMP]',
  requestId: '[REQUEST_ID]',
};

beforeAll(async () => {
  await env.DB.exec(`
    INSERT OR REPLACE INTO users (id, name, email, createdAt, updatedAt)
    VALUES (1, 'Alice', 'alice@example.com', '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')
  `);
});

describe('GET /users/:id', () => {
  it('returns a user object matching the snapshot', async () => {
    const snap = await fetchSnapshot('/users/1', {}, MASK);
    // First run: press `u` in watch mode to create; subsequent runs compare
    expect(snap).toMatchInlineSnapshot(`
      {
        "body": {
          "createdAt": "[TIMESTAMP]",
          "email": "alice@example.com",
          "id": "[ID]",
          "name": "Alice",
          "updatedAt": "[TIMESTAMP]",
        },
        "contentType": "application/json",
        "status": 200,
      }
    `);
  });

  it('returns 404 for unknown user', async () => {
    const snap = await fetchSnapshot('/users/9999', {}, MASK);
    expect(snap).toMatchInlineSnapshot(`
      {
        "body": {
          "error": "user_not_found",
          "message": "No user with id 9999",
          "requestId": "[REQUEST_ID]",
        },
        "contentType": "application/json",
        "status": 404,
      }
    `);
  });
});
```

### 4. External snapshot file management

```typescript
// test/products.snapshot.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { fetchJSON } from './helpers/snapshot';

const MASK = { id: '[ID]', createdAt: '[TS]', price: '[PRICE]' };

beforeAll(async () => {
  await env.DB.batch([
    env.DB.prepare(`INSERT OR REPLACE INTO products (id, name, price, createdAt) VALUES (1,'Widget',999,'2024-01-01')`),
    env.DB.prepare(`INSERT OR REPLACE INTO products (id, name, price, createdAt) VALUES (2,'Gadget',1499,'2024-01-01')`),
  ]);
});

describe('GET /products', () => {
  it('lists all products', async () => {
    const body = await fetchJSON('/products', {}, MASK);
    // Stored in test/__snapshots__/products.snapshot.test.ts.snap
    expect(body).toMatchSnapshot();
  });

  it('filters by name query param', async () => {
    const body = await fetchJSON('/products?name=Widget', {}, MASK);
    expect(body).toMatchSnapshot();
  });
});
```

The generated `.snap` file:

```
// Vitest Snapshot v1, https://vitest.dev/guide/snapshot.html

exports[`GET /products > filters by name query param 1`] = `
[
  {
    "createdAt": "[TS]",
    "id": "[ID]",
    "name": "Widget",
    "price": "[PRICE]",
  },
]
`;

exports[`GET /products > lists all products 1`] = `
[
  {
    "createdAt": "[TS]",
    "id": "[ID]",
    "name": "Widget",
    "price": "[PRICE]",
  },
  {
    "createdAt": "[TS]",
    "id": "[ID]",
    "name": "Gadget",
    "price": "[PRICE]",
  },
]
`;
```

### 5. Serialising D1 results for snapshots

```typescript
// test/helpers/d1Snapshot.ts
import type { D1Result } from '@cloudflare/workers-types';

/**
 * Converts a D1Result into a plain array suitable for snapshotting.
 * Sorts rows by a stable key to avoid ordering flakiness.
 */
export function stableD1<T extends Record<string, unknown>>(
  result: D1Result<T>,
  sortKey: keyof T,
): T[] {
  return [...result.results].sort((a, b) =>
    String(a[sortKey]).localeCompare(String(b[sortKey])),
  );
}
```

```typescript
// Usage in a test
import { env } from 'cloudflare:test';
import { stableD1 } from './helpers/d1Snapshot';
import { maskDynamic } from './helpers/snapshot';

it('D1 query result matches snapshot', async () => {
  const result = await env.DB.prepare('SELECT * FROM orders').all<{ id: number; status: string; createdAt: string }>();
  const rows = stableD1(result, 'id');
  const masked = maskDynamic(rows, { id: '[ID]', createdAt: '[TS]' });
  expect(masked).toMatchSnapshot();
});
```

### 6. Snapshot update workflow

```bash
# Update all outdated snapshots (after an intentional API change)
npx vitest run --update-snapshots

# Update snapshots for a single test file
npx vitest run --update-snapshots test/users.snapshot.test.ts

# Interactive watch mode — press `u` to update the failing snapshot
npx vitest --watch
```

In CI, never pass `--update-snapshots`. A missing or mismatched snapshot is a build failure that requires a deliberate developer action.

---

## Implementation Details

- Inline snapshots are re-written into the test source file by Vitest; commit the changes after `--update-snapshots`.
- External `.snap` files are committed to source control — treat them as code review artefacts.
- `maskDynamic` is pure and synchronous; it can be used on both HTTP response bodies and raw D1 rows.
- For arrays whose order is non-deterministic (e.g. unordered `SELECT`), always sort before snapshotting.

---

## Anti-patterns

- **Snapshotting entire headers objects** — header order is unstable; snapshot only specific headers (`content-type`, `cache-control`).
- **Not masking timestamps** — leads to snapshot churn every run; always replace with a stable placeholder.
- **Adding `--update-snapshots` to CI flags** — silently hides regressions; snapshots must be committed by humans.
- **Giant snapshots** — if a snapshot exceeds ~100 lines, split the test or assert on a subset of fields.

---

## Gotchas

- `toMatchInlineSnapshot` rewrites the test file in-process; if Vitest runs in parallel with `--reporter=junit` the file write can conflict. Run inline-snapshot tests in a single worker thread: `--pool=forks --poolOptions.forks.singleFork`.
- D1's `INTEGER PRIMARY KEY` returns a `number` in JavaScript but `bigint` under some drivers; assert the type before snapshotting.
- `.snap` files contain backticks escaped as `` \` `` — do not manually edit them unless you know the escape rules.

---

## Verification

```bash
# All snapshot tests must pass without --update-snapshots in CI
npx vitest run --reporter=verbose test/*.snapshot.test.ts
```

Expected: all green; any `snapshot mismatch` is a deliberate API change that needs review.

---

## Related

- `documentation/categories/testing/workers-vitest-d1-fixtures.md`
- `documentation/categories/testing/workers-test-data-factory-d1.md`
- `documentation/categories/testing/integration-test-d1-fixtures.md`

---

## Sources

- https://vitest.dev/guide/snapshot
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
