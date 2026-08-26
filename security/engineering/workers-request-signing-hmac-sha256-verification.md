# Request Signing with HMAC-SHA256 for Workers Service-to-Service Auth

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Cloudflare Workers calling each other internally. You need to prove that a request originates from a trusted caller Worker — not an arbitrary internet client — without exposing a shared secret in plaintext headers.

## Context

HMAC-SHA256 request signing lets the calling Worker produce a cryptographic signature over deterministic request attributes (method, path, timestamp, body hash). The receiving Worker verifies the signature using a shared secret stored in KV. Replay attacks are mitigated by rejecting signatures whose embedded timestamp is more than 5 minutes old. Key rotation is handled with a dual-secret KV strategy so both the old and new key are accepted during the rotation window.

---

## Signing and Verification Implementation

```typescript
// shared/signing.ts  — imported by both caller and receiver Workers

export interface SignatureComponents {
  method: string;       // uppercase HTTP verb
  path: string;         // pathname + search string, e.g. /api/users?page=2
  timestamp: number;    // Unix seconds (Math.floor(Date.now() / 1000))
  bodyHash: string;     // hex SHA-256 of the raw request body ('' for no body)
}

/** Build the canonical string that is signed / verified. */
export function buildSigningString(c: SignatureComponents): string {
  return `${c.method}\n${c.path}\n${c.timestamp}\n${c.bodyHash}`;
}

/** Derive a CryptoKey from a raw UTF-8 secret string. */
async function importKey(secret: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify'],
  );
}

/** Compute HMAC-SHA256 over the canonical string; returns hex. */
export async function sign(components: SignatureComponents, secret: string): Promise<string> {
  const key = await importKey(secret);
  const signingString = buildSigningString(components);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(signingString));
  return Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

/** Constant-time verify; returns true if signature matches. */
export async function verify(components: SignatureComponents, secret: string, sig: string): Promise<boolean> {
  const key = await importKey(secret);
  const signingString = buildSigningString(components);
  const expected = new Uint8Array(
    sig.match(/../g)!.map(h => parseInt(h, 16)),
  );
  return crypto.subtle.verify('HMAC', key, expected, new TextEncoder().encode(signingString));
}

/** SHA-256 hex of arbitrary bytes. */
export async function hashBody(body: ArrayBuffer | null): Promise<string> {
  if (!body || body.byteLength === 0) return '';
  const digest = await crypto.subtle.digest('SHA-256', body);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## Calling Worker — Attaching the Signature

```typescript
// caller/index.ts
import { sign, hashBody } from '../shared/signing';

interface Env {
  SIGNING_SECRET: string;   // wrangler secret
  RECEIVER_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(env.RECEIVER_URL + '/api/data');
    const bodyBytes = new TextEncoder().encode(JSON.stringify({ hello: 'world' }));
    const bodyHash = await hashBody(bodyBytes.buffer as ArrayBuffer);
    const timestamp = Math.floor(Date.now() / 1000);

    const sig = await sign(
      { method: 'POST', path: url.pathname + url.search, timestamp, bodyHash },
      env.SIGNING_SECRET,
    );

    return fetch(url.toString(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Signature': `t=${timestamp},v1=${sig}`,
      },
      body: bodyBytes,
    });
  },
};
```

---

## Receiving Worker — Verifying the Signature

```typescript
// receiver/index.ts
import { verify, hashBody } from '../shared/signing';

interface Env {
  SIGNING_SECRETS: KVNamespace;  // KV binding; keys: 'v1', 'v2' during rotation
}

const MAX_CLOCK_SKEW_SECONDS = 300; // 5 minutes

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const header = request.headers.get('X-Signature') ?? '';
    const match = header.match(/^t=(\d+),v1=([0-9a-f]+)$/);
    if (!match) return new Response('Missing signature', { status: 401 });

    const timestamp = parseInt(match[1], 10);
    const sig = match[2];
    const now = Math.floor(Date.now() / 1000);

    if (Math.abs(now - timestamp) > MAX_CLOCK_SKEW_SECONDS) {
      return new Response('Signature expired', { status: 401 });
    }

    const bodyBuffer = await request.arrayBuffer();
    const bodyHash = await hashBody(bodyBuffer);
    const url = new URL(request.url);
    const components = { method: request.method, path: url.pathname + url.search, timestamp, bodyHash };

    // Dual-key check: try current key first, then previous key (rotation window)
    const [secret1, secret2] = await Promise.all([
      env.SIGNING_SECRETS.get('v1'),
      env.SIGNING_SECRETS.get('v2'),
    ]);

    const secrets = [secret1, secret2].filter(Boolean) as string[];
    let valid = false;
    for (const secret of secrets) {
      if (await verify(components, secret, sig)) { valid = true; break; }
    }
    if (!valid) return new Response('Invalid signature', { status: 401 });

    // Re-attach body for downstream processing
    return handleVerifiedRequest(new Request(request, { body: bodyBuffer }));
  },
};

async function handleVerifiedRequest(req: Request): Promise<Response> {
  return Response.json({ ok: true });
}
```

---

## Key Rotation Strategy

1. Generate a new secret and write it to KV as `v2` (keep existing `v1` in place).
2. Deploy the new signing secret to the **calling** Worker as `SIGNING_SECRET=<new>`.
3. Both Workers now accept `v1` and `v2` signatures during the rotation window.
4. After the rotation window (e.g. 10 minutes), delete `v1` from KV and rename `v2` → `v1`.

KV write commands:
```bash
wrangler kv key put --binding SIGNING_SECRETS v2 "<new-secret>"
# After window:
wrangler kv key delete --binding SIGNING_SECRETS v1
wrangler kv key put --binding SIGNING_SECRETS v1 "<new-secret>"
wrangler kv key delete --binding SIGNING_SECRETS v2
```

---

## Anti-patterns

- **Signing only the path** — an attacker can replay any prior request to the same path indefinitely.
- **Comparing signatures with `===`** — JavaScript string equality is not constant-time; use `crypto.subtle.verify`.
- **Storing the signing secret in a Worker env var visible in the dashboard** — use `wrangler secret put` so it is encrypted at rest.
- **Not including the body hash** — body tampering goes undetected.

## Gotchas

- `request.arrayBuffer()` consumes the body stream; reconstruct the request before passing it to downstream handlers.
- `crypto.subtle` is available globally in Workers; no import needed.
- KV `get` returns `null` if the key does not exist — always filter nulls before iterating secrets.
- The `X-Signature` header format `t=<ts>,v1=<sig>` is intentionally similar to Stripe's webhook format for ecosystem familiarity.

## Verification

```bash
# Smoke-test: call the receiver directly without a signature — expect 401
curl -i https://receiver.workers.dev/api/data -X POST -d '{"hello":"world"}'
# HTTP/1.1 401 Missing signature

# Replay with an old timestamp — expect 401
curl -i https://receiver.workers.dev/api/data -X POST \
  -H 'X-Signature: t=1000000000,v1=deadbeef' -d '{"hello":"world"}'
# HTTP/1.1 401 Signature expired
```

## Related

- `workers-oauth2-client-credentials-d1-token-cache.md`
- `cloudflare-zero-trust-api-gateway-workers.md`
- Cloudflare Workers `crypto.subtle` reference

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://stripe.com/docs/webhooks/signatures
- NIST SP 800-107 — HMAC recommendations
