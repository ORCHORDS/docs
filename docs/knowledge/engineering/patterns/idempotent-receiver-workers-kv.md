# Idempotent Receiver Pattern with Workers and KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A client retries a payment, order creation, or any mutating request after a network timeout. Without idempotency guards the server processes the mutation twice, causing duplicate charges or duplicate records. You need the server to detect duplicates and replay the original response without re-executing side effects.

## Context

Workers are stateless, so idempotency state must live outside the isolate. Workers KV is a natural fit: it is globally readable after a write propagates, cheap to query, and supports TTL-based expiry so old records are automatically collected.

The pattern:
1. Client supplies an `Idempotency-Key` header (UUID or content hash).
2. Worker checks KV for a cached result under that key.
3. On a miss the Worker executes the mutation, stores the serialised response in KV, returns `201 Created`.
4. On a hit the Worker reads the cached response and returns it with `200 OK` (replay signal).

---

## Section 1 — Request Hashing and Key Derivation

```typescript
// idempotency-key.ts
export async function deriveKey(request: Request): Promise<string> {
  const explicit = request.headers.get('Idempotency-Key');
  if (explicit) return `ik:${explicit}`;

  const body = await request.clone().arrayBuffer();
  const input = new TextEncoder().encode(`${request.method}:${request.url}:${body.byteLength}`);
  const combined = new Uint8Array(input.length + body.byteLength);
  combined.set(input, 0);
  combined.set(new Uint8Array(body), input.length);
  const digest = await crypto.subtle.digest('SHA-256', combined);
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return `ik:body:${hex}`;
}
```

## Section 2 — KV Cache Store

```typescript
// idempotency-store.ts
export interface CachedResponse {
  statusCode: number;
  headers: Record<string, string>;
  body: string; // base64-encoded
  createdAtMs: number;
}

const TTL_SECONDS = 86_400;

export async function getCached(
  kv: KVNamespace,
  key: string,
): Promise<CachedResponse | null> {
  const raw = await kv.get(key);
  if (!raw) return null;
  return JSON.parse(raw) as CachedResponse;
}

export async function putCached(
  kv: KVNamespace,
  key: string,
  response: Response,
): Promise<void> {
  const bodyBytes = await response.clone().arrayBuffer();
  const body = btoa(String.fromCharCode(...new Uint8Array(bodyBytes)));
  const headers: Record<string, string> = {};
  response.headers.forEach((v, k) => {
    if (!['content-encoding', 'transfer-encoding', 'connection'].includes(k)) {
      headers[k] = v;
    }
  });
  const cached: CachedResponse = {
    statusCode: response.status,
    headers,
    body,
    createdAtMs: Date.now(),
  };
  await kv.put(key, JSON.stringify(cached), { expirationTtl: TTL_SECONDS });
}

export function replayResponse(cached: CachedResponse): Response {
  const bodyBytes = Uint8Array.from(atob(cached.body), (c) => c.charCodeAt(0));
  return new Response(bodyBytes, {
    status: 200,
    headers: {
      ...cached.headers,
      'X-Idempotent-Replayed': 'true',
      'X-Original-Status': String(cached.statusCode),
    },
  });
}
```

## Section 3 — Worker Entry Point

```typescript
// worker.ts
import { deriveKey } from './idempotency-key';
import { getCached, putCached, replayResponse } from './idempotency-store';

export interface Env {
  IDEMPOTENCY_KV: KVNamespace;
}

async function executeMutation(request: Request): Promise<Response> {
  const body = await request.json();
  return Response.json(
    { id: crypto.randomUUID(), received: body, createdAt: new Date().toISOString() },
    { status: 201 },
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!['POST', 'PUT', 'PATCH'].includes(request.method)) {
      return new Response('Method not allowed', { status: 405 });
    }

    const iKey = await deriveKey(request);

    const cached = await getCached(env.IDEMPOTENCY_KV, iKey);
    if (cached) return replayResponse(cached);

    const mutationResponse = await executeMutation(request.clone());

    if (mutationResponse.status < 500) {
      await putCached(env.IDEMPOTENCY_KV, iKey, mutationResponse.clone());
    }

    return mutationResponse;
  },
};
```

## Section 4 — Client-Side Contract

```typescript
// client.ts
async function createOrderIdempotent(
  payload: unknown,
  idempotencyKey: string,
): Promise<{ replayed: boolean; data: unknown }> {
  const res = await fetch('https://api.example.com/orders', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const replayed = res.headers.get('X-Idempotent-Replayed') === 'true';
  return { replayed, data: await res.json() };
}

const KEY = crypto.randomUUID();
const result = await createOrderIdempotent({ product: 'widget', qty: 2 }, KEY);
console.log(result.replayed ? 'replayed' : 'created', result.data);
```

## Anti-patterns

- Using the request URL alone as the idempotency key: a `POST /orders` URL is not unique across logical operations.
- Not storing failed responses: a retry after a 4xx will re-execute the mutation.
- Infinite TTL: expense and no cleanup; expire after the client's maximum retry window.
- Hashing a streaming body without buffering: call `request.clone().arrayBuffer()` once.

## Gotchas

- KV is eventually consistent; during the ~60 s propagation window a read on a different PoP may miss the cached result. Use a DO-based in-flight lock for strictly-once execution.
- `expirationTtl` must be >= 60 seconds (Workers KV minimum).
- `btoa`/`atob` handle Latin-1 only; encode to `Uint8Array` for binary correctness as shown above.
- Storing large response bodies (>25 MB) in KV will fail; store metadata only and re-fetch on replay.

## Verification

```bash
KEY=$(uuidgen)
for i in 1 2; do
  echo "--- Attempt $i ---"
  curl -s -X POST https://your-worker.example.com/orders \
    -H 'Content-Type: application/json' \
    -H "Idempotency-Key: $KEY" \
    -d '{"product":"widget","qty":2}' \
    -D - | grep -E '(HTTP|X-Idempotent|X-Original|{)'
done
# Attempt 1: HTTP/2 201
# Attempt 2: HTTP/2 200, X-Idempotent-Replayed: true
```

## Related

- documentation/docs/policies/patterns/event-sourcing-d1-append-only-log.md
- documentation/docs/policies/patterns/two-phase-commit-workers-d1-kv.md
- Stripe idempotency keys documentation

## Sources

- https://developers.cloudflare.com/kv/
- https://stripe.com/docs/api/idempotent_requests
- https://www.rfc-editor.org/rfc/rfc8252
