# Zero-Downtime Migration Strategy: Monolithic API to Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to migrate a monolithic origin API to Cloudflare Workers incrementally, endpoint by endpoint, with the ability to roll back any endpoint to the origin in under 60 seconds without a code deployment.

## Context

The strangler-fig pattern routes a configurable percentage of traffic to the new Workers backend. A KV flag (`migration_pct`) controls the split. A Tail Worker samples both responses in parallel and writes diffs to D1 for confidence-building. When all endpoints are validated, a final cutover removes the origin.

Components:
- **Proxy Worker**: reads `migration_pct` from KV, routes traffic
- **Tail Worker**: samples parallel responses and logs diffs to D1
- **D1 tables**: `migration_endpoints`, `response_diffs`
- **KV namespace**: `MIGRATION_FLAGS`
- **New backend**: a separate Worker or Workers service binding

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS migration_endpoints (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  path           TEXT    NOT NULL UNIQUE,
  migrated_at    TEXT,
  migration_pct  INTEGER NOT NULL DEFAULT 0,   -- 0-100
  rollback_count INTEGER NOT NULL DEFAULT 0,
  notes          TEXT
);

CREATE TABLE IF NOT EXISTS response_diffs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  path          TEXT    NOT NULL,
  sampled_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  origin_status INTEGER,
  worker_status INTEGER,
  body_match    INTEGER NOT NULL DEFAULT 0,   -- 0=mismatch, 1=match
  origin_ms     INTEGER,
  worker_ms     INTEGER,
  diff_summary  TEXT
);

CREATE INDEX idx_response_diffs_path ON response_diffs(path, sampled_at);
```

---

## Proxy Worker: Traffic Splitting

```typescript
// src/proxy.ts
export interface Env {
  MIGRATION_FLAGS: KVNamespace;
  NEW_BACKEND:     Fetcher;          // service binding to new Workers backend
  ORIGIN_URL:      string;           // legacy origin, e.g. https://api.legacy.com
  DB:              D1Database;
}

function shouldMigrate(pct: number): boolean {
  return Math.random() * 100 < pct;
}

async function getMigrationPct(env: Env, path: string): Promise<number> {
  // Per-path override takes priority; fall back to global default
  const perPath = await env.MIGRATION_FLAGS.get(`migration_pct:${path}`);
  if (perPath !== null) return parseInt(perPath, 10);
  const global  = await env.MIGRATION_FLAGS.get('migration_pct');
  return global !== null ? parseInt(global, 10) : 0;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url  = new URL(request.url);
    const path = url.pathname;

    const pct = await getMigrationPct(env, path);

    if (pct > 0 && shouldMigrate(pct)) {
      // Route to new Workers backend via service binding
      const workerResponse = await env.NEW_BACKEND.fetch(request.clone());

      // Tail sampling: compare with origin in background (non-blocking)
      if (pct < 100 && Math.random() < 0.1) {  // sample 10% of migrated traffic
        ctx.waitUntil(compareWithOrigin(request.clone(), workerResponse.clone(), path, env));
      }

      return workerResponse;
    }

    // Fall through to legacy origin
    return fetch(new Request(env.ORIGIN_URL + path + url.search, request));
  },
};

async function compareWithOrigin(
  request: Request,
  workerResponse: Response,
  path: string,
  env: Env
): Promise<void> {
  const originStart = Date.now();
  const originResp  = await fetch(new Request(env.ORIGIN_URL + path, request));
  const originMs    = Date.now() - originStart;

  const [workerBody, originBody] = await Promise.all([
    workerResponse.text(),
    originResp.text(),
  ]);

  const bodyMatch = workerBody === originBody;
  const diffSummary = bodyMatch ? null : (
    `worker_len=${workerBody.length} origin_len=${originBody.length}`
  );

  await env.DB.prepare(
    `INSERT INTO response_diffs(path, origin_status, worker_status, body_match, origin_ms, diff_summary)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    path,
    originResp.status,
    workerResponse.status,
    bodyMatch ? 1 : 0,
    originMs,
    diffSummary
  ).run();
}
```

---

## KV Flag Management: Per-Endpoint Traffic Control

```bash
# Set global migration percentage to 10%
wrangler kv key put migration_pct "10" --namespace-id ${KV_NS_ID}

# Increase a specific endpoint to 50%
wrangler kv key put "migration_pct:/api/v1/users" "50" --namespace-id ${KV_NS_ID}

# Full cutover for one endpoint
wrangler kv key put "migration_pct:/api/v1/users" "100" --namespace-id ${KV_NS_ID}

# Instant rollback: set to 0 (takes effect within KV replication SLA ~60 s)
wrangler kv key put migration_pct "0" --namespace-id ${KV_NS_ID}

# Emergency per-endpoint rollback
wrangler kv key put "migration_pct:/api/v1/orders" "0" --namespace-id ${KV_NS_ID}
```

---

## Migration Progress Dashboard (D1 Queries)

```sql
-- Overall endpoint migration status
SELECT path, migration_pct, migrated_at, rollback_count
FROM migration_endpoints
ORDER BY migration_pct DESC, path;

-- Response match rate per endpoint (last 24 h)
SELECT
  path,
  COUNT(*)                          AS samples,
  ROUND(AVG(body_match) * 100, 1)  AS match_pct,
  ROUND(AVG(origin_ms), 0)         AS avg_origin_ms,
  ROUND(AVG(worker_ms), 0)         AS avg_worker_ms
FROM response_diffs
WHERE sampled_at > datetime('now', '-24 hours')
GROUP BY path
ORDER BY match_pct ASC;

-- Rollback events
SELECT path, rollback_count FROM migration_endpoints WHERE rollback_count > 0;
```

---

## Rollback Procedure

```bash
#!/usr/bin/env bash
# rollback.sh — instant traffic rollback to origin
set -euo pipefail

ENDPOINT="${1:-}"
KV_NS_ID="${KV_NAMESPACE_ID}"

if [[ -n "$ENDPOINT" ]]; then
  echo "Rolling back endpoint: $ENDPOINT"
  wrangler kv key put "migration_pct:${ENDPOINT}" "0" --namespace-id "$KV_NS_ID"
else
  echo "Rolling back ALL traffic to origin"
  wrangler kv key put migration_pct "0" --namespace-id "$KV_NS_ID"
fi

# Record rollback in D1
curl -sf -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{ \"sql\": \"UPDATE migration_endpoints SET rollback_count = rollback_count + 1 WHERE path = ?\", \"params\": [\"${ENDPOINT:-ALL}\"] }"

echo "Rollback complete. KV propagates within ~60 s."
```

---

## Final Cutover Sequence

```bash
# 1. Reduce DNS TTL to 60 s (at least 24 h before cutover)
#    Update your DNS record TTL via Cloudflare API or dashboard.

# 2. Confirm all endpoints at 100%
wrangler kv key put migration_pct "100" --namespace-id "${KV_NS_ID}"

# 3. Monitor for 30 minutes via D1 match-rate query above.

# 4. Decommission origin — update DNS CNAME from origin IP to Workers route
#    (already a no-op if traffic_pct=100, but eliminates the fallback)
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${DNS_RECORD_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"content":"workers-route-placeholder","ttl":1}'

# 5. Mark all endpoints as migrated in D1
curl -sf -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"sql":"UPDATE migration_endpoints SET migrated_at = datetime(\'now\') WHERE migrated_at IS NULL"}'
```

---

## Anti-patterns

- **Big-bang cutover (0% → 100% in one step)**: always ramp gradually (5% → 25% → 50% → 100%) over days, using D1 match-rate data to build confidence.
- **Using a Cookie or IP hash for traffic splitting instead of random**: deterministic splitting means the same user always hits the same backend; issues may not surface until 100%.
- **Forgetting to update `migration_endpoints` table**: without this record, rollback_count is meaningless and post-mortem analysis is harder.
- **Comparing response bodies byte-for-byte when timestamps differ**: normalise dynamic fields (timestamps, request IDs) before comparison in `compareWithOrigin`.
- **Leaving the Tail Worker running at 100% after cutover**: remove the sampling logic to avoid unnecessary D1 writes and CPU usage.

## Gotchas

- KV `get()` has ~60 ms median latency; cache the migration percentage in a module-level variable with a 30 s TTL to avoid adding latency to every request.
- Workers service bindings (`env.NEW_BACKEND.fetch()`) do not count as egress — they are free and low-latency. Prefer them over a second `fetch()` to a Workers URL.
- `ctx.waitUntil()` extends the request lifetime for the comparison, but the total response is still returned to the user immediately. The comparison result is write-only.
- D1 `INSERT` in `waitUntil` can fail silently. Add a `console.error` catch to surface failures in Workers Logs.

## Verification

```bash
# Confirm current migration percentage from KV
wrangler kv key get migration_pct --namespace-id "${KV_NS_ID}"

# Check match rate is > 99% before increasing pct
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT path, ROUND(AVG(body_match)*100,1) AS match_pct FROM response_diffs WHERE sampled_at > datetime(\'now\',' '-1 hour\') GROUP BY path"}'
```

## Related

- `cloudflare-access-service-token-rotation-automation.md`
- `terraform-workers-secret-rotation-automation.md`
- `cloudflare-workers-tail-worker-patterns.md`
- `cloudflare-kv-cache-patterns.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
- https://martinfowler.com/bliki/StranglerFigApplication.html
