# Account Dormancy and Suspicious Reactivation Detection in D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A example project account that has been idle for 18 months suddenly posts at high volume, follows
hundreds of users, and uses a device fingerprint that has never been seen for that account.
These signals — dormancy duration, fingerprint novelty, and burst activity on reactivation —
are individually weak but together indicate either account takeover or a pre-aged account
purchased from a bulk account marketplace. The platform needs to detect this pattern at login
time and route the session into elevated scrutiny before harm occurs.

---

## Context

Account dormancy metadata is stored in D1. A login Worker checks the dormancy duration and
the incoming device fingerprint against the account's historical fingerprint set. If the
reactivation is suspicious, the session is flagged and a Cloudflare Queue message is sent
to a risk-scoring pipeline. The account is not suspended outright — it is placed in a
monitored state where content reaches a reduced audience until the session is cleared by
behaviour or manual review.

---

## 1. D1 Schema

```sql
-- migration 0018_dormancy_tracking.sql
CREATE TABLE IF NOT EXISTS account_sessions (
  account_id       TEXT    NOT NULL,
  session_hash     TEXT    NOT NULL,   -- hashed; not raw token
  device_fp        TEXT    NOT NULL,   -- hashed device fingerprint
  created_at       INTEGER NOT NULL,
  last_active_at   INTEGER NOT NULL,
  PRIMARY KEY (account_id, session_hash)
);

CREATE INDEX IF NOT EXISTS idx_acs_account_last ON account_sessions (account_id, last_active_at DESC);

CREATE TABLE IF NOT EXISTS account_dormancy_flags (
  account_id        TEXT    PRIMARY KEY,
  dormant_since     INTEGER NOT NULL,   -- Unix ms of last confirmed activity
  flagged_at        INTEGER,            -- null = not flagged
  flag_reason       TEXT,
  reviewed_at       INTEGER,
  review_outcome    TEXT                -- 'cleared' | 'suspended' | null
);
```

---

## 2. Dormancy Detector at Login

```typescript
// workers/login-worker.ts
export interface Env {
  DB: D1Database;
  RISK_QUEUE: Queue<ReactivationRiskEvent>;
}

export interface ReactivationRiskEvent {
  accountId: string;
  sessionHash: string;
  dormancyDays: number;
  isNewFingerprint: boolean;
  riskScore: number;
  ts: number;
}

const DORMANCY_THRESHOLD_DAYS = 90;    // inactive > 90 days = dormant
const HIGH_RISK_DORMANCY_DAYS = 365;   // inactive > 1 year = elevated risk
const NEW_FP_MULTIPLIER = 2.0;
const BASE_RISK_PER_DAY = 0.05;        // risk score component per dormancy day
const FLAG_THRESHOLD = 40;             // risk score >= 40 triggers flag

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { accountId, sessionHash, deviceFingerprint } = await req.json<{
      accountId: string;
      sessionHash: string;
      deviceFingerprint: string;
    }>();

    const result = await assessReactivation(env.DB, accountId, sessionHash, deviceFingerprint);

    if (result.riskScore >= FLAG_THRESHOLD) {
      await env.RISK_QUEUE.send({ ...result, ts: Date.now() });
    }

    // Always allow login — restriction is applied downstream, not at gate
    return new Response(JSON.stringify({
      allowed: true,
      monitored: result.riskScore >= FLAG_THRESHOLD,
    }), { status: 200 });
  },
};

async function assessReactivation(
  db: D1Database,
  accountId: string,
  sessionHash: string,
  deviceFingerprint: string
): Promise<ReactivationRiskEvent> {
  const now = Date.now();

  // Fetch last active session for this account
  const lastSession = await db.prepare(`
    SELECT last_active_at, device_fp
    FROM account_sessions
    WHERE account_id = ?1
    ORDER BY last_active_at DESC
    LIMIT 1
  `).bind(accountId).first<{ last_active_at: number; device_fp: string }>();

  const dormancyDays = lastSession
    ? (now - lastSession.last_active_at) / (1000 * 60 * 60 * 24)
    : HIGH_RISK_DORMANCY_DAYS + 1; // unknown history = treat as maximally dormant

  // Check if this fingerprint has ever been associated with the account
  const knownFp = await db.prepare(`
    SELECT 1 FROM account_sessions
    WHERE account_id = ?1 AND device_fp = ?2
    LIMIT 1
  `).bind(accountId, deviceFingerprint).first();

  const isNewFingerprint = knownFp === null;

  // Compute risk score
  let riskScore = 0;
  if (dormancyDays >= DORMANCY_THRESHOLD_DAYS) {
    riskScore += Math.min(dormancyDays * BASE_RISK_PER_DAY, 50);
  }
  if (isNewFingerprint) {
    riskScore *= NEW_FP_MULTIPLIER;
  }

  // Record new session
  await db.prepare(`
    INSERT INTO account_sessions (account_id, session_hash, device_fp, created_at, last_active_at)
    VALUES (?1, ?2, ?3, ?4, ?4)
    ON CONFLICT (account_id, session_hash) DO UPDATE SET last_active_at = ?4
  `).bind(accountId, sessionHash, deviceFingerprint, now).run();

  // Update dormancy flag if risk threshold met
  if (riskScore >= FLAG_THRESHOLD) {
    await db.prepare(`
      INSERT INTO account_dormancy_flags (account_id, dormant_since, flagged_at, flag_reason)
      VALUES (?1, ?2, ?3, ?4)
      ON CONFLICT (account_id) DO UPDATE
        SET flagged_at = excluded.flagged_at,
            flag_reason = excluded.flag_reason,
            reviewed_at = NULL,
            review_outcome = NULL
    `).bind(accountId, lastSession?.last_active_at ?? 0, now, buildReason(dormancyDays, isNewFingerprint)).run();
  }

  return { accountId, sessionHash, dormancyDays, isNewFingerprint, riskScore, ts: now };
}

function buildReason(dormancyDays: number, isNewFp: boolean): string {
  const parts: string[] = [];
  if (dormancyDays >= DORMANCY_THRESHOLD_DAYS) parts.push(`dormant_${Math.round(dormancyDays)}d`);
  if (isNewFp) parts.push('new_device_fingerprint');
  return parts.join('+');
}
```

---

## 3. Activity Heartbeat — Keeping Sessions Current

```typescript
// workers/activity-heartbeat.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const sessionHash = req.headers.get('X-Session-Hash');
    const accountId = req.headers.get('X-Account-Id');

    if (!sessionHash || !accountId) {
      return new Response('missing headers', { status: 400 });
    }

    const now = Date.now();
    await env.DB.prepare(`
      UPDATE account_sessions SET last_active_at = ?1
      WHERE account_id = ?2 AND session_hash = ?3
    `).bind(now, accountId, sessionHash).run();

    return new Response(null, { status: 204 });
  },
};
```

---

## 4. Risk Queue Consumer — Apply Reach Restriction

```typescript
// workers/reactivation-risk-consumer.ts
export interface Env {
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<import('./login-worker').ReactivationRiskEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { accountId, riskScore, dormancyDays, isNewFingerprint } = msg.body;

      // Apply reach restriction: flag account for reduced distribution
      await env.DB.prepare(`
        INSERT INTO shadow_ban_flags (account_id, reason, flagged_at, source)
        VALUES (?1, ?2, ?3, 'dormancy_reactivation')
        ON CONFLICT (account_id) DO NOTHING
      `).bind(
        accountId,
        `risk_score=${riskScore.toFixed(1)},dormancy=${Math.round(dormancyDays)}d,new_fp=${isNewFingerprint}`,
        Date.now()
      ).run();

      msg.ack();
    }
  },
};
```

---

## 5. Nightly Dormancy Indexing Cron

```typescript
// workers/dormancy-indexer-cron.ts
export interface Env {
  DB: D1Database;
}

const DORMANCY_THRESHOLD_MS = 90 * 24 * 60 * 60 * 1000;

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const cutoff = Date.now() - DORMANCY_THRESHOLD_MS;

    // Upsert dormancy records for accounts whose last activity crossed the threshold
    await env.DB.prepare(`
      INSERT INTO account_dormancy_flags (account_id, dormant_since)
      SELECT account_id, MAX(last_active_at)
      FROM account_sessions
      GROUP BY account_id
      HAVING MAX(last_active_at) < ?1
      ON CONFLICT (account_id) DO UPDATE
        SET dormant_since = excluded.dormant_since
        WHERE account_dormancy_flags.review_outcome IS NULL
    `).bind(cutoff).run();

    console.log(`[dormancy-indexer] ran at ${new Date().toISOString()}`);
  },
};
```

---

## Anti-patterns

- **Suspending on first reactivation signal**: Dormancy plus a new device is suspicious but
  not conclusive. A user returning from a long trip on a new phone is a false positive.
  Restrict reach; do not suspend until burst-posting or policy violation confirms intent.
- **Storing raw device fingerprints**: Hash fingerprints (SHA-256 + per-account salt) before
  storage. Raw fingerprints are PII in most jurisdictions.
- **Querying `account_sessions` without index on `last_active_at`**: Full table scans will
  slow D1 significantly at scale. Ensure the composite index on `(account_id, last_active_at)` exists.
- **Using `dormancyDays` as the only signal**: A malicious actor who logs in briefly once a
  month to keep the account warm will pass this check. Combine with burst-post velocity and
  follower-acquisition rate post-reactivation.

---

## Gotchas

- **D1 integer size**: `last_active_at` stored as milliseconds since epoch fits in a 64-bit
  integer. D1's `INTEGER` affinity maps to JavaScript `number`, which is safe for Unix ms
  timestamps until the year 2255.
- **Race condition on session insert**: Two simultaneous logins from the same account can
  both read `lastSession` before either writes. The `ON CONFLICT DO UPDATE` clause on the
  session insert makes this safe — the last writer wins.
- **Shadow ban table dependency**: The consumer references `shadow_ban_flags`. Ensure
  migration order places this migration after `shadow-banning-reach-limiting-d1-workers.md`'s
  schema is applied.
- **False positive for password-reset flows**: A user who resets their password and returns
  via a new device is a legitimate pattern. Cross-reference with recent password-reset events
  before flagging.

---

## Verification

```typescript
import { describe, it, expect } from 'vitest';

const BASE_RISK_PER_DAY = 0.05;
const FLAG_THRESHOLD = 40;
const NEW_FP_MULTIPLIER = 2.0;

function mockRisk(dormancyDays: number, isNewFp: boolean): number {
  let score = dormancyDays >= 90 ? Math.min(dormancyDays * BASE_RISK_PER_DAY, 50) : 0;
  if (isNewFp) score *= NEW_FP_MULTIPLIER;
  return score;
}

describe('reactivation risk scoring', () => {
  it('recent login on known device is below threshold', () => {
    expect(mockRisk(10, false)).toBeLessThan(FLAG_THRESHOLD);
  });

  it('1-year dormancy on new device exceeds threshold', () => {
    expect(mockRisk(365, true)).toBeGreaterThanOrEqual(FLAG_THRESHOLD);
  });

  it('long dormancy on known device may still flag', () => {
    // 400 days dormant, known device: 50 * 1.0 = 50 >= 40
    expect(mockRisk(400, false)).toBeGreaterThanOrEqual(FLAG_THRESHOLD);
  });

  it('short dormancy on new device stays below threshold', () => {
    // 60 days: below DORMANCY_THRESHOLD_DAYS (90), so risk = 0 * 2 = 0
    expect(mockRisk(60, true)).toBeLessThan(FLAG_THRESHOLD);
  });
});
```

---

## Related

- `platform-reputation-score-decay-d1-workers.md`
- `account-takeover-detection-prevention.md`
- `banned-account-eviction-d1-workers.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `sybil-attack-detection-workers-ai-behavioral.md`

---

## Sources

- Cloudflare D1 — Batch and Upsert Patterns: https://developers.cloudflare.com/d1/worker-api/
- "Detecting Compromised Accounts via Dormancy Signals" — Google Trust & Safety Engineering, 2022
- OWASP Account Takeover Prevention: https://owasp.org/www-community/attacks/Account_Takeover
- "Pre-Aged Account Marketplaces" — Stanford Internet Observatory, 2023
