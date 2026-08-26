# Cloudflare Waiting Room Queue Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your site deploys a Cloudflare Waiting Room during high-traffic events (flash sales,
ticket drops, product launches) and you need to observe — in near-real-time and
historically — how many users are queued, how long they wait, what fraction bypass
the room, and when session throughput saturates the room's active-user limit.
The Cloudflare dashboard shows current state; it does not provide time-series
storage you can query after the event or correlate with revenue metrics.

## Context

Cloudflare Waiting Room fires a `waitingroom` Logpush log field and emits metrics
via the GraphQL Analytics API under `waitingRoomAnalyticsAdaptiveGroups`. However,
Logpush only captures per-visitor HTTP events, not the aggregate queue depth signal.
The recommended pattern is a combination of:
1. A scheduled Worker that polls the Waiting Room REST API every minute to capture
   aggregate metrics (queue depth, active sessions, estimated wait time) and writes
   them to Analytics Engine.
2. A Logpush → R2 pipeline for per-visitor event audit logs (separate from queue metrics).

This article focuses on the aggregate monitoring pipeline using Analytics Engine.

---

## Waiting Room REST API polling Worker

```typescript
// src/wr-poller.ts
interface WaitingRoomStatus {
  estimated_queued_users: number;
  estimated_total_active_users: number;
  event_end_time: string | null;
  estimated_wait_time: number;   // seconds
  result_time: string;           // ISO-8601
}

export async function pollWaitingRoom(env: Env): Promise<void> {
  const rooms: string[] = env.WAITING_ROOM_IDS.split(","); // "zone_id:room_id,..."

  for (const entry of rooms) {
    const [zoneId, roomId] = entry.split(":");
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${zoneId}/waiting_rooms/${roomId}/status`,
      { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
    );

    if (!res.ok) continue;
    const { result } = await res.json<{ result: WaitingRoomStatus }>();

    env.AE.writeDataPoint({
      blobs:   [zoneId, roomId],
      doubles: [
        result.estimated_queued_users,           // double1
        result.estimated_total_active_users,     // double2
        result.estimated_wait_time,              // double3 (seconds)
      ],
      indexes: ["waiting_room"],
    });
  }
}

// Wired to cron:
export default {
  async scheduled(_e: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await pollWaitingRoom(env);
  },
};
```

## wrangler.toml

```toml
name = "waiting-room-monitor"
main = "src/wr-poller.ts"
compatibility_date = "2026-08-01"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "WAITING_ROOM_METRICS"

[triggers]
crons = ["* * * * *"]   # every minute
```

## Queue depth time-series query

```sql
-- Queue depth and active sessions for a specific room over the last 2 hours
SELECT
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE) AS bucket,
  max(double1)                                       AS peak_queued,
  max(double2)                                       AS peak_active,
  avg(double3)                                       AS avg_wait_sec
FROM WAITING_ROOM_METRICS
WHERE timestamp >= NOW() - INTERVAL '2' HOUR
  AND index1 = 'waiting_room'
  AND blob2 = ?   -- room ID
GROUP BY bucket
ORDER BY bucket ASC;
```

## Saturation alert — active sessions approaching room limit

```typescript
// src/saturation-alert.ts
export async function checkSaturation(env: Env, roomId: string, activeLimit: number): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      body: JSON.stringify({
        query: `
          SELECT max(double2) AS peak_active, max(double1) AS peak_queued, max(double3) AS max_wait_sec
          FROM WAITING_ROOM_METRICS
          WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
            AND index1 = 'waiting_room'
            AND blob2 = ?
        `,
        parameters: [roomId],
      }),
    }
  );

  const { data } = await res.json<{ data: Array<{ peak_active: number; peak_queued: number; max_wait_sec: number }> }>();
  if (!data.length) return;

  const { peak_active, peak_queued, max_wait_sec } = data[0];
  const utilizationPct = (peak_active / activeLimit) * 100;

  if (utilizationPct > 90) {
    await env.ALERT_QUEUE.send({
      severity: "warning",
      message: `Waiting Room ${roomId}: ${utilizationPct.toFixed(0)}% of active-session limit reached. Queue depth: ${peak_queued}. Est. wait: ${Math.round(max_wait_sec / 60)} min.`,
    });
  }
  if (peak_queued > 50_000) {
    await env.ALERT_QUEUE.send({
      severity: "critical",
      message: `Waiting Room ${roomId}: ${peak_queued.toLocaleString()} users queued. Queue exceeding capacity planning threshold.`,
    });
  }
}
```

## Bypass and admission rate from Logpush

```typescript
// Logpush field 'WaitingRoomState' = 'bypass' | 'waiting' | 'admitted'
// After routing Logpush HTTP logs to R2, query via Workers Analytics:
const bypassQuery = `
  SELECT
    toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS minute,
    countIf(blob3 = 'admitted')  AS admitted,
    countIf(blob3 = 'waiting')   AS waiting,
    countIf(blob3 = 'bypass')    AS bypassed,
    count()                      AS total
  FROM WR_LOGPUSH_AE
  WHERE timestamp >= NOW() - INTERVAL '30' MINUTE
  GROUP BY minute
  ORDER BY minute ASC
`;
// blob3 populated by a Logpush-to-AE transform Worker (see logpush-s3-compatible-r2-destination.md)
```

## Post-event capacity analysis

```sql
-- Peak queue depth and admission throughput for the last event (last 24 hours)
SELECT
  DATE(timestamp)                           AS event_date,
  max(double1)                              AS peak_queue_depth,
  max(double2)                              AS peak_active_sessions,
  max(double3)                              AS peak_wait_secs,
  round(max(double3) / 60.0, 1)            AS peak_wait_minutes
FROM WAITING_ROOM_METRICS
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
  AND index1 = 'waiting_room'
  AND blob2 = 'my-room-id'
GROUP BY event_date;
```

---

## Anti-patterns

- **Relying solely on the Cloudflare dashboard for event capacity planning**: the
  dashboard shows current state and has no export for post-event analysis. Store
  the time-series in AE from the start of any planned high-traffic event.
- **Polling faster than once per minute**: the Waiting Room status API reflects
  Cloudflare's own 1-minute sampling interval. Sub-minute polling returns identical
  data and wastes API quota.
- **Setting `total_active_users` limit without load-testing the origin**: the Waiting
  Room protects the origin only if the limit is calibrated to the origin's actual
  capacity. Monitor origin error rates alongside queue depth.

## Gotchas

- The Waiting Room REST API requires `Waiting Room: Read` permission on the API token
  scoped to the zone, not the account. A token with only account-level permissions
  returns 403.
- `estimated_queued_users` and `estimated_wait_time` are Cloudflare estimates, not
  exact counts. Treat them as trend signals, not precise measurements.
- A Waiting Room configured with a custom page (`custom_page_html`) does not affect
  the REST API response; the poller works regardless of page type.
- If the Waiting Room has no active event and no real-time queue, `estimated_queued_users`
  may return 0 even during normal traffic. Verify the room is active via the `status`
  field in the API response before writing a data point.

## Verification

```bash
# Manually check room status
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/waiting_rooms/$ROOM_ID/status" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '{queued: .result.estimated_queued_users, active: .result.estimated_total_active_users, wait_sec: .result.estimated_wait_time}'

# Query AE for last 10 minutes of data
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT max(double1) AS peak_q, max(double2) AS peak_active FROM WAITING_ROOM_METRICS WHERE timestamp >= NOW() - INTERVAL '"'"'10'"'"' MINUTE AND index1 = '"'"'waiting_room'"'"'"}' \
  | jq '.data[0]'
```

## Related

- `cloudflare-health-checks-origin-monitoring.md`
- `cloudflare-graphql-api-metrics-export-d1.md`
- `synthetic-monitoring-uptime-checks.md`
- `workers-cron-trigger-missed-execution-alerting.md`
- `logpush-s3-compatible-r2-destination.md`

## Sources

- Cloudflare Waiting Room: https://developers.cloudflare.com/waiting-room/
- Waiting Room status API: https://developers.cloudflare.com/waiting-room/reference/waiting-room-api/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
