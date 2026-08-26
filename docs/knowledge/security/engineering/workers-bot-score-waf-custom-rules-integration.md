# Workers Bot Management Score Integration with WAF Custom Rules

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

An API endpoint on example project (example.com) receives automated traffic that bypasses coarse IP-based rate limits because bots rotate IPs or use residential proxies. The existing WAF rules block known bad actors but miss sophisticated bot traffic with low threat scores. The team needs to combine Cloudflare's bot management score (`cf.bot_management.score`) with WAF custom rules and Worker-side behavioral signals to achieve layered bot defense without over-blocking legitimate users.

## Context

Cloudflare Bot Management assigns every request a bot score from 1 (definitely a bot) to 99 (definitely human). The score is available in WAF custom rule expressions as `cf.bot_management.score` and inside Workers as `request.cf.botManagement.score`. Effective bot defense layers WAF rules (evaluated before the Worker, at the edge) for fast rejection of clear-cut bots, with Worker-side logic handling the ambiguous middle range (scores 30–75) by applying CAPTCHA challenges, honeypot checks, or behavioral rate limiting backed by Durable Objects. This article covers the end-to-end integration pattern.

## 1. WAF Custom Rules for Clear-Cut Bot Traffic

Create WAF custom rules in the Cloudflare dashboard or via Terraform. These fire before the Worker and incur zero CPU cost:

```
# Rule 1: Hard block definitively automated traffic on sensitive endpoints
Expression:
  (cf.bot_management.score lt 10)
  and (http.request.uri.path wildcard "/api/*")
Action: Block (403)

# Rule 2: JS Challenge for low-confidence bots on public pages
Expression:
  (cf.bot_management.score lt 30)
  and (not cf.bot_management.verified_bot)
  and (http.request.uri.path wildcard "/app/*")
Action: Managed Challenge

# Rule 3: Skip bot scoring for verified good bots (crawlers, uptime monitors)
Expression:
  (cf.bot_management.verified_bot)
  and (http.request.uri.path wildcard "/api/public/*")
Action: Skip → Bot Management checks
```

The `cf.bot_management.verified_bot` field identifies bots on Cloudflare's allow-list (Googlebot, UptimeRobot, etc.); never block them indiscriminately.

## 2. Reading Bot Score Inside a Worker

```typescript
interface BotManagement {
  score: number;
  verifiedBot: boolean;
  staticResource: boolean;
  ja3Hash: string;
  ja4: string;
}

interface CfRequest extends IncomingRequestCfProperties {
  botManagement: BotManagement;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cf = request.cf as CfRequest | undefined;
    const botScore = cf?.botManagement?.score ?? 99;
    const isVerifiedBot = cf?.botManagement?.verifiedBot ?? false;

    // Ambiguous bot range: apply additional Worker-side checks
    if (botScore < 50 && !isVerifiedBot) {
      return handleAmbiguousBot(request, env, botScore);
    }

    return handleLegitimateRequest(request, env);
  },
};
```

## 3. Behavioral Rate Limiting for the Ambiguous Score Range (30–75)

Requests in the ambiguous range receive a stricter per-IP rate limit enforced by a Durable Object, separate from the standard user-level rate limit:

```typescript
async function handleAmbiguousBot(
  request: Request,
  env: Env,
  botScore: number
): Promise<Response> {
  const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const id = env.BOT_LIMITER.idFromName(ip);
  const stub = env.BOT_LIMITER.get(id);

  const limitResp = await stub.fetch(
    new Request("https://internal/check", {
      method: "POST",
      body: JSON.stringify({ botScore, path: new URL(request.url).pathname }),
    })
  );

  if (limitResp.status === 429) {
    return new Response("Too Many Requests", {
      status: 429,
      headers: { "Retry-After": "60" },
    });
  }

  // Optionally inject a Cloudflare Turnstile challenge header for score 30–50
  if (botScore < 50) {
    return new Response(null, {
      status: 302,
      headers: { Location: `/challenge?next=${encodeURIComponent(request.url)}` },
    });
  }

  return handleLegitimateRequest(request, env);
}
```

## 4. Durable Object: IP-Level Bot Rate Limiter

```typescript
import { DurableObject } from "cloudflare:workers";

const BOT_WINDOW_MS = 60_000;       // 1-minute window
const BOT_SCORE_THRESHOLD = 50;
const AMBIGUOUS_REQUEST_LIMIT = 20; // max 20 requests/min for score < 50

export class BotLimiter extends DurableObject {
  private requests: number[] = [];

  async fetch(request: Request): Promise<Response> {
    const { botScore } = (await request.json()) as { botScore: number; path: string };
    const now = Date.now();

    // Evict requests outside the window
    this.requests = this.requests.filter((t) => now - t < BOT_WINDOW_MS);

    if (botScore < BOT_SCORE_THRESHOLD) {
      if (this.requests.length >= AMBIGUOUS_REQUEST_LIMIT) {
        return new Response("Rate limited", { status: 429 });
      }
    }

    this.requests.push(now);
    return new Response("OK", { status: 200 });
  }
}
```

## 5. Logging Bot Scores to Analytics Engine for Rule Tuning

Before tightening WAF rules, collect bot score distributions over real traffic to avoid false positives:

```typescript
async function logBotSignal(
  env: Env & { AE: AnalyticsEngineDataset },
  request: Request,
  botScore: number,
  action: "pass" | "challenge" | "block"
): Promise<void> {
  const cf = request.cf as CfRequest | undefined;
  env.AE.writeDataPoint({
    blobs: [
      action,
      cf?.botManagement?.ja3Hash ?? "",
      cf?.country ?? "",
      new URL(request.url).pathname,
    ],
    doubles: [botScore],
    indexes: [action],
  });
}
```

Query the Analytics Engine SQL API after 24 hours to see score distribution:

```sql
SELECT
  floor(double1 / 10) * 10 AS score_bucket,
  blob1                     AS action,
  COUNT(*)                  AS requests
FROM  AE_DATASET
WHERE timestamp > NOW() - INTERVAL '1' DAY
GROUP BY score_bucket, action
ORDER BY score_bucket;
```

## 6. JA4 Fingerprint Allowlist for API Clients

Verified API clients (mobile apps, partner integrations) should bypass bot scoring by JA4 TLS fingerprint, reducing false positives for high-value traffic:

```typescript
const TRUSTED_JA4_FINGERPRINTS = new Set([
  "t13d1517h2_8daaf6152771_b0da82dd1658", // iOS app v4.x
  "t13d1516h2_8daaf6152771_9e4e5cefd6b5", // Android app v3.x
]);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cf = request.cf as CfRequest | undefined;
    const ja4 = cf?.botManagement?.ja4 ?? "";

    if (TRUSTED_JA4_FINGERPRINTS.has(ja4)) {
      // Bypass bot score logic for known-good clients
      return handleLegitimateRequest(request, env);
    }

    const botScore = cf?.botManagement?.score ?? 99;
    if (botScore < 10) return new Response("Forbidden", { status: 403 });

    return handleLegitimateRequest(request, env);
  },
};
```

Maintain the JA4 allowlist in a KV namespace so it can be updated without a Worker redeploy.

## Anti-patterns

- Blocking all traffic with `botScore < 30` without exempting `cf.bot_management.verified_bot` — this blocks Googlebot and other legitimate crawlers.
- Using `cf.bot_management.score` as the sole criterion for blocking authenticated API traffic — a signed-in user with a low bot score (shared corporate IP, VPN) should be treated differently than an anonymous low-score request.
- Trusting `CF-Connecting-IP` as a stable identifier without also checking the JA3/JA4 fingerprint — residential proxy networks rotate IPs but often reuse TLS fingerprints.
- Logging the raw bot score to an external analytics service without checking for PII in surrounding fields (country, IP).
- Applying `BEGIN IMMEDIATE` (from D1 patterns) logic to bot limiting state in a regular Worker — use a Durable Object for shared mutable state.

## Gotchas

- `cf.botManagement` is only populated when Cloudflare Bot Management (Enterprise add-on) or Super Bot Fight Mode (Pro/Business) is enabled on the zone. On a free zone the field is absent; always null-check with `?? 99`.
- WAF custom rules with `cf.bot_management.score` are evaluated before Workers; a Worker cannot override a WAF block. Ensure WAF rules are correct before adding Worker-side logic.
- JA4 fingerprints change with TLS library updates; monitor app release cycles and update the allowlist ahead of major releases.
- `cf.bot_management.staticResource` is `true` for images, CSS, JS fetched directly; applying bot scoring to static assets creates unnecessary challenges for CDN prefetch.
- Durable Object `BotLimiter` instances are per-IP and reside in a single region; under very high volume from one IP the DO becomes a hot spot. For global bot mitigation, WAF rules (evaluated at every PoP) are more efficient.

## Verification

```bash
# Simulate a low-bot-score request using curl with a custom JA3
# (Cloudflare assigns low scores to well-known automation fingerprints)
# In staging, verify the Worker returns 302 challenge redirect for score < 50
curl -v https://staging.example.com/api/data \
  -H "Accept: application/json"

# Check Analytics Engine for score distribution
wrangler analytics-engine query \
  --dataset BOT_SIGNALS \
  --sql "SELECT floor(double1/10)*10 AS bucket, COUNT(*) FROM BOT_SIGNALS GROUP BY bucket ORDER BY bucket"

# Confirm verified bot (e.g. Googlebot) is never blocked
curl -A "Googlebot/2.1 (+http://www.google.com/bot.html)" \
  https://example.com/api/public/sitemap
# Expected: 200, not 403 or 302
```

## Related

- `cloudflare-bot-management-abuse-prevention.md`
- `workers-request-fingerprinting-bot-detection-d1.md`
- `cloudflare-rate-limiting-v2-api-abuse-prevention.md`
- `cloudflare-turnstile-workers-integration.md`
- `waf-custom-rules-xss-prevention.md`
- `rate-limiting-sliding-window-durable-objects.md`

## Sources

- Cloudflare Bot Management: https://developers.cloudflare.com/bots/
- Bot Management in Workers (`cf.botManagement`): https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- WAF Custom Rules Expressions: https://developers.cloudflare.com/waf/custom-rules/create-dashboard/
- JA4 TLS Fingerprinting: https://github.com/FoxIO-LLC/ja4
