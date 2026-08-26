# Account Merge Duplicate Identity D1 Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user holds two accounts on example project — one created via Farcaster, one via email — and wants them unified. Alternatively, moderation detects two accounts belong to the same real identity and must be collapsed (duplicate identity enforcement). Both cases need a merge that preserves content, transfers reputation, and leaves a redirect tombstone so old links resolve.

## Context

example project uses anonymous IDs (`wam_<ulid>`) as primary keys throughout D1. Merging two accounts means: picking a canonical `primary_id`, repointing all foreign-key references from the `secondary_id`, writing a tombstone row, and atomically updating KV cache entries. The whole operation must be idempotent in case of mid-flight Worker crash and safe to replay.

---

## Merge Eligibility Check

Before merging, assert that neither account is banned, neither is under a legal hold, and the two have not already been merged.

```typescript
interface MergeCandidate {
  id: string;
  status: 'active' | 'suspended' | 'banned';
  legalHold: boolean;
  mergedInto?: string;
}

async function assertMergeEligible(
  db: D1Database,
  primaryId: string,
  secondaryId: string,
): Promise<void> {
  const rows = await db.prepare(
    `SELECT id, status, legal_hold as legalHold, merged_into as mergedInto
     FROM accounts WHERE id IN (?, ?)`,
  ).bind(primaryId, secondaryId).all<MergeCandidate>();

  const map = new Map(rows.results.map(r => [r.id, r]));
  for (const id of [primaryId, secondaryId]) {
    const acct = map.get(id);
    if (!acct) throw new Error(`Account ${id} not found`);
    if (acct.status === 'banned') throw new Error(`Account ${id} is banned`);
    if (acct.legalHold) throw new Error(`Account ${id} is under legal hold`);
    if (acct.mergedInto) throw new Error(`Account ${id} already merged into ${acct.mergedInto}`);
  }
}
```

## Merge Transaction — Foreign Key Repoint

D1 does not support cross-statement transactions with deferred FKs, so each table is updated individually. A `merge_jobs` table tracks progress so replays are safe.

```typescript
const MERGE_STEPS = [
  { table: 'posts',         col: 'author_id' },
  { table: 'reactions',     col: 'actor_id'  },
  { table: 'reports',       col: 'reporter_id' },
  { table: 'follows',       col: 'follower_id' },
  { table: 'follows',       col: 'followed_id' },
  { table: 'dm_participants', col: 'account_id' },
] as const;

async function executeMergeSteps(
  db: D1Database,
  primaryId: string,
  secondaryId: string,
  jobId: string,
): Promise<void> {
  const completed = await db.prepare(
    `SELECT step FROM merge_job_steps WHERE job_id = ?`,
  ).bind(jobId).all<{ step: string }>();
  const done = new Set(completed.results.map(r => r.step));

  for (const { table, col } of MERGE_STEPS) {
    const stepKey = `${table}.${col}`;
    if (done.has(stepKey)) continue; // idempotent replay

    await db.prepare(
      `UPDATE ${table} SET ${col} = ? WHERE ${col} = ?`,
    ).bind(primaryId, secondaryId).run();

    await db.prepare(
      `INSERT OR IGNORE INTO merge_job_steps (job_id, step, completed_at)
       VALUES (?, ?, ?)`,
    ).bind(jobId, stepKey, Date.now()).run();
  }
}
```

## Reputation Score Transfer

Reputation is additive: the primary account absorbs the secondary's score, clipped to platform max, and a decay penalty is applied to discourage merge-farming.

```typescript
const MAX_REPUTATION = 10_000;
const MERGE_DECAY_FACTOR = 0.85; // secondary score transferred at 85%

async function transferReputation(
  db: D1Database,
  primaryId: string,
  secondaryId: string,
): Promise<void> {
  const sec = await db.prepare(
    `SELECT reputation_score FROM accounts WHERE id = ?`,
  ).bind(secondaryId).first<{ reputation_score: number }>();

  if (!sec) return;
  const transfer = Math.floor(sec.reputation_score * MERGE_DECAY_FACTOR);

  await db.prepare(
    `UPDATE accounts
     SET reputation_score = MIN(reputation_score + ?, ?)
     WHERE id = ?`,
  ).bind(transfer, MAX_REPUTATION, primaryId).run();
}
```

## Tombstone and Redirect

The secondary account row is not deleted — it becomes a redirect tombstone so old links resolve via a 301.

```typescript
async function writeTombstone(
  db: D1Database,
  kv: KVNamespace,
  primaryId: string,
  secondaryId: string,
  mergedBy: string,
): Promise<void> {
  await db.prepare(
    `UPDATE accounts
     SET status = 'merged', merged_into = ?, merged_at = ?, merged_by = ?
     WHERE id = ?`,
  ).bind(primaryId, Date.now(), mergedBy, secondaryId).run();

  // KV redirect for edge-fast 301
  await kv.put(
    `account_redirect:${secondaryId}`,
    primaryId,
    { expirationTtl: 60 * 60 * 24 * 365 }, // 1 year
  );
}

// Edge redirect handler
export async function handleProfileRequest(
  id: string,
  kv: KVNamespace,
): Promise<Response | null> {
  const canonical = await kv.get(`account_redirect:${id}`);
  if (canonical) {
    return Response.redirect(`/u/${canonical}`, 301);
  }
  return null;
}
```

## Merge Orchestration Worker

Ties all steps together, writes job record, marks completion.

```typescript
export async function mergeAccounts(
  env: { DB: D1Database; KV: KVNamespace },
  primaryId: string,
  secondaryId: string,
  triggeredBy: string,
  reason: 'user_request' | 'moderation_duplicate',
): Promise<{ jobId: string }> {
  await assertMergeEligible(env.DB, primaryId, secondaryId);

  const jobId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO merge_jobs (id, primary_id, secondary_id, triggered_by, reason, started_at)
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).bind(jobId, primaryId, secondaryId, triggeredBy, reason, Date.now()).run();

  await executeMergeSteps(env.DB, primaryId, secondaryId, jobId);
  await transferReputation(env.DB, primaryId, secondaryId);
  await writeTombstone(env.DB, env.KV, primaryId, secondaryId, triggeredBy);

  await env.DB.prepare(
    `UPDATE merge_jobs SET completed_at = ? WHERE id = ?`,
  ).bind(Date.now(), jobId).run();

  return { jobId };
}
```

## Duplicate Detection via Signal Overlap

Moderation tooling flags pairs where ≥3 signals overlap (IP subnet, device fingerprint, email domain, post timing).

```typescript
async function findDuplicateCandidates(
  db: D1Database,
  accountId: string,
): Promise<Array<{ candidateId: string; signals: string[] }>> {
  const rows = await db.prepare(
    `SELECT a2.id as candidateId,
            GROUP_CONCAT(s.signal_type) as signals,
            COUNT(*) as overlap
     FROM account_signals s1
     JOIN account_signals s2 ON s1.signal_value = s2.signal_value
                             AND s1.signal_type  = s2.signal_type
     JOIN accounts a2 ON a2.id = s2.account_id
     JOIN account_signals s ON s.account_id = s2.account_id
     WHERE s1.account_id = ?
       AND s2.account_id != ?
       AND a2.status = 'active'
     GROUP BY a2.id
     HAVING overlap >= 3
     ORDER BY overlap DESC LIMIT 20`,
  ).bind(accountId, accountId).all<{ candidateId: string; signals: string }>();

  return rows.results.map(r => ({
    candidateId: r.candidateId,
    signals: r.signals.split(','),
  }));
}
```

---

## Anti-patterns

- Deleting the secondary account row — breaks content integrity, removes audit trail, invalidates old share links.
- Running all UPDATE statements in a single Workers fetch without step-tracking — a CPU-limit eviction leaves the database in a half-migrated state.
- Merging banned accounts into active ones — the banned account's violations must not be laundered into the primary.
- Allowing users to choose which account is secondary without moderator review — can be exploited to reset ban flags.

## Gotchas

- D1 `UPDATE` is not atomic across tables. Use `merge_job_steps` as a checkpoint log so replays skip completed steps.
- `follows` table has two foreign keys (`follower_id`, `followed_id`). Both must be repointed separately.
- After merge, unique-constraint violations on `follows` (primary already follows someone the secondary followed) must be caught and silently ignored.
- KV redirect TTL should be long (≥1 year). Expiry before all crawlers update their indexes creates dead links.

## Verification

```bash
# Confirm secondary is tombstoned
wrangler d1 execute example project-db --command \
  "SELECT id, status, merged_into FROM accounts WHERE id = '<secondary_id>'"

# Confirm posts repointed
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) FROM posts WHERE author_id = '<secondary_id>'"  # expect 0

# Check KV redirect
wrangler kv key get "account_redirect:<secondary_id>" --namespace-id=$KV_ID

# Replay safety: re-run merge and confirm no-op (step rows already exist)
```

---

## Related

- `anonymous-account-graph-clustering-d1.md`
- `sock-puppet-network-detection.md`
- `platform-reputation-score-decay-d1-workers.md`
- `platform-audit-log-immutable-d1-workers.md`
- `banned-account-eviction-d1-workers.md`

## Sources

- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- DSA Article 23 (transparency reporting on repeat offenders) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
