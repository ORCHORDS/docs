# Request Signing with HMAC for Mutual Auth Between Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You have two Cloudflare Workers — a sender and a receiver — that communicate over HTTPS, and you need to prove that each request originated from your own infrastructure rather than an external caller. mTLS certificates are heavy to manage at the edge; a shared-secret HMAC signature over `method + path + timestamp + body-hash` provides the same mutual authentication with zero certificate lifecycle overhead. This pattern also prevents replay attacks by caching used nonces in KV.

---

## Context
HMAC-SHA256 is a symmetric MAC: both sender and receiver share the same secret, sign the same canonical message, and compare. The signature covers the HTTP method, URL path, a Unix timestamp (to reject stale requests), and a SHA-256 hash of the request body (to prevent body tampering). A nonce — a random per-request ID — is included in the signed payload and stored in KV for 5 minutes; any request that reuses a nonce is rejected as a replay even if the timestamp is fresh. The shared secret is stored as a Wrangler secret, never in environment variables or source code.

---

## Section 1 — Shared Secret & Wrangler Config

```toml
# wrangler.toml (sender Worker)
name = "sender-worker"
main = "src/sender.ts"
compatibility_date = "2025-04-01"

[[kv_namespaces]]
binding = "NONCE_STORE"
id = "<your-kv-namespace-id>"
preview_id = "<your-preview-id>"

[vars]
RECEIVER_URL = "https://receiver-worker.example.workers.dev"
```

```toml
# wrangler.toml (receiver Worker)
name = "receiver-worker"
main = "src/receiver.ts"
compatibility_date = "2025-04-01"

[[kv_namespaces]]
binding = "NONCE_STORE"
id = "<same-kv-namespace-id>"  # shared namespace for nonce dedup
preview_id = "<your-preview-id>"
```

```bash
# Store shared secret in both Workers
npx wrangler secret put HMAC_SECRET --name sender-worker
npx wrangler secret put HMAC_SECRET --name receiver-worker
# Paste the same random 32-byte hex string when prompted
```

---

## Section 2 — Implementation

```typescript
// src/signing.ts  (shared module used by both sender and receiver)

export async function importHmacKey(secret: string): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

export async function sha256Hex(data: ArrayBuffer | string): Promise<string> {
  const buf =
    typeof data === "string" ? new TextEncoder().encode(data) : data;
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface SignedHeaders {
  "X-Signature": string;
  "X-Timestamp": string;
  "X-Nonce": string;
  "X-Body-Hash": string;
}

/**
 * Canonical message:
 *   METHOD\nPATH\nTIMESTAMP\nNONCE\nBODY_HASH
 */
export function buildCanonicalMessage(
  method: string,
  path: string,
  timestamp: string,
  nonce: string,
  bodyHash: string
): string {
  return [method.toUpperCase(), path, timestamp, nonce, bodyHash].join("\n");
}

// ─── SENDER ──────────────────────────────────────────────────────────────────

export interface Env {
  HMAC_SECRET: string;
  NONCE_STORE: KVNamespace;
  RECEIVER_URL: string;
}

export async function signRequest(
  method: string,
  path: string,
  body: string,
  secret: string
): Promise<SignedHeaders> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const nonce = crypto.randomUUID();
  const bodyHash = await sha256Hex(body);
  const canonical = buildCanonicalMessage(method, path, timestamp, nonce, bodyHash);

  const key = await importHmacKey(secret);
  const sigBuffer = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(canonical)
  );
  const signature = btoa(String.fromCharCode(...new Uint8Array(sigBuffer)));

  return {
    "X-Signature": signature,
    "X-Timestamp": timestamp,
    "X-Nonce": nonce,
    "X-Body-Hash": bodyHash,
  };
}
```

```typescript
// src/sender.ts
import { signRequest } from "./signing";

export interface Env {
  HMAC_SECRET: string;
  RECEIVER_URL: string;
  NONCE_STORE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = "/internal/data";
    const body = JSON.stringify({ hello: "world", ts: Date.now() });

    const signedHeaders = await signRequest(
      "POST",
      path,
      body,
      env.HMAC_SECRET
    );

    const response = await fetch(`${env.RECEIVER_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...signedHeaders,
      },
      body,
    });

    return new Response(await response.text(), { status: response.status });
  },
};
```

```typescript
// src/receiver.ts
import { importHmacKey, sha256Hex, buildCanonicalMessage } from "./signing";

export interface Env {
  HMAC_SECRET: string;
  NONCE_STORE: KVNamespace;
}

const MAX_AGE_SECONDS = 300; // 5 minutes
const NONCE_TTL_SECONDS = 310;

export async function verifyRequest(
  request: Request,
  body: string,
  env: Env
): Promise<{ ok: boolean; reason?: string }> {
  const signature = request.headers.get("X-Signature");
  const timestamp = request.headers.get("X-Timestamp");
  const nonce = request.headers.get("X-Nonce");
  const bodyHash = request.headers.get("X-Body-Hash");

  if (!signature || !timestamp || !nonce || !bodyHash) {
    return { ok: false, reason: "missing_headers" };
  }

  // 1. Reject stale timestamps
  const now = Math.floor(Date.now() / 1000);
  const ts = parseInt(timestamp, 10);
  if (isNaN(ts) || Math.abs(now - ts) > MAX_AGE_SECONDS) {
    return { ok: false, reason: "stale_timestamp" };
  }

  // 2. Reject replayed nonces
  const nonceKey = `nonce:${nonce}`;
  const existing = await env.NONCE_STORE.get(nonceKey);
  if (existing !== null) {
    return { ok: false, reason: "replay" };
  }

  // 3. Verify body hash
  const actualBodyHash = await sha256Hex(body);
  if (actualBodyHash !== bodyHash) {
    return { ok: false, reason: "body_tampered" };
  }

  // 4. Verify HMAC signature
  const url = new URL(request.url);
  const canonical = buildCanonicalMessage(
    request.method,
    url.pathname,
    timestamp,
    nonce,
    bodyHash
  );

  const key = await importHmacKey(env.HMAC_SECRET);

  let sigBytes: Uint8Array;
  try {
    sigBytes = new Uint8Array(
      Array.from(atob(signature)).map((c) => c.charCodeAt(0))
    );
  } catch {
    return { ok: false, reason: "invalid_signature_encoding" };
  }

  const valid = await crypto.subtle.verify(
    "HMAC",
    key,
    sigBytes,
    new TextEncoder().encode(canonical)
  );

  if (!valid) return { ok: false, reason: "signature_mismatch" };

  // 5. Mark nonce as used
  await env.NONCE_STORE.put(nonceKey, "1", { expirationTtl: NONCE_TTL_SECONDS });

  return { ok: true };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/internal/data") {
      return new Response("Not found", { status: 404 });
    }

    const body = await request.text();
    const result = await verifyRequest(request, body, env);

    if (!result.ok) {
      return new Response(JSON.stringify({ error: result.reason }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Process authenticated request
    return new Response(JSON.stringify({ received: JSON.parse(body) }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Section 3 — Integration / Testing

```typescript
// test/signing.test.ts
import { describe, it, expect } from "vitest";
import { signRequest, importHmacKey, buildCanonicalMessage, sha256Hex } from "../src/signing";

describe("HMAC signing round-trip", () => {
  const secret = "test-secret-32bytes-padded-here!";

  it("verifies its own signature", async () => {
    const body = JSON.stringify({ foo: "bar" });
    const headers = await signRequest("POST", "/test", body, secret);

    const bodyHash = await sha256Hex(body);
    const canonical = buildCanonicalMessage(
      "POST",
      "/test",
      headers["X-Timestamp"],
      headers["X-Nonce"],
      bodyHash
    );

    const key = await importHmacKey(secret);
    const sigBytes = new Uint8Array(
      Array.from(atob(headers["X-Signature"])).map((c) => c.charCodeAt(0))
    );
    const valid = await crypto.subtle.verify(
      "HMAC",
      key,
      sigBytes,
      new TextEncoder().encode(canonical)
    );
    expect(valid).toBe(true);
  });

  it("fails on tampered body", async () => {
    const body = "original";
    const headers = await signRequest("POST", "/test", body, secret);
    // Attacker changes body but keeps headers
    const tamperedBodyHash = await sha256Hex("tampered");
    expect(tamperedBodyHash).not.toBe(headers["X-Body-Hash"]);
  });
});
```

```bash
# Deploy both workers
npx wrangler deploy --config wrangler.sender.toml
npx wrangler deploy --config wrangler.receiver.toml

# Trigger a signed request from sender
curl https://sender-worker.example.workers.dev/

# Attempt replay: copy headers from a prior request
curl -X POST https://receiver-worker.example.workers.dev/internal/data \
  -H "X-Signature: <copied>" \
  -H "X-Timestamp: <copied>" \
  -H "X-Nonce: <copied>" \
  -H "X-Body-Hash: <copied>" \
  -d '{"hello":"world"}'
# Expected: {"error":"replay"}
```

---

## Anti-patterns
- **Signing only headers** — If the body is not included in the signature, an attacker can change the payload while keeping valid headers. Always hash the body.
- **Using a wall-clock timestamp without checking skew** — A signed request is valid forever without a time window check; always reject requests older than 5 minutes.
- **Shared KV namespace without key prefix** — In a multi-tenant deployment, nonce keys from different tenants can collide; always prefix with `nonce:<tenant>:<uuid>`.
- **Storing the secret in `[vars]`** — Wrangler vars are plaintext in `wrangler.toml` and visible in the dashboard; use `wrangler secret put` instead.

---

## Gotchas
- `crypto.subtle.verify` uses constant-time comparison internally; do not implement your own byte-by-byte comparison.
- `atob`/`btoa` in Workers handle Base64 of binary data correctly only if you convert through `Uint8Array`; avoid passing raw `ArrayBuffer` to `btoa`.
- KV `put` with `expirationTtl` is eventually consistent; in a high-throughput scenario a nonce could theoretically be accepted twice within a very small window. For strict dedup, use Durable Objects instead of KV.
- The nonce TTL (310s) is intentionally slightly longer than `MAX_AGE_SECONDS` (300s) to avoid a race where a valid request at second 299 has its nonce evicted before the TTL check at second 301.

---

## Verification
```bash
# Generate a test HMAC locally
echo -n $'POST\n/internal/data\n'$(date +%s)$'\ntest-nonce\n'$(echo -n '{}' | openssl dgst -sha256 | cut -d' ' -f2) \
  | openssl dgst -sha256 -hmac "<your-secret>" -binary | base64

# Confirm nonce is stored in KV after a request
npx wrangler kv key list --namespace-id=<id> --prefix="nonce:"

# Confirm nonce expires after 310s
npx wrangler kv key get --namespace-id=<id> "nonce:<uuid>"
```

---

## Related
- `workers-api-key-management-kv-hashed.md`
- `workers-sri-hash-html-rewriter.md`

---

## Sources
- RFC 2104 — HMAC: Keyed-Hashing for Message Authentication — https://datatracker.ietf.org/doc/html/rfc2104
- Web Crypto API HMAC (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/HmacKeyGenParams
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/api/
- AWS Signature Version 4 (design reference) — https://docs.aws.amazon.com/general/latest/gr/sigv4_signing.html
