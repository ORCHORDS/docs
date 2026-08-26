# Privacy-Preserving Email Click Tracking on Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Standard email click tracking embeds user-identifying tokens in URLs and logs full
IP addresses, creating GDPR and CCPA exposure. Marketers still need to know whether a
campaign link was clicked and which variant performed better. A Cloudflare Worker acting
as the redirect endpoint can record click events without storing PII: it hashes the
subscriber identifier with a rotating pepper, drops the real IP, and uses Cloudflare
Analytics Engine for aggregated reporting rather than per-user event rows.

## Context

Each link in an outgoing email is rewritten to
`https://t.acme.example/c/<campaign>/<link-id>/<token>` where `<token>` is an HMAC of
the subscriber ID with a per-campaign pepper that rotates every 24 hours. The Worker
resolves the destination, emits an Analytics Engine data point, and immediately 302s the
reader to the real URL. No raw subscriber ID or IP is written to any persistent store.
Aggregate counts are queryable via the Analytics Engine SQL API without exposing
individual reader identities.

## Link Rewriting at Send Time

```typescript
import { createHmac } from "node:crypto";

export interface Env {
  CLICK_PEPPER_KV: KVNamespace;   // rotating pepper stored per campaign
  DB: D1Database;
  BASE_REDIRECT_URL: string;      // e.g. "https://t.acme.example/c"
}

// Rotate pepper daily; call this from a Cron Trigger Worker.
export async function rotatePepper(env: Env, campaignId: string): Promise<void> {
  const pepper = crypto.randomUUID().replace(/-/g, "");
  // TTL = 48 hours so in-flight emails sent just before rotation still resolve.
  await env.CLICK_PEPPER_KV.put(
    `pepper:${campaignId}`,
    pepper,
    { expirationTtl: 172_800 }
  );
}

export function buildClickUrl(
  baseUrl: string,
  pepper: string,
  campaignId: string,
  linkId: string,
  subscriberId: string,
  destination: string
): string {
  // Pseudonymous token: HMAC(pepper, subscriberId) — not reversible without the pepper.
  const token = createHmac("sha256", pepper)
    .update(subscriberId)
    .digest("hex")
    .slice(0, 16);

  const dest = encodeURIComponent(destination);
  return `${baseUrl}/${campaignId}/${linkId}/${token}?d=${dest}`;
}

// Example usage during template rendering:
export async function rewriteLinks(
  html: string,
  campaignId: string,
  subscriberId: string,
  env: Env
): Promise<string> {
  const pepper = await env.CLICK_PEPPER_KV.get(`pepper:${campaignId}`);
  if (!pepper) throw new Error(`No pepper found for campaign ${campaignId}`);

  let linkIndex = 0;
  return html.replace(/]+)"/g, (_match, url: string) => {
    const linkId = `l${linkIndex++}`;
    const clickUrl = buildClickUrl(
      env.BASE_REDIRECT_URL,
      pepper,
      campaignId,
      linkId,
      subscriberId,
      url
    );
    return ``;
  });
}
```

## Click Redirect Worker with Analytics Engine

```typescript
export interface Env {
  CLICK_ANALYTICS: AnalyticsEngineDataset;
  CLICK_PEPPER_KV: KVNamespace;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Path: /c/<campaignId>/<linkId>/<token>
    const [, , campaignId, linkId, token] = url.pathname.split("/");
    const destination = url.searchParams.get("d");

    if (!campaignId || !linkId || !token || !destination) {
      return new Response("Bad Request", { status: 400 });
    }

    // Emit to Analytics Engine — no IP, no raw subscriber ID.
    env.CLICK_ANALYTICS.writeDataPoint({
      blobs: [campaignId, linkId, token],   // token = pseudonymous subscriber proxy
      doubles: [1],
      indexes: [campaignId],
    });

    // Optional: write a coarse aggregate to D1 (no PII).
    await env.DB.prepare(
      `INSERT INTO click_counts (campaign_id, link_id, day, count)
       VALUES (?, ?, date('now'), 1)
       ON CONFLICT (campaign_id, link_id, day) DO UPDATE SET count = count + 1`
    )
      .bind(campaignId, linkId)
      .run();

    // Never set a tracking cookie on the redirect response.
    return Response.redirect(decodeURIComponent(destination), 302);
  },
};
```

## Analytics Engine Query and D1 Aggregate Schema

```typescript
// Query click counts from Analytics Engine via the REST API (no PII exposed).
export async function fetchClickReport(
  accountId: string,
  apiToken: string,
  campaignId: string
): Promise<{ linkId: string; clicks: number }[]> {
  const query = `
    SELECT blob2 AS link_id, SUM(_sample_interval) AS clicks
    FROM click_tracking_dataset
    WHERE blob1 = '${campaignId}'
      AND timestamp > NOW() - INTERVAL '7' DAY
    GROUP BY link_id
    ORDER BY clicks DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const data = (await resp.json()) as {
    data: { link_id: string; clicks: number }[];
  };
  return data.data;
}

// D1 coarse aggregate schema (no subscriber references):
/*
CREATE TABLE IF NOT EXISTS click_counts (
  campaign_id  TEXT NOT NULL,
  link_id      TEXT NOT NULL,
  day          TEXT NOT NULL,
  count        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (campaign_id, link_id, day)
);
*/
```

## Anti-patterns

- Storing full subscriber IDs in the redirect URL path or query string — even if hashed,
  a rainbow table attack on a known subscriber list can reverse the mapping.
- Logging `request.headers.get("CF-Connecting-IP")` to D1 — this constitutes processing
  personal data under GDPR and requires explicit consent and a lawful basis.
- Using a static salt instead of a rotating pepper — an attacker who obtains the salt can
  precompute all tokens for a known subscriber list.

## Gotchas

- Analytics Engine data points are eventually consistent; fresh clicks may not appear in
  SQL queries for up to 60 seconds after the redirect.
- The pepper must be available in KV before sending the campaign; a missing pepper causes
  the redirect Worker to return 400 for all clicks in that campaign.
- Apple Mail Privacy Protection pre-fetches all links in an email upon delivery; this will
  inflate click counts. Filter out Apple proxy user-agent strings in the redirect Worker:
  `request.headers.get("User-Agent")?.includes("Apple-Mail")`.

## Verification

```bash
# Trigger a test redirect and confirm no IP is written to D1.
curl -v "https://t.acme.example/c/camp001/l0/deadbeef1234?d=https%3A%2F%2Facme.example%2Fproduct"

# Query Analytics Engine for click counts (should see count > 0, no PII).
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data '{"query":"SELECT blob2, SUM(_sample_interval) FROM click_tracking_dataset WHERE blob1='"'"'camp001'"'"' GROUP BY blob2"}'
```

## Related

- `email/email-click-tracking.md`
- `email/tracking-pixel-privacy.md`
- `email/analytics-engine-email-tracking.md`
- `email/apple-mail-privacy-protection-open-rate-impact.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/kv/
- https://gdpr-info.eu/art-25-gdpr/
- https://developers.cloudflare.com/email-routing/email-workers/
