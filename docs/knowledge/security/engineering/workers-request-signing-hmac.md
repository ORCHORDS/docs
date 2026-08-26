# HMAC Request Signing for Service-to-Service Authentication in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Two Cloudflare Workers (or a Worker and an external service) need to authenticate each other without transmitting long-lived secrets in headers. Requests must be tamper-evident so that a man-in-the-middle cannot modify the payload or headers undetected, and replayed requests captured in transit must be rejected.

## Context

HMAC-SHA256 request signing follows the same principles as AWS Signature Version 4 but simplified for Workers-to-Workers communication. A canonical string is built from deterministic parts of the request (method, path, query, selected headers, body hash), then signed with a shared secret imported via Web Crypto. The receiving Worker independently reconstructs the canonical string and compares signatures in constant time.

## Solution

### Step 1 — Key Import Helper

```typescript
// lib/hmac.ts
export async function importHmacKey(secret: string): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,          // not extractable
    ['sign', 'verify']
  );
}

export async function hmacSign(key: CryptoKey, message: string): Promise<string> {
  const encoder = new TextEncoder();
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(message));
  return bufferToHex(signature);
}

export async function hmacVerify(
  key: CryptoKey,
  message: string,
  expectedHex: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const expected = hexToBuffer(expectedHex);
  return crypto.subtle.verify('HMAC', key, expected, encoder.encode(message));
}

function bufferToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function hexToBuffer(hex: string): Uint8Array {
  const bytes = [];
  for (let i = 0; i < hex.length; i += 2) {
    bytes.push(parseInt(hex.slice(i, i + 2), 16));
  }
  return new Uint8Array(bytes);
}
```

### Step 2 — Canonical Request String Builder

```typescript
// lib/canonical.ts
export const SIGNED_HEADERS = ['content-type', 'x-service-id', 'x-timestamp'];

export async function buildCanonicalString(
  request: Request,
  bodyHash: string
): Promise<string> {
  const url = new URL(request.url);

  // Sorted, lowercase query parameters
  const sortedQuery = [...url.searchParams.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');

  // Only sign the listed headers, in a fixed order
  const canonicalHeaders = SIGNED_HEADERS
    .map(h => `${h}:${(request.headers.get(h) ?? '').trim()}`)
    .join('\n');

  return [
    request.method.toUpperCase(),
    url.pathname,
    sortedQuery,
    canonicalHeaders,
    SIGNED_HEADERS.join(';'),
    bodyHash,
  ].join('\n');
}

export async function hashBody(body: string | null): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(body ?? '');
  const digest = await crypto.subtle.digest('SHA-256', data);
  return bufferToHex(digest);
}

function bufferToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

### Step 3 — Signing Outbound Requests

```typescript
// lib/signer.ts
import { importHmacKey, hmacSign } from './hmac';
import { buildCanonicalString, hashBody } from './canonical';

export async function signRequest(
  request: Request,
  secret: string,
  serviceId: string
): Promise<Request> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const body = request.body ? await request.clone().text() : null;
  const bodyHash = await hashBody(body);

  // Clone with added signing headers before building canonical string
  const headers = new Headers(request.headers);
  headers.set('x-timestamp', timestamp);
  headers.set('x-service-id', serviceId);
  if (body !== null && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }

  const signedRequest = new Request(request.url, {
    method: request.method,
    headers,
    body,
  });

  const canonical = await buildCanonicalString(signedRequest, bodyHash);
  const key = await importHmacKey(secret);
  const signature = await hmacSign(key, canonical);

  headers.set('x-signature', signature);
  return new Request(request.url, { method: request.method, headers, body });
}
```

### Step 4 — Signature Verification Middleware

```typescript
// middleware/verifySignature.ts
import { importHmacKey, hmacVerify } from '../lib/hmac';
import { buildCanonicalString, hashBody } from '../lib/canonical';

const MAX_CLOCK_SKEW_SECONDS = 300; // 5 minutes

export async function verifySignatureMiddleware(
  request: Request,
  secret: string,
  usedNonces: KVNamespace
): Promise<{ ok: true } | { ok: false; status: number; message: string }> {
  const timestamp = request.headers.get('x-timestamp');
  const signature = request.headers.get('x-signature');

  if (!timestamp || !signature) {
    return { ok: false, status: 401, message: 'Missing signing headers' };
  }

  // Replay prevention: reject requests outside the clock skew window
  const requestTime = parseInt(timestamp, 10);
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - requestTime) > MAX_CLOCK_SKEW_SECONDS) {
    return { ok: false, status: 401, message: 'Request timestamp out of range' };
  }

  // Nonce check — prevent exact replay within the skew window
  const nonceKey = `nonce:${signature}`;
  const used = await usedNonces.get(nonceKey);
  if (used) {
    return { ok: false, status: 401, message: 'Request already processed' };
  }

  // Reconstruct canonical string from the incoming request
  const body = request.body ? await request.clone().text() : null;
  const bodyHash = await hashBody(body);
  const canonical = await buildCanonicalString(request, bodyHash);

  const key = await importHmacKey(secret);
  const valid = await hmacVerify(key, canonical, signature);

  if (!valid) {
    return { ok: false, status: 401, message: 'Signature mismatch' };
  }

  // Mark nonce as used (TTL slightly longer than skew window)
  await usedNonces.put(nonceKey, '1', { expirationTtl: MAX_CLOCK_SKEW_SECONDS + 60 });
  return { ok: true };
}
```

### Step 5 — Worker Integration Example

```typescript
// worker.ts
import { signRequest } from './lib/signer';
import { verifySignatureMiddleware } from './middleware/verifySignature';

interface Env {
  SHARED_SECRET: string;
  SERVICE_ID: string;
  NONCE_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // --- Receiving side: verify incoming signed request ---
    if (url.pathname === '/api/internal/data') {
      const result = await verifySignatureMiddleware(request, env.SHARED_SECRET, env.NONCE_KV);
      if (!result.ok) {
        return new Response(result.message, { status: result.status });
      }
      return Response.json({ data: 'secret payload' });
    }

    // --- Sending side: sign an outbound request to another service ---
    if (url.pathname === '/proxy/fetch') {
      const outbound = new Request('https://other-worker.example.com/api/internal/data', {
        method: 'GET',
      });
      const signed = await signRequest(outbound, env.SHARED_SECRET, env.SERVICE_ID);
      return fetch(signed);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

- **Key import**: `importKey` with `extractable: false` ensures the raw secret cannot be exported back from the CryptoKey object, limiting exposure if the key object leaks.
- **Canonical ordering**: Sorting query parameters and using a fixed set of signed headers makes the canonical string deterministic regardless of header insertion order.
- **Body hashing**: Including a SHA-256 hash of the body in the canonical string makes any payload modification detectable even when TLS is terminated at an intermediary.
- **Clock skew**: 300 seconds (5 minutes) matches AWS SigV4 and is a practical tolerance for Workers running across Cloudflare's globally distributed PoPs.
- **Nonce KV TTL**: Set to `MAX_CLOCK_SKEW_SECONDS + 60` so the nonce outlives the window during which a replay would otherwise be accepted.

## Anti-patterns

- Do not compare signatures with `===`; always use `crypto.subtle.verify` for constant-time comparison to prevent timing attacks.
- Do not sign only the URL — a body substitution attack becomes trivial without body hashing.
- Do not use a single global nonce store shared across all service pairs; namespace nonce keys by `serviceId:signature`.
- Do not rely solely on timestamp freshness without a nonce store; two requests with identical payloads in the same second would both pass.
- Do not use `MD5` or `SHA-1` for the body hash; use `SHA-256` minimum.

## Gotchas

- `request.clone().text()` consumes the body stream; ensure you always clone before reading if the body needs to be forwarded later.
- Workers KV `put` is asynchronous — await it before returning the success response to avoid a race where a fast retry arrives before the nonce is stored.
- Header names are case-insensitive in HTTP but string-sensitive in JavaScript. Normalize all header names to lowercase before building the canonical string.
- When the shared secret rotates, have a brief overlap period where both old and new secrets are valid to avoid downtime during rolling deploys.

## Verification

1. Send a correctly signed request — expect `200`.
2. Replay the identical request — expect `401 Request already processed`.
3. Mutate a single character in the signature — expect `401 Signature mismatch`.
4. Set `x-timestamp` to a value 400 seconds in the past — expect `401 Request timestamp out of range`.
5. Modify the request body after signing — expect `401 Signature mismatch`.

## Related

- `workers-oauth2-pkce-flow.md` — obtaining bearer tokens to use alongside HMAC signing
- `workers-ip-allowlist-kv-middleware.md` — additional network-layer restriction for internal APIs

## Sources

- Web Crypto API (Cloudflare Workers): https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- AWS Signature Version 4 (canonical request reference): https://docs.aws.amazon.com/general/latest/gr/sigv4-create-canonical-request.html
- RFC 2104 — HMAC: https://datatracker.ietf.org/doc/html/rfc2104
