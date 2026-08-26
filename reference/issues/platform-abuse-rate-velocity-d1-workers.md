# Platform Abuse Velocity Detection: D1 Sliding Windows and Workers Middleware

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Velocity Detection Problem

Abuse on UGC platforms rarely looks like a single egregious action — it looks like a high-frequency sequence of low-severity actions: 40 account creations per hour from the same IP range, 200 reports filed by a single user in a day, 15 failed login attempts per minute per account. Rate limiting per-endpoint at a fixed quota catches brute force but misses coordinated slow-drip abuse that stays just below per-endpoint limits.

Velocity detection tracks event counts over sliding time windows at multiple granularities (1 min, 1 hour, 24 hours) per user and per IP, then compares counts against configured thresholds. When thresholds are exceeded, Workers middleware blocks the request synchronously and enqueues an async enforcement action — account suspension, IP block, or analyst review — without adding async latency to the request for benign users.

D1 provides consistent, queryable time-series event counts without requiring a Redis instance or a separate rate-limit service. Sliding windows are implemented as SQL aggregates over an `events` table partitioned by `(actor, event_type, ts)`. A separate Workers cron purges rows older than 30 days to control table growth.

## Context

- Runtime: Cloudflare Workers fetch middleware + D1 + Queues
- Storage: D1 for event counts (append-only `abuse_events` table)
- Enforcement: Cloudflare Queues for async suspension, KV for hot block-list cache
- Cron: Workers cron for old-event purge

## D1 Schema and Sliding Window Query

```sql
-- schema: abuse_events table (D1 migration)
CREATE TABLE abuse_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id   TEXT NOT NULL,   -- user_id or 'ip:1.2.3.4'
  event_type TEXT NOT NULL,   -- 'login_fail', 'report_filed', 'account_create', etc.
  ts         INTEGER NOT NULL  -- epoch ms
);
CREATE INDEX idx_ae_actor_type_ts ON abuse_events (actor_id, event_type, ts);

-- abuse_thresholds table (editable without code deploy)
CREATE TABLE abuse_thresholds (
  event_type   TEXT NOT NULL,
  window_ms    INTEGER NOT NULL,  -- e.g. 60000, 3600000, 86400000
  actor_scope  TEXT NOT NULL,     -- 'user' | 'ip'
  max_count    INTEGER NOT NULL,
  action       TEXT NOT NULL,     -- 'block' | 'review' | 'shadowban'
  PRIMARY KEY (event_type, window_ms, actor_scope)
);
```

```ts
// lib/velocity-checker.ts
export interface VelocityThreshold {
  event_type: string;
  window_ms: number;
  actor_scope: 'user' | 'ip';
  max_count: number;
  action: 'block' | 'review' | 'shadowban';
}

export interface VelocityViolation {
  actorId: string;
  eventType: string;
  windowMs: number;
  count: number;
  maxCount: number;
  action: string;
}

export async function checkVelocity(
  userId: string,
  ipAddress: string,
  eventType: string,
  env: Env
): Promise<VelocityViolation | null> {
  const thresholds = await env.DB.prepare(
    `SELECT * FROM abuse_thresholds WHERE event_type = ?`
  ).bind(eventType).all<VelocityThreshold>();

  for (const t of thresholds.results) {
    const actorId = t.actor_scope === 'user' ? userId : `ip:${ipAddress}`;
    const windowStart = Date.now() - t.window_ms;

    const row = await env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM abuse_events
       WHERE actor_id = ? AND event_type = ? AND ts >= ?`
    ).bind(actorId, eventType, windowStart).first<{ cnt: number }>();

    const count = row?.cnt ?? 0;
    if (count >= t.max_count) {
      return { actorId, eventType, windowMs: t.window_ms, count, maxCount: t.max_count, action: t.action };
    }
  }
  return null;
}

export async function recordEvent(
  userId: string,
  ipAddress: string,
  eventType: string,
  actorScope: 'user' | 'ip',
  env: Env
): Promise<void> {
  const actorId = actorScope === 'user' ? userId : `ip:${ipAddress}`;
  await env.DB.prepare(
    `INSERT INTO abuse_events (actor_id, event_type, ts) VALUES (?, ?, ?)`
  ).bind(actorId, eventType, Date.now()).run();
}
```

## Workers Middleware Integration

The middleware records the event first, then checks velocity. Recording before checking ensures the current request is included in the window count (prevents off-by-one under concurrent requests). Violations are handled synchronously for `block`, asynchronously via Queue for `review` and `shadowban`.

```ts
// middleware/velocity-guard.ts
import { checkVelocity, recordEvent, VelocityViolation } from '../lib/velocity-checker';
import { isHotBlocked } from '../lib/hot-blocklist';

export async function velocityGuard(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  eventType: string,
  next: () => Promise<Response>
): Promise<Response> {
  const userId  = request.headers.get('X-User-Id')  ?? 'anonymous';
  const ipRaw   = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
  const ip      = ipRaw.split(',')[0].trim(); // handle X-Forwarded-For chaining

  // Fast path: check KV hot block-list before D1
  if (await isHotBlocked(userId, ip, env)) {
    return Response.json({ error: 'Rate limit exceeded', code: 'VELOCITY_BLOCK' }, { status: 429 });
  }

  // Record event (both user and IP actors)
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO abuse_events (actor_id, event_type, ts) VALUES (?, ?, ?)`).bind(userId, eventType, Date.now()),
    env.DB.prepare(`INSERT INTO abuse_events (actor_id, event_type, ts) VALUES (?, ?, ?)`).bind(`ip:${ip}`, eventType, Date.now()),
  ]);

  // Check velocity for both scopes
  const violation = await checkVelocity(userId, ip, eventType, env);
  if (violation) {
    ctx.waitUntil(handleViolation(violation, userId, ip, env));

    if (violation.action === 'block') {
      return Response.json({ error: 'Rate limit exceeded', code: 'VELOCITY_BLOCK' }, { status: 429 });
    }
    // shadowban/review: let request proceed but mark it
    request.headers.set('X-Shadowban', '1');
  }

  return next();
}

async function handleViolation(violation: VelocityViolation, userId: string, ip: string, env: Env): Promise<void> {
  await env.ENFORCEMENT_QUEUE.send({
    violatorId: violation.actorId,
    userId,
    ip,
    eventType: violation.eventType,
    action: violation.action,
    count: violation.count,
    maxCount: violation.maxCount,
    windowMs: violation.windowMs,
    detectedAt: Date.now(),
  });

  // Cache the block in KV for fast path on subsequent requests
  if (violation.action === 'block') {
    const key = violation.actorId.startsWith('ip:') ? `blocked_ip:${ip}` : `blocked_user:${userId}`;
    await env.ABUSE_KV.put(key, '1', { expirationTtl: 3600 });
  }
}
```

## Async Enforcement Queue Consumer

```ts
// workers/enforcement-consumer.ts
interface EnforcementMessage {
  violatorId: string;
  userId: string;
  ip: string;
  eventType: string;
  action: 'block' | 'review' | 'shadowban';
  count: number;
  maxCount: number;
  windowMs: number;
  detectedAt: number;
}

export default {
  async queue(batch: MessageBatch<EnforcementMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { userId, action, eventType, count } = msg.body;

      if (action === 'block' || action === 'shadowban') {
        await env.DB.prepare(
          `UPDATE users SET moderation_status = ?, flagged_at = ? WHERE id = ?`
        ).bind(action === 'block' ? 'suspended' : 'shadowbanned', Date.now(), userId).run();
      } else if (action === 'review') {
        await env.DB.prepare(
          `INSERT INTO analyst_queue (user_id, reason, event_count, event_type, queued_at) VALUES (?, ?, ?, ?, ?)`
        ).bind(userId, 'velocity_threshold', count, eventType, Date.now()).run();
      }

      msg.ack();
    }
  },
};
```

## Cron: Purge Old Events

```ts
// workers/abuse-event-purge.ts  (cron: "0 3 * * *" — 03:00 UTC daily)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000; // 30 days
    await env.DB.prepare(`DELETE FROM abuse_events WHERE ts < ?`).bind(cutoff).run();
  },
};
```

## Anti-patterns

- Using KV alone for event counts — KV lacks atomic increment; concurrent writes race
- Checking velocity before recording — the triggering event is excluded from the window count
- Performing the enforcement action synchronously in the request path — adds latency for all users
- Using `SELECT COUNT(*)` without an index on `(actor_id, event_type, ts)` — full table scan under load
- Setting a single global threshold for all event types — different events need different sensitivity

## Gotchas

- D1 `DELETE` on large tables is slow; batch deletes in the purge cron with `LIMIT 1000` loops
- `CF-Connecting-IP` can be spoofed if the Worker is not behind Cloudflare's WAF; validate accordingly
- KV `expirationTtl` is in seconds, not milliseconds — `3600` means 1 hour, not 1 second
- D1 write throughput (~1000/s) may be a bottleneck on very high-traffic endpoints; consider sampling 10% of events for velocity on ultra-hot paths
- Sliding window queries perform a range scan per request; add a covering index or pre-aggregate in a cron if the `abuse_events` table exceeds 10 M rows

## Verification

```ts
// Verify that exceeding threshold returns 429
const mockEnv = buildMockEnvWithThreshold({ eventType: 'login_fail', windowMs: 60_000, maxCount: 5, action: 'block' });
for (let i = 0; i < 5; i++) {
  await velocityGuard(buildRequest('u1', '1.2.3.4'), mockEnv, mockCtx, 'login_fail', async () => new Response('ok'));
}
const res = await velocityGuard(buildRequest('u1', '1.2.3.4'), mockEnv, mockCtx, 'login_fail', async () => new Response('ok'));
console.assert(res.status === 429, '6th attempt within window must be blocked');
```

## Related

- `documentation/categories/issues/viral-content-cascade-rate-limiting-durable-objects.md`
- `documentation/categories/issues/real-time-toxic-content-scoring-workers-ai.md`
- `documentation/categories/issues/d1-integer-overflow-javascript.md`
- `documentation/categories/issues/d1-column-affinity-gotcha.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/kv/
- https://owasp.org/www-community/attacks/Credential_stuffing
