# k6 Workers API Pagination Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker exposes a paginated list endpoint (cursor- or offset-based).
Under load, users report stale cursors, duplicated rows, and response-time spikes
at page boundaries. You need a k6 script that:

1. Drives realistic multi-page traversal at concurrent VU levels.
2. Asserts cursor integrity (no gaps, no duplicates) across pages.
3. Identifies latency regressions at deep page depths.
4. Produces per-page percentile metrics visible in Grafana Cloud k6.

---

## Context

Pagination on Workers typically uses one of three schemes:

| Scheme | Cursor shape | D1 idiom |
|---|---|---|
| Keyset / cursor | opaque base64 token | `WHERE id > :last_id` |
| Offset | `?page=N&limit=M` | `LIMIT M OFFSET N*M` |
| Link-header | RFC 5988 `next` rel | any |

Keyset pagination is preferred for Workers + D1 because offset scans are O(N)
in D1. This article demonstrates keyset testing; offset variants follow the
same structure with a simpler cursor decoder.

---

## Worker Under Test (Reference)

```ts
// src/worker.ts — abbreviated
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const cursor = url.searchParams.get('cursor') ?? null;
    const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20'), 100);

    let rows: { id: number; name: string }[];
    if (cursor) {
      const lastId = parseInt(atob(cursor), 10);
      const stmt = env.DB.prepare(
        'SELECT id, name FROM items WHERE id > ? ORDER BY id LIMIT ?'
      );
      rows = await stmt.bind(lastId, limit).all().then((r) => r.results as typeof rows);
    } else {
      const stmt = env.DB.prepare('SELECT id, name FROM items ORDER BY id LIMIT ?');
      rows = await stmt.bind(limit).all().then((r) => r.results as typeof rows);
    }

    const nextCursor =
      rows.length === limit ? btoa(String(rows[rows.length - 1].id)) : null;

    return Response.json({ items: rows, nextCursor });
  },
};
```

---

## k6 Script: `pagination-load.js`

```js
// k6-scripts/pagination-load.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// ── Custom metrics ──────────────────────────────────────────────────────────
const paginationErrors = new Counter('pagination_errors');
const cursorMissing    = new Rate('cursor_missing_rate');
const pageDepthTrend   = new Trend('page_depth', true);
const itemsPerRequest  = new Trend('items_per_request', true);

// ── Options ─────────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    shallow_pages: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
      env: { MAX_PAGES: '3', PAGE_LIMIT: '20' },
      tags: { scenario: 'shallow' },
    },
    deep_pages: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '90s', target: 10 },
        { duration: '30s', target: 0 },
      ],
      env: { MAX_PAGES: '20', PAGE_LIMIT: '20' },
      tags: { scenario: 'deep' },
    },
    burst_first_page: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 50,
      maxVUs: 100,
      env: { MAX_PAGES: '1', PAGE_LIMIT: '100' },
      tags: { scenario: 'burst_first' },
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1500'],
    'http_req_duration{scenario:deep}': ['p(95)<800'],
    pagination_errors: ['count<5'],
    cursor_missing_rate: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.WORKER_URL ?? 'https://api.example.com';

// ── VU logic ─────────────────────────────────────────────────────────────────
export default function () {
  const maxPages  = parseInt(__ENV.MAX_PAGES  ?? '5',  10);
  const pageLimit = parseInt(__ENV.PAGE_LIMIT ?? '20', 10);

  let cursor    = null;
  let pageIndex = 0;
  const seenIds = new Set();

  while (pageIndex < maxPages) {
    const url = buildUrl(cursor, pageLimit);
    const res = http.get(url, {
      headers: { 'Accept': 'application/json' },
      tags: { page_depth: String(pageIndex) },
    });

    const ok = check(res, {
      'status is 200':        (r) => r.status === 200,
      'has items array':      (r) => Array.isArray(r.json('items')),
      'items not empty':      (r) => r.json('items').length > 0,
      'no duplicate IDs':     (r) => {
        const items = r.json('items');
        return items.every((item) => {
          if (seenIds.has(item.id)) return false;
          seenIds.add(item.id);
          return true;
        });
      },
      'items count <= limit': (r) => r.json('items').length <= pageLimit,
    });

    if (!ok) {
      paginationErrors.add(1);
    }

    pageDepthTrend.add(pageIndex);
    itemsPerRequest.add((res.json('items') ?? []).length);

    const nextCursor = res.json('nextCursor');
    if (!nextCursor) {
      // Reached the last page — valid terminal state
      cursorMissing.add(pageIndex < maxPages - 1 ? 1 : 0);
      break;
    }

    cursor = nextCursor;
    pageIndex++;
    sleep(0.1); // courtesy pause between pages
  }
}

function buildUrl(cursor, limit) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  return `${BASE_URL}/items?${params}`;
}
```

---

## Cursor Integrity Checker (Separate Smoke Script)

Run this as a pre-load smoke test to verify the API is semantically correct
before hammering it with hundreds of VUs.

```js
// k6-scripts/pagination-smoke.js
import http from 'k6/http';
import { check, fail } from 'k6';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: { checks: ['rate==1.0'] },
};

const BASE_URL = __ENV.WORKER_URL ?? 'https://api.example.com';
const LIMIT     = 10;
const MAX_PAGES = 50; // guard against infinite loop if nextCursor never clears

export default function () {
  let cursor    = null;
  let page      = 0;
  const allIds  = [];

  while (page < MAX_PAGES) {
    const params = new URLSearchParams({ limit: String(LIMIT) });
    if (cursor) params.set('cursor', cursor);

    const res  = http.get(`${BASE_URL}/items?${params}`);
    const body = res.json();

    check(res, { [`page ${page} status 200`]: (r) => r.status === 200 });

    const ids = (body.items ?? []).map((i) => i.id);
    allIds.push(...ids);

    cursor = body.nextCursor ?? null;
    page++;

    if (!cursor) break;
  }

  // Assert no duplicates across all pages
  const unique = new Set(allIds);
  if (unique.size !== allIds.length) {
    fail(`Duplicate IDs detected: ${allIds.length} total, ${unique.size} unique`);
  }

  // Assert IDs are monotonically increasing (keyset guarantee)
  for (let i = 1; i < allIds.length; i++) {
    if (allIds[i] <= allIds[i - 1]) {
      fail(`Non-monotonic IDs at index ${i}: ${allIds[i - 1]} then ${allIds[i]}`);
    }
  }

  console.log(`Traversed ${page} pages, ${allIds.length} unique items — OK`);
}
```

---

## Running the Scripts

```bash
# 1. Smoke test first
k6 run \
  --env WORKER_URL=https://your-worker.your-domain.workers.dev \
  k6-scripts/pagination-smoke.js

# 2. Full load test
k6 run \
  --env WORKER_URL=https://your-worker.your-domain.workers.dev \
  --out json=results/pagination-load.json \
  k6-scripts/pagination-load.js

# 3. Stream to Grafana Cloud k6
k6 run \
  --env WORKER_URL=https://your-worker.your-domain.workers.dev \
  -o cloud \
  k6-scripts/pagination-load.js
```

---

## CI Integration (GitHub Actions)

```yaml
# .github/workflows/pagination-load.yml
name: Pagination Load Test
on:
  push:
    branches: [main]

jobs:
  k6-pagination:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: grafana/setup-k6-action@v1
      - name: Smoke test
        run: |
          k6 run \
            --env WORKER_URL=${{ vars.STAGING_WORKER_URL }} \
            k6-scripts/pagination-smoke.js
      - name: Load test
        run: |
          k6 run \
            --env WORKER_URL=${{ vars.STAGING_WORKER_URL }} \
            --out json=pagination-results.json \
            k6-scripts/pagination-load.js
      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: k6-pagination-results
          path: pagination-results.json
```

---

## Anti-patterns

- **Using offset pagination for load testing** — D1 offset scans are O(N); deep
  offsets will show escalating latency that is an implementation problem, not a
  load-testing problem. Fix the API first.
- **Not seeding test data** — if the database is empty the test always hits one
  page and exits trivially. Seed at least `MAX_PAGES * PAGE_LIMIT * 2` rows.
- **Asserting cursor format in the load test** — cursor encoding is an
  implementation detail. Assert presence/absence only; decode in smoke tests.
- **Sharing cursor state across VUs** — each VU must maintain its own cursor
  chain. Global `let cursor` shared across VUs is a race condition.

---

## Gotchas

- Workers enforce a CPU time budget per request. Deep keyset queries on D1 can
  approach the limit when the table is large and unindexed — add `CREATE INDEX
  items_id ON items(id)`.
- `__ENV` variables in k6 are strings. Always parse with `parseInt`/`parseFloat`
  before arithmetic.
- The `constant-arrival-rate` scenario spawns new VUs if iteration duration
  exceeds the rate interval — cap `maxVUs` or the Cloudflare account's connection
  limits will be hit.
- k6 `check()` does not abort the iteration on failure. Wrap abort logic in
  `fail()` only for the smoke script where correctness gates the load run.
- When running against a deployed Worker, Cloudflare's 100 ms CPU limit applies.
  The staging environment should have the same limits as production.

---

## Verification

After the load run, inspect `pagination-results.json`:

```bash
# p95 latency per scenario
cat pagination-results.json \
  | jq 'select(.type=="Point" and .metric=="http_req_duration") | .data' \
  | jq -s 'group_by(.tags.scenario)
    | map({scenario: .[0].tags.scenario, p95: (map(.value) | sort | .[length * 0.95 | floor])})'

# total pagination errors
cat pagination-results.json \
  | jq 'select(.type=="Point" and .metric=="pagination_errors") | .data.value' \
  | jq -s 'add'
```

Both thresholds should pass: `p(95)<500` and `pagination_errors count<5`.

---

## Related

- `k6-load-testing-cloudflare-workers-api.md`
- `k6-workers-d1-write-throughput-load-testing.md`
- `k6-workers-rate-limiter-load-test.md`
- `d1-test-fixtures-wrangler-seed.md`
- `vitest-workers-env-var-override-testing.md`

---

## Sources

- k6 documentation: https://grafana.com/docs/k6/latest/
- k6 custom metrics: https://grafana.com/docs/k6/latest/using-k6/metrics/create-custom-metrics/
- Cloudflare D1 keyset pagination: https://developers.cloudflare.com/d1/examples/
- Grafana k6 Cloud output: https://grafana.com/docs/k6/latest/results-output/real-time/cloud/
