# Email Send-Time Optimization with Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You send marketing or transactional emails to a global subscriber list and notice large variance in open rates depending on when messages arrive. Recipients in Tokyo open at 9 AM JST; recipients in São Paulo open at 8 PM BRT. Blasting at one UTC time guarantees you land in the wrong time slot for most of the world.

The goal is to derive the optimal send window per recipient from historical engagement data stored in Analytics Engine, then schedule delivery per-recipient through Workers + Queues.

---

## Context

Cloudflare Analytics Engine is a time-series write-optimised store accessible from Workers. By logging email open and click events with a `timestamp` blob and a recipient `index`, you can later query per-recipient engagement distributions using the SQL API. Combined with the recipient's inferred or explicit time zone (stored in D1), you can bucket opens by local hour-of-day to find each subscriber's peak engagement window.

The optimisation pipeline runs as a nightly Cron Trigger Worker that:

1. Queries Analytics Engine for the last 90 days of opens per subscriber.
2. Computes the modal local-hour bucket.
3. Writes the preferred send-hour back to D1.
4. The send Worker reads the preferred hour and delays delivery via Queues until the next occurrence of that hour.

---

## Logging Opens to Analytics Engine

```typescript
// open-tracker-worker.ts (handles pixel requests)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const subscriberId = url.searchParams.get("sid");
    const campaignId = url.searchParams.get("cid");

    if (!subscriberId) {
      return new Response(null, { status: 400 });
    }

    env.EMAIL_ANALYTICS.writeDataPoint({
      indexes: [subscriberId],
      blobs: [campaignId ?? "unknown", "open"],
      doubles: [1],
      // timestamp defaults to Date.now()
    });

    // Return 1×1 transparent GIF
    const pixel = new Uint8Array([
      0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,
      0x00,0xff,0x00,0x2c,0x00,0x00,0x00,0x00,0x01,0x00,
      0x01,0x00,0x00,0x02,0x00,0x3b,
    ]);

    return new Response(pixel, {
      headers: { "Content-Type": "image/gif", "Cache-Control": "no-store" },
    });
  },
};
```

---

## Querying Analytics Engine for Per-Subscriber Open Hours

```typescript
// analytics-engine SQL API (called from Cron Worker)
async function fetchOpenHours(
  subscriberId: string,
  env: Env
): Promise<number[]> {
  const query = `
    SELECT
      toHour(timestamp) AS hour_utc,
      SUM(_sample_interval) AS opens
    FROM email_opens
    WHERE
      index1 = '${subscriberId}'
      AND timestamp >= NOW() - INTERVAL '90' DAY
    GROUP BY hour_utc
    ORDER BY opens DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  if (!resp.ok) throw new Error(`Analytics Engine query failed: ${resp.status}`);

  const data = await resp.json<{ data: { hour_utc: number; opens: number }[] }>();

  // Return hours ordered by open volume descending
  return data.data.map((row) => row.hour_utc);
}
```

---

## Computing Local-Hour Preference with Time Zone Offset

```typescript
async function computePreferredSendHour(
  subscriberId: string,
  env: Env
): Promise<number> {
  // Fetch subscriber's stored UTC offset in minutes from D1
  const row = await env.DB.prepare(
    "SELECT utc_offset_minutes FROM subscribers WHERE id = ?"
  )
    .bind(subscriberId)
    .first<{ utc_offset_minutes: number }>();

  const utcOffsetMinutes = row?.utc_offset_minutes ?? 0;

  // Get UTC hours ranked by open frequency
  const utcHours = await fetchOpenHours(subscriberId, env);

  if (utcHours.length === 0) {
    // No history — use global default: 9 AM local time
    return ((9 * 60 - utcOffsetMinutes + 1440) % 1440) / 60;
  }

  // Best UTC hour is top of the ranked list
  const bestUtcHour = utcHours[0];

  // Convert back to local hour for human-readable storage
  const localHour = Math.round(
    ((bestUtcHour * 60 + utcOffsetMinutes) % 1440) / 60
  );

  return localHour;
}
```

---

## Nightly Cron Worker to Refresh Preferred Hours

```typescript
// wrangler.toml
// [triggers]
// crons = ["0 2 * * *"]   # 02:00 UTC daily

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const batchSize = 500;
    let offset = 0;

    while (true) {
      const batch = await env.DB.prepare(
        "SELECT id FROM subscribers WHERE active = 1 LIMIT ? OFFSET ?"
      )
        .bind(batchSize, offset)
        .all<{ id: string }>();

      if (!batch.results.length) break;

      await Promise.allSettled(
        batch.results.map(async (sub) => {
          const preferredHour = await computePreferredSendHour(sub.id, env);

          await env.DB.prepare(
            `UPDATE subscribers
             SET preferred_send_hour_utc = ?, send_hour_updated_at = datetime('now')
             WHERE id = ?`
          )
            .bind(preferredHour, sub.id)
            .run();
        })
      );

      offset += batchSize;
    }
  },
};
```

---

## Scheduling Sends via Queues for the Right Hour

```typescript
// send-scheduler-worker.ts
export async function scheduleSend(
  subscriberId: string,
  payload: EmailPayload,
  env: Env
) {
  const row = await env.DB.prepare(
    "SELECT preferred_send_hour_utc FROM subscribers WHERE id = ?"
  )
    .bind(subscriberId)
    .first<{ preferred_send_hour_utc: number | null }>();

  const targetHour = row?.preferred_send_hour_utc ?? 9; // default 09:00 UTC

  const now = new Date();
  const nextSend = new Date(now);
  nextSend.setUTCHours(targetHour, 0, 0, 0);

  // If the window already passed today, schedule for tomorrow
  if (nextSend <= now) {
    nextSend.setUTCDate(nextSend.getUTCDate() + 1);
  }

  const delaySeconds = Math.floor((nextSend.getTime() - now.getTime()) / 1000);

  await env.EMAIL_QUEUE.send(
    { subscriberId, ...payload },
    { delaySeconds }
  );
}
```

---

## Anti-patterns

- **Querying Analytics Engine per send at delivery time** — SQL queries have latency; derive preferred hours in the nightly Cron and cache in D1.
- **Using only UTC opens without converting to local time** — a subscriber in UTC+9 who consistently opens at 09:00 JST appears in UTC bucket 00:00; always apply the offset before computing the modal hour.
- **Assuming time zone from IP geolocation on first email** — IPs change; prefer explicit time zone preference from signup, falling back to CF-IPCountry header mapped to a representative offset.
- **Recomputing buckets over all time** — limit the lookback window (90 days) to avoid stale patterns from subscribers who changed jobs or travel habits.

---

## Gotchas

- Analytics Engine `toHour()` returns UTC; there is no built-in time zone conversion in the AE SQL dialect. Apply offsets in application code.
- Analytics Engine has a write rate of 25 data points per request and up to 1,000 requests/second per dataset; high-volume open tracking may require batching via a Durable Object queue.
- Queues `delaySeconds` maximum is 43,200 (12 hours). If the target send window is more than 12 hours away, re-enqueue the message when it dequeues with the remaining delay, or use a Cron Trigger to drain a scheduled-sends table in D1.
- Subscribers with fewer than ~10 opens have insufficient data for reliable modal-hour computation; fall back to segment averages or a global default.

---

## Verification

```bash
# Confirm Analytics Engine dataset is receiving events
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT COUNT(*) as total FROM email_opens WHERE timestamp > NOW() - INTERVAL '\''1'\'' DAY"}'

# Check preferred hours were written
wrangler d1 execute DB \
  --command "SELECT id, preferred_send_hour_utc, send_hour_updated_at FROM subscribers LIMIT 10"

# Verify a queued message delay
wrangler queues consumer list EMAIL_QUEUE
```

---

## Related

- `email-scheduling-patterns.md`
- `analytics-engine-email-tracking.md`
- `email-open-click-analytics-engine.md`
- `email-engagement-scoring-segmentation.md`
- `transactional-queue-cloudflare-queues.md`

---

## Sources

- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Queues delayed delivery — https://developers.cloudflare.com/queues/configuration/delay-messages/
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
