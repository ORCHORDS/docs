# Workers Cron Trigger Security Hardening

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Scheduled Workers (cron triggers) run sensitive operations — purging expired records, rotating keys, sending billing summaries. Teams discover the cron handler is also reachable as a plain HTTP route, or that manual dashboard invocations bypass audit controls. Without context-aware guards, an attacker who reaches the internal route can replay scheduled logic on demand.

## Context

Cloudflare Workers support two execution entry points: `fetch` (HTTP requests) and `scheduled` (cron events). The `scheduled` handler receives an `event.scheduledTime` timestamp and a `controller` object; it has no `Request`. However, developers sometimes expose a `/cron-run` HTTP endpoint that calls the same underlying function — inadvertently making the scheduled job externally triggerable. Hardening requires: (1) context detection to separate `scheduled` from `fetch`, (2) secret-authenticated override for dashboard manual triggers, and (3) immutable audit logs to R2/Analytics Engine.

---

## 1. Context Detection — Separating Scheduled from HTTP

```typescript
// src/index.ts
export interface Env {
  CRON_OVERRIDE_SECRET: string;
  DB: D1Database;
  AUDIT: AnalyticsEngineDataset;
}

export default {
  // HTTP handler — never exposes cron logic without auth
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/internal/cron-override') {
      return handleCronOverride(request, env, ctx);
    }
    return new Response('Not found', { status: 404 });
  },

  // Scheduled handler — the only trusted cron entry point
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runCronJob(env, event.scheduledTime, 'cron'));
  },
};
```

---

## 2. Secret-Authenticated Manual Override Endpoint

Expose a manual trigger only for debugging, protected by a constant-time secret check and scoped to internal subnets via a Cloudflare Access service token.

```typescript
async function handleCronOverride(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  // Require POST to prevent accidental GET triggers
  if (request.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }

  const provided = request.headers.get('X-Cron-Secret') ?? '';
  const expected = env.CRON_OVERRIDE_SECRET;

  // Constant-time comparison via SubtleCrypto to prevent timing attacks
  const enc = new TextEncoder();
  const providedBuf = enc.encode(provided.padEnd(64, '\0').slice(0, 64));
  const expectedBuf = enc.encode(expected.padEnd(64, '\0').slice(0, 64));
  const key = await crypto.subtle.importKey('raw', expectedBuf, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig1 = await crypto.subtle.sign('HMAC', key, providedBuf);
  const sig2 = await crypto.subtle.sign('HMAC', key, expectedBuf);
  const match =
    new Uint8Array(sig1).every((b, i) => b === new Uint8Array(sig2)[i]);

  if (!match) {
    return new Response('Unauthorized', { status: 401 });
  }

  ctx.waitUntil(runCronJob(env, Date.now(), 'manual-override'));
  return new Response(JSON.stringify({ queued: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## 3. Idempotency Guard — Preventing Double Execution

Use D1 to insert a deduplication row before doing any work; roll back on duplicate key.

```typescript
async function runCronJob(
  env: Env,
  scheduledTime: number,
  source: 'cron' | 'manual-override',
): Promise<void> {
  const runId = `${Math.floor(scheduledTime / 60_000)}`; // 1-minute epoch bucket

  const guard = await env.DB.prepare(
    `INSERT OR IGNORE INTO cron_runs (run_id, source, started_at)
     VALUES (?, ?, datetime('now'))`,
  )
    .bind(runId, source)
    .run();

  if (guard.meta.changes === 0) {
    // Already running or ran within this minute bucket
    await auditLog(env, 'cron.skipped.duplicate', { runId, source });
    return;
  }

  try {
    await doCronWork(env);
    await env.DB.prepare(`UPDATE cron_runs SET status='ok' WHERE run_id=?`).bind(runId).run();
    await auditLog(env, 'cron.success', { runId, source });
  } catch (err) {
    await env.DB.prepare(`UPDATE cron_runs SET status='error' WHERE run_id=?`).bind(runId).run();
    await auditLog(env, 'cron.error', { runId, source, error: String(err) });
    throw err;
  }
}
```

---

## 4. Audit Logging to Analytics Engine

```typescript
async function auditLog(
  env: Env,
  event: string,
  data: Record<string, unknown>,
): Promise<void> {
  env.AUDIT.writeDataPoint({
    blobs: [event, JSON.stringify(data)],
    doubles: [Date.now()],
    indexes: [event.split('.')[0]], // index on event family for fast lookup
  });
}
```

---

## 5. Wrangler Configuration

```toml
# wrangler.toml
[triggers]
crons = ["0 * * * *"]   # hourly

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<uuid>"

[[analytics_engine_datasets]]
binding = "AUDIT"
dataset = "security_audit"

[vars]
# Never put CRON_OVERRIDE_SECRET here — use wrangler secret put
```

---

## Anti-patterns

- Calling `runCronJob()` directly from an unauthenticated HTTP route — lets any client trigger it.
- Using `Math.random()` or `Date.now()` string comparison for secret validation — vulnerable to timing attacks.
- Running cron logic without idempotency guards — double-firing on network retry causes duplicate operations.
- Logging the full `CRON_OVERRIDE_SECRET` value into Analytics Engine — rotates it from a secret to observable telemetry.
- Omitting `waitUntil` in the scheduled handler — the runtime kills the Worker before async work completes.

## Gotchas

- `event.scheduledTime` is milliseconds since Unix epoch, not a `Date` object; convert with `new Date(event.scheduledTime)`.
- Manual triggers from the Cloudflare dashboard invoke the `scheduled` handler directly (not `fetch`), so the HTTP override endpoint is separate.
- Analytics Engine writes are batched; a Worker that crashes before `ctx.waitUntil` resolves may lose the last audit write.
- D1 `INSERT OR IGNORE` requires a `UNIQUE` constraint on `run_id`; add `CREATE UNIQUE INDEX` in migrations.
- Workers cron triggers have a maximum execution wall time of 30 seconds (CPU time limits apply separately).

## Verification

```bash
# Confirm the override endpoint requires a secret
curl -X POST https://api.example.com/internal/cron-override \
  -H "X-Cron-Secret: wrong" -w "%{http_code}"
# Expected: 401

# Confirm correct secret succeeds
curl -X POST https://api.example.com/internal/cron-override \
  -H "X-Cron-Secret: $CRON_OVERRIDE_SECRET" -w "%{http_code}"
# Expected: 200

# Query deduplication table after two rapid firings
wrangler d1 execute app-db --command \
  "SELECT run_id, source, status FROM cron_runs ORDER BY started_at DESC LIMIT 5"
```

## Related

- `durable-objects-alarm-session-expiry-revocation.md` — Durable Object alarms as alternative to cron triggers
- `workers-audit-log-immutable-r2-worm-pattern.md` — Immutable audit log pattern for cron outputs
- `workers-environment-variable-hygiene.md` — Managing `CRON_OVERRIDE_SECRET` lifecycle
- `timing-safe-compare.md` — SubtleCrypto constant-time comparison patterns

## Sources

- [Cloudflare Workers Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Scheduled Events — ScheduledEvent API](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/)
- [Workers Limits — CPU and Wall Time](https://developers.cloudflare.com/workers/platform/limits/)
- [Analytics Engine Write API](https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/)
