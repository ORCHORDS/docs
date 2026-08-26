# Cloudflare Rate Limiting v2 Rules vs Workers-Side Rate Limiting

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You need to rate-limit an API endpoint.  You can configure a Rate Limiting rule in the
Cloudflare dashboard (the "Rate Limiting v2" product under Security → WAF) **or** implement
counting logic inside a Durable Object or Workers KV.  This article explains when to use
each approach, what Rate Limiting v2 actually guarantees, where it falls short, and how to
combine both layers for production-grade enforcement.

## Context

### Rate Limiting v2 (Rules-based)

Cloudflare's current-generation rate limiting is built on the Rules engine — the same
engine that powers WAF Custom Rules, Transform Rules, and Redirect Rules.  It replaced the
legacy "Rate Limiting" product (available before 2022) which was configured through a
separate UI and API endpoint.

Key characteristics:
- Evaluated **before** a request reaches your Worker or origin.
- Counts are maintained **per Cloudflare PoP** (not globally) by default; a token may be
  shared across the small cluster of machines in a PoP.
- Counting period: 10 s, 1 min, 2 min, 5 min, 10 min.
- Actions: Block, Managed Challenge, JS Challenge, Log only.
- Available on **Pro and above** plans (varies by action type).
- Score (sliding window) or Fixed window counting available.

### Workers-side rate limiting

Implemented in your own Worker using:
- **Durable Objects** — exact, globally consistent counting via SQLite or in-memory state.
- **Workers KV** — eventually consistent; susceptible to race conditions under load.
- **Cloudflare Rate Limiting binding** (`RateLimit`) — a new binding type
  (available 2024+) that wraps a managed rate limiter accessible from a Worker without
  writing your own Durable Object counter.

### The `RateLimit` binding (Workers Rate Limiting API)

This is a first-class binding introduced to give Workers access to a managed,
PoP-distributed counter without deploying Durable Objects:

```toml
# wrangler.toml
[[unsafe.bindings]]
type       = "ratelimit"
name       = "MY_RATE_LIMITER"
namespace_id = "1001"          # arbitrary integer, unique per limiter in this Worker
simple = { limit = 100, period = 60 }   # 100 requests per 60 seconds per key
```

```typescript
interface Env {
  MY_RATE_LIMITER: RateLimit;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const { success } = await env.MY_RATE_LIMITER.limit({ key: ip });

    if (!success) {
      return new Response("Rate limit exceeded", {
        status: 429,
        headers: { "Retry-After": "60" },
      });
    }

    return handleRequest(request, env);
  },
};
```

The `RateLimit` binding has the same PoP-level counting semantics as Rules-based rate
limiting.  It is **not** globally exact, but it is the lowest-overhead option for
per-Worker rate limiting.

## Section 1 — Rate Limiting v2 Rules Configuration

### Via Dashboard

Security → WAF → Rate Limiting Rules → Create rule.

Expression:
```
(http.request.uri.path matches "^/api/") and (http.request.method eq "POST")
```

Characteristics (what to count per):
- IP address (`ip.src`)
- IP + path (`ip.src` + `http.request.uri.path`)
- JA3 fingerprint (TLS fingerprint, useful for bot traffic)
- Cookie value (`http.cookie`)
- Header value (`http.request.headers["X-User-ID"]`)
- Country (`ip.geoip.country`)

Threshold: 50 requests per 60 seconds per characteristic.
Action: Block for 60 seconds.

### Via Terraform

```hcl
resource "cloudflare_ruleset" "rate_limiting" {
  zone_id     = var.zone_id
  name        = "API Rate Limiting"
  description = "Rate limit POST /api/* by IP"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = "{\"error\":\"rate_limit_exceeded\"}"
      }
    }

    ratelimit {
      characteristics    = ["ip.src"]
      period             = 60      # seconds
      requests_per_period = 50
      mitigation_timeout = 60
      counting_expression = "(http.request.uri.path matches \"^/api/\")"
    }

    expression  = "(http.request.uri.path matches \"^/api/\")"
    description = "50 req/min per IP on /api/*"
    enabled     = true
  }
}
```

## Section 2 — Durable Object Rate Limiter (Global Exact Counting)

When you need **globally exact** rate limiting — e.g., a user cannot exceed their billing
quota regardless of which PoP they hit — use a Durable Object:

```toml
# wrangler.toml
[[durable_objects.bindings]]
name       = "RATE_LIMITER"
class_name = "RateLimiterDO"

[[migrations]]
tag           = "v1"
new_classes   = ["RateLimiterDO"]
```

```typescript
// src/rate-limiter-do.ts
export class RateLimiterDO implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const { limit, window, key } = await request.json() as {
      limit: number;
      window: number;    // seconds
      key: string;
    };

    const now = Date.now();
    const windowStart = now - window * 1000;

    // SQLite storage for atomic updates
    const count = await this.state.storage.get<number>(`count:${key}`) ?? 0;
    const resetAt = await this.state.storage.get<number>(`reset:${key}`) ?? 0;

    if (resetAt < now) {
      // Window expired — reset
      await this.state.storage.put(`count:${key}`, 1);
      await this.state.storage.put(`reset:${key}`, now + window * 1000);
      return Response.json({ allowed: true, remaining: limit - 1 });
    }

    if (count >= limit) {
      return Response.json({
        allowed: false,
        remaining: 0,
        retryAfter: Math.ceil((resetAt - now) / 1000),
      });
    }

    await this.state.storage.put(`count:${key}`, count + 1);
    return Response.json({ allowed: true, remaining: limit - count - 1 });
  }
}
```

```typescript
// src/worker.ts — calling the DO
interface Env {
  RATE_LIMITER: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const userId = getUserId(request);  // from JWT or session
    if (!userId) return new Response("Unauthorized", { status: 401 });

    // Route to a DO shard keyed by userId
    const id = env.RATE_LIMITER.idFromName(`user:${userId}`);
    const stub = env.RATE_LIMITER.get(id);

    const result = await stub.fetch(new Request("https://do/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 1000, window: 3600, key: userId }),
    }));

    const { allowed, remaining, retryAfter } = await result.json() as {
      allowed: boolean;
      remaining: number;
      retryAfter?: number;
    };

    if (!allowed) {
      return new Response("Quota exceeded", {
        status: 429,
        headers: { "Retry-After": String(retryAfter ?? 60) },
      });
    }

    const resp = await handleRequest(request, env);
    resp.headers.set("X-RateLimit-Remaining", String(remaining));
    return resp;
  },
};
```

## Section 3 — Decision Matrix

| Requirement | Use CF Rate Limiting v2 | Use `RateLimit` binding | Use Durable Object |
|---|---|---|---|
| Block before Worker runs | Yes | No | No |
| Per-IP limiting | Yes | Yes | Yes |
| Per-user (JWT claim) limiting | No (no JWT decode) | Yes | Yes |
| Per-tenant quota (exact) | No | No | Yes |
| Globally consistent count | No | No | Yes |
| < 1 ms overhead | Yes | Yes | No (~5–20 ms DO call) |
| Handles 100k+ rps | Yes | Yes | Yes (with sharding) |
| Custom 429 response body | Yes (via action params) | Yes (in Worker) | Yes (in Worker) |
| Counting across multiple paths | Yes (`counting_expression`) | Yes (custom key) | Yes |
| Visibility in Cloudflare Analytics | Yes | Partial (Workers metrics) | No |
| Mobile-specific limits | No (rate rules don't decode UA) | Yes (check `cf.deviceType`) | Yes |

## Section 4 — Layered Strategy (Recommended Production Setup)

Use Rules-based rate limiting as a coarse **first line of defense** (blocks obvious abuse
at the edge, before your Worker spends CPU), and Durable Object counting as the **precise
business-logic enforcement** layer:

```
Request
  │
  ▼
[CF Rate Limiting v2 Rule]
  │ Block: >500 req/min per IP → 429 (no Worker invocation, minimal cost)
  │ Pass: normal traffic
  ▼
[Worker fetch handler]
  │
  ├─ Extract user ID from JWT
  ├─ Call Durable Object: check user's hourly API quota
  │   └─ Exceeded → return 429 with X-RateLimit-Remaining: 0
  │
  └─ Handle request normally
```

This layered approach means:
- Bots and scanners are blocked at the rules layer without burning Worker CPU or DO budget.
- Legitimate users who hit their per-user quota get a precise 429 with correct remaining
  count.
- Pricing / metering is enforced exactly by the DO, not approximate PoP-level counts.

## Mobile vs Desktop Considerations

- **CF Rate Limiting v2 and iCloud Private Relay** — iOS users behind Private Relay appear
  to come from Apple's proxy IP ranges.  Rate limiting by `ip.src` will inadvertently group
  many legitimate iOS users under the same counter.  Add `or ip.geoip.country eq "US"`
  exclusions, or use a higher threshold for known Apple egress ranges.  See
  `icloud-private-relay-geolocation-rate-limiting.md` for the full treatment.
- **Mobile API retries** — mobile apps often retry on 429 with exponential backoff but
  sometimes with jitter that causes thundering herd.  Return `Retry-After` in both your
  Rules 429 response and your Worker 429 response.  Cloudflare Rate Limiting v2 supports
  a custom response body; include `{"retry_after": N}` for SDK-aware clients.
- **Device-type-aware limits in Workers** — the `RateLimit` binding key can include device
  type; mobile clients can get a higher limit for burst traffic on spotty connections:

```typescript
const deviceType = (request.cf as IncomingRequestCfProperties)?.deviceType ?? "desktop";
const key = `${userId}:${deviceType}`;
const { success } = await env.MY_RATE_LIMITER.limit({ key });
```

## Anti-patterns

- **Using KV for rate limiting counters** — KV is eventually consistent; two simultaneous
  requests from different PoPs can both read `count=49`, both increment to `50`, and both
  succeed when the limit is 50.  This is not a race-safe counter.
- **One Durable Object for all users** — a single DO is a single-threaded hot spot.  Shard
  by user ID prefix or use `idFromName(userId)` so each user gets their own DO instance.
- **Relying on `CF-Connecting-IP` for rate limiting inside a Worker without header
  validation** — if your Worker is reachable directly (not behind Cloudflare proxy), this
  header can be spoofed.  Ensure `proxied = true` on your DNS record.
- **Setting mitigation_timeout shorter than period** — a mitigation timeout of 10 s with a
  60 s counting window means the block lifts before the window resets; an attacker can re-
  enter the limit immediately.  Set `mitigation_timeout >= period`.

## Gotchas

- **Rate Limiting v2 counts are approximate** — Cloudflare documents that counts are
  per-PoP and may allow slightly more than the threshold in some cases.  Do not rely on
  this for billing-exact metering.
- **`counting_expression` vs `expression`** — the `expression` determines which requests
  the rule *applies to* (i.e., can be blocked); `counting_expression` determines which
  requests *increment the counter*.  They can differ: you might count all `/api/` requests
  but only block `POST` requests once the limit is hit.
- **Legacy Rate Limiting API** — the old `/zones/{zone_id}/rate_limits` REST endpoint
  manages the deprecated product.  New rules must use the Rulesets API
  (`/zones/{zone_id}/rulesets/phases/http_ratelimit/entrypoint`).
- **`RateLimit` binding `namespace_id`** — this is a local integer (1–Int32), not a
  Cloudflare resource ID.  Different namespace_ids in the same Worker create independent
  counters.  They are not shared across Workers.
- **DO rate limiter cold starts** — a Durable Object that has never been invoked has a
  ~50–100 ms startup latency on the first call.  For high-frequency APIs this is a one-time
  hit; for low-frequency APIs it can recur.  Consider keeping the DO warm with a scheduled
  Worker ping.

## Verification

```bash
# 1. Check active rate limiting rules
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/http_ratelimit/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.rules[] | {description, enabled}'

# 2. Load-test to trigger the rule (use a controlled environment)
npx autocannon -c 10 -d 10 -m POST https://api.example.com/api/test
# Expect 429 responses after threshold is reached

# 3. Check rate limiting analytics in the dashboard
# Security → Analytics → filter by "Rate Limit" action

# 4. Verify Durable Object counting
npx wrangler tail my-worker --format=pretty | grep "remaining"

# 5. Confirm Retry-After header is present on 429
curl -sv -X POST https://api.example.com/api/test 2>&1 | grep -i "retry-after"
```

## Related

- `waf-rate-limiting-deep-dive.md` — WAF rules and rate limiting overlap
- `rate-limiting-cgnat-mobile-fingerprinting.md` — CGNAT / mobile carrier grouping
- `durable-objects-best-practices.md` — DO sharding and performance
- `icloud-private-relay-geolocation-rate-limiting.md` — Apple Private Relay IP ranges
- `workers-resource-limits.md` — CPU and memory limits during DO calls
- `kv-eventually-consistent.md` — why KV is wrong for counters

## Sources

- Cloudflare Rate Limiting v2: https://developers.cloudflare.com/waf/rate-limiting-rules/
- Rulesets API (rate limiting phase): https://developers.cloudflare.com/ruleset-engine/rulesets/phase-rulesets/
- Workers Rate Limiting binding: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- Durable Objects: https://developers.cloudflare.com/durable-objects/
- iCloud Private Relay IP ranges: https://mask-api.icloud.com/egress-ip-ranges.csv
