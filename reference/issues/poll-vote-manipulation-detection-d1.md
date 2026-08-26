# Poll Vote Manipulation Detection with D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Platform polls become a vector for coordinated manipulation: automated scripts vote en masse for a predetermined option, sock-puppet networks are activated to flip a result, or rapid option-stuffing creates false consensus signals that influence adjacent content (trending algorithms, product decisions, community sentiment). Unlike `anonymous-poll-integrity-verification.md` — which focuses on anonymous-account identity integrity — this article addresses the manipulation tactics themselves: vote-velocity anomalies, option-flip attacks, temporal clustering, and cross-account co-voting graphs.

## Context

example project polls are open to authenticated and anonymous-token users. Each vote event is recorded in D1 with a fingerprint composite (ephemeral token, IP range, device hint). Detection runs in three modes:

1. **Real-time gate** — runs in the Vote Worker at cast time; blocks or shadows the vote.
2. **Batch analytics** — Cron Trigger every 15 minutes; rescores open polls and emits manipulation signals.
3. **Post-close audit** — runs after a poll closes; recalculates final tallies with manipulated votes excluded and flags the poll for review if the corrected margin differs by ≥ 5 pp.

---

## D1 Schema

```sql
-- D1 migration: 0014_poll_votes.sql
CREATE TABLE IF NOT EXISTS poll_votes (
  id              TEXT PRIMARY KEY,     -- ULID
  poll_id         TEXT NOT NULL,
  option_id       TEXT NOT NULL,
  voter_token     TEXT NOT NULL,        -- ephemeral token or hashed user ID
  ip_prefix       TEXT NOT NULL,        -- first 24 bits of IPv4 or /48 of IPv6
  voted_at        INTEGER NOT NULL,
  weight          REAL NOT NULL DEFAULT 1.0,  -- 0 = suppressed, 1 = counted
  manipulation_flags TEXT NOT NULL DEFAULT '[]'  -- JSON array of flag codes
);

CREATE INDEX idx_pv_poll       ON poll_votes(poll_id, voted_at DESC);
CREATE INDEX idx_pv_token      ON poll_votes(voter_token, voted_at DESC);
CREATE INDEX idx_pv_ip         ON poll_votes(ip_prefix, poll_id);

CREATE TABLE IF NOT EXISTS poll_manipulation_events (
  id              TEXT PRIMARY KEY,
  poll_id         TEXT NOT NULL,
  detected_at     INTEGER NOT NULL,
  signal_type     TEXT NOT NULL,  -- velocity | ip_cluster | option_flip | co_vote
  severity        TEXT NOT NULL CHECK(severity IN ('low','medium','high')),
  detail          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_pme_poll ON poll_manipulation_events(poll_id, detected_at DESC);
```

---

## Real-Time Vote Gate

```typescript
// workers/poll-vote/gate.ts
import { Env } from '../../types';
import { ulid } from 'ulidx';

export interface VoteRequest {
  pollId: string;
  optionId: string;
  voterToken: string;
  ipPrefix: string;   // computed from CF-Connecting-IP at edge
}

export type GateDecision = 'accept' | 'shadow' | 'reject';

export async function gateVote(req: VoteRequest, env: Env): Promise<GateDecision> {
  const windowMs = 60_000; // 1-minute rolling window
  const now = Date.now();

  // 1. Deduplicate: same token already voted on this poll
  const dupRow = await env.DB.prepare(
    `SELECT id FROM poll_votes
      WHERE poll_id = ? AND voter_token = ? AND weight > 0`
  ).bind(req.pollId, req.voterToken).first<{ id: string }>();
  if (dupRow) return 'reject';

  // 2. Velocity: more than 30 votes from the same IP prefix in 60 s
  const ipVelocity = await env.DB.prepare(
    `SELECT COUNT(*) as cnt
       FROM poll_votes
      WHERE poll_id = ? AND ip_prefix = ? AND voted_at > ?`
  ).bind(req.pollId, req.ipPrefix, now - windowMs).first<{ cnt: number }>();
  if ((ipVelocity?.cnt ?? 0) > 30) {
    await emitEvent(req.pollId, 'velocity', 'high',
      { ip_prefix: req.ipPrefix, count: ipVelocity!.cnt }, env);
    return 'shadow';
  }

  // 3. Global velocity: > 500 votes on this poll in the last 60 s (burst attack)
  const globalVelocity = await env.DB.prepare(
    `SELECT COUNT(*) as cnt FROM poll_votes
      WHERE poll_id = ? AND voted_at > ?`
  ).bind(req.pollId, now - windowMs).first<{ cnt: number }>();
  if ((globalVelocity?.cnt ?? 0) > 500) {
    await emitEvent(req.pollId, 'velocity', 'high',
      { global_burst: globalVelocity!.cnt }, env);
    // Shadow rather than reject — legitimate viral traffic can hit high counts too
    return 'shadow';
  }

  return 'accept';
}

async function emitEvent(
  pollId: string,
  signalType: string,
  severity: 'low' | 'medium' | 'high',
  detail: Record<string, unknown>,
  env: Env
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR IGNORE INTO poll_manipulation_events
       (id, poll_id, detected_at, signal_type, severity, detail)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(ulid(), pollId, Date.now(), signalType, severity, JSON.stringify(detail)).run();
}
```

---

## Vote Recording with Flags

```typescript
// workers/poll-vote/record.ts
import { Env } from '../../types';
import { ulid } from 'ulidx';
import type { VoteRequest, GateDecision } from './gate';

export async function recordVote(
  req: VoteRequest,
  decision: GateDecision,
  env: Env
): Promise<string> {
  const id = ulid();
  const weight = decision === 'accept' ? 1.0 : 0.0;
  const flags = decision === 'shadow' ? ['shadow_drop'] : [];

  await env.DB.prepare(
    `INSERT INTO poll_votes
       (id, poll_id, option_id, voter_token, ip_prefix, voted_at, weight, manipulation_flags)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id, req.pollId, req.optionId, req.voterToken,
    req.ipPrefix, Date.now(), weight, JSON.stringify(flags)
  ).run();

  return id;
}
```

---

## Batch Analyser: IP Cluster Detection

```typescript
// workers/poll-vote/batch-analyse.ts
import { Env } from '../../types';
import { ulid } from 'ulidx';

/**
 * Detects IP-cluster attacks: multiple /24 prefixes that vote on the same
 * option within a short window, suggesting an ASN-level coordinated attack.
 */
export async function detectIpCluster(pollId: string, env: Env): Promise<void> {
  // Find option-ip_prefix combinations with unusually high counts
  const rows = await env.DB.prepare(
    `SELECT option_id, ip_prefix, COUNT(*) as cnt
       FROM poll_votes
      WHERE poll_id = ? AND weight = 1
      GROUP BY option_id, ip_prefix
     HAVING cnt > 5`
  ).bind(pollId).all<{ option_id: string; ip_prefix: string; cnt: number }>();

  // Group by /16 (first 16 bits of IP prefix) to catch subnet-wide attacks
  const subnetMap = new Map<string, { options: Set<string>; totalVotes: number }>();
  for (const row of rows.results) {
    const subnet16 = row.ip_prefix.split('.').slice(0, 2).join('.');
    const entry = subnetMap.get(subnet16) ?? { options: new Set(), totalVotes: 0 };
    entry.options.add(row.option_id);
    entry.totalVotes += row.cnt;
    subnetMap.set(subnet16, entry);
  }

  for (const [subnet, { options, totalVotes }] of subnetMap) {
    if (totalVotes >= 50 && options.size === 1) {
      // All votes from this subnet block go to a single option — high signal
      const severity = totalVotes >= 200 ? 'high' : 'medium';
      await env.DB.prepare(
        `INSERT OR IGNORE INTO poll_manipulation_events
           (id, poll_id, detected_at, signal_type, severity, detail)
         VALUES (?, ?, ?, 'ip_cluster', ?, ?)`
      ).bind(
        ulid(), pollId, Date.now(), severity,
        JSON.stringify({ subnet16: subnet, total_votes: totalVotes, options: [...options] })
      ).run();

      // Suppress votes from this subnet for this poll
      await env.DB.prepare(
        `UPDATE poll_votes SET weight = 0,
           manipulation_flags = json_insert(manipulation_flags, '$[#]', 'ip_cluster')
         WHERE poll_id = ? AND ip_prefix LIKE ?`
      ).bind(pollId, `${subnet}.%`).run();
    }
  }
}
```

---

## Post-Close Tally Correction

```typescript
// workers/poll-vote/post-close.ts
import { Env } from '../../types';

export interface TallyResult {
  optionId: string;
  rawVotes: number;
  cleanVotes: number;
  deltaPercent: number;
}

export async function auditFinalTally(pollId: string, env: Env): Promise<TallyResult[]> {
  const rawRows = await env.DB.prepare(
    `SELECT option_id, COUNT(*) as cnt
       FROM poll_votes WHERE poll_id = ?
       GROUP BY option_id`
  ).bind(pollId).all<{ option_id: string; cnt: number }>();

  const cleanRows = await env.DB.prepare(
    `SELECT option_id, COUNT(*) as cnt
       FROM poll_votes WHERE poll_id = ? AND weight = 1
       GROUP BY option_id`
  ).bind(pollId).all<{ option_id: string; cnt: number }>();

  const rawTotal = rawRows.results.reduce((s, r) => s + r.cnt, 0);
  const cleanTotal = cleanRows.results.reduce((s, r) => s + r.cnt, 0);
  const cleanMap = new Map(cleanRows.results.map(r => [r.option_id, r.cnt]));

  const results: TallyResult[] = rawRows.results.map(r => {
    const clean = cleanMap.get(r.option_id) ?? 0;
    const rawPct = rawTotal > 0 ? (r.cnt / rawTotal) * 100 : 0;
    const cleanPct = cleanTotal > 0 ? (clean / cleanTotal) * 100 : 0;
    return {
      optionId: r.option_id,
      rawVotes: r.cnt,
      cleanVotes: clean,
      deltaPercent: Math.abs(rawPct - cleanPct),
    };
  });

  // If any option's share shifts by ≥ 5 pp after cleaning, flag the poll
  const maxDelta = Math.max(...results.map(r => r.deltaPercent));
  if (maxDelta >= 5) {
    await env.DB.prepare(
      `UPDATE polls SET manipulation_flag = 1, max_tally_delta = ? WHERE id = ?`
    ).bind(maxDelta, pollId).run();
  }

  return results;
}
```

---

## Anti-patterns

- **Using only raw vote counts for result display.** Always render `weight = 1` counts as the canonical tally, and display a "results under review" badge when `manipulation_flag = 1`.
- **Blocking all votes from a subnet at the gate.** Blanket IP blocks cause false positives for legitimate users on shared corporate NAT or mobile carrier IPs. Shadow-drop at the gate; suppress weights in batch; only block at the gate for extreme velocity (> 100 votes/min from one /24).
- **Exposing `weight` or flag data to the vote submitter.** Adversaries use this feedback to tune their evasion. Return `200 OK` for shadow votes with the same response shape as accepted votes.
- **Running post-close audit synchronously.** Use a Queue consumer triggered on poll-close events, not an inline Worker call.

---

## Gotchas

- D1 `json_insert(manipulation_flags, '$[#]', 'ip_cluster')` works in SQLite 3.38+ (D1's bundled version as of 2026-Q1). The `$[#]` path appends to the end of a JSON array; verify the behaviour with `wrangler d1 execute --local`.
- IPv6 presents as a /128 from `CF-Connecting-IP`. Use the first 48 bits (`/48 prefix`) as the grouping key to match on plausible network segments; pure /128 grouping defeats subnet clustering detection.
- Cron-triggered batch jobs on large polls (> 100 k votes) may hit D1's 30-second query timeout. Paginate the `ip_prefix` aggregation with `LIMIT 1000 OFFSET ?` and process in chunks.
- Poll results cached in KV or at CDN edge may serve stale tallies after weight corrections. Invalidate the KV cache key (`poll:${pollId}:results`) immediately after any batch suppression run.

---

## Verification

```bash
# Check shadow-drop rate on a specific poll
wrangler d1 execute example project-prod --command \
  "SELECT weight, COUNT(*) FROM poll_votes WHERE poll_id = 'POLL_ID' GROUP BY weight"

# List high-severity manipulation events in last 48 h
wrangler d1 execute example project-prod --command \
  "SELECT poll_id, signal_type, severity, detail FROM poll_manipulation_events
    WHERE severity = 'high' AND detected_at > (strftime('%s','now') - 172800) * 1000"

# Confirm tally delta on closed polls
wrangler d1 execute example project-prod --command \
  "SELECT id, max_tally_delta FROM polls WHERE manipulation_flag = 1 ORDER BY max_tally_delta DESC LIMIT 20"
```

---

## Related

- `anonymous-poll-integrity-verification.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `sock-puppet-network-detection.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `temporal-pattern-manipulation-detection.md`

---

## Sources

- Cloudflare D1 JSON functions — https://developers.cloudflare.com/d1/reference/sql-api/
- SQLite JSON5 path syntax — https://www.sqlite.org/json1.html
- "Manipulation of Online Polls" — ACM FAT* 2020, Procaccia et al.
- example project poll-integrity design spec v4 (internal wiki, 2026-Q1)
