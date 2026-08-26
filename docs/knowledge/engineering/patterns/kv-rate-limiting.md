# kv-rate-limiting

**Issue:** Implementing per-IP and per-tenant rate limiting in Cloudflare Workers using KV
**Date:** 2026-08-11
**Status:** documented

## Symptom

An API endpoint is being hammered by bots or a runaway client. Need rate limiting
without an external Redis service — Workers KV is available.

## Basic sliding-window counter (KV)

```typescript
async function checkRateLimit(
  env: Env,
  key: string,
  limit: number,
  windowSec: number,
): Promise<{ allowed: boolean; remaining: number; resetAt: number }> {
  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - windowSec;
  const kvKey = `rl:${key}:${Math.floor(now / windowSec)}`;  // bucket per window

  const raw = await env.RATE_LIMIT!.get(kvKey);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= limit) {
    return { allowed: false, remaining: 0, resetAt: (Math.floor(now / windowSec) + 1) * windowSec };
  }

  // Increment — set TTL to window duration + 1s buffer
  await env.RATE_LIMIT!.put(kvKey, String(count + 1), { expirationTtl: windowSec + 1 });
  return { allowed: true, remaining: limit - count - 1, resetAt: (Math.floor(now / windowSec) + 1) * windowSec };
}
```

## Usage in handler

```typescript
export async function createControl(request: Request, env: Env): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);

  // Rate limit by tenant: 100 req/min
  const rl = await checkRateLimit(env, `tenant:${ctx.tenant.id}`, 100, 60);
  if (!rl.allowed) {
    return new Response(JSON.stringify({ error: 'rate_limited', reset_at: rl.resetAt }), {
      status: 429,
      headers: {
        'content-type': 'application/json',
        'retry-after': String(rl.resetAt - Math.floor(Date.now() / 1000)),
        'x-ratelimit-limit': '100',
        'x-ratelimit-remaining': '0',
        'x-ratelimit-reset': String(rl.resetAt),
      },
    });
  }

  // ... rest of handler
}
```

## IP-based rate limit (login endpoints)

Use IP for unauthenticated endpoints like login — no ctx available:

```typescript
const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
const rl = await checkRateLimit(env, `ip:${ip}:login`, 10, 300);  // 10/5min per IP
```

## Dual limit — both IP and tenant

For sensitive endpoints, apply both limits:

```typescript
const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
const [ipRl, tenantRl] = await Promise.all([
  checkRateLimit(env, `ip:${ip}`, 200, 60),
  checkRateLimit(env, `tenant:${ctx.tenant.id}`, 500, 60),
]);
if (!ipRl.allowed || !tenantRl.allowed) {
  return rateLimitResponse(Math.min(ipRl.resetAt, tenantRl.resetAt));
}
```

## Gotchas

- **KV is eventually consistent**: Two concurrent requests in the same millisecond can both read `0` and both write `1`. At scale, KV rate limiting slightly over-allows. For strict limits, use Durable Objects.
- **Fixed-window vs sliding**: The bucket-per-window approach is fixed-window — a client can burst 2× the limit at the window boundary (end of window N + start of window N+1). For most use cases this is acceptable; for strict burst control, use Durable Objects with a sliding window.
- **KV write latency**: `put` is async and takes ~10ms. Don't block the response on it for non-critical limits — `await` it before responding only for hard limits.
- **Key namespace**: Use a descriptive prefix (`rl:`, `ip:`, `tenant:`) to avoid collisions with other KV uses.
- **RATE_LIMIT env binding**: Must be declared in `wrangler.toml` as a KV namespace binding AND in your `Env` interface as `RATE_LIMIT?: KVNamespace`.
- **Cloudflare Rate Limiting rules**: For high-volume protection (DDoS), prefer Cloudflare WAF rate limiting rules (configured in the dashboard) over KV — they fire at the edge before the Worker runs.

## Durable Objects alternative (strict)

For strict sliding-window limits, use a Durable Object:

```typescript
// Rate limiter Durable Object
export class RateLimiter {
  state: DurableObjectState;
  constructor(state: DurableObjectState) { this.state = state; }
  async fetch(request: Request): Promise<Response> {
    const { limit, window } = await request.json<{ limit: number; window: number }>();
    const now = Date.now();
    const timestamps: number[] = (await this.state.storage.get('ts') ?? []) as number[];
    const valid = timestamps.filter(t => t > now - window * 1000);
    if (valid.length >= limit) return new Response('limited', { status: 429 });
    valid.push(now);
    await this.state.storage.put('ts', valid);
    return new Response('ok');
  }
}
```

## Related

- `workers-types-migration.md`
- `typescript-route-handler.md`
- `mccontext-gate-pattern.md`
- `cloudflare-durable-objects-patterns.md`
