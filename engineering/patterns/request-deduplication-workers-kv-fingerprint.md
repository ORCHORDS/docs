# Request Deduplication at the Edge with KV Fingerprints

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Clients retry idempotent-by-intent requests (payment submissions, order placements, webhook deliveries) and your origin processes duplicates, causing double-charges or duplicate records. You need edge-level deduplication that intercepts retries before they reach origin, with sub-millisecond overhead on the hot path.

## Context

KV is the right primitive here: globally replicated reads (p99 < 5 ms on cache hit), simple TTL-based expiry, and atomic `putIfMatch` for the in-flight marker. The pattern has two layers:

1. **Result cache** — store the first successful response under the request fingerprint with a 60-second TTL. Subsequent identical requests return the cached response immediately.
2. **In-flight marker** — a short-lived KV key written *before* processing begins. Concurrent identical requests read this marker and wait (or return 202), preventing the thundering-herd problem where multiple requests race to origin before any result is cached.

## Deduplication Worker

```typescript
// dedup-worker/index.ts
import { sha256Hex } from './crypto';

const RESULT_TTL_S  = 60;   // cache successful responses for 60 s
const INFLIGHT_TTL_S = 10;  // in-flight marker expires after 10 s
const POLL_INTERVAL_MS = 200;
const POLL_MAX_MS = 8_000;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const fingerprint = await buildFingerprint(request.clone());
    const resultKey   = `result:${fingerprint}`;
    const inflightKey = `inflight:${fingerprint}`;

    // 1. Check for a cached result (happy path for retries)
    const cached = await env.DEDUP_KV.get(resultKey, { type: 'text' });
    if (cached !== null) {
      const { status, headers, body } = JSON.parse(cached);
      return new Response(body, { status, headers });
    }

    // 2. Check for an in-flight marker (thundering herd guard)
    const inflight = await env.DEDUP_KV.get(inflightKey);
    if (inflight !== null) {
      // Another instance is processing — poll until result appears
      return pollForResult(env, resultKey);
    }

    // 3. Write the in-flight marker (best-effort; race is acceptable here)
    await env.DEDUP_KV.put(inflightKey, '1', { expirationTtl: INFLIGHT_TTL_S });

    try {
      // 4. Forward to origin
      const originResponse = await forwardToOrigin(request, env);
      const bodyText = await originResponse.text();

      if (originResponse.ok) {
        // 5. Cache the successful result
        const entry = JSON.stringify({
          status:  originResponse.status,
          headers: Object.fromEntries(originResponse.headers),
          body:    bodyText,
        });
        await env.DEDUP_KV.put(resultKey, entry, { expirationTtl: RESULT_TTL_S });
      }

      return new Response(bodyText, {
        status:  originResponse.status,
        headers: originResponse.headers,
      });
    } finally {
      // 6. Remove in-flight marker regardless of outcome
      await env.DEDUP_KV.delete(inflightKey);
    }
  },
};

// Stable fingerprint: method + normalised URL + SHA-256 of body
async function buildFingerprint(request: Request): Promise<string> {
  const method = request.method.toUpperCase();
  const url    = normaliseUrl(new URL(request.url));
  const body   = request.method !== 'GET' && request.method !== 'HEAD'
    ? await request.text()
    : '';
  const bodyHash = await sha256Hex(body);
  return sha256Hex(`${method}:${url}:${bodyHash}`);
}

function normaliseUrl(url: URL): string {
  // Sort query params so ?b=2&a=1 and ?a=1&b=2 produce the same fingerprint
  url.searchParams.sort();
  url.hash = '';   // fragments are client-only, never sent to origin
  return url.toString();
}

async function pollForResult(env: Env, resultKey: string): Promise<Response> {
  const deadline = Date.now() + POLL_MAX_MS;
  while (Date.now() < deadline) {
    await sleep(POLL_INTERVAL_MS);
    const cached = await env.DEDUP_KV.get(resultKey, { type: 'text' });
    if (cached !== null) {
      const { status, headers, body } = JSON.parse(cached);
      return new Response(body, { status, headers });
    }
  }
  // Timeout — forward anyway as a safety net
  return new Response('Dedup timeout', { status: 503 });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function forwardToOrigin(request: Request, env: Env): Promise<Response> {
  const originUrl = new URL(request.url);
  originUrl.hostname = env.ORIGIN_HOST;
  return fetch(new Request(originUrl.toString(), request));
}

// crypto.ts
export async function sha256Hex(input: string): Promise<string> {
  const data   = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

## Wrangler Binding Configuration

```jsonc
{
  "name": "dedup-worker",
  "kv_namespaces": [
    { "binding": "DEDUP_KV", "id": "<kv-namespace-id>" }
  ],
  "vars": {
    "ORIGIN_HOST": "origin.example.com"
  }
}
```

## Fingerprint Key Design Decisions

| Component | Rationale |
|---|---|
| `method` | POST and GET to the same URL are semantically different |
| `normaliseUrl()` with sorted params | Prevents `?a=1&b=2` vs `?b=2&a=1` producing different fingerprints |
| `sha256(body)` | Avoids storing raw bodies in the fingerprint; safe for large payloads |
| Outer `sha256` of the concatenated string | Fixed-length KV key regardless of URL length |

## Anti-patterns

- **Fingerprinting non-idempotent requests** — only deduplicate requests your domain declares idempotent (e.g., via `Idempotency-Key` header). Blindly deduplicating `POST /transfer` without a client key causes legitimate distinct requests to be collapsed.
- **Caching error responses** — only cache `originResponse.ok` (2xx). A transient 500 cached for 60 s blocks legitimate retries.
- **Omitting the in-flight marker** — without it, 50 simultaneous identical requests all reach origin before the first result is cached.
- **Using URL alone as the key** — two different bodies to the same endpoint are different requests; always include the body hash.

## Gotchas

- KV `put` is **eventually consistent** across regions; the in-flight marker may not be visible to a request landing in a different PoP within the first ~100 ms. This is acceptable — the in-flight guard is a best-effort herd reducer, not a strict mutex. D1 or a Durable Object is required for strict exactly-once semantics.
- `request.clone()` before calling `buildFingerprint` is mandatory because reading the body stream is destructive.
- The `finally` block deletes the in-flight marker even when origin returns an error, so the next retry goes through rather than hitting a stale `inflight:` key.
- KV `expirationTtl` minimum is 60 seconds for persistent namespaces; use a preview namespace for lower TTLs in testing.

## Verification

```bash
# Send the same request 5 times concurrently
for i in $(seq 1 5); do
  curl -s -X POST https://worker.example.com/checkout \
    -H 'Content-Type: application/json' \
    -d '{"order_id":"ord-999"}' &
done
wait

# Inspect the KV namespace for the result key
wrangler kv key list --namespace-id <id> | grep 'result:'

# Confirm origin received exactly 1 request (check origin logs / D1 orders table)
wrangler d1 execute orders-db \
  --command "SELECT COUNT(*) FROM orders WHERE order_id='ord-999'"
```

## Related

- `competing-consumers-workers-queues-concurrency.md`
- `rate-limit-sliding-window-durable-objects-workers.md`
- Cloudflare KV — Expiring Keys
- Web Crypto API — `SubtleCrypto.digest`

## Sources

- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/concepts/how-kv-works/
