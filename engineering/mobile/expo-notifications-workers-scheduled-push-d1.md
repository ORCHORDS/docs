# Expo Notifications Workers Scheduled Push D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An Expo app needs to send scheduled push notifications — reminders, appointment alerts, daily
digests — where the schedule is set by the user and persisted server-side. Local notifications
are insufficient because the device may be offline or the app may have been uninstalled and
reinstalled. Teams want Cloudflare Workers + D1 to store schedules and a Cloudflare Cron Trigger
to fire batched notifications via Expo Push Notification Service (EPNS), with delivery receipts
tracked back in D1.

## Context

Expo's push notification service (EPNS) accepts a simple JSON payload to its HTTP API
(`https://exp.host/--/api/v2/push/send`) and supports APNs + FCM delivery in a single call.
A Cloudflare Worker running on a Cron Trigger can query D1 for due notifications, batch-call
EPNS, and record receipts — all without a dedicated notification server.

Stack:
- Expo SDK 52+ (`expo-notifications`)
- Expo Push Token (EAS Build / managed workflow)
- Cloudflare Workers (schedule management + EPNS caller)
- Cloudflare Cron Triggers (1-minute resolution)
- Cloudflare D1 (notification schedule + receipt storage)
- TypeScript

## D1 Schema

```sql
-- D1: notification schedules and delivery receipts

CREATE TABLE IF NOT EXISTS push_schedules (
  id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id       TEXT NOT NULL,
  expo_token    TEXT NOT NULL,         -- ExponentPushToken[...]
  title         TEXT NOT NULL,
  body          TEXT NOT NULL,
  data          TEXT,                  -- JSON string for app payload
  scheduled_at  TEXT NOT NULL,         -- ISO8601 UTC
  recurrence    TEXT,                  -- 'daily', 'weekly', or NULL for one-shot
  sent_at       TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_push_schedules_due
  ON push_schedules (scheduled_at)
  WHERE sent_at IS NULL;

CREATE TABLE IF NOT EXISTS push_receipts (
  id            TEXT PRIMARY KEY,      -- EPNS ticket ID
  schedule_id   TEXT NOT NULL REFERENCES push_schedules(id),
  status        TEXT NOT NULL,         -- 'ok', 'error', 'pending'
  error_message TEXT,
  checked_at    TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Cloudflare Worker: Schedule Manager + Cron Trigger

```typescript
// worker/src/index.ts
import { Env } from './types';
import { sendBatchNotifications, checkReceipts } from './epns';

export default {
  // HTTP handler: register/cancel schedules from the Expo app
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/schedules' && request.method === 'POST') {
      return createSchedule(request, env);
    }
    if (url.pathname.startsWith('/schedules/') && request.method === 'DELETE') {
      return deleteSchedule(request, url, env);
    }
    if (url.pathname === '/schedules' && request.method === 'GET') {
      return listSchedules(request, url, env);
    }
    return new Response('Not found', { status: 404 });
  },

  // Cron Trigger: runs every minute to send due notifications
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runNotificationCron(env));
  },
};

async function createSchedule(request: Request, env: Env): Promise<Response> {
  const { userId, expoToken, title, body, data, scheduledAt, recurrence } =
    await request.json<{
      userId: string;
      expoToken: string;
      title: string;
      body: string;
      data?: Record<string, unknown>;
      scheduledAt: string;
      recurrence?: 'daily' | 'weekly';
    }>();

  if (!expoToken.startsWith('ExponentPushToken[')) {
    return new Response(JSON.stringify({ error: 'Invalid Expo push token format' }), {
      status: 400,
    });
  }

  const result = await env.DB.prepare(
    `INSERT INTO push_schedules (user_id, expo_token, title, body, data, scheduled_at, recurrence)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     RETURNING id`,
  )
    .bind(userId, expoToken, title, body, data ? JSON.stringify(data) : null, scheduledAt, recurrence ?? null)
    .first<{ id: string }>();

  return new Response(JSON.stringify({ scheduleId: result?.id }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function deleteSchedule(request: Request, url: URL, env: Env): Promise<Response> {
  const scheduleId = url.pathname.split('/').pop();
  await env.DB.prepare(`DELETE FROM push_schedules WHERE id = ?`).bind(scheduleId).run();
  return new Response(JSON.stringify({ ok: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function listSchedules(request: Request, url: URL, env: Env): Promise<Response> {
  const userId = url.searchParams.get('userId');
  if (!userId) return new Response(JSON.stringify({ error: 'userId required' }), { status: 400 });
  const { results } = await env.DB.prepare(
    `SELECT id, title, body, scheduled_at, recurrence, sent_at
     FROM push_schedules WHERE user_id = ? ORDER BY scheduled_at ASC LIMIT 50`,
  )
    .bind(userId)
    .all();
  return new Response(JSON.stringify({ schedules: results }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

async function runNotificationCron(env: Env): Promise<void> {
  const now = new Date().toISOString();

  // Fetch up to 100 due notifications (EPNS batch limit is 100)
  const { results: dueSchedules } = await env.DB.prepare(
    `SELECT id, expo_token, title, body, data, recurrence, scheduled_at
     FROM push_schedules
     WHERE scheduled_at <= ? AND sent_at IS NULL
     ORDER BY scheduled_at ASC LIMIT 100`,
  )
    .bind(now)
    .all<{
      id: string;
      expo_token: string;
      title: string;
      body: string;
      data: string | null;
      recurrence: string | null;
      scheduled_at: string;
    }>();

  if (dueSchedules.length === 0) return;

  const tickets = await sendBatchNotifications(dueSchedules);

  // Record tickets and mark sent; reschedule recurring notifications
  const stmts = dueSchedules.flatMap((schedule, i) => {
    const ticket = tickets[i];
    const markSent = env.DB.prepare(
      `UPDATE push_schedules SET sent_at = ? WHERE id = ?`,
    ).bind(now, schedule.id);

    const recordReceipt = env.DB.prepare(
      `INSERT INTO push_receipts (id, schedule_id, status, error_message)
       VALUES (?, ?, ?, ?)`,
    ).bind(
      ticket.id ?? crypto.randomUUID(),
      schedule.id,
      ticket.status,
      ticket.details?.error ?? null,
    );

    const reschedule = schedule.recurrence
      ? env.DB.prepare(
          `INSERT INTO push_schedules (user_id, expo_token, title, body, data, scheduled_at, recurrence)
           SELECT user_id, expo_token, title, body, data,
             datetime(scheduled_at, CASE recurrence WHEN 'daily' THEN '+1 day' ELSE '+7 days' END),
             recurrence
           FROM push_schedules WHERE id = ?`,
        ).bind(schedule.id)
      : null;

    return reschedule ? [markSent, recordReceipt, reschedule] : [markSent, recordReceipt];
  });

  await env.DB.batch(stmts);
}
```

```typescript
// worker/src/epns.ts
interface EpnsMessage {
  to: string;
  title: string;
  body: string;
  data?: Record<string, unknown>;
  sound?: 'default';
  badge?: number;
  priority?: 'default' | 'normal' | 'high';
}

interface EpnsTicket {
  id?: string;
  status: 'ok' | 'error';
  message?: string;
  details?: { error?: string; fault?: string };
}

export async function sendBatchNotifications(
  schedules: { expo_token: string; title: string; body: string; data: string | null }[],
): Promise<EpnsTicket[]> {
  const messages: EpnsMessage[] = schedules.map((s) => ({
    to: s.expo_token,
    title: s.title,
    body: s.body,
    data: s.data ? JSON.parse(s.data) : undefined,
    sound: 'default',
    priority: 'high',
  }));

  const response = await fetch('https://exp.host/--/api/v2/push/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'Accept-Encoding': 'gzip, deflate',
    },
    body: JSON.stringify(messages),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`EPNS batch send failed ${response.status}: ${text}`);
  }

  const { data } = await response.json<{ data: EpnsTicket[] }>();
  return data;
}

export async function checkReceipts(
  ticketIds: string[],
): Promise<Record<string, { status: string; message?: string }>> {
  const response = await fetch('https://exp.host/--/api/v2/push/getReceipts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: ticketIds }),
  });
  const { data } = await response.json<{ data: Record<string, { status: string; message?: string }> }>();
  return data;
}
```

```typescript
// worker/src/types.ts
export interface Env {
  DB: D1Database;
}
```

Wrangler config:
```toml
# wrangler.toml
name = "push-scheduler"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "push-db"
database_id = "<your-d1-database-id>"

[[triggers]]
crons = ["* * * * *"]  # every minute
```

## Expo App: Register Token and Create Schedule

```typescript
// src/notifications/pushService.ts
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';

const WORKER_BASE = 'https://push.example.workers.dev';

export async function registerAndSendTokenToWorker(userId: string): Promise<string | null> {
  if (!Device.isDevice) {
    console.warn('Push notifications require a physical device');
    return null;
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') return null;

  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;

  // Store token on the server for use by Cron Trigger
  await fetch(`${WORKER_BASE}/path/to/token`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expoToken: token }),
  });

  return token;
}

export async function scheduleReminder(params: {
  userId: string;
  expoToken: string;
  title: string;
  body: string;
  scheduledAt: Date;
  recurrence?: 'daily' | 'weekly';
  data?: Record<string, unknown>;
}): Promise<string> {
  const response = await fetch(`${WORKER_BASE}/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...params,
      scheduledAt: params.scheduledAt.toISOString(),
    }),
  });

  if (!response.ok) throw new Error(`Schedule creation failed: ${response.status}`);
  const { scheduleId } = await response.json<{ scheduleId: string }>();
  return scheduleId;
}

export async function cancelSchedule(scheduleId: string): Promise<void> {
  await fetch(`${WORKER_BASE}/schedules/${scheduleId}`, { method: 'DELETE' });
}
```

## Anti-patterns

- **Using Expo local notifications for server-driven schedules** — local notifications are lost
  on app reinstall and cannot be managed from the server. Use EPNS + Workers Cron.
- **Sending one EPNS request per notification** — EPNS accepts batches of 100; sending 1,000
  individual requests hits rate limits and inflates CPU time on the Worker.
- **Storing raw FCM/APNs device tokens instead of Expo tokens** — Expo tokens abstract platform
  differences; raw tokens require separate APNs and FCM logic and certificate management.
- **Not using `ctx.waitUntil()`** in the Cron Trigger handler — D1 writes after the cron body
  returns will be cancelled by the runtime. Always wrap async DB work in `ctx.waitUntil()`.
- **Scheduling at second-level resolution** — Cron Triggers have 1-minute granularity. Notify
  users that "reminder set for approximately 9:00 AM" not "9:00:00 AM".

## Gotchas

- EPNS does not guarantee delivery order within a batch; do not rely on ordering for multi-step
  notification sequences.
- D1 `datetime(scheduled_at, '+1 day')` uses SQLite's date functions, which operate in UTC.
  Ensure all `scheduled_at` values stored by the client are UTC ISO8601.
- Expo push tokens change when a user reinstalls the app. Implement a token refresh flow
  (`Notifications.addPushTokenListener`) and update the `push_schedules` table.
- The EPNS free tier limits to 100 messages per minute per project. For high-volume apps, spread
  cron execution using Cloudflare Queues to fan out EPNS calls.
- Workers Cron Triggers may fire up to 30 seconds late during high load. Add a 60-second
  tolerance window in the D1 query: `scheduled_at <= datetime('now', '+60 seconds')`.

## Verification

```bash
# Manually trigger the cron handler
curl -X POST https://push.example.workers.dev/__scheduled \
  -H 'x-cf-cron: * * * * *'
# Note: only works in Wrangler dev; blocked in production

# In Wrangler dev:
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Inspect D1 for sent notifications
npx wrangler d1 execute push-db \
  --command "SELECT id, title, sent_at FROM push_schedules ORDER BY scheduled_at DESC LIMIT 10;"

# Check EPNS receipts
npx wrangler d1 execute push-db \
  --command "SELECT * FROM push_receipts WHERE status = 'error' LIMIT 10;"
```

## Related

- `expo-eas-build-cloudflare-workers-secrets.md`
- `mobile-push-notifications-cloudflare-queues.md`
- `mobile-push-delivery-reliability.md`
- `capacitor-workers-push-notification-scheduling-d1.md`
- `mobile-push-notifications-rich-interactive.md`

## Sources

- https://docs.expo.dev/push-notifications/overview/
- https://docs.expo.dev/push-notifications/sending-notifications/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/
