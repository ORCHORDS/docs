# Cryptographic Signing of API Responses in Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A downstream client — a mobile app, another microservice, or a CLI tool — fetches data from a Cloudflare Worker and must verify that:

1. The response body was authored by the legitimate Worker, not a CDN cache poisoning attack or a man-in-the-middle.
2. The response has not been tampered with in transit (beyond what TLS already guarantees).
3. A specific set of response headers (e.g., `Content-Type`, `X-Request-Id`) was set by the Worker, not injected by an intermediary.

TLS alone is insufficient when edge nodes, reverse proxies, or third-party CDN layers sit between the Worker and the client. Response signing provides an end-to-end integrity and authenticity guarantee that survives all transport layers.

## Context

The Web Crypto API is available natively inside the Workers runtime. Ed25519 (via `CryptoKey` with `{ name: "Ed25519" }`) is the preferred algorithm: it is fast, produces compact 64-byte signatures, has no weak parameter choices unlike RSA/ECDSA, and its public keys are only 32 bytes — small enough to embed directly in firmware or mobile app bundles.

The signing approach here follows the structure popularised by the IETF HTTP Message Signatures specification (RFC 9421) but is intentionally simplified for API responses: a canonical byte string is constructed from selected headers plus the full response body, then signed once before the response is sent.

Key pairs are stored as Workers Secrets (environment variables) in base64-encoded form. The Worker exports the public key in raw format so clients can verify without a certificate hierarchy.

## Generating and Rotating the Signing Key Pair

Generate a key pair locally, base64-encode it, and upload it as Secrets.

```bash
# One-time setup — run locally, never commit to VCS
node -e "
const { subtle } = globalThis.crypto;
async function main() {
  const { privateKey, publicKey } = await subtle.generateKey(
    { name: 'Ed25519' },
    true,   // extractable
    ['sign', 'verify']
  );
  const priv = Buffer.from(await subtle.exportKey('pkcs8', privateKey)).toString('base64');
  const pub  = Buffer.from(await subtle.exportKey('raw',   publicKey )).toString('base64');
  console.log('SIGNING_PRIVATE_KEY=' + priv);
  console.log('SIGNING_PUBLIC_KEY='  + pub);
}
main();
"

# Upload to Workers — repeat for each environment
wrangler secret put SIGNING_PRIVATE_KEY
wrangler secret put SIGNING_PUBLIC_KEY
```

For zero-downtime rotation, promote a new key pair while the old key ID is still accepted on the client side. Embed the key ID (e.g., a short hash of the public key) in the `X-Signature-Key-Id` header so clients know which public key to use when you eventually maintain two active keys during a rollover window.

## Signing Logic in the Worker

```typescript
// src/signing.ts

export interface SigningEnv {
  SIGNING_PRIVATE_KEY: string; // base64-encoded PKCS#8
  SIGNING_PUBLIC_KEY:  string; // base64-encoded raw 32 bytes
}

/**
 * Import the Ed25519 private key from a base64-encoded PKCS#8 blob.
 * Cache the CryptoKey in a module-level variable so the import only
 * runs once per isolate lifetime.
 */
let _cachedKey: CryptoKey | null = null;

async function getSigningKey(b64: string): Promise<CryptoKey> {
  if (_cachedKey) return _cachedKey;
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  _cachedKey = await crypto.subtle.importKey(
    'pkcs8',
    raw.buffer,
    { name: 'Ed25519' },
    false,  // non-extractable at runtime
    ['sign']
  );
  return _cachedKey;
}

/**
 * Build the canonical byte string that is signed.
 * Format (newline-delimited):
 *   METHOD SP REQUEST_PATH\n
 *   content-type: VALUE\n
 *   x-request-id: VALUE\n
 *   \n
 *   BODY_HEX
 *
 * Only include headers that are meaningful for integrity; omit
 * hop-by-hop headers (Connection, Transfer-Encoding, etc.).
 */
function buildSigningInput(
  method: string,
  path: string,
  headers: Headers,
  bodyHex: string
): string {
  const SIGNED_HEADERS = ['content-type', 'x-request-id', 'cache-control'];
  const headerLines = SIGNED_HEADERS
    .filter(h => headers.has(h))
    .map(h => `${h}: ${headers.get(h)}`)
    .join('\n');
  return `${method.toUpperCase()} ${path}\n${headerLines}\n\n${bodyHex}`;
}

/**
 * Sign a Response and return a new Response with two extra headers:
 *   X-Signature:        base64url Ed25519 signature
 *   X-Signature-Key-Id: first 8 chars of the base64 public key (stable identifier)
 */
export async function signResponse(
  request: Request,
  response: Response,
  env: SigningEnv
): Promise<Response> {
  // Buffer the body — Workers stream is consumed once
  const bodyBytes = new Uint8Array(await response.arrayBuffer());
  const bodyHex   = Array.from(bodyBytes).map(b => b.toString(16).padStart(2, '0')).join('');

  const url    = new URL(request.url);
  const method = request.method;
  const path   = url.pathname + url.search;

  const newHeaders = new Headers(response.headers);
  const signingInput = buildSigningInput(method, path, newHeaders, bodyHex);

  const key       = await getSigningKey(env.SIGNING_PRIVATE_KEY);
  const encoder   = new TextEncoder();
  const sigBuffer = await crypto.subtle.sign(
    { name: 'Ed25519' },
    key,
    encoder.encode(signingInput)
  );

  const sigB64   = btoa(String.fromCharCode(...new Uint8Array(sigBuffer)));
  const keyId    = env.SIGNING_PUBLIC_KEY.slice(0, 8);

  newHeaders.set('X-Signature',        sigB64);
  newHeaders.set('X-Signature-Key-Id', keyId);

  return new Response(bodyBytes, {
    status:  response.status,
    headers: newHeaders,
  });
}
```

Wire it into your handler:

```typescript
// src/index.ts
import { signResponse, SigningEnv } from './signing';

export default {
  async fetch(request: Request, env: SigningEnv): Promise<Response> {
    // ... your normal business logic ...
    const upstream = await fetch('https://internal-api.example.com' + new URL(request.url).pathname);
    return signResponse(request, upstream, env);
  },
};
```

## Client-Side Verification

```typescript
// Runs in any Web Crypto environment: browser, Node ≥ 18, Deno, Bun.

async function verifyResponseSignature(
  response: Response,
  publicKeyB64: string,
  originalRequest: Request
): Promise<boolean> {
  const sig    = response.headers.get('X-Signature');
  if (!sig) return false;

  const bodyBytes = new Uint8Array(await response.clone().arrayBuffer());
  const bodyHex   = Array.from(bodyBytes).map(b => b.toString(16).padStart(2, '0')).join('');

  const url    = new URL(originalRequest.url);
  const method = originalRequest.method;
  const path   = url.pathname + url.search;

  const SIGNED_HEADERS = ['content-type', 'x-request-id', 'cache-control'];
  const headerLines = SIGNED_HEADERS
    .filter(h => response.headers.has(h))
    .map(h => `${h}: ${response.headers.get(h)}`)
    .join('\n');

  const signingInput = `${method.toUpperCase()} ${path}\n${headerLines}\n\n${bodyHex}`;

  const rawKey = Uint8Array.from(atob(publicKeyB64), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    'raw',
    rawKey.buffer,
    { name: 'Ed25519' },
    false,
    ['verify']
  );

  const sigBytes = Uint8Array.from(atob(sig), c => c.charCodeAt(0));
  const encoder  = new TextEncoder();
  return crypto.subtle.verify(
    { name: 'Ed25519' },
    key,
    sigBytes,
    encoder.encode(signingInput)
  );
}

// Usage
const ok = await verifyResponseSignature(response, PUBLIC_KEY_B64, request);
if (!ok) throw new Error('Response signature verification failed');
```

## Anti-patterns

**Do not sign compressed bodies.** If your Worker applies Brotli or gzip via the `Content-Encoding` header after signing, the bytes the client receives differ from the bytes that were signed. Sign the raw, uncompressed body or set a canonical representation that includes the `Content-Encoding` header value and applies the same encoding before hashing.

**Do not sign only the body hash.** Signing just `SHA-256(body)` without including the request path and key response headers allows a signature from endpoint `/api/v1/user/1` to be replayed against `/api/v1/admin/1` if the bodies are structurally identical. Always bind the signature to the request context.

**Do not use HMAC with a symmetric key for cross-client verification.** HMAC requires the client to possess the same secret, which means every compromised client exposes the signing key. Ed25519 asymmetric signing lets you freely publish the verification key.

**Do not store the private key in wrangler.toml or `.dev.vars` committed to the repo.** Always use `wrangler secret put`. The dev variable can live in `.dev.vars` (git-ignored) for local development.

**Do not cache the full response body in Workers KV before signing.** Sign the response as it leaves the Worker, not a cached copy; stale cache entries might carry a valid signature on outdated data.

## Gotchas

- **Streaming vs. buffering**: Signing requires the complete body before you can compute the signature. This forces `response.arrayBuffer()`, which buffers the entire response in the isolate's memory. For very large responses (> a few MB), consider signing only a SHA-256 digest of the body and including `content-digest: sha-256=...` in the signed header set, following RFC 9530.
- **Key caching across isolates**: The module-level `_cachedKey` variable is local to each isolate instance. When the Worker cold-starts under high load, many parallel isolates each pay the import cost once. This is acceptable; do not attempt cross-isolate shared state.
- **Clock skew in freshness checking**: If you also want replay protection (not just integrity), add a signed `X-Response-Timestamp` header and reject responses older than 60 seconds on the client side.
- **Ed25519 availability**: Workers runtime v3 and above include Ed25519 in SubtleCrypto. Miniflare (local dev) v3+ also supports it. Older pinned runtimes may need to fall back to P-256 ECDSA.

## Verification

```bash
# Fetch a signed response and verify the signature header exists
curl -si https://api.example.com/v1/data | grep -i x-signature

# End-to-end test using a small Node script
node -e "
const PUB = process.env.SIGNING_PUBLIC_KEY;
// ... paste verifyResponseSignature function above ...
fetch('https://api.example.com/v1/data').then(async res => {
  const ok = await verifyResponseSignature(res, PUB, { url: res.url, method: 'GET' });
  console.log('Signature valid:', ok);
});
"

# Confirm the key ID header matches the first 8 chars of the public key
curl -si https://api.example.com/v1/data | grep X-Signature-Key-Id
```

Unit test the canonicalization function independently before testing the full signing pipeline — it is the most likely source of client/server divergence.

## Related

- `http-message-signatures-component-coverage-and-replay.md` — RFC 9421 full spec for request signing
- `api-key-authentication.md` — simpler bearer-token auth for lower-trust scenarios
- `secrets-encryption-at-rest.md` — how to protect the private key at rest
- `jwt-best-practices.md` — JWT as an alternative response-integrity mechanism
- `timing-safe-compare.md` — safe signature bytes comparison on the client side

## Sources

- RFC 9421 — HTTP Message Signatures (IETF, 2024)
- RFC 9530 — Digest Fields for HTTP (IETF, 2024)
- Web Cryptography API W3C specification — SubtleCrypto.sign() with Ed25519
- Cloudflare Workers Runtime API — Web Standards compatibility notes
- NIST SP 800-186 — Recommendations for Discrete Logarithm-based Cryptography (EdDSA)
