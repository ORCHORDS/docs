# API Request Replay Prevention with Nonce Storage in D1 Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

An attacker captures a valid signed API request (webhook delivery, payment instruction, signed action token) and replays it seconds or minutes later. HMAC or JWT signature verification passes because the signature is still valid — but the operation executes twice. You need a stateful layer that rejects duplicate requests even when the cryptographic signature is correct.

This is distinct from idempotency keys (which deduplicate *client retries*) — replay prevention rejects *adversarial reuse* of a captured request.

---

## Context

The standard pattern is:

1. Client embeds a **nonce** (random, single-use value) and a **timestamp** in each request.
2. Server verifies the signature covers the nonce and timestamp.
3. Server checks the nonce has not been seen before and the timestamp is within the allowed window.
4. Server stores the nonce in D1 with a TTL equal to the replay window (e.g. 5 minutes).

Cloudflare D1 (SQLite at the edge) is well suited for this because:
- It is co-located with Workers in the same datacenter.
- Writes are synchronous from the Worker's perspective.
- SQLite's serializable isolation prevents concurrent Workers from accepting the same nonce simultaneously.
- D1 row-level TTL via a `expires_at` column allows inexpensive cleanup.

---

## Schema Setup

```sql
-- migrations/0001_nonces.sql
CREATE TABLE IF NOT EXISTS used_nonces (
  nonce     TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  used_at   INTEGER NOT NULL,  -- Unix seconds
  expires_at INTEGER NOT NULL  -- Unix seconds
);

CREATE INDEX IF NOT EXISTS idx_nonces_expires ON used_nonces (expires_at);
```

Apply with:

```bash
wrangler d1 execute MY_DB --file migrations/0001_nonces.sql
```

---

## Nonce Validation Middleware

```typescript
export interface Env {
  MY_DB: D1Database;
  HMAC_SECRET: string;
}

const REPLAY_WINDOW_SECONDS = 300; // 5 minutes

interface SignedRequest {
  nonce: string;       // UUID v4 or 32-byte hex
  timestamp: number;   // Unix seconds
  client_id: string;
  payload: unknown;
  signature: string;   // HMAC-SHA256 hex over canonical string
}

async function verifyAndConsumeNonce(
  db: D1Database,
  clientId: string,
  nonce: string,
  timestamp: number
): Promise<{ ok: boolean; reason?: string }> {
  const now = Math.floor(Date.now() / 1000);

  // 1. Timestamp window check
  if (Math.abs(now - timestamp) > REPLAY_WINDOW_SECONDS) {
    return { ok: false, reason: "timestamp_out_of_window" };
  }

  // 2. Nonce format validation (UUID v4)
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(nonce)) {
    return { ok: false, reason: "invalid_nonce_format" };
  }

  const expiresAt = now + REPLAY_WINDOW_SECONDS;

  // 3. Atomic insert — fails if nonce already exists (PRIMARY KEY constraint)
  try {
    await db
      .prepare(
        `INSERT INTO used_nonces (nonce, client_id, used_at, expires_at)
         VALUES (?, ?, ?, ?)`
      )
      .bind(nonce, clientId, now, expiresAt)
      .run();
  } catch (err: unknown) {
    // D1 throws on UNIQUE constraint violation
    if (err instanceof Error && err.message.includes("UNIQUE constraint")) {
      return { ok: false, reason: "nonce_already_used" };
    }
    throw err; // unexpected DB error — let it propagate
  }

  return { ok: true };
}
```

---

## HMAC Signature Verification

```typescript
async function verifyHmacSignature(
  secret: string,
  body: SignedRequest
): Promise<boolean> {
  const encoder = new TextEncoder();

  // Canonical string: deterministic serialization of the signed fields
  const canonical = [
    body.client_id,
    body.nonce,
    String(body.timestamp),
    JSON.stringify(body.payload),
  ].join("\n");

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  const signatureBytes = hexToBytes(body.signature);
  return crypto.subtle.verify("HMAC", key, signatureBytes, encoder.encode(canonical));
}

function hexToBytes(hex: string): Uint8Array {
  const arr = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    arr[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return arr;
}
```

---

## Full Request Handler

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let body: SignedRequest;
    try {
      body = await request.json<SignedRequest>();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    // Step 1: verify HMAC signature (covers nonce + timestamp + payload)
    const sigOk = await verifyHmacSignature(env.HMAC_SECRET, body);
    if (!sigOk) {
      return new Response("Invalid signature", { status: 401 });
    }

    // Step 2: check and consume nonce (stateful replay guard)
    const nonceResult = await verifyAndConsumeNonce(
      env.MY_DB,
      body.client_id,
      body.nonce,
      body.timestamp
    );
    if (!nonceResult.ok) {
      return new Response(
        JSON.stringify({ error: nonceResult.reason }),
        { status: 409, headers: { "Content-Type": "application/json" } }
      );
    }

    // Step 3: process the verified, replay-safe request
    return processPayload(body.payload);
  },
};
```

---

## Nonce Cleanup Cron Trigger

D1 does not auto-expire rows. Run a scheduled cleanup to prevent unbounded table growth.

```typescript
// Cron Trigger: "*/10 * * * *" (every 10 minutes)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Math.floor(Date.now() / 1000);
    const result = await env.MY_DB
      .prepare("DELETE FROM used_nonces WHERE expires_at < ?")
      .bind(cutoff)
      .run();
    console.log(`Cleaned up ${result.meta.changes} expired nonces`);
  },
};
```

Add to `wrangler.toml`:

```toml
[triggers]
crons = ["*/10 * * * *"]
```

---

## Anti-patterns

- **Storing nonces in KV with TTL only** — KV eventual consistency means two Workers in different PoPs can both accept the same nonce within the replication window. Use D1 (strongly consistent writes) for the nonce store.
- **Checking nonce existence before insert** — SELECT-then-INSERT has a TOCTOU race. The atomic INSERT with UNIQUE constraint is the correct primitive.
- **Wide replay windows** — a 60-minute window stores 60× more nonces and gives attackers more time. Use the smallest window that accommodates legitimate clock skew (≤ 5 minutes).
- **Not including the nonce in the signed payload** — if the nonce is outside the signature, an attacker can substitute a fresh nonce on a captured request.
- **Not scoping nonces to a client_id** — without scoping, a nonce collision across different clients produces confusing rejections and can be exploited for denial-of-service.

---

## Gotchas

- D1 is regionally replicated but write-primary reads may be slightly stale. For the nonce INSERT, always use the primary write path — D1 routes inserts to the primary automatically.
- Concurrent bursts can produce serialization errors on D1. Wrap the `verifyAndConsumeNonce` call in a retry loop for transient `SQLITE_BUSY` errors, but cap at 2 retries to avoid masking actual replay attempts.
- The `request.json()` call consumes the body stream. Clone the request or cache the body text if you need it for both HMAC verification and downstream processing.
- D1's free tier has row write limits; a high-traffic API should monitor D1 write metrics and size the replay window accordingly.

---

## Verification

```typescript
// test: same nonce rejected on second request
const nonce = crypto.randomUUID();
const timestamp = Math.floor(Date.now() / 1000);
const payload = { amount: 100 };

const makeBody = (): SignedRequest => ({
  client_id: "test-client",
  nonce,
  timestamp,
  payload,
  signature: signHmac(secret, "test-client", nonce, timestamp, payload),
});

const r1 = await worker.fetch("/api/action", { method: "POST", body: JSON.stringify(makeBody()) });
assert(r1.status === 200, "first request should succeed");

const r2 = await worker.fetch("/api/action", { method: "POST", body: JSON.stringify(makeBody()) });
assert(r2.status === 409, "replay should be rejected");
const body2 = await r2.json();
assert(body2.error === "nonce_already_used");
```

---

## Related

- `hmac-webhook-signature-rotation-zero-downtime.md`
- `webhook-signature-verification-hmac.md`
- `saml-replay-attack-prevention.md`
- `idempotency-one-time-secret-replay.md`
- `sql-injection-prevention-d1-workers.md`
- `rate-limiting-per-user-d1-durable-objects.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- NIST SP 800-63B §5.1.4 — nonce requirements for authentication protocols
- RFC 4122 — UUID v4 structure
- Web Crypto API HMAC — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
