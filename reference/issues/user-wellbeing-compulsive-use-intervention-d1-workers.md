# User Wellbeing & Compulsive-Use Intervention — D1 & Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Trust & Safety receives escalating complaints from users (and, in some jurisdictions, regulators) about the platform amplifying compulsive engagement loops. Users report losing hours per session, inability to stop scrolling, and distress triggered by notification pings. Separately, the UK Online Safety Act 2023, the EU Digital Services Act (Art. 27 for minors), and proposed US KOSA legislation require platforms to implement "features to support user wellbeing." Failing to build these is both a safety gap and a compliance liability.

## Context

This is not about dark-pattern enforcement (covered in `dark-patterns-deceptive-design-regulation.md`) but about proactive platform-side tooling: detecting compulsive usage patterns from session data, surfacing opt-in intervention prompts, and giving users controls over notification cadence and daily limits. The stack is: D1 (session duration + engagement metrics), Workers (session hook + threshold evaluator), KV (user preference store), and Queues (async notification digest pipeline).

## 1. Session Duration Tracking Schema

```sql
-- migrations/0077_wellbeing.sql
CREATE TABLE IF NOT EXISTS user_sessions (
  session_id       TEXT PRIMARY KEY,
  account_id       TEXT,             -- nullable for anonymous sessions
  device_fp        TEXT,             -- device fingerprint for anon tracking
  started_at       INTEGER NOT NULL,
  last_active_at   INTEGER NOT NULL,
  scroll_events    INTEGER DEFAULT 0,
  content_opened   INTEGER DEFAULT 0,
  notifications_tapped INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_us_account ON user_sessions(account_id, started_at DESC);

CREATE TABLE IF NOT EXISTS wellbeing_preferences (
  account_id         TEXT PRIMARY KEY,
  daily_limit_min    INTEGER,          -- NULL = no limit
  digest_mode        INTEGER DEFAULT 0, -- 0 = realtime, 1 = digest
  digest_hour        INTEGER DEFAULT 17, -- local hour for digest delivery
  break_reminder_min INTEGER DEFAULT 60, -- remind after N continuous minutes
  opt_out_at         INTEGER           -- user opted out of all nudges
);
```

## 2. Session Heartbeat Worker (Called Every 60 s from Client)

```typescript
// src/wellbeing-heartbeat.ts
export async function recordHeartbeat(
  sessionId: string,
  accountId: string | null,
  deviceFp: string,
  scrollDelta: number,
  env: Env,
  ctx: ExecutionContext
): Promise<{ showBreakPrompt: boolean; dailyLimitReached: boolean }> {
  const now = Date.now();

  await env.DB.prepare(
    `INSERT INTO user_sessions
       (session_id, account_id, device_fp, started_at, last_active_at, scroll_events)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(session_id) DO UPDATE SET
       last_active_at = excluded.last_active_at,
       scroll_events  = scroll_events + excluded.scroll_events`
  )
    .bind(sessionId, accountId, deviceFp, now, now, scrollDelta)
    .run();

  if (!accountId) return { showBreakPrompt: false, dailyLimitReached: false };

  const prefs = await getWellbeingPrefs(accountId, env);
  if (prefs.opt_out_at) return { showBreakPrompt: false, dailyLimitReached: false };

  // Continuous session duration
  const session = await env.DB.prepare(
    "SELECT started_at FROM user_sessions WHERE session_id = ?"
  )
    .bind(sessionId)
    .first<{ started_at: number }>();

  const sessionMinutes = session ? (now - session.started_at) / 60_000 : 0;
  const showBreakPrompt =
    prefs.break_reminder_min != null &&
    sessionMinutes >= prefs.break_reminder_min &&
    Math.round(sessionMinutes) % prefs.break_reminder_min < 1; // once per threshold

  // Daily usage total (rolling 24 h)
  const dailySeconds = await getDailyUsage(accountId, env);
  const dailyLimitReached =
    prefs.daily_limit_min != null &&
    dailySeconds / 60 >= prefs.daily_limit_min;

  if (dailyLimitReached) {
    ctx.waitUntil(env.WELLBEING_QUEUE.send({ type: "daily_limit", accountId }));
  }

  return { showBreakPrompt, dailyLimitReached };
}

async function getWellbeingPrefs(accountId: string, env: Env) {
  return (
    (await env.DB.prepare(
      "SELECT * FROM wellbeing_preferences WHERE account_id = ?"
    )
      .bind(accountId)
      .first<{
        daily_limit_min: number | null;
        break_reminder_min: number;
        digest_mode: number;
        opt_out_at: number | null;
      }>()) ?? {
      daily_limit_min: null,
      break_reminder_min: 60,
      digest_mode: 0,
      opt_out_at: null,
    }
  );
}

async function getDailyUsage(accountId: string, env: Env): Promise<number> {
  const since = Date.now() - 24 * 3600 * 1000;
  const { total } = (await env.DB.prepare(
    `SELECT SUM(last_active_at - started_at) AS total
     FROM user_sessions
     WHERE account_id = ? AND started_at >= ?`
  )
    .bind(accountId, since)
    .first<{ total: number }>()) ?? { total: 0 };
  return (total ?? 0) / 1000; // return seconds
}
```

## 3. Compulsive Pattern Detector (Daily Cron Job)

```typescript
// src/wellbeing-detector.ts — runs nightly via Cron Trigger
// Detects: sessions > 3 h, late-night usage (midnight–5 am local), 7-day streaks
export async function detectCompulsivePatterns(env: Env): Promise<void> {
  const cutoff = Date.now() - 7 * 24 * 3600 * 1000;

  const candidates = await env.DB.prepare(
    `SELECT account_id,
            COUNT(*) AS session_count,
            SUM(last_active_at - started_at) AS total_ms,
            MAX(last_active_at - started_at) AS max_session_ms,
            SUM(CASE WHEN (started_at % 86400000) BETWEEN 0 AND 18000000
                THEN 1 ELSE 0 END) AS late_night_sessions
     FROM user_sessions
     WHERE started_at >= ? AND account_id IS NOT NULL
     GROUP BY account_id
     HAVING total_ms > 3600000 * 3 * 7   -- >3 h/day avg over 7 days
        OR  max_session_ms > 3600000 * 5  -- any session > 5 h
        OR  late_night_sessions >= 3`
  )
    .bind(cutoff)
    .all<{
      account_id: string;
      session_count: number;
      total_ms: number;
      max_session_ms: number;
      late_night_sessions: number;
    }>();

  for (const row of candidates.results) {
    // Only nudge accounts that haven't opted out and haven't been nudged in 7 days
    const cacheKey = `wellbeing:nudged:${row.account_id}`;
    const alreadyNudged = await env.KV.get(cacheKey);
    if (alreadyNudged) continue;

    await env.WELLBEING_QUEUE.send({
      type: "pattern_nudge",
      accountId: row.account_id,
      signals: {
        totalHoursWeek: Math.round(row.total_ms / 3_600_000),
        maxSessionHours: Math.round(row.max_session_ms / 3_600_000),
        lateNightSessions: row.late_night_sessions,
      },
    });

    await env.KV.put(cacheKey, "1", { expirationTtl: 7 * 24 * 3600 });
  }
}
```

## 4. Digest Mode Notification Batcher

```typescript
// src/wellbeing-digest.ts — Cron Trigger: 0 * * * * (hourly)
export async function sendDigests(env: Env): Promise<void> {
  const currentHourUTC = new Date().getUTCHours();

  // Find accounts with digest_mode=1 whose digest hour matches now (UTC approx)
  const accounts = await env.DB.prepare(
    `SELECT account_id FROM wellbeing_preferences
     WHERE digest_mode = 1 AND digest_hour = ?`
  )
    .bind(currentHourUTC)
    .all<{ account_id: string }>();

  for (const { account_id } of accounts.results) {
    // Fetch accumulated notifications from KV
    const pendingKey = `notif:pending:${account_id}`;
    const pending = await env.KV.get<string[]>(pendingKey, "json") ?? [];

    if (pending.length === 0) continue;

    // Dispatch one digest notification
    await env.NOTIFICATION_QUEUE.send({
      type: "digest",
      accountId: account_id,
      items: pending,
      count: pending.length,
    });

    await env.KV.delete(pendingKey);
  }
}
```

## 5. User Preference API (Worker Route)

```typescript
// src/wellbeing-prefs.ts
export async function upsertWellbeingPrefs(
  accountId: string,
  prefs: {
    daily_limit_min?: number | null;
    break_reminder_min?: number;
    digest_mode?: boolean;
    opt_out?: boolean;
  },
  env: Env
): Promise<void> {
  const now = Date.now();
  await env.DB.prepare(
    `INSERT INTO wellbeing_preferences
       (account_id, daily_limit_min, break_reminder_min, digest_mode, opt_out_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(account_id) DO UPDATE SET
       daily_limit_min    = COALESCE(excluded.daily_limit_min, daily_limit_min),
       break_reminder_min = COALESCE(excluded.break_reminder_min, break_reminder_min),
       digest_mode        = COALESCE(excluded.digest_mode, digest_mode),
       opt_out_at         = COALESCE(excluded.opt_out_at, opt_out_at)`
  )
    .bind(
      accountId,
      prefs.daily_limit_min ?? null,
      prefs.break_reminder_min ?? null,
      prefs.digest_mode != null ? (prefs.digest_mode ? 1 : 0) : null,
      prefs.opt_out ? now : null
    )
    .run();
}
```

## Anti-patterns

- Surfacing break prompts every session regardless of duration — users in very short sessions should never see a break nudge; gate on minimum session length (>= 20 min).
- Enforcing hard daily limits without user consent — the platform may cap usage for minors per regulation (UK OSA, DSA), but for adults a hard cutoff without opt-in is a dark pattern in reverse.
- Storing continuous session data indefinitely — session rows are PII-adjacent; apply a 90-day rolling retention policy aligned with your privacy policy.
- Computing rolling daily usage inline on every heartbeat — this is a full-table scan; use a materialized counter in KV updated on session close, refreshed daily by a Cron job.

## Gotchas

- Anonymous sessions cannot persist wellbeing preferences across devices; link prefs to device fingerprint only as a best-effort fallback, and prompt account creation to enable full wellbeing features.
- `SUM(last_active_at - started_at)` over-counts if the client sends heartbeats after the session genuinely ends (e.g., backgrounded app); cap each heartbeat gap to 90 s before accumulating.
- Digest mode suppresses notifications in KV; if KV is evicted or the namespace is misconfigured, notifications are lost silently — add a D1 backup table for notifications with status `pending | sent`.
- Late-night detection using `started_at % 86400000` is UTC-relative; for accurate local-time classification, store the user's UTC offset (from Cloudflare's `cf-timezone` header) in the accounts table.

## Verification

```bash
# Confirm wellbeing_preferences table exists with expected columns
wrangler d1 execute example project-prod --command \
  "PRAGMA table_info(wellbeing_preferences)"

# Simulate heartbeat call
curl -X POST https://staging.example.com/api/wellbeing/heartbeat \
  -H "X-Account-Id: test-user-1" \
  -d '{"sessionId":"sess-abc","scrollDelta":15}'
# Expect: {"showBreakPrompt":false,"dailyLimitReached":false}

# Check compulsive usage candidates from last 7 days (staging)
wrangler d1 execute example project-staging --command \
  "SELECT account_id, SUM(last_active_at-started_at)/3600000.0 AS hours_7d
   FROM user_sessions WHERE started_at > strftime('%s','now','-7 days')*1000
   GROUP BY account_id ORDER BY hours_7d DESC LIMIT 10"
```

## Related

- `dark-patterns-deceptive-design-regulation.md`
- `underage-user-detection-behavioral-signals.md`
- `age-verification-online-platforms-regulation.md`
- `platform-health-score-dashboard-analytics-engine.md`
- `platform-exodus-churn-prediction-d1-workers-ai.md`

## Sources

- UK Online Safety Act 2023, Schedule 4 — Safety duties protecting children
- EU DSA Art. 27 — Recommender system transparency and minor protections
- Kids Online Safety Act (KOSA) 2024 — US Senate bill S.1409
- Center for Humane Technology — "Ledger of Harms" (humanetech.com)
- Cloudflare Cron Triggers: developers.cloudflare.com/workers/configuration/cron-triggers/
