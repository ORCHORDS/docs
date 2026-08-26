# Cloudflare Snippets — Lightweight Edge JavaScript

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You need to modify a response header, set a cookie, redirect a small subset of paths, or A/B-test a landing page — but standing up a full Cloudflare Worker feels like overkill. You want code that runs in milliseconds, is version-controlled in a Rules-style UI, and does not consume the Workers paid-plan subrequest budget.

## Context

Cloudflare Snippets are short JavaScript/TypeScript functions that execute at the Cloudflare edge as part of the Rules pipeline. They sit between WAF rules and the origin, share the same execution environment as Workers (V8 isolates), but operate under tighter resource limits and a much simpler deployment model.

| Feature | Workers | Snippets |
|---|---|---|
| CPU limit | 10 ms (Standard) / unlimited (Unbound) | 5 ms |
| Outbound `fetch()` | Yes (500 subrequests) | **No** |
| KV / R2 / D1 bindings | Yes | **No** |
| Durable Objects | Yes | **No** |
| Invocation trigger | Route / Service binding / Cron | **Rules match** |
| Deployment target | Account-level Worker | **Zone-level Snippet** |
| Cold start | < 5 ms | < 2 ms (typically) |

Snippets are ideal when you need to:
- Rewrite headers on the way in or out
- Implement lightweight redirects that don't fit Page Rules
- Set first-party cookies for analytics without a full Worker
- Perform simple request routing (geo-based redirects, bot detection via `cf.bot_management.score`)
- Run A/B tests by assigning a cohort cookie and varying cache keys

## Creating a Snippet via the Dashboard

1. **Zone → Rules → Snippets → Create Snippet**
2. Write JavaScript in the inline editor (TypeScript is transpiled automatically)
3. Add a Rule expression to match the requests where this Snippet runs
4. Save and deploy — no `wrangler deploy` needed

The match expression uses the same Filter DSL as WAF rules:

```
(http.request.uri.path matches "^/checkout" and not cf.bot_management.verified_bot)
```

## Creating a Snippet via the API

```bash
# Create the snippet code
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/snippets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: multipart/form-data" \
  -F 'metadata={"main_module":"snippet.js"}' \
  -F 'snippet.js=@./snippet.js'

# Bind the snippet to a rule filter
curl -X PUT "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/snippets/rules" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "snippet_name": "my-snippet",
        "expression": "(http.request.uri.path matches \"^/api\")",
        "description": "Add security headers on /api",
        "enabled": true
      }
    ]
  }'
```

## Example: Adding Security Headers

```javascript
// snippet.js — runs on every matched request, no fetch() needed
export default {
  async fetch(request) {
    // Pass the request through to origin unchanged
    const response = await fetch(request);

    // Clone is required because Response bodies are one-use streams
    const newResponse = new Response(response.body, response);

    newResponse.headers.set('X-Content-Type-Options', 'nosniff');
    newResponse.headers.set('X-Frame-Options', 'DENY');
    newResponse.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
    newResponse.headers.set(
      'Permissions-Policy',
      'camera=(), microphone=(), geolocation=(self)',
    );

    return newResponse;
  },
};
```

> **Wait** — Snippets have no `fetch()`! The `fetch(request)` call inside a Snippet is allowed only as the **pass-through** to origin. It counts as the single implicit subrequest that Snippets allow for origin forwarding. Arbitrary outbound `fetch()` to third-party URLs is blocked.

## Example: Geo-Based Redirect Without a Worker

```javascript
// geo-redirect.js
export default {
  async fetch(request) {
    const country = request.cf?.country ?? 'US';

    const redirectMap = {
      GB: 'https://uk.example.com',
      DE: 'https://de.example.com',
      FR: 'https://fr.example.com',
    };

    const target = redirectMap[country];
    if (target) {
      const url = new URL(request.url);
      return Response.redirect(`${target}${url.pathname}${url.search}`, 302);
    }

    // Fall through to origin
    return fetch(request);
  },
};
```

Attach this to the Rule expression: `(not cf.bot_management.verified_bot and ip.geoip.country in {"GB" "DE" "FR"})`

## Example: A/B Test Cookie Assignment

```javascript
// ab-test.js — assigns visitors to cohort A or B deterministically by IP hash
export default {
  async fetch(request) {
    const existing = getCookieValue(request.headers.get('Cookie') ?? '', 'ab_cohort');

    if (existing === 'A' || existing === 'B') {
      // Cohort already assigned — vary the cache key but don't redirect
      const resp = await fetch(request);
      const out = new Response(resp.body, resp);
      out.headers.append('Vary', 'Cookie');
      return out;
    }

    // Assign cohort based on IP address (deterministic, no random drift)
    const ip = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
    const cohort = simpleHash(ip) % 2 === 0 ? 'A' : 'B';

    const resp = await fetch(request);
    const out = new Response(resp.body, resp);
    out.headers.set('Set-Cookie', `ab_cohort=${cohort}; Path=/; SameSite=Lax; Max-Age=86400`);
    return out;
  },
};

function getCookieValue(cookieHeader, name) {
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? match[1] : null;
}

// djb2 hash — no SubtleCrypto needed (no async = no await = faster)
function simpleHash(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
    hash = hash >>> 0; // keep unsigned 32-bit
  }
  return hash;
}
```

## Example: Rewrite Request Path

```javascript
// path-rewrite.js — strip /v1 prefix before forwarding to legacy origin
export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/v1/')) {
      url.pathname = url.pathname.replace('/v1/', '/');
      return fetch(new Request(url.toString(), request));
    }

    return fetch(request);
  },
};
```

## Terraform Management

```hcl
resource "cloudflare_snippet" "security_headers" {
  zone_id = var.zone_id
  name    = "security-headers"

  main_module = "main.js"

  files {
    name    = "main.js"
    content = file("${path.module}/snippets/security_headers.js")
  }
}

resource "cloudflare_snippet_rules" "security_headers_rule" {
  zone_id = var.zone_id

  rules {
    enabled     = true
    expression  = "(http.request.uri.path matches \"^/\")"
    description = "Apply security headers zone-wide"
    snippet_name = cloudflare_snippet.security_headers.name
  }
}
```

## Anti-patterns

- **Using Snippets for anything requiring external API calls** — the no-outbound-fetch constraint is hard; use a Worker + service binding for those patterns.
- **Putting heavy string manipulation or regex compilation in the hot path** — 5 ms CPU is tight; compile regexes at module scope (top-level, not inside `fetch()`).
- **Treating Snippets as a Page Rules replacement for all redirects** — for bulk redirects (> 100 entries) use Bulk Redirects (Rules → Redirect Rules) instead; Snippets need code updates for each new rule.
- **Relying on `globalThis` state between requests** — like Workers, Snippets run in isolates that may be reused or evicted; no reliable global mutable state.

## Gotchas

- Snippets are **zone-scoped**, not account-scoped. You cannot share a Snippet across zones without re-deploying to each zone.
- The `request.cf` object (including `country`, `bot_management`, `asn`) is available inside Snippets, but `request.cf.tlsClientAuth` and similar advanced TLS properties require the zone to have mutual TLS configured.
- Snippets execute **after** WAF rules but **before** Workers on the same route. If both a Snippet and a Worker match a request, the Snippet runs first.
- The `fetch(request)` pass-through inside a Snippet goes to the next handler in the chain (origin or a Worker), not necessarily the raw origin server.
- Module-scoped `await` (top-level await) is not supported in Snippets. All async initialization must happen inside the handler.
- There is currently no `wrangler` CLI support for Snippets; deployment is via the dashboard or the REST API. CI pipelines should use the API.

## Verification

```bash
# List all snippets on a zone
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/snippets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].name'

# Verify a snippet's code
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/snippets/security-headers" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.snippet_name'

# Test the header after deployment
curl -si https://example.com/ | grep -i "x-content-type-options"
# Expected: X-Content-Type-Options: nosniff
```

## Related

- `workers-best-practices.md` — full Workers patterns when outbound fetch or bindings are needed
- `pages-functions-routing.md` — routing logic for Pages-hosted sites
- `waf-best-practices.md` — WAF rules that precede Snippets in the pipeline
- `cloudflare-rules-trace-request-simulation-boundary.md` — simulating rule execution order

## Sources

- https://developers.cloudflare.com/rules/snippets/
- https://developers.cloudflare.com/rules/snippets/create-api/
- https://developers.cloudflare.com/rules/reference/filter-fields/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/snippet
