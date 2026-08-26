# Email NPS / CSAT Survey Response Tracking with Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You embed a 1–10 NPS rating row or a 1–5 CSAT scale directly in transactional
emails and need to capture the click, store the score, and redirect the user to a
thank-you page—without a third-party survey tool and without relying on JavaScript
inside the email client.

## Context

Email clients execute no JavaScript. Ratings must be plain anchor links pointing
to a Cloudflare Worker endpoint. The Worker reads the score and subscriber ID from
query params, writes the result to D1, then 302-redirects to a branded landing
page. All logic is server-side; the pattern works in Gmail, Apple Mail, Outlook,
and any webmail.

## D1 Schema

```sql
-- migrations/0001_nps_responses.sql
CREATE TABLE IF NOT EXISTS nps_responses (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  subscriber_id TEXT NOT NULL,
  campaign_id   TEXT NOT NULL,
  score         INTEGER NOT NULL CHECK (score BETWEEN 0 AND 10),
  verbatim      TEXT,
  responded_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ip_hash       TEXT
);

CREATE INDEX IF NOT EXISTS idx_nps_campaign ON nps_responses (campaign_id);
CREATE INDEX IF NOT EXISTS idx_nps_subscriber ON nps_responses (subscriber_id);
```

Apply with: `wrangler d1 migrations apply email-db --remote`

## Email Link Generation (template helper)

```typescript
// src/nps-links.ts
export function buildNpsLinks(
  baseUrl: string,
  subscriberId: string,
  campaignId: string
): { score: number; url: string; label: string }[] {
  const token = btoa(JSON.stringify({ sub: subscriberId, cid: campaignId }));
  return Array.from({ length: 11 }, (_, i) => ({
    score: i,
    url: `${baseUrl}/survey/nps?t=${encodeURIComponent(token)}&s=${i}`,
    label: String(i),
  }));
}
```

Render the links as a horizontal table row in your MJML/HTML template. The `t`
parameter is a base64 JWT-lite carrying subscriber and campaign context; sign it
with an HMAC for production use.

## Worker: Capture Response and Redirect

```typescript
// src/survey-worker.ts
interface Env {
  DB: D1Database;
  NPS_HMAC_SECRET: string;
  THANK_YOU_URL: string;
}

async function verifyToken(
  token: string,
  secret: string
): Promise<{ sub: string; cid: string } | null> {
  try {
    // In production replace with HMAC-SHA256 verification
    return JSON.parse(atob(token)) as { sub: string; cid: string };
  } catch {
    return null;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/survey/nps")) {
      return new Response("not found", { status: 404 });
    }

    const rawToken = url.searchParams.get("t") ?? "";
    const scoreStr = url.searchParams.get("s") ?? "";
    const score = parseInt(scoreStr, 10);

    if (isNaN(score) || score < 0 || score > 10) {
      return new Response("invalid score", { status: 400 });
    }

    const payload = await verifyToken(rawToken, env.NPS_HMAC_SECRET);
    if (!payload) {
      return new Response("invalid token", { status: 403 });
    }

    // Idempotent: one response per subscriber per campaign
    const existing = await env.DB.prepare(
      "SELECT id FROM nps_responses WHERE subscriber_id = ? AND campaign_id = ?"
    )
      .bind(payload.sub, payload.cid)
      .first<{ id: string }>();

    if (!existing) {
      const ipRaw = request.headers.get("CF-Connecting-IP") ?? "";
      const ipHash = ipRaw
        ? Array.from(
            new Uint8Array(
              await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ipRaw))
            )
          )
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("")
        : null;

      await env.DB.prepare(
        `INSERT INTO nps_responses (subscriber_id, campaign_id, score, ip_hash)
         VALUES (?, ?, ?, ?)`
      )
        .bind(payload.sub, payload.cid, score, ipHash)
        .run();
    }

    return Response.redirect(
      `${env.THANK_YOU_URL}?score=${score}&already=${existing ? "1" : "0"}`,
      302
    );
  },
};
```

## Verbatim Follow-up Page

After redirect, the thank-you page optionally POSTs a free-text comment back:

```typescript
// Append to survey-worker.ts fetch handler, route POST /survey/nps/comment
if (request.method === "POST" && url.pathname === "/survey/nps/comment") {
  const body = await request.json<{ token: string; comment: string }>();
  const p = await verifyToken(body.token, env.NPS_HMAC_SECRET);
  if (!p) return new Response("forbidden", { status: 403 });
  const trimmed = (body.comment ?? "").slice(0, 2000);
  await env.DB.prepare(
    "UPDATE nps_responses SET verbatim = ? WHERE subscriber_id = ? AND campaign_id = ?"
  )
    .bind(trimmed, p.sub, p.cid)
    .run();
  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## Analytics: Score Breakdown Query

```sql
-- NPS calculation: promoters (9-10) minus detractors (0-6) / total
SELECT
  campaign_id,
  COUNT(*)                                              AS total,
  ROUND(100.0 * SUM(CASE WHEN score >= 9 THEN 1 END) / COUNT(*), 1) AS pct_promoters,
  ROUND(100.0 * SUM(CASE WHEN score <= 6 THEN 1 END) / COUNT(*), 1) AS pct_detractors,
  ROUND(
    100.0 * (SUM(CASE WHEN score >= 9 THEN 1 END)
           - SUM(CASE WHEN score <= 6 THEN 1 END)) / COUNT(*), 1
  )                                                     AS nps_score
FROM nps_responses
GROUP BY campaign_id
ORDER BY responded_at DESC;
```

## Anti-patterns

- **Storing raw IP addresses** – hash IPs before storing; GDPR and CASL treat IP
  addresses as personal data.
- **Re-recording on every click** – the idempotency check prevents ballot stuffing
  if a user clicks multiple scores; always upsert-guard before INSERT.
- **No token expiry** – survey links should expire (e.g., 30 days); embed an `exp`
  claim in the token and reject expired submissions.

## Gotchas

- Some email clients pre-fetch links (bot clicks); the Worker should detect
  non-human agents via `User-Agent` heuristics or Cloudflare bot scores before
  recording a response.
- Apple Mail Privacy Protection may trigger the URL on behalf of the user without
  a score being selected; the `s` param solves this because each score is a
  distinct URL (no single tracking pixel ambiguity).
- D1 has a 30-second query timeout per request in `fetch` handlers; NPS writes are
  fast single-row INSERTs and well within budget.

## Verification

```bash
# Simulate a score-7 click
curl -I "https://example.com/survey/nps?t=$(echo -n '{"sub":"u1","cid":"c1"}' | base64)&s=7"
# Expect: HTTP/1.1 302 Found  Location: https://example.com/thank-you?score=7&already=0

# Check D1
wrangler d1 execute email-db --remote \
  --command "SELECT * FROM nps_responses ORDER BY responded_at DESC LIMIT 5;"
```

## Related

- `email-click-tracking.md`
- `email-click-tracking-privacy-preserving-workers.md`
- `email-open-click-analytics-engine.md`
- `email-consent-audit-trail-d1.md`

## Sources

- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- NPS methodology: https://www.netpromoter.com/know/
- CF bot management signals: https://developers.cloudflare.com/bots/
