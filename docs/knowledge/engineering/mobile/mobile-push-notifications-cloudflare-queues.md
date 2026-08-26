# Mobile Push Notifications via Cloudflare Queues

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project social events (likes, comments, follows) trigger
push notifications. Sending pushes synchronously inside a
Cloudflare Worker that also handles the event write causes
timeout errors (524) when APNS or FCM are slow to respond.
Bulk social events (a post going viral) cause thousands of
concurrent pushes that saturate the Worker's outbound
fetch limit. Android users receive pushes 10–30 s after
iOS users. Delivery failures (expired tokens, uninstalled
apps) are not tracked, so the device token table grows
stale indefinitely.

## Context

Cloudflare Queues provides a managed message queue that
decouples event producers (Workers that handle API
requests) from event consumers (Workers that deliver
pushes). Producers enqueue a notification job and return
immediately; a separate consumer Worker drains the queue
and contacts APNS (iOS) or FCM (Android) in parallel
batches. Delivery receipts (success, permanent failure,
token expiry) are written to a D1 table for audit and
token cleanup. For iOS specifics see
`ios-push-notifications-apns-workers.md`.

---

## 1. Architecture Overview

```
 Mobile Client                   Cloudflare Edge
 ┌──────────┐    POST /event     ┌─────────────────────┐
 │  example project │ ─────────────────► │  Producer Worker    │
 │   App    │                   │  (handles API req)  │
 └──────────┘                   │                     │
                                │  1. Write to D1     │
                                │  2. Enqueue job →───┤
                                └────────────┬────────┘
                                             │
                                    Cloudflare Queue
                                    "push-notifications"
                                             │
                                    ┌────────▼────────┐
                                    │ Consumer Worker  │
                                    │ (push delivery) │
                                    └───┬─────────┬───┘
                                        │         │
                              ┌─────────▼─┐  ┌────▼──────────┐
                              │  APNS     │  │  FCM (Android)│
                              │  (iOS)    │  │               │
                              └─────────┬─┘  └────┬──────────┘
                                        │         │
                              ┌─────────▼─────────▼──────────┐
                              │   D1: push_receipts table    │
                              └──────────────────────────────┘
```

---

## 2. Queue Setup

```toml
# wrangler.toml (producer and consumer share the same queue)

[[queues.producers]]
queue   = "push-notifications"
binding = "PUSH_QUEUE"

[[queues.consumers]]
queue             = "push-notifications"
max_batch_size    = 100
max_batch_timeout = 5        # seconds to wait for a full batch
max_retries       = 3
dead_letter_queue = "push-notifications-dlq"
```

The consumer receives batches of up to 100 messages every
5 seconds (or when 100 messages accumulate). Set
`max_batch_size` to 100 to align with FCM's batch send
limit (500 max; 100 is safer for per-consumer CPU budgets).

---

## 3. Producer: Enqueue Push Job

```ts
// workers/src/events/socialEvent.ts
import { Env } from '../types';

interface PushJob {
  recipientUserId: string;
  platform:        'ios' | 'android';
  deviceToken:     string;
  title:           string;
  body:            string;
  data?:           Record<string, string>;
  collapseKey?:    string;
  idempotencyKey:  string;
}

export async function enqueuePush(
  env: Env,
  job: PushJob
): Promise<void> {
  await env.PUSH_QUEUE.send(job, {
    contentType: 'json',
    // Delay delivery by 0–2 s to batch concurrent events
    delaySeconds: Math.floor(Math.random() * 2),
  });
}

// Usage in a social event handler:
export async function handleLike(
  req: Request,
  env: Env
): Promise<Response> {
  const { postId, likerId } = await req.json<{
    postId:  string;
    likerId: string;
  }>();

  // Write the like to D1
  await env.DB.prepare(
    'INSERT INTO likes (post_id, user_id, created_at)' +
    ' VALUES (?, ?, ?)'
  ).bind(postId, likerId, Date.now()).run();

  // Look up post author device info
  const device = await env.DB.prepare(
    'SELECT device_token, platform FROM devices' +
    ' WHERE user_id = (SELECT user_id FROM posts' +
    '   WHERE id = ?) LIMIT 1'
  ).bind(postId).first<{
    device_token: string;
    platform: 'ios' | 'android';
  }>();

  if (device) {
    await enqueuePush(env, {
      recipientUserId: postId,   // resolved upstream
      platform:        device.platform,
      deviceToken:     device.device_token,
      title:           'New like',
      body:            'Someone liked your post',
      collapseKey:     `likes:${postId}`,
      idempotencyKey:  `like:${postId}:${likerId}`,
    });
  }

  return Response.json({ ok: true });
}
```

---

## 4. Consumer: Fan-out Delivery Worker

```ts
// workers/src/push-consumer.ts
import { MessageBatch, Message } from '@cloudflare/workers-types';
import { Env } from './types';
import { sendApns }
  from './apns';                  // see ios-push-notifications-apns-workers.md
import { sendFcm }
  from './fcm';

export default {
  async queue(
    batch: MessageBatch<PushJob>,
    env:   Env
  ): Promise<void> {
    const ios     = batch.messages.filter(
      m => m.body.platform === 'ios'
    );
    const android = batch.messages.filter(
      m => m.body.platform === 'android'
    );

    // Deliver in parallel; collect results
    const [iosResults, androidResults] = await Promise.all([
      deliverIos(ios, env),
      deliverAndroid(android, env),
    ]);

    // Write receipts to D1
    await writeReceipts(
      [...iosResults, ...androidResults], env
    );

    // Ack successful messages; retry failures
    for (const { msg, success } of [
      ...iosResults, ...androidResults
    ]) {
      if (success) {
        msg.ack();
      } else {
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

type Result = {
  msg:          Message<PushJob>;
  success:      boolean;
  errorReason?: string;
  tokenInvalid?: boolean;
};

async function deliverIos(
  messages: Message<PushJob>[],
  env: Env
): Promise<Result[]> {
  return Promise.all(messages.map(async (msg) => {
    try {
      await sendApns(msg.body.deviceToken, {
        alert: {
          title: msg.body.title,
          body:  msg.body.body,
        },
        sound: 'default',
      }, env, {
        collapseId: msg.body.collapseKey,
        priority:   10,
      });
      return { msg, success: true };
    } catch (err: unknown) {
      const e = err as Error;
      const tokenInvalid =
        e.message?.startsWith('APNS_UNREGISTERED');
      return {
        msg,
        success:      false,
        errorReason:  e.message,
        tokenInvalid,
      };
    }
  }));
}

async function deliverAndroid(
  messages: Message<PushJob>[],
  env: Env
): Promise<Result[]> {
  if (!messages.length) return [];
  // FCM V1 API: batch up to 500 messages per request
  return sendFcmBatch(messages, env);
}
```

---

## 5. FCM V1 Android Delivery

```ts
// workers/src/fcm.ts

const FCM_ENDPOINT =
  'https://fcm.googleapis.com/v1/projects/' +
  '{PROJECT_ID}/messages:send';

export async function sendFcm(
  deviceToken: string,
  title:       string,
  body:        string,
  data?:       Record<string, string>,
  env?:        { FCM_PROJECT_ID: string;
                 FCM_SERVICE_ACCOUNT: string }
): Promise<void> {
  const accessToken = await getFcmAccessToken(env!);

  const res = await fetch(
    FCM_ENDPOINT.replace('{PROJECT_ID}',
      env!.FCM_PROJECT_ID),
    {
      method: 'POST',
      headers: {
        'authorization': `Bearer ${accessToken}`,
        'content-type':  'application/json',
      },
      body: JSON.stringify({
        message: {
          token:        deviceToken,
          notification: { title, body },
          data:         data ?? {},
          android: {
            priority: 'HIGH',
            notification: { sound: 'default' },
          },
        },
      }),
    }
  );

  if (!res.ok) {
    const err = await res.json<{
      error: { status: string; message: string }
    }>();
    const st = err.error?.status;
    if (st === 'UNREGISTERED' || st === 'INVALID_ARGUMENT') {
      throw new Error(`FCM_UNREGISTERED:${deviceToken}`);
    }
    throw new Error(
      `FCM error ${res.status}: ${err.error?.message}`
    );
  }
}
```

---

## 6. Delivery Receipt Tracking in D1

```sql
-- D1 migration: 0009_push_receipts.sql
CREATE TABLE IF NOT EXISTS push_receipts (
  id              TEXT PRIMARY KEY,  -- idempotencyKey
  user_id         TEXT NOT NULL,
  device_token    TEXT NOT NULL,
  platform        TEXT NOT NULL,
  delivered_at    INTEGER,
  failed_at       INTEGER,
  error_reason    TEXT,
  token_invalid   INTEGER DEFAULT 0,  -- 1 = revoke token
  retry_count     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS
  idx_receipts_user ON push_receipts (user_id, delivered_at);
CREATE INDEX IF NOT EXISTS
  idx_receipts_invalid
    ON push_receipts (token_invalid)
    WHERE token_invalid = 1;
```

Run a nightly D1 cleanup Worker to remove invalid tokens:

```ts
// workers/src/cron/cleanTokens.ts
export async function cleanInvalidTokens(
  env: Env
): Promise<void> {
  await env.DB.prepare(
    'DELETE FROM devices WHERE device_token IN (' +
    '  SELECT device_token FROM push_receipts' +
    '  WHERE token_invalid = 1' +
    ')'
  ).run();

  await env.DB.prepare(
    'DELETE FROM push_receipts WHERE token_invalid = 1'
  ).run();
}
```

---

## Anti-patterns

- Sending pushes synchronously inside the event handler
  Worker. A slow APNS/FCM response causes the Worker to
  hit its CPU limit and return a 524 to the client.
- Retrying the same device token after receiving an
  UNREGISTERED (APNS 410, FCM UNREGISTERED) response.
  These tokens are permanently invalid; retrying wastes
  queue throughput and can trigger rate limiting.
- Using a single Cloudflare Queue with `max_batch_size = 1`
  for push notifications. This creates one Worker invocation
  per push and burns through your Workers request quota.
- Logging device tokens in plaintext in Worker logs. Device
  tokens are sensitive; hash or truncate before logging.

## Gotchas

- Cloudflare Queues guarantee at-least-once delivery. The
  consumer must be idempotent. Use `idempotencyKey` to
  deduplicate pushes in the receipt table before sending.
- FCM HTTP v1 (OAuth 2.0) replaced the legacy FCM API
  (Server Key) in June 2024. The legacy key no longer
  works; all Workers must use the v1 endpoint with a
  service account access token.
- APNS on Cloudflare Workers uses HTTP/1.1 internally
  (Workers runtime handles the HTTP/2 upgrade at the edge,
  but the underlying `fetch` call from a Worker to an
  external host behaves as HTTP/1.1). APNS still accepts
  this. See `ios-push-notifications-apns-workers.md`.
- The dead-letter queue (`push-notifications-dlq`) must
  have a separate consumer or be drained manually. Messages
  that exhaust `max_retries` accumulate silently otherwise.

## Verification

```bash
# Confirm queue is draining
wrangler queues list

# Monitor consumer Worker logs
wrangler tail push-consumer --format=pretty

# Check D1 receipt table after a test push event
wrangler d1 execute example project-db --command \
  "SELECT platform, COUNT(*) as n,
          SUM(token_invalid) as invalid
   FROM push_receipts
   GROUP BY platform"
```

## Related

- `ios-push-notifications-apns-workers.md`
- `android-firebase-messaging.md`
- `react-native-push-notifications.md`
- `mobile-push-delivery-reliability.md`
- `mobile-network-resilience-cloudflare-workers.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/configuration/
- https://firebase.google.com/docs/cloud-messaging/send-message
- https://developer.apple.com/documentation/usernotifications/sending-notification-requests-to-apns
- https://developers.cloudflare.com/d1/
