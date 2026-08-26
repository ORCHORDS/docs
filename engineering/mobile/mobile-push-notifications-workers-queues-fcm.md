# Sending FCM Push Notifications from a Workers Queue Consumer

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to send Firebase Cloud Messaging (FCM v1 API) push notifications from a Cloudflare Workers backend at scale. Notifications are enqueued by other Workers and consumed in batches. Each device's FCM registration token is stored in a D1 table, and you need to handle per-token delivery failures gracefully without failing the entire batch.

---

## Context
The FCM v1 API (the only API Google still supports as of 2024) requires a short-lived OAuth2 access token obtained from a Google service account. Fetching this token on every message send is expensive; instead, cache it in KV with a TTL slightly shorter than the 3600-second token lifetime. A Workers Queue consumer receives batches of notification jobs, looks up each recipient's FCM token from D1, calls FCM, and marks failed tokens for removal or retry. This architecture decouples notification dispatch from the request path and provides back-pressure via the Queue.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "push-consumer"
main = "src/consumer.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "push-jobs"
batch_size = 100
batch_timeout = 5
max_retries = 3

[[d1_databases]]
binding = "DB"
database_name = "mobile-db"
database_id = "<YOUR_D1_DATABASE_ID>"

[[kv_namespaces]]
binding = "CACHE"
id = "<YOUR_KV_NAMESPACE_ID>"

# Secrets (set via wrangler secret put):
# FCM_SERVICE_ACCOUNT_JSON  — full service-account JSON as a string
# FCM_PROJECT_ID            — Firebase project ID
```

```sql
-- D1 migration: 0001_fcm_tokens.sql
CREATE TABLE IF NOT EXISTS fcm_tokens (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT    NOT NULL,
  token       TEXT    NOT NULL UNIQUE,
  platform    TEXT    NOT NULL CHECK(platform IN ('ios','android')),
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fcm_user ON fcm_tokens(user_id);
```

---

## Section 2 — Worker implementation

```typescript
// src/consumer.ts
export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  FCM_SERVICE_ACCOUNT_JSON: string;
  FCM_PROJECT_ID: string;
  pushJobs: Queue;
}

interface PushJob {
  userId: string;
  title: string;
  body: string;
  data?: Record<string, string>;
}

// ── OAuth2 token via service-account ──────────────────────────────────────
async function getFcmAccessToken(env: Env): Promise<string> {
  const cached = await env.CACHE.get('fcm:access_token');
  if (cached) return cached;

  const sa = JSON.parse(env.FCM_SERVICE_ACCOUNT_JSON);
  const now = Math.floor(Date.now() / 1000);

  // Build JWT assertion
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
    .replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const claim = btoa(JSON.stringify({
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/firebase.messaging',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
  })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');

  const signingInput = `${header}.${claim}`;

  // Import private key
  const pemBody = sa.private_key
    .replace(/<redacted-private-key>/g, '')
    .replace(/\n/g, '');
  const keyBuf = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8', keyBuf.buffer,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false, ['sign']
  );

  const sig = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    new TextEncoder().encode(signingInput)
  );
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');

  const assertion = `${signingInput}.${sigB64}`;

  // Exchange assertion for access token
  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion,
    }),
  });
  const { access_token, expires_in } = await tokenRes.json<{ access_token: string; expires_in: number }>();

  // Cache with 5-minute buffer
  await env.CACHE.put('fcm:access_token', access_token, {
    expirationTtl: expires_in - 300,
  });

  return access_token;
}

// ── single FCM send ────────────────────────────────────────────────────────
async function sendToToken(
  token: string,
  title: string,
  body: string,
  data: Record<string, string> = {},
  accessToken: string,
  projectId: string
): Promise<{ success: boolean; shouldRemove: boolean }> {
  const res = await fetch(
    `https://fcm.googleapis.com/v1/projects/${projectId}/messages:send`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: {
          token,
          notification: { title, body },
          data,
          android: { priority: 'high' },
          apns: { headers: { 'apns-priority': '10' } },
        },
      }),
    }
  );

  if (res.ok) return { success: true, shouldRemove: false };

  const err = await res.json<{ error?: { status?: string } }>();
  const unrecoverable = ['REGISTRATION_TOKEN_NOT_VALID', 'UNREGISTERED'];
  const shouldRemove = unrecoverable.includes(err?.error?.status ?? '');
  return { success: false, shouldRemove };
}

// ── queue consumer ─────────────────────────────────────────────────────────
export default {
  async queue(batch: MessageBatch<PushJob>, env: Env): Promise<void> {
    const accessToken = await getFcmAccessToken(env);
    const staleTokens: string[] = [];

    for (const msg of batch.messages) {
      const { userId, title, body, data = {} } = msg.body;

      const rows = await env.DB.prepare(
        'SELECT token FROM fcm_tokens WHERE user_id = ?'
      ).bind(userId).all<{ token: string }>();

      const results = await Promise.allSettled(
        rows.results.map((r) =>
          sendToToken(r.token, title, body, data, accessToken, env.FCM_PROJECT_ID)
            .then((result) => ({ token: r.token, ...result }))
        )
      );

      for (const r of results) {
        if (r.status === 'fulfilled' && r.value.shouldRemove) {
          staleTokens.push(r.value.token);
        }
      }

      msg.ack();
    }

    // Bulk-delete stale tokens
    if (staleTokens.length > 0) {
      const placeholders = staleTokens.map(() => '?').join(',');
      await env.DB.prepare(
        `DELETE FROM fcm_tokens WHERE token IN (${placeholders})`
      ).bind(...staleTokens).run();
    }
  },
};
```

---

## Section 3 — Client-side (React Native / Expo)

```typescript
// lib/registerPushToken.ts
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import { apiFetch } from './apiClient'; // from react-native-expo-cloudflare-workers-api

export async function registerPushToken(): Promise<void> {
  if (!Device.isDevice) {
    console.warn('Push notifications only work on physical devices.');
    return;
  }

  const { status: existing } = await Notifications.getPermissionsAsync();
  let finalStatus = existing;
  if (existing !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== 'granted') return;

  // Expo push token wraps FCM / APNs; extract the raw device token for direct FCM
  const expoPushToken = (await Notifications.getExpoPushTokenAsync()).data;
  const deviceToken = (await Notifications.getDevicePushTokenAsync()).data as string;

  const platform = Platform.OS === 'ios' ? 'ios' : 'android';

  await apiFetch('/push/register', {
    method: 'POST',
    body: JSON.stringify({ token: deviceToken, platform }),
  });
}

// Worker endpoint to upsert the token:
// POST /push/register  { token: string, platform: 'ios'|'android' }
// INSERT OR REPLACE INTO fcm_tokens (user_id, token, platform, updated_at)
// VALUES (?, ?, ?, datetime('now'))
```

---

## Anti-patterns
- **Fetching the OAuth2 token per message** — one token per batch is enough; fetching per message exhausts the Google token endpoint rate limit and adds hundreds of milliseconds of latency per notification.
- **Ignoring `UNREGISTERED` errors** — stale tokens accumulate in D1 and waste FCM quota; always delete them promptly.
- **Using the legacy FCM HTTP v1 keys** — the server-key based API was deprecated in June 2024 and will be removed; use OAuth2 service account tokens.
- **Blocking the queue consumer on D1 writes** — ack messages before bulk-deleting stale tokens so the queue is not held waiting on cleanup.

---

## Gotchas
- `crypto.subtle.importKey` with `pkcs8` requires the `Workers Unbound` or `Standard` plan; it is available in the free tier as of compatibility date 2023-01-01.
- The FCM v1 endpoint path includes the Firebase project ID — double-check it matches the project tied to the service account.
- Expo's `getDevicePushTokenAsync()` returns the raw APNs device token on iOS, not the FCM token. If your backend calls FCM directly, you must use this raw token (not the Expo push token).
- Queue consumer `max_retries` retries the entire batch on unhandled exceptions; ack individual messages inside the loop to avoid duplicate sends.

---

## Verification
```bash
# Apply D1 migration
npx wrangler d1 execute mobile-db --file=0001_fcm_tokens.sql

# Deploy consumer
npx wrangler deploy

# Enqueue a test notification via a producer Worker or wrangler CLI
npx wrangler queues send push-jobs \
  --message '{"userId":"user:test@example.com","title":"Hello","body":"World"}'

# Check D1 for tokens
npx wrangler d1 execute mobile-db \
  --command 'SELECT * FROM fcm_tokens LIMIT 10;'
```

---

## Related
- `react-native-expo-cloudflare-workers-api.md`
- `offline-first-sync-workers-d1-mobile.md`

---

## Sources
- FCM v1 API — https://firebase.google.com/docs/reference/fcm/rest/v1/projects.messages/send
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Expo Notifications — https://docs.expo.dev/versions/latest/sdk/notifications/
