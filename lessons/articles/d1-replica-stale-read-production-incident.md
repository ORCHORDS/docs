# Incident: D1 Read Replica Stale Data Served Expired Subscription Entitlements

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production
- **Severity:** P2 — subset of users received incorrect entitlement decisions for 22 minutes

---

## Symptom

After deploying a subscription downgrade flow at 11:40 UTC, customer support began receiving reports of users who had successfully downgraded from a Pro plan to a Free plan but continued to see Pro-tier features available — and in two cases, continued to be billed Pro pricing on subsequent invoice runs. Investigation revealed that D1 read replicas in regions geographically distant from the primary were serving pre-downgrade rows up to 22 minutes after the write had committed on the primary.

---

## Context

Cloudflare D1 replicates writes from a single primary SQLite node to read replicas distributed across Cloudflare's network. Reads issued from a Worker are routed to a "nearby" replica for latency. This is an eventually consistent system: **replica lag is not bounded by a hard SLA** — it is typically seconds, but under write load or network partition conditions it can extend to minutes.

The platform's entitlement-check Worker read the `subscriptions` table from D1 using the default `client.prepare(...).first()` call, which routes to the nearest replica. No session consistency hint was used. A subscription downgrade write committed on the primary at 11:40:14 UTC; a read replica serving users in the AP region did not reflect the write until 12:02:37 UTC — a 22-minute, 23-second lag.

---

## Timeline

| UTC | Event |
|-----|-------|
| 11:40:14 | Downgrade transaction commits on D1 primary |
| 11:40:16 | Downgrade API returns 200 to client |
| 11:41:00 | AP-region Worker reads subscriptions from stale replica — serves Pro entitlements |
| 11:55:00 | First support ticket filed: "I downgraded but still see Pro features" |
| 12:00:00 | Engineer begins investigation; suspects caching layer |
| 12:02:37 | AP-region replica catches up; stale reads resolve |
| 12:08:00 | Incident confirmed as D1 replica lag; write-after-read consistency requirement identified |
| 12:22:00 | Hotfix deployed: entitlement reads routed to primary via `DATABASE_BINDING.withSession('first-uncached')` |
| 12:30:00 | Incident closed; affected invoices flagged for billing correction |

---

## Root Cause Analysis

### Primary: Entitlement Reads Did Not Require Primary Consistency

The entitlement-check path called `env.DB.prepare('SELECT tier FROM subscriptions WHERE user_id = ?').bind(userId).first()`. This routed to the nearest replica. For a read-heavy dashboard widget this is correct; for an entitlement gate immediately after a write it is incorrect. The code made no distinction between "this read must reflect recent writes" and "this read can tolerate staleness."

### Contributing: No Replica Lag Monitoring

The platform had no metric tracking D1 replication lag. The first indication of a lag event was a customer complaint, not an internal alert.

### Contributing: Billing Job Read Subscriptions from Replica

The invoice cron job that ran 18 minutes after the downgrade also read from D1 without primary pinning, picked up the stale Pro-tier row, and generated two incorrect Pro invoices.

---

## Technical Sections

### 1. D1 Consistency Model: Replicas vs Primary

D1 exposes a read consistency hint via the binding's session semantics. As of the D1 GA API, callers can influence where their read lands:

```ts
// Default: nearest replica — fast, eventually consistent
const row = await env.DB.prepare('SELECT tier FROM subscriptions WHERE user_id = ?')
  .bind(userId)
  .first();

// Primary read — consistent, slightly higher latency
// Use for reads that must reflect a recent write in the same logical flow
const row = await env.DB.withSession('first-uncached')
  .prepare('SELECT tier FROM subscriptions WHERE user_id = ?')
  .bind(userId)
  .first();
```

`withSession('first-uncached')` forces the query to the primary node, bypassing replica cache. Use it when:
- The read immediately follows a write (write-then-read pattern)
- The data drives an access control or billing decision
- The read is the source of truth for an idempotency check

### 2. Write-Then-Read Consistency Pattern

Always pin reads to the primary when the caller has just performed a write that the read must observe:

```ts
async function downgradeSubscription(userId: string, newTier: string, env: Env): Promise<void> {
  // Write — always goes to primary
  await env.DB.prepare(
    'UPDATE subscriptions SET tier = ?, updated_at = ? WHERE user_id = ?'
  ).bind(newTier, Date.now(), userId).run();

  // Read-after-write — must use primary to avoid serving stale data
  const updated = await env.DB.withSession('first-uncached')
    .prepare('SELECT tier, updated_at FROM subscriptions WHERE user_id = ?')
    .bind(userId)
    .first<{ tier: string; updated_at: number }>();

  if (!updated || updated.tier !== newTier) {
    throw new Error('Subscription update did not persist — primary read verification failed');
  }

  // Now safe to return success to the caller
}
```

### 3. Entitlement Gate: Always Read from Primary

For any code path that gates access or triggers billing, enforce primary reads at the function boundary:

```ts
async function getEntitlements(userId: string, env: Env): Promise<Entitlements> {
  // Intentionally uses primary — entitlement decisions are security-sensitive.
  // Replica lag is not acceptable here; the ~5ms primary latency premium is worth it.
  const row = await env.DB.withSession('first-uncached')
    .prepare('SELECT tier, features, valid_until FROM subscriptions WHERE user_id = ?')
    .bind(userId)
    .first<SubscriptionRow>();

  if (!row || Date.now() > row.valid_until) {
    return FREE_TIER_ENTITLEMENTS;
  }
  return ENTITLEMENTS_BY_TIER[row.tier] ?? FREE_TIER_ENTITLEMENTS;
}
```

Document this at the module level with a comment explaining **why** primary reads are required, so future reviewers do not "optimise" it back to replica reads.

### 4. Monitoring D1 Replication Lag

D1 does not expose a replication lag metric via the dashboard or API. A synthetic approach works: periodically write a known value to a sentinel row on the primary, then read it from a regional Worker and compare:

```ts
// Scheduled sentinel write (runs every 30s on a global cron Worker)
async function writeSentinel(env: Env): Promise<void> {
  const ts = Date.now();
  await env.DB.prepare(
    'INSERT INTO _replication_sentinel (id, written_at) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET written_at = excluded.written_at'
  ).bind(ts).run();
}

// Regional check Worker (deployed to every region via Smart Placement off)
async function checkSentinelLag(env: Env): Promise<void> {
  const row = await env.DB.prepare('SELECT written_at FROM _replication_sentinel WHERE id = 1').first<{ written_at: number }>();
  const lag = Date.now() - (row?.written_at ?? 0);
  await env.ANALYTICS.writeDataPoint({
    blobs: [env.CF_REGION ?? 'unknown'],
    doubles: [lag],
    indexes: ['d1_replication_lag_ms'],
  });
  if (lag > 10_000) { // 10-second threshold
    await notifyOps(env, `D1 replication lag in ${env.CF_REGION}: ${lag}ms`);
  }
}
```

### 5. Classifying Reads by Consistency Requirement

Establish a coding convention that marks every D1 read with its consistency requirement:

```ts
// Convention: suffix variable name with _primary or _replica to make intent explicit
const subscription_primary = await env.DB.withSession('first-uncached')
  .prepare('SELECT * FROM subscriptions WHERE user_id = ?').bind(userId).first();

const recentActivity_replica = await env.DB
  .prepare('SELECT * FROM activity_log WHERE user_id = ? ORDER BY ts DESC LIMIT 20')
  .bind(userId).all();
```

Add a lint rule (via a custom ESLint plugin or a grep-based CI check) that flags any D1 `.first()` or `.all()` call inside files matching `*entitlement*`, `*billing*`, or `*payment*` that does not use `withSession`.

### 6. Billing Job Hardening

Batch billing jobs must always read from the primary, and they must verify the subscription state has not changed between their read and their write:

```ts
async function billUser(userId: string, env: Env): Promise<void> {
  const sub = await env.DB.withSession('first-uncached')
    .prepare('SELECT tier, updated_at FROM subscriptions WHERE user_id = ?')
    .bind(userId)
    .first<SubscriptionRow>();

  if (!sub) throw new Error(`No subscription for user ${userId}`);

  // Optimistic lock: re-check updated_at has not changed before issuing invoice
  const invoice = buildInvoice(sub);
  const result = await env.DB.prepare(
    'INSERT INTO invoices (user_id, tier, amount) SELECT ?, ?, ? WHERE (SELECT updated_at FROM subscriptions WHERE user_id = ?) = ?'
  ).bind(userId, sub.tier, invoice.amount, userId, sub.updated_at).run();

  if (result.meta.changes === 0) {
    throw new RetryableError('Subscription changed between read and invoice write — retry');
  }
}
```

---

## Anti-Patterns

- **Treating all D1 reads as interchangeable.** Replica reads and primary reads have different consistency guarantees. A codebase that uses bare `.first()` everywhere will eventually serve stale data in a security-sensitive context.
- **No documentation on read consistency at call sites.** Future developers optimise for performance without understanding why a particular read must be consistent.
- **Billing jobs reading from replicas.** Invoice generation must reflect ground truth. Any read that determines a monetary amount must be pinned to the primary.
- **Assuming replica lag is always sub-second.** D1 replication lag is typically short but is not SLA-bounded. Cross-region lag under write pressure or partial network events can extend to minutes.
- **Discovering replica lag through customer complaints.** Synthetic lag monitoring must precede incidents.

---

## Gotchas

- `withSession('first-uncached')` adds latency because the query must reach the primary, which may be geographically distant. For the AP region hitting a US-East primary, expect 50–120ms additional round-trip time versus a local replica read.
- D1's session token mechanism (`withSession(token)`) allows carrying a consistency token from a write result through to subsequent reads. This is more efficient than `first-uncached` when multiple reads must all follow a specific write.
- `env.DB.batch([...])` does not automatically pin to the primary unless wrapped with `withSession`.
- Wrangler local dev (`--local`) uses an in-process SQLite with no replication. Local testing cannot reproduce replica lag. Use a staging D1 database in a multi-region test environment for lag simulation.
- Deleting a row and immediately reading to confirm deletion requires `withSession('first-uncached')`. Reading from a replica that has not yet received the delete will return the deleted row.

---

## Verification

Post-incident verification on 2026-08-23:

1. Deployed sentinel write + regional read Workers to production; replication lag dashboard live in Analytics Engine. Lag in all regions confirmed below 3 seconds under normal conditions.
2. Grep CI check deployed: build fails if any file in `src/entitlements/`, `src/billing/`, or `src/payments/` contains a D1 `.first()` or `.all()` call without `withSession`.
3. Subscription downgrade end-to-end test asserts that the entitlement API returns Free-tier entitlements within 100ms of downgrade commit when called from a simulated AP-region Worker — passing.
4. Two affected invoices identified, corrected, and refunded. Billing team confirmed no further incorrect charges.

---

## Related

- `d1-write-contention-viral-event-postmortem.md`
- `d1-batch-size-limit-exceeded-postmortem.md`
- `eventual-consistency-surprises-clients.md`
- `idempotency-keys-for-all-payment-calls.md`
- `cloudflare-storage-primitive-selection.md`

---

## Sources

- Cloudflare D1 — read replication and consistency: https://developers.cloudflare.com/d1/best-practices/read-replication/
- D1 client API — withSession: https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- CAP theorem and eventual consistency primer: https://en.wikipedia.org/wiki/CAP_theorem
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
