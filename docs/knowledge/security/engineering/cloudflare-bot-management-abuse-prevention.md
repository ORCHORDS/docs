# Cloudflare Bot Management Integration for Abuse Prevention

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

API endpoints are being hammered by credential-stuffing bots, scraping automation,
or synthetic traffic that bypasses simple IP-based rate limits. Standard rate limiting
fires too late — the bot has already consumed quota, triggered downstream costs (LLM
inference, email sends, payment checks), or poisoned analytics before a block lands.
You need behavioural signal from the Cloudflare network layer available inside your
Worker before any application logic runs.

## Context

Cloudflare Bot Management enriches every request with a **Bot Score** (0–99, low =
likely human, high = likely automated) and a **Bot Verification** result. These values
live in the `cf` object that Cloudflare attaches to the `IncomingRequestCfProperties`
struct passed to every Worker. The Enterprise Bot Management product adds JA3/JA4
fingerprints, verified bot allow-lists (Googlebot, etc.), machine-learning anomaly
scores, and the ability to serve managed JS challenges. The Pro/Business tier gives
access to Super Bot Fight Mode flags which surface as simpler boolean properties.

Attack vectors this addresses:
- **Credential stuffing** — automated login attempts using leaked credential lists.
- **Card testing / carding** — bots firing small charges to verify stolen card data.
- **Content scraping** — competitive or AI-training scrapers that consume bandwidth.
- **Account creation fraud** — bulk sign-up bots that abuse free tiers.
- **Inventory hoarding** — bots that hold limited-stock items in cart without buying.

## Accessing Bot Score in a Worker

The `cf` object is available on every `Request` passed to `fetch` event handlers or
the `fetch()` export in module syntax.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cf = request.cf as IncomingRequestCfProperties | undefined;

    // Enterprise Bot Management
    const botScore: number = (cf as any)?.botManagement?.score ?? 50;
    const verifiedBot: boolean = (cf as any)?.botManagement?.verifiedBot ?? false;
    const staticResource: boolean = (cf as any)?.botManagement?.staticResource ?? false;

    // Super Bot Fight Mode (Pro / Business)
    const likelyBot = (cf as any)?.botManagement?.likelyAutomated ?? false;

    // JA4 fingerprint — Enterprise only
    const ja4: string | undefined = (cf as any)?.botManagement?.ja4 ?? undefined;

    return routeRequest(request, env, { botScore, verifiedBot, staticResource, ja4 });
  },
};
```

## Tiered Response Strategy

A single hard block at score threshold 50 creates high false-positive rates. Use a
tiered approach instead:

```typescript
type BotTier = 'human' | 'uncertain' | 'managed-challenge' | 'block';

function classifyBot(botScore: number, verifiedBot: boolean): BotTier {
  if (verifiedBot) return 'human';          // Googlebot, Bingbot, etc.
  if (botScore <= 30) return 'human';
  if (botScore <= 55) return 'uncertain';   // monitor, log, maybe challenge
  if (botScore <= 80) return 'managed-challenge';
  return 'block';
}

async function enforceBotPolicy(
  request: Request,
  env: Env,
  tier: BotTier,
  endpoint: string,
): Promise<Response | null> {
  switch (tier) {
    case 'human':
      return null; // proceed normally

    case 'uncertain':
      // Log for analysis; apply stricter rate limit
      await logBotEvent(env, request, tier, endpoint);
      return null; // still serve, but with tighter quotas applied downstream

    case 'managed-challenge':
      // For browser-facing endpoints, redirect to Cloudflare challenge page.
      // For pure API endpoints, return 429 with Retry-After.
      if (isApiEndpoint(endpoint)) {
        return new Response(JSON.stringify({ error: 'rate_limited' }), {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': '60',
            'X-Block-Reason': 'bot-score',
          },
        });
      }
      // Browser endpoint: Cloudflare WAF rule issues the actual JS challenge;
      // here we just add a header that a WAF rule can key on.
      return null;

    case 'block':
      await logBotEvent(env, request, tier, endpoint);
      return new Response(JSON.stringify({ error: 'forbidden' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
  }
}
```

## JA4 Fingerprint Blocklisting

JA4 (successor to JA3) hashes the TLS ClientHello parameters into a stable fingerprint
that persists across IP rotation. Maintain a KV-stored blocklist of known-bad JA4
hashes:

```typescript
async function checkJa4Blocklist(
  env: Env,
  ja4: string | undefined,
): Promise<boolean> {
  if (!ja4) return false;
  // KV key: "ja4block:<hash>", value: JSON with reason + added timestamp
  const entry = await env.BOT_KV.get(`ja4block:${ja4}`);
  return entry !== null;
}

// To add a fingerprint at runtime from an admin endpoint:
async function blockJa4(env: Env, ja4: string, reason: string): Promise<void> {
  await env.BOT_KV.put(
    `ja4block:${ja4}`,
    JSON.stringify({ reason, blocked_at: new Date().toISOString() }),
    { expirationTtl: 86400 * 30 }, // auto-expire after 30 days
  );
}
```

## Honeypot Field Detection (Mobile + Web)

Supplement Cloudflare signals with application-layer honeypots. For web forms, add a
hidden field that browsers will not auto-fill and real users will not see:

```html
<!-- Invisible to screen readers; hidden via CSS not display:none -->
<input
  type="text"
  name="_hp_username"
  style="position:absolute;left:-9999px;top:-9999px;opacity:0;"
  tabindex="-1"
  autocomplete="off"
  aria-hidden="true"
/>
```

Worker-side check:

```typescript
async function checkHoneypot(formData: FormData): Promise<boolean> {
  const hp = formData.get('_hp_username');
  // Bots fill every field; humans leave honeypots empty
  return hp !== null && hp !== '';
}
```

For mobile API clients, the equivalent is a request-timing honeypot: if a signup form
is submitted in under 800 ms, it is almost certainly automated. Embed a `form_started`
timestamp in a signed token issued when the form loads:

```typescript
// Issue token on GET /signup
const formToken = await signTimestampToken(env.FORM_SECRET, Date.now());

// Verify on POST /signup
async function verifyFormTiming(token: string, minMs = 800): Promise<boolean> {
  const issuedAt = await verifyTimestampToken(env.FORM_SECRET, token);
  if (!issuedAt) return false; // tampered
  return Date.now() - issuedAt >= minMs;
}
```

## Verified Bot Allow-list Passthrough

Block legitimate crawlers only at your own cost. Verified bots (Googlebot, etc.) should
bypass application-level bot checks but still pass through auth and content controls:

```typescript
const VERIFIED_BOT_PATHS_ALLOWED = ['/sitemap.xml', '/robots.txt', '/feed'];

function allowVerifiedBot(verifiedBot: boolean, path: string): boolean {
  if (!verifiedBot) return false;
  return VERIFIED_BOT_PATHS_ALLOWED.some((p) => path.startsWith(p));
}
```

## Anti-patterns

- **Blocking on IP alone**: Residential proxy networks rotate IPs per request. IP blocks
  are effective for only minutes.
- **Hard-coding score thresholds in source**: Optimal thresholds shift as Cloudflare
  updates its ML model. Store thresholds in KV or environment variables.
- **Ignoring `verifiedBot`**: Blocking Googlebot tanks search rankings. Always check
  `verifiedBot` before applying hard blocks.
- **Logging bot scores but never acting**: Without feedback loops the ML model receives
  no signal and attack patterns are never escalated to WAF rules.
- **Challenging every API call**: Managed challenges require JavaScript execution.
  Mobile API clients cannot complete them. Use 429 + backoff for API surfaces.
- **Treating score 50 as a hard line**: The score is a probability estimate. At 50
  there is significant uncertainty; build a band of stricter-but-not-blocking policy
  around the midrange.

## Gotchas

- The `cf` object is only present on requests arriving at Cloudflare's edge. In local
  `wrangler dev` sessions, `cf` is `undefined` or mocked; guard every access.
- JA4 fingerprints are only populated for TLS connections. Requests that arrive over
  HTTP (rare but possible on non-HTTPS zones) will have no fingerprint.
- `verifiedBot` relies on Cloudflare's verified bot list maintained at
  `https://radar.cloudflare.com/traffic/verified-bots`. Custom internal crawlers are
  not on this list; whitelist them by IP range or service token instead.
- Bot scores are computed per-request on the first Worker invocation. If you use
  Workers chained via service bindings, the score is only on the outermost request.
- The managed challenge flow issues a cookie after a human passes. Subsequent requests
  carry that cookie and will receive lower bot scores automatically — do not count this
  as "the block is working".

## Verification

```bash
# Simulate a request with a manually injected bot score (wrangler dev only)
curl -X POST https://localhost:8787/api/login \
  -H "Content-Type: application/json" \
  -H "X-Bot-Score: 95" \    # Only meaningful if your Worker reads this header in dev
  -d '{"email":"test@example.com","password":"hunter2"}'

# Check KV for logged bot events
wrangler kv:key list --namespace-id=<BOT_KV_ID> --prefix=botlog:

# Verify JA4 blocklist entry
wrangler kv:key get --namespace-id=<BOT_KV_ID> "ja4block:<fingerprint>"
```

In Cloudflare Analytics, filter Security Events by "Bot Management" to correlate
score-based blocks against your Worker logs. Use Log Push to stream events to an
external SIEM for baseline building.

## Related

- `cloudflare-waf-mobile-api-false-positives.md`
- `rate-limiting-ddos-defense-layers.md`
- `credential-stuffing-account-takeover-defense.md`
- `ddos-mitigation-strategies.md`
- `honeypot-tokens-canary.md`

## Sources

- Cloudflare Bot Management documentation: https://developers.cloudflare.com/bots/
- JA4 specification: https://github.com/FoxIO-LLC/ja4
- Cloudflare Radar verified bots list: https://radar.cloudflare.com/traffic/verified-bots
- OWASP Automated Threat Handbook: https://owasp.org/www-project-automated-threats-to-web-applications/
