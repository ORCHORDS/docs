# Content Flooding Rate Shaping With Durable Objects

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Anonymous users on example project / example.com occasionally flood feeds with hundreds of posts in seconds, drowning out organic content and degrading the experience for all readers. Unlike traditional rate limiting that simply rejects requests, content flooding requires adaptive rate shaping: slowing output gradually so legitimate burst-posters are not penalized while true flooding is suppressed. The platform needs per-session and per-subnet shaping that persists across Worker invocations without a centralized backend.

## Context

Because example project users are anonymous, there is no account-level token bucket. Durable Objects provide a natural fit: one DO per ephemeral session ID (derived from Turnstile token + IP subnet) stores a leaky-bucket counter with nanosecond-resolution timestamps. The DO lives at the Cloudflare edge closest to the user, keeping enforcement latency below 2 ms even before touching D1.

## Detection — Leaky-Bucket Counter in a Durable Object

Each POST /submit request hits a Worker that resolves the correct Durable Object for the session. The DO tracks the last-drain timestamp and accumulated credit; bursts drain naturally while sustained flooding trips the shaper.

```typescript
// durable-objects/ContentFloodShaper.ts
export interface Env {
  FLOOD_SHAPER: DurableObjectNamespace;
}

export interface BucketState {
  credits: number;
  lastDrainMs: number;
  violationCount: number;
}

const CAPACITY = 20;          // max burst posts
const REFILL_RATE = 1 / 30;  // 1 credit per 30 seconds
const PENALTY_MULTIPLIER = 2; // each violation halves effective rate

export class ContentFloodShaper implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const bucket = await this.state.storage.get<BucketState>("bucket") ?? {
      credits: CAPACITY,
      lastDrainMs: Date.now(),
      violationCount: 0,
    };

    const nowMs = Date.now();
    const elapsedSec = (nowMs - bucket.lastDrainMs) / 1000;
    const refill = elapsedSec * REFILL_RATE * (1 / (1 + bucket.violationCount * 0.5));
    bucket.credits = Math.min(CAPACITY, bucket.credits + refill);
    bucket.lastDrainMs = nowMs;

    if (bucket.credits < 1) {
      bucket.violationCount = Math.min(bucket.violationCount + 1, 10);
      await this.state.storage.put("bucket", bucket);
      const retryAfter = Math.ceil(1 / (REFILL_RATE / (1 + bucket.violationCount * 0.5)));
      return new Response(JSON.stringify({ allowed: false, retryAfter }), {
        status: 429,
        headers: { "Content-Type": "application/json" },
      });
    }

    bucket.credits -= 1;
    if (bucket.violationCount > 0) bucket.violationCount = Math.max(0, bucket.violationCount - 0.1);
    await this.state.storage.put("bucket", bucket);
    return new Response(JSON.stringify({ allowed: true, credits: Math.floor(bucket.credits) }), {
      headers: { "Content-Type": "application/json" },
    });
  }
}
```

## Enforcement — Worker Gateway

The gateway Worker resolves the shaper DO by session fingerprint and either passes the request or returns a shaped delay response. Critically, it never hard-blocks on the first violation; it inserts artificial backpressure so floods organically stall rather than triggering obvious 429 walls that drive evasion.

```typescript
// workers/submit-gateway.ts
import type { Env } from "../durable-objects/ContentFloodShaper";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const sessionId = request.headers.get("X-Session-Token") ?? "anon";
    const subnet = (request.headers.get("CF-Connecting-IP") ?? "0.0.0.0").split(".").slice(0, 3).join(".");
    const shaperKey = `${subnet}:${sessionId.slice(0, 16)}`;

    const shaperId = env.FLOOD_SHAPER.idFromName(shaperKey);
    const shaper = env.FLOOD_SHAPER.get(shaperId);

    const shaperResponse = await shaper.fetch(new Request("https://shaper/check"));
    const { allowed, retryAfter } = await shaperResponse.json<{ allowed: boolean; retryAfter?: number }>();

    if (!allowed) {
      // Shaped delay response: client is told to retry, not hard-blocked
      return new Response(
        JSON.stringify({ error: "rate_shaped", retryAfter }),
        {
          status: 429,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": String(retryAfter ?? 30),
            "X-Shape-Reason": "content-flood",
          },
        }
      );
    }

    // Forward to origin / D1 write path
    const upstream = await fetch("https://origin.example.com/submit", {
      method: "POST",
      headers: request.headers,
      body: request.body,
    });
    return upstream;
  },
};
```

## Escalation — Persistent Strike Recording in D1

Repeated flooding despite shaping triggers a persistent record in D1, moving the user from shaped to shadow-limited. After 3 escalations within 24 hours, the account is queued for human review.

```typescript
// workers/flood-escalation.ts
export async function recordFloodEscalation(
  db: D1Database,
  shaperKey: string
): Promise<{ shadowLimit: boolean; queuedForReview: boolean }> {
  const windowStart = new Date(Date.now() - 86_400_000).toISOString();

  await db.prepare(
    `INSERT INTO flood_strikes (shaper_key, struck_at)
     VALUES (?, ?)
     ON CONFLICT DO NOTHING`
  ).bind(shaperKey, new Date().toISOString()).run();

  const { results } = await db.prepare(
    `SELECT COUNT(*) as cnt FROM flood_strikes
     WHERE shaper_key = ? AND struck_at > ?`
  ).bind(shaperKey, windowStart).all<{ cnt: number }>();

  const strikeCount = results[0]?.cnt ?? 0;

  if (strikeCount >= 3) {
    await db.prepare(
      `INSERT INTO shadow_limits (shaper_key, limited_until, reason)
       VALUES (?, datetime('now', '+24 hours'), 'content-flood')
       ON CONFLICT(shaper_key) DO UPDATE SET
         limited_until = datetime('now', '+24 hours'),
         reason = 'content-flood'`
    ).bind(shaperKey).run();

    if (strikeCount === 3) {
      await db.prepare(
        `INSERT INTO moderation_queue (subject_key, reason, queued_at)
         VALUES (?, 'content-flood-escalation', datetime('now'))`
      ).bind(shaperKey).run();
    }
    return { shadowLimit: true, queuedForReview: strikeCount === 3 };
  }
  return { shadowLimit: false, queuedForReview: false };
}
```

## Monitoring — Analytics Engine Metrics

Each shaping event is emitted to Cloudflare Analytics Engine so the on-call team can watch flood activity in real time without polling D1.

```typescript
// workers/flood-metrics.ts
export function emitFloodMetric(
  analytics: AnalyticsEngineDataset,
  shaperKey: string,
  action: "shaped" | "escalated" | "shadow-limited",
  credits: number
): void {
  analytics.writeDataPoint({
    blobs: [shaperKey, action],
    doubles: [credits],
    indexes: [shaperKey.slice(0, 32)],
  });
}
```

Query via Workers Analytics Engine API:
```sql
SELECT
  blob2 AS action,
  COUNT() AS events,
  AVG(double1) AS avg_credits_remaining
FROM flood_metrics
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY action
ORDER BY events DESC
```

## Anti-patterns

- Hard-blocking on first violation — drives sophisticated flooders to rotate sessions; gradual shaping is stealthier
- Keying the DO solely on IP — /64 IPv6 subnets can share one address; combine with session token
- Storing timestamps as Unix integers in DO storage — use milliseconds to avoid drift in refill calculations
- Setting `violationCount` decay too fast — flooders exploit rapid credit recovery between burst windows
- Forgetting DO hibernation — if the DO idles out, credits reset; persist state to `storage` on every mutation

## Gotchas

- Durable Objects have a 128 MB memory limit; don't cache flood history in memory, use `storage` only
- `state.storage.put` is durable but not transactional across concurrent fetches; use `state.blockConcurrencyWhile` for atomic read-modify-write on the bucket
- `CF-Connecting-IP` is only available in production; in `wrangler dev` it is absent — provide a fallback
- The leaky-bucket refill must account for DO eviction gaps; always recompute from the stored `lastDrainMs`
- Analytics Engine writes are best-effort; don't use them as the source of truth for escalation counts

## Verification

1. Deploy the DO and gateway Worker with `wrangler deploy`.
2. Run a flood simulation: `for i in $(seq 1 50); do curl -s -X POST .../submit -H "X-Session-Token: test123"; done` — expect the first 20 to succeed and subsequent requests to return 429 with `Retry-After`.
3. Confirm D1 strike records appear after the third 429 within the same `shaperKey`.
4. Tail Analytics Engine: verify `action=shaped` events accumulate in real time.
5. After 3 escalations, confirm `shadow_limits` and `moderation_queue` rows exist in D1.

## Related

- `/documentation/categories/issues/anonymous-dm-spam-burst-detection-durable-objects.md`
- `/documentation/categories/issues/platform-abuse-rate-velocity-d1-workers.md`
- `/documentation/categories/issues/shadow-banning-reach-limiting-d1-workers.md`
- `/documentation/categories/issues/viral-content-cascade-rate-limiting-durable-objects.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/state/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
