# Capacitor Workers Push Notification Click Tracking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Capacitor (Ionic) app sends push notifications via a Cloudflare Worker but has no reliable signal for which notifications were opened, which deep-link path was navigated to, or how long after delivery the user engaged. Standard APNS/FCM delivery receipts report delivery, not user interaction. The team needs per-campaign click analytics without adding a third-party SDK.

## Context

Capacitor's `@capacitor/push-notifications` plugin exposes `pushNotificationActionPerformed` for both foreground and background notification opens. The notification payload includes a `data` field that can carry a tracking ID. On click, the app fires a lightweight beacon to a Cloudflare Worker, which writes the click event to Analytics Engine and — if the notification carried a deep link — returns a redirect or stores the destination for the app to navigate to. D1 stores the campaign metadata and the Workers Queues consumer updates delivery/click counts asynchronously.

---

## Notification Payload Schema

```typescript
// Shared type used by both Worker and app
interface NotificationPayload {
  title: string;
  body: string;
  data: {
    trackingId: string;   // UUID, stored in D1 campaigns table
    deepLink?: string;    // e.g. "app://products/123"
    campaignId: string;
    channel: 'promo' | 'transactional' | 'alert';
  };
}
```

---

## Worker: Track Click Endpoint

```typescript
// workers/push-track.ts
interface Env {
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
  CLICK_QUEUE: Queue;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const { trackingId, campaignId, channel, deepLink, userId, platform } =
      await request.json<{
        trackingId: string;
        campaignId: string;
        channel: string;
        deepLink?: string;
        userId?: string;
        platform: 'ios' | 'android' | 'web';
      }>();

    // Fast path: write to Analytics Engine (non-blocking)
    env.ANALYTICS.writeDataPoint({
      blobs: [campaignId, channel, platform, userId ?? 'anon', deepLink ?? ''],
      doubles: [1, Date.now()],
      indexes: [campaignId],
    });

    // Enqueue D1 update to avoid latency on this request
    await env.CLICK_QUEUE.send({
      type: 'push_click',
      trackingId,
      campaignId,
      userId,
      platform,
      clickedAt: new Date().toISOString(),
    });

    // Return deepLink destination so the app can navigate
    return Response.json({ ok: true, deepLink: deepLink ?? null });
  },
};
```

---

## Worker: Queue Consumer (D1 Click Counter)

```typescript
// workers/push-track-consumer.ts
interface ClickMessage {
  type: 'push_click';
  trackingId: string;
  campaignId: string;
  userId?: string;
  platform: string;
  clickedAt: string;
}

export default {
  async queue(batch: MessageBatch<ClickMessage>, env: Env): Promise<void> {
    const stmt = env.DB.prepare(
      `INSERT INTO push_clicks (tracking_id, campaign_id, user_id, platform, clicked_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT (tracking_id) DO NOTHING`
    );

    const updateCampaign = env.DB.prepare(
      `UPDATE campaigns SET click_count = click_count + 1 WHERE id = ?`
    );

    const stmts = batch.messages.flatMap((msg) => [
      stmt.bind(
        msg.body.trackingId,
        msg.body.campaignId,
        msg.body.userId ?? null,
        msg.body.platform,
        msg.body.clickedAt
      ),
      updateCampaign.bind(msg.body.campaignId),
    ]);

    await env.DB.batch(stmts);
    batch.ackAll();
  },
};
```

---

## Capacitor App: Notification Click Handler

```typescript
// src/notifications/clickTracker.ts
import { PushNotifications, ActionPerformed } from '@capacitor/push-notifications';
import { App } from '@capacitor/app';
import { Router } from 'vue-router'; // or React Router / Angular Router

const WORKER_URL = 'https://your-worker.workers.dev/push-track';

export function registerClickTracking(router: Router, userId: string | null) {
  PushNotifications.addListener(
    'pushNotificationActionPerformed',
    async (action: ActionPerformed) => {
      const data = action.notification.data as {
        trackingId?: string;
        campaignId?: string;
        deepLink?: string;
        channel?: string;
      };

      if (!data.trackingId || !data.campaignId) return;

      const platform = (await App.getInfo()).id.includes('ios') ? 'ios' : 'android';

      try {
        const response = await fetch(WORKER_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          // keepalive: true ensures the beacon fires even if the page is navigating
          keepalive: true,
          body: JSON.stringify({
            trackingId: data.trackingId,
            campaignId: data.campaignId,
            channel: data.channel ?? 'unknown',
            deepLink: data.deepLink,
            userId,
            platform,
          }),
        });

        const result = await response.json<{ ok: boolean; deepLink: string | null }>();

        // Navigate to deep link if provided
        if (result.deepLink) {
          const url = new URL(result.deepLink);
          // Convert app://products/123 → /products/123
          router.push(url.pathname + url.search);
        }
      } catch (err) {
        // Tracking failure must never block navigation
        console.warn('Click tracking failed:', err);
        if (data.deepLink) {
          const url = new URL(data.deepLink);
          router.push(url.pathname + url.search);
        }
      }
    }
  );
}
```

---

## Sending Notifications with Tracking IDs (Worker Push Sender)

```typescript
// workers/push-sender.ts — called by your campaign scheduler
async function sendPushNotification(
  env: Env,
  userId: string,
  campaign: Campaign
): Promise<void> {
  const trackingId = crypto.randomUUID();

  // Store tracking metadata in D1
  await env.DB.prepare(
    `INSERT INTO push_notifications (tracking_id, campaign_id, user_id, sent_at)
     VALUES (?, ?, ?, ?)`
  ).bind(trackingId, campaign.id, userId, new Date().toISOString()).run();

  // Look up device token from KV (registered by Capacitor on app launch)
  const deviceInfo = await env.DEVICE_TOKENS.get(`token:${userId}`, 'json') as DeviceToken;
  if (!deviceInfo) return;

  const payload: NotificationPayload = {
    title: campaign.title,
    body: campaign.body,
    data: {
      trackingId,
      campaignId: campaign.id,
      deepLink: campaign.deepLink,
      channel: campaign.channel,
    },
  };

  if (deviceInfo.platform === 'ios') {
    await sendAPNS(env, deviceInfo.token, payload);
  } else {
    await sendFCM(env, deviceInfo.token, payload);
  }
}
```

---

## Capacitor App: Register Device Token with Worker

```typescript
// src/notifications/tokenRegistration.ts
import { PushNotifications } from '@capacitor/push-notifications';
import { Device } from '@capacitor/device';

const REGISTER_URL = 'https://your-worker.workers.dev/push-register';

export async function registerDeviceToken(userId: string, authToken: string) {
  await PushNotifications.requestPermissions();
  await PushNotifications.register();

  PushNotifications.addListener('registration', async ({ value: token }) => {
    const { platform } = await Device.getInfo();
    await fetch(REGISTER_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({ userId, token, platform }),
    });
  });
}
```

---

## Anti-patterns

- **Firing the click beacon from `pushNotificationReceived` instead of `pushNotificationActionPerformed`** — the received event fires on delivery (foreground only), not on user tap; this inflates click counts.
- **Blocking app navigation on the tracking fetch** — always navigate first (or in parallel) and track asynchronously; a slow Worker must not delay the user experience.
- **Storing `trackingId` only in the notification payload without a D1 record** — if the beacon fails and the user never retaps, the click is untrackable; store a `pending` row in D1 on send.
- **Using Cloudflare Analytics Engine without a `campaignId` index** — queries without an index scan the full dataset; always pass `indexes: [campaignId]`.

---

## Gotchas

- On iOS, `pushNotificationActionPerformed` fires before the app is fully active when the app was killed. Ensure your router and auth state are initialized before calling `router.push`.
- Android background click handling requires `capacitor-plugin-firebase-messaging` or the built-in plugin with a custom `FirebaseMessagingService`. The default Capacitor plugin does not intercept notification clicks in killed-state on Android 13+.
- `keepalive: true` on `fetch` is only respected in a browser/WebView context; in a native Capacitor context the TCP socket is held open by the OS, so it is a no-op but harmless.
- D1's `ON CONFLICT DO NOTHING` is essential: if the user taps the notification twice (double-tap by mistake), the second insert is silently dropped.

---

## Verification

```bash
# Create a test notification and check D1 for click record
npx wrangler d1 execute YOUR_DB --command \
  "SELECT tracking_id, clicked_at FROM push_clicks ORDER BY clicked_at DESC LIMIT 5"

# Query Analytics Engine for click counts per campaign (last 24h)
npx wrangler analytics-engine query --dataset push_clicks \
  --query "SELECT blob1 as campaign, SUM(double1) as clicks FROM push_clicks GROUP BY blob1"
```

---

## Related

- `capacitor-workers-push-notification-scheduling-d1.md`
- `mobile-push-notifications-cloudflare-queues.md`
- `expo-workers-push-notification-receipts.md`
- `mobile-push-delivery-reliability.md`
- `workers-ai-push-notification-personalization.md`

---

## Sources

- Capacitor Push Notifications plugin: https://capacitorjs.com/docs/apis/push-notifications
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- D1 Database: https://developers.cloudflare.com/d1/
- APNS HTTP/2 provider API: https://developer.apple.com/documentation/usernotifications/sending-notification-requests-to-apns
