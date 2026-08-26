# Underage User Detection via Behavioral Signals

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Age-verified accounts on example project occasionally exhibit post-submission times, vocabulary
patterns, interaction cadences, and device fingerprints statistically associated with
users under 21.  A user who passed KYC at registration (or used a borrowed document)
may still present persistent behavioral signals that warrant re-verification.  Without
a continuous behavioral scoring layer the platform has no mechanism to surface these
accounts for human review before a regulatory audit or a CSAM-adjacent incident does.

## Context

example project is a 21+ anonymous social platform.  Age verification occurs at registration via
a KYC Worker (see `age-verification-cloudflare-workers-kyc.md`).  Behavioral
monitoring is a supplementary layer — not a replacement for KYC — intended to surface
accounts whose ongoing behavior diverges significantly from an adult baseline.  All
signals are aggregated into a D1 `risk_log` table.  The system must comply with COPPA
(under-13 prohibition) and GDPR Article 22 (no fully-automated legally significant
decisions without human review).  A high risk score gates the account for human
moderator review; it does not trigger automatic suspension.

## Behavioral Signal Taxonomy

Signals are grouped into three tiers by reliability.  Each signal contributes a
weighted score (0–100) that is averaged into a composite `risk_score`.

```
┌──────────────┬─────────────────────────────────────┬────────┬──────────────────┐
│ Tier         │ Signal                              │ Weight │ Rationale        │
├──────────────┼─────────────────────────────────────┼────────┼──────────────────┤
│ High         │ Post time ≥ 70 % between 15:00–18:00│  0.30  │ After-school hrs │
│ High         │ Vocabulary match to <18 corpus       │  0.35  │ NLP classifier   │
│ High         │ Cloudflare Bot Score < 30            │  0.25  │ Automated pattern│
│ Medium       │ Session length < 90 s > 20×/week    │  0.15  │ Scroll & leave   │
│ Medium       │ Reaction emoji ratio > 0.80          │  0.10  │ Emoji-heavy use  │
│ Medium       │ Device OS = iOS, model = iPad mini   │  0.10  │ Youth device     │
│ Low          │ Content category = gaming/TikTok ref │  0.08  │ Cultural marker  │
│ Low          │ Interaction bursts on school calendar │  0.07  │ School schedule  │
│ Low          │ Report-received: sexual content      │  0.05  │ Accidental access│
└──────────────┴─────────────────────────────────────┴────────┴──────────────────┘
```

Weights do not sum to 1.0 by design; they are per-signal caps fed into a bounded
aggregation function, not a probability distribution.

## Cloudflare Bot Score and Turnstile Integration

Cloudflare's Bot Management assigns a score (1 = bot, 99 = human) per request.  Low
scores on authenticated content-submission endpoints indicate scripted or emulated
clients, which correlate with underage users running shared account scripts.

```ts
// worker/middleware/behaviorGate.ts
export async function behaviorGate(
  request: Request,
  env: Env,
  accountId: string,
): Promise<{ risk: number; requiresTurnstile: boolean }> {
  const cf = request.cf as IncomingRequestCfProperties;
  const botScore = cf.botManagement?.score ?? 99;

  let risk = 0;

  // Bot score contribution (inverted: low score = high risk)
  if (botScore < 30) risk += 25;
  else if (botScore < 50) risk += 10;

  // Pull existing accumulated risk from D1
  const row = await env.DB.prepare(
    "SELECT risk_score FROM risk_log WHERE account_id = ? ORDER BY created_at DESC LIMIT 1"
  ).bind(accountId).first<{ risk_score: number }>();

  const accumulated = row?.risk_score ?? 0;
  const composite = Math.min(100, accumulated * 0.8 + risk * 0.2); // exponential decay

  // Require Turnstile re-challenge at composite >= 60
  return { risk: composite, requiresTurnstile: composite >= 60 };
}
```

Turnstile is invoked server-side at the edge for high-risk sessions.  The client
receives a `cf-mitigated: challenge` header or, if the SPA handles it, a
`{ requiresTurnstile: true }` JSON flag in the API response.

## D1 Risk Log Schema

```sql
CREATE TABLE IF NOT EXISTS risk_log (
  id            TEXT    PRIMARY KEY,   -- UUIDv7
  account_id    TEXT    NOT NULL,
  signal_type   TEXT    NOT NULL,      -- matches Tier taxonomy above
  signal_value  REAL    NOT NULL,      -- raw value that triggered the signal
  weight        REAL    NOT NULL,
  risk_score    REAL    NOT NULL,      -- composite at time of this event
  session_id    TEXT,
  ip_asn        INTEGER,
  created_at    INTEGER NOT NULL       -- Unix ms
);

CREATE INDEX idx_rl_account ON risk_log(account_id, created_at DESC);
CREATE INDEX idx_rl_score   ON risk_log(risk_score DESC) WHERE risk_score >= 60;
```

A nightly D1 query materializes the 7-day rolling risk score per account into
`accounts.behavioral_risk_score` for fast dashboard sorting:

```sql
UPDATE accounts
SET behavioral_risk_score = (
  SELECT AVG(risk_score)
  FROM risk_log
  WHERE risk_log.account_id = accounts.id
    AND created_at >= unixepoch('now', '-7 days') * 1000
)
WHERE id IN (SELECT DISTINCT account_id FROM risk_log WHERE created_at >= unixepoch('now', '-24 hours') * 1000);
```

## COPPA and GDPR Safeguards

```
┌──────────────────────────────┬───────────────────────────────────────────────┐
│ Safeguard                    │ Implementation                                │
├──────────────────────────────┼───────────────────────────────────────────────┤
│ No automatic suspension      │ Score >= 80 creates moderator task only       │
│ Human-in-the-loop required   │ GDPR Art.22: moderator approves all actions   │
│ Data minimization            │ risk_log rows purged after 90 days            │
│ Pseudonymization             │ account_id is UUID; no PII in risk_log        │
│ COPPA immediate deletion     │ Confirmed <13 triggers instant data wipe      │
│ Transparency notice          │ Account notified of review (not score value)  │
│ Appeals path                 │ Links to account-suspension-appeals workflow  │
│ No cross-context profiling   │ Risk score not shared with third parties      │
└──────────────────────────────┴───────────────────────────────────────────────┘
```

COPPA requires that upon confirmed detection of a user under 13, the platform must
delete all personal information collected from that user without delay.  The deletion
Worker must wipe: `accounts`, `posts`, `reactions`, `reports`, `risk_log`, and all
R2 media objects associated with the account.

```ts
// worker/lib/coppaWipe.ts
export async function coppaWipe(env: Env, accountId: string): Promise<void> {
  const tables = ["reactions", "reports", "risk_log", "posts", "accounts"];
  const stmts = tables.map(t =>
    env.DB.prepare(`DELETE FROM ${t} WHERE account_id = ?`).bind(accountId)
  );
  await env.DB.batch(stmts);

  // R2 media
  const listed = await env.R2_MEDIA.list({ prefix: `user/${accountId}/` });
  await Promise.all(listed.objects.map(o => env.R2_MEDIA.delete(o.key)));
}
```

## Anti-patterns

- Using post-submission time alone as a definitive signal — adults also post in the
  afternoon; single-signal decisions have unacceptable false-positive rates.
- Logging raw vocabulary samples in `risk_log` — storing actual post text in a risk
  table creates a secondary PII store and complicates GDPR erasure.
- Setting `risk_score >= 50` as the automatic suspension threshold — GDPR Article 22
  prohibits legally-significant automated decisions without human review; suspension
  is legally significant.
- Sharing behavioral risk scores with advertisers or analytics vendors — constitutes
  cross-context profiling under CCPA and Article 5(1)(b) GDPR purpose limitation.
- Re-running the nightly UPDATE without a `WHERE` clause limiting to recently active
  accounts — performs a full table scan on `risk_log` every night as the table grows.

## Gotchas

- `cf.botManagement` is `undefined` (not `null`) when Bot Management is not provisioned
  on the Cloudflare plan.  Always guard with `cf.botManagement?.score ?? 99` so
  unprotected environments default to the "human" assumption (99), not a false alarm.
- `unixepoch('now')` in D1 returns seconds; `created_at` is stored in milliseconds.
  Multiply by 1000: `unixepoch('now', '-7 days') * 1000`.
- Vocabulary classifiers trained on English-language youth corpora underperform on
  multilingual example project content.  Apply the vocabulary signal only when the account's
  detected language matches the classifier's training language.
- The `risk_log` index on `risk_score >= 60` is a partial index.  D1's SQLite engine
  uses it only when the query's WHERE clause exactly matches the partial expression.
  `WHERE risk_score > 59` will NOT use the partial index.
- Purging `risk_log` rows older than 90 days via a Worker cron must paginate deletes;
  D1 has a 10 MB per-statement result size limit and a 10 s CPU time limit per Worker
  invocation.  Delete in batches of 500 rows.

## Verification

```bash
# 1. Insert a synthetic high-risk signal and check composite score
wrangler d1 execute example project-db --command \
  "INSERT INTO risk_log VALUES('test-1','acct-abc','post_time_after_school',1.0,0.30,75,NULL,0,$(date +%s)000)"

# 2. Query the composite score for the account
wrangler d1 execute example project-db --command \
  "SELECT AVG(risk_score) FROM risk_log WHERE account_id='acct-abc'"
# Expect: 75.0

# 3. Trigger the behavior gate via Worker endpoint
curl -X POST https://example.com/api/posts \
  -H "Authorization: Bearer $USER_JWT" \
  -d '{"content":"test post"}'
# If composite >= 60: Expect response includes {"requiresTurnstile":true}

# 4. Verify COPPA wipe removes all records
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) FROM risk_log WHERE account_id='acct-abc'"
# Expect: 0 after coppaWipe runs
```

## Related

- `age-verification-cloudflare-workers-kyc.md`
- `877-csam-vendor-integration.md`
- `anonymous-platform-abuse-prevention.md`
- `platform-trust-score-cloudflare-signals.md`
- `gdpr-article-22-automated-decisions-2026.md`
- `account-suspension-appeals-worker-workflow.md`

## Sources

- COPPA (Children's Online Privacy Protection Act) — ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa
- GDPR Article 22 — eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679
- Cloudflare Bot Management — developers.cloudflare.com/bots/plans/bm-subscription/
- Cloudflare Turnstile — developers.cloudflare.com/turnstile/
- Cloudflare D1 — developers.cloudflare.com/d1/
- Cloudflare R2 — developers.cloudflare.com/r2/
