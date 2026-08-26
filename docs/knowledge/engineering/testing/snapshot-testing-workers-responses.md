# snapshot-testing-workers-responses

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

A example project Workers API refactor changes the casing of a JSON key
from `startsAt` to `starts_at`. All existing unit tests pass
because they only assert on status codes and selected fields.
The mobile app's data model breaks silently because no test
captured the full response structure. Three weeks later a QA
engineer notices the regression during manual testing. The team
needs a mechanism that detects structural JSON changes — added
keys, removed keys, changed types — without writing an assertion
for every single field.

## Context

Snapshot testing captures the full serialised output of a system
under test and stores it as a reference file (the snapshot). On
subsequent runs the output is compared against the stored reference;
any difference fails the test and shows a diff. For Cloudflare
Workers the snapshot is the HTTP response body — typically JSON.

Two complementary snapshot strategies apply to example project:

1. **Unit-level response snapshots** — the Worker handler is called
   directly in Vitest (with Miniflare bindings) and the JSON body
   is snapshot-tested. Fast, no network required.
2. **HTTP-level response snapshots** — a live request is sent to
   the staging Worker and the response body and headers are
   snapshot-tested. Slower, but catches serialisation middleware
   differences.

Both strategies maintain separate snapshots for mobile and desktop
response variants because the Worker returns different shapes
depending on the `x-client-platform` request header.

## Project Structure

```
workers/
  api/
    src/
      index.ts
    __tests__/
      snapshots/
        unit/
          __snapshots__/
            events-mobile.snap
            events-desktop.snap
          events-mobile.snap.spec.ts
          events-desktop.snap.spec.ts
        http/
          __snapshots__/
            events-http-mobile.snap
            events-http-desktop.snap
          events-http.snap.spec.ts
scripts/
  snapshot-update.sh         # wrapper for vitest --update-snapshots
```

## Unit-level Snapshot Test

The Worker is invoked via Wrangler's `unstable_dev` in the same
Miniflare isolate. The response JSON is normalised before
snapshotting to remove non-deterministic fields (timestamps,
generated IDs) so that the snapshot remains stable across runs.

```ts
// workers/api/__tests__/snapshots/unit/events-mobile.snap.spec.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';
import { createEvent } from '../../factories/event.factory.js';
import { cleanupTestRun } from '../../helpers/cleanup.js';
import { randomUUID } from 'node:crypto';

let worker: UnstableDevWorker;
const testRunId = randomUUID();

beforeAll(async () => {
  worker = await unstable_dev('src/index.ts', {
    experimental: { disableExperimentalWarning: true },
    vars: { ENVIRONMENT: 'test' },
  });

  const db = (worker as unknown as { env: { DB: D1Database } }).env.DB;
  await createEvent(db, testRunId, {
    title:            'Snapshot Fixture Event',
    starts_at:        '2026-09-01T18:00:00Z',
    preferred_layout: 'mobile',
    image_url:        'https://cdn.example.com/img/fixture.jpg',
  });
});

afterAll(async () => {
  const db = (worker as unknown as { env: { DB: D1Database } }).env.DB;
  await cleanupTestRun(db, testRunId);
  await worker.stop();
});

/** Replace non-deterministic values so snapshots are stable. */
function normalise(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(normalise);
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => {
        // Stable replacements for volatile fields
        if (k === 'id')        return [k, '<uuid>'];
        if (k === 'createdAt') return [k, '<timestamp>'];
        if (k === 'updatedAt') return [k, '<timestamp>'];
        if (k === 'cursor')    return [k, '<cursor>'];
        return [k, normalise(v)];
      })
    );
  }
  return obj;
}

describe('GET /api/events — mobile response snapshot', () => {
  it('matches the mobile response structure snapshot', async () => {
    const res  = await worker.fetch('/api/events', {
      headers: {
        Accept:               'application/json',
        'x-client-platform':  'mobile',
      },
    });

    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('application/json');

    const body = await res.json<unknown>();
    // Snapshot the normalised structure — stable across test runs
    expect(normalise(body)).toMatchSnapshot();
  });

  it('mobile response omits embedHtml field', async () => {
    const res  = await worker.fetch('/api/events', {
      headers: { 'x-client-platform': 'mobile' },
    });
    const body = await res.json<{ results: Array<Record<string, unknown>> }>();
    // Structural assertion to complement the snapshot
    expect(body.results[0]).not.toHaveProperty('embedHtml');
  });
});
```

```ts
// workers/api/__tests__/snapshots/unit/events-desktop.snap.spec.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';
import { createEvent } from '../../factories/event.factory.js';
import { cleanupTestRun } from '../../helpers/cleanup.js';
import { randomUUID } from 'node:crypto';

let worker: UnstableDevWorker;
const testRunId = randomUUID();

beforeAll(async () => {
  worker = await unstable_dev('src/index.ts', {
    experimental: { disableExperimentalWarning: true },
    vars: { ENVIRONMENT: 'test' },
  });
  const db = (worker as unknown as { env: { DB: D1Database } }).env.DB;
  await createEvent(db, testRunId, {
    title:            'Snapshot Fixture Event',
    starts_at:        '2026-09-01T18:00:00Z',
    preferred_layout: 'desktop',
  });
});

afterAll(async () => {
  const db = (worker as unknown as { env: { DB: D1Database } }).env.DB;
  await cleanupTestRun(db, testRunId);
  await worker.stop();
});

function normalise(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(normalise);
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => {
        if (k === 'id')        return [k, '<uuid>'];
        if (k === 'createdAt') return [k, '<timestamp>'];
        if (k === 'cursor')    return [k, '<cursor>'];
        return [k, normalise(v)];
      })
    );
  }
  return obj;
}

describe('GET /api/events — desktop response snapshot', () => {
  it('matches the desktop response structure snapshot', async () => {
    const res  = await worker.fetch('/api/events', {
      headers: {
        Accept:               'application/json',
        'x-client-platform':  'desktop',
      },
    });

    expect(res.status).toBe(200);
    const body = await res.json<unknown>();
    expect(normalise(body)).toMatchSnapshot();
  });

  it('desktop response includes embedHtml field', async () => {
    const res  = await worker.fetch('/api/events', {
      headers: { 'x-client-platform': 'desktop' },
    });
    const body = await res.json<{ results: Array<Record<string, unknown>> }>();
    expect(body.results[0]).toHaveProperty('embedHtml');
  });
});
```

## HTTP-level Snapshot Test

The HTTP-level snapshot test sends a real request to the staging
Worker and captures the response. This catches differences in
serialisation middleware, CORS headers, and caching headers
that unit tests with Miniflare may not surface:

```ts
// workers/api/__tests__/snapshots/http/events-http.snap.spec.ts
import { describe, it, expect } from 'vitest';

const BASE = process.env.SNAPSHOT_WORKER_URL
  ?? 'https://staging.example project.workers.dev';

function normalise(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(normalise);
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => {
        if (k === 'id')        return [k, '<uuid>'];
        if (k === 'createdAt') return [k, '<timestamp>'];
        if (k === 'cursor')    return [k, '<cursor>'];
        return [k, normalise(v)];
      })
    );
  }
  return obj;
}

describe('HTTP snapshot — staging Worker', () => {
  it('mobile response shape matches snapshot', async () => {
    const res  = await fetch(`${BASE}/api/events`, {
      headers: {
        Accept:               'application/json',
        'x-client-platform':  'mobile',
      },
    });

    expect(res.status).toBe(200);
    const body = await res.json<unknown>();
    expect(normalise(body)).toMatchSnapshot();
  });

  it('desktop response shape matches snapshot', async () => {
    const res  = await fetch(`${BASE}/api/events`, {
      headers: {
        Accept:               'application/json',
        'x-client-platform':  'desktop',
      },
    });

    expect(res.status).toBe(200);
    const body = await res.json<unknown>();
    expect(normalise(body)).toMatchSnapshot();
  });

  it('response includes expected CORS and cache headers', async () => {
    const res = await fetch(`${BASE}/api/events`, {
      headers: { Accept: 'application/json' },
    });

    expect(res.headers.get('access-control-allow-origin')).toBe('*');
    expect(res.headers.get('cache-control')).toMatchSnapshot();
    expect(res.headers.get('cf-cache-status')).toMatchSnapshot();
  });
});
```

## Normalisation Reference

Non-deterministic fields that must always be normalised before
snapshotting to prevent spurious failures:

| Field | Replacement | Reason |
|-------|-------------|--------|
| `id` | `<uuid>` | Generated per row |
| `createdAt` / `created_at` | `<timestamp>` | Changes on each insert |
| `updatedAt` / `updated_at` | `<timestamp>` | Changes on each update |
| `cursor` | `<cursor>` | Pagination cursor is opaque |
| `requestId` | `<request-id>` | Cloudflare-assigned per request |
| `ray` / `cf-ray` | `<ray>` | Cloudflare Ray ID in headers |

Fields that must NOT be normalised — they carry structural meaning:

- Field names (keys) — renaming is a regression.
- Field types — `string` vs `number` is a regression.
- Nullability — `null` vs `undefined` vs missing key is a regression.
- Array vs object — structural regressions must be visible.

## Snapshot Update Workflow

```bash
# Update ALL snapshots (use after an intentional schema change)
npx vitest run --update-snapshots \
  workers/api/__tests__/snapshots/

# Update only the mobile unit snapshot
npx vitest run --update-snapshots \
  workers/api/__tests__/snapshots/unit/events-mobile.snap.spec.ts

# Review the diff before committing
git diff workers/api/__tests__/snapshots/unit/__snapshots__/
```

Always review the diff in the snapshot file before committing an
update. The key questions:

1. Was the change intentional?
2. Is the diff in the right direction (a new field added vs an
   existing field removed)?
3. Does the mobile snapshot and the desktop snapshot both reflect
   the intended change correctly?

## CI Integration

```yaml
# .github/workflows/snapshots.yml
name: Snapshot tests
on:
  pull_request:
    branches: [main]

jobs:
  unit-snapshots:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm ci
      - name: Unit snapshot tests (Miniflare)
        run: |
          npx vitest run \
            workers/api/__tests__/snapshots/unit/

  http-snapshots:
    runs-on: ubuntu-latest
    needs: unit-snapshots
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm ci
      - name: HTTP snapshot tests (staging)
        env:
          SNAPSHOT_WORKER_URL: ${{ vars.STAGING_WORKER_URL }}
        run: |
          npx vitest run \
            workers/api/__tests__/snapshots/http/
```

## Mobile vs Desktop Snapshot Diff Example

After a refactor that incorrectly removes the `imageUrl` field
from the mobile response, Vitest shows:

```diff
  - Snapshot
  + Received

  Object {
    "results": Array [
      Object {
        "id": "<uuid>",
        "title": "Snapshot Fixture Event",
        "startsAt": "2026-09-01T18:00:00Z",
-       "imageUrl": "https://cdn.example.com/img/fixture.jpg",
        "venue": Object {
          "name": "The O2 Arena",
        },
      },
    ],
    "meta": Object {
      "total": 1,
      "cursor": "<cursor>",
    },
  }
```

The removal of `imageUrl` in the mobile snapshot immediately
surfaces the regression. The desktop snapshot, which does not
include `imageUrl` in its expected shape, is unaffected and
continues to pass, confirming that the bug is mobile-path specific.

## Anti-patterns

- Snapshotting raw unstabilised JSON with real UUIDs and timestamps —
  the snapshot will fail on the next run even when the structure
  did not change. Always normalise volatile fields.
- Treating a failing snapshot as an automatic update — `--update-snapshots`
  should only be run when the diff represents an intentional change.
  A CI job must never pass `--update-snapshots`; updates are a
  deliberate developer action.
- Using a single shared snapshot file for both mobile and desktop
  responses — a change to the mobile shape will break the desktop
  snapshot test, creating a misleading failure attribution.
- Snapshotting every endpoint response — large snapshot files
  that capture rarely-changing data add noise and slow reviews.
  Snapshot the structural shape of key API responses, not every
  endpoint.
- Omitting the normalise step for nested objects — a nested
  `venue.id` field will contain a real UUID and cause spurious
  failures just as much as a top-level `id`.

## Gotchas

- Vitest's `toMatchSnapshot` stores snapshots in a
  `__snapshots__` directory adjacent to the test file. The
  snapshot filename mirrors the test file name with a `.snap`
  suffix. Commit these files to the repository.
- When a test is renamed, the old snapshot key becomes an
  obsolete snapshot. Run `npx vitest --update-snapshots` once
  after renaming tests to prune obsolete keys.
- HTTP-level snapshots against a staging Worker may include
  Cloudflare-managed response headers (`cf-ray`, `server: cloudflare`)
  that change on every request. Snapshot headers selectively —
  only the headers your application code controls.
- `toMatchSnapshot` is not the same as `toMatchInlineSnapshot` —
  the latter embeds the snapshot inline in the test file, which
  is ergonomic for small payloads but becomes unreadable for
  deeply nested JSON. Use file-based snapshots for API responses.

## Verification

```bash
# Run all snapshot tests; confirm zero failures
npx vitest run workers/api/__tests__/snapshots/

# Confirm no obsolete snapshot keys
npx vitest run --update-snapshots \
  workers/api/__tests__/snapshots/
git diff --stat workers/api/__tests__/snapshots/unit/__snapshots__/
# Should show no changes if all snapshots are up to date
```

## Related

- `testing/snapshot-testing-best-practices.md`
- `testing/snapshot-testing-pitfalls.md`
- `testing/jest-snapshot-testing.md`
- `testing/test-data-management-d1-factories.md`
- `testing/workers-unit-testing-fetch-mocking.md`

## Source URLs (verified 2026-08-22)

- https://vitest.dev/guide/snapshot
- https://developers.cloudflare.com/workers/wrangler/api/#unstable_dev
- https://developers.cloudflare.com/workers/testing/miniflare/
- https://vitest.dev/api/expect#tomatchsnapshot
