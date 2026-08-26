# HMAC-Signed API Requests from React Native to Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Mobile API endpoints on Cloudflare Workers are scraped or abused by automated clients that bypass JWT authentication, because the signing secret is embedded in the app binary or extracted from a rooted device.

## Context
HMAC-SHA256 request signing provides a shared-secret layer on top of (or instead of) JWT bearer tokens. The Worker verifies the signature and a short-lived nonce, rejecting replayed or tampered requests. The secret is provisioned at install time from the Worker (bound to a device attestation), stored in the platform keychain, and never transmitted after provisioning. This pattern complements — but does not replace — Play Integrity / App Attest device attestation.

## Cloudflare Worker — Signature Verification
```typescript
// workers/middleware/hmac-verify.ts
export interface HmacEnv {
  HMAC_SECRET_KV: KVNamespace;   // per-device secrets stored by device_id
  NONCE_KV: KVNamespace;         // short-lived nonce deduplication
}

export async function verifyHmacSignature(
  req: Request,
  env: HmacEnv,
): Promise<Response | null> {
  const deviceId   = req.headers.get('X-Device-Id') ?? '';
  const timestamp  = req.headers.get('X-Timestamp') ?? '';
  const nonce      = req.headers.get('X-Nonce') ?? '';
  const signature  = req.headers.get('X-Signature') ?? '';

  if (!deviceId || !timestamp || !nonce || !signature) {
    return new Response('Missing HMAC headers', { status: 400 });
  }

  // Reject requests older than 5 minutes (clock skew tolerance)
  const ts = Number(timestamp);
  if (Math.abs(Date.now() - ts) > 5 * 60 * 1000) {
    return new Response('Request expired', { status: 401 });
  }

  // Deduplicate nonces to block replay attacks
  const nonceKey = `nonce:${deviceId}:${nonce}`;
  const seen = await env.NONCE_KV.get(nonceKey);
  if (seen) return new Response('Replay detected', { status: 401 });
  await env.NONCE_KV.put(nonceKey, '1', { expirationTtl: 600 }); // 10 min TTL

  // Look up per-device secret
  const secret = await env.HMAC_SECRET_KV.get(`secret:${deviceId}`);
  if (!secret) return new Response('Unknown device', { status: 403 });

  // Reconstruct the signed string: METHOD\nURL\nTIMESTAMP\nNONCE\nBODY_HASH
  const bodyBytes = new Uint8Array(await req.clone().arrayBuffer());
  const bodyHash  = Array.from(
    new Uint8Array(await crypto.subtle.digest('SHA-256', bodyBytes))
  ).map(b => b.toString(16).padStart(2, '0')).join('');

  const url = new URL(req.url);
  const stringToSign = [req.method, url.pathname + url.search, timestamp, nonce, bodyHash].join('\n');

  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
  );
  const sigBytes = Uint8Array.from(
    atob(signature.replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0)
  );
  const valid = await crypto.subtle.verify(
    'HMAC', key, sigBytes, new TextEncoder().encode(stringToSign)
  );
  if (!valid) return new Response('Invalid signature', { status: 401 });

  return null; // pass through to handler
}
```

## React Native — HMAC Signing Utility
```typescript
// src/api/hmac.ts  (requires react-native-quick-crypto or expo-crypto)
import { createHmac, createHash } from 'react-native-quick-crypto';
import { getSecureItem } from './keychain';    // react-native-keychain wrapper
import uuid from 'react-native-uuid';

interface SignedHeaders {
  'X-Device-Id': string;
  'X-Timestamp': string;
  'X-Nonce': string;
  'X-Signature': string;
}

export async function buildHmacHeaders(
  method: string,
  path: string,
  body: string | null,
): Promise<SignedHeaders> {
  const [deviceId, secret] = await Promise.all([
    getSecureItem('device_id'),
    getSecureItem('hmac_secret'),
  ]);

  if (!deviceId || !secret) throw new Error('Device not provisioned');

  const timestamp = String(Date.now());
  const nonce     = uuid.v4() as string;

  const bodyHash = body
    ? createHash('sha256').update(body).digest('hex')
    : createHash('sha256').update('').digest('hex');

  const stringToSign = [method.toUpperCase(), path, timestamp, nonce, bodyHash].join('\n');
  const signature = createHmac('sha256', secret)
    .update(stringToSign)
    .digest('base64url');    // URL-safe base64, no padding issues

  return {
    'X-Device-Id': deviceId,
    'X-Timestamp': timestamp,
    'X-Nonce': nonce,
    'X-Signature': signature,
  };
}
```

## React Native — Signed Fetch Wrapper
```typescript
// src/api/signedFetch.ts
import { buildHmacHeaders } from './hmac';

export async function signedFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const parsed = new URL(url);
  const method = (init.method ?? 'GET').toUpperCase();
  const body   = typeof init.body === 'string' ? init.body : null;

  const hmacHeaders = await buildHmacHeaders(method, parsed.pathname + parsed.search, body);

  return fetch(url, {
    ...init,
    headers: {
      ...init.headers,
      ...hmacHeaders,
      'Content-Type': 'application/json',
    },
  });
}

// Usage
const res = await signedFetch('https://api.example.com/items', {
  method: 'POST',
  body: JSON.stringify({ title: 'New item' }),
});
```

## Device Provisioning Flow
```typescript
// workers/provision.ts — called once after App Attest / Play Integrity verification
export async function provisionDevice(req: Request, env: HmacEnv & { ATTESTATION_KV: KVNamespace }) {
  // 1. Validate App Attest / Play Integrity token (omitted for brevity)
  const attestationValid = await validateAttestation(req, env);
  if (!attestationValid) return new Response('Attestation failed', { status: 403 });

  const deviceId = crypto.randomUUID();
  const secret   = Array.from(
    crypto.getRandomValues(new Uint8Array(32))
  ).map(b => b.toString(16).padStart(2, '0')).join('');

  await env.HMAC_SECRET_KV.put(`secret:${deviceId}`, secret, {
    expirationTtl: 90 * 24 * 3600,   // rotate every 90 days
  });

  return Response.json({ deviceId, secret });
}
```

```typescript
// src/provisioning/registerDevice.ts  (run at app first-launch)
import * as Keychain from 'react-native-keychain';
import uuid from 'react-native-uuid';

export async function provisionIfNeeded(): Promise<void> {
  const existing = await Keychain.getGenericPassword({ service: 'hmac_secret' });
  if (existing) return;   // already provisioned

  const attestToken = await getPlayIntegrityOrAppAttestToken();
  const res = await fetch('https://api.example.com/provision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Attest': attestToken },
    body: JSON.stringify({ platform: Platform.OS }),
  });
  const { deviceId, secret } = await res.json();

  await Keychain.setGenericPassword('device', deviceId, { service: 'device_id' });
  await Keychain.setGenericPassword('device', secret,   { service: 'hmac_secret' });
}
```

## Anti-patterns
- Hardcoding the HMAC secret in the app bundle — extractable via reverse engineering or memory inspection.
- Omitting the request body from the signed string — allows body substitution attacks while keeping a valid signature.
- Using a monotonic counter instead of a nonce — counters can be predicted and exploited across device restarts.
- Storing the secret in AsyncStorage or MMKV — unencrypted on unrooted devices and trivially readable on rooted ones.
- Skipping the timestamp check — without it, captured requests can be replayed indefinitely.

## Gotchas
- `Date.now()` on Android can drift by several seconds on budget devices without NTP sync; the 5-minute window accommodates typical skew.
- URL encoding differences between the client URL builder and the Worker's `URL` parser can cause signature mismatches — always sign `pathname + search`, not the full URL including origin.
- Rotating secrets requires a background sync to deliver the new secret before the old one's TTL expires; overlap the TTL windows by at least 24 hours.
- KV nonce deduplication has ~60 ms eventual consistency; under extreme write concurrency a replayed nonce could slip through. Use Durable Objects for stricter guarantees.

## Verification
1. Capture a signed request with Proxyman and replay it immediately — the Worker should return 401 (duplicate nonce).
2. Replay the same request 6 minutes later — the Worker should return 401 (expired timestamp).
3. Tamper with the request body and replay — the Worker should return 401 (invalid signature).
4. Uninstall and reinstall the app — `provisionIfNeeded()` should issue a new `deviceId`/`secret` pair and subsequent signed requests should succeed.

## Related
- [play-integrity-attestation.md](play-integrity-attestation.md)
- [cross-platform-app-attestation-device-integrity.md](cross-platform-app-attestation-device-integrity.md)
- [mobile-jwt-storage-pitfalls.md](mobile-jwt-storage-pitfalls.md)
- [react-native-secure-storage.md](react-native-secure-storage.md)
- [mobile-auth-oauth-pkce.md](mobile-auth-oauth-pkce.md)

## Sources
- MDN SubtleCrypto HMAC: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- react-native-quick-crypto: https://github.com/margelo/react-native-quick-crypto
- Cloudflare Workers KV TTL: https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
