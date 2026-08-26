# Temporal Pattern Manipulation Detection

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

example project platform analysts notice that certain content systematically trends at predictable intervals — midnight UTC spikes every night, or waves of activity peaking on the hour precisely. Real organic communities behave with natural timing variance; synthetic activity arrives on a suspiciously regular clock. Adversaries exploit temporal regularity to inflate algorithmic signals (trending topics, hot posts) using automated scripts that stagger posts across time without realising the mechanical rhythm betrays them.

## Context

Temporal pattern analysis is a low-cost, high-signal abuse detection layer because it requires no content inspection — only timestamps. Genuine human posting follows irregular Poisson-like distributions with circadian structure; bot-driven posting follows discrete cron schedules or constant inter-arrival times. D1 stores the timestamp series and scheduled Workers compute distribution statistics. Flagged sessions are cross-referenced with other trust signals before action.

---

## 1. Action Timestamp Ingestion Schema

```sql
CREATE TABLE IF NOT EXISTS session_actions (
  action_id    TEXT PRIMARY KEY,
  session_hash TEXT NOT NULL,
  action_type  TEXT NOT NULL,   -- 'post' | 'like' | 'reply' | 'boost'
  acted_at     INTEGER NOT NULL -- Unix ms
);

CREATE INDEX idx_actions_session ON session_actions (session_hash, acted_at);
CREATE INDEX idx_actions_time    ON session_actions (acted_at);

-- Precomputed inter-arrival stats per session
CREATE TABLE IF NOT EXISTS session_iat_stats (
  session_hash TEXT PRIMARY KEY,
  sample_count INTEGER NOT NULL,
  mean_iat_ms  REAL NOT NULL,
  stddev_iat_ms REAL NOT NULL,
  cv           REAL NOT NULL,   -- coefficient of variation = stddev / mean
  updated_at   INTEGER NOT NULL
);
```

---

## 2. Inter-arrival Time (IAT) Computation

Compute the inter-arrival times for a session's actions over a rolling 24-hour window.

```typescript
interface IATStats {
  sampleCount: number;
  meanMs: number;
  stddevMs: number;
  cv: number; // coefficient of variation
}

export async function computeSessionIAT(
  sessionHash: string,
  env: Env,
): Promise<IATStats | null> {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;

  const rows = await env.DB.prepare(
    `SELECT acted_at FROM session_actions
     WHERE session_hash = ? AND acted_at > ?
     ORDER BY acted_at ASC`,
  ).bind(sessionHash, cutoff).all<{ acted_at: number }>();

  const timestamps = rows.results.map((r) => r.acted_at);
  if (timestamps.length < 3) return null; // not enough data

  const iats: number[] = [];
  for (let i = 1; i < timestamps.length; i++) {
    iats.push(timestamps[i] - timestamps[i - 1]);
  }

  const n = iats.length;
  const mean = iats.reduce((a, b) => a + b, 0) / n;
  const variance = iats.reduce((s, x) => s + (x - mean) ** 2, 0) / n;
  const stddev = Math.sqrt(variance);
  const cv = mean > 0 ? stddev / mean : 0;

  return { sampleCount: n, meanMs: mean, stddevMs: stddev, cv };
}
```

Low CV (< 0.3) indicates mechanically regular timing — a strong bot signal. Human CV typically ranges 0.8–2.5.

---

## 3. Cron-like Pattern Detection

Detect sessions whose action timestamps cluster on round-minute or round-hour boundaries.

```typescript
export async function detectCronAlignment(
  sessionHash: string,
  env: Env,
): Promise<number> {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;

  const rows = await env.DB.prepare(
    `SELECT acted_at FROM session_actions
     WHERE session_hash = ? AND acted_at > ?`,
  ).bind(sessionHash, cutoff).all<{ acted_at: number }>();

  if (rows.results.length < 5) return 0;

  const timestamps = rows.results.map((r) => r.acted_at);

  // How many actions fall within ±3 s of a round minute?
  const nearRoundMinute = timestamps.filter((ts) => {
    const secondsWithinMinute = (ts / 1000) % 60;
    return secondsWithinMinute <= 3 || secondsWithinMinute >= 57;
  }).length;

  return nearRoundMinute / timestamps.length; // 0-1; > 0.6 is suspicious
}
```

---

## 4. Scheduled Batch Scoring Worker

Evaluate all sessions active in the past 24 hours and write composite temporal risk scores.

```typescript
// wrangler.toml: [triggers] crons = ["0 */2 * * *"]
export async function scoreSessions(env: Env): Promise<void> {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;

  const activeSessions = await env.DB.prepare(
    `SELECT DISTINCT session_hash FROM session_actions WHERE acted_at > ?`,
  ).bind(cutoff).all<{ session_hash: string }>();

  const updates: D1PreparedStatement[] = [];

  for (const { session_hash } of activeSessions.results) {
    const iat = await computeSessionIAT(session_hash, env);
    if (!iat) continue;

    const cronScore = await detectCronAlignment(session_hash, env);

    // Low CV = high regularity; map to 0-1 risk contribution
    const iatRisk = iat.cv < 0.3 ? 1 - iat.cv / 0.3 : 0;
    const composite = 0.5 * iatRisk + 0.5 * cronScore;

    updates.push(
      env.DB.prepare(
        `INSERT OR REPLACE INTO session_iat_stats
         (session_hash, sample_count, mean_iat_ms, stddev_iat_ms, cv, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
      ).bind(
        session_hash,
        iat.sampleCount,
        iat.meanMs,
        iat.stddevMs,
        iat.cv,
        Date.now(),
      ),
    );

    if (composite >= 0.7) {
      updates.push(
        env.DB.prepare(
          `INSERT OR IGNORE INTO temporal_risk_flags
           (session_hash, composite_score, flagged_at)
           VALUES (?, ?, ?)`,
        ).bind(session_hash, composite, Date.now()),
      );
    }

    // Flush in batches of 50 to stay within D1 batch limits
    if (updates.length >= 50) {
      await env.DB.batch(updates.splice(0, 50));
    }
  }

  if (updates.length > 0) await env.DB.batch(updates);
}
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS temporal_risk_flags (
  session_hash    TEXT PRIMARY KEY,
  composite_score REAL NOT NULL,
  flagged_at      INTEGER NOT NULL,
  reviewed        INTEGER NOT NULL DEFAULT 0
);
```

---

## 5. Platform-wide Burst Detection

Detect coordinated bursts — many sessions acting within a narrow time window across the whole platform, not just per-session.

```typescript
export async function detectCoordinatedBurst(
  windowMs: number,
  threshold: number,
  env: Env,
): Promise<boolean> {
  const cutoff = Date.now() - windowMs;

  const row = await env.DB.prepare(
    `SELECT COUNT(DISTINCT session_hash) AS session_count
     FROM session_actions
     WHERE acted_at > ?`,
  ).bind(cutoff).first<{ session_count: number }>();

  const sessionCount = row?.session_count ?? 0;

  // Compare against trailing average from KV
  const avgStr = await env.KV.get("metrics:avg_sessions_per_window");
  const avg = avgStr ? parseFloat(avgStr) : sessionCount;

  // More than 5× trailing average in the window = coordinated burst
  return sessionCount > avg * 5;
}
```

---

## Anti-patterns

- **Using wall-clock UTC hours as the sole signal**: legitimate global platforms have natural UTC midnight spikes from specific timezones; normalise for geography before flagging.
- **Flagging on a single low-CV observation**: a session that posts exactly 5 times quickly at session start may have low CV trivially; require at least 10 data points.
- **Computing IAT in the hot Worker path**: IAT computation is expensive for large timestamp sets; always compute in a scheduled background Worker and read pre-computed scores at decision time.
- **Treating temporal flags as definitive bot signals alone**: temporal regularity is a necessary but not sufficient signal; cross-reference with IP diversity, content entropy, and engagement graph signals.
- **Deleting `session_actions` aggressively**: retaining at least 7 days of timestamps is needed for multi-day rhythm detection (e.g., bots active only on weekday mornings).

## Gotchas

- SQLite's `%` modulo operator works on integers; dividing `acted_at` (milliseconds) by 1000 before applying modulo 60 is required to get seconds-within-minute correctly.
- D1 does not have a native `STDDEV` aggregate function; compute variance in TypeScript after fetching the timestamp array, not in SQL.
- `COUNT(DISTINCT session_hash)` in the burst query can be slow on large `session_actions` tables; add a partial index on `acted_at` descending or use Analytics Engine for real-time burst monitoring instead.
- The batch size limit for `env.DB.batch()` is 100 statements; the example flushes at 50 for safety margin.
- `cv = 0` for a session with exactly 2 actions (one IAT); that is why the minimum sample count is set to 3 (2 IATs) before computing stats.

## Verification

1. Insert 20 actions for a test session at exactly 30-second intervals; confirm `cv` in `session_iat_stats` is < 0.05 and `composite_score >= 0.7`.
2. Insert 20 actions for a human-simulated session with random gaps (10–300 s); confirm `cv > 0.8` and no `temporal_risk_flags` row.
3. Confirm `detectCronAlignment` returns > 0.8 for a session where all 10 actions are within 2 seconds of a round minute.
4. Simulate a burst of 200 distinct sessions in a 5-minute window vs. a KV baseline of 40; confirm `detectCoordinatedBurst` returns `true`.
5. Verify the cron Worker completes within 30 seconds for 1000 active sessions (benchmark in a staging environment).

## Related

- `sock-puppet-network-detection.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `viral-content-cascade-rate-limiting-durable-objects.md`
- `repeat-offender-detection-anonymous-sessions.md`

## Sources

- "BotOrNot: A System to Evaluate the Credibility of Twitter Accounts" — Varol et al., ICWSM 2017 (IAT methodology)
- Cloudflare Workers scheduled events documentation
- D1 SQL reference — index usage and modulo arithmetic
- "Detecting Synchronized Behaviour in Social Bot Campaigns" — IEEE TIFS 2024
