# Reputation Score Gaming Prevention in D1 Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Anonymous platforms that surface user or content reputation scores (karma, trust rank, visibility tier) create a perverse incentive: actors who discover the scoring formula optimise for it rather than authentic contribution. Common attacks include self-upvoting via sock-puppet accounts, coordinated mutual-upvote rings, posting-then-deleting to farm post-count metrics, and timing posts to exploit algorithmic amplification windows. Left unchecked, score gaming inflates bad actors to high-visibility tiers where they cause disproportionate harm.

## Context

Gaming prevention operates at multiple layers. D1 stores the canonical reputation score and the raw action log that feeds it. Workers enforce per-action rate limits, reject actions where the graph distance between actor and target is suspiciously low (a sign of sock-puppet rings), and apply diminishing-returns curves so each incremental upvote from the same cluster contributes less. A scheduled Worker periodically audits the score ledger for statistical outliers and marks inflated accounts for review. No PII is involved — all graph edges use hashed anonymous identifiers.

## Schema — Score Ledger and Action Log

```sql
-- migration: 0020_reputation_gaming.sql
CREATE TABLE reputation_scores (
  account_id    TEXT PRIMARY KEY,
  score         REAL NOT NULL DEFAULT 0,
  tier          TEXT NOT NULL DEFAULT 'new',  -- new / regular / trusted / flagged
  last_audit    INTEGER,
  audit_flag    INTEGER NOT NULL DEFAULT 0    -- 1 = under review
);

CREATE TABLE reputation_events (
  event_id      TEXT PRIMARY KEY,
  actor_id      TEXT NOT NULL,   -- who performed the action
  target_id     TEXT NOT NULL,   -- whose score changed
  action        TEXT NOT NULL,   -- 'upvote' | 'downvote' | 'post' | 'comment'
  delta         REAL NOT NULL,   -- score change (positive or negative)
  weight        REAL NOT NULL DEFAULT 1.0,  -- diminishing-returns multiplier applied
  cluster_dist  INTEGER,         -- graph distance between actor and target at event time
  created_at    INTEGER NOT NULL
);

CREATE INDEX idx_rep_events_target ON reputation_events(target_id, created_at);
CREATE INDEX idx_rep_events_actor  ON reputation_events(actor_id,  created_at);
```

## Per-Action Rate Limits with Diminishing Returns

Before applying a reputation event the Worker checks how many times the actor has already acted on the target (self-upvote detection) and how many upvotes the target has already received from the actor's cluster today.

```typescript
// worker: reputation-event-handler.ts
export interface Env {
  DB: D1Database;
}

const CLUSTER_DAILY_UPVOTE_CAP = 5;   // cluster members combined
const ACTOR_TARGET_UPVOTE_CAP = 1;    // per actor-target pair ever

function diminishingWeight(nthEvent: number): number {
  // Each successive upvote from the same cluster contributes exponentially less
  return Math.pow(0.5, Math.max(0, nthEvent - 1));
}

export async function applyReputationEvent(
  env: Env,
  actorId: string,
  targetId: string,
  action: 'upvote' | 'downvote' | 'post' | 'comment',
  actorClusterId: string | null
): Promise<{ accepted: boolean; reason?: string }> {
  // Guard: actor cannot vote on themselves
  if (actorId === targetId) {
    return { accepted: false, reason: 'self_action' };
  }

  // Guard: actor-target pair already voted (prevents simple sock-puppet loops)
  const priorVote = await env.DB.prepare(
    `SELECT event_id FROM reputation_events
     WHERE actor_id = ?1 AND target_id = ?2 AND action = ?3 LIMIT 1`
  ).bind(actorId, targetId, action).first();

  if (priorVote) {
    return { accepted: false, reason: 'duplicate_vote' };
  }

  // Count today's upvotes from the same cluster to the same target
  let clusterTodayCount = 0;
  if (actorClusterId && action === 'upvote') {
    const dayStart = Math.floor(Date.now() / 1000) - 86400;
    const row = await env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM reputation_events re
       JOIN account_cluster_members acm ON acm.account_id = re.actor_id
       WHERE acm.cluster_id = ?1
         AND re.target_id  = ?2
         AND re.action     = 'upvote'
         AND re.created_at >= ?3`
    ).bind(actorClusterId, targetId, dayStart).first<{ cnt: number }>();

    clusterTodayCount = row?.cnt ?? 0;

    if (clusterTodayCount >= CLUSTER_DAILY_UPVOTE_CAP) {
      return { accepted: false, reason: 'cluster_cap_exceeded' };
    }
  }

  const baseDeltas: Record<string, number> = {
    upvote:  0.5,
    downvote: -0.3,
    post:    0.1,
    comment: 0.05,
  };

  const baseDelta = baseDeltas[action] ?? 0;
  const weight = action === 'upvote'
    ? diminishingWeight(clusterTodayCount + 1)
    : 1.0;
  const delta = baseDelta * weight;
  const now = Math.floor(Date.now() / 1000);

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO reputation_events
         (event_id, actor_id, target_id, action, delta, weight, cluster_dist, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL, ?7)`
    ).bind(crypto.randomUUID(), actorId, targetId, action, delta, weight, now),

    env.DB.prepare(
      `INSERT INTO reputation_scores (account_id, score) VALUES (?1, ?2)
       ON CONFLICT(account_id) DO UPDATE SET score = score + ?2`
    ).bind(targetId, delta),
  ]);

  return { accepted: true };
}
```

## Score Tier Reclassification

A scheduled Worker reclassifies account tiers based on current score and flags statistical outliers whose score growth velocity is implausible for organic users.

```typescript
// worker: tier-reclassifier.ts (scheduled, hourly)
export interface Env {
  DB: D1Database;
}

const TIER_THRESHOLDS = [
  { min: 100, tier: 'trusted'  },
  { min:  20, tier: 'regular'  },
  { min:   0, tier: 'new'      },
];

function scoreTier(score: number): string {
  for (const { min, tier } of TIER_THRESHOLDS) {
    if (score >= min) return tier;
  }
  return 'new';
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Reclassify tiers
    const { results: accounts } = await env.DB.prepare(
      `SELECT account_id, score FROM reputation_scores WHERE audit_flag = 0`
    ).all<{ account_id: string; score: number }>();

    const tierUpdates = accounts.map((a) =>
      env.DB.prepare(
        `UPDATE reputation_scores SET tier = ?1 WHERE account_id = ?2`
      ).bind(scoreTier(a.score), a.account_id)
    );

    for (let i = 0; i < tierUpdates.length; i += 900) {
      await env.DB.batch(tierUpdates.slice(i, i + 900));
    }

    // Flag outliers: accounts that gained >50 points in the last hour
    const hourAgo = Math.floor(Date.now() / 1000) - 3600;
    await env.DB.prepare(
      `UPDATE reputation_scores
       SET audit_flag = 1, last_audit = unixepoch()
       WHERE account_id IN (
         SELECT target_id FROM reputation_events
         WHERE created_at >= ?1
         GROUP BY target_id
         HAVING SUM(delta) > 50
       )`
    ).bind(hourAgo).run();

    console.log(`[tier-reclassifier] processed ${accounts.length} accounts`);
  },
};
```

## Score Rollback on Confirmed Gaming

When moderation confirms gaming, the associated reputation events are marked as purged and the target's score is recalculated from the clean event log.

```typescript
// worker: score-rollback.ts
export interface Env {
  DB: D1Database;
}

export async function rollbackGamedScore(
  env: Env,
  targetId: string,
  actorClusterId: string
): Promise<void> {
  // Mark all upvotes from the gaming cluster as purged
  await env.DB.prepare(
    `UPDATE reputation_events
     SET weight = 0, delta = 0
     WHERE target_id = ?1
       AND action = 'upvote'
       AND actor_id IN (
         SELECT account_id FROM account_cluster_members WHERE cluster_id = ?2
       )`
  ).bind(targetId, actorClusterId).run();

  // Recalculate canonical score from remaining events
  const row = await env.DB.prepare(
    `SELECT COALESCE(SUM(delta), 0) AS clean_score
     FROM reputation_events
     WHERE target_id = ?1 AND weight > 0`
  ).bind(targetId).first<{ clean_score: number }>();

  const cleanScore = row?.clean_score ?? 0;
  const tier = scoreTier(cleanScore);

  await env.DB.prepare(
    `UPDATE reputation_scores
     SET score = ?1, tier = ?2, audit_flag = 0, last_audit = unixepoch()
     WHERE account_id = ?3`
  ).bind(cleanScore, tier, targetId).run();
}

function scoreTier(score: number): string {
  if (score >= 100) return 'trusted';
  if (score >= 20)  return 'regular';
  return 'new';
}
```

## Anti-patterns

- Computing reputation scores directly from raw vote counts without applying weights — a single Sybil cluster of 50 accounts can trivially push a target to the highest tier
- Storing cluster membership only at cluster-build time and not at event time — if an account is later moved to a different cluster, the historical events lose their cluster attribution; record `actor_cluster_id` on each event row
- Exposing the scoring formula publicly in documentation or error messages — transparency is valuable for users but helps adversaries tune their gaming strategies; describe the system in general terms only
- Using a single global `reputation_scores` table row for atomic updates — concurrent Worker invocations can race on `score + delta`; D1's SQLite serialisation handles this for single-writer cases but verify under load
- Applying the same diminishing-returns curve to organic actions (posts, comments) as to votes — organic contributions should not be penalised; only apply multipliers to vote-type actions

## Gotchas

- D1 `COALESCE(SUM(delta), 0)` returns `null` when no rows match, not `0`; the `COALESCE` is required
- `JOIN account_cluster_members` in the rate-limit query can be slow if the cluster table is large — add an index on `account_cluster_members(cluster_id, account_id)` and cap the query with `LIMIT 100`
- The `ON CONFLICT ... DO UPDATE SET score = score + ?2` syntax requires that `score` is not the conflict target column; the conflict target is `account_id` (the primary key)
- Tier reclassification and outlier flagging run in the same scheduled event; if the event takes >30 s (Worker CPU limit), split them into two separate cron triggers
- `SUM(delta) > 50` in the outlier query operates on REAL arithmetic; floating-point accumulation errors are negligible for reputation scores but do not use this query for financial calculations

## Verification

1. Create two accounts in the same cluster; have account A upvote account B; confirm `reputation_events.weight < 1.0` after the first upvote and `weight = 0.5^1 = 0.5` for the second from the same cluster.
2. Attempt a self-upvote (actor == target); assert `accepted: false, reason: 'self_action'`.
3. Insert 5 upvote events from cluster members to the same target in under 24 h; attempt a 6th; assert `accepted: false, reason: 'cluster_cap_exceeded'`.
4. Fire the tier-reclassifier cron; confirm accounts with `score >= 100` have `tier = 'trusted'` in D1.
5. Inject 60 delta units in 1 hour via synthetic events; fire the reclassifier; confirm `audit_flag = 1` is set on the target account.
6. Call `rollbackGamedScore` with the gaming cluster; confirm `score` recalculates to the pre-gaming baseline.

## Related

- `platform-reputation-score-decay-d1-workers.md`
- `anonymous-account-graph-clustering-d1.md`
- `sock-puppet-network-detection.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `inauthentic-review-bombing-detection-d1-analytics-engine.md`
- `sybil-attack-detection-workers-ai-behavioral.md`

## Sources

- Cloudflare D1 documentation — SQLite dialect and batch API: https://developers.cloudflare.com/d1/
- Sybil attack literature review — Douceur (2002): https://dl.acm.org/doi/10.5555/646334.687813
- Reddit karma farming analysis — ACM WebSci 2019: https://dl.acm.org/doi/10.1145/3292522.3326033
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
