# k6 D1 Read Throughput Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker exposes a read-heavy API backed by D1 (SQLite). You need to quantify SELECT query throughput under concurrent load, detect index regression before production, and establish a P95 latency budget for read paths.

## Context

D1 is a globally-distributed SQLite database. Read operations involve a local SQLite engine running inside the Worker isolate; D1 uses a primary write path plus read replicas. Under high concurrency, bottlenecks emerge from query plan quality, missing indexes, and row serialisation cost. k6 can drive these read paths at scale, capturing per-query latency distributions and error rates.

The write-throughput article covers INSERT workloads. This article focuses exclusively on SELECT patterns: point lookups, range scans, joins, and paginated cursors.

---

## 1. Worker Under Test

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/users/lookup") {
      const id = url.searchParams.get("id");
      const row = await env.DB.prepare(
        "SELECT id, name, email FROM users WHERE id = ?"
      )
        .bind(id)
        .first();
      return Response.json(row ?? null, { status: row ? 200 : 404 });
    }

    if (path === "/users/page") {
      const cursor = Number(url.searchParams.get("cursor") ?? 0);
      const limit = 20;
      const rows = await env.DB.prepare(
        "SELECT id, name, email FROM users WHERE id > ? ORDER BY id LIMIT ?"
      )
        .bind(cursor, limit)
        .all();
      return Response.json({ rows: rows.results, next: rows.results.at(-1)?.id ?? null });
    }

    if (path === "/posts/search") {
      const tag = url.searchParams.get("tag") ?? "";
      const rows = await env.DB.prepare(
        `SELECT p.id, p.title, p.created_at
         FROM posts p
         JOIN post_tags pt ON pt.post_id = p.id
         WHERE pt.tag = ?
         ORDER BY p.created_at DESC
         LIMIT 50`
      )
        .bind(tag)
        .all();
      return Response.json(rows.results);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## 2. k6 Script — Point Lookup Throughput

```javascript
// k6/d1-read-point-lookup.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const lookupLatency = new Trend("d1_point_lookup_ms", true);
const errorRate = new Rate("d1_error_rate");

const BASE = __ENV.WORKER_URL ?? "https://my-worker.example.workers.dev";

// Pre-seeded user IDs — must exist in D1 before the run
const USER_IDS = Array.from({ length: 1000 }, (_, i) => i + 1);

export const options = {
  scenarios: {
    point_lookup: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 50 },
        { duration: "2m",  target: 200 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    d1_point_lookup_ms: ["p(95)<80", "p(99)<200"],
    d1_error_rate: ["rate<0.001"],
    http_req_failed: ["rate<0.001"],
  },
};

export default function () {
  const id = USER_IDS[Math.floor(Math.random() * USER_IDS.length)];
  const start = Date.now();
  const res = http.get(`${BASE}/users/lookup?id=${id}`);
  lookupLatency.add(Date.now() - start);

  const ok = check(res, {
    "status 200 or 404": (r) => r.status === 200 || r.status === 404,
    "response is json": (r) => r.headers["Content-Type"]?.includes("application/json"),
  });
  errorRate.add(!ok);

  sleep(0.05);
}
```

---

## 3. k6 Script — Paginated Cursor Scan

```javascript
// k6/d1-read-pagination.js
import http from "k6/http";
import { check } from "k6";
import { Trend, Counter } from "k6/metrics";

const pageLatency = new Trend("d1_page_scan_ms", true);
const rowsRead = new Counter("d1_rows_read_total");

const BASE = __ENV.WORKER_URL ?? "https://my-worker.example.workers.dev";

export const options = {
  scenarios: {
    pagination: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    d1_page_scan_ms: ["p(95)<150"],
    http_req_failed: ["rate<0.005"],
  },
};

export default function () {
  // Walk through a few pages per VU iteration to simulate real read patterns
  let cursor = Math.floor(Math.random() * 5000); // random starting point
  for (let page = 0; page < 3; page++) {
    const start = Date.now();
    const res = http.get(`${BASE}/users/page?cursor=${cursor}`);
    pageLatency.add(Date.now() - start);

    const ok = check(res, { "status 200": (r) => r.status === 200 });
    if (!ok) break;

    const body = res.json();
    rowsRead.add(body.rows?.length ?? 0);
    if (body.next == null) break;
    cursor = body.next;
  }
}
```

---

## 4. k6 Script — Join Query Throughput

```javascript
// k6/d1-read-join.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const joinLatency = new Trend("d1_join_query_ms", true);
const errorRate = new Rate("d1_join_error_rate");

const TAGS = ["typescript", "cloudflare", "workers", "d1", "kv", "r2", "ai"];
const BASE = __ENV.WORKER_URL ?? "https://my-worker.example.workers.dev";

export const options = {
  vus: 50,
  duration: "2m",
  thresholds: {
    d1_join_query_ms: ["p(95)<250", "p(99)<500"],
    d1_join_error_rate: ["rate<0.005"],
  },
};

export default function () {
  const tag = TAGS[Math.floor(Math.random() * TAGS.length)];
  const start = Date.now();
  const res = http.get(`${BASE}/posts/search?tag=${encodeURIComponent(tag)}`);
  joinLatency.add(Date.now() - start);

  errorRate.add(!check(res, { "status 200": (r) => r.status === 200 }));
  sleep(0.1);
}
```

---

## 5. CI Integration and Threshold Enforcement

```yaml
# .github/workflows/d1-read-load-test.yml
name: D1 Read Throughput Gate

on:
  pull_request:
    paths: ["src/**", "migrations/**"]

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: grafana/setup-k6-action@v1

      - name: Deploy preview Worker
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Seed D1 read fixtures
        run: npx wrangler d1 execute DB --env staging --file ./scripts/seed-read-fixtures.sql
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run point-lookup load test
        run: k6 run k6/d1-read-point-lookup.js
        env:
          WORKER_URL: ${{ secrets.STAGING_WORKER_URL }}

      - name: Run join query load test
        run: k6 run k6/d1-read-join.js
        env:
          WORKER_URL: ${{ secrets.STAGING_WORKER_URL }}
```

---

## Anti-patterns

- **Testing without indexes** — run `EXPLAIN QUERY PLAN SELECT …` in the D1 console before load testing; a full table scan will cap throughput far below index-backed performance.
- **Using `all()` when only one row is needed** — `.first()` is cheaper; the load test will mask the cost at low VU counts but expose it at 200+.
- **Shared cursor state across VUs** — mutable state leaks between k6 VU iterations on the same thread; always derive `cursor` from request-local state.
- **Seeding inside the k6 `setup()` function** — seeding hundreds of rows through the Worker's HTTP API during `setup()` is extremely slow; pre-seed via `wrangler d1 execute` instead.
- **Ignoring `meta.served_by`** — D1 exposes which replica served a query; correlate this with latency to detect primary vs. replica read distribution issues.

## Gotchas

- D1 primary is in one region; read replicas are rolled out globally but replication lag can surface stale rows during high write + concurrent read tests.
- `cursor`-based pagination is safe under concurrent load; `OFFSET`-based pagination degrades O(n) and will hit thresholds well before offset-cursor approaches.
- k6 `constant-arrival-rate` executor is more realistic for API load than `constant-vus` — it controls RPS not VU count.
- D1 row count limits per query default to 1000; queries returning more than that silently truncate; always assert `.rows.length < 1000` in checks.
- The `d1_rows_read` billing metric in the Cloudflare dashboard correlates directly with scan width; large joins under load can spike costs unexpectedly.

## Verification

```bash
# Check query plans before running load tests
npx wrangler d1 execute DB --command \
  "EXPLAIN QUERY PLAN SELECT id, name, email FROM users WHERE id = 1"

# Run point-lookup baseline (no load, confirm latency ceiling)
k6 run --vus 1 --duration 10s k6/d1-read-point-lookup.js

# Full staged ramp
k6 run k6/d1-read-point-lookup.js --out json=results/point-lookup.json

# Inspect percentiles
k6 inspect results/point-lookup.json | jq '.metrics.d1_point_lookup_ms'
```

## Related

- `k6-workers-d1-write-throughput-load-testing.md`
- `d1-test-fixtures-wrangler-seed.md`
- `vitest-workers-d1-schema-migration-testing.md`
- `k6-load-testing-cloudflare-workers-api.md`
- `performance-regression-testing-workers.md`

## Sources

- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/d1/best-practices/optimize-queries/
- https://k6.io/docs/using-k6/scenarios/executors/constant-arrival-rate/
- https://www.sqlite.org/eqp.html
