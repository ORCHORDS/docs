# Capacitor Workers Push Notification Scheduling with D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Capacitor apps need to schedule future push notifications (reminders, drip campaigns, appointment alerts) without a dedicated backend—using Cloudflare Workers as the scheduler and D1 as the persistent schedule store, with delivery via FCM/APNS.

## Context
On-device scheduled notifications via `@capacitor/local-notifications` are erased when the user uninstalls and reinstalls the app, or switches devices. Moving the schedule to a Cloudflare D1 table lets a Worker cron trigger fan out notifications at the right time across all of a user's devices via FCM (Android) and APNS (iOS). The Capacitor app registers device push tokens with the Worker on startup and optionally submits schedule entries; the Worker cron runs every minute, queries D1 for due notifications, and dispatches them to the appropriate push gateway.

## D1 Schema

```sql
-- Create via: wrangler d1 execute push-db --file=schema.sql

CREATE TABLE IF NOT EXISTS device_tokens (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  platform    TEXT NOT NULL CHECK(platform IN ('ios', 'android')),
  token       TEXT NOT NULL,
  registered_at INTEGER NOT NULL,
  UNIQUE(user_id, token)
);

CREATE TABLE IF NOT EXISTS scheduled_notifications (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  title         TEXT NOT NULL,
  body          TEXT NOT NULL,
  data          TEXT,           -- JSON blob for deep-link payload
  scheduled_at  INTEGER NOT NULL, -- Unix ms
  sent_at       INTEGER,
  cancelled     INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scheduled_by_time
  ON scheduled_notifications(scheduled_at)
  WHERE sent_at IS NULL AND cancelled = 0;

CREATE INDEX IF NOT EXISTS idx_tokens_by_user
  ON device_tokens(user_id);
```

## Workers Implementation

```typescript
// worker/src/push-scheduler.ts
export interface Env {
  DB: D1Database;
  FCM_SERVER_KEY: string;
  APNS_KEY_ID: string;
  APNS_TEAM_ID: string;
  APNS_BUNDLE_ID: string;
  APNS_KEY_P8: string; // PEM private key stored as secret
}

interface DeviceToken {
  id: string;
  user_id: string;
  platform: "ios" | "android";
  token: string;
}

interface ScheduledNotification {
  id: string;
  user_id: string;
  title: string;
  body: string;
  data: string | null;
}

async function sendFCM(
  token: string,
  title: string,
  body: string,
  data: Record<string, string>,
  serverKey: string
): Promise<boolean> {
  const res = await fetch("https://fcm.googleapis.com/fcm/send", {
    method: "POST",
    headers: {
      Authorization: `key=${serverKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      to: token,
      notification: { title, body },
      data,
      priority: "high",
    }),
  });
  return res.ok;
}

async function sendAPNS(
  token: string,
  title: string,
  body: string,
  data: Record<string, string>,
  env: Env
): Promise<boolean> {
  // Sign JWT for APNS HTTP/2
  const header = btoa(JSON.stringify({ alg: "ES256", kid: env.APNS_KEY_ID }));
  const payload = btoa(
    JSON.stringify({ iss: env.APNS_TEAM_ID, iat: Math.floor(Date.now() / 1000) })
  );

  // Note: Real APNS JWT signing requires WebCrypto ECDSA with P-256.
  // This is a schematic—use a complete APNS library for production.
  const apnsJwt = `${header}.${payload}.SIGNATURE_PLACEHOLDER`;

  const res = await fetch(
    `https://api.push.apple.com/3/device/${token}`,
    {
      method: "POST",
      headers: {
        authorization: `bearer ${apnsJwt}`,
        "apns-topic": env.APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        aps: { alert: { title, body }, sound: "default", badge: 1 },
        ...data,
      }),
    }
  );
  return res.ok;
}

async function processDueNotifications(env: Env): Promise<number> {
  const now = Date.now();

  // Fetch up to 100 due notifications
  const due = await env.DB.prepare(
    `SELECT id, user_id, title, body, data
     FROM scheduled_notifications
     WHERE scheduled_at <= ?1 AND sent_at IS NULL AND cancelled = 0
     ORDER BY scheduled_at ASC
     LIMIT 100`
  )
    .bind(now)
    .all<ScheduledNotification>();

  if (!due.results?.length) return 0;

  let dispatched = 0;

  for (const notif of due.results) {
    const tokens = await env.DB.prepare(
      "SELECT id, user_id, platform, token FROM device_tokens WHERE user_id = ?1"
    )
      .bind(notif.user_id)
      .all<DeviceToken>();

    const extraData: Record<string, string> = notif.data
      ? JSON.parse(notif.data)
      : {};

    const sends = (tokens.results ?? []).map(async (dt) => {
      if (dt.platform === "android") {
        return sendFCM(dt.token, notif.title, notif.body, extraData, env.FCM_SERVER_KEY);
      } else {
        return sendAPNS(dt.token, notif.title, notif.body, extraData, env);
      }
    });

    await Promise.allSettled(sends);
    dispatched++;
  }

  // Mark all as sent in a batch
  const ids = due.results.map((n) => `'${n.id}'`).join(",");
  await env.DB.prepare(
    `UPDATE scheduled_notifications SET sent_at = ?1 WHERE id IN (${ids})`
  )
    .bind(now)
    .run();

  return dispatched;
}

export default {
  // REST handler: token registration + schedule CRUD
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /tokens — register a device token
    if (url.pathname === "/tokens" && request.method === "POST") {
      const { userId, platform, token } = await request.json<{
        userId: string;
        platform: "ios" | "android";
        token: string;
      }>();

      await env.DB.prepare(
        `INSERT INTO device_tokens (id, user_id, platform, token, registered_at)
         VALUES (?1, ?2, ?3, ?4, ?5)
         ON CONFLICT(user_id, token) DO UPDATE SET platform = excluded.platform,
           registered_at = excluded.registered_at`
      )
        .bind(crypto.randomUUID(), userId, platform, token, Date.now())
        .run();

      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // POST /schedule — schedule a notification
    if (url.pathname === "/schedule" && request.method === "POST") {
      const { userId, title, body, data, scheduledAt } =
        await request.json<{
          userId: string;
          title: string;
          body: string;
          data?: Record<string, string>;
          scheduledAt: number; // Unix ms
        }>();

      if (scheduledAt <= Date.now()) {
        return new Response(JSON.stringify({ error: "scheduledAt must be in the future" }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      }

      const id = crypto.randomUUID();
      await env.DB.prepare(
        `INSERT INTO scheduled_notifications
           (id, user_id, title, body, data, scheduled_at, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`
      )
        .bind(
          id,
          userId,
          title,
          body,
          data ? JSON.stringify(data) : null,
          scheduledAt,
          Date.now()
        )
        .run();

      return new Response(JSON.stringify({ id }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // DELETE /schedule/:id — cancel a scheduled notification
    if (url.pathname.startsWith("/schedule/") && request.method === "DELETE") {
      const id = url.pathname.replace("/schedule/", "");
      await env.DB.prepare(
        "UPDATE scheduled_notifications SET cancelled = 1 WHERE id = ?1"
      )
        .bind(id)
        .run();
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },

  // Cron trigger: runs every minute
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(processDueNotifications(env));
  },
};
```

```toml
# wrangler.toml
name = "push-scheduler"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "push-db"
database_id = "YOUR_D1_DB_ID"

[triggers]
crons = ["* * * * *"]
```

## Capacitor App Integration

```typescript
// src/services/pushScheduler.ts
import { PushNotifications } from "@capacitor/push-notifications";
import { Capacitor } from "@capacitor/core";

const WORKERS_URL = import.meta.env.VITE_WORKERS_URL as string;

export async function registerDeviceToken(userId: string): Promise<void> {
  await PushNotifications.requestPermissions();
  await PushNotifications.register();

  PushNotifications.addListener("registration", async ({ value: token }) => {
    const platform = Capacitor.getPlatform() as "ios" | "android";
    await fetch(`${WORKERS_URL}/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId, platform, token }),
    });
  });

  PushNotifications.addListener("registrationError", (err) => {
    console.error("Push registration failed:", err.error);
  });
}

export async function scheduleReminder(
  userId: string,
  title: string,
  body: string,
  scheduledAt: Date,
  data?: Record<string, string>
): Promise<string> {
  const res = await fetch(`${WORKERS_URL}/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      title,
      body,
      scheduledAt: scheduledAt.getTime(),
      data,
    }),
  });

  if (!res.ok) throw new Error(await res.text());
  const { id } = await res.json<{ id: string }>();
  return id;
}

export async function cancelReminder(scheduleId: string): Promise<void> {
  await fetch(`${WORKERS_URL}/schedule/${encodeURIComponent(scheduleId)}`, {
    method: "DELETE",
  });
}
```

## Anti-patterns
- Running the cron trigger every second—Workers cron minimum granularity is one minute; sub-minute precision requires a Durable Object alarm instead
- Storing APNS/FCM credentials in environment variables without using Wrangler secrets (`wrangler secret put FCM_SERVER_KEY`)
- Deleting sent notification rows immediately—keep them for at least 30 days for debugging delivery failures
- Querying `scheduled_notifications` without the `WHERE sent_at IS NULL` filter—will re-send already-dispatched notifications after a cron retry
- Using `@capacitor/local-notifications` for server-controlled schedules—local notifications are device-local and do not survive reinstall

## Gotchas
- Workers cron triggers fire at most once per minute; if the previous invocation is still running when the next minute fires, the next invocation is skipped—keep `processDueNotifications` well under 10 seconds
- D1 `IN (?)` with a dynamic list requires string interpolation of IDs; use `crypto.randomUUID()` for IDs to keep them safe for interpolation (no SQL injection via UUIDs)
- APNS HTTP/2 push requires `ECDSA P-256` JWT signing; Cloudflare Workers `crypto.subtle` supports this but the `importKey` call needs the key in JWK or PKCS#8 format—convert the `.p8` file with `openssl pkcs8 -topk8 -nocrypt`
- `@capacitor/push-notifications` on iOS requires `aps-environment` entitlement set to `production` for App Store builds and `development` for local testing—mismatches cause silent token rejection
- FCM `registration_id` tokens rotate; listen for the `registration` event on every app start and upsert the token, using the `ON CONFLICT DO UPDATE` pattern shown above

## Verification
1. `wrangler d1 execute push-db --local --file=schema.sql` then `wrangler dev`; POST a token and a notification scheduled 65 seconds in the future; wait for the cron to fire and confirm the `sent_at` column is set.
2. On a physical Android device, call `registerDeviceToken` and verify the token appears in `device_tokens` via `wrangler d1 execute push-db --command="SELECT * FROM device_tokens"`.
3. POST a notification scheduled 2 minutes in the future; cancel it via DELETE; confirm `cancelled = 1` and the cron does not dispatch it.
4. Simulate a failed FCM response (use a `nock` stub or `msw` in tests) and verify `sent_at` is still set—delivery best-effort, no infinite retry loop.
5. Deploy to production with `wrangler deploy` and use `wrangler tail` to stream logs; confirm cron invocations appear every minute.

## Related
- `mobile-push-notifications-cloudflare-queues.md`
- `ios-push-notifications-apns-workers.md`
- `capacitor-d1-sqlite-offline-sync.md`
- `workers-ai-push-notification-personalization.md`

## Sources
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://capacitorjs.com/docs/apis/push-notifications
