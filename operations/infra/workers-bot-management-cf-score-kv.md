# Bot Management Using cf.botManagement.score in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare Workers endpoint is receiving automated traffic that skews analytics, drains rate-limit quotas, and adds cost. You want to leverage Cloudflare's built-in bot scoring — available on Business and Enterprise plans — to allow verified good bots (e.g., Googlebot), challenge suspicious traffic, and log bot detection events to D1 for dashboard analysis.

---

## Context
Every request to a Worker on a Bot Management-enabled zone carries `request.cf.botManagement`, a struct containing a `score` (1–99, lower = more likely bot), `verifiedBot` (boolean for known crawlers), and `staticResource` (boolean for assets). Workers read these fields with zero extra latency because Cloudflare's edge populates them before the Worker runs. A KV-backed allowlist lets you whitelist specific bot user-agents or ASNs that your business relies on (e.g., monitoring services). Detections are written to D1 in a `waitUntil()` call so they never add latency to the response, and a Grafana-compatible SQL query exposes the bot score distribution for dashboarding.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "bot-management"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "BOT_ALLOWLIST_KV"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "BOT_LOG_DB"
database_name = "bot-logs"
database_id = "<your-d1-database-id>"

[vars]
BOT_SCORE_THRESHOLD = "30"
CHALLENGE_PAGE_URL = "https://example.com/challenge"
```

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  BOT_ALLOWLIST_KV: KVNamespace;
  BOT_LOG_DB: D1Database;
  BOT_SCORE_THRESHOLD: string;
  CHALLENGE_PAGE_URL: string;
}

interface BotManagement {
  score: number;
  verifiedBot: boolean;
  staticResource: boolean;
  ja3Hash?: string;
}

async function isAllowlisted(env: Env, request: Request): Promise<boolean> {
  const ua = request.headers.get("User-Agent") ?? "";
  const asn = (request.cf as Record<string, unknown>)?.asn as string | undefined;

  // Check UA prefix key (e.g., "ua:Googlebot")
  const uaKey = `ua:${ua.split("/")[0]}`;
  const [uaEntry, asnEntry] = await Promise.all([
    env.BOT_ALLOWLIST_KV.get(uaKey),
    asn ? env.BOT_ALLOWLIST_KV.get(`asn:${asn}`) : Promise.resolve(null),
  ]);
  return uaEntry !== null || asnEntry !== null;
}

async function logDetection(
  env: Env,
  request: Request,
  bm: BotManagement,
  action: string
): Promise<void> {
  const url = new URL(request.url);
  await env.BOT_LOG_DB.prepare(
    `INSERT INTO bot_detections
       (ts, path, score, verified_bot, ja3_hash, action, country, asn)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      Date.now(),
      url.pathname,
      bm.score,
      bm.verifiedBot ? 1 : 0,
      bm.ja3Hash ?? null,
      action,
      (request.cf as Record<string, unknown>)?.country ?? null,
      (request.cf as Record<string, unknown>)?.asn ?? null
    )
    .run();
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cf = request.cf as Record<string, unknown> | undefined;
    const bm = cf?.botManagement as BotManagement | undefined;

    // If bot management data is unavailable (e.g., zone not enabled), pass through
    if (!bm) return fetch(request);

    const threshold = parseInt(env.BOT_SCORE_THRESHOLD, 10);

    // Always allow verified bots (Googlebot, Bingbot, etc.)
    if (bm.verifiedBot) {
      ctx.waitUntil(logDetection(env, request, bm, "allow_verified"));
      return fetch(request);
    }

    // Check custom allowlist
    if (await isAllowlisted(env, request)) {
      ctx.waitUntil(logDetection(env, request, bm, "allow_allowlist"));
      return fetch(request);
    }

    // Block or challenge based on score
    if (bm.score < threshold) {
      ctx.waitUntil(logDetection(env, request, bm, "challenge"));
      // Redirect to managed challenge page
      return Response.redirect(env.CHALLENGE_PAGE_URL, 302);
    }

    // Borderline scores (threshold to threshold+20) — log but allow
    if (bm.score < threshold + 20) {
      ctx.waitUntil(logDetection(env, request, bm, "allow_borderline"));
    }

    return fetch(request);
  },
};
```

```sql
-- D1 schema (run once with wrangler d1 execute)
CREATE TABLE IF NOT EXISTS bot_detections (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  path        TEXT    NOT NULL,
  score       INTEGER NOT NULL,
  verified_bot INTEGER NOT NULL DEFAULT 0,
  ja3_hash    TEXT,
  action      TEXT    NOT NULL,
  country     TEXT,
  asn         TEXT
);

CREATE INDEX IF NOT EXISTS idx_bot_ts    ON bot_detections (ts);
CREATE INDEX IF NOT EXISTS idx_bot_score ON bot_detections (score);
```

## Section 3 — Integration / Testing

```bash
# Create D1 database
wrangler d1 create bot-logs
# Update wrangler.toml database_id, then apply schema:
wrangler d1 execute bot-logs --file=schema.sql

# Create KV namespace for allowlist
wrangler kv namespace create BOT_ALLOWLIST_KV

# Populate allowlist entries
wrangler kv key put --namespace-id=<id> "ua:UptimeRobot" "true"
wrangler kv key put --namespace-id=<id> "asn:AS15169" "true"  # Google ASN

# Deploy
wrangler deploy

# Query bot score distribution (dashboard query)
wrangler d1 execute bot-logs --command "
  SELECT
    CASE
      WHEN score < 30  THEN 'bot (0-29)'
      WHEN score < 50  THEN 'suspicious (30-49)'
      WHEN score < 80  THEN 'borderline (50-79)'
      ELSE                  'human (80-99)'
    END AS bucket,
    COUNT(*) AS requests,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
  FROM bot_detections
  WHERE ts > unixepoch('now', '-1 day') * 1000
  GROUP BY bucket
  ORDER BY MIN(score);
"

# Check recent challenge actions
wrangler d1 execute bot-logs --command "
  SELECT path, score, country, ja3_hash, datetime(ts/1000, 'unixepoch') AS time
  FROM bot_detections
  WHERE action = 'challenge'
  ORDER BY ts DESC
  LIMIT 20;
"
```

---

## Anti-patterns
- **Blocking on score alone without verified_bot check** — Googlebot has a low score by design; always check `verifiedBot` first to avoid blocking legitimate crawlers.
- **Doing D1 writes synchronously in the request path** — use `ctx.waitUntil()` to avoid adding I/O latency to every response.
- **Using a fixed global threshold for all paths** — set lower thresholds for sensitive endpoints (e.g., `/api/checkout`) and higher ones for public content.
- **Ignoring `staticResource`** — image and font requests from real browsers are often scored low; use `staticResource` to skip bot checks for assets.

---

## Gotchas
- `request.cf.botManagement` is only populated on zones with Bot Management enabled (Business or Enterprise plan). On lower plans the property is absent.
- D1 is eventually consistent for reads across regions; log queries may miss the last few seconds of events.
- JA3 fingerprints (`ja3Hash`) are not guaranteed to be present on all requests — always handle the `undefined` case.
- `Response.redirect()` returns a 302; for API clients that do not follow redirects, return a 429 with a JSON body instead.

---

## Verification

```bash
# Simulate a low-score request (use a known bot UA or manipulate headers in dev)
curl -i -A "python-requests/2.31.0" https://bot-management.<subdomain>.workers.dev/

# Verify D1 captured the detection
wrangler d1 execute bot-logs --command \
  "SELECT * FROM bot_detections ORDER BY ts DESC LIMIT 5;"

# Check KV allowlist is working
wrangler kv key list --namespace-id=<id>

# Tail live logs to watch scoring in real time
wrangler tail --format=pretty | grep -E 'score|action|verified'
```

---

## Related
- `workers-load-balancer-health-check-kv.md`
- `terraform-cloudflare-workers-kv-r2.md`

---

## Sources
- Cloudflare Bot Management — https://developers.cloudflare.com/bots/
- Workers `request.cf` properties — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Cloudflare D1 — https://developers.cloudflare.com/d1/
