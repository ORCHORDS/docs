# Web Push Notifications via Cloudflare Workers (VAPID)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to send browser push notifications from a Workers-based backend
without running a dedicated Node server. The entire push pipeline — VAPID key
creation, subscription storage, payload encryption, and dispatch — lives in
Workers + D1.

## Context

- **VAPID** (Voluntary Application Server Identification) identifies your server
  to push services; keys are EC P-256, generated once and stored as secrets
- **D1** stores `PushSubscription` objects serialised as JSON
- Workers' **Web Crypto API** (`crypto.subtle`) handles ECDH + AES-GCM
  encryption without Node's `crypto` module
- The `web-push` npm package targets Node; we use a lightweight
  Workers-compatible alternative (`web-push-webcrypto`) or implement the
  RFC 8291 encryption manually

---

## 1 — Generate VAPID keys (one-time, local)

```bash
# Requires Node locally — keys are then stored as Wrangler secrets
npx web-push generate-vapid-keys --json
# Output:
# {
#   "publicKey":  "BEL...",
#   "privateKey": "abc..."
# }

npx wrangler secret put VAPID_PUBLIC_KEY
npx wrangler secret put VAPID_PRIVATE_KEY
npx wrangler secret put VAPID_SUBJECT   # e.g. mailto:ops@example.com
```

## 2 — D1 schema

```sql
-- migrations/0001_push_subscriptions.sql
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id     TEXT NOT NULL,
  endpoint    TEXT NOT NULL UNIQUE,
  p256dh      TEXT NOT NULL,   -- base64url-encoded client public key
  auth        TEXT NOT NULL,   -- base64url-encoded 16-byte auth secret
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_push_user ON push_subscriptions(user_id);
```

```bash
npx wrangler d1 execute MY_DB --file=migrations/0001_push_subscriptions.sql
```

## 3 — Worker: subscribe endpoint

```typescript
// src/worker/push/subscribe.ts
import type { Env } from '../types.js';

export async function handleSubscribe(
  request: Request,
  env: Env,
  userId: string
): Promise<Response> {
  const body = await request.json<{
    endpoint: string;
    keys: { p256dh: string; auth: string };
  }>();

  if (!body.endpoint || !body.keys?.p256dh || !body.keys?.auth) {
    return new Response('Invalid subscription object', { status: 400 });
  }

  await env.DB.prepare(
    `INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id`
  )
    .bind(userId, body.endpoint, body.keys.p256dh, body.keys.auth)
    .run();

  return new Response(JSON.stringify({ ok: true }), {
    status: 201,
    headers: { 'content-type': 'application/json' },
  });
}
```

## 4 — VAPID JWT + RFC 8291 payload encryption helper

```typescript
// src/worker/push/encrypt.ts
// Implements RFC 8291 (message encryption for Web Push) using Web Crypto

const B64 = (buf: ArrayBuffer) =>
  btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

const fromB64 = (s: string): Uint8Array =>
  Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));

export async function encryptPayload(
  plaintext: string,
  p256dhB64: string,
  authB64: string
): Promise<{ ciphertext: ArrayBuffer; salt: Uint8Array; serverPublicKey: Uint8Array }> {
  const enc = new TextEncoder();

  // Client's public key
  const clientPub = await crypto.subtle.importKey(
    'raw', fromB64(p256dhB64), { name: 'ECDH', namedCurve: 'P-256' }, true, []
  );

  // Ephemeral server key pair
  const serverKeyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveKey', 'deriveBits']
  );

  // ECDH shared secret
  const sharedBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: clientPub }, serverKeyPair.privateKey, 256
  );

  const salt = crypto.getRandomValues(new Uint8Array(16));
  const serverPubRaw = new Uint8Array(
    await crypto.subtle.exportKey('raw', serverKeyPair.publicKey)
  );
  const authSecret = fromB64(authB64);

  // HKDF — PRK via auth secret (RFC 8291 §3.3)
  const prk = await crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey', 'deriveBits']);

  async function hkdfExpand(prk: CryptoKey, info: Uint8Array, length: number): Promise<Uint8Array> {
    const bits = await crypto.subtle.deriveBits(
      { name: 'HKDF', hash: 'SHA-256', salt: authSecret, info }, prk, length * 8
    );
    return new Uint8Array(bits);
  }

  const keyInfo  = enc.encode('Content-Encoding: aes128gcm\0');
  const nonceInfo = enc.encode('Content-Encoding: nonce\0');

  const contentKey = await crypto.subtle.importKey(
    'raw', await hkdfExpand(prk, keyInfo, 16), { name: 'AES-GCM' }, false, ['encrypt']
  );
  const nonce = await hkdfExpand(prk, nonceInfo, 12);

  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce }, contentKey, enc.encode(plaintext)
  );

  return { ciphertext, salt, serverPublicKey: serverPubRaw };
}
```

## 5 — Worker: send push notification

```typescript
// src/worker/push/send.ts
import { encryptPayload } from './encrypt.js';
import type { Env } from '../types.js';

const B64 = (buf: ArrayBuffer | Uint8Array) =>
  btoa(String.fromCharCode(...(buf instanceof Uint8Array ? buf : new Uint8Array(buf))))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

async function buildVapidHeaders(env: Env, audience: string): Promise<Record<string, string>> {
  const header = B64(new TextEncoder().encode(JSON.stringify({ typ: 'JWT', alg: 'ES256' })));
  const now = Math.floor(Date.now() / 1000);
  const payload = B64(new TextEncoder().encode(JSON.stringify({
    aud: audience, exp: now + 43200, sub: env.VAPID_SUBJECT,
  })));

  const privKeyBytes = Uint8Array.from(atob(env.VAPID_PRIVATE_KEY.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  const privKey = await crypto.subtle.importKey(
    'pkcs8', privKeyBytes, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']
  );
  const sig = B64(await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    privKey,
    new TextEncoder().encode(`${header}.${payload}`)
  ));

  return {
    Authorization: `vapid t=${header}.${payload}.${sig},k=${env.VAPID_PUBLIC_KEY}`,
    'Crypto-Key': `p256ecdsa=${env.VAPID_PUBLIC_KEY}`,
  };
}

export async function sendPush(
  env: Env,
  endpoint: string,
  p256dh: string,
  auth: string,
  notification: { title: string; body: string; url?: string }
): Promise<void> {
  const { ciphertext, salt, serverPublicKey } = await encryptPayload(
    JSON.stringify(notification), p256dh, auth
  );

  const audience = new URL(endpoint).origin;
  const vapidHeaders = await buildVapidHeaders(env, audience);

  // Assemble RFC 8291 body with 86-byte header
  const body = new Uint8Array(86 + ciphertext.byteLength);
  // salt (16) | rs (4) | idlen (1) | keyid (65) | ciphertext
  body.set(salt, 0);
  new DataView(body.buffer).setUint32(16, 4096, false); // record size
  body[20] = 65; // key id length
  body.set(serverPublicKey, 21);
  body.set(new Uint8Array(ciphertext), 86);

  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: {
      ...vapidHeaders,
      'Content-Type': 'application/octet-stream',
      'Content-Encoding': 'aes128gcm',
      'TTL': '86400',
    },
    body,
  });

  if (!resp.ok && resp.status !== 201) {
    throw new Error(`Push failed: ${resp.status} ${await resp.text()}`);
  }
}
```

## 6 — Service Worker handler (client)

```typescript
// public/sw.ts
self.addEventListener('push', (event: PushEvent) => {
  const data = event.data?.json() as { title: string; body: string; url?: string } | null;
  if (!data) return;
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icon-192.png',
      data: { url: data.url ?? '/' },
    })
  );
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url)
  );
});
```

## Anti-patterns

- **Using `web-push` npm package directly in Workers** — it imports `node:crypto`
  and `node:https`; switch to `web-push-webcrypto` or the manual approach above.
- **Storing VAPID private key in plaintext in `wrangler.toml`** — always use
  `wrangler secret put`.
- **Not handling 410 Gone / 404 from push services** — these mean the
  subscription is expired; delete the row from D1 immediately on receipt.

## Gotchas

1. VAPID JWT `aud` must be the **origin** of the push endpoint URL, not the full URL.
2. The AES-GCM ciphertext includes a 16-byte authentication tag appended by
   `crypto.subtle.encrypt`; account for this in the body length calculation.
3. Firefox push endpoints enforce a 4096-byte record size; Chrome is more lenient.
4. `crypto.subtle.importKey('pkcs8', ...)` requires the private key in DER/PKCS8
   format, not raw. Convert with `openssl pkcs8 -topk8 -nocrypt` if needed.

## Verification

```bash
# Apply D1 migration
npx wrangler d1 execute MY_DB --file=migrations/0001_push_subscriptions.sql --local

# Start worker
npx wrangler dev --local --compatibility-date=2025-01-01

# Subscribe from browser DevTools console:
# const sw = await navigator.serviceWorker.ready;
# const sub = await sw.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: 'BEL...' });
# await fetch('/push/subscribe', { method: 'POST', body: JSON.stringify(sub), headers: {'content-type':'application/json'} });

# Trigger a push from curl:
curl -X POST http://localhost:8787/push/send \
  -H 'content-type: application/json' \
  -d '{"userId":"u1","title":"Hello","body":"From Workers!"}'
```

## Related

- `documentation/categories/frontend/workers-pwa-manifest-offline-pages.md`
- `documentation/workers/workers-d1-drizzle-orm.md`

## Sources

- https://datatracker.ietf.org/doc/html/rfc8291 (Message Encryption)
- https://datatracker.ietf.org/doc/html/rfc8292 (VAPID)
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://web.dev/push-notifications-web-push-protocol/
