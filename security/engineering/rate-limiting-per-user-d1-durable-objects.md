# Rate Limiting Per-User with D1 and Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

IP-based rate limiting fails against distributed attackers using residential proxies
or clients legitimately behind NAT (an entire office building shares one IP). Per-user
rate limiting keys on an authenticated identity — usually a user ID or API key — and
applies quotas regardless of the source IP. The challenge on Cloudflare Workers is
choosing between D1 (SQL, persistent, eventually consistent across regions) and
Durable Objects (strongly consistent, serialised, per-object single-threaded) for the
counter store, and then composing them for different rate-limiting semantics.

## Context

Two architecturally distinct problems require different stores:

1. **Burst / short-window limiting** (e.g., 10 requests per second per user):
   Requires sub-second precision and atomic increment-and-read. D1 is too slow for
   this (typical RTT 5–30 ms, which itself exceeds the 100 ms burst window). Use a
   **Durable Object** per user — it is single-threaded by design and lives in the
   region nearest the first connection.

2. **Quota / long-window limiting** (e.g., 10 000 API calls per month per tenant):
   Counters can tolerate a few seconds of lag. D1 writes are durable; use them for
   billing-level quotas that must survive Worker restarts and be queryable for
   reporting.

Attack vectors addressed:
- **API farming** — one account making bulk extraction calls beyond contractual limits.
- **Enumeration amplification** — a single compromised account probing
  `/api/users/{id}` for thousands of IDs.
- **Cost-by-proxy attacks** — an attacker forcing a victim to exhaust their own quota
  (relevant for multi-tenant SaaS).

## Durable Object Per-User Burst Limiter

```typescript
// src/rate-limiter-do.ts

export interface RateLimitState {
  windowStart: number;
  count: number;
}

export class UserRateLimiter implements DurableObject {
  private state: DurableObjectState;
  private WINDOW_MS = 1_000;   // 1-second sliding window
  private MAX_REQUESTS = 10;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();

    // Read current window state (Durable Object storage is synchronous-ish)
    let windowStart: number = (await this.state.storage.get<number>('ws')) ?? now;
    let count: number = (await this.state.storage.get<number>('cnt')) ?? 0;

    // Reset window if expired
    if (now - windowStart >= this.WINDOW_MS) {
      windowStart = now;
      count = 0;
    }

    count += 1;

    // Persist updated state
    await this.state.storage.put('ws', windowStart);
    await this.state.storage.put('cnt', count);

    const allowed = count <= this.MAX_REQUESTS;
    const remaining = Math.max(0, this.MAX_REQUESTS - count);
    const resetAt = windowStart + this.WINDOW_MS;

    return new Response(
      JSON.stringify({ allowed, remaining, resetAt }),
      {
        status: allowed ? 200 : 429,
        headers: {
          'Content-Type': 'application/json',
          'X-RateLimit-Limit': String(this.MAX_REQUESTS),
          'X-RateLimit-Remaining': String(remaining),
          'X-RateLimit-Reset': String(Math.ceil(resetAt / 1000)),
        },
      },
    );
  }
}
```

Worker entry point wiring:

```typescript
// src/index.ts
import { UserRateLimiter } from './rate-limiter-do';
export { UserRateLimiter };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const userId = await authenticate(request, env);
    if (!userId) {
      return new Response('Unauthorized', { status: 401 });
    }

    // Route to the Durable Object for this user
    const doId = env.USER_RATE_LIMITER.idFromName(userId);
    const limiterStub = env.USER_RATE_LIMITER.get(doId);

    const limitResponse = await limiterStub.fetch(new Request(request.url));
    const limitData = await limitResponse.json<{ allowed: boolean }>();

    if (!limitData.allowed) {
      return new Response(
        JSON.stringify({ error: 'rate_limit_exceeded' }),
        {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': '1',
            ...Object.fromEntries(limitResponse.headers),
          },
        },
      );
    }

    return handleRequest(request, env, userId);
  },
};
```

`wrangler.toml` binding:

```toml
[[durable_objects.bindings]]
name = "USER_RATE_LIMITER"
class_name = "UserRateLimiter"

[[migrations]]
tag = "v1"
new_classes = ["UserRateLimiter"]
```

## D1 Monthly Quota Tracking

```sql
-- migrations/0010_rate_limit_quotas.sql
CREATE TABLE IF NOT EXISTS api_usage (
  user_id      TEXT    NOT NULL,
  period_key   TEXT    NOT NULL,   -- 'YYYY-MM' for monthly, 'YYYY-WW' for weekly
  call_count   INTEGER NOT NULL DEFAULT 0,
  updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, period_key)
);

CREATE INDEX IF NOT EXISTS idx_api_usage_user ON api_usage(user_id);
```

```typescript
// Returns true if the user is within quota, false if exceeded.
async function checkAndIncrementMonthlyQuota(
  db: D1Database,
  userId: string,
  monthlyLimit: number,
): Promise<{ allowed: boolean; used: number; limit: number }> {
  const periodKey = new Date().toISOString().slice(0, 7); // 'YYYY-MM'

  // Atomic upsert: insert or increment, then read the new value.
  // D1 serialises writes per database, so this is safe without explicit transactions
  // as long as we use a single statement.
  const result = await db
    .prepare(
      `INSERT INTO api_usage (user_id, period_key, call_count, updated_at)
         VALUES (?1, ?2, 1, datetime('now'))
       ON CONFLICT(user_id, period_key)
         DO UPDATE SET
           call_count  = call_count + 1,
           updated_at  = datetime('now')
       RETURNING call_count`,
    )
    .bind(userId, periodKey)
    .first<{ call_count: number }>();

  const used = result?.call_count ?? 1;
  const allowed = used <= monthlyLimit;

  return { allowed, used, limit: monthlyLimit };
}
```

## Composing Both Layers

```typescript
async function enforceRateLimits(
  request: Request,
  env: Env,
  userId: string,
  tenantMonthlyLimit: number,
): Promise<Response | null> {
  // Layer 1: burst (Durable Object)
  const doId = env.USER_RATE_LIMITER.idFromName(userId);
  const burstResult = await env.USER_RATE_LIMITER.get(doId).fetch(
    new Request(request.url),
  );
  if (burstResult.status === 429) {
    const headers = new Headers(burstResult.headers);
    headers.set('X-RateLimit-Type', 'burst');
    return new Response(JSON.stringify({ error: 'burst_limit_exceeded' }), {
      status: 429,
      headers,
    });
  }

  // Layer 2: monthly quota (D1)
  const { allowed, used, limit } = await checkAndIncrementMonthlyQuota(
    env.DB,
    userId,
    tenantMonthlyLimit,
  );
  if (!allowed) {
    return new Response(
      JSON.stringify({
        error: 'monthly_quota_exceeded',
        used,
        limit,
        reset: getMonthReset(),
      }),
      {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'X-RateLimit-Type': 'quota',
          'X-RateLimit-Limit': String(limit),
          'X-RateLimit-Used': String(used),
          'X-RateLimit-Reset': String(getMonthReset()),
        },
      },
    );
  }

  return null; // all limits passed
}

function getMonthReset(): number {
  const d = new Date();
  return Math.floor(new Date(d.getFullYear(), d.getMonth() + 1, 1).getTime() / 1000);
}
```

## Mobile vs Web Considerations

**Web clients** typically send authenticated requests from a session cookie or Bearer
token. The `userId` is extracted from the validated session. No special handling is
needed for NAT — each browser session identifies as the authenticated user.

**Mobile clients** deserve additional nuance:
- **Offline operation**: a mobile client may batch-send multiple queued requests when
  connectivity restores. If each queued action counts as one API call, users get
  penalised for being offline. Consider a `X-Batched-Count` header that instructs the
  Worker to debit multiple quota units in one transaction.
- **Background refresh**: iOS background app refresh and Android WorkManager can issue
  requests without the user actively using the app. Attribute these to the user's
  quota but emit a `source=background` metric dimension so quotas can be tiered by
  call source.
- **Roaming users**: a user travelling across regions will have their Durable Object
  requests redirected to the home region. This adds latency but preserves consistency.
  The Cloudflare DO `locationHint` option can pin the DO to a region close to the
  user's primary location at creation time.

## Admin: Quota Inspection and Manual Reset

```typescript
// GET /admin/path/to/quota
async function getQuotaReport(db: D1Database, userId: string) {
  const rows = await db
    .prepare(
      `SELECT period_key, call_count, updated_at
         FROM api_usage
        WHERE user_id = ?1
        ORDER BY period_key DESC
        LIMIT 6`,
    )
    .bind(userId)
    .all<{ period_key: string; call_count: number; updated_at: string }>();

  return rows.results;
}

// POST /admin/path/to/quota/reset — admin-only endpoint
async function resetMonthlyQuota(db: D1Database, userId: string): Promise<void> {
  const periodKey = new Date().toISOString().slice(0, 7);
  await db
    .prepare(
      `UPDATE api_usage SET call_count = 0, updated_at = datetime('now')
        WHERE user_id = ?1 AND period_key = ?2`,
    )
    .bind(userId, periodKey)
    .run();
}
```

## Anti-patterns

- **Using KV for burst limiting**: KV is eventually consistent with ~1–2 s global
  propagation. Under burst conditions multiple Workers may read a stale count and all
  allow requests that should be blocked. Use Durable Objects for sub-second precision.
- **Keying the Durable Object on IP address**: NAT breaks this; authenticated user ID
  is the right key. For unauthenticated endpoints, combine IP + User-Agent hash.
- **A single global Durable Object for all users**: a single DO is single-threaded.
  Every request for every user would queue behind one another. Always shard by user.
- **Not persisting DO state across hibernation**: if the DO hibernates and storage is
  not used, the in-memory counter resets to zero, effectively granting a fresh window.
  Always use `this.state.storage` — not instance variables — for durable counters.
- **D1 for burst windows without transactions**: D1 `INSERT … ON CONFLICT … DO UPDATE`
  in a single statement is atomic at the row level. Multi-statement "read then write"
  patterns without transactions are not atomic and will under-count under concurrency.

## Gotchas

- Durable Objects are billed per GB-month of storage and per million requests. One DO
  per user at scale (millions of users) is common and cost-effective, but monitor
  storage usage if you store per-user history beyond simple counters.
- The `idFromName` function is deterministic and global. If two different namespaces
  use the same name string, they get different DOs (namespaced by binding), but if you
  accidentally reuse the same DO binding for two logical purposes, they share state.
- D1 `ON CONFLICT DO UPDATE` increments the column atomically within a single write
  transaction but does not provide serializable isolation across concurrent Workers.
  For billing-critical counters, run the upsert inside an explicit `BEGIN; … COMMIT`
  block or accept ±1 calls of imprecision as a business decision.
- Rate-limit headers (`X-RateLimit-*`) are non-standard but widely implemented.
  The IETF draft `draft-ietf-httpapi-ratelimit-headers` standardises them; align with
  that draft for client compatibility.

## Verification

```bash
# Hit the burst limit (11 rapid requests for a limit of 10)
for i in $(seq 1 11); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    https://api.example.com/api/data)
  echo "Request $i: $STATUS"
done
# First 10 should be 200; 11th should be 429 with X-RateLimit-Type: burst

# Check monthly quota via admin endpoint
curl -s -H "X-Admin-Key: $ADMIN_KEY" \
  https://api.example.com/admin/path/to/quota | jq .

# Verify D1 counter
wrangler d1 execute my-db \
  --command "SELECT * FROM api_usage WHERE user_id = '$USER_ID' ORDER BY period_key DESC LIMIT 3"
```

## Related

- `rate-limiting-ddos-defense-layers.md`
- `rate-limiting-strategies.md`
- `graphql-rate-limiting.md`
- `cloudflare-bot-management-abuse-prevention.md`
- `sql-injection-prevention-d1-workers.md`

## Sources

- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- IETF RateLimit Headers draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
- OWASP API Security API4:2023 Unrestricted Resource Consumption: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
