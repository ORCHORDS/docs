# Platform Reputation Score Decay in D1 and Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A trust-and-safety system awards and deducts reputation points but never ages them: a
user who behaved badly two years ago is still penalized as harshly as a user who offended
last week. Conversely, a user who built a strong reputation years ago and then goes dark
retains a full score indefinitely, making dormant-account-reactivation abuse trivial.
example project needs a scheduled decay mechanism that exponentially softens historical signals
while preserving recency weight.

---

## Context

Reputation scores stored in D1 are static unless explicitly updated. A Cloudflare Workers
Cron Trigger runs nightly and applies a half-life decay formula to each account's score
components. The decay is *component-wise* (positive reputation and negative reputation
decay at different rates), which lets the system reward rehabilitation without discarding
the memory of past violations entirely. The net score is recomputed and written back to D1
in a single transactional batch.

---

## 1. D1 Schema

```sql
-- migration 0012_reputation_decay.sql
CREATE TABLE IF NOT EXISTS reputation_components (
  account_id    TEXT    NOT NULL,
  component     TEXT    NOT NULL,  -- 'positive' | 'negative' | 'trust_bonus'
  raw_points    REAL    NOT NULL DEFAULT 0,
  last_updated  INTEGER NOT NULL,  -- Unix timestamp ms
  PRIMARY KEY (account_id, component)
);

CREATE TABLE IF NOT EXISTS reputation_net (
  account_id    TEXT PRIMARY KEY,
  net_score     REAL    NOT NULL DEFAULT 0,
  computed_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rep_last_updated ON reputation_components (last_updated);
```

---

## 2. Decay Formula

The half-life per component is configurable. Positive reputation decays slowly (90-day
half-life), negative reputation decays faster (30-day half-life), reflecting a rehabilitation
model. Trust bonuses earned through verified behaviour do not decay.

```typescript
// lib/decay.ts
export interface DecayConfig {
  halfLifeDays: number;
}

export const COMPONENT_CONFIG: Record<string, DecayConfig> = {
  positive:    { halfLifeDays: 90 },
  negative:    { halfLifeDays: 30 },
  trust_bonus: { halfLifeDays: Infinity }, // never decays
};

/**
 * Applies exponential half-life decay.
 * decayed = raw * 2^(-elapsed / halfLife)
 */
export function applyDecay(raw: number, lastUpdatedMs: number, nowMs: number, config: DecayConfig): number {
  if (!isFinite(config.halfLifeDays)) return raw;
  const elapsedDays = (nowMs - lastUpdatedMs) / (1000 * 60 * 60 * 24);
  const factor = Math.pow(2, -(elapsedDays / config.halfLifeDays));
  return raw * factor;
}

export function computeNetScore(
  components: Array<{ component: string; raw_points: number; last_updated: number }>,
  nowMs: number
): number {
  let net = 0;
  for (const c of components) {
    const config = COMPONENT_CONFIG[c.component] ?? { halfLifeDays: 60 };
    const decayed = applyDecay(c.raw_points, c.last_updated, nowMs, config);
    // Positive components add; negative subtract
    net += c.component === 'negative' ? -decayed : decayed;
  }
  return Math.max(0, Math.min(1000, net)); // clamp to [0, 1000]
}
```

---

## 3. Cron Worker

```typescript
// workers/reputation-decay-cron.ts
import { applyDecay, computeNetScore, COMPONENT_CONFIG } from '../lib/decay';

export interface Env {
  DB: D1Database;
}

const BATCH_SIZE = 500; // D1 binding allows up to 1000 rows per query result

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const now = Date.now();

    let offset = 0;
    let processed = 0;

    while (true) {
      // Paginate through all accounts with stale components
      const { results } = await env.DB.prepare(`
        SELECT DISTINCT account_id FROM reputation_components
        ORDER BY account_id
        LIMIT ?1 OFFSET ?2
      `).bind(BATCH_SIZE, offset).all<{ account_id: string }>();

      if (!results || results.length === 0) break;

      for (const { account_id } of results) {
        await decayAccount(env.DB, account_id, now);
        processed++;
      }

      offset += results.length;
      if (results.length < BATCH_SIZE) break;
    }

    console.log(`[reputation-decay] processed ${processed} accounts at ${new Date(now).toISOString()}`);
  },
};

async function decayAccount(db: D1Database, accountId: string, nowMs: number): Promise<void> {
  const { results: components } = await db.prepare(`
    SELECT component, raw_points, last_updated
    FROM reputation_components
    WHERE account_id = ?1
  `).bind(accountId).all<{ component: string; raw_points: number; last_updated: number }>();

  if (!components || components.length === 0) return;

  // Compute decayed values per component
  const updates = components.map((c) => {
    const config = COMPONENT_CONFIG[c.component] ?? { halfLifeDays: 60 };
    const decayed = applyDecay(c.raw_points, c.last_updated, nowMs, config);
    return { component: c.component, decayed };
  });

  const net = computeNetScore(
    components.map((c, i) => ({ ...c, raw_points: updates[i].decayed })),
    nowMs
  );

  // Batch all writes in a single D1 transaction
  const stmts: D1PreparedStatement[] = [
    ...updates.map(({ component, decayed }) =>
      db.prepare(`
        UPDATE reputation_components
        SET raw_points = ?1, last_updated = ?2
        WHERE account_id = ?3 AND component = ?4
      `).bind(decayed, nowMs, accountId, component)
    ),
    db.prepare(`
      INSERT INTO reputation_net (account_id, net_score, computed_at)
      VALUES (?1, ?2, ?3)
      ON CONFLICT(account_id) DO UPDATE SET net_score = excluded.net_score, computed_at = excluded.computed_at
    `).bind(accountId, net, nowMs),
  ];

  await db.batch(stmts);
}
```

---

## 4. Reputation Write (Event-Driven)

When a moderation event occurs, points are added to the appropriate component and the
`last_updated` timestamp is reset to now — preserving the decayed value as the new baseline
so that decay restarts from the current (already-diminished) total.

```typescript
// lib/reputation-write.ts
export async function addReputationPoints(
  db: D1Database,
  accountId: string,
  component: 'positive' | 'negative' | 'trust_bonus',
  delta: number
): Promise<void> {
  const now = Date.now();

  // Upsert: start from 0 if no prior record, otherwise accumulate
  await db.prepare(`
    INSERT INTO reputation_components (account_id, component, raw_points, last_updated)
    VALUES (?1, ?2, ?3, ?4)
    ON CONFLICT(account_id, component) DO UPDATE
      SET raw_points  = reputation_components.raw_points + ?3,
          last_updated = ?4
  `).bind(accountId, component, delta, now).run();
}
```

---

## 5. Serving the Net Score

```typescript
// workers/reputation-api.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const accountId = url.searchParams.get('account_id');
    if (!accountId) return new Response('missing account_id', { status: 400 });

    const row = await env.DB.prepare(`
      SELECT net_score, computed_at FROM reputation_net WHERE account_id = ?1
    `).bind(accountId).first<{ net_score: number; computed_at: number }>();

    if (!row) return new Response(JSON.stringify({ score: 0, tier: 'unrated' }), {
      headers: { 'Content-Type': 'application/json' },
    });

    const tier =
      row.net_score >= 750 ? 'trusted' :
      row.net_score >= 400 ? 'standard' :
      row.net_score >= 100 ? 'monitored' : 'restricted';

    return new Response(JSON.stringify({ score: row.net_score, tier, computed_at: row.computed_at }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## 6. wrangler.toml Cron Binding

```toml
[triggers]
crons = ["0 3 * * *"]   # 03:00 UTC daily

[[d1_databases]]
binding = "DB"
database_name = "example project-moderation"
database_id = "<YOUR_D1_DATABASE_ID>"
```

---

## Anti-patterns

- **Single score field with manual subtraction**: Merging positive and negative into one
  integer means you cannot apply differential decay rates. Keep components separate.
- **Decaying to zero and clamping**: A user whose score reaches ~0 through decay should
  be treated as "neutral", not "banned". Distinguish zero from explicit restriction flags.
- **Updating `last_updated` on every read**: Some implementations accidentally reset the
  decay clock when serving the score. Only reset on writes.
- **Running the cron without pagination**: D1 query results are bounded. A full-table scan
  without LIMIT/OFFSET will silently truncate beyond D1's row limit.

---

## Gotchas

- **D1 batch size**: `db.batch()` accepts up to 100 statements in one call. For accounts
  with many components, split into sub-batches of 100.
- **Floating-point drift**: Exponential decay of small values can produce subnormal floats.
  Floor values below 0.01 to 0 before writing to avoid storing meaningless precision.
- **Cron at scale**: A 03:00 UTC cron on a large platform hits every account in sequence.
  If the Worker CPU limit (30s on Free, 15 min on Paid) is a concern, use a Queue-based
  fan-out: the cron enqueues account IDs and consumer Workers process them in parallel.
- **Clock skew**: Workers' `Date.now()` is wall-clock time. The decay formula assumes
  monotonic time. Log `nowMs` in the cron run for forensic replay.

---

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { applyDecay, computeNetScore } from '../lib/decay';

describe('decay formula', () => {
  const DAY_MS = 86_400_000;

  it('halves positive score after 90 days', () => {
    const decayed = applyDecay(100, 0, 90 * DAY_MS, { halfLifeDays: 90 });
    expect(decayed).toBeCloseTo(50, 1);
  });

  it('trust_bonus does not decay', () => {
    const decayed = applyDecay(200, 0, 365 * DAY_MS, { halfLifeDays: Infinity });
    expect(decayed).toBe(200);
  });

  it('net score clamps to [0, 1000]', () => {
    const net = computeNetScore([
      { component: 'negative', raw_points: 5000, last_updated: Date.now() },
    ], Date.now());
    expect(net).toBe(0);
  });
});
```

---

## Related

- `anonymous-user-reputation-bootstrap-d1-workers.md`
- `platform-trust-score-cloudflare-signals.md`
- `account-dormancy-suspicious-reactivation-d1.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `shadow-banning-reach-limiting-d1-workers.md`

---

## Sources

- Cloudflare D1 — Batch Statements: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Workers — Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- "Designing Reputation Systems" — Khariri (2017), O'Reilly
- Quora Trust & Safety Engineering Blog — "Decay Models in Ranking Systems"
