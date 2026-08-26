# API Abuse Prevention with Cloudflare Rate Limiting v2

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Cloudflare Workers API is being abused in one or more of these patterns:

- **Credential stuffing**: High-volume POST requests to `/api/auth/login` testing leaked username/password pairs.
- **Scraping**: Authenticated or unauthenticated enumeration of `/api/products`, `/api/users/:id`, or similar endpoints at rates no human user reaches.
- **Denial-of-wallet**: Repeated requests to expensive Worker routes that trigger paid AI API calls, heavy D1 queries, or R2 reads, inflating your bill.
- **API key brute force**: Sequential guessing of numeric API key suffixes against `/api/key/validate`.
- **Abuse of free tier**: Automated accounts hammering trial or freemium endpoints to extract value beyond intended limits.

Cloudflare Rate Limiting v2 (released 2023, generally available 2024) replaces the legacy v1 product with a WAF-style rule engine that integrates with the full Cloudflare request pipeline, supports compound characteristics (IP + cookie + header + body field), and is configurable as code via Terraform and the Cloudflare API.

## Context

Rate Limiting v2 differs from the legacy product in several important ways:

| Feature                  | Legacy v1                       | v2 (current)                          |
|--------------------------|----------------------------------|---------------------------------------|
| Configuration            | Dashboard only                   | Terraform, API, dashboard             |
| Counting characteristics | IP address only (by default)     | IP, ASN, cookie, header, query param, body field, JA3 fingerprint, country |
| Rule expression          | URL pattern matching             | Wireshark-style filter expressions    |
| Mitigation actions       | Block, challenge                 | Block, challenge, managed challenge, rate-limit response, log |
| Period granularity       | 1s, 10s, 1m, 10m, 1h            | 10s, 1m, 2m, 5m, 10m, 1h            |
| Workers integration      | None                             | `RateLimiter` binding in Workers      |
| Bypass rules             | Not supported                    | `Skip` action via WAF rule ordering   |

Rate Limiting v2 rules run in the Cloudflare network layer, **before** your Worker code executes, making them significantly cheaper and faster for high-volume attack mitigation. The Workers `RateLimiter` API provides a complementary in-Worker rate limiting primitive for cases where you need per-user or per-operation granularity that the network layer cannot see.

## Configuring v2 Rules via Terraform

```hcl
# terraform/rate-limiting.tf

resource "cloudflare_ruleset" "api_rate_limits" {
  zone_id = var.zone_id
  name    = "API Rate Limiting Rules"
  kind    = "zone"
  phase   = "http_ratelimit"

  # Rule 1: Login endpoint — 5 requests per 60s per IP
  rules {
    action = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = jsonencode({
          error   = "rate_limit_exceeded"
          message = "Too many login attempts. Try again in 60 seconds."
        })
      }
    }
    ratelimit {
      characteristics    = ["cf.unique_visitor_id"]  # IP + User-Agent fingerprint
      period             = 60
      requests_per_period = 5
      mitigation_timeout = 60
    }
    expression  = "(http.request.uri.path eq \"/api/auth/login\" and http.request.method eq \"POST\")"
    description = "Throttle login attempts to 5/min per visitor"
    enabled     = true
  }

  # Rule 2: API key validation — 10 per 60s per IP
  rules {
    action = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = jsonencode({ error = "rate_limit_exceeded" })
      }
    }
    ratelimit {
      characteristics    = ["ip.src"]
      period             = 60
      requests_per_period = 10
      mitigation_timeout = 300  # 5-minute block after threshold
    }
    expression  = "http.request.uri.path eq \"/api/key/validate\""
    description = "Block API key brute force"
    enabled     = true
  }

  # Rule 3: Authenticated scraping — 300 requests per 60s per authenticated user
  # Uses the Authorization header value as the counting characteristic
  rules {
    action = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = jsonencode({ error = "quota_exceeded" })
      }
    }
    ratelimit {
      characteristics    = ["http.request.headers[\"authorization\"]"]
      period             = 60
      requests_per_period = 300
      mitigation_timeout = 60
    }
    expression  = "(http.request.uri.path matches \"^/api/\" and http.request.headers[\"authorization\"] ne \"\")"
    description = "Per-token API quota 300 req/min"
    enabled     = true
  }

  # Rule 4: Expensive AI endpoint — 10 per 600s per IP
  rules {
    action = "managed_challenge"
    ratelimit {
      characteristics    = ["ip.src", "cf.colo.id"]
      period             = 600
      requests_per_period = 10
      mitigation_timeout = 600
    }
    expression  = "http.request.uri.path eq \"/api/generate\""
    description = "Protect expensive AI endpoint from denial-of-wallet"
    enabled     = true
  }
}
```

## Workers RateLimiter Binding

For finer-grained control inside Worker logic — per-user-ID limits that are invisible to the network layer — use the `RateLimiter` binding introduced in Workers v3:

```toml
# wrangler.toml
[[unsafe.bindings]]
name = "API_LIMITER"
type = "ratelimit"
namespace_id = "1001"        # arbitrary integer namespace per logical limiter
simple = { limit = 100, period = 60 }  # 100 requests per 60 seconds
```

```typescript
// src/index.ts
interface Env {
  API_LIMITER: RateLimit;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authHeader = request.headers.get('Authorization') ?? '';
    const userId = extractUserId(authHeader);  // your JWT/API-key parsing

    if (!userId) {
      return Response.json({ error: 'unauthorized' }, { status: 401 });
    }

    // Check per-user rate limit — key on user ID, not IP
    const { success } = await env.API_LIMITER.limit({ key: userId });
    if (!success) {
      return Response.json(
        { error: 'rate_limit_exceeded', retry_after: 60 },
        {
          status: 429,
          headers: {
            'Retry-After': '60',
            'X-RateLimit-Limit':     '100',
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset':     String(Math.ceil(Date.now() / 1000) + 60),
          },
        }
      );
    }

    // ... business logic ...
    return Response.json({ ok: true });
  },
};

function extractUserId(authHeader: string): string | null {
  // Simplified — use your actual JWT verification
  if (!authHeader.startsWith('Bearer ')) return null;
  try {
    const payload = JSON.parse(atob(authHeader.split('.')[1]));
    return payload.sub ?? null;
  } catch {
    return null;
  }
}
```

## Layered Rate Limiting Strategy

Effective API abuse prevention combines multiple layers. Apply them in order from cheapest to most granular:

```
Request →
  [1] Network layer: Cloudflare v2 rule — IP-based login throttle (free, pre-Worker)
      ↓ passes
  [2] Network layer: Cloudflare v2 rule — token-based authenticated quota
      ↓ passes
  [3] Worker RateLimiter: per-user-ID quota using Workers binding
      ↓ passes
  [4] Worker logic: per-operation limits (e.g., max 5 concurrent AI generations per user)
      using Durable Objects counter
      ↓ passes
  [5] Downstream: D1 / R2 / AI binding — final safety net
```

Layer 1 and 2 block most attacks with zero Worker CPU cost. Layer 3 handles authenticated abuse that shares an IP (shared office NAT, VPN exit nodes). Layer 4 protects the most expensive operations.

## Sliding Window Counter in Durable Objects (Layer 4)

For the most precise per-user, per-operation control with sub-second granularity:

```typescript
// src/operation-limiter.ts — Durable Object
export class OperationLimiter {
  private state: DurableObjectState;
  private readonly windowMs = 60_000;
  private readonly maxOps   = 5;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();

    // Load existing request timestamps
    let timestamps: number[] = (await this.state.storage.get<number[]>('ts')) ?? [];

    // Evict timestamps outside the window
    timestamps = timestamps.filter(t => now - t < this.windowMs);

    if (timestamps.length >= this.maxOps) {
      const resetAt = Math.min(...timestamps) + this.windowMs;
      return Response.json({
        allowed: false,
        retry_after: Math.ceil((resetAt - now) / 1000),
      });
    }

    timestamps.push(now);
    await this.state.storage.put('ts', timestamps);

    return Response.json({ allowed: true, remaining: this.maxOps - timestamps.length });
  }
}
```

## Detecting Distributed Attacks (High ASN Diversity)

When attackers rotate IPs across many ASNs, per-IP limits are insufficient. Use Cloudflare's WAF analytics to detect the pattern, then switch to a CAPTCHA or Turnstile challenge:

```hcl
# Add a rule that triggers managed challenge when the endpoint is under sustained load
# regardless of individual IP rates — signals distributed attack
resource "cloudflare_ruleset" "distributed_attack_response" {
  zone_id = var.zone_id
  name    = "Distributed Attack Mitigation"
  kind    = "zone"
  phase   = "http_request_firewall_managed"

  rules {
    action = "managed_challenge"
    # This uses Cloudflare's ML-based bot score — score < 30 = likely bot
    expression  = "(cf.bot_management.score lt 30 and http.request.uri.path matches \"^/api/\")"
    description = "Challenge likely bots on API endpoints"
    enabled     = true
  }
}
```

## Anti-patterns

**Do not rely solely on IP-based rate limiting.** IPv6 prefix rotation, residential proxy networks, and shared office NAT all make IP-based limits either too aggressive (blocking legitimate users) or too permissive (individual IPs send fewer requests than the threshold while the total attack volume is high). Layer IP limits with token-based and behavior-based signals.

**Do not set `mitigation_timeout` to 0.** A zero timeout means the limiter counts requests but never blocks. This is a valid "log only" mode for testing, but it must be explicitly intentional — many accidental misconfiguration reports stem from omitting this field.

**Do not create rate limits that reset on the exact minute boundary.** Attackers exploit fixed-window resets by sending bursts at :59 and :01. Use the Workers `RateLimiter` binding (which uses a sliding window internally) or implement your own sliding window in Durable Objects.

**Do not apply rate limits to health-check endpoints.** `/health`, `/ping`, and `/metrics` endpoints are typically polled by load balancers at high rates. Exempt them explicitly with a "Skip" WAF rule positioned before the rate limit rules.

**Do not forget to test in `log` mode before enabling `block`.** Set `action = "log"` first, monitor the Cloudflare Firewall Events dashboard for at least 24 hours, confirm you are not blocking legitimate traffic, then switch to `block`.

## Gotchas

- **v2 billing**: Rate Limiting v2 is included in the Pro plan for basic rules and requires Business/Enterprise for advanced characteristics (JA3, body fields). Verify your plan before writing Terraform that uses body-field characteristics.
- **`cf.unique_visitor_id` is derived from IP + User-Agent**, not a cookie. It is more resilient to IP rotation than raw `ip.src` but is not a strong identifier for determined attackers.
- **Workers `RateLimiter` is eventually consistent**: Two simultaneous requests in different edge PoPs may both pass a limit that has just been reached. For strict serialisation use a Durable Object.
- **Header-based counting and case sensitivity**: `http.request.headers["Authorization"]` is case-sensitive in Cloudflare rule expressions. APIs that send `authorization` (lowercase) require a lowercase key or a `lower()` function call.
- **`mitigation_timeout` vs `period`**: The period is the counting window. The mitigation timeout is how long to block *after* the threshold is crossed. They are independent. Setting `mitigation_timeout = period` gives clean 1-window blocks; setting it higher gives escalating punishment.

## Verification

```bash
# Confirm rate limit rules are active
curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | select(.phase == "http_ratelimit")'

# Trigger the login rate limit
for i in $(seq 1 10); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://api.example.com/api/auth/login \
    -d '{"username":"test","password":"wrong"}'
done
# Expected: first 5 return 401, remainder return 429

# Check Firewall Events in the dashboard:
# Security → Events → filter by Action=block, Service=Rate limiting

# Test Workers RateLimiter binding locally
wrangler dev --test-scheduled
```

## Related

- `rate-limiting-per-user-d1-durable-objects.md` — Durable Object sliding window counters
- `rate-limiting-strategies.md` — choosing the right strategy for your traffic pattern
- `cloudflare-bot-management-abuse-prevention.md` — ML-based bot scoring integration
- `cloudflare-turnstile-workers-integration.md` — gating expensive actions behind a CAPTCHA
- `denial-of-wallet-llm-cost-abuse.md` — protecting AI Workers endpoints from cost abuse

## Sources

- Cloudflare Rate Limiting v2 — Product documentation (developers.cloudflare.com/waf/rate-limiting-rules)
- Cloudflare Workers RateLimiter binding — workers.cloudflare.com/docs/runtime-apis/bindings/rate-limiter
- Cloudflare Terraform Provider — cloudflare_ruleset resource, phase http_ratelimit
- OWASP Testing Guide — OTG-BUSLOGIC-006 Testing for the Circumvention of Work Flows
- Stripe Engineering Blog — "Rate limiting at stripe" — sliding window algorithms in production
