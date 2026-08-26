# Idempotency Key Pattern for Safe Request Retries with Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Clients retry failed or timed-out requests — payment charges, order submissions, email sends — and your API processes the same request twice, charging the customer twice or sending duplicate emails. You need request-level idempotency: the second (and subsequent) calls with the same idempotency key must return the same response as the first call without re-executing the side-effectful operation.

## Context

Idempotency keys are a standard API pattern (used by Stripe, Braintree, etc.). The server stores the response of the first successful call keyed by the idempotency key, and replays the stored response for subsequent calls. Workers KV is an ideal store: it is globally distributed (fast reads from any PoP), supports TTL for automatic expiry, and is available as a binding with no cold-start penalty. The challenge is handling concurrent first-calls for the same key — two requests arriving simultaneously must not both execute the operation.

## Solution

On receipt of a request with an `Idempotency-Key` header, compute a fingerprint, check KV for an existing response, replay it if present. If absent, set a "processing" sentinel in KV atomically (using `putIfAbsent` semantics via conditional logic), execute the operation, store the result, then return it. Concurrent duplicates see the sentinel and return 409 Conflict.

```typescript
// wrangler.toml excerpt
// [[kv_namespaces]]
//   binding = "IDEMPOTENCY"
//   id = "..."

export interface Env {
  IDEMPOTENCY: KVNamespace;
  DB:          D1Database;
}

// TTLs
const IDEMPOTENCY_TTL_SECONDS = 86_400;      // 24 hours — key stays valid for retries
const PROCESSING_TTL_SECONDS  = 30;           // 30 s sentinel TTL — auto-cleared if Worker crashes

// Status values stored in KV
type IdempotencyStatus = 'processing' | 'completed';

interface IdempotencyRecord {
  status:    IdempotencyStatus;
  fingerprint: string;
  createdAt: number;
  // Only present when status === 'completed'
  responseStatus?: number;
  responseBody?:   string;
  responseHeaders?: Record<string, string>;
}

// --- Fingerprinting ---

async function fingerprintRequest(request: Request, body: string): Promise<string> {
  // Fingerprint = hash(method + path + sorted-headers-of-interest + body)
  const components = [
    request.method,
    new URL(request.url).pathname,
    body,
    // Include content-type so that same body but different encoding is a different fingerprint
    request.headers.get('Content-Type') ?? '',
  ].join('|');

  const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(components));
  return Array.from(new Uint8Array(hashBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

// --- KV helpers ---

function idempotencyKVKey(idempotencyKey: string, userId: string): string {
  // Scope key to userId to prevent cross-user key collisions
  return `idempotency:${userId}:${idempotencyKey}`;
}

async function getRecord(kv: KVNamespace, key: string): Promise<IdempotencyRecord | null> {
  return kv.get<IdempotencyRecord>(key, 'json');
}

async function setProcessing(kv: KVNamespace, key: string, fingerprint: string): Promise<boolean> {
  // Emulate putIfAbsent: read first, then write only if absent.
  // Note: KV does not have native atomic CAS. This is a best-effort sentinel;
  // true atomic prevention requires a Durable Object for high-concurrency paths.
  const existing = await kv.get(key);
  if (existing !== null) return false;  // already set by another request

  const record: IdempotencyRecord = {
    status:      'processing',
    fingerprint,
    createdAt:   Date.now(),
  };
  await kv.put(key, JSON.stringify(record), { expirationTtl: PROCESSING_TTL_SECONDS });
  return true;
}

async function setCompleted(
  kv: KVNamespace,
  key: string,
  fingerprint: string,
  responseStatus: number,
  responseBody: string,
  responseHeaders: Record<string, string>
): Promise<void> {
  const record: IdempotencyRecord = {
    status:          'completed',
    fingerprint,
    createdAt:       Date.now(),
    responseStatus,
    responseBody,
    responseHeaders,
  };
  await kv.put(key, JSON.stringify(record), { expirationTtl: IDEMPOTENCY_TTL_SECONDS });
}

// --- Response serialisation ---

function serializableHeaders(response: Response): Record<string, string> {
  const headers: Record<string, string> = {};
  // Only replay safe, non-sensitive headers
  for (const name of ['Content-Type', 'X-Request-Id', 'X-Trace-Id']) {
    const v = response.headers.get(name);
    if (v) headers[name] = v;
  }
  return headers;
}

function replayResponse(record: IdempotencyRecord): Response {
  return new Response(record.responseBody, {
    status:  record.responseStatus!,
    headers: {
      ...record.responseHeaders,
      'Idempotent-Replayed': 'true',
    },
  });
}

// --- Core business operation (example: create order) ---

async function createOrder(
  db: D1Database,
  userId: string,
  body: Record<string, unknown>
): Promise<{ orderId: string; total: number }> {
  const orderId = crypto.randomUUID();
  await db
    .prepare('INSERT INTO orders (id, user_id, payload, created_at) VALUES (?1, ?2, ?3, ?4)')
    .bind(orderId, userId, JSON.stringify(body), new Date().toISOString())
    .run();
  return { orderId, total: (body.amount as number) ?? 0 };
}

// --- Main handler ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const userId = request.headers.get('X-User-Id');
    if (!userId) return new Response('Unauthorized', { status: 401 });

    const idempotencyKey = request.headers.get('Idempotency-Key');

    // Read body once — we need it for fingerprinting and for the operation
    const rawBody  = await request.text();
    const bodyJson = JSON.parse(rawBody) as Record<string, unknown>;

    if (!idempotencyKey) {
      // No idempotency key — process normally without deduplication
      const result = await createOrder(env.DB, userId, bodyJson);
      return Response.json(result, { status: 201 });
    }

    const kvKey      = idempotencyKVKey(idempotencyKey, userId);
    const fingerprint = await fingerprintRequest(request, rawBody);

    // 1. Check for existing record
    const existing = await getRecord(env.IDEMPOTENCY, kvKey);

    if (existing) {
      if (existing.fingerprint !== fingerprint) {
        // Same key, different request content — reject per Stripe convention
        return new Response(
          JSON.stringify({ error: 'Idempotency key reused with different request body' }),
          { status: 422, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (existing.status === 'processing') {
        // Concurrent duplicate — another instance is already handling this key
        return new Response(
          JSON.stringify({ error: 'Request is already being processed', retryAfterMs: 500 }),
          { status: 409, headers: { 'Content-Type': 'application/json', 'Retry-After': '1' } }
        );
      }

      if (existing.status === 'completed') {
        // Replay stored response
        return replayResponse(existing);
      }
    }

    // 2. Set processing sentinel
    const acquired = await setProcessing(env.IDEMPOTENCY, kvKey, fingerprint);
    if (!acquired) {
      // Lost the race — another Worker instance set the sentinel first
      return new Response(
        JSON.stringify({ error: 'Request is already being processed', retryAfterMs: 500 }),
        { status: 409, headers: { 'Content-Type': 'application/json', 'Retry-After': '1' } }
      );
    }

    // 3. Execute the operation
    let response: Response;
    try {
      const result = await createOrder(env.DB, userId, bodyJson);
      response = Response.json(result, { status: 201 });
    } catch (err) {
      // On failure, delete the sentinel so the client can retry with the same key
      await env.IDEMPOTENCY.delete(kvKey);
      throw err;  // Re-throw so Workers runtime returns a 500
    }

    // 4. Persist completed response
    const responseBody    = await response.clone().text();
    const responseHeaders = serializableHeaders(response);
    await setCompleted(
      env.IDEMPOTENCY,
      kvKey,
      fingerprint,
      response.status,
      responseBody,
      responseHeaders
    );

    return response;
  },
};

// --- High-concurrency variant: Durable Object as atomic lock ---
//
// For paths where KV's non-atomic sentinel is insufficient (e.g., payment processing
// where even a brief window of concurrent execution is unacceptable), replace the
// KV sentinel with a Durable Object lock:
//
// export class IdempotencyLockDO implements DurableObject {
//   private state: DurableObjectState;
//   constructor(state: DurableObjectState) { this.state = state; }
//
//   async fetch(request: Request): Promise<Response> {
//     const key = await request.text();
//     const existing = await this.state.storage.get<string>(key);
//     if (existing) return Response.json({ acquired: false, existing });
//     await this.state.storage.put(key, 'processing');
//     await this.state.storage.setAlarm(Date.now() + 30_000);  // auto-release
//     return Response.json({ acquired: true });
//   }
//
//   async alarm() { await this.state.storage.deleteAll(); }
// }
```

## Implementation Details

**Key scoping.** The KV key includes the `userId` to prevent one user from accidentally or maliciously replaying another user's idempotency key. The format `idempotency:{userId}:{idempotencyKey}` is human-readable for debugging.

**Request fingerprinting.** The fingerprint covers method, path, Content-Type, and body. If a client sends the same idempotency key with a different body, the server returns 422 — this follows the Stripe convention and catches client bugs.

**Processing sentinel TTL.** The sentinel expires after 30 seconds. If the Worker crashes mid-operation the sentinel auto-clears, allowing the client to retry. 30 s is generous; tune to your operation's p99 latency.

**Failure handling.** On operation failure the sentinel is explicitly deleted so the same idempotency key can be retried. Idempotency keys are single-use only on success — a failed operation can always be retried with the same key.

**Completed response TTL.** Completed records live for 24 hours. Clients should retry within this window. After expiry, the key is treated as new and the operation would re-execute.

**KV eventual consistency caveat.** KV `get` is eventually consistent within a region. Two concurrent requests from different PoPs could both see `null` and both proceed past the sentinel check. For truly atomic concurrency control, use the Durable Object variant in the comment block above.

## Anti-patterns

- **Accepting any string as an idempotency key without length/format validation.** Clients could craft arbitrarily long keys, causing KV key storage bloat. Validate that keys are UUIDs or bounded strings.
- **Replaying sensitive response fields (tokens, secrets).** Only replay safe fields. Store the full response body but strip secrets before saving.
- **Not deleting the sentinel on failure.** If the operation fails and the sentinel stays, the client's retry with the same key will return 409 forever until the sentinel TTL expires.
- **Sharing idempotency keys across users.** Without `userId` scoping, a malicious user could guess another user's idempotency key and replay their response.
- **Infinite TTL.** KV has no built-in garbage collection. Always set `expirationTtl` to prevent indefinite accumulation.

## Gotchas

- KV `put` with `expirationTtl` requires the value to be at least 60 seconds for the `expirationTtl` to take effect on some plans. Use `expiration` (absolute Unix timestamp) as a fallback.
- `request.text()` consumes the body stream. After calling it, `request.body` is null. Always read the body once and reuse the string.
- KV `get<T>(key, 'json')` returns `null` (not a typed empty value) when the key does not exist. Always null-check before accessing properties.
- The `clone()` call on the `Response` is necessary because `response.text()` consumes the response body; `clone()` creates a second readable stream.
- Workers KV is eventually consistent across regions. A request hitting a European PoP may not see a key written 50 ms ago from a US PoP. For global zero-duplicate guarantees, use a Durable Object.

## Verification

```bash
# First call — should process and return 201
curl -X POST https://api.example.com/orders \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: usr_123' \
  -H 'Idempotency-Key: idem-key-abc-123' \
  -d '{"amount": 99.99, "productId": "prod_456"}'

# Immediate retry — should return 201 with same body and Idempotent-Replayed: true
curl -X POST https://api.example.com/orders \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: usr_123' \
  -H 'Idempotency-Key: idem-key-abc-123' \
  -d '{"amount": 99.99, "productId": "prod_456"}'
# Expect: Idempotent-Replayed: true header in response

# Same key, different body — should return 422
curl -X POST https://api.example.com/orders \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: usr_123' \
  -H 'Idempotency-Key: idem-key-abc-123' \
  -d '{"amount": 199.99, "productId": "prod_456"}'
# Expect: 422 Unprocessable Entity

# Check KV record directly
wrangler kv:key get --namespace-id=<ID> "idempotency:usr_123:idem-key-abc-123"
```

## Related

- `workers-token-bucket-rate-limiter-do` — Durable Object as atomic lock (for high-concurrency variant)
- `workers-api-gateway-pattern` — gateway can inject idempotency key validation before forwarding
- `workers-compensating-transaction-pattern` — handling partial failures in multi-step operations

## Sources

- Stripe idempotency keys: https://stripe.com/docs/api/idempotent_requests
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- IETF Idempotency-Key header draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
