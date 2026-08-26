# Email A/B Subject Line Testing With Workers and Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project (example.com) sends notification emails (new follower, reply, trending post) and wants to know which subject line phrasing drives higher open rates without relying on third-party ESP dashboards. A/B assignment must be deterministic per user per campaign so retries don't flip the variant, and results must be queryable in real time via Analytics Engine.

## Context
Cloudflare Analytics Engine accepts arbitrary data points via `writeDataPoint` directly from a Worker, making it the right store for open/send events without a separate database. Workers can deterministically assign variants using a stable hash of userId + campaignId. The open pixel is served by a separate Worker that logs the impression and redirects. No external analytics vendor is needed.

## Variant Assignment — Deterministic Hash

Variant assignment must be stable: the same user must always receive the same variant for a given campaign regardless of which Worker instance processes the send. A simple FNV-1a hash of `${userId}:${campaignId}` modulo the number of variants guarantees this without a database lookup.

```typescript
// ab-assign.ts
export function assignVariant(
  userId: string,
  campaignId: string,
  variants: string[]
): string {
  const key = `${userId}:${campaignId}`;
  let hash = 2166136261; // FNV offset basis
  for (let i = 0; i < key.length; i++) {
    hash ^= key.charCodeAt(i);
    hash = (hash * 16777619) >>> 0; // FNV prime, keep 32-bit unsigned
  }
  return variants[hash % variants.length];
}

// Example usage
const variant = assignVariant(userId, "notif-follower-v3", ["control", "treatment"]);
// "control" or "treatment" — same result on every retry
```

## Send Worker — Logging Impressions

When the email is sent the Worker writes a `send` data point to Analytics Engine. The `blobs` carry the variant and campaign; `doubles` carry a 1 so SQL aggregations (`SUM`) can count sends.

```typescript
// send-worker.ts
interface Env {
  EMAIL_AE: AnalyticsEngineDataset;
}

const SUBJECTS: Record<string, Record<string, string>> = {
  "notif-follower-v3": {
    control:   "Someone followed you on example project",
    treatment: "You have a new follower 👀",
  },
};

export async function sendNotificationEmail(
  env: Env,
  userId: string,
  recipientEmail: string,
  campaignId: string
): Promise<void> {
  const variants = Object.keys(SUBJECTS[campaignId]);
  const variant = assignVariant(userId, campaignId, variants);
  const subject = SUBJECTS[campaignId][variant];

  await sendViaMailChannels(env, { to: recipientEmail, subject, html: await buildBody(env, campaignId) });

  env.EMAIL_AE.writeDataPoint({
    blobs: [campaignId, variant, "send"],
    doubles: [1],
    indexes: [campaignId],
  });
}
```

## Open Tracking Worker — Logging Opens

The email body contains a 1×1 tracking pixel URL: `https://track.example.com/open?c=<campaignId>&u=<userId>&v=<variant>`. The tracking Worker logs the open event to Analytics Engine and returns the transparent GIF. The variant is encoded in the URL (set at send time) so the open Worker does not need to re-derive it.

```typescript
// open-tracker.ts
const GIF_1x1 = new Uint8Array([
  0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,
  0x00,0xff,0x00,0x2c,0x00,0x00,0x00,0x00,0x01,0x00,
  0x01,0x00,0x00,0x02,0x00,0x3b,
]);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const campaignId = url.searchParams.get("c") ?? "unknown";
    const userId     = url.searchParams.get("u") ?? "unknown";
    const variant    = url.searchParams.get("v") ?? "unknown";

    // De-duplicate: only count first open per user per campaign
    const dedupKey = `open:${campaignId}:${userId}`;
    const already = await env.OPEN_DEDUP_KV.get(dedupKey);
    if (!already) {
      env.EMAIL_AE.writeDataPoint({
        blobs: [campaignId, variant, "open"],
        doubles: [1],
        indexes: [campaignId],
      });
      await env.OPEN_DEDUP_KV.put(dedupKey, "1", { expirationTtl: 30 * 86400 });
    }

    return new Response(GIF_1x1, {
      headers: {
        "Content-Type": "image/gif",
        "Cache-Control": "no-store, no-cache",
      },
    });
  },
};
```

## Querying Results — Analytics Engine SQL API

Analytics Engine exposes a SQL API at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`. Poll this from a dashboard Worker or a cron to compute open rates per variant.

```typescript
// query-results.ts
export async function getABResults(
  accountId: string,
  apiToken: string,
  campaignId: string
): Promise<{ variant: string; sends: number; opens: number; openRate: number }[]> {
  const sql = `
    SELECT
      blob2 AS variant,
      blob3 AS event_type,
      SUM(_sample_interval * double1) AS count
    FROM EMAIL_METRICS
    WHERE
      timestamp > NOW() - INTERVAL '30' DAY
      AND blob1 = '${campaignId}'
    GROUP BY blob2, blob3
  `;

  const resp = await fetch(
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

  const json = await resp.json<{ data: { variant: string; event_type: string; count: number }[] }>();

  // Pivot into per-variant rows
  const byVariant: Record<string, { sends: number; opens: number }> = {};
  for (const row of json.data) {
    if (!byVariant[row.variant]) byVariant[row.variant] = { sends: 0, opens: 0 };
    if (row.event_type === "send") byVariant[row.variant].sends += row.count;
    if (row.event_type === "open") byVariant[row.variant].opens += row.count;
  }

  return Object.entries(byVariant).map(([variant, { sends, opens }]) => ({
    variant,
    sends,
    opens,
    openRate: sends > 0 ? opens / sends : 0,
  }));
}
```

## Anti-patterns
- Storing variant assignment in D1 at send time and reading it back in the open Worker — creates a round-trip on every pixel load and a hot-row under burst traffic; encode the variant in the pixel URL instead.
- Using random assignment per send — retries flip the variant and inflate one bucket's sends while the other gets credited for the open.
- Counting opens without deduplication — email clients pre-fetch images; without a KV dedup gate a single open generates multiple data points.
- Running statistical significance tests outside a controlled time window — mixing results from list-growth periods distorts the sample.

## Gotchas
- Analytics Engine data points are sampled at high volume; use `_sample_interval` in SQL aggregations (`SUM(_sample_interval * double1)`) to get unbiased counts.
- The SQL API requires the dataset to be bound in the Worker's `wrangler.toml` under `[[analytics_engine_datasets]]` with a `dataset` name matching the `analytics_engine_dataset` binding name.
- Apple Mail Privacy Protection pre-loads tracking pixels; open rates for Apple Mail users will be inflated regardless of variant — segment by client if possible.
- Analytics Engine retains data for 31 days on the default plan; export results to R2 or D1 before the window closes if longer retention is needed.

## Verification
1. Send 100 test emails split 50/50 across two variants; confirm Analytics Engine shows 50 sends per variant within 5 minutes.
2. Open 10 emails for one variant; query the SQL API and verify `openRate` ≈ 0.20 for that variant.
3. Re-trigger the send for the same userId/campaignId and confirm the variant is identical (hash is deterministic).
4. Open the same pixel URL twice for one user; confirm only one open data point is recorded (KV dedup working).

## Related
- [email-open-click-analytics-engine.md](email-open-click-analytics-engine.md)
- [email-a-b-testing.md](email-a-b-testing.md)
- [email-template-versioning-ab-testing-r2.md](email-template-versioning-ab-testing-r2.md)
- [email-click-tracking-privacy-preserving-workers.md](email-click-tracking-privacy-preserving-workers.md)
- [apple-mail-privacy-protection-open-rate-impact.md](apple-mail-privacy-protection-open-rate-impact.md)

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/email-routing/email-workers/
