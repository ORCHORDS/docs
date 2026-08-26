# Mobile API Rate Limiting with Per-Device Token Buckets in Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your mobile API is getting hammered by automated scripts or misbehaving app versions that loop retry logic. You need per-device rate limiting that survives Worker restarts and scales globally without a central Redis cluster. You also want to allow brief bursts (the user tapped the button twice), enforce a hard ceiling, return standard `X-RateLimit-*` headers, and record limit violations for analytics.

## Context

Cloudflare Workers KV is eventually consistent globally but supports atomic `put` with TTL, making it suitable for a token-bucket algorithm where the bucket state is a small JSON value. The device identity is extracted from a request header (`X-Device-ID`) set by the mobile SDK. Because KV reads have ~50–60 ms global median latency (from cache) and writes propagate in seconds, the approach is best for limits measured in seconds-to-minutes, not sub-second throttling. For sub-second throttling, use Durable Objects.

## Solution

```typescript
// rate-limit-worker.ts
import { Hono } from 'hono';

export interface Env {
  RATE_KV: KVNamespace;
  DB: D1Database;
  // Per-plan limits (can also be loaded from KV config)
  LIMIT_FREE_RPM: string;   // requests per minute for free tier
  LIMIT_PRO_RPM: string;    // requests per minute for pro tier
  BURST_MULTIPLIER: string; // e.g. "1.5" => 50% burst above steady rate
}

interface TokenBucket {
  tokens: number;
  lastRefillAt: number; // Unix ms
}

const WINDOW_MS = 60_000; // 1-minute rolling window

async function resolveDeviceLimit(deviceId: string, env: Env): Promise<number> {
  // Look up per-device plan tier from D1 (cached in KV for 5 min)
  const cached = await env.RATE_KV.get(`plan:${deviceId}`);
  if (cached) return parseInt(cached, 10);

  const row = await env.DB.prepare(
    'SELECT plan FROM device_plans WHERE device_id = ? LIMIT 1'
  ).bind(deviceId).first<{ plan: string }>();

  const rpm = row?.plan === 'pro'
    ? parseInt(env.LIMIT_PRO_RPM, 10)
    : parseInt(env.LIMIT_FREE_RPM, 10);

  await env.RATE_KV.put(`plan:${deviceId}`, String(rpm), { expirationTtl: 300 });
  return rpm;
}

async function consumeToken(
  deviceId: string,
  env: Env,
  maxRpm: number
): Promise<{ allowed: boolean; remaining: number; resetAt: number; retryAfter?: number }> {
  const burstMultiplier = parseFloat(env.BURST_MULTIPLIER ?? '1.5');
  const bucketCapacity = Math.ceil(maxRpm * burstMultiplier);
  const refillRate = maxRpm / WINDOW_MS; // tokens per ms

  const key = `bucket:${deviceId}`;
  const raw = await env.RATE_KV.get(key);
  const now = Date.now();

  let bucket: TokenBucket;
  if (!raw) {
    // First request — full bucket
    bucket = { tokens: bucketCapacity, lastRefillAt: now };
  } else {
    bucket = JSON.parse(raw) as TokenBucket;
    // Refill tokens based on elapsed time
    const elapsed = now - bucket.lastRefillAt;
    const refilled = elapsed * refillRate;
    bucket.tokens = Math.min(bucketCapacity, bucket.tokens + refilled);
    bucket.lastRefillAt = now;
  }

  const resetAt = now + WINDOW_MS;

  if (bucket.tokens < 1) {
    // Rate limited — do NOT consume a token
    const msUntilToken = Math.ceil((1 - bucket.tokens) / refillRate);
    // Persist state (bucket is empty, don't let it over-drain)
    await env.RATE_KV.put(key, JSON.stringify(bucket), { expirationTtl: 120 });
    return { allowed: false, remaining: 0, resetAt, retryAfter: Math.ceil(msUntilToken / 1000) };
  }

  bucket.tokens -= 1;
  await env.RATE_KV.put(key, JSON.stringify(bucket), { expirationTtl: 120 });

  return { allowed: true, remaining: Math.floor(bucket.tokens), resetAt };
}

function rateLimitHeaders(
  limit: number,
  remaining: number,
  resetAt: number,
  retryAfter?: number
): Record<string, string> {
  const headers: Record<string, string> = {
    'X-RateLimit-Limit': String(limit),
    'X-RateLimit-Remaining': String(remaining),
    'X-RateLimit-Reset': String(Math.ceil(resetAt / 1000)), // Unix seconds
    'X-RateLimit-Policy': `${limit};w=60`,
  };
  if (retryAfter !== undefined) {
    headers['Retry-After'] = String(retryAfter);
  }
  return headers;
}

async function recordViolation(deviceId: string, path: string, env: Env): Promise<void> {
  // Fire-and-forget violation analytics
  await env.DB.prepare(
    `INSERT INTO rate_limit_violations (device_id, path, created_at)
     VALUES (?, ?, datetime('now'))`
  ).bind(deviceId, path).run();
}

// ── Middleware factory ────────────────────────────────────────────────────────
const app = new Hono<{ Bindings: Env }>();

app.use('*', async (c, next) => {
  const deviceId = c.req.header('X-Device-ID');

  // If no device ID, fall back to IP-based limiting
  const identity = deviceId ?? (c.req.header('CF-Connecting-IP') ?? 'unknown');
  const maxRpm = deviceId
    ? await resolveDeviceLimit(identity, c.env)
    : parseInt(c.env.LIMIT_FREE_RPM, 10);

  const { allowed, remaining, resetAt, retryAfter } = await consumeToken(
    identity,
    c.env,
    maxRpm
  );

  const headers = rateLimitHeaders(maxRpm, remaining, resetAt, retryAfter);

  if (!allowed) {
    if (deviceId) {
      // Non-blocking analytics write
      c.executionCtx.waitUntil(recordViolation(deviceId, c.req.path, c.env));
    }
    return c.json(
      {
        error: 'Too Many Requests',
        retryAfter,
        message: `Rate limit exceeded. Try again in ${retryAfter}s.`,
      },
      429,
      headers
    );
  }

  // Attach rate-limit headers to successful responses
  await next();
  Object.entries(headers).forEach(([k, v]) => c.res.headers.set(k, v));
});

// ── Sample protected route ────────────────────────────────────────────────────
app.get('/api/data', (c) => c.json({ data: 'your payload here' }));

export default app;
```

```sql
-- D1 migrations
CREATE TABLE IF NOT EXISTS device_plans (
  device_id TEXT PRIMARY KEY,
  plan      TEXT NOT NULL DEFAULT 'free',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_limit_violations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id  TEXT NOT NULL,
  path       TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_rlv_device_id   ON rate_limit_violations(device_id);
CREATE INDEX idx_rlv_created_at  ON rate_limit_violations(created_at);
```

```toml
# wrangler.toml
[vars]
LIMIT_FREE_RPM     = "60"
LIMIT_PRO_RPM      = "600"
BURST_MULTIPLIER   = "1.5"

[[kv_namespaces]]
binding = "RATE_KV"
id      = "<kv-namespace-uuid>"

[[d1_databases]]
binding       = "DB"
database_name = "example project-main"
database_id   = "<d1-uuid>"
```

## Implementation Details

- **Token bucket vs. fixed window**: Token bucket handles bursts naturally (up to `capacity = rpm * burstMultiplier`) while converging to the steady-state rate. Fixed windows can allow double the rate at window boundaries.
- **KV TTL**: The bucket key TTL is set to 120 seconds (2 × window). If the device is silent for 2 minutes, the KV entry expires and the next request starts with a full bucket — no manual cleanup needed.
- **Plan cache in KV**: Avoid hitting D1 on every request by caching the plan tier in KV with a 5-minute TTL (`plan:{deviceId}`).
- **`waitUntil` for analytics**: `c.executionCtx.waitUntil(...)` lets the violation insert happen after the 429 response is sent, keeping response latency low.
- **IP fallback**: If the mobile SDK does not send `X-Device-ID` (e.g., first launch before registration), the Worker falls back to `CF-Connecting-IP` with free-tier limits.

## Anti-patterns

- **Using KV for sub-second rate limiting**: KV has ~50–100 ms read latency at cold cache. For millisecond-granularity limits (e.g., 10 req/s), use Durable Objects with in-memory state.
- **Not setting a KV TTL**: Omitting TTL causes stale bucket entries to accumulate indefinitely. Always set `expirationTtl`.
- **Trusting `X-Device-ID` without verification**: A client can spoof any device ID. For production, verify the device ID against a cryptographic token (HMAC or JWT) to prevent bucket borrowing.
- **Blocking on violation analytics**: Writing to D1 synchronously before returning 429 adds latency. Always use `waitUntil`.
- **Counting tokens as float with high precision**: Floating-point drift over thousands of operations can cause tokens to creep. Floor/ceil at read and write.

## Gotchas

- KV is eventually consistent. In a burst of concurrent requests hitting different edge nodes, a device may briefly exceed its limit before the bucket state propagates. Accept ~5–10% overage on bursts; for strict enforcement use Durable Objects.
- The `expirationTtl` for KV values is in seconds, not milliseconds. Passing milliseconds (120000 instead of 120) silently sets a TTL far in the future.
- `c.executionCtx` is only available in Hono when the Worker is configured with `export default { fetch(req, env, ctx) }` or when Hono is initialized with the execution context. Check your Hono version for the correct context accessor.
- `CF-Connecting-IP` is always present in production but may be `undefined` in `wrangler dev` local mode.

## Verification

```bash
# 1. Hammer the endpoint and observe 429
for i in $(seq 1 70); do
  curl -s -o /dev/null -w "%{http_code} " \
    -H 'X-Device-ID: test-device-001' \
    https://example.com/api/data
done
# Expect: 200 x60 (with burst to ~90), then 429 with Retry-After header

# 2. Inspect bucket state in KV
npx wrangler kv key get --binding RATE_KV 'bucket:test-device-001'

# 3. Query violations
npx wrangler d1 execute example project-main \
  --command "SELECT device_id, count(*) FROM rate_limit_violations GROUP BY 1 ORDER BY 2 DESC LIMIT 10"

# 4. Check response headers
curl -i -H 'X-Device-ID: test-device-001' https://example.com/api/data | grep -i x-ratelimit
```

## Related

- `workers-biometric-auth-passkey-api.md` — protect auth endpoints with this rate limiter
- `workers-app-version-gating-kv.md` — gate rate limit tiers by app version
- `workers-deep-link-routing-universal-links.md` — protect deep link analytics endpoint

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/examples/rate-limiting/
- https://developers.cloudflare.com/durable-objects/ (for sub-second alternative)
- https://ietf-wg-httpapi.github.io/ratelimit-headers/draft-ietf-httpapi-ratelimit-headers.html
