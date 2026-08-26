# rate-limiting-ddos-defense-layers

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

An anonymous social platform receives a volumetric HTTP flood: 80,000
requests per second against `/api/feed`, saturating Workers CPU quota.
Simultaneously, a credential-stuffing campaign sends 1,200 login
attempts per minute from 400 rotating IPs. D1 query latency climbs to
8 seconds; P99 for authenticated users degrades to 12 seconds.
Cloudflare Analytics shows 94% of traffic from headless browsers with
no TLS fingerprint diversity.

## Context

No single control stops a determined volumetric attack against a
Workers-based API. Defense-in-depth layers each class of traffic at
the layer where it is cheapest to stop: Cloudflare WAF rules stop
zone-level floods before they reach Workers; Workers KV rate limiting
enforces per-user quotas at request time; Turnstile distinguishes
humans from bots on sensitive endpoints; IP reputation blocking
eliminates known-bad infrastructure.

## Layer 1 — Cloudflare WAF zone-level rate limiting

WAF rate limiting is enforced at the Cloudflare network edge before
the request enters a Worker. It is the cheapest layer and the first
line of defence against volumetric floods.

```bash
# Create a rate limit rule via API (or Dashboard:
# Security → WAF → Rate limiting rules)
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rate_limits" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "API flood protection",
    "match": { "request": { "url": "*/api/*" } },
    "threshold": 500,
    "period": 60,
    "action": { "mode": "challenge", "timeout": 300 },
    "bypass": [{ "name": "url", "value": "*/api/health" }]
  }'
```

Use threshold 60 req/60 s for authentication endpoints
(`/api/auth/login`), 500 req/60 s for general API paths. Action
`challenge` for moderate abuse; `ban` for credential stuffing.

## Layer 2 — Workers KV per-user rate limiting

KV-based rate limiting enforces per-user quotas inside the Worker
after WAF rules pass, using a sliding window counter.

```typescript
// workers/ratelimit.ts
export async function checkRateLimit(
  kv: KVNamespace,
  key: string,           // e.g. `rl:user:<userId>:post`
  limit: number,
  windowSec: number,
): Promise<{ allowed: boolean; remaining: number }> {
  const now = Math.floor(Date.now() / 1000);
  const wk = `${key}:${Math.floor(now / windowSec)}`;
  const raw = await kv.get(wk);
  const count = (raw ? parseInt(raw, 10) : 0) + 1;
  await kv.put(wk, String(count), { expirationTtl: windowSec * 2 });
  return { allowed: count <= limit, remaining: Math.max(0, limit - count) };
}

// In a Worker handler:
const { allowed, remaining } = await checkRateLimit(
  env.RATE_LIMIT_KV, `rl:user:${userId}:post`, 10, 60,
);
if (!allowed) {
  return new Response("Too Many Requests", {
    status: 429,
    headers: { "Retry-After": "60", "X-RateLimit-Remaining": "0" },
  });
}
```

Cloudflare's **Rate Limiting API** (Workers binding, beta) eliminates
manual KV counters — prefer it when available for your plan.

## Layer 3 — Turnstile for bot traffic

Turnstile issues a short-lived token the Worker validates server-side.
Deploy it on registration, login, and high-value mutation endpoints.

```typescript
async function verifyTurnstile(
  token: string, env: Env, ip: string
): Promise<boolean> {
  const res = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        secret: env.TURNSTILE_SECRET_KEY,
        response: token,
        remoteip: ip,
      }),
    },
  );
  const { success } = await res.json<{ success: boolean }>();
  return success;
}
```

Tokens are single-use with a 5-minute expiry. Always validate
server-side; the presence of the token field alone is not sufficient.

## Layer 4 — IP reputation blocking and DDoS runbook

Enable Cloudflare's IP reputation managed ruleset:
`Security → WAF → Managed rules → Cloudflare Managed Ruleset →
IP Reputation`

Reserve hard blocks for authentication and write paths. Avoid blocking
entire ASNs on read endpoints — this harms legitimate users on shared
infrastructure.

**DDoS response runbook (anonymous social platform):**

| Step | Action | ETA |
|---|---|---|
| 1 | Security Events → identify attack pattern | 2 min |
| 2 | Enable Under Attack Mode (IUAM) | 1 min |
| 3 | Add emergency WAF rule: 100 req/60 s on `/api/*` | 3 min |
| 4 | Identify top attacking ASNs in Security Analytics | 5 min |
| 5 | Block top ASNs on write paths only | 3 min |
| 6 | Ensure Turnstile is active on `/api/auth` | 5 min |
| 7 | Monitor D1 latency and Workers CPU until normal | ongoing |
| 8 | Disable IUAM after ≥30 min of stable traffic | — |
| 9 | Write post-incident note in `documentation/docs/policies/issues/` | 24 h |

Never disable Cloudflare proxying during an attack — this exposes the
origin IP. If origin IPs are leaked, rotate them.

## Anti-patterns

- Rate limiting only at the Worker level — Workers still consume CPU
  budget under floods; WAF rules are enforced before Workers run.
- Using a fixed window counter — allows 2× the intended rate at
  window boundaries; use sliding windows.
- Returning 200 OK for rate-limited requests — breaks RFC-compliant
  SDKs; always return 429 with `Retry-After`.
- Blocking entire countries on read endpoints — harms legitimate users
  and is rarely necessary with tuned WAF rules.

## Gotchas

- **KV eventual consistency.** KV counters can be read stale under
  very high concurrency, allowing bursts slightly above the limit.
  Use Durable Objects for strict per-user enforcement.
- **IUAM and API clients.** Under Attack Mode presents a JavaScript
  challenge; mobile apps and API clients cannot complete it. Exempt
  known API paths with a WAF bypass rule or Cloudflare Access service
  tokens.
- **WAF rate limits count by IP by default.** Behind shared NAT,
  many users share one IP. Set thresholds generously for GET
  endpoints; save strict limits for mutation paths.
- **Turnstile token reuse.** Server-side validation marks the token
  used; a replay returns `{ success: false }`.

## Verification

- 50 rapid-fire POSTs to `/api/auth/login` return 429 from attempt 11+.
- Cloudflare Security Analytics shows rate limit events during a
  load test from a single IP.
- A Turnstile-protected endpoint returns 400 when the token field is
  absent or invalid.
- IUAM can be toggled in the dashboard; challenge page renders
  without CSP errors.

## Related

- `security/rate-limiting-strategies.md`
- `security/ddos-mitigation-strategies.md`
- `security/credential-stuffing-account-takeover-defense.md`
- `cloudflare/turnstile-integration.md`
- `cloudflare/workers-kv-patterns.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/waf/rate-limiting-rules/
- https://developers.cloudflare.com/turnstile/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/ddos-protection/
- https://developers.cloudflare.com/workers/platform/limits/
