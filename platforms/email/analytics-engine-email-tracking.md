# Email Open and Click Tracking with Cloudflare Analytics Engine

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Standard email tracking relies on third-party pixel URLs and click-redirect services managed by the ESP. When you use a self-hosted or multi-ESP stack, or when you need raw event data for custom BI dashboards, you need your own tracking infrastructure.

Cloudflare **Analytics Engine** is purpose-built for this workload: it accepts high-frequency write events from Workers with no external database round-trip, stores data in a time-series columnar format, and exposes it via a SQL API. A tracking Worker handles the open pixel and click redirect, writes a data point to Analytics Engine in the same Worker invocation, and returns the response in milliseconds.

This avoids the latency and cost of writing every open/click to D1 or an external analytics service.

---

## Context

### Analytics Engine Data Model

Each `writeDataPoint` call writes one **data point** with:

| Field | Capacity | Use |
|-------|----------|-----|
| `indexes` | 1 string (96 bytes) | Partition key — typically campaign or email ID |
| `blobs` | 20 strings (1 KB each) | Categorical dimensions: recipient, template, link label, country |
| `doubles` | 20 floats | Numeric values: link position, message size |
| `timestamp` | auto (ms precision) | Event time |

Data points are queryable via `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql` with a ClickHouse-compatible SQL dialect.

### Privacy Considerations

Tracking pixels are blocked by Apple Mail Privacy Protection (MPP), certain corporate firewalls, and some email clients that pre-fetch images. Open tracking data should be treated as a **lower bound**, not ground truth. Always supplement with click data (more reliable) and engagement signals.

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "email-tracker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[analytics_engine_datasets]]
binding = "EMAIL_ANALYTICS"
dataset = "email_events"

[[kv_namespaces]]
binding = "LINK_MAP"
id      = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"    # maps token → destination URL

[vars]
BASE_TRACKING_URL  = "https://track.example.com"
PIXEL_CACHE_SECS   = "86400"
```

---

## Section 2: Event Schema Design

Define a consistent schema for data point fields before writing any events. Changing field positions later requires a migration.

```typescript
// src/schema.ts

/**
 * Analytics Engine data point layout for email events.
 *
 * index1  : campaign_id (partition key — queries within a campaign are fast)
 *
 * blob1   : event_type     — "open" | "click"
 * blob2   : email_id       — unique per recipient message
 * blob3   : recipient      — normalized email address
 * blob4   : template       — template slug (e.g. "welcome", "invoice")
 * blob5   : link_label     — for clicks: human label of the link (e.g. "cta-button")
 * blob6   : country        — CF-IPCountry header value
 * blob7   : user_agent     — first 512 chars of User-Agent
 * blob8   : mail_client    — inferred client: "apple-mail", "gmail-web", "outlook", "other"
 *
 * double1 : link_position  — 0-based index of the link in the email (clicks only)
 * double2 : is_bot         — 1 if heuristically a bot/pre-fetch, 0 otherwise
 */

export interface EmailEventPoint {
  campaignId: string;
  eventType: "open" | "click";
  emailId: string;
  recipient: string;
  template: string;
  linkLabel?: string;
  country?: string;
  userAgent?: string;
  mailClient?: string;
  linkPosition?: number;
  isBot?: boolean;
}
```

---

## Section 3: Tracking Pixel Worker (Open Tracking)

```typescript
// src/open-tracker.ts
import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";
import type { EmailEventPoint } from "./schema";
import { inferMailClient, isLikelyBot } from "./heuristics";

export interface Env {
  EMAIL_ANALYTICS: AnalyticsEngineDataset;
  PIXEL_CACHE_SECS: string;
}

// 1×1 transparent GIF (37 bytes, base64-encoded)
const PIXEL_B64 =
  "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

function decodePixel(): Uint8Array {
  const binary = atob(PIXEL_B64);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

function writeOpenEvent(
  point: EmailEventPoint,
  analytics: AnalyticsEngineDataset
): void {
  analytics.writeDataPoint({
    indexes: [point.campaignId],
    blobs: [
      point.eventType,           // blob1
      point.emailId,             // blob2
      point.recipient,           // blob3
      point.template,            // blob4
      point.linkLabel ?? "",     // blob5
      point.country ?? "",       // blob6
      (point.userAgent ?? "").slice(0, 512), // blob7
      point.mailClient ?? "other",           // blob8
    ],
    doubles: [
      point.linkPosition ?? 0,   // double1
      point.isBot ? 1 : 0,       // double2
    ],
  });
}

export async function handlePixelRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);

  // Token encodes: base64url(JSON.stringify({ campaignId, emailId, recipient, template }))
  const token = url.searchParams.get("t");
  if (!token) {
    return new Response(decodePixel(), {
      headers: { "Content-Type": "image/gif", "Cache-Control": "no-store" },
    });
  }

  let metadata: { campaignId: string; emailId: string; recipient: string; template: string };
  try {
    metadata = JSON.parse(atob(token.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return new Response(decodePixel(), {
      headers: { "Content-Type": "image/gif", "Cache-Control": "no-store" },
    });
  }

  const ua = request.headers.get("User-Agent") ?? "";
  const country = request.headers.get("CF-IPCountry") ?? "";
  const mailClient = inferMailClient(ua);
  const bot = isLikelyBot(ua, request.headers);

  writeOpenEvent(
    {
      campaignId: metadata.campaignId,
      eventType: "open",
      emailId: metadata.emailId,
      recipient: metadata.recipient,
      template: metadata.template,
      country,
      userAgent: ua,
      mailClient,
      isBot: bot,
    },
    env.EMAIL_ANALYTICS
  );

  const cacheSecs = parseInt(env.PIXEL_CACHE_SECS, 10);
  return new Response(decodePixel(), {
    headers: {
      "Content-Type": "image/gif",
      // Allow CDN caching so MPP prefetch doesn't fire the Worker repeatedly
      "Cache-Control": `public, max-age=${cacheSecs}, immutable`,
    },
  });
}
```

---

## Section 4: Click Redirect Worker

```typescript
// src/click-tracker.ts
import type { AnalyticsEngineDataset, KVNamespace } from "@cloudflare/workers-types";
import { inferMailClient, isLikelyBot } from "./heuristics";

export interface ClickEnv {
  EMAIL_ANALYTICS: AnalyticsEngineDataset;
  LINK_MAP: KVNamespace;
}

interface LinkRecord {
  destination: string;
  campaignId: string;
  emailId: string;
  recipient: string;
  template: string;
  label: string;
  position: number;
}

export async function handleClickRequest(
  request: Request,
  env: ClickEnv
): Promise<Response> {
  const url = new URL(request.url);
  const token = url.pathname.replace("/c/", "").split("/")[0];

  if (!token) return Response.redirect("https://example.com", 302);

  const raw = await env.LINK_MAP.get(token, { type: "json" }) as LinkRecord | null;

  if (!raw) {
    return Response.redirect("https://example.com", 302);
  }

  const ua = request.headers.get("User-Agent") ?? "";
  const country = request.headers.get("CF-IPCountry") ?? "";

  env.EMAIL_ANALYTICS.writeDataPoint({
    indexes: [raw.campaignId],
    blobs: [
      "click",                             // blob1
      raw.emailId,                         // blob2
      raw.recipient,                       // blob3
      raw.template,                        // blob4
      raw.label,                           // blob5
      country,                             // blob6
      ua.slice(0, 512),                    // blob7
      inferMailClient(ua),                 // blob8
    ],
    doubles: [
      raw.position,                        // double1
      isLikelyBot(ua, request.headers) ? 1 : 0, // double2
    ],
  });

  // 307 preserves method; 302 is fine for GET-based link clicks
  return Response.redirect(raw.destination, 302);
}
```

---

## Section 5: Mail Client and Bot Heuristics

```typescript
// src/heuristics.ts

export function inferMailClient(ua: string): string {
  const u = ua.toLowerCase();
  if (u.includes("applemail") || u.includes("mimestream")) return "apple-mail";
  if (u.includes("googleimageproxy") || u.includes("gmail")) return "gmail-web";
  if (u.includes("outlook")) return "outlook";
  if (u.includes("thunderbird")) return "thunderbird";
  if (u.includes("yahoomail") || u.includes("yahoo mail")) return "yahoo-mail";
  return "other";
}

/**
 * Heuristically detect pre-fetches and bot opens.
 * Apple MPP uses "Mozilla/5.0" with no identifying features but adds
 * specific iCloud IP ranges. We detect on UA alone for portability.
 */
export function isLikelyBot(ua: string, headers: Headers): boolean {
  const u = ua.toLowerCase();

  // Known bot patterns
  if (u.includes("googleimageproxy")) return true;
  if (u.includes("yahoo link preview")) return true;
  if (u.includes("microsoft office")) return true;

  // Outlook Safe Links prefetcher
  if (headers.get("X-Scanning-Agent") !== null) return true;

  // Missing UA is suspicious in click context but acceptable for pixel
  if (!ua) return true;

  return false;
}
```

---

## Section 6: Querying Analytics Engine

Query event data via the Analytics Engine SQL API from a Worker or external tool.

```typescript
// src/analytics-query.ts

export async function getCampaignStats(
  campaignId: string,
  accountId: string,
  apiToken: string
): Promise<unknown> {
  const sql = `
    SELECT
      blob1 AS event_type,
      countIf(blob1 = 'open'  AND double2 = 0) AS human_opens,
      countIf(blob1 = 'open'  AND double2 = 1) AS bot_opens,
      countIf(blob1 = 'click' AND double2 = 0) AS human_clicks,
      countIf(blob1 = 'click' AND double2 = 1) AS bot_clicks,
      blob8  AS mail_client,
      blob6  AS country,
      toStartOfDay(timestamp) AS day
    FROM email_events
    WHERE
      index1 = '${campaignId}'
      AND timestamp >= now() - INTERVAL '30' DAY
    GROUP BY event_type, mail_client, country, day
    ORDER BY day DESC, human_opens DESC
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!response.ok) {
    throw new Error(`Analytics API error ${response.status}: ${await response.text()}`);
  }

  return response.json();
}

// Unique open rate per campaign
export async function getUniqueOpenRate(
  campaignId: string,
  totalSent: number,
  accountId: string,
  apiToken: string
): Promise<number> {
  const sql = `
    SELECT uniq(blob3) AS unique_openers
    FROM email_events
    WHERE index1 = '${campaignId}' AND blob1 = 'open' AND double2 = 0
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  const data = await response.json<{ data: [{ unique_openers: number }] }>();
  const uniqueOpeners = data.data[0]?.unique_openers ?? 0;
  return totalSent > 0 ? uniqueOpeners / totalSent : 0;
}
```

---

## Section 7: Generating Tracking URLs at Send Time

```typescript
// src/token-generator.ts

interface EmailMetadata {
  campaignId: string;
  emailId: string;
  recipient: string;
  template: string;
}

export function generatePixelUrl(
  base: string,
  metadata: EmailMetadata
): string {
  const token = btoa(JSON.stringify(metadata))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `${base}/px/1.gif?t=${token}`;
}

export async function generateClickUrl(
  base: string,
  metadata: EmailMetadata,
  destination: string,
  label: string,
  position: number,
  kv: KVNamespace
): Promise<string> {
  // Use a short random token so URLs are not predictably guessable
  const token = crypto.randomUUID().replace(/-/g, "").slice(0, 12);

  await kv.put(
    token,
    JSON.stringify({
      destination,
      ...metadata,
      label,
      position,
    } satisfies LinkRecord & EmailMetadata),
    { expirationTtl: 60 * 60 * 24 * 365 } // 1 year
  );

  return `${base}/c/${token}`;
}
```

---

## Anti-Patterns

- **Writing to Analytics Engine inside a `waitUntil`** — `writeDataPoint` is synchronous and must be called before the response is returned. If you defer it to `ctx.waitUntil`, the Worker runtime may batch the data point late and it will miss the query window.
- **Using `blob` fields as free-form strings** — Analytics Engine blobs are indexed; high-cardinality free-text (e.g., full subject lines) wastes index space without query benefit. Use IDs and labels instead.
- **Not filtering bots in queries** — Apple MPP and link scanners inflate open counts dramatically. Always add `AND double2 = 0` to filter bot events.
- **Storing destination URLs in the pixel token** — pixel tokens are embedded in HTML that clients can inspect. Never encode the destination in the token; always use a KV lookup for click redirects.
- **Using 301 redirects for click tracking** — 301 is cached by browsers. A user who clicks once and returns via browser back/forward bypasses the tracking Worker on subsequent visits. Use 302 or 307.

---

## Gotchas

- **Analytics Engine retention** — data is retained for **90 days** by default. For long-term trend analysis, export aggregate queries to D1 or R2 via a nightly Cron Trigger.
- **writeDataPoint rate limits** — up to **25 data points per Worker invocation** can be written in a single call to `writeDataPoint`. Batch events where possible; each call is 1 data point, so 25 calls = 25 points in one invocation.
- **SQL API quota** — Analytics Engine SQL queries are subject to rate limits per account. Cache frequently-run dashboard queries in KV with a short TTL (e.g., 5 minutes).
- **`uniq()` vs `COUNT(DISTINCT)`** — the Analytics Engine SQL API uses ClickHouse syntax. Use `uniq(column)` for approximate distinct counts; `COUNT(DISTINCT column)` may not be supported in all query contexts.
- **Pixel caching and MPP** — Apple Mail Privacy Protection pre-fetches pixels via Apple proxy servers and caches them. Setting a long `max-age` on the pixel response prevents Apple from re-firing the Worker on every email open, but means you see one event per device, not per open.

---

## Verification

```bash
# Deploy the Worker
wrangler deploy

# Trigger a test open (replace token with a real base64 payload)
curl -v "https://track.example.com/px/1.gif?t=$(echo -n '{"campaignId":"test-001","emailId":"msg-abc","recipient":"test@example.com","template":"welcome"}' | base64 | tr '+/' '-_' | tr -d '=')"

# Trigger a test click (assuming token "abc123def456" was written to KV)
curl -v "https://track.example.com/c/abc123def456"

# Query the Analytics Engine (replace placeholders)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1, count() AS n FROM email_events WHERE index1 = '\''test-001'\'' GROUP BY blob1"}'

# Expected: {"data":[{"blob1":"open","n":1}],...}
```

---

## Related

- `email-open-tracking.md` — general open tracking patterns
- `email-click-tracking.md` — general click tracking patterns
- `email-analytics-metrics.md` — metrics definitions and benchmarks
- `apple-mail-privacy-protection-open-rate-impact.md` — MPP impact on open tracking
- `tracking-pixel-privacy.md` — privacy and consent considerations
- `email-archiving-compliance-retention-r2.md` — long-term event retention to R2

---

## Sources

- [Cloudflare Analytics Engine documentation](https://developers.cloudflare.com/analytics/analytics-engine/)
- [Analytics Engine SQL API](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/)
- [Analytics Engine — writeDataPoint reference](https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/)
- [Apple Mail Privacy Protection — developer guidance](https://support.apple.com/en-us/HT212109)
- [RFC 3986 — URI Generic Syntax (base64url encoding)](https://datatracker.ietf.org/doc/html/rfc3986)
- [ClickHouse SQL reference (Analytics Engine dialect)](https://clickhouse.com/docs/en/sql-reference/)
