# Sleeper Account Activation Detection — D1 & Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A coordinated harassment campaign or spam wave lands from accounts that are weeks or months old and have clean histories. Standard new-account velocity checks do not fire because the accounts are aged. Post-incident forensics shows hundreds of accounts were registered in a tight cluster, sat dormant, then all posted within minutes of each other. Existing botnet registration detection (`botnet-registration-detection-turnstile-fingerprinting.md`) catches accounts at creation time but cannot flag accounts that were registered cleanly and only weaponized later.

## Context

Sleeper-account campaigns are a maturation of bot tradecraft. Operators register accounts in bulk, let them accrue natural-looking age, occasionally post innocuous content ("warming"), then activate them simultaneously on a trigger signal. Detection requires long-horizon behavioral modeling: tracking registration cohorts, dormancy periods, warm-up cadence, and sudden synchronous activation. The stack is: D1 (account lifecycle events + cohort metadata), Workers (activation event handler + anomaly scorer), Queues (deferred cohort re-evaluation), and Durable Objects (per-cohort live coordination state).

## 1. Account Lifecycle Schema

```sql
-- migrations/0055_sleeper_accounts.sql
CREATE TABLE IF NOT EXISTS account_events (
  account_id   TEXT NOT NULL,
  event_type   TEXT NOT NULL,  -- registered | warmed | activated | flagged
  occurred_at  INTEGER NOT NULL,
  ip_hash      TEXT,
  asn          INTEGER,
  session_fp   TEXT            -- device fingerprint hash
);
CREATE INDEX IF NOT EXISTS idx_ae_account ON account_events(account_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_ae_type    ON account_events(event_type, occurred_at);

CREATE TABLE IF NOT EXISTS registration_cohorts (
  cohort_id        TEXT PRIMARY KEY,   -- e.g. "2026-07-15T14:00:00Z/asn:209"
  registered_at    INTEGER NOT NULL,
  asn              INTEGER,
  size             INTEGER NOT NULL,
  activation_count INTEGER DEFAULT 0,
  flagged          INTEGER DEFAULT 0   -- boolean
);
```

## 2. Cohort Assignment at Registration

```typescript
// src/sleeper-cohort.ts
const COHORT_WINDOW_MS = 30 * 60 * 1000; // 30-minute registration windows

export async function assignCohort(
  accountId: string,
  asn: number,
  registeredAt: number,
  env: Env
): Promise<string> {
  // Quantize time to 30-min bucket
  const bucket = Math.floor(registeredAt / COHORT_WINDOW_MS) * COHORT_WINDOW_MS;
  const cohortId = `${new Date(bucket).toISOString()}/${asn}`;

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO account_events (account_id, event_type, occurred_at, asn)
       VALUES (?, 'registered', ?, ?)`
    ).bind(accountId, registeredAt, asn),
    env.DB.prepare(
      `INSERT INTO registration_cohorts (cohort_id, registered_at, asn, size)
       VALUES (?, ?, ?, 1)
       ON CONFLICT(cohort_id) DO UPDATE SET size = size + 1`
    ).bind(cohortId, bucket, asn, 1),
  ]);

  // Store cohort assignment on account record
  await env.DB.prepare(
    "UPDATE accounts SET cohort_id = ? WHERE id = ?"
  )
    .bind(cohortId, accountId)
    .run();

  return cohortId;
}
```

## 3. Activation Event Handler

```typescript
// src/sleeper-activation.ts
const DORMANCY_THRESHOLD_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

export async function recordActivation(
  accountId: string,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const now = Date.now();

  // Fetch account registration time and cohort
  const acct = await env.DB.prepare(
    "SELECT created_at, cohort_id FROM accounts WHERE id = ?"
  )
    .bind(accountId)
    .first<{ created_at: number; cohort_id: string }>();

  if (!acct) return;

  const dormancyMs = now - acct.created_at;
  const isDormant = dormancyMs >= DORMANCY_THRESHOLD_MS;

  await env.DB.prepare(
    "INSERT INTO account_events (account_id, event_type, occurred_at) VALUES (?, 'activated', ?)"
  )
    .bind(accountId, now)
    .run();

  if (isDormant && acct.cohort_id) {
    // Increment cohort activation counter, then schedule anomaly check
    await env.DB.prepare(
      "UPDATE registration_cohorts SET activation_count = activation_count + 1 WHERE cohort_id = ?"
    )
      .bind(acct.cohort_id)
      .run();

    ctx.waitUntil(
      env.SLEEPER_QUEUE.send({
        cohortId: acct.cohort_id,
        triggeredBy: accountId,
        checkAt: now,
      })
    );
  }
}
```

## 4. Cohort Anomaly Scorer (Queue Consumer)

```typescript
// src/sleeper-scorer.ts
const BURST_WINDOW_MINUTES = 15;
const BURST_THRESHOLD_RATIO = 0.25; // >25% of cohort activates within window

export default {
  async queue(
    batch: MessageBatch<{ cohortId: string; checkAt: number }>,
    env: Env
  ) {
    for (const msg of batch.messages) {
      const { cohortId, checkAt } = msg.body;
      const windowStart = checkAt - BURST_WINDOW_MINUTES * 60 * 1000;

      const cohort = await env.DB.prepare(
        "SELECT size, activation_count FROM registration_cohorts WHERE cohort_id = ?"
      )
        .bind(cohortId)
        .first<{ size: number; activation_count: number }>();

      if (!cohort) { msg.ack(); continue; }

      // Count activations within the burst window
      const { count } = (await env.DB.prepare(
        `SELECT COUNT(*) AS count
         FROM account_events ae
         JOIN accounts a ON ae.account_id = a.id
         WHERE a.cohort_id = ? AND ae.event_type = 'activated'
           AND ae.occurred_at >= ?`
      )
        .bind(cohortId, windowStart)
        .first<{ count: number }>()) ?? { count: 0 };

      const ratio = count / cohort.size;

      if (ratio >= BURST_THRESHOLD_RATIO && cohort.size >= 10) {
        // Flag cohort — route all member accounts to manual review queue
        await env.DB.batch([
          env.DB.prepare(
            "UPDATE registration_cohorts SET flagged = 1 WHERE cohort_id = ?"
          ).bind(cohortId),
          env.DB.prepare(
            `UPDATE accounts SET trust_level = 'suspect'
             WHERE cohort_id = ? AND trust_level != 'banned'`
          ).bind(cohortId),
        ]);

        await env.MODERATION_QUEUE.send({
          type: "sleeper_cohort",
          cohortId,
          burstCount: count,
          cohortSize: cohort.size,
          ratio,
        });
      }

      msg.ack();
    }
  },
};
```

## 5. Warm-Up Pattern Heuristic

```typescript
// src/sleeper-warmup.ts — detects accounts that posted exactly 1-3 times then went silent
export async function detectWarmupPattern(
  cohortId: string,
  env: Env
): Promise<number> {
  // Returns fraction of cohort members fitting warm-up profile
  const rows = await env.DB.prepare(
    `SELECT a.id,
            COUNT(p.id) AS post_count,
            MAX(p.created_at) AS last_post_at
     FROM accounts a
     LEFT JOIN posts p ON p.account_id = a.id
     WHERE a.cohort_id = ?
     GROUP BY a.id`
  )
    .bind(cohortId)
    .all<{ id: string; post_count: number; last_post_at: number | null }>();

  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const warmUp = rows.results.filter(
    (r) =>
      r.post_count >= 1 &&
      r.post_count <= 3 &&
      (r.last_post_at ?? 0) < sevenDaysAgo
  );

  return rows.results.length > 0 ? warmUp.length / rows.results.length : 0;
}
```

## 6. Durable Object: Cohort Live State

```typescript
// src/CohortMonitor.ts
export class CohortMonitor implements DurableObject {
  private activations: number[] = [];

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const { accountId, ts }: { accountId: string; ts: number } =
      await req.json();

    this.activations = (await this.state.storage.get<number[]>("acts")) ?? [];
    const cutoff = ts - 15 * 60 * 1000;
    this.activations = this.activations.filter((t) => t >= cutoff);
    this.activations.push(ts);
    await this.state.storage.put("acts", this.activations);

    return Response.json({ recentActivations: this.activations.length });
  }
}
```

## Anti-patterns

- Using account age alone as a trust signal — sleeper accounts specifically exploit age-based trust.
- Setting BURST_THRESHOLD_RATIO too low on small cohorts — a 3-person cohort where 1 activates is 33% but not suspicious; enforce `cohort.size >= 10`.
- Flagging cohorts based solely on ASN without time-bucketing — large ASNs (cloud providers) span millions of legitimate users.
- Auto-banning all cohort members on first flag — warm-up pattern + burst is strong signal but still warrants human review before permanent action.

## Gotchas

- D1 `COUNT(*)` across large `account_events` tables is slow without the compound index on `(cohort_id, occurred_at)` — add it via `accounts JOIN account_events` pattern shown above.
- Cohort IDs are time-bucketed; accounts registered across a bucket boundary appear in different cohorts even if registered seconds apart. Use a 30-min overlap check for edge cases.
- Queue consumers may process messages out of order; always re-read D1 state rather than relying on message payload counts.
- If the platform allows anonymous sessions without accounts, cohort tracking must fall back to device fingerprint clustering instead of account IDs.

## Verification

```bash
# Check cohort size distribution
wrangler d1 execute example project-prod --command \
  "SELECT size, COUNT(*) n FROM registration_cohorts GROUP BY size ORDER BY size DESC LIMIT 20"

# Simulate activation burst in staging
for i in $(seq 1 30); do
  curl -s -X POST https://staging.example.com/api/post \
    -H "X-Account-Id: sleeper-test-$i" \
    -d '{"text":"test"}' &
done; wait

# Verify flagging
wrangler d1 execute example project-prod --command \
  "SELECT cohort_id, size, activation_count, flagged FROM registration_cohorts WHERE flagged=1 ORDER BY activation_count DESC LIMIT 10"
```

## Related

- `botnet-registration-detection-turnstile-fingerprinting.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `sock-puppet-network-detection.md`
- `anonymous-account-graph-clustering-d1.md`
- `sybil-attack-detection-workers-ai-behavioral.md`

## Sources

- Stanford Internet Observatory, "Coordinated Inauthentic Behavior on Social Platforms" (2024)
- Meta Transparency Report — Coordinated Inauthentic Behavior Takedowns (2025)
- Cloudflare D1 docs: developers.cloudflare.com/d1/
- Cloudflare Durable Objects: developers.cloudflare.com/durable-objects/
