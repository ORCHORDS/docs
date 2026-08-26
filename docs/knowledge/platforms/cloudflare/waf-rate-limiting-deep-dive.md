# waf-rate-limiting-deep-dive

**Issue:** Cloudflare WAF rate limiting rules — best practices
**Date:** 2026-08-09
**Status:** documented

## Symptom
Bots are scraping your API. Brute force is hammering
your login. A single user is making 1000 req/sec.
You wish you had a real rate limiter at the edge.

## Root cause
**Without rate limiting, your origin is the rate
limiter.** Use Cloudflare WAF rate limiting rules.

**Source:** Cloudflare WAF docs:
https://developers.cloudflare.com/waf/rate-limiting-rules/

## The "rate limit rule" concept

A rate limiting rule has:
- **Expression:** What matches
- **Action:** What happens when limit hit
- **Characteristics:** Counter key
- **Period:** Time window
- **Requests per period:** Threshold
- **Duration:** Mitigation timeout

The rule is structured.

## The "characteristics" concept

For the counter key:
- **IP:** By source IP
- **IP + NAT:** Same NAT users share
- **Header value:** API key
- **Cookie:** Session
- **ASN:** By ASN
- **Country:** By geo
- **Path:** By URL
- **JA3/JA4:** TLS fingerprint
- **JSON field:** API token
- **Custom:** Your expression

The characteristics are the key.

## The "plan tier" pattern

| Feature | Free | Pro | Business | Ent App Sec | Ent Adv RL |
|---|---|---|---|---|---|
| Rule fields | Path, Bot | + Host, URI, Query | + Method, IP, UA | + Headers | + Body, JSON |
| Characteristics | IP | IP | IP, IP+NAT | + Headers, Cookie, Path | + JA3, JSON, Form, Custom |
| Period max | 10s | 1 min | 10 min | 65,535s | 65,535s |
| Mitigation | 10s | 1 h | 1 day | 1 day | 1 day |
| Number of rules | 1 | 2 | 5 | 100 | 100 |

The tier is per plan.

## The "supported periods" pattern

For periods (seconds):
- 10, 15, 20, 30, 40, 45, 60 (1 min)
- 90, 120 (2 min), 180, 240, 300 (5 min)
- 480, 600 (10 min), 900, 1200 (20 min)
- 1800, 2400, 3600 (1 h), 65535, 86400 (1 day)

The periods are the supported list.

## The "login brute force" pattern

For login protection:
```
Field          | Operator  | Value
URI Path       | equals    | /login
Country        | equals    | US
IP Source      | not equal | 192.0.0.1
```

Expression:
```javascript
(http.request.uri.path eq "/login"
  and ip.src.country eq "US"
  and ip.src ne 192.0.0.1)
```

Characteristics: IP + Data center ID.

## The "API rate limit" pattern

For API:
```
Field       | Operator  | Value
URI Path    | contains  | /product
Method      | equals    | POST
```

Expression:
```javascript
(http.request.uri.path contains "/product"
  and http.request.method eq "POST")
```

Characteristics: IP + x-api-key header.

## The "multi-tenant" pattern

For multi-tenant:
```
Field | Operator | Value
URI   | wildcard | /graphql/*
```

Characteristics: x-api-key header.

Use **complexity-based** for GraphQL:
- **Score:** From response header `my-score`
- **Period:** 1 min
- **Threshold:** 400
- **Action:** Block for 10 min

The limit is per complexity.

## The "complexity-based" pattern

For GraphQL/expensive:
- **Counting:** Sum of complexity from response header
- **Period:** 1 min
- **Score:** 400
- **Action:** Block

The limit is on score, not request count.

## The "throttle vs block" pattern

For action behavior:
- **Block:** Deny all during mitigation
- **Throttle:** Allow below rate, block above
- **Use:** Block for security, Throttle for API

The action is per need.

## The "custom response" pattern

For blocked response:
- **Type:** text/html, text/plain, application/json,
  application/xml
- **Code:** 400-499 (default 429)
- **Body:** Max 30 KB

The response is custom.

## The "exclude known bots" pattern

For bots:
```
cf.client.bot eq false
```

The known bots are excluded.

## The "cached assets" pattern

For cached:
- **Default:** Counts cached too
- **Disable:** "Also apply rate limiting to cached
  assets" → only origin requests counted

The cache is excluded.

## The "rule order" pattern

For evaluation:
- Rules evaluated in order
- Block stops evaluation
- Place block first, then challenge

The order matters.

## The "Enterprise throttle" pattern

For Ent with App Sec add-on:
- **Throttle:** Allow below rate, block above
- **Config:** "Throttle requests over the maximum
  configured rate"
- **Use:** API protection

The throttle is precise.

## The "rate limit + Turnstile" pattern

For sensitive flows:
- Rate limit by IP
- Turnstile challenge for high-value
- Anomaly detection for bots

The flows are layered.

## The "Workers + rate limit" pattern

For custom:
```typescript
// Custom logic in Worker
export default {
  async fetch(req, env) {
    const ip = req.headers.get("CF-Connecting-IP");
    const key = `rl:${ip}`;
    const count = await env.RATE_LIMITER.get(key);

    if (count > 100) {
      return new Response("Too Many Requests", { status: 429 });
    }

    await env.RATE_LIMITER.put(key, count + 1, {
      expirationTtl: 60,
    });

    return fetch(req);
  },
};
```

The custom is in Workers.

## The "Rate Limiting API" pattern

For API:
```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/{zone_id}/rate_limits" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "mode": "block",
    "match": {
      "request": {
        "url": "*.example.com/api/*",
        "methods": ["POST"]
      }
    },
    "threshold": 100,
    "period": 60
  }'
```

The API is RESTful.

## The "Terraform" pattern

For Terraform:
```hcl
resource "cloudflare_rate_limit" "api" {
  zone_id = var.zone_id
  name    = "API rate limit"
  match {
    request {
      url_pattern = "*.example.com/api/*"
      methods     = ["POST"]
    }
  }
  threshold = 100
  period    = 60
  action {
    mode    = "block"
    timeout = 600
  }
}
```

The Terraform is the IaC.

## The "rule expression" pattern

For complex:
```javascript
(
  http.request.uri.path eq "/api/auth/login"
  or http.request.uri.path eq "/api/auth/signup"
)
and not cf.client.bot
and ip.src.country in {"US" "CA" "GB"}
```

The expression is composed.

## The "rule + managed ruleset" pattern

For layered:
- **Rate limit rules:** Custom
- **Managed ruleset:** OWASP, Cloudflare
- **Bot Management:** Score-based

The layers stack.

## The "rate limit + KV" pattern

For distributed:
- **Workers:** Custom logic
- **KV:** Shared state
- **Pattern:** Token bucket

The KV is the store.

## The "rate limit + Durable Objects" pattern

For accurate:
- **Durable Objects:** Strongly consistent
- **Pattern:** Per-user counter
- **Use:** Quota enforcement

The DO is the counter.

## The "rate limit anti-pattern" anti-patterns

### 1. Too broad
- **Issue:** Blocks legitimate users
- **Fix:** Specific paths + characteristics

### 2. Too narrow
- **Issue:** Attackers bypass
- **Fix:** Multiple rules

### 3. No exclude bots
- **Issue:** Blocks Google
- **Fix:** `not cf.client.bot`

### 4. No monitoring
- **Issue:** Silent failures
- **Fix:** Log blocked + alert

## Verification
- **Test:** Rule fires on threshold
- **Test:** Action is correct
- **Test:** Exclusions work
- **Live:** Origin load is healthy
- **Audit:** Quarterly review

## Gotchas
- **The "cached assets" gotcha.** Toggle off.
- **The "rule order" gotcha.** Block first.
- **The "throttle vs block" gotcha.** Choose per need.

## Related
- `cloudflare/waf-best-practices.md`
- `cloudflare/turnstile-best-practices.md`
- `cloudflare/workers-rpc.md`
- `cloudflare/durable-objects-patterns.md`
- `security/owasp-api-top-10-2023.md`
- Cloudflare WAF: https://developers.cloudflare.com/waf/rate-limiting-rules/
- Cloudflare rate limit examples: https://developers.cloudflare.com/waf/rate-limiting-rules/use-cases/
