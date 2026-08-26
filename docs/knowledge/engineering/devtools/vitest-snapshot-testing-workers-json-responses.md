# Vitest Snapshot Testing for Workers JSON Responses

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers HTTP handlers return JSON API responses that grow complex over time
— nested objects, computed fields, pagination envelopes. Writing exhaustive `expect(body.x).toBe(y)` assertions for every field is tedious, prone to gaps, and breaks silently when new fields are added. You want a snapshot-based approach that:

1. Captures the entire response body on first run and locks it in a `.snap` file.
2. Fails future runs if the response shape changes unexpectedly.
3. Works inside `@cloudflare/vitest-pool-workers` without leaking Node.js-specific matchers
   into the Workers isolate.
4. Integrates with the existing `SELF.fetch()` / `env.QUEUE` pattern used in Workers tests.

---

## Context

Vitest's snapshot engine (`expect(value).toMatchSnapshot()` and inline
`expect(value).toMatchInlineSnapshot()`) works inside `@cloudflare/vitest-pool-workers`
test files with minor configuration. Because Workers tests run inside a V8 isolate, the
snapshot serialiser must serialise only JSON-serialisable values — no Promises, no DOM
nodes, no Node.js Buffers.

Snapshots are stored in `__snapshots__/` next to the test file (or inline in the test
file for `toMatchInlineSnapshot`). They are committed to version control and reviewed in
PRs as part of the API contract.

This pattern is most useful for:
- List/collection endpoint responses (pagination, sort, filter combinations)
- Computed summary fields (aggregates, derived state)
- Error response shapes (error code, message, field validation errors)
- Header sets on responses (Content-Type, Cache-Control, Vary)

---

## Step 1 — Basic JSON Body Snapshot

```typescript
// test/api/users.test.ts
import { SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { seedUser } from "../fixtures/seed";

describe("GET /api/v1/users", () => {
  beforeEach(async () => {
    await seedUser({ id: "usr_001", email: "alice@example.com", name: "Alice" });
    await seedUser({ id: "usr_002", email: "bob@example.com", name: "Bob" });
  });

  it("returns a paginated user list", async () => {
    const response = await SELF.fetch("http://localhost/api/v1/users?limit=2");
    expect(response.status).toBe(200);

    const body = await response.json();

    // Snapshot the full response body — locked on first run
    expect(body).toMatchSnapshot();
  });
});
```

First run output (snapshot created):

```
1 snapshot written.
```

Subsequent run (no change):

```
1 snapshot passed.
```

After an accidental schema change:

```
Snapshot name: `GET /api/v1/users returns a paginated user list 1`

  - Expected
  + Received

    Object {
  -   "data": Array [
  +   "users": Array [
```

---

## Step 2 — Stabilising Dynamic Fields

Snapshots break on non-deterministic fields like `id`, `createdAt`, and `updatedAt`.
Replace them before snapshotting:

```typescript
// test/helpers/sanitize-snapshot.ts

type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

/**
 * Replace known dynamic fields with stable placeholders so snapshots
 * don't fail on timestamps, UUIDs, or other non-deterministic values.
 */
export function sanitizeSnapshot(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(sanitizeSnapshot);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => {
        // UUID fields
        if (/^(id|.*_id|.*Id)$/.test(k) && typeof v === "string") {
          return [k, "[uuid]"];
        }
        // Timestamp fields
        if (/^(created_at|updated_at|createdAt|updatedAt|timestamp)$/.test(k)) {
          return [k, "[timestamp]"];
        }
        // Recurse
        return [k, sanitizeSnapshot(v)];
      })
    );
  }
  return value;
}
```

```typescript
// test/api/users.test.ts (updated)
import { sanitizeSnapshot } from "../helpers/sanitize-snapshot";

it("returns a paginated user list", async () => {
  const response = await SELF.fetch("http://localhost/api/v1/users?limit=2");
  const body = await response.json<Record<string, unknown>>();

  expect(sanitizeSnapshot(body as any)).toMatchSnapshot();
});
```

Snapshot file after first run:

```
// Vitest Snapshot v1, https://vitest.dev/guide/snapshot.html

exports[`GET /api/v1/users returns a paginated user list 1`] = `
{
  "data": [
    {
      "createdAt": "[timestamp]",
      "email": "alice@example.com",
      "id": "[uuid]",
      "name": "Alice",
    },
    {
      "createdAt": "[timestamp]",
      "email": "bob@example.com",
      "id": "[uuid]",
      "name": "Bob",
    },
  ],
  "pagination": {
    "limit": 2,
    "nextCursor": "[uuid]",
    "total": 2,
  },
}
`;
```

---

## Step 3 — Snapshotting Response Headers

```typescript
// test/api/cache-headers.test.ts
import { SELF } from "cloudflare:test";
import { it, expect } from "vitest";

it("sets correct cache headers on static assets", async () => {
  const response = await SELF.fetch("http://localhost/api/v1/products/cat_electronics");

  // Extract only the headers we want to snapshot (avoid snapshotting all headers
  // which includes server-generated values like Date and CF-Ray)
  const relevantHeaders = Object.fromEntries(
    ["cache-control", "content-type", "vary", "etag"].map((h) => [
      h,
      response.headers.get(h) ?? "<absent>",
    ])
  );

  expect(relevantHeaders).toMatchSnapshot();
});
```

---

## Step 4 — Inline Snapshots for Small Responses

For small, stable responses, inline snapshots keep the assertion co-located with the test
and avoid a separate `.snap` file:

```typescript
// test/api/health.test.ts
import { SELF } from "cloudflare:test";
import { it, expect } from "vitest";

it("returns health check response", async () => {
  const response = await SELF.fetch("http://localhost/healthz");
  const body = await response.json();

  expect(body).toMatchInlineSnapshot(`
    {
      "status": "ok",
      "version": "1.0.0",
    }
  `);
});
```

Vitest auto-fills the inline snapshot argument on first run. Update it with:

```bash
pnpm vitest run --update-snapshots
```

---

## Step 5 — Error Response Snapshot Suite

A dedicated snapshot suite for error responses locks the error contract:

```typescript
// test/api/error-responses.test.ts
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("Error response shapes", () => {
  it("returns 404 shape for missing resource", async () => {
    const response = await SELF.fetch("http://localhost/api/v1/users/nonexistent");
    expect(response.status).toBe(404);
    expect(await response.json()).toMatchInlineSnapshot(`
      {
        "code": "USER_NOT_FOUND",
        "message": "User not found",
        "status": 404,
      }
    `);
  });

  it("returns 422 shape for validation error", async () => {
    const response = await SELF.fetch("http://localhost/api/v1/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "not-an-email" }),
    });
    expect(response.status).toBe(422);
    const body = await response.json();
    expect(body).toMatchInlineSnapshot(`
      {
        "code": "VALIDATION_ERROR",
        "errors": [
          {
            "field": "email",
            "message": "Invalid email address",
          },
        ],
        "message": "Validation failed",
        "status": 422,
      }
    `);
  });
});
```

---

## Step 6 — CI: Fail on Uncommitted Snapshot Changes

Prevent snapshot drift from going unnoticed in PRs:

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: pnpm vitest run

- name: Check for uncommitted snapshot changes
  run: |
    if ! git diff --exit-code -- "**/__snapshots__/**"; then
      echo "ERROR: Snapshots changed but were not committed."
      echo "Run: pnpm vitest run --update-snapshots, review the diff, and commit the .snap files."
      exit 1
    fi
```

---

## Step 7 — Custom Snapshot Serialiser for Response Objects

If you want to snapshot the full `Response` object (status + headers + body) as a single
unit, register a custom serialiser:

```typescript
// test/setup.ts
import { expect } from "vitest";

expect.addSnapshotSerializer({
  test(val): val is Response {
    return val instanceof Response;
  },
  async serialize(val: Response): Promise<string> {
    const body = await val.clone().text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(body);
    } catch {
      parsed = body;
    }
    return JSON.stringify(
      {
        status: val.status,
        contentType: val.headers.get("content-type"),
        body: parsed,
      },
      null,
      2
    );
  },
});
```

Note: custom async serialisers are supported in Vitest 1.x+ via the `serialize` method
returning a `Promise<string>`. In older versions, pre-await the body before snapshotting.

---

## Anti-patterns

**Snapshotting non-deterministic values without sanitisation:**
```typescript
// BAD — snapshot breaks every run because id and createdAt change
expect(await response.json()).toMatchSnapshot();

// GOOD — sanitise first
expect(sanitizeSnapshot(await response.json())).toMatchSnapshot();
```

**Using snapshots as a substitute for unit tests on logic:**
Snapshots catch regressions in serialised output. They don't test invariants. Use
`expect(body.total).toBeGreaterThan(0)` for logical assertions and snapshots for shape.

**Committing auto-updated snapshots without reviewing the diff:**
Always read snapshot diffs in PRs. A snapshot update that adds a new field is a contract
change that downstream consumers of your API may depend on.

**One large snapshot per file instead of targeted snapshots per endpoint:**
A single mega-snapshot that covers all endpoints makes it hard to identify which endpoint
changed. Organise snapshot tests by endpoint or by feature area.

---

## Gotchas

- `@cloudflare/vitest-pool-workers` runs tests inside a V8 isolate. The snapshot state
  is managed by Vitest's main thread, not the isolate. This means `toMatchSnapshot()` works
  correctly — the result value is transferred out of the isolate and serialised in the main
  thread.
- Snapshot files use a different format in Vitest vs Jest. Do not mix `@jest/expect` with
  Vitest — the serialisers are different and snapshot files will be in incompatible formats.
- `toMatchInlineSnapshot` mutates the test source file to fill in the snapshot value on
  first run. This requires write access to the test file. In read-only CI environments, run
  `--update-snapshots` locally before committing.
- When using `SELF.fetch()`, the Response body stream can only be consumed once. Always
  use `response.clone()` if you need both the raw response (for header checks) and the body
  (for snapshot checks) in the same test.
- Vitest's `--watch` mode auto-updates inline snapshots interactively. Disable this in CI
  with `vitest run` (not `vitest`) to avoid accidental snapshot writes.

---

## Verification

```bash
# Create snapshots from scratch (delete existing .snap files first to verify)
rm -rf test/__snapshots__
pnpm vitest run
# Expected: "N snapshots written"

# Verify no snapshot drift after a code change
pnpm vitest run
git diff --exit-code -- "**/__snapshots__/**"
# Expected: no diff

# Update snapshots after an intentional response shape change
pnpm vitest run --update-snapshots
git diff -- "**/__snapshots__/**"
# Review the diff before committing
```

---

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `vitest-pool-workers-cloudflare-test-api.md`
- `vitest-workers-request-clone-stream-testing.md`
- `miniflare-d1-test-seeding-fixtures.md`
- `vitest-global-setup-d1-migration-runner.md`

---

## Sources

- Vitest snapshot testing docs: https://vitest.dev/guide/snapshot.html
- Vitest custom serialiser API: https://vitest.dev/guide/snapshot.html#custom-serializer
- `@cloudflare/vitest-pool-workers` docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Cloudflare Workers testing patterns: https://developers.cloudflare.com/workers/testing/
- Jest snapshot best practices (applicable to Vitest): https://jestjs.io/docs/snapshot-testing#best-practices
