# Workers Rate Limit Bypass Mitigation Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have deployed rate limiting on a Cloudflare Worker (via Durable Objects, the built-in
`rate_limit` binding, or KV counters) but you are seeing bypass attempts:

- Attackers rotate IPs or use residential proxies, evading per-IP limits.
- `X-Forwarded-For` or `CF-Connecting-IP` headers are spoofed or missing.
- API keys are shared across multiple clients to pool requests under one limit.
- Attackers split load across many low-traffic paths that each fall under the threshold.

This article catalogs the most common bypass vectors and shows hardened Workers patterns
that close each gap.

---

## Context

Rate limiting is only as strong as its **key**. A key that an attacker can forge, rotate,
or distribute nullifies the limit. The mitigations below focus on making the key
unforgeable and the limit meaningful even under adversarial conditions.

Cloudflare provides several enforcement layers:

1. **Cloudflare Rate Limiting rules** (WAF layer) — applied before the Worker runs.
2. **Workers `rate_limit` binding** — first-party, backed by Cloudflare's internal
   counters; the key is set by the Worker.
3. **Durable Objects sliding-window counters** — full control, highest flexibility.

All three are vulnerable to key-manipulation if the Worker is not careful about what it
uses as the rate-limit key.

---

## Vector 1: IP Spoofing via X-Forwarded-For

### The Problem

A Worker reading `request.headers.get('X-Forwarded-For')` for the client IP can be
tricked into using a fake IP inserted by the client.

### The Fix

Always use `request.headers.get('CF-Connecting-IP')` or the Cloudflare-provided
`cf.ip` from the `IncomingRequestCfProperties` object. Cloudflare strips and overwrites
`CF-Connecting-IP` at the edge — it cannot be spoofed by the client.

```typescript
// src/rate-key.ts
export function getRateLimitKey(request: Request): string {
  // CF-Connecting-IP is set by Cloudflare's network — not client-controlled
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  return `ip:${ip}`;
}

// Combine IP + path prefix for per-endpoint limits
export function getEndpointKey(request: Request): string {
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const url = new URL(request.url);
  // Normalise path to strip user-specific segments
  const prefix = url.pathname.split('/').slice(0, 3).join('/');
  return `ep:${ip}:${prefix}`;
}
```

---

## Vector 2: API Key Sharing / Key Pool Distribution

### The Problem

Multiple clients share a single API key to collectively exceed per-key limits that would
block an individual. Each client stays under threshold; the aggregate load is harmful.

### The Fix

Rate limit by **API key**, not by IP. Tie the limit to the authenticated identity so the
key holder is responsible for the full load:

```typescript
// src/key-rate-limit.ts
import type { Env } from './env';

export async function checkApiKeyRateLimit(
  request: Request,
  env: Env,
): Promise<Response | null> {
  const authHeader = request.headers.get('Authorization') ?? '';
  const apiKey = <redacted-secret>'Bearer ') ? authHeader.slice(7) : null;

  if (!apiKey) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Hash the key so it's safe to use as a KV key
  const keyHash = await hashApiKey(apiKey);
  const limitKey = `apikey:${keyHash}`;

  const { success } = await env.RATE_LIMITER.limit({ key: limitKey });
  if (!success) {
    return new Response('Too Many Requests', {
      status: 429,
      headers: { 'Retry-After': '60' },
    });
  }

  return null; // no rate limit hit — continue
}

async function hashApiKey(key: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
  return btoa(String.fromCharCode(...new Uint8Array(buf))).slice(0, 32);
}
```

---

## Vector 3: Path Variation to Evade Per-Path Limits

### The Problem

`/api/search?q=a`, `/api/search?q=b`, `/api/search?q=c` are treated as three different
paths by naive routing-based limiters even though they all hit the same handler.

### The Fix

Normalise the rate limit key to the **handler identifier**, not the raw URL. Strip query
parameters and dynamic path segments:

```typescript
// src/route-normalizer.ts
const DYNAMIC_SEGMENT = /\/[0-9a-f-]{8,}|\/\d+/g;

export function normalizeRoute(url: URL): string {
  // Remove query string and dynamic ID segments
  const path = url.pathname.replace(DYNAMIC_SEGMENT, '/:id');
  return `${url.hostname}:${path}`;
}

// Usage in a Worker
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    const routeKey = `${ip}:${normalizeRoute(url)}`;

    const { success } = await env.RATE_LIMITER.limit({ key: routeKey });
    if (!success) return new Response('Too Many Requests', { status: 429 });

    return handleRequest(request, env);
  },
};
```

---

## Vector 4: Distributed Low-Rate Attacks

### The Problem

An attacker runs thousands of IPs each under the threshold. No single IP triggers the
limit, but the aggregate causes damage (e.g., credential stuffing at 1 attempt / IP / min).

### The Fix

Combine **per-IP limits** with **global resource limits** and **account lockout** keyed
to the target resource (username, email):

```typescript
// src/login-rate-limit.ts
import type { Env } from './env';

export async function checkLoginRateLimit(
  request: Request,
  env: Env,
  targetEmail: string,
): Promise<Response | null> {
  const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';

  // Key 1: per-IP limit (5 login attempts / minute)
  const ipKey = `login:ip:${ip}`;
  // Key 2: per-target-account limit (10 attempts / 5 minutes — across all IPs)
  const emailHash = await sha256Hex(targetEmail.toLowerCase());
  const accountKey = `login:account:${emailHash}`;

  const [ipResult, accountResult] = await Promise.all([
    env.RATE_LIMITER.limit({ key: ipKey }),
    env.RATE_LIMITER.limit({ key: accountKey }),
  ]);

  if (!ipResult.success || !accountResult.success) {
    return new Response('Too Many Requests', {
      status: 429,
      headers: { 'Retry-After': '300' },
    });
  }

  return null;
}

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Vector 5: Timing the Window Reset

### The Problem

Fixed-window counters reset at predictable intervals (e.g., every 60 s on the minute).
An attacker sends a burst just before and just after the reset, effectively doubling their
allowed rate.

### The Fix

Use a **sliding window** algorithm. The Cloudflare `rate_limit` binding uses a sliding
window internally. If you are building your own counter in a Durable Object, use the
standard two-bucket approximation:

```typescript
// src/sliding-window.ts — inside a Durable Object
const WINDOW_SECONDS = 60;
const MAX_REQUESTS = 100;

interface WindowState {
  currentCount: number;
  currentWindowStart: number;
  previousCount: number;
}

export function slidingWindowAllow(state: WindowState, nowMs: number): boolean {
  const nowSec = nowMs / 1000;
  const windowStart = Math.floor(nowSec / WINDOW_SECONDS) * WINDOW_SECONDS;

  if (windowStart > state.currentWindowStart) {
    // Rolled into a new window
    state.previousCount = state.currentCount;
    state.currentCount = 0;
    state.currentWindowStart = windowStart;
  }

  const elapsed = nowSec - windowStart;
  const weightedCount =
    state.previousCount * (1 - elapsed / WINDOW_SECONDS) + state.currentCount;

  if (weightedCount >= MAX_REQUESTS) return false;

  state.currentCount++;
  return true;
}
```

---

## Vector 6: Header Injection to Override the Rate Limit Response

### The Problem

Some middleware trusts a downstream `X-RateLimit-Bypass: true` header set by an internal
service — an attacker forges this header externally.

### The Fix

Never trust bypass headers from external requests. If internal services need to bypass
limits, use **Cloudflare Service Bindings** (which never expose the Worker to the
Internet) rather than a header:

```typescript
// src/internal-check.ts
export function isInternalServiceBinding(request: Request): boolean {
  // Service bindings arrive without CF-Ray and with a special internal header
  // that cannot be set by external clients
  // Better: use a separate Worker path only bound via service bindings
  return request.headers.has('X-Internal-Service-Token')
    && request.headers.get('CF-Worker') !== null;
}

// Preferred: gate bypass logic entirely behind a service binding
// wrangler.toml: [[services]] binding = "INTERNAL" service = "my-internal-worker"
export async function fetchViaBinding(env: Env, path: string) {
  return env.INTERNAL.fetch(`https://internal${path}`);
}
```

---

## Anti-patterns

- **Keying on `User-Agent`.** Trivially rotated by any HTTP client.
- **Keying on `X-Forwarded-For`.** Client-controlled; can be set to an arbitrary IP.
- **Using a fixed-window counter with a publicly known reset time.** Enables burst-around-
  reset attacks.
- **Rate limiting only at the route level, not the resource level.** An attacker hammering
  `/login` on 1000 different usernames uses 1 request per route key per account.
- **Returning the internal key in the error response.** A `Retry-After` header is fine;
  leaking the key string helps the attacker probe key construction.

---

## Gotchas

- The Cloudflare `rate_limit` binding is eventually consistent across edge nodes — for
  very short windows (< 1 s), you may see slightly more than the limit. For security-
  sensitive endpoints, add a second Durable Object check for strict consistency.
- `CF-Connecting-IP` is only set when the request arrives via Cloudflare's network. In
  local `wrangler dev` the header is absent; stub it in your test fixture.
- The `rate_limit` binding's key is hashed internally — you can use the raw email address
  as the key; Cloudflare does not expose counter values, only `{ success: boolean }`.
- Setting `Retry-After` does not prevent the client from ignoring it. It is informational.

---

## Verification

```bash
# Validate that per-account lockout kicks in regardless of IP rotation
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-Forwarded-For: 10.0.0.$i" \
    -X POST https://api.example.com/login \
    -d '{"email":"victim@example.com","password":"wrong"}'
done
# Expect the first 10 to return 401 (wrong password), subsequent to return 429
```

---

## Related

- `rate-limiting-sliding-window-durable-objects.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `token-bucket-rate-limiting-durable-objects.md`
- `cloudflare-rate-limiting-v2-api-abuse-prevention.md`
- `credential-stuffing-account-takeover-defense.md`
- `x-forwarded-for-client-ip-spoofing.md`

---

## Sources

- Cloudflare rate limiting binding — https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- Cloudflare WAF rate limiting rules — https://developers.cloudflare.com/waf/rate-limiting-rules/
- OWASP Testing for Weak Lock Out Mechanism — https://owasp.org/www-project-web-security-testing-guide/
- RFC 6585 Additional HTTP Status Codes (429) — https://datatracker.ietf.org/doc/html/rfc6585
