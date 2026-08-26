# Workers Bot Management Score — Tiered Challenge and Routing Logic

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your application needs to respond differently to requests based on Cloudflare's bot confidence score rather than applying a single global block rule. Human users, good bots, suspicious scrapers, and verified malicious bots each need a distinct response path — serving degraded content, redirecting to a CAPTCHA, throttling API calls, or blocking outright — all without touching WAF rules.

## Context

Cloudflare Bot Management enriches every request with a score in `request.cf.botManagement`. The `score` property ranges from 1 (very likely a bot) to 99 (very likely human). Additional signals — `verifiedBot`, `ja3Hash`, `ja4`, `corporateProxy` — let you distinguish good bots (Googlebot, CDN health checks) from attack traffic. All this data is available synchronously in a Worker's `fetch` handler at zero latency since it is computed at the edge before the Worker runs. This article focuses on programmatic routing logic in Workers, which complements rather than replaces WAF Bot Management rules.

## Reading Bot Management Properties

```typescript
// types reference: @cloudflare/workers-types
export interface Env {
  ORIGIN: Fetcher;         // Service binding to origin Worker or external
  HONEYPOT: Fetcher;       // Sink that logs bot traffic to Analytics Engine
  BOT_SCORE_THRESHOLD_BLOCK: string;   // default "10"
  BOT_SCORE_THRESHOLD_CHALLENGE: string; // default "30"
}

interface BotManagementInfo {
  score: number;
  verifiedBot: boolean;
  ja3Hash: string;
  ja4: string;
  corporateProxy: boolean;
  staticResource: boolean;
  detectionIds: Record<string, number>;
}

function getBotInfo(request: Request): BotManagementInfo | null {
  const cf = (request as Request & { cf?: CfProperties }).cf;
  if (!cf?.botManagement) return null;
  return cf.botManagement as unknown as BotManagementInfo;
}
```

## Tiered Response Logic

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const bot = getBotInfo(request);
    const url = new URL(request.url);

    // Static assets: skip bot checks to reduce overhead
    if (/\.(js|css|woff2|png|jpg|ico|svg)$/.test(url.pathname)) {
      return env.ORIGIN.fetch(request);
    }

    if (!bot) {
      // Bot Management not available (e.g. local dev) — pass through
      return env.ORIGIN.fetch(request);
    }

    const blockThreshold = parseInt(env.BOT_SCORE_THRESHOLD_BLOCK, 10) || 10;
    const challengeThreshold =
      parseInt(env.BOT_SCORE_THRESHOLD_CHALLENGE, 10) || 30;

    // Verified bots (Googlebot, Bingbot, etc.) get full access
    if (bot.verifiedBot) {
      return env.ORIGIN.fetch(request);
    }

    // Corporate proxies often depress the score — treat leniently
    if (bot.corporateProxy && bot.score >= 40) {
      return env.ORIGIN.fetch(request);
    }

    // High-confidence bot — block or route to honeypot
    if (bot.score <= blockThreshold) {
      // Log to Analytics Engine before responding
      logBotRequest(request, bot, "blocked");
      return new Response("Access denied", {
        status: 403,
        headers: { "Content-Type": "text/plain" },
      });
    }

    // Suspicious range — return degraded/empty response for scraper-sensitive routes
    if (bot.score <= challengeThreshold && url.pathname.startsWith("/api/listings")) {
      logBotRequest(request, bot, "degraded");
      return Response.json({ results: [], meta: { degraded: true } });
    }

    // Moderately suspicious — add a Turnstile challenge gate for login pages
    if (bot.score <= challengeThreshold && url.pathname === "/login") {
      logBotRequest(request, bot, "challenged");
      return new Response(turnstileChallengePage(), {
        status: 403,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    // Likely human — serve normally
    return env.ORIGIN.fetch(request);
  },
};

function logBotRequest(
  request: Request,
  bot: BotManagementInfo,
  action: string
): void {
  // Fire-and-forget; in production use ctx.waitUntil with Analytics Engine write
  console.log(
    JSON.stringify({
      url: request.url,
      botScore: bot.score,
      ja3: bot.ja3Hash,
      verifiedBot: bot.verifiedBot,
      action,
      ts: Date.now(),
    })
  );
}

function turnstileChallengePage(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Verify you're human</title></head>
<body>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
  <form method="POST" action="/login">
    <div class="cf-turnstile" data-sitekey="YOUR_TURNSTILE_SITE_KEY"></div>
    <button type="submit">Continue</button>
  </form>
</body>
</html>`;
}
```

## JA4 Fingerprint-Based Allow/Block List

```typescript
// Supplement score-based routing with TLS fingerprint allowlist
const KNOWN_GOOD_JA4: Set<string> = new Set([
  // Add fingerprints of internal health-check clients here
  "t13d1516h2_e7d1b6f7cae3_7ac63c3c3b3a",
]);

const KNOWN_BAD_JA4: Set<string> = new Set([
  // Known attack tool fingerprints (update from threat intel)
  "t13d1516h2_abc123_bad000",
]);

export function applyFingerprintPolicy(
  bot: BotManagementInfo
): "allow" | "block" | "continue" {
  if (KNOWN_GOOD_JA4.has(bot.ja4)) return "allow";
  if (KNOWN_BAD_JA4.has(bot.ja4)) return "block";
  return "continue";
}
```

## Rate Limiting Low-Score Bots with Durable Objects

```typescript
import type { DurableObjectNamespace, DurableObjectStub } from "@cloudflare/workers-types";

export interface Env {
  BOT_RATE_LIMITER: DurableObjectNamespace;
}

export async function checkBotRateLimit(
  env: Env,
  clientIP: string,
  bot: BotManagementInfo
): Promise<boolean> {
  // Only rate-limit suspicious (score ≤ 50) non-verified traffic
  if (bot.verifiedBot || bot.score > 50) return false; // not limited

  const id = env.BOT_RATE_LIMITER.idFromName(`ip:${clientIP}`);
  const stub: DurableObjectStub = env.BOT_RATE_LIMITER.get(id);

  const res = await stub.fetch("https://internal/check", { method: "POST" });
  const { limited } = await res.json<{ limited: boolean }>();
  return limited;
}
```

## Anti-patterns

- Using `botManagement.score` as the sole signal without checking `verifiedBot` — blocks Googlebot and other legitimate crawlers when the score happens to dip below threshold.
- Blocking at `score < 1` (impossible value) or `score <= 0` — the score floor is 1; guard against misconfigured thresholds with `Math.max(1, threshold)`.
- Logging `ja3Hash` or `ja4` in plain-text to public logs — fingerprints can be reverse-correlated to client configurations; treat them as moderately sensitive.

## Gotchas

- `request.cf.botManagement` is only populated on **Enterprise Bot Management** plans; on non-enterprise zones the property is `undefined`, and accessing `.score` throws — always null-check.
- The `score` represents Cloudflare's real-time confidence, not a historical reputation; a single high-score session can include one low-score request (e.g. a JS challenge probe), so make routing decisions per-request, not per-session.

## Verification

```bash
# Simulate a low-score bot request with a custom CF-Worker-Test header
# (use wrangler dev with cf property overrides for local testing)
wrangler dev --test-scheduled

# In a test Worker override cf.botManagement:
curl -X GET "http://localhost:8787/api/listings" \
  -H "X-Test-Bot-Score: 5"

# In production, check Worker logs for blocked requests
wrangler tail --format=pretty | grep '"action":"blocked"'

# Verify verified bots still reach origin
curl -A "Googlebot/2.1 (+http://www.google.com/bot.html)" \
  "https://example.com/api/listings" -sI | grep HTTP
```

## Related

- `cloudflare/bot-management-enterprise.md`
- `cloudflare/cloudflare-turnstile-invisible-widget-server-validation.md`
- `cloudflare/rate-limiting-v2-vs-workers-side.md`

## Sources

- https://developers.cloudflare.com/bots/reference/bot-management-variables/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/bots/concepts/bot-score/
