# Idempotency Key Patterns for Workers API Endpoints

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

A client posts a payment request to your Worker. The network drops before the response arrives. The client retries. Your Worker processes the payment twice, charging the customer double. You need a mechanism that recognises the retry and returns the original result without re-executing the side effect — even though the Worker is stateless and has no in-memory history.

---

## Context

Idempotency keys make non-idempotent operations safe to retry. The client generates a unique key (typically a UUID v4 or v7) and includes it in the request header (`Idempotency-Key: <uuid>`). The server stores the key alongside the result. On a retry with the same key, the server returns the stored result instead of re-executing.

In a Cloudflare Workers stack, the storage for idempotency records must be durable across Worker instances. The two natural choices are:

- **Workers KV**: Fast reads (~1 ms), global eventually-consistent propagation. Suitable when a short window of duplicate processing on concurrent retries is acceptable (e.g. idempotency windows of minutes).
- **D1**: Strongly consistent within the primary region. Use `INSERT OR IGNORE` to enforce uniqueness atomically. Suitable for financial operations, state machines, and any case where duplicate processing is never acceptable.

This article covers both patterns and their composition.

---

## Idempotency Key Contract

```
Client request header:
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

Server response headers (on first execution):
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

Server response headers (on replay):
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  Idempotency-Replayed: true
```

A key must be:
- Scoped to a user or tenant (never globally shared across users).
- Tied to the request method and path (key reuse across different operations must be rejected).
- Expired after a retention window (e.g. 24 hours for payments, 7 days for batch imports).

---

## D1-Backed Idempotency (Strongly Consistent)

### Schema

```sql
-- idempotency_records.sql
CREATE TABLE IF NOT EXISTS idempotency_records (
  -- Composite key: prevent a key from being reused across users or operations
  idem_key       TEXT    NOT NULL,
  user_id        TEXT    NOT NULL,
  operation      TEXT    NOT NULL,   -- e.g. "POST /payments"

  -- Stored response
  status_code    INTEGER NOT NULL,
  response_body  TEXT    NOT NULL,   -- JSON string
  response_hdrs  TEXT    NOT NULL DEFAULT '{}',  -- JSON of headers to replay

  -- Lifecycle
  created_at     TEXT    NOT NULL,
  expires_at     TEXT    NOT NULL,

  PRIMARY KEY (idem_key, user_id, operation)
);

CREATE INDEX IF NOT EXISTS idx_idem_expires ON idempotency_records (expires_at);
```

### Middleware

```typescript
// src/middleware/idempotency.ts
import type { Env } from '../env';

const IDEMPOTENCY_HEADER = 'Idempotency-Key';
const RETENTION_HOURS    = 24;

export interface IdempotencyContext {
  key:       string;
  userId:    string;
  operation: string;
}

/**
 * Check whether this request is a replay of an already-processed operation.
 * Returns the stored response if it is, or null if it is a new request.
 */
export async function checkIdempotency(
  env: Env,
  ctx: IdempotencyContext,
): Promise<Response | null> {
  const row = await env.DB.prepare(`
    SELECT status_code, response_body, response_hdrs
    FROM   idempotency_records
    WHERE  idem_key  = ?
      AND  user_id   = ?
      AND  operation = ?
      AND  expires_at > ?
  `).bind(
    ctx.key,
    ctx.userId,
    ctx.operation,
    new Date().toISOString(),
  ).first<{
    status_code: number;
    response_body: string;
    response_hdrs: string;
  }>();

  if (!row) return null;  // New request, proceed normally

  const headers = new Headers(JSON.parse(row.response_hdrs) as Record<string, string>);
  headers.set(IDEMPOTENCY_HEADER, ctx.key);
  headers.set('Idempotency-Replayed', 'true');
  headers.set('Content-Type', 'application/json');

  return new Response(row.response_body, {
    status:  row.status_code,
    headers,
  });
}

/**
 * Record the result of a freshly-executed operation.
 * Uses INSERT OR IGNORE so concurrent retries that race to insert cannot double-record.
 */
export async function recordIdempotency(
  env: Env,
  ctx: IdempotencyContext,
  response: Response,
): Promise<void> {
  const body    = await response.clone().text();
  const headers: Record<string, string> = {};
  response.headers.forEach((v, k) => { headers[k] = v; });

  const now     = new Date();
  const expires = new Date(now.getTime() + RETENTION_HOURS * 3_600_000);

  await env.DB.prepare(`
    INSERT OR IGNORE INTO idempotency_records
      (idem_key, user_id, operation, status_code, response_body, response_hdrs, created_at, expires_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    ctx.key,
    ctx.userId,
    ctx.operation,
    response.status,
    body,
    JSON.stringify(headers),
    now.toISOString(),
    expires.toISOString(),
  ).run();
}
```

### Usage in a Payment Handler

```typescript
// src/handlers/payments.ts
import { checkIdempotency, recordIdempotency } from '../middleware/idempotency';

export async function handleCreatePayment(
  request: Request,
  env: Env,
  userId: string,
): Promise<Response> {
  const key = request.headers.get('Idempotency-Key');
  if (!key) {
    return Response.json(
      { error: 'Idempotency-Key header is required for this operation' },
      { status: 422 },
    );
  }

  // Validate UUID format to prevent injection
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(key)) {
    return Response.json({ error: 'Invalid Idempotency-Key format' }, { status: 422 });
  }

  const idempCtx = { key, userId, operation: 'POST /payments' };

  // 1. Check for a stored result
  const replay = await checkIdempotency(env, idempCtx);
  if (replay) return replay;

  // 2. Execute the real operation
  const body = await request.json<{ amountCents: number; currency: string }>();
  const paymentId = crypto.randomUUID();

  // ... charge the customer, write to D1, etc.
  await env.DB.prepare(`
    INSERT INTO payments (id, user_id, amount_cents, currency, status, created_at)
    VALUES (?, ?, ?, ?, 'completed', ?)
  `).bind(paymentId, userId, body.amountCents, body.currency, new Date().toISOString()).run();

  const result = Response.json(
    { paymentId, status: 'completed', amountCents: body.amountCents },
    {
      status: 201,
      headers: { 'Idempotency-Key': key },
    },
  );

  // 3. Record the result before returning
  await recordIdempotency(env, idempCtx, result);
  return result;
}
```

---

## KV-Backed Idempotency (Fast, Eventually Consistent)

Use KV when:
- The operation is not financial (duplicate is unlikely to cause real harm).
- You need idempotency across all global PoPs simultaneously and can accept a short race window.
- The response body is small (KV values ≤ 25 MB, but keep under 1 KB for best performance).

```typescript
// src/middleware/idempotency-kv.ts

const TTL_SECONDS = 86_400; // 24 hours

interface StoredResult {
  statusCode: number;
  body: string;
  headers: Record<string, string>;
}

export async function kvCheckIdempotency(
  kv: KVNamespace,
  key: string,
  userId: string,
  operation: string,
): Promise<Response | null> {
  const kvKey = `idem:${userId}:${operation}:${key}`;
  const stored = await kv.get<StoredResult>(kvKey, 'json');
  if (!stored) return null;

  const headers = new Headers(stored.headers);
  headers.set('Idempotency-Replayed', 'true');

  return new Response(stored.body, {
    status:  stored.statusCode,
    headers,
  });
}

export async function kvRecordIdempotency(
  kv: KVNamespace,
  key: string,
  userId: string,
  operation: string,
  response: Response,
): Promise<void> {
  const body = await response.clone().text();
  const headers: Record<string, string> = {};
  response.headers.forEach((v, k) => { headers[k] = v; });

  const kvKey = `idem:${userId}:${operation}:${key}`;
  const stored: StoredResult = { statusCode: response.status, body, headers };

  await kv.put(kvKey, JSON.stringify(stored), { expirationTtl: TTL_SECONDS });
}
```

---

## Generating Stable Idempotency Keys (Client-Side)

Clients must generate a stable key that survives network retries. Use UUID v7 (time-ordered) for natural sorting and debuggability:

```typescript
// Client-side key generation (TypeScript)
function generateIdempotencyKey(): string {
  // UUID v4 fallback (widely supported)
  return crypto.randomUUID();
}

// For deterministic keys (same request content → same key)
async function deterministicKey(
  userId: string,
  operation: string,
  requestHash: string,
): Promise<string> {
  const input   = `${userId}:${operation}:${requestHash}`;
  const encoded = new TextEncoder().encode(input);
  const hash    = await crypto.subtle.digest('SHA-256', encoded);
  const hex     = [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
  // Format as UUID v5-style (truncate to 32 hex chars)
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20,32)}`;
}
```

---

## Handling In-Flight Requests (Locking)

Between checking for a record and writing the result, a second retry can arrive and find no record, causing duplicate execution. Mitigate with a status field or a D1 locking row:

```sql
-- Add a 'processing' status to the idempotency table
ALTER TABLE idempotency_records ADD COLUMN locked_at TEXT;

-- On first receipt: insert a 'pending' lock row
INSERT OR IGNORE INTO idempotency_records
  (idem_key, user_id, operation, status_code, response_body, response_hdrs, created_at, expires_at, locked_at)
VALUES (?, ?, ?, 0, '', '{}', ?, ?, ?);
-- If INSERT was ignored → concurrent retry; return 409 Conflict and ask client to retry in 1-2 s
-- If INSERT succeeded → proceed with real work, then UPDATE the row with the real result
```

For Workers, the window between check and lock is typically <1 ms for D1 in the same region, so the risk is low. For maximum safety, use a Durable Object to serialize access per idempotency key.

---

## Cleanup: Purging Expired Records

Run a scheduled Worker (Cron Trigger) to purge expired records and prevent table bloat:

```typescript
// src/scheduled/idempotency-cleanup.ts
export async function cleanupExpiredIdempotencyRecords(
  db: D1Database,
): Promise<void> {
  const result = await db.prepare(`
    DELETE FROM idempotency_records
    WHERE expires_at < ?
  `).bind(new Date().toISOString()).run();

  console.log(`Purged ${result.meta.changes} expired idempotency records`);
}
```

```toml
# wrangler.toml
[[triggers]]
crons = ["0 3 * * *"]   # 03:00 UTC daily
```

---

## Anti-patterns

- **Scoping keys globally (not per-user)**: A key from user A can replay an operation for user B if not scoped. Always namespace by user ID or tenant ID.
- **Using the key without tying it to the operation**: Key `abc123` for `POST /payments` should not replay for `POST /refunds`. Include the HTTP method + path in the composite key.
- **Not validating key format**: Free-form keys allow injection attacks. Enforce UUID format server-side.
- **Returning 200 on replay of a 201**: Replay responses must return the original status code, not a normalised 200. Clients may use the status to determine whether the resource was created or already existed.
- **Not recording the response before returning it**: Recording after returning means a crash between return and record leaves no record. Use a `ctx.waitUntil()` if the write is non-blocking, but prefer synchronous write before return for financial operations.
- **Storing large responses in the idempotency table**: Idempotency records are metadata. If the response body is >10 KB, store it in R2 and record only the R2 URL.

---

## Gotchas

- **KV race window**: Between reading KV and writing the result, two Workers can both see no record and both execute the operation. The window is typically 50–200 ms cross-PoP. For operations where duplicates are unacceptable, use D1 `INSERT OR IGNORE` which enforces atomicity at the database level.
- **D1 `INSERT OR IGNORE` vs. `ON CONFLICT DO NOTHING`**: Both are valid SQLite syntax; `INSERT OR IGNORE` is shorthand. On conflict, the affected-rows count is 0, not an error. Check `result.meta.changes` to detect whether the insert was fresh or ignored.
- **Response body consumption**: `response.text()` or `.json()` consumes the body stream. Always `.clone()` the response before reading its body if you need to return the original response to the client.
- **Clock skew on `expires_at`**: Different Workers may have slightly different wall-clock times. Use D1's `datetime('now')` in SQL comparisons where possible, or accept ±1 second skew in TTL enforcement.

---

## Verification

```bash
# 1. First request — expect 201
curl -X POST https://myapp.workers.dev/payments \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"amountCents":1000,"currency":"USD"}' \
  -i

# 2. Retry with the same key — expect 201 + Idempotency-Replayed: true
curl -X POST https://myapp.workers.dev/payments \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"amountCents":1000,"currency":"USD"}' \
  -i
# Verify: Idempotency-Replayed: true header present

# 3. Different key — expect a second payment created (new UUID)
curl -X POST https://myapp.workers.dev/payments \
  -H "Idempotency-Key: $(cat /proc/sys/kernel/random/uuid)" \
  -H "Content-Type: application/json" \
  -d '{"amountCents":1000,"currency":"USD"}' \
  -i

# 4. Verify DB has exactly 2 payment rows and 2 idempotency records
wrangler d1 execute MY_DB --command "SELECT COUNT(*) FROM payments;"
wrangler d1 execute MY_DB --command "SELECT COUNT(*) FROM idempotency_records;"
```

---

## Related

- `idempotency-design.md` — general idempotency patterns (provider-agnostic)
- `message-deduplication.md` — deduplication in message queues
- `event-sourcing-d1-append-only-store.md` — `idempotency_key UNIQUE` in event tables
- `outbox-pattern.md` — outbox + idempotency for reliable at-most-once side effects
- `retry-pattern.md` — client-side retry strategies and back-off
- `exactly-once-delivery.md` — exactly-once guarantees at the infrastructure level

---

## Sources

- Stripe idempotency keys guide — https://stripe.com/docs/api/idempotent_requests
- IETF draft: Idempotency-Key HTTP header — https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-04.txt
- Cloudflare Workers D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare Workers KV documentation — https://developers.cloudflare.com/kv/
- SQLite `INSERT OR IGNORE` semantics — https://www.sqlite.org/lang_insert.html
