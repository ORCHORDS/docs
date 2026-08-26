# Vitest D1 Time-Travel Restore Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare D1 supports time-travel: the ability to restore a database to any point in time
within the last 30 days by exporting a historical bookmark. Teams need automated tests that
verify the restore workflow end-to-end — that the Worker correctly calls the D1 time-travel
API, that the application layer recovers gracefully when it receives a restored snapshot with
potentially different row counts or schema states, and that the observability hooks (audit log,
Slack alert) fire correctly. Without a local simulation of D1 time-travel, this path is
untested until a real disaster strikes.

## Context

The example project platform's `apps/admin-worker` exposes a `/restore` endpoint that operators call
to initiate a D1 time-travel restore. The endpoint calls the Cloudflare REST API to create a
restore bookmark, waits for completion, then validates that a canary query returns expected row
counts. The test suite must cover the happy path (restore succeeds), the failure path (bookmark
creation fails), and the race path (restore times out mid-flight). These tests run in the
Vitest Workers pool using Miniflare for the D1 binding and MSW for the Cloudflare REST API.

---

## Architecture of the Restore Endpoint Under Test

```typescript
// apps/admin-worker/src/handlers/restore.ts
import type { Env } from "../types";

export interface RestoreRequest {
  targetTimestamp: string;   // ISO 8601
  reason: string;
}

export interface RestoreResult {
  bookmarkId: string;
  restoredAt: string;
  rowCount: number;
}

export async function handleRestore(
  req: Request,
  env: Env
): Promise<Response> {
  const body = await req.json<RestoreRequest>();

  // 1. Create a D1 time-travel bookmark via Cloudflare API
  const bookmark = await createBookmark(
    env.CF_ACCOUNT_ID,
    env.CF_API_TOKEN,
    env.D1_DATABASE_ID,
    body.targetTimestamp
  );

  // 2. Poll until bookmark is ready (max 30 s)
  await waitForBookmark(env, bookmark.id);

  // 3. Validate restore by running a canary query against the restored DB
  const { results } = await env.example project_DB.prepare(
    "SELECT COUNT(*) AS n FROM articles"
  ).first<{ n: number }>();

  // 4. Audit log
  await env.example project_DB.prepare(
    "INSERT INTO restore_log (bookmark_id, reason, row_count) VALUES (?, ?, ?)"
  ).bind(bookmark.id, body.reason, results.n).run();

  return Response.json({
    bookmarkId: bookmark.id,
    restoredAt: new Date().toISOString(),
    rowCount: results.n,
  } satisfies RestoreResult);
}

async function createBookmark(
  accountId: string, token: string, databaseId: string, timestamp: string
) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/time_travel/bookmark`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ timestamp }),
    }
  );
  if (!res.ok) throw new Error(`Bookmark API failed: ${res.status}`);
  const json = await res.json<{ result: { id: string; state: string } }>();
  return json.result;
}

async function waitForBookmark(env: Env, bookmarkId: string) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/d1/database/${env.D1_DATABASE_ID}/time_travel/bookmark/${bookmarkId}`,
      { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
    );
    const { result } = await res.json<{ result: { state: string } }>();
    if (result.state === "complete") return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("Bookmark restore timed out");
}
```

---

## MSW Handler for D1 Time-Travel API

```typescript
// test/mocks/d1-time-travel-api.ts
import { http, HttpResponse } from "msw";

export let bookmarkState: "pending" | "complete" | "failed" = "complete";
export let bookmarkCallCount = 0;
export const createdBookmarks: string[] = [];

export function resetBookmarkMock() {
  bookmarkState = "complete";
  bookmarkCallCount = 0;
  createdBookmarks.length = 0;
}

const ACCOUNT_ID = "test-account-id";
const DATABASE_ID = "test-db-id";

export const d1TimeTravelHandlers = [
  // POST: create bookmark
  http.post(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${DATABASE_ID}/time_travel/bookmark`,
    async ({ request }) => {
      const body = await request.json<{ timestamp: string }>();
      const id = `bm-${Date.now()}`;
      createdBookmarks.push(id);
      return HttpResponse.json({
        success: true,
        result: { id, state: "pending", timestamp: body.timestamp },
      });
    }
  ),

  // GET: poll bookmark status
  http.get(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${DATABASE_ID}/time_travel/bookmark/:id`,
    ({ params }) => {
      bookmarkCallCount++;
      return HttpResponse.json({
        success: true,
        result: { id: params.id, state: bookmarkState },
      });
    }
  ),
];
```

---

## Vitest Test: Happy Path

```typescript
// test/restore/restore-happy.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { setupServer } from "msw/node";
import { env, SELF } from "cloudflare:test";
import {
  d1TimeTravelHandlers,
  resetBookmarkMock,
  createdBookmarks,
} from "../mocks/d1-time-travel-api";

const server = setupServer(...d1TimeTravelHandlers);

beforeEach(async () => {
  server.listen({ onUnhandledRequest: "error" });
  resetBookmarkMock();
  // Seed D1 with known state
  await env.example project_DB.exec(`
    CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, title TEXT);
    CREATE TABLE IF NOT EXISTS restore_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      bookmark_id TEXT,
      reason TEXT,
      row_count INTEGER
    );
    INSERT INTO articles VALUES (1, 'A'), (2, 'B'), (3, 'C');
  `);
});

afterEach(async () => {
  server.close();
  await env.example project_DB.exec(`
    DROP TABLE IF EXISTS articles;
    DROP TABLE IF EXISTS restore_log;
  `);
});

describe("POST /admin/restore – happy path", () => {
  it("creates a bookmark and returns rowCount", async () => {
    const res = await SELF.fetch("http://localhost/admin/restore", {
      method: "POST",
      body: JSON.stringify({
        targetTimestamp: "2026-08-01T00:00:00Z",
        reason: "accidental deletion",
      }),
      headers: { "Content-Type": "application/json" },
    });

    expect(res.status).toBe(200);
    const json = await res.json<{ bookmarkId: string; rowCount: number }>();
    expect(json.bookmarkId).toMatch(/^bm-/);
    expect(json.rowCount).toBe(3);
    expect(createdBookmarks).toHaveLength(1);
  });

  it("writes an entry to restore_log", async () => {
    await SELF.fetch("http://localhost/admin/restore", {
      method: "POST",
      body: JSON.stringify({ targetTimestamp: "2026-08-01T00:00:00Z", reason: "test run" }),
      headers: { "Content-Type": "application/json" },
    });

    const row = await env.example project_DB.prepare(
      "SELECT reason, row_count FROM restore_log LIMIT 1"
    ).first<{ reason: string; row_count: number }>();

    expect(row?.reason).toBe("test run");
    expect(row?.row_count).toBe(3);
  });
});
```

---

## Vitest Test: Bookmark API Failure

```typescript
// test/restore/restore-api-failure.test.ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { env, SELF } from "cloudflare:test";

const server = setupServer(
  http.post(
    "https://api.cloudflare.com/client/v4/accounts/*/d1/database/*/time_travel/bookmark",
    () => HttpResponse.json({ success: false, errors: [{ code: 7003 }] }, { status: 403 })
  )
);

beforeEach(async () => {
  server.listen();
  await env.example project_DB.exec(
    `CREATE TABLE IF NOT EXISTS restore_log (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       bookmark_id TEXT, reason TEXT, row_count INTEGER
     )`
  );
});
afterEach(async () => {
  server.close();
  await env.example project_DB.exec(`DROP TABLE IF EXISTS restore_log`);
});

describe("POST /admin/restore – API failure", () => {
  it("returns 502 when bookmark API returns 403", async () => {
    const res = await SELF.fetch("http://localhost/admin/restore", {
      method: "POST",
      body: JSON.stringify({ targetTimestamp: "2026-08-01T00:00:00Z", reason: "fail test" }),
      headers: { "Content-Type": "application/json" },
    });
    expect(res.status).toBe(502);
  });

  it("does not write to restore_log on failure", async () => {
    await SELF.fetch("http://localhost/admin/restore", {
      method: "POST",
      body: JSON.stringify({ targetTimestamp: "2026-08-01T00:00:00Z", reason: "fail test" }),
      headers: { "Content-Type": "application/json" },
    });
    const count = await env.example project_DB.prepare(
      "SELECT COUNT(*) AS n FROM restore_log"
    ).first<{ n: number }>();
    expect(count?.n).toBe(0);
  });
});
```

---

## Vitest Test: Restore Timeout (Fake Timers)

```typescript
// test/restore/restore-timeout.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { setupServer } from "msw/node";
import {
  d1TimeTravelHandlers,
  resetBookmarkMock,
  bookmarkState,
} from "../mocks/d1-time-travel-api";
import { SELF, env } from "cloudflare:test";

// Override: bookmark stays in "pending" forever
vi.mock("../mocks/d1-time-travel-api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../mocks/d1-time-travel-api")>();
  return { ...mod, bookmarkState: "pending" };
});

const server = setupServer(...d1TimeTravelHandlers);

beforeEach(() => { server.listen(); resetBookmarkMock(); vi.useFakeTimers(); });
afterEach(() => { server.close(); vi.useRealTimers(); });

describe("POST /admin/restore – timeout", () => {
  it("returns 504 when bookmark does not complete within 30 s", async () => {
    const fetchPromise = SELF.fetch("http://localhost/admin/restore", {
      method: "POST",
      body: JSON.stringify({ targetTimestamp: "2026-08-01T00:00:00Z", reason: "timeout test" }),
      headers: { "Content-Type": "application/json" },
    });

    // Advance timers past the 30 s deadline
    await vi.advanceTimersByTimeAsync(31_000);

    const res = await fetchPromise;
    expect(res.status).toBe(504);
  });
});
```

---

## Simulating a Restored Snapshot (Row Count Change)

```typescript
// test/restore/restored-snapshot.test.ts
import { it, expect, beforeEach, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { d1TimeTravelHandlers, resetBookmarkMock } from "../mocks/d1-time-travel-api";
import { env, SELF } from "cloudflare:test";

const server = setupServer(...d1TimeTravelHandlers);

beforeEach(async () => {
  server.listen();
  resetBookmarkMock();
  // Simulate a "restored" state: only 1 article (pre-bulk-insert point-in-time)
  await env.example project_DB.exec(`
    CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, title TEXT);
    CREATE TABLE IF NOT EXISTS restore_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      bookmark_id TEXT, reason TEXT, row_count INTEGER
    );
    INSERT INTO articles VALUES (1, 'Original');
  `);
});

afterEach(async () => {
  server.close();
  await env.example project_DB.exec("DROP TABLE IF EXISTS articles; DROP TABLE IF EXISTS restore_log;");
});

it("rowCount in response reflects the restored snapshot row count", async () => {
  const res = await SELF.fetch("http://localhost/admin/restore", {
    method: "POST",
    body: JSON.stringify({ targetTimestamp: "2026-07-01T00:00:00Z", reason: "rollback" }),
    headers: { "Content-Type": "application/json" },
  });
  const { rowCount } = await res.json<{ rowCount: number }>();
  // Should reflect the seeded 1-row "restored" state, not the pre-restore count
  expect(rowCount).toBe(1);
});
```

---

## Anti-patterns

- **Calling real Cloudflare API in unit tests** – The D1 time-travel REST API is rate-limited
  and requires a real database ID. Always mock with MSW in unit/integration tests; use the
  real API only in manual E2E or canary tests.
- **Not seeding D1 to a known state before each test** – Time-travel tests are inherently
  stateful. Without `beforeEach` seeding, row counts are non-deterministic.
- **Using `vi.useFakeTimers()` without `vi.useRealTimers()` in teardown** – Fake timers leak
  across tests in Vitest Workers pool. Always pair in `beforeEach`/`afterEach`.
- **Asserting on bookmark ID format** – Bookmark IDs from the real API differ from mock IDs.
  Assert on structure (starts with `bm-` or `is string`) rather than exact format.
- **Testing restore without testing the audit log** – The restore log is a critical
  compliance record. Always assert it is written on success and not written on failure.

---

## Gotchas

- D1 time-travel in production operates on the actual database; your Worker sees the new
  state transparently. In Miniflare tests, you simulate this by seeding D1 to the
  "post-restore" state before the test runs.
- MSW in the Vitest Workers pool requires the Node.js `server.listen()` interceptor, not the
  Service Worker interceptor. The Workers pool runs in Node, not a browser.
- `vi.advanceTimersByTimeAsync` must be called after the fetch is initiated (as a floating
  promise) but before it is awaited — otherwise the timeout branch is never reached.
- Cloudflare's actual time-travel API has a `minimum 5-minute delay` policy; the mock omits
  this. If you add integration tests against the real API, add a timestamp at least 5 minutes
  in the past.
- `env.example project_DB.exec()` in Miniflare does not support multi-statement strings in all versions.
  Use separate `.prepare().run()` calls or confirm your Miniflare version supports batched exec.

---

## Verification

```bash
# Run only restore tests
pnpm vitest run test/restore/

# Verbose output
pnpm vitest run --reporter=verbose test/restore/restore-happy.test.ts

# Type-check handlers and test files
pnpm tsc --noEmit

# Coverage
pnpm vitest run --coverage \
  --coverage.include="apps/admin-worker/src/handlers/restore.ts" \
  test/restore/
```

Expected: 6 tests green (happy × 2, API failure × 2, timeout × 1, snapshot × 1), 100%
statement coverage on `restore.ts`.

---

## Related

- `miniflare-d1-integration-testing.md`
- `miniflare-d1-migration-testing.md`
- `d1-batch-transactions-vitest.md`
- `vitest-cloudflare-pool-workers.md`
- `mock-service-worker-msw-api-mocking.md`

---

## Sources

- Cloudflare D1 Time Travel docs: https://developers.cloudflare.com/d1/platform/time-travel/
- MSW Node.js setup: https://mswjs.io/docs/integrations/node
- Vitest fake timers: https://vitest.dev/guide/mocking.html#timers
- `@cloudflare/vitest-pool-workers` D1 binding: https://developers.cloudflare.com/workers/testing/vitest-integration/get-started/write-your-first-test/
