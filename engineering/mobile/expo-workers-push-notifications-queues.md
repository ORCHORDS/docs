# Expo Push Notifications via Cloudflare Workers Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A backend event (new message, order update, payment confirmation) needs to trigger a push notification to one or many Expo-registered devices. Direct synchronous calls to the Expo Push API from a Workers handler block the request and risk timeouts when thousands of tokens must be notified. Delivery failures are silently dropped and stale device tokens accumulate in the database.

---

## Context
Cloudflare Queues decouples the event producer from the Expo Push API consumer: the Workers handler enqueues a lightweight message in under 1 ms and returns immediately to the caller. A separate Queue consumer Worker batches up to 100 tokens per `sendPushNotificationsAsync` call — the maximum Expo's API accepts in a single request. A D1 table records each notification's delivery status and surfaces `DeviceNotRegistered` errors so stale tokens can be pruned automatically. Exponential backoff in the consumer prevents hammering the Expo API during a transient outage.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "push-notification-worker"
compatibility_date = "2025-06-01"

[[queues.producers]]
binding = "PUSH_QUEUE"
queue = "expo-push-queue"

[[queues.consumers]]
queue = "expo-push-queue"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "expo-push-dlq"

[[d1_databases]]
binding = "DB"
database_name = "notifications"
database_id = "<YOUR_D1_DATABASE_ID>"
```

```bash
# Create the D1 table
npx wrangler d1 execute notifications --command "
CREATE TABLE IF NOT EXISTS push_notifications (
  id          TEXT PRIMARY KEY,
  expo_token  TEXT NOT NULL,
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  data        TEXT,
  status      TEXT NOT NULL DEFAULT 'queued',
  receipt_id  TEXT,
  error       TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pn_status ON push_notifications(status);
CREATE INDEX IF NOT EXISTS idx_pn_token  ON push_notifications(expo_token);
"
```

---

## Section 2 — Implementation

```typescript
// src/push-worker.ts
import { Expo, ExpoPushMessage, ExpoPushTicket } from 'expo-server-sdk';

export interface Env {
  PUSH_QUEUE: Queue;
  DB: D1Database;
}

export type PushPayload = {
  id: string;
  expoPushToken: string;
  title: string;
  body: string;
  data?: Record<string, unknown>;
};

// ---------- Producer: enqueue from any Worker route ----------
export async function enqueuePush(
  env: Env,
  payload: Omit<PushPayload, 'id'>,
): Promise<string> {
  const id = crypto.randomUUID();
  const now = Date.now();

  await env.DB.prepare(
    `INSERT INTO push_notifications (id, expo_token, title, body, data, status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)`,
  )
    .bind(id, payload.expoPushToken, payload.title, payload.body,
          payload.data ? JSON.stringify(payload.data) : null, now, now)
    .run();

  await env.PUSH_QUEUE.send({ ...payload, id });
  return id;
}

// ---------- Consumer: process batches ----------
const expo = new Expo({ useFcmV1: true });

async function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

export default {
  // HTTP handler (producer side)
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await req.json<Omit<PushPayload, 'id'>>();
    if (!Expo.isExpoPushToken(body.expoPushToken)) {
      return Response.json({ error: 'Invalid Expo push token' }, { status: 400 });
    }

    const id = await enqueuePush(env, body);
    return Response.json({ queued: true, id }, { status: 202 });
  },

  // Queue consumer
  async queue(batch: MessageBatch<PushPayload>, env: Env): Promise<void> {
    const messages = batch.messages.map(m => m.body);

    // Filter valid Expo tokens
    const valid = messages.filter(m => Expo.isExpoPushToken(m.expoPushToken));

    const pushMessages: ExpoPushMessage[] = valid.map(m => ({
      to: m.expoPushToken,
      sound: 'default',
      title: m.title,
      body: m.body,
      data: m.data ?? {},
    }));

    // Expo SDK chunks automatically; we handle tickets manually for D1 tracking
    const chunks = expo.chunkPushNotifications(pushMessages);
    const allTickets: ExpoPushTicket[] = [];

    for (const chunk of chunks) {
      let attempt = 0;
      const MAX = 5;
      while (attempt < MAX) {
        try {
          const tickets = await expo.sendPushNotificationsAsync(chunk);
          allTickets.push(...tickets);
          break;
        } catch (err) {
          attempt++;
          if (attempt === MAX) throw err;
          await sleep(Math.pow(2, attempt) * 500); // 1s, 2s, 4s, 8s
        }
      }
    }

    // Persist ticket results
    const now = Date.now();
    for (let i = 0; i < valid.length; i++) {
      const ticket = allTickets[i];
      const notif = valid[i];

      if (!ticket) continue;

      if (ticket.status === 'ok') {
        await env.DB.prepare(
          `UPDATE push_notifications SET status='sent', receipt_id=?, updated_at=? WHERE id=?`,
        ).bind(ticket.id, now, notif.id).run();
      } else {
        const details = (ticket as any).details;
        const error = details?.error ?? 'unknown';

        // Auto-remove stale tokens
        if (error === 'DeviceNotRegistered') {
          await env.DB.prepare(
            `UPDATE push_notifications SET status='invalid_token', error=?, updated_at=? WHERE id=?`,
          ).bind(error, now, notif.id).run();
          // Mark token for pruning — downstream job reads this index
          await env.DB.prepare(
            `UPDATE push_notifications SET status='pruned' WHERE expo_token=? AND status='invalid_token'`,
          ).bind(notif.expoPushToken).run();
        } else {
          await env.DB.prepare(
            `UPDATE push_notifications SET status='failed', error=?, updated_at=? WHERE id=?`,
          ).bind(error, now, notif.id).run();
          // Rethrow so the Queue retries the message
          throw new Error(`Expo push error for ${notif.id}: ${error}`);
        }
      }
    }
  },
};
```

---

## Section 3 — Integration / Testing

```typescript
// test/push-worker.test.ts  (Vitest + Miniflare)
import { describe, it, expect, vi, beforeEach } from 'vitest';
import worker, { PushPayload } from '../src/push-worker';

const mockSend = vi.fn().mockResolvedValue(undefined);
const mockD1 = {
  prepare: vi.fn().mockReturnThis(),
  bind: vi.fn().mockReturnThis(),
  run: vi.fn().mockResolvedValue({}),
};

const env = {
  PUSH_QUEUE: { send: mockSend },
  DB: mockD1,
} as any;

describe('POST /  (enqueue)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns 202 for a valid Expo token', async () => {
    const req = new Request('http://localhost', {
      method: 'POST',
      body: JSON.stringify({
        expoPushToken: 'ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]',
        title: 'Hello',
        body: 'World',
      }),
    });
    const res = await worker.fetch(req, env, {} as any);
    expect(res.status).toBe(202);
    expect(mockSend).toHaveBeenCalledOnce();
  });

  it('returns 400 for an invalid token', async () => {
    const req = new Request('http://localhost', {
      method: 'POST',
      body: JSON.stringify({ expoPushToken: 'bad', title: 'x', body: 'y' }),
    });
    const res = await worker.fetch(req, env, {} as any);
    expect(res.status).toBe(400);
  });
});
```

```bash
# Deploy consumer + producer
npx wrangler deploy

# Tail consumer logs
npx wrangler tail push-notification-worker --format=pretty

# Inspect DLQ
npx wrangler queues messages expo-push-dlq
```

---

## Anti-patterns
- **Calling `sendPushNotificationsAsync` synchronously inside a `fetch` handler** — exceeds the 30-second CPU limit under load and blocks the caller.
- **Never pruning `DeviceNotRegistered` tokens** — wastes queue capacity and inflates D1 row counts.
- **Sending all receipts in a single `getReceiptsAsync` call** — Expo receipt IDs must be polled 15-30 minutes later; a separate scheduled Worker should handle this.

---

## Gotchas
- `max_batch_size = 100` matches Expo's chunk limit exactly; setting it higher causes the SDK to chunk internally but does not improve throughput.
- Queue retries re-deliver the entire batch on failure — make the consumer idempotent by checking `status != 'sent'` before updating D1.
- Expo tokens from `expo-notifications` are prefixed `ExponentPushToken[...]`; FCM/APNS raw tokens are not valid here.

---

## Verification

```bash
# Trigger a test notification
curl -X POST https://push-notification-worker.example.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"expoPushToken":"ExponentPushToken[xxx]","title":"Test","body":"Hello"}'

# Check D1 delivery status
npx wrangler d1 execute notifications \
  --command "SELECT status, COUNT(*) FROM push_notifications GROUP BY status"
```

---

## Related
- `react-native-cloudflare-workers-api-client.md`
- `workers-mobile-offline-sync-d1.md`

---

## Sources
- Expo Push Notifications API — https://docs.expo.dev/push-notifications/sending-notifications/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- expo-server-sdk — https://github.com/expo/expo-server-sdk-node
