# D1 Atomic Transactions and TOCTOU Race Condition Prevention

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker reads a user's account balance, checks that it is sufficient, then deducts the amount in a second query. Under concurrent load — multiple Workers handling simultaneous requests for the same user — two Workers both read the same balance, both pass the check, and both execute the deduction, resulting in a negative balance or double-spend. This is a classic Time-of-Check to Time-of-Use (TOCTOU) race condition, and it is trivially reproducible in D1 because Workers run in parallel by default.

## Context

Cloudflare D1 is a SQLite-compatible database with ACID transactions via the `db.batch()` API and `BEGIN`/`COMMIT` statements. Unlike Durable Objects, D1 does not serialize access — multiple Workers can execute concurrent transactions. SQLite's isolation model (SERIALIZABLE by default for write transactions) prevents dirty reads but does not automatically prevent application-level TOCTOU patterns where the check and the mutation are expressed as separate statements outside a transaction. The fix is to express the check and the mutation as a single atomic `UPDATE ... WHERE` or to use `BEGIN IMMEDIATE` to take a write lock before reading.

## 1. The Broken Pattern (TOCTOU)

```typescript
// INSECURE: Read-then-write without a transaction
export async function deductBalance(
  env: Env,
  userId: string,
  amount: number
): Promise<void> {
  const { results } = await env.DB.prepare(
    "SELECT balance FROM accounts WHERE id = ?"
  ).bind(userId).all();

  const balance = results[0]?.balance as number;
  if (balance < amount) throw new Error("Insufficient funds"); // check

  // ← Another Worker can win the race here ←
  await env.DB.prepare(
    "UPDATE accounts SET balance = balance - ? WHERE id = ?"
  ).bind(amount, userId).run(); // use — may go negative
}
```

## 2. Atomic UPDATE with Conditional WHERE (Preferred)

Express the check and the mutation in a single statement. D1/SQLite evaluates the `WHERE` condition and applies the update atomically under a row-level write lock:

```typescript
export async function deductBalance(
  env: Env,
  userId: string,
  amount: number
): Promise<{ success: boolean }> {
  const result = await env.DB.prepare(`
    UPDATE accounts
    SET    balance = balance - ?
    WHERE  id      = ?
      AND  balance >= ?
  `).bind(amount, userId, amount).run();

  // `meta.changes` is 0 if the WHERE condition failed (insufficient funds)
  if (result.meta.changes === 0) {
    return { success: false }; // insufficient funds or user not found
  }
  return { success: true };
}
```

No separate SELECT is required. The database atomically checks the condition and applies the update, eliminating the race window.

## 3. Multi-Step Transactions with BEGIN IMMEDIATE

When the business logic requires reading a value and then making a decision based on it before writing, use `BEGIN IMMEDIATE` to acquire a write lock for the duration of the transaction:

```typescript
export async function transferFunds(
  env: Env,
  fromId: string,
  toId: string,
  amount: number
): Promise<void> {
  await env.DB.batch([
    env.DB.prepare("BEGIN IMMEDIATE"),

    // Now holding a write lock — no other writer can proceed
    env.DB.prepare(`
      UPDATE accounts SET balance = balance - ?
      WHERE id = ? AND balance >= ?
    `).bind(amount, fromId, amount),

    env.DB.prepare(`
      UPDATE accounts SET balance = balance + ?
      WHERE id = ?
    `).bind(amount, toId),

    env.DB.prepare("COMMIT"),
  ]);
  // D1 batch() is all-or-nothing; if any statement fails, D1 rolls back.
}
```

`BEGIN IMMEDIATE` takes a reserved lock on the database file immediately, preventing concurrent writes from interleaving. Note: D1's write throughput is limited (one writer at a time per D1 database); use this only when the atomic conditional UPDATE pattern is insufficient.

## 4. Idempotency Keys to Prevent Duplicate Operations

Even with atomic transactions, a Worker timeout or network retry can cause the client to re-submit the same operation. An idempotency key guards against double execution:

```typescript
export async function processPayment(
  env: Env,
  idempotencyKey: string,
  userId: string,
  amount: number
): Promise<{ alreadyProcessed: boolean }> {
  const result = await env.DB.batch([
    env.DB.prepare("BEGIN IMMEDIATE"),

    // Try to insert the idempotency record first; fail if already exists
    env.DB.prepare(`
      INSERT OR IGNORE INTO idempotency_keys (key, user_id, processed_at)
      VALUES (?, ?, ?)
    `).bind(idempotencyKey, userId, Date.now()),

    // Only deduct if the idempotency insert actually happened
    env.DB.prepare(`
      UPDATE accounts
      SET    balance = balance - ?
      WHERE  id      = ?
        AND  balance >= ?
        AND  EXISTS (
          SELECT 1 FROM idempotency_keys
          WHERE key = ? AND processed_at >= ?
        )
    `).bind(amount, userId, amount, idempotencyKey, Date.now() - 5000),

    env.DB.prepare("COMMIT"),
  ]);

  const insertMeta = result[1].meta;
  return { alreadyProcessed: insertMeta.changes === 0 };
}
```

## 5. Optimistic Locking with a Version Column

For update-heavy workloads where `BEGIN IMMEDIATE` throughput is a concern, use an optimistic locking pattern — include a `version` column and fail the update if the version changed since the read:

```typescript
export async function updateUserProfile(
  env: Env,
  userId: string,
  patch: Partial<UserProfile>,
  expectedVersion: number
): Promise<{ conflict: boolean }> {
  const result = await env.DB.prepare(`
    UPDATE user_profiles
    SET    name    = COALESCE(?, name),
           bio     = COALESCE(?, bio),
           version = version + 1,
           updated_at = ?
    WHERE  id      = ?
      AND  version = ?
  `)
    .bind(patch.name ?? null, patch.bio ?? null, Date.now(), userId, expectedVersion)
    .run();

  if (result.meta.changes === 0) {
    return { conflict: true }; // another writer changed the row; client must re-read
  }
  return { conflict: false };
}
```

Return the new version in the response so the client can include it in subsequent requests.

## 6. Checking `meta.changes` to Detect Failed Conditionals

D1's `RunResult.meta.changes` reports the number of rows actually modified. Always check it after a conditional UPDATE rather than assuming success:

```typescript
async function claimCoupon(env: Env, couponCode: string, userId: string): Promise<boolean> {
  const result = await env.DB.prepare(`
    UPDATE coupons
    SET    claimed_by = ?, claimed_at = ?
    WHERE  code       = ?
      AND  claimed_by IS NULL   -- still available
  `).bind(userId, Date.now(), couponCode).run();

  return result.meta.changes === 1; // false = already claimed
}
```

## Anti-patterns

- Performing a SELECT followed by an UPDATE in separate `env.DB.prepare().run()` calls without a transaction — the classic TOCTOU window.
- Using `db.batch()` with a SELECT then an UPDATE and assuming the SELECT result gates the UPDATE — `batch()` does not make the SELECT's result visible to subsequent statements in the same batch (each statement is evaluated independently unless inside a transaction).
- Relying on Workers invocation serialization for mutual exclusion — Workers run concurrently; there is no implicit lock.
- Using `BEGIN DEFERRED` (the SQLite default) when you need write isolation — `DEFERRED` only acquires a write lock at the first actual write, leaving the read window unprotected.

## Gotchas

- D1 `db.batch()` wraps all statements in an implicit transaction, but that transaction is `DEFERRED`, not `IMMEDIATE`. For write-guarded reads you must explicitly include `BEGIN IMMEDIATE` as the first statement.
- `meta.changes` reflects rows changed by the current statement only, not accumulated across a batch.
- Idempotency key tables must have a TTL purge strategy (cron + `DELETE WHERE processed_at < ?`) to prevent unbounded growth.
- `BEGIN IMMEDIATE` on D1 can time out under write-heavy load — implement exponential back-off retries with jitter at the application layer.
- Optimistic locking conflict rates rise with concurrent update frequency; if conflicts exceed ~5% of requests, consider using a Durable Object as a serializing lock for that resource.

## Verification

```bash
# Simulate concurrent deductions — both should not succeed if balance = amount
for i in 1 2; do
  curl -s -X POST https://api.example.com/pay \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"amount": 100}' &
done
wait

# Query D1 directly via Wrangler to confirm balance did not go negative
wrangler d1 execute prod-db \
  --command "SELECT id, balance FROM accounts WHERE id = 'user-123'"

# Expected: balance is 0 (or original minus one successful deduction), not -100
```

## Related

- `race-condition-toctou-web.md`
- `api-replay-prevention-nonce-d1-workers.md`
- `anonymous-vote-integrity-d1-workers.md`
- `d1-row-level-security-tenant-isolation.md`
- `idempotency-one-time-secret-replay.md`

## Sources

- SQLite Isolation Levels: https://www.sqlite.org/isolation.html
- D1 Batch API: https://developers.cloudflare.com/d1/worker-api/d1-client-api/#dbbatch
- OWASP Race Conditions: https://owasp.org/www-community/vulnerabilities/Time_of_check_time_of_use
- CWE-367 TOCTOU Race Condition: https://cwe.mitre.org/data/definitions/367.html
