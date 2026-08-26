# Push Notifications via FCM and APNs from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to send push notifications from Cloudflare Workers to both Android (via Firebase Cloud Messaging v1 API) and iOS (via APNs HTTP/2 with JWT auth). Your app registers device tokens on the server; you need bulk fan-out, reliable delivery status tracking, and automatic token cleanup when devices unregister.

## Context

FCM v1 API requires OAuth2 Bearer tokens generated from a Google service account key. APNs HTTP/2 requires a p8 JWT (ES256, signed with the key from Apple Developer). Workers cannot open persistent HTTP/2 connections — `fetch` is used per request, but Cloudflare's runtime negotiates HTTP/2 to APNs transparently.

For bulk sends, use Cloudflare Queues to fan-out to individual device tokens rather than looping synchronously in `fetch()`. D1 stores device tokens keyed by user ID and platform. When FCM returns 404 or APNs returns 410, the token is permanently invalid and must be purged from D1.

## Solution

```typescript
// wrangler.toml
// [[d1_databases]]
// binding = "DB"
// database_name = "notifications"
//
// [[queues.producers]]
// binding = "NOTIFICATION_QUEUE"
// queue = "push-notifications"
//
// [[queues.consumers]]
// queue = "push-notifications"
// max_batch_size = 50
// max_retries = 3

export interface Env {
  DB: D1Database;
  NOTIFICATION_QUEUE: Queue;
  FCM_SERVICE_ACCOUNT: string;  // JSON string of GCP service account
  APNS_KEY_ID: string;
  APNS_TEAM_ID: string;
  APNS_PRIVATE_KEY: string;     // PEM p8 key
  APNS_BUNDLE_ID: string;
}

interface DeviceToken {
  id: string;
  user_id: string;
  platform: 'android' | 'ios';
  token: string;
  created_at: string;
}

interface PushPayload {
  title: string;
  body: string;
  data?: Record<string, string>;
  badge?: number;
  sound?: string;
}

interface QueueMessage {
  token: DeviceToken;
  payload: PushPayload;
  notification_id: string;
}

// --- OAuth2 JWT for FCM v1 ---

async function getFCMAccessToken(serviceAccountJson: string): Promise<string> {
  const sa = JSON.parse(serviceAccountJson);
  const now = Math.floor(Date.now() / 1000);

  const header = { alg: 'RS256', typ: 'JWT' };
  const claim = {
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/firebase.messaging',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
  };

  const encode = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  const unsigned = `${encode(header)}.${encode(claim)}`;

  const keyData = sa.private_key
    .replace(/<redacted-private-key>/, '')
    .replace(/\n/g, '');

  const binaryKey = Uint8Array.from(atob(keyData), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8',
    binaryKey,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign'],
  );

  const signature = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    new TextEncoder().encode(unsigned),
  );

  const sig = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  const jwt = `${unsigned}.${sig}`;

  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt,
    }),
  });

  const tokenData = await tokenRes.json<{ access_token: string }>();
  return tokenData.access_token;
}

// --- APNs JWT (ES256) ---

async function getAPNsJWT(keyId: string, teamId: string, pemKey: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: 'ES256', kid: keyId };
  const payload = { iss: teamId, iat: now };

  const encode = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  const unsigned = `${encode(header)}.${encode(payload)}`;

  const keyData = pemKey
    .replace(/<redacted-private-key>/, '')
    .replace(/\n/g, '');

  const binaryKey = Uint8Array.from(atob(keyData), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8',
    binaryKey,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign'],
  );

  const signature = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    cryptoKey,
    new TextEncoder().encode(unsigned),
  );

  const sig = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  return `${unsigned}.${sig}`;
}

// --- FCM v1 send ---

async function sendFCM(
  token: string,
  payload: PushPayload,
  projectId: string,
  accessToken: string,
): Promise<{ success: boolean; stale: boolean }> {
  const message = {
    message: {
      token,
      notification: { title: payload.title, body: payload.body },
      android: {
        notification: { sound: payload.sound ?? 'default' },
      },
      data: payload.data ?? {},
    },
  };

  const res = await fetch(
    `https://fcm.googleapis.com/v1/projects/${projectId}/messages:send`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(message),
    },
  );

  if (res.status === 200) return { success: true, stale: false };
  if (res.status === 404) return { success: false, stale: true };  // token not found
  return { success: false, stale: false };
}

// --- APNs HTTP/2 send ---

async function sendAPNs(
  deviceToken: string,
  payload: PushPayload,
  bundleId: string,
  jwt: string,
): Promise<{ success: boolean; stale: boolean }> {
  const body = {
    aps: {
      alert: { title: payload.title, body: payload.body },
      badge: payload.badge ?? 1,
      sound: payload.sound ?? 'default',
    },
    ...payload.data,
  };

  const res = await fetch(`https://api.push.apple.com/3/device/${deviceToken}`, {
    method: 'POST',
    headers: {
      Authorization: `bearer ${jwt}`,
      'apns-topic': bundleId,
      'apns-push-type': 'alert',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (res.status === 200) return { success: true, stale: false };
  if (res.status === 410) return { success: false, stale: true };  // device unregistered
  return { success: false, stale: false };
}

// --- HTTP handler: enqueue notification for a user ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/tokens') {
      const { user_id, platform, token } = await request.json<{
        user_id: string;
        platform: 'android' | 'ios';
        token: string;
      }>();
      const id = crypto.randomUUID();
      await env.DB.prepare(
        'INSERT INTO device_tokens (id, user_id, platform, token, created_at) VALUES (?, ?, ?, ?, ?)'
        + ' ON CONFLICT(token) DO UPDATE SET user_id = excluded.user_id',
      ).bind(id, user_id, platform, token, new Date().toISOString()).run();
      return Response.json({ id }, { status: 201 });
    }

    if (request.method === 'POST' && url.pathname === '/notify/user') {
      const { user_id, payload } = await request.json<{
        user_id: string;
        payload: PushPayload;
      }>();

      const tokens = await env.DB.prepare(
        'SELECT * FROM device_tokens WHERE user_id = ?',
      ).bind(user_id).all<DeviceToken>();

      const notification_id = crypto.randomUUID();

      await env.DB.prepare(
        'INSERT INTO notification_log (id, user_id, title, status, created_at) VALUES (?, ?, ?, ?, ?)',
      ).bind(notification_id, user_id, payload.title, 'queued', new Date().toISOString()).run();

      await env.NOTIFICATION_QUEUE.sendBatch(
        tokens.results.map((token) => ({
          body: { token, payload, notification_id } satisfies QueueMessage,
        })),
      );

      return Response.json({ notification_id, queued: tokens.results.length });
    }

    return new Response('Not found', { status: 404 });
  },

  // --- Queue consumer: deliver each message to its platform ---

  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    const sa = JSON.parse(env.FCM_SERVICE_ACCOUNT);

    // Fetch auth tokens once for the whole batch
    const [fcmToken, apnsJWT] = await Promise.all([
      getFCMAccessToken(env.FCM_SERVICE_ACCOUNT),
      getAPNsJWT(env.APNS_KEY_ID, env.APNS_TEAM_ID, env.APNS_PRIVATE_KEY),
    ]);

    for (const msg of batch.messages) {
      const { token, payload } = msg.body;
      let result: { success: boolean; stale: boolean };

      if (token.platform === 'android') {
        result = await sendFCM(token.token, payload, sa.project_id, fcmToken);
      } else {
        result = await sendAPNs(token.token, payload, env.APNS_BUNDLE_ID, apnsJWT);
      }

      if (result.stale) {
        // Purge dead token from D1; no retry needed
        await env.DB.prepare('DELETE FROM device_tokens WHERE id = ?')
          .bind(token.id).run();
        msg.ack();
      } else if (result.success) {
        msg.ack();
      } else {
        // Transient failure — let Queues retry up to max_retries
        msg.retry();
      }
    }
  },
};
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE device_tokens (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id    TEXT NOT NULL,
  platform   TEXT NOT NULL CHECK (platform IN ('android', 'ios')),
  token      TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_device_tokens_user ON device_tokens (user_id);

CREATE TABLE notification_log (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  title      TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'queued',
  created_at TEXT NOT NULL
);
```

**FCM v1 vs legacy:** The v1 API uses short-lived OAuth2 Bearer tokens scoped to `firebase.messaging`. The legacy server-key API (`Authorization: key=…`) was deprecated in June 2024. All new integrations must use v1.

**APNs sandbox vs production:** For development builds use `api.sandbox.push.apple.com`. Gate via an env var (`APNS_SANDBOX=true`) to keep the same Worker code path for both.

**Idempotency on Queue retry:** If a Worker crashes mid-batch, some messages may be redelivered. Add a `delivered_ids` KV set keyed by `notification_id + token.id`, checked before dispatching, to avoid duplicate notifications on retry.

**APNs JWT expiry:** The APNs JWT is valid for 1 hour. For a Queue consumer processing thousands of tokens, regenerate the JWT every 45 minutes using a counter on `msg.attempts` or by tracking `iat` in a local variable.

## Anti-patterns

- Looping over all device tokens synchronously inside `fetch()` — this will hit the 30-second CPU limit for users with many devices; always enqueue first.
- Caching FCM access tokens in `globalThis` — Worker isolates are short-lived and spawned on demand; use KV with a TTL of 3500 seconds instead.
- Not differentiating 404 (FCM) from 410 (APNs) — both mean the token is dead, but the HTTP status codes differ by platform.
- Sending APNs without `apns-push-type` header — required since iOS 13; omitting it causes silent delivery failure on watchOS and some iOS versions.

## Gotchas

- `crypto.subtle.importKey` for ECDSA requires `pkcs8` format. Apple p8 keys are PKCS#8 by default — no conversion needed.
- APNs returns an empty 200 body on success. Do not attempt `await res.json()` on a 200 APNs response; it will throw.
- FCM v1 returns `{ name: "projects/{id}/messages/{msg_id}" }` on success. Parse this to extract the server-assigned message ID for delivery tracking.
- The Queues `max_batch_size` of 50 means auth tokens fetched at the start of `queue()` are reused for at most 50 sends. This is well within the 1-hour JWT lifetime.

## Verification

```bash
# Register a device token
curl -s -X POST https://your-worker.workers.dev/tokens \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","platform":"android","token":"fcm-device-token-abc"}'

# Send a notification (enqueues to Queue)
curl -s -X POST https://your-worker.workers.dev/notify/user \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","payload":{"title":"Hello","body":"World"}}'
# → {"notification_id":"...","queued":1}

# Tail the Worker to watch Queue consumer logs
wrangler tail --format pretty
```

## Related

- `workers-queues-fan-out.md` — general fan-out pattern with Cloudflare Queues
- `workers-d1-schema-migrations.md` — managing D1 schema changes in CI/CD

## Sources

- [FCM HTTP v1 API reference](https://firebase.google.com/docs/reference/fcm/rest/v1/projects.messages/send)
- [Sending notification requests to APNs](https://developer.apple.com/documentation/usernotifications/sending-notification-requests-to-apns)
- [Cloudflare Queues — batch consumers](https://developers.cloudflare.com/queues/reference/batching-retries/)
- [Web Crypto: RSASSA-PKCS1-v1_5 and ECDSA](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign)
