# test-data-management-d1-factories

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project integration tests against D1 fail intermittently because
tests insert rows without cleanup and the next test run finds
stale data that changes its outcome. A test that verifies
"an empty events list returns an empty array" fails when a
previous test left three rows in the database. Mobile-specific
tests that expect a compact response payload receive the full
desktop payload because both tests share the same fixture row
without a `platform` discriminator. There is no factory layer —
tests hard-code INSERT statements that fall out of sync when the
D1 schema changes.

## Context

The factory pattern wraps row construction behind typed builder
functions. Factories have sensible defaults for every column and
accept overrides for the fields that matter to a specific test.
A `cleanup` strategy — transactional rollback, truncation, or
row-level delete by a test-run ID — ensures that tests do not
bleed state into each other.

For example project + D1 the recommended approach uses:

- **Factories** — `createEvent`, `createUser`, etc., each returns
  the inserted row with its generated ID.
- **Test-run isolation** — each test suite seeds rows tagged with
  a `testRunId` UUIDv4. Cleanup deletes only rows with that ID.
- **Wrangler's `unstable_dev` binding** — factories run inside the
  same Miniflare context as the Worker under test, hitting the
  same in-memory D1 database.
- **Mobile vs desktop variants** — factories accept a `platform`
  parameter that sets the `preferred_layout` column, driving the
  Worker's conditional response shaping.

## Project Structure

```
workers/
  api/
    src/
      db/
        schema.ts              # D1 table definitions (Drizzle or raw SQL)
    __tests__/
      factories/
        index.ts               # re-export all factories
        event.factory.ts
        user.factory.ts
        ticket.factory.ts
      helpers/
        test-db.ts             # unstable_dev + factory bootstrap
        cleanup.ts             # row-level cleanup helpers
      integration/
        events.test.ts         # example integration test using factories
```

## Factory Implementation

```ts
// workers/api/__tests__/factories/event.factory.ts
import type { D1Database } from '@cloudflare/workers-types';
import { randomUUID }       from 'node:crypto';

export interface EventRow {
  id:               string;
  title:            string;
  description:      string;
  starts_at:        string;
  venue_id:         string | null;
  image_url:        string | null;
  preferred_layout: 'mobile' | 'desktop' | 'adaptive';
  published:        1 | 0;
  test_run_id:      string;
  created_at:       string;
}

export type EventOverrides = Partial<Omit<EventRow, 'id' | 'created_at'>>;

/**
 * Insert one event row into D1 and return the full row.
 *
 * @param db         The D1Database binding from the Miniflare context.
 * @param testRunId  UUID that identifies the current test run.
 *                   Used for cleanup — only rows with this ID are deleted.
 * @param overrides  Column values that override the defaults.
 */
export async function createEvent(
  db: D1Database,
  testRunId: string,
  overrides: EventOverrides = {}
): Promise<EventRow> {
  const id  = randomUUID();
  const now = new Date().toISOString();

  const row: EventRow = {
    id,
    title:            `Test Event ${id.slice(0, 8)}`,
    description:      'A fixture event created by the test factory.',
    starts_at:        '2026-09-01T18:00:00Z',
    venue_id:         null,
    image_url:        'https://cdn.example.com/img/fixture.jpg',
    preferred_layout: 'adaptive',
    published:        1,
    test_run_id:      testRunId,
    created_at:       now,
    ...overrides,
  };

  await db
    .prepare(
      `INSERT INTO events
         (id, title, description, starts_at, venue_id,
          image_url, preferred_layout, published,
          test_run_id, created_at)
       VALUES
         (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      row.id, row.title, row.description, row.starts_at,
      row.venue_id, row.image_url, row.preferred_layout,
      row.published, row.test_run_id, row.created_at
    )
    .run();

  return row;
}

/** Create N events, optionally each with incremented `starts_at`. */
export async function createEvents(
  db: D1Database,
  testRunId: string,
  count: number,
  overrides: EventOverrides = {}
): Promise<EventRow[]> {
  const base = new Date(overrides.starts_at ?? '2026-09-01T18:00:00Z');
  const rows: EventRow[] = [];

  for (let i = 0; i < count; i++) {
    const startsAt = new Date(base.getTime() + i * 3_600_000).toISOString();
    rows.push(
      await createEvent(db, testRunId, { ...overrides, starts_at: startsAt })
    );
  }

  return rows;
}
```

```ts
// workers/api/__tests__/factories/user.factory.ts
import type { D1Database } from '@cloudflare/workers-types';
import { randomUUID }       from 'node:crypto';

export interface UserRow {
  id:          string;
  email:       string;
  platform:    'mobile' | 'desktop';
  test_run_id: string;
  created_at:  string;
}

export async function createUser(
  db: D1Database,
  testRunId: string,
  overrides: Partial<Omit<UserRow, 'id' | 'created_at'>> = {}
): Promise<UserRow> {
  const id  = randomUUID();
  const row: UserRow = {
    id,
    email:       `test+${id.slice(0, 8)}@example.com`,
    platform:    'desktop',
    test_run_id: testRunId,
    created_at:  new Date().toISOString(),
    ...overrides,
  };

  await db
    .prepare(
      `INSERT INTO users (id, email, platform, test_run_id, created_at)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(row.id, row.email, row.platform, row.test_run_id, row.created_at)
    .run();

  return row;
}
```

## Cleanup Helpers

```ts
// workers/api/__tests__/helpers/cleanup.ts
import type { D1Database } from '@cloudflare/workers-types';

const TABLES_WITH_TEST_RUN = [
  'tickets',
  'events',
  'users',
] as const;

/**
 * Delete all rows inserted by the given test run from every table
 * that carries a `test_run_id` column. Call in `afterEach` or
 * `afterAll` depending on desired isolation granularity.
 */
export async function cleanupTestRun(
  db: D1Database,
  testRunId: string
): Promise<void> {
  // Reverse table order to respect foreign-key constraints
  for (const table of [...TABLES_WITH_TEST_RUN].reverse()) {
    await db
      .prepare(`DELETE FROM ${table} WHERE test_run_id = ?`)
      .bind(testRunId)
      .run();
  }
}
```

## Test-run Bootstrap Helper

```ts
// workers/api/__tests__/helpers/test-db.ts
import { randomUUID }       from 'node:crypto';
import { unstable_dev }     from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';
import { cleanupTestRun }   from './cleanup.js';
import * as factories       from '../factories/index.js';

export interface TestContext {
  worker:     UnstableDevWorker;
  db:         D1Database;
  testRunId:  string;
  factories:  typeof factories;
  cleanup:    () => Promise<void>;
}

export async function setupTestDb(): Promise<TestContext> {
  const testRunId = randomUUID();

  const worker = await unstable_dev('src/index.ts', {
    experimental: { disableExperimentalWarning: true },
    vars: { ENVIRONMENT: 'test' },
  });

  // Access the D1 binding directly from the dev worker
  const db = (worker as unknown as { env: { DB: D1Database } }).env.DB;

  return {
    worker,
    db,
    testRunId,
    factories,
    cleanup: () => cleanupTestRun(db, testRunId),
  };
}
```

## Integration Test: Mobile vs Desktop Data

```ts
// workers/api/__tests__/integration/events.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { setupTestDb, type TestContext } from '../helpers/test-db.js';

describe('GET /api/events', () => {
  let ctx: TestContext;

  beforeAll(async () => {
    ctx = await setupTestDb();
  });

  afterAll(async () => {
    await ctx.cleanup();
    await ctx.worker.stop();
  });

  it('returns an empty list when no events exist for this test run', async () => {
    // No factory calls — database is empty for this test run
    const res  = await ctx.worker.fetch('/api/events');
    const body = await res.json<{ results: unknown[] }>();
    expect(res.status).toBe(200);
    expect(body.results).toHaveLength(0);
  });

  it('returns mobile-compact payload for mobile events', async () => {
    await ctx.factories.createEvent(ctx.db, ctx.testRunId, {
      preferred_layout: 'mobile',
      title: 'Mobile Test Event',
    });

    const res  = await ctx.worker.fetch('/api/events', {
      headers: { 'x-client-platform': 'mobile' },
    });
    const body = await res.json<{ results: Array<Record<string, unknown>> }>();

    expect(res.status).toBe(200);
    expect(body.results[0]).toHaveProperty('imageUrl');
    // Mobile payload omits the full venue embed
    expect(body.results[0]).not.toHaveProperty('embedHtml');
  });

  it('returns desktop-full payload for desktop events', async () => {
    await ctx.factories.createEvent(ctx.db, ctx.testRunId, {
      preferred_layout: 'desktop',
      title: 'Desktop Test Event',
    });

    const res  = await ctx.worker.fetch('/api/events', {
      headers: { 'x-client-platform': 'desktop' },
    });
    const body = await res.json<{ results: Array<Record<string, unknown>> }>();

    expect(res.status).toBe(200);
    // Desktop payload includes the full venue embed
    expect(body.results[0]).toHaveProperty('embedHtml');
  });

  it('returns multiple events ordered by starts_at asc', async () => {
    await ctx.factories.createEvents(ctx.db, ctx.testRunId, 3);

    const res  = await ctx.worker.fetch('/api/events?sort=asc');
    const body = await res.json<{ results: Array<{ startsAt: string }> }>();

    expect(body.results.length).toBeGreaterThanOrEqual(3);
    // Verify ordering
    for (let i = 1; i < body.results.length; i++) {
      expect(body.results[i].startsAt >= body.results[i - 1].startsAt).toBe(true);
    }
  });
});
```

## Mobile vs Desktop Test Data Differences

| Dimension | Mobile factory default | Desktop factory default |
|-----------|------------------------|------------------------|
| `preferred_layout` | `'mobile'` | `'desktop'` |
| `image_url` | Always set (required for mobile card) | Optional |
| Description length | Truncated at 120 chars | Full text |
| Venue data | `venue_id` only (no join) | Full venue join expected |
| Response assertion | No `embedHtml` field | `embedHtml` field present |

Use `createEvent(db, runId, { preferred_layout: 'mobile' })` for
mobile-path tests and `{ preferred_layout: 'desktop' }` for
desktop-path tests. The `adaptive` default triggers the Worker
to select the layout based on the `x-client-platform` header.

## Cleanup Strategies Comparison

| Strategy | How | Isolation level | Speed | Risk |
|----------|-----|-----------------|-------|------|
| `test_run_id` DELETE | Delete rows WHERE test_run_id = ? | Per test suite | Fast | Low — only deletes own rows |
| TRUNCATE | `DELETE FROM table` (SQLite = TRUNCATE) | Global | Fastest | High — wipes all data |
| Schema reset | Drop and re-create tables | Global | Slow | High — requires migration rerun |
| Transactional rollback | Wrap test in transaction, roll back | Per test | Fast | Medium — D1 has limited txn support |

The `test_run_id` DELETE strategy is recommended for D1 because
D1's SQLite dialect does not support `ROLLBACK` from application
code outside of explicit `db.batch()` transactions, and DDL-level
resets are expensive in CI.

## Anti-patterns

- Sharing a single `testRunId` across unrelated test files —
  parallel test workers will delete each other's rows during cleanup.
  Generate a new UUID per test file (in `beforeAll`), not per suite.
- Hard-coding row IDs in factory defaults — two parallel test
  workers inserting the same ID will cause a UNIQUE constraint
  violation. Always use `randomUUID()` for primary keys.
- Calling `cleanupTestRun` in `beforeAll` instead of `afterAll` —
  cleanup before a test cannot clean rows that failed to clean up
  in a previous run if the test run crashed. Use `afterAll` with
  a try/finally guard.
- Building fixture rows with INSERT … SELECT from existing data —
  the factory then depends on production-like data being present,
  coupling tests to the seeding order.
- Omitting the `test_run_id` column from the D1 schema — add it
  as a non-null TEXT column with a default of `''` so that legacy
  cleanup queries do not match accidental empty strings.

## Gotchas

- `unstable_dev` creates an in-memory D1 instance; the database is
  empty on every test run. Do not assume any rows exist unless a
  factory inserted them.
- `db.batch()` is the D1 equivalent of a transaction for multiple
  INSERT statements. Use it in `createEvents` for atomic multi-row
  inserts to avoid partial-write failures.
- Accessing `worker.env.DB` directly requires casting because the
  TypeScript type of `unstable_dev` does not expose the `env` field.
  This is an internal implementation detail — it may change in a
  future Wrangler release.
- D1's foreign-key enforcement is disabled by default in SQLite.
  Enable it in the test schema with `PRAGMA foreign_keys = ON` if
  the cleanup order matters for referential integrity.

## Verification

```bash
# Run integration tests with verbose output
npx vitest run --reporter=verbose \
  workers/api/__tests__/integration/events.test.ts

# Confirm no test_run_id rows are left after the run
# (requires a local D1 inspector; substitute with wrangler d1 execute)
wrangler d1 execute example project-local \
  --command "SELECT COUNT(*) FROM events WHERE test_run_id != ''" \
  --local
```

## Related

- `testing/d1-test-fixtures-wrangler-seed.md`
- `testing/d1-testing-local.md`
- `testing/miniflare-d1-integration-testing.md`
- `testing/factory-pattern-tests.md`
- `testing/test-database-isolation.md`
- `testing/database-seeding-tests.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/d1/reference/d1-client-api/
- https://developers.cloudflare.com/workers/wrangler/api/#unstable_dev
- https://developers.cloudflare.com/d1/reference/transactions/
- https://vitest.dev/api/#beforeall
