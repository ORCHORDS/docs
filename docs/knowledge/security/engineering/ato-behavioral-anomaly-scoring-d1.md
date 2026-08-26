# Account Takeover Detection: Behavioral Anomaly Scoring with D1

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Valid credentials stolen via phishing, credential stuffing, or dark-web dumps allow attackers to authenticate successfully — defeating password-based controls entirely. You need a second layer that asks: *does this authenticated session behave like the real account owner?* Behavioral anomaly scoring captures signals that differ between legitimate users and attackers (login timing, IP geolocation shift, device fingerprint change, unusual action sequences) and converts them into a numeric risk score. Sessions exceeding a threshold are challenged or blocked before they can exfiltrate data.

---

## Context

Account Takeover (ATO) through credential replay is the leading cause of data breaches in SaaS applications. Prevention falls into two phases:

1. **At authentication** — detecting that the credentials may have been stolen (covered by `credential-stuffing-account-takeover-defense.md`).
2. **Post-authentication** — detecting that an authenticated session is behaving abnormally even though the password was correct.

This article covers phase 2: building a lightweight behavioral baseline per user in D1 and scoring each session against it in a Cloudflare Worker. D1's SQL interface lets you express anomaly queries concisely without a separate time-series database.

**Risk score model:**
Each signal contributes a weight. The total score for a session is the sum of triggered signal weights. Scores are bucket thresholds:
- `0–30`: low risk — no action
- `31–60`: medium risk — silently flag, log for review
- `61–80`: high risk — step-up authentication (MFA re-prompt)
- `>80`: critical — block session, force password reset, alert security team

---

## D1 Schema

```sql
-- migrations/0001_ato_baseline.sql

CREATE TABLE IF NOT EXISTS user_login_baseline (
  user_id       TEXT NOT NULL,
  -- Rolling 30-day statistics updated on each successful login
  typical_hour_min  INTEGER NOT NULL DEFAULT 0,   -- earliest typical login hour (0-23)
  typical_hour_max  INTEGER NOT NULL DEFAULT 23,  -- latest typical login hour (0-23)
  country_codes     TEXT NOT NULL DEFAULT '[]',   -- JSON array of seen country codes
  device_hashes     TEXT NOT NULL DEFAULT '[]',   -- JSON array of recent device fingerprint hashes
  avg_session_actions REAL NOT NULL DEFAULT 0,    -- average actions per session
  last_login_ip     TEXT,
  last_login_at     INTEGER,                      -- unix epoch ms
  login_count       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS session_risk_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT NOT NULL,
  user_id       TEXT NOT NULL,
  risk_score    INTEGER NOT NULL,
  signals       TEXT NOT NULL,   -- JSON array of triggered signal names
  action_taken  TEXT NOT NULL,   -- 'allow' | 'flag' | 'challenge' | 'block'
  ip_address    TEXT,
  country_code  TEXT,
  device_hash   TEXT,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch('now') * 1000)
);

CREATE INDEX IF NOT EXISTS idx_session_risk_user
  ON session_risk_log (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_session_risk_score
  ON session_risk_log (risk_score DESC, created_at DESC);
```

---

## Behavioral Signal Definitions

```typescript
// src/ato/signals.ts
export interface SessionContext {
  userId: string;
  sessionId: string;
  ipAddress: string;
  countryCode: string;        // from CF-IPCountry header
  deviceHash: string;         // stable hash of device fingerprint
  loginHour: number;          // 0-23 UTC
  requestPath: string;
}

export interface UserBaseline {
  typicalHourMin: number;
  typicalHourMax: number;
  countryCodes: string[];     // parsed from JSON
  deviceHashes: string[];     // parsed from JSON
  lastLoginIp: string | null;
  lastLoginAt: number | null;
  loginCount: number;
}

export interface Signal {
  name: string;
  weight: number;
  triggered: boolean;
}

/** Returns all signals with their triggered state */
export function evaluateSignals(
  ctx: SessionContext,
  baseline: UserBaseline
): Signal[] {
  const signals: Signal[] = [];

  // New country: weight 25
  signals.push({
    name: 'new_country',
    weight: 25,
    triggered:
      baseline.loginCount > 3 &&
      !baseline.countryCodes.includes(ctx.countryCode),
  });

  // Country changed from last login: weight 15
  signals.push({
    name: 'country_change_from_last',
    weight: 15,
    triggered:
      baseline.lastLoginAt !== null &&
      Date.now() - baseline.lastLoginAt < 60 * 60 * 1000 && // within 1 hour
      !baseline.countryCodes.slice(-1).includes(ctx.countryCode),
  });

  // New device fingerprint: weight 20
  signals.push({
    name: 'new_device',
    weight: 20,
    triggered:
      baseline.loginCount > 2 &&
      !baseline.deviceHashes.includes(ctx.deviceHash),
  });

  // Login at unusual hour: weight 10
  signals.push({
    name: 'unusual_hour',
    weight: 10,
    triggered:
      baseline.loginCount > 5 &&
      (ctx.loginHour < baseline.typicalHourMin ||
        ctx.loginHour > baseline.typicalHourMax),
  });

  // New IP (not just new country): weight 5
  signals.push({
    name: 'new_ip',
    weight: 5,
    triggered:
      baseline.lastLoginIp !== null &&
      baseline.lastLoginIp !== ctx.ipAddress,
  });

  // First login ever from this account (low baseline confidence): weight 0
  signals.push({
    name: 'thin_baseline',
    weight: 0,
    triggered: baseline.loginCount < 3,
  });

  // Targeting high-value endpoint directly (skipping normal navigation): weight 20
  const highValuePaths = ['/api/export', '/api/billing', '/api/admin'];
  signals.push({
    name: 'direct_high_value_access',
    weight: 20,
    triggered: highValuePaths.some(p => ctx.requestPath.startsWith(p)),
  });

  return signals;
}

export function computeScore(signals: Signal[]): number {
  return signals
    .filter(s => s.triggered)
    .reduce((sum, s) => sum + s.weight, 0);
}

export type RiskAction = 'allow' | 'flag' | 'challenge' | 'block';

export function scoreToAction(score: number): RiskAction {
  if (score > 80) return 'block';
  if (score > 60) return 'challenge';
  if (score > 30) return 'flag';
  return 'allow';
}
```

---

## D1 Queries: Baseline Lookup and Update

```typescript
// src/ato/baseline.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { UserBaseline } from './signals';

export async function loadBaseline(
  db: D1Database,
  userId: string
): Promise<UserBaseline> {
  const row = await db
    .prepare(
      `SELECT typical_hour_min, typical_hour_max, country_codes,
              device_hashes, last_login_ip, last_login_at, login_count
       FROM user_login_baseline WHERE user_id = ?`
    )
    .bind(userId)
    .first<{
      typical_hour_min: number;
      typical_hour_max: number;
      country_codes: string;
      device_hashes: string;
      last_login_ip: string | null;
      last_login_at: number | null;
      login_count: number;
    }>();

  if (!row) {
    return {
      typicalHourMin: 0,
      typicalHourMax: 23,
      countryCodes: [],
      deviceHashes: [],
      lastLoginIp: null,
      lastLoginAt: null,
      loginCount: 0,
    };
  }

  return {
    typicalHourMin: row.typical_hour_min,
    typicalHourMax: row.typical_hour_max,
    countryCodes: JSON.parse(row.country_codes),
    deviceHashes: JSON.parse(row.device_hashes),
    lastLoginIp: row.last_login_ip,
    lastLoginAt: row.last_login_at,
    loginCount: row.login_count,
  };
}

const MAX_HISTORY = 10; // keep last 10 distinct values

export async function updateBaseline(
  db: D1Database,
  userId: string,
  countryCode: string,
  deviceHash: string,
  loginHour: number,
  ipAddress: string
): Promise<void> {
  const existing = await loadBaseline(db, userId);

  // Expand hour range
  const newHourMin = Math.min(existing.typicalHourMin, loginHour);
  const newHourMax = Math.max(existing.typicalHourMax, loginHour);

  // Add country and trim history
  const countries = [...new Set([...existing.countryCodes, countryCode])].slice(
    -MAX_HISTORY
  );

  // Add device hash and trim history
  const devices = [...new Set([...existing.deviceHashes, deviceHash])].slice(
    -MAX_HISTORY
  );

  await db
    .prepare(
      `INSERT INTO user_login_baseline
         (user_id, typical_hour_min, typical_hour_max, country_codes,
          device_hashes, last_login_ip, last_login_at, login_count)
       VALUES (?, ?, ?, ?, ?, ?, ?, 1)
       ON CONFLICT (user_id) DO UPDATE SET
         typical_hour_min  = excluded.typical_hour_min,
         typical_hour_max  = excluded.typical_hour_max,
         country_codes     = excluded.country_codes,
         device_hashes     = excluded.device_hashes,
         last_login_ip     = excluded.last_login_ip,
         last_login_at     = excluded.last_login_at,
         login_count       = login_count + 1`
    )
    .bind(
      userId,
      newHourMin,
      newHourMax,
      JSON.stringify(countries),
      JSON.stringify(devices),
      ipAddress,
      Date.now()
    )
    .run();
}

export async function logSessionRisk(
  db: D1Database,
  ctx: { sessionId: string; userId: string; ipAddress: string; countryCode: string; deviceHash: string },
  riskScore: number,
  triggeredSignals: string[],
  action: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO session_risk_log
         (session_id, user_id, risk_score, signals, action_taken,
          ip_address, country_code, device_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      ctx.sessionId,
      ctx.userId,
      riskScore,
      JSON.stringify(triggeredSignals),
      action,
      ctx.ipAddress,
      ctx.countryCode,
      ctx.deviceHash
    )
    .run();
}
```

---

## Worker Middleware Integration

```typescript
// src/ato/middleware.ts
import type { D1Database } from '@cloudflare/workers-types';
import {
  evaluateSignals,
  computeScore,
  scoreToAction,
  type SessionContext,
} from './signals';
import { loadBaseline, updateBaseline, logSessionRisk } from './baseline';

export interface AtoEnv {
  DB: D1Database;
}

export async function atoCheck(
  request: Request,
  env: AtoEnv,
  ctx: ExecutionContext,
  next: () => Promise<Response>
): Promise<Response> {
  const userId = request.headers.get('x-authenticated-user-id');
  if (!userId) return next(); // unauthenticated — not in scope here

  const sessionId = request.headers.get('x-session-id') ?? crypto.randomUUID();
  const ipAddress = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
  const countryCode = request.headers.get('CF-IPCountry') ?? 'XX';
  const deviceHash = request.headers.get('x-device-fingerprint-hash') ?? 'unknown';
  const loginHour = new Date().getUTCHours();
  const { pathname } = new URL(request.url);

  const sessionCtx: SessionContext = {
    userId,
    sessionId,
    ipAddress,
    countryCode,
    deviceHash,
    loginHour,
    requestPath: pathname,
  };

  // Fetch baseline — single D1 read
  const baseline = await loadBaseline(env.DB, userId);
  const signals = evaluateSignals(sessionCtx, baseline);
  const score = computeScore(signals);
  const action = scoreToAction(score);
  const triggeredNames = signals.filter(s => s.triggered).map(s => s.name);

  // Async: log risk and update baseline without blocking the response
  ctx.waitUntil(
    (async () => {
      await logSessionRisk(env.DB, sessionCtx, score, triggeredNames, action);
      if (action === 'allow' || action === 'flag') {
        // Only update baseline for sessions we're allowing through
        await updateBaseline(env.DB, userId, countryCode, deviceHash, loginHour, ipAddress);
      }
    })()
  );

  if (action === 'block') {
    return new Response(
      JSON.stringify({ error: 'Session blocked due to suspicious activity. Please re-authenticate.' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (action === 'challenge') {
    return new Response(
      JSON.stringify({ error: 'step_up_required', sessionId }),
      { status: 401, headers: { 'Content-Type': 'application/json', 'X-ATO-Challenge': 'mfa' } }
    );
  }

  // Propagate risk score to downstream handlers for auditing
  const modifiedRequest = new Request(request, {
    headers: {
      ...Object.fromEntries(request.headers),
      'x-ato-risk-score': String(score),
      'x-ato-action': action,
    },
  });

  return next.call(null).then ? next() : (next as unknown as () => Promise<Response>)();
}
```

---

## Security Analytics Queries

```sql
-- Top 20 highest-risk sessions in the last 24 hours
SELECT user_id, session_id, risk_score, signals, action_taken,
       country_code, device_hash,
       datetime(created_at / 1000, 'unixepoch') AS created_at_utc
FROM session_risk_log
WHERE created_at > (unixepoch('now') - 86400) * 1000
ORDER BY risk_score DESC
LIMIT 20;

-- Users with more than 3 challenge/block events in 7 days
SELECT user_id, COUNT(*) AS incidents
FROM session_risk_log
WHERE action_taken IN ('challenge', 'block')
  AND created_at > (unixepoch('now') - 604800) * 1000
GROUP BY user_id
HAVING COUNT(*) > 3
ORDER BY incidents DESC;

-- Most common triggered signals across blocked sessions
SELECT json_each.value AS signal, COUNT(*) AS count
FROM session_risk_log, json_each(session_risk_log.signals)
WHERE action_taken = 'block'
  AND created_at > (unixepoch('now') - 86400) * 1000
GROUP BY signal
ORDER BY count DESC;
```

---

## Anti-patterns

**Blocking on thin baselines.** A new account with `login_count < 3` has no reliable baseline. Flag these sessions silently and require MFA for sensitive actions rather than blocking outright. Include the `thin_baseline` signal with weight 0 as a marker.

**Storing raw IP addresses without a data retention policy.** IP addresses are personal data under GDPR. Add a `created_at`-based purge job (via Cron Trigger) to delete rows older than your retention period.

**Using client-supplied device fingerprints without validation.** The device hash in `x-device-fingerprint-hash` must be computed server-side or signed by your frontend SDK — never trusted directly from untrusted input. An attacker can replay a known-good fingerprint.

**Updating the baseline for blocked sessions.** Never call `updateBaseline` when `action === 'block'`. Doing so would allow an attacker to gradually shift the baseline toward their own behavior pattern (baseline poisoning).

**Alerting on every flagged session.** "flag" action should go to a queue for async review, not a PagerDuty alert. Only "block" actions with high confidence (score > 80) justify immediate alerts.

---

## Gotchas

**VPN and corporate proxies shift country codes legitimately.** A user switching from home (US) to corporate VPN (IE) will trigger `new_country`. Combine with `last_login_at` timing: a country change within the same 1-hour window is more suspicious than one spanning 8 hours.

**D1 `json_each` availability.** The analytics queries use `json_each()`, which requires SQLite 3.38+ (available in D1). If you export the schema to another SQLite, verify version compatibility.

**`ctx.waitUntil` must not throw uncaught exceptions.** Wrap the baseline update in a try/catch so a D1 write failure does not produce an unhandled promise rejection that Cloudflare logs as an error.

**Device fingerprints drift over browser updates.** Rotate the device hash list when a new hash appears but the old one had more than 10 logins and the location is unchanged. A hash change + same IP + same hour is a browser update, not an attacker.

---

## Verification

```bash
# Simulate a new-country login and verify challenge response
curl -s -X GET https://api.example.com/api/profile \
  -H "x-authenticated-user-id: user_123" \
  -H "x-session-id: sess_abc" \
  -H "CF-Connecting-IP: 91.108.56.1" \
  -H "CF-IPCountry: RU" \
  -H "x-device-fingerprint-hash: abc123" | jq .
# Expected: {"error":"step_up_required","sessionId":"sess_abc"}

# Verify risk log entry in D1
wrangler d1 execute DB --command \
  "SELECT risk_score, signals, action_taken FROM session_risk_log \
   WHERE user_id = 'user_123' ORDER BY created_at DESC LIMIT 1"
```

---

## Related

- `credential-stuffing-account-takeover-defense.md` — defending the authentication layer
- `rate-limiting-per-user-d1-durable-objects.md` — per-user rate limiting complements ATO scoring
- `audit-log-security.md` — storing risk logs durably for compliance
- `totp-mfa-implementation.md` — step-up MFA to challenge risky sessions
- `jwt-sliding-window-refresh-workers-kv.md` — invalidating sessions post-block

---

## Sources

- OWASP Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- NIST SP 800-63B §5.2 — Authenticator Assurance Levels and risk-based authentication
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- "Behavioral Analytics for Account Takeover Prevention" — Shape Security Research, 2022
- GDPR Recital 26 and Article 4(1) — personal data scope including IP addresses
