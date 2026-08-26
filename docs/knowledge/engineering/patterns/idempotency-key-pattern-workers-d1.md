# idempotency-key-pattern-workers-d1

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

A mobile user taps "Subscribe" on a slow connection. The request
times out on the client side. The client retries. The server
processes both requests. The user is charged twice. Their card
statement shows two line items. Support tickets spike. Refunding
requires manual intervention.

Same failure mode: a Worker crashes after the D1 write succeeds but
before the HTTP 200 is sent. The client sees a network error and
retries. The write runs twice.

## Context

HTTP is not transactional end-to-end. The network can drop a
response after the server commits. Mobile clients retry. Payment
processors recommend (or require) idempotency keys on all
mutation endpoints. D1's SQL `ON CONFLICT DO NOTHING` + a
UUID key stored by the client gives exactly-once semantics across
retries without distributed locks.

The pattern has two sides:
1. **Client generates a UUID before the first attempt** and sends
   it on every retry as `Idempotency-Key: <uuid>`.
2. **Server records the UUID + result on first success** and returns
   the cached result on subsequent attempts.

## Client-Side Key Generation

Generate the key before any network call. Persist it to local
storage so it survives app restarts during a retry window.

```ts
// mobile / browser client
function getOrCreateIdempotencyKey(operationId: string): string {
  const storageKey = `idem:${operationId}`;
  let key = localStorage.getItem(storageKey);
  if (!key) {
    key = crypto.randomUUID();
    localStorage.setItem(storageKey, key);
  }
  return key;
}

async function subscribe(planId: string): Promise<SubscribeResult> {
  const idempKey = getOrCreateIdempotencyKey(`subscribe:${planId}`);

  const res = await fetch('/v1/subscriptions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempKey,
    },
    body: JSON.stringify({ plan_id: planId }),
  });

  if (res.ok) {
    // Success — clear the key so next subscribe attempt is fresh
    localStorage.removeItem(`idem:subscribe:${planId}`);
  }
  return res.json<SubscribeResult>();
}
```

Key scope: one UUID per logical user intent (one per "subscribe
attempt for this plan"). Never reuse a key across different
operations — `create-subscription` and `create-invoice` get
separate keys.

## D1 Schema

```sql
-- Idempotency record table
CREATE TABLE IF NOT EXISTS idempotency_records (
  key          TEXT    NOT NULL PRIMARY KEY,  -- client UUID
  tenant_id    TEXT    NOT NULL,
  operation    TEXT    NOT NULL,              -- 'subscribe', 'charge', etc.
  status_code  INTEGER NOT NULL,
  response     TEXT    NOT NULL,             -- JSON-serialised response body
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL              -- epoch seconds; GC after this
);

CREATE INDEX IF NOT EXISTS idx_idem_tenant
  ON idempotency_records (tenant_id, created_at);
```

`ON CONFLICT DO NOTHING` is the atomic guard. Even if two requests
race, only the first insert wins. Both requests then read the same
stored response.

## Worker Handler

```ts
const IDEM_TTL_SECONDS = 86_400; // 24 h retention window

export async function handleSubscribe(req: Request, env: Env, ctx: McContext): Promise<Response> {
  const idempKey = req.headers.get('Idempotency-Key');
  if (!idempKey) {
    return Response.json({ error: 'idempotency_key_required' }, { status: 400 });
  }
  // Validate UUID format — reject anything else
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(idempKey)) {
    return Response.json({ error: 'idempotency_key_invalid' }, { status: 400 });
  }

  // 1. Check for existing record
  const existing = await env.DB.prepare(
    `SELECT status_code, response FROM idempotency_records WHERE key = ? AND tenant_id = ?`
  ).bind(idempKey, ctx.tenant.id).first<{ status_code: number; response: string }>();

  if (existing) {
    // Return the original response — idempotent replay
    return new Response(existing.response, {
      status: existing.status_code,
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Replayed': 'true',
      },
    });
  }

  // 2. Execute the operation
  const body = await req.json<{ plan_id: string }>();
  let statusCode: number;
  let responseBody: unknown;

  try {
    const subscription = await createSubscription(env, ctx, body.plan_id);
    statusCode = 201;
    responseBody = subscription;
  } catch (err) {
    // Do NOT store failed responses — allow retry with same key
    throw err;
  }

  const responseJson = JSON.stringify(responseBody);
  const now = Math.floor(Date.now() / 1000);

  // 3. Persist result atomically — ON CONFLICT DO NOTHING handles races
  await env.DB.prepare(`
    INSERT INTO idempotency_records
      (key, tenant_id, operation, status_code, response, created_at, expires_at)
    VALUES (?, ?, 'subscribe', ?, ?, ?, ?)
    ON CONFLICT (key) DO NOTHING
  `).bind(idempKey, ctx.tenant.id, statusCode, responseJson, now, now + IDEM_TTL_SECONDS).run();

  // After the race, read back — ensures we return the winner's response
  const committed = await env.DB.prepare(
    `SELECT status_code, response FROM idempotency_records WHERE key = ?`
  ).bind(idempKey).first<{ status_code: number; response: string }>();

  return new Response(committed!.response, {
    status: committed!.status_code,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Failure Scenarios and Correct Behaviour

| Scenario                              | Key present? | Expected outcome              |
|---------------------------------------|--------------|-------------------------------|
| First request, success                | No           | Insert record, return 201     |
| Retry after network drop (success)    | Yes          | Return stored 201 (replayed)  |
| Two concurrent requests               | Race         | One inserts; both read same   |
| First request fails (5xx)             | No           | No insert; retry allowed      |
| Retry after server-side failure       | No           | Re-execute, insert on success |
| Different tenant, same UUID           | N/A          | Separate rows by tenant_id    |
| Key reused for different operation    | Yes (wrong)  | 409 Conflict (see gotchas)    |

## Key Expiry and Garbage Collection

Store `expires_at` and run a scheduled cleanup Worker:

```ts
// cron: "0 3 * * *"
export async function gcIdempotencyRecords(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    `DELETE FROM idempotency_records WHERE expires_at < ?`
  ).bind(now).run();
}
```

The 24-hour window covers all realistic mobile retry scenarios —
a user who is offline for 25 hours must start a new intent with
a new key, which is acceptable.

## Mobile Double-Tap Prevention

On the client, disable the button immediately after the first tap
and re-enable only on failure, not just on response:

```ts
async function onSubscribeTap(planId: string) {
  subscribeButton.disabled = true;
  try {
    await subscribe(planId);
    // navigate away — key cleared inside subscribe()
  } catch (err) {
    subscribeButton.disabled = false; // allow retry; key still in localStorage
    showError(err);
  }
}
```

The combination of UI lock + persisted idempotency key provides
defence-in-depth: the UI prevents double-taps; the server-side
key handles network retries; D1 `ON CONFLICT` handles races.

## Anti-patterns

- **Server-generated keys.** The server can't know if the client
  already has a key from a previous attempt. Client-generated
  keys are required for retry-across-timeout safety.
- **Storing failure responses.** If the payment processor returns
  500, do not persist that as the idempotent result. Allow the
  client to retry with the same key.
- **Reusing keys across operations.** One key must map to exactly
  one intent. Mixing `subscribe` and `cancel` on the same key
  produces incorrect replays.
- **No tenant scope on the key.** A malicious tenant could replay
  another tenant's idempotency key. Always scope by tenant.
- **Short expiry windows.** A 1-minute window doesn't cover a
  mobile client that goes offline. 24 hours is the minimum for
  payment mutations.

## Gotchas

- If the read-back after `ON CONFLICT DO NOTHING` returns a record
  whose response differs from what the current request would have
  returned, return the stored record — that is correct idempotent
  behaviour even if the outcome is surprising.
- D1's `ON CONFLICT DO NOTHING` does not raise an error; it
  silently succeeds with 0 rows affected. Always read back to
  determine which writer won.
- UUID v4 has `2^122` possible values. Collision probability for
  10M operations per day over 10 years is ~0. Do not accept
  non-UUID keys (rejects predictable short tokens that may
  conflict across tenants).
- Cloudflare D1 does not support `RETURNING` on
  `INSERT ... ON CONFLICT DO NOTHING`. Two queries (insert then
  select) are required.

## Verification

```bash
# First call — expect 201
curl -s -X POST https://api.example.com/v1/subscriptions \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"plan_id":"pro"}' | jq .

# Second call with same key — expect 201 + Idempotency-Replayed: true
curl -si -X POST https://api.example.com/v1/subscriptions \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"plan_id":"pro"}' | grep -E "201|Idempotency-Replayed"
```

Verify the `idempotency_records` table has exactly one row for
that key after both calls.

## Related

- `idempotency-keys.md` — generic pattern reference
- `idempotency-reservation-lease-recovery.md` — lease-based variant
- `saga-pattern-multi-step-workers.md` — idempotency at each saga step
- `database-transaction-design.md` — D1 transaction patterns

## Sources

- Stripe API: Idempotent Requests: https://stripe.com/docs/api/idempotent_requests
- Cloudflare D1 SQL: https://developers.cloudflare.com/d1/
- RFC 7231 §4.2.2 — Idempotent Methods
