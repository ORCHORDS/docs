# Web Push Notifications via Cloudflare Workers with VAPID

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to send browser push notifications from a Cloudflare Workers backend without managing a Node.js server. Users subscribe via the Web Push API and your Worker must deliver encrypted payloads using VAPID authentication, handle subscription expiry, and clean up stale endpoints stored in KV.

## Context

The Web Push Protocol (RFC 8030) requires the server to:
1. Authenticate itself to the push service via VAPID (Voluntary Application Server Identification).
2. Encrypt the notification payload with the user's public key using the Message Encryption spec (RFC 8291).
3. Manage subscription lifecycle — subscriptions expire and push services return `410 Gone` or `404` on delivery failure.

Cloudflare Workers provide `SubtleCrypto` natively, making VAPID signing and payload encryption feasible without npm dependencies. Subscriptions are stored in KV for durability across Worker instances.

## Solution

### 1. VAPID Key Generation (one-time, offline)

Generate your VAPID keypair once and store the private key as a Worker secret:

<redacted-secret>
// scripts/generate-vapid-keys.ts  (run locally with Deno or Node)
async function generateVapidKeys() {
  const keyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    ['deriveKey'],
  );

  const publicKeyRaw = await crypto.subtle.exportKey('raw', keyPair.publicKey);
  const privateKeyJwk = await crypto.subtle.exportKey('jwk', keyPair.privateKey);

  const publicKeyB64 = btoa(String.fromCharCode(...new Uint8Array(publicKeyRaw)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

  console.log('VAPID_PUBLIC_KEY =', publicKeyB64);
  console.log('VAPID_PRIVATE_KEY =', JSON.stringify(privateKeyJwk));
}

generateVapidKeys();
// Store VAPID_PRIVATE_KEY via: wrangler secret put VAPID_PRIVATE_KEY
// Store VAPID_PUBLIC_KEY as a plain env var in wrangler.toml
```

### 2. Worker Environment Bindings (`wrangler.toml`)

```toml
[vars]
VAPID_PUBLIC_KEY  = "BExamplePublicKeyBase64UrlEncoded"
VAPID_SUBJECT     = "mailto:push@example.com"

[[kv_namespaces]]
binding = "PUSH_SUBSCRIPTIONS"
id      = "<your-kv-namespace-id>"

# VAPID_PRIVATE_KEY stored as secret via wrangler secret put
```

### 3. TypeScript Types

```typescript
// src/types.ts
export interface Env {
  PUSH_SUBSCRIPTIONS: KVNamespace;
  VAPID_PUBLIC_KEY: string;
  VAPID_PRIVATE_KEY: string;  // JSON-serialised JWK
  VAPID_SUBJECT: string;
}

export interface PushSubscriptionRecord {
  endpoint: string;
  keys: {
    p256dh: string;  // base64url-encoded user public key
    auth: string;    // base64url-encoded 16-byte auth secret
  };
  userId: string;
  createdAt: number;
  lastUsed: number;
}

export interface NotificationPayload {
  title: string;
  body: string;
  icon?: string;
  url?: string;
  tag?: string;
}
```

### 4. Subscription Storage

```typescript
// src/subscriptions.ts
import type { Env, PushSubscriptionRecord } from './types';

export async function saveSubscription(
  env: Env,
  userId: string,
  subscription: PushSubscription,
): Promise<void> {
  const record: PushSubscriptionRecord = {
    endpoint: subscription.endpoint,
    keys: {
      p256dh: subscription.toJSON().keys?.p256dh ?? '',
      auth:   subscription.toJSON().keys?.auth   ?? '',
    },
    userId,
    createdAt: Date.now(),
    lastUsed:  Date.now(),
  };

  // Key by userId + fingerprint of endpoint to support multiple devices
  const endpointHash = await hashEndpoint(subscription.endpoint);
  const kvKey = `sub:${userId}:${endpointHash}`;

  await env.PUSH_SUBSCRIPTIONS.put(kvKey, JSON.stringify(record), {
    expirationTtl: 60 * 60 * 24 * 90, // 90-day TTL; refresh on each visit
  });
}

export async function getSubscriptionsForUser(
  env: Env,
  userId: string,
): Promise<PushSubscriptionRecord[]> {
  const list = await env.PUSH_SUBSCRIPTIONS.list({ prefix: `sub:${userId}:` });
  const records: PushSubscriptionRecord[] = [];

  for (const key of list.keys) {
    const raw = await env.PUSH_SUBSCRIPTIONS.get(key.name);
    if (raw) records.push(JSON.parse(raw) as PushSubscriptionRecord);
  }

  return records;
}

export async function deleteSubscription(
  env: Env,
  userId: string,
  endpoint: string,
): Promise<void> {
  const endpointHash = await hashEndpoint(endpoint);
  await env.PUSH_SUBSCRIPTIONS.delete(`sub:${userId}:${endpointHash}`);
}

async function hashEndpoint(endpoint: string): Promise<string> {
  const data = new TextEncoder().encode(endpoint);
  const buf  = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
    .slice(0, 16);
}
```

### 5. VAPID JWT Signing

```typescript
// src/vapid.ts
function b64urlEncode(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function strToB64url(str: string): string {
  return btoa(unescape(encodeURIComponent(str)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function buildVapidAuthHeader(
  endpoint: string,
  vapidPrivateKeyJwk: JsonWebKey,
  vapidPublicKeyB64: string,
  subject: string,
): Promise<string> {
  const audience = new URL(endpoint).origin;
  const expiration = Math.floor(Date.now() / 1000) + 12 * 3600; // 12h

  const header  = strToB64url(JSON.stringify({ typ: 'JWT', alg: 'ES256' }));
  const payload = strToB64url(JSON.stringify({ aud: audience, exp: expiration, sub: subject }));
  const signingInput = `${header}.${payload}`;

  const privateKey = await crypto.subtle.importKey(
    'jwk',
    vapidPrivateKeyJwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign'],
  );

  const sig = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    privateKey,
    new TextEncoder().encode(signingInput),
  );

  const jwt = `${signingInput}.${b64urlEncode(sig)}`;
  return `vapid t=${jwt},k=${vapidPublicKeyB64}`;
}
```

### 6. Payload Encryption (RFC 8291 / aes128gcm)

```typescript
// src/encrypt.ts
function b64urlDecode(str: string): Uint8Array {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/').padEnd(
    str.length + (4 - (str.length % 4)) % 4, '='
  );
  return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
}

export async function encryptPayload(
  payload: string,
  p256dhB64: string,
  authB64: string,
): Promise<{ ciphertext: Uint8Array; salt: Uint8Array; serverPublicKey: Uint8Array }> {
  const receiverPublicKeyRaw = b64urlDecode(p256dhB64);
  const authSecret           = b64urlDecode(authB64);

  // Generate ephemeral server key pair
  const serverKeyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveKey', 'deriveBits']
  );
  const serverPublicKeyRaw = new Uint8Array(
    await crypto.subtle.exportKey('raw', serverKeyPair.publicKey)
  );

  // Import receiver public key
  const receiverPublicKey = await crypto.subtle.importKey(
    'raw', receiverPublicKeyRaw, { name: 'ECDH', namedCurve: 'P-256' }, false, []
  );

  // ECDH shared secret
  const sharedSecretBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: receiverPublicKey },
    serverKeyPair.privateKey,
    256,
  );

  // HKDF to derive content encryption key and nonce (RFC 8291)
  const salt = crypto.getRandomValues(new Uint8Array(16));

  const hkdfKey = await crypto.subtle.importKey(
    'raw', sharedSecretBits, 'HKDF', false, ['deriveBits']
  );

  // PRK_combine: HKDF-Extract with authSecret as salt, sharedSecret as IKM
  const prk = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: authSecret,
      info: buildInfo('WebPush: info\0', receiverPublicKeyRaw, serverPublicKeyRaw),
    },
    hkdfKey,
    256,
  );

  const prkKey = await crypto.subtle.importKey('raw', prk, 'HKDF', false, ['deriveBits']);

  const cek = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('Content-Encoding: aes128gcm\0') },
    prkKey, 128,
  );
  const nonceBits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('Content-Encoding: nonce\0') },
    prkKey, 96,
  );

  const aesKey = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['encrypt']);

  // Pad and encrypt
  const plaintext = new TextEncoder().encode(payload);
  const paddedPlaintext = new Uint8Array([...plaintext, 2]); // delimiter

  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: new Uint8Array(nonceBits) },
      aesKey,
      paddedPlaintext,
    )
  );

  return { ciphertext, salt, serverPublicKey: serverPublicKeyRaw };
}

function buildInfo(prefix: string, ua: Uint8Array, as: Uint8Array): Uint8Array {
  const p = new TextEncoder().encode(prefix);
  const result = new Uint8Array(p.length + 1 + 2 + ua.length + 2 + as.length);
  let offset = 0;
  result.set(p, offset); offset += p.length;
  result[offset++] = 0;
  new DataView(result.buffer).setUint16(offset, ua.length, false); offset += 2;
  result.set(ua, offset); offset += ua.length;
  new DataView(result.buffer).setUint16(offset, as.length, false); offset += 2;
  result.set(as, offset);
  return result;
}
```

### 7. Worker Entry Point — Send Notification

```typescript
// src/index.ts
import type { Env, NotificationPayload } from './types';
import { getSubscriptionsForUser, deleteSubscription } from './subscriptions';
import { buildVapidAuthHeader } from './vapid';
import { encryptPayload } from './encrypt';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/send' && request.method === 'POST') {
      const { userId, notification } = await request.json<{
        userId: string;
        notification: NotificationPayload;
      }>();

      const results = await sendToUser(env, userId, notification);
      return Response.json({ sent: results.sent, failed: results.failed });
    }

    return new Response('Not found', { status: 404 });
  },
};

async function sendToUser(
  env: Env,
  userId: string,
  notification: NotificationPayload,
): Promise<{ sent: number; failed: number }> {
  const subscriptions = await getSubscriptionsForUser(env, userId);
  const privateKeyJwk: JsonWebKey = JSON.parse(env.VAPID_PRIVATE_KEY);

  let sent = 0;
  let failed = 0;

  await Promise.all(
    subscriptions.map(async sub => {
      try {
        const { ciphertext, salt, serverPublicKey } = await encryptPayload(
          JSON.stringify(notification),
          sub.keys.p256dh,
          sub.keys.auth,
        );

        // Build RFC 8291 aes128gcm content-encoding header
        const recordSize = 4096;
        const header = new Uint8Array(21 + serverPublicKey.length);
        const dv = new DataView(header.buffer);
        header.set(salt, 0);
        dv.setUint32(16, recordSize, false);
        header[20] = serverPublicKey.length;
        header.set(serverPublicKey, 21);

        const body = new Uint8Array(header.length + ciphertext.length);
        body.set(header, 0);
        body.set(ciphertext, header.length);

        const authHeader = await buildVapidAuthHeader(
          sub.endpoint,
          privateKeyJwk,
          env.VAPID_PUBLIC_KEY,
          env.VAPID_SUBJECT,
        );

        const response = await fetch(sub.endpoint, {
          method: 'POST',
          headers: {
            'Content-Type':     'application/octet-stream',
            'Content-Encoding': 'aes128gcm',
            'Authorization':    authHeader,
            'TTL':              '86400',
          },
          body,
        });

        if (response.status === 201) {
          sent++;
        } else if (response.status === 410 || response.status === 404) {
          // Subscription expired — clean up
          await deleteSubscription(env, userId, sub.endpoint);
          failed++;
        } else {
          console.error('Push failed:', response.status, await response.text());
          failed++;
        }
      } catch (err) {
        console.error('Push error:', err);
        failed++;
      }
    }),
  );

  return { sent, failed };
}
```

## Implementation Details

- **Key storage**: VAPID private key lives as a Worker secret (encrypted at rest by Cloudflare). Never embed it in `wrangler.toml`.
- **KV prefix scheme**: `sub:{userId}:{endpointHash}` lets you list all subscriptions for a user with a single `list` call and its prefix filter.
- **TTL refresh**: Call `saveSubscription` on every service-worker registration event, not just the first one. This resets the 90-day KV TTL and keeps active subscribers alive.
- **VAPID JWT lifetime**: 12 hours is the recommended maximum. Do not cache JWTs across requests — compute fresh ones per delivery batch to avoid clock-skew rejections.
- **Concurrency**: `Promise.all` over subscriptions is safe here because each push is an independent outbound HTTP call. If a user has hundreds of devices, chunk into batches of 50 to avoid hitting Workers subrequest limits (1,000 per invocation).
- **RFC 8291 body framing**: The aes128gcm content-encoding prepends a header block containing `salt || rs (uint32be) || keyid_len (uint8) || server_public_key`. Missing this framing causes the browser to silently discard the notification.

## Anti-patterns

- **Do not** use the `aesgcm` legacy encryption scheme. Modern browsers only support `aes128gcm`.
- **Do not** send the VAPID private key through a KV namespace — use `wrangler secret put`.
- **Do not** ignore `410 Gone` responses. Accumulating dead subscriptions wastes KV storage and increases delivery time.
- **Do not** reuse ephemeral ECDH key pairs across messages. Generate a fresh pair per encryption call.
- **Do not** set `TTL: 0` unless you need immediate delivery semantics — it means "discard if not deliverable now".

## Gotchas

- Chrome-controlled push services (FCM) have their own rate limits. Bursting thousands of pushes in a single Worker invocation will hit the 1,000 subrequest cap.
- Safari requires the `Web-Push` HTTP header on the subscription request from the browser side; the server-side protocol remains the same.
- Workers' `SubtleCrypto.deriveBits` requires the key to be exported as `extractable: false` after import — but for HKDF you must import with `extractable: false` from the start.
- The RFC 8291 `keyid` field length byte must equal 65 (uncompressed P-256 key), not 0 or a compressed length.

## Verification

1. Register a push subscription in the browser devtools console:
   ```js
   const reg = await navigator.serviceWorker.ready;
   const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: '<VAPID_PUBLIC_KEY>' });
   console.log(JSON.stringify(sub));
   ```
2. POST the JSON output to your `/subscribe` endpoint.
3. Trigger `/send` with the `userId`.
4. Confirm the notification appears without devtools open (service worker must be active).
5. Verify the subscription KV entry exists: `wrangler kv:key get --namespace-id=<id> sub:<userId>:<hash>`.
6. To test expiry cleanup, use a tampered endpoint and verify the key is deleted after the 410 response.

## Related

- `workers-device-fingerprint-session-kv.md` — linking push subscriptions to authenticated sessions
- `workers-app-manifest-dynamic-pwa.md` — install prompt and PWA registration flow
- Cloudflare Workers KV docs: https://developers.cloudflare.com/kv/
- RFC 8030 (Web Push): https://datatracker.ietf.org/doc/html/rfc8030
- RFC 8291 (Message Encryption): https://datatracker.ietf.org/doc/html/rfc8291

## Sources

- RFC 8030 — Generic Event Delivery Using HTTP Push
- RFC 8291 — Message Encryption for Web Push
- RFC 7515 — JSON Web Signature (JWT)
- Web Push Voluntary Application Server Identification (VAPID) — RFC 8292
- Cloudflare Workers SubtleCrypto reference: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
