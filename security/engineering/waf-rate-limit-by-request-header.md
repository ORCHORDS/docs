# WAF Custom Rule Rate Limiting by Request Header

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An API receives requests from many source IPs (CDN edge nodes, mobile proxies, IPv6 rotators) making IP-keyed rate limiting ineffective. Abuse targets a specific API version (`X-API-Version: v1`), client type (`User-Agent: BotClient/1.0`), or tenant segment (`X-Tenant-Plan: free`). Standard IP rate limits miss the pattern entirely. Header-keyed WAF rate limiting rules pin the limit to a header value, independent of source IP.

## Context

Cloudflare WAF rate limiting rules (v2) allow custom `characteristics` that key the rate limit counter. In addition to `cf.colo.id`, `ip.src`, and `http.request.uri.path`, you can key on any request header using `http.request.headers["x-header-name"]`. This enables rate limits that fire when a single header value — e.g., a specific User-Agent string, API version, or tenant plan tier — exceeds a threshold, regardless of how many IPs are involved. Workers can augment this by normalizing or injecting headers before WAF evaluation.

---

## 1. WAF Rate Limit Rule — Key on Custom Header

Dashboard configuration expressed as Terraform for reproducibility:

```hcl
# terraform/waf.tf
resource "cloudflare_rate_limit" "api_version_v1" {
  zone_id   = var.zone_id
  threshold = 100
  period    = 60   # seconds

  match {
    request {
      url_scheme = "HTTPS"
      # Only fire on API paths
      url_patterns = ["https://api.example.com/v1/*"]
    }
  }

  # Key the counter on the X-API-Version header value
  # All requests sharing the same header value share one counter
  characteristics = [
    "http.request.headers[\"x-api-version\"]",
    "cf.colo.id",   # prevent cross-colo counter bleed
  ]

  action {
    mode    = "ban"
    timeout = 300
    response {
      content_type = "application/json"
      body         = "{\"error\":\"rate_limited\",\"retry_after\":300}"
    }
  }
}
```

---

## 2. WAF Custom Rule — Rate Limit by User-Agent Family

Rate limit scraper User-Agents without blocking legitimate browser traffic:

```hcl
resource "cloudflare_ruleset" "rate_limit_scrapers" {
  zone_id = var.zone_id
  name    = "Rate limit scraper User-Agents"
  kind    = "zone"
  phase   = "http_ratelimit"

  rules {
    action = "block"
    ratelimit {
      characteristics       = ["http.request.headers[\"user-agent\"]"]
      period                = 10
      requests_per_period   = 20
      mitigation_timeout    = 600
      requests_to_origin    = false
    }
    # Match only known scraper UA patterns
    expression = "(http.request.uri.path contains \"/api/\") and (http.user_agent contains \"python-requests\" or http.user_agent contains \"Go-http-client\" or http.user_agent contains \"curl\")"
    description = "Rate limit script-like User-Agents on API paths"
    enabled     = true
  }
}
```

---

## 3. Workers Middleware — Normalize Headers Before WAF

WAF rules evaluate headers as-is. Inject a canonical header in a Workers subrequest chain so the WAF sees a consistent value regardless of client casing or whitespace.

```typescript
// src/normalize-headers.ts
export interface Env {
  NEXT: Fetcher; // service binding to origin Worker
}

const PLAN_TIERS = new Set(['free', 'pro', 'business', 'enterprise']);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const mutable = new Request(request);
    const headers = new Headers(mutable.headers);

    // Normalize X-Tenant-Plan to lowercase canonical value
    const rawPlan = (headers.get('x-tenant-plan') ?? 'free').toLowerCase().trim();
    const plan = PLAN_TIERS.has(rawPlan) ? rawPlan : 'free';
    headers.set('x-tenant-plan', plan);

    // Normalize X-API-Version — strip leading 'v' and whitespace
    const rawVersion = (headers.get('x-api-version') ?? 'v1').trim().replace(/^v/i, '');
    headers.set('x-api-version', rawVersion);

    // Pass normalized request to origin; WAF on the origin Worker's zone fires after normalization
    return env.NEXT.fetch(new Request(request.url, {
      method: request.method,
      headers,
      body: request.body,
    }));
  },
};
```

---

## 4. Tenant-Plan Rate Limiting — Tiered Limits Per Plan

Combine header-keyed WAF rules with a Workers pre-check that enforces plan-specific limits stored in KV:

```typescript
// src/plan-rate-limit.ts
export interface Env {
  PLAN_LIMITS: KVNamespace;
  RATE_COUNTERS: DurableObjectNamespace;
}

interface PlanConfig {
  requestsPerMinute: number;
}

const DEFAULT_LIMITS: Record<string, number> = {
  free: 30,
  pro: 300,
  business: 1000,
  enterprise: 10000,
};

export async function checkPlanRateLimit(
  request: Request,
  env: Env,
  tenantId: string,
  plan: string,
): Promise<Response | null> {
  const limitKey = `plan:${plan}:rpm`;
  const stored = await env.PLAN_LIMITS.get<PlanConfig>(limitKey, 'json');
  const limit = stored?.requestsPerMinute ?? DEFAULT_LIMITS[plan] ?? 30;

  // Durable Object counter keyed to tenantId (not IP)
  const id = env.RATE_COUNTERS.idFromName(`tenant:${tenantId}`);
  const stub = env.RATE_COUNTERS.get(id);

  const countResp = await stub.fetch(new Request('https://do/increment', {
    method: 'POST',
    body: JSON.stringify({ window: 60, limit }),
  }));

  if (countResp.status === 429) {
    return new Response(
      JSON.stringify({ error: 'plan_rate_limited', plan, limit }),
      {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'Retry-After': '60',
          'X-RateLimit-Limit': String(limit),
          'X-RateLimit-Policy': `${limit};w=60;comment="plan-${plan}"`,
        },
      },
    );
  }
  return null; // allow request to proceed
}
```

---

## 5. Testing Header-Keyed Rules With Wrk2

```bash
# Flood from a single IP with a fixed User-Agent to verify the counter keys on header, not IP
wrk2 -t4 -c50 -d30s -R 200 \
  -H "User-Agent: python-requests/2.28.0" \
  https://api.example.com/api/data

# Expect: HTTP 429 responses after the threshold from WAF
# Verify counter isolates: same IP with different UA is NOT rate limited
wrk2 -t1 -c5 -d10s -R 20 \
  -H "User-Agent: Mozilla/5.0 (legitimate)" \
  https://api.example.com/api/data
# Expect: HTTP 200 responses (different counter bucket)
```

---

## Anti-patterns

- Keying rate limits only on `ip.src` — trivially bypassed with IPv6 rotation or residential proxy pools.
- Using `http.request.headers["user-agent"]` on a header value that clients can freely spoof — combine with `cf.bot_management.score` for abuse-resistant enforcement.
- Setting `mitigation_timeout` to 0 — the block expires immediately after the window, allowing burst-then-reset abuse.
- Defining the WAF rule before the Worker that normalizes headers — the WAF fires before normalization, keying on raw values.
- Applying the same threshold to all API paths — high-traffic bulk endpoints need higher limits than sensitive auth endpoints.

## Gotchas

- Cloudflare WAF rate limit `characteristics` strings are case-sensitive; `http.request.headers["X-API-Version"]` and `http.request.headers["x-api-version"]` behave as different keys — normalize to lowercase before matching.
- WAF rate limit rules in the `http_ratelimit` phase run before Workers by default; if your Worker normalizes headers, deploy it as a `fetch` handler at a higher-priority chain position or use a different service binding topology.
- The `requests_to_origin` flag controls whether only origin-bound requests count — set `false` to count all requests including cache hits.
- Rate limit counters in WAF are eventually consistent across PoPs; brief bursts may slip through before global counter sync.
- `cf.colo.id` as a secondary characteristic prevents one PoP's counter from triggering blocks at other PoPs — include it when traffic is globally distributed.

## Verification

```bash
# List WAF rate limit rules via API
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rate_limits" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, threshold, period, characteristics: .match}'

# Confirm a specific header-keyed rule is active
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.phase=="http_ratelimit") | .rules[].ratelimit.characteristics'
```

## Related

- `cloudflare-rate-limiting-v2-api-abuse-prevention.md` — General rate limiting by IP and URI
- `rate-limiting-sliding-window-durable-objects.md` — Durable Objects-based sliding window counters
- `workers-ip-reputation-d1-blocklist-realtime.md` — IP reputation enforcement in Workers
- `waf-custom-rules-xss-prevention.md` — WAF custom rules for XSS payload matching

## Sources

- [Cloudflare Rate Limiting v2 — Characteristics](https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/#characteristics)
- [Cloudflare Ruleset Engine — HTTP Rate Limit Phase](https://developers.cloudflare.com/ruleset-engine/reference/phases/#http_ratelimit)
- [Terraform cloudflare_ruleset resource](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset)
- [Workers as WAF pre-processors](https://developers.cloudflare.com/workers/reference/how-workers-works/)
