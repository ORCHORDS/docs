# Expo Push Notification Receipts via Workers Cron

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Push notifications sent through Expo's push API are not always delivered, but failures only surface in the receipt API polled 15–30 minutes later. A Workers Cron Trigger is the natural place to poll receipts and take action on `DeviceNotRegistered` or `MessageTooBig` errors.

## Context
Expo's push service is a two-step API: `/push/send` returns ticket IDs immediately, and `/push/getReceipts` returns delivery status after ~15 minutes. Workers Cron runs on Cloudflare's edge on a schedule, reads pending ticket IDs from D1, polls Expo, and writes results back. The whole flow is serverless and costs nothing at rest.

## Storing Ticket IDs After Send

After calling `/push/send`, persist each ticket ID to D1 so the cron can pick them up later.

```typescript
// worker/src/push.ts
import { Env } from './types';

export interface PushTicket {
  id: string;
  userId: string;
  sentAt: number;
  polledAt?: number;
}

export async function sendAndStorePush(
  env: Env,
  to: string,
  userId: string,
  body: string,
  data?: Record<string, unknown>
): Promise<void> {
  const res = await fetch('https://exp.host/--/api/v2/push/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ to, body, data }),
  });

  const json = (await res.json()) as { data: { status: string; id?: string; details?: unknown } };

  if (json.data.status === 'ok' && json.data.id) {
    await env.DB.prepare(
      `INSERT INTO push_tickets (ticket_id, user_id, sent_at) VALUES (?, ?, ?)`
    )
      .bind(json.data.id, userId, Date.now())
      .run();
  }
}
```

D1 schema:

```sql
CREATE TABLE push_tickets (
  ticket_id TEXT PRIMARY KEY,
  user_id   TEXT NOT NULL,
  sent_at   INTEGER NOT NULL,
  polled_at INTEGER,
  status    TEXT,
  error     TEXT
);

CREATE TABLE push_tokens (
  user_id TEXT PRIMARY KEY,
  token   TEXT NOT NULL
);
```

## Cron Handler: Poll Expo Receipt API

```typescript
// worker/src/index.ts
import { Env } from './types';

const EXPO_RECEIPT_URL = 'https://exp.host/--/api/v2/push/getReceipts';
const POLL_BATCH = 100; // Expo max per request
const RECEIPT_MIN_AGE_MS = 15 * 60 * 1000; // 15 minutes

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(pollReceipts(env));
  },
};

async function pollReceipts(env: Env): Promise<void> {
  const cutoff = Date.now() - RECEIPT_MIN_AGE_MS;

  const { results } = await env.DB.prepare(
    `SELECT ticket_id, user_id FROM push_tickets
     WHERE polled_at IS NULL AND sent_at < ?
     LIMIT ?`
  )
    .bind(cutoff, POLL_BATCH)
    .all<{ ticket_id: string; user_id: string }>();

  if (!results.length) return;

  const ids = results.map((r) => r.ticket_id);

  const res = await fetch(EXPO_RECEIPT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ ids }),
  });

  const json = (await res.json()) as {
    data: Record<string, { status: 'ok' | 'error'; message?: string; details?: { error?: string } }>;
  };

  const now = Date.now();
  const stmt = env.DB.prepare(
    `UPDATE push_tickets SET polled_at = ?, status = ?, error = ? WHERE ticket_id = ?`
  );

  const batch = ids.map((id) => {
    const receipt = json.data[id];
    return stmt.bind(now, receipt?.status ?? 'unknown', receipt?.details?.error ?? null, id);
  });

  await env.DB.batch(batch);
  await handleErrors(env, results, json.data);
}
```

## Handling DeviceNotRegistered and Other Errors

```typescript
type ReceiptMap = Record<string, { status: string; details?: { error?: string } }>;

async function handleErrors(
  env: Env,
  tickets: { ticket_id: string; user_id: string }[],
  receipts: ReceiptMap
): Promise<void> {
  const userMap = Object.fromEntries(tickets.map((t) => [t.ticket_id, t.user_id]));

  for (const [id, receipt] of Object.entries(receipts)) {
    if (receipt.status !== 'error') continue;

    const errorCode = receipt.details?.error;
    const userId = userMap[id];
    if (!userId) continue;

    if (errorCode === 'DeviceNotRegistered') {
      // Token is stale — remove it so we stop sending to this device
      await env.DB.prepare(`DELETE FROM push_tokens WHERE user_id = ?`)
        .bind(userId)
        .run();
      console.log(`Removed stale push token for user ${userId}`);
    } else if (errorCode === 'MessageTooBig') {
      // Log for investigation; payload needs trimming
      console.error(`MessageTooBig for ticket ${id} (user ${userId})`);
    } else if (errorCode === 'InvalidCredentials') {
      // Alert on-call — Expo credentials rotated without updating Worker secret
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        body: JSON.stringify({ text: `Expo push: InvalidCredentials on ticket ${id}` }),
      });
    }
  }
}
```

## wrangler.toml Cron Setup

```toml
name = "push-receipt-poller"
main = "src/index.ts"
compatibility_date = "2025-08-01"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<your-d1-id>"

[triggers]
crons = ["*/20 * * * *"]   # every 20 minutes — receipts need 15 min to settle
```

## Anti-patterns
- Polling receipts immediately after send — Expo needs 15+ minutes to resolve delivery
- Storing ticket IDs in KV with no TTL — orphaned tickets accumulate silently
- Ignoring `DeviceNotRegistered` — keeps sending to dead tokens, wastes Expo quota
- Fetching more than 100 receipt IDs per request — Expo enforces a 100-item batch limit
- Re-polling already-processed tickets — check `polled_at IS NULL` to avoid duplicate work

## Gotchas
- Expo receipt IDs are different from push ticket IDs — map them correctly at the `/send` step
- `status: 'ok'` in the receipt only means Expo delivered to APNs/FCM, not that the user saw it
- Workers Cron fires at most once per minute; do not rely on sub-minute precision
- D1's `batch()` has a 1 000-statement limit; split into chunks if POLL_BATCH > 1 000
- `ctx.waitUntil` is required so the cron does not terminate before the async work finishes

## Verification

```sql
-- Check unpolled tickets older than 15 minutes
SELECT COUNT(*) AS pending
FROM push_tickets
WHERE polled_at IS NULL AND sent_at < (unixepoch('now','subsec') * 1000 - 900000);

-- Error breakdown
SELECT error, COUNT(*) AS cnt
FROM push_tickets
WHERE status = 'error'
GROUP BY error
ORDER BY cnt DESC;

-- DeviceNotRegistered rate (last 24 h)
SELECT
  ROUND(100.0 * SUM(CASE WHEN error = 'DeviceNotRegistered' THEN 1 ELSE 0 END) / COUNT(*), 2)
    AS dnr_rate_pct
FROM push_tickets
WHERE sent_at > (unixepoch('now','subsec') * 1000 - 86400000);
```

```bash
# Trigger cron manually for testing
wrangler dev --local --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*%2F20+*+*+*+*"
```

## Related
- `expo-notifications-workers-scheduled-push-d1.md` — scheduling pushes with D1
- `mobile-push-delivery-reliability.md` — delivery SLO patterns
- `mobile-push-notifications-cloudflare-queues.md` — queue-based fan-out for push
- `expo-config-plugins-workers-push-token-registration.md` — token upsert on boot

## Sources
- https://docs.expo.dev/push-notifications/sending-notifications/#individual-errors
- https://docs.expo.dev/push-notifications/push-receipts-and-errors/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/api/worker-api/
