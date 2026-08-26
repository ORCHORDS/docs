# Minnesota Consumer Data Privacy Act (MCDPA) — Workers & D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project deployment processes personal data of Minnesota residents. The Minnesota Consumer Data Privacy Act (Minn. Stat. §§ 325O.01–325O.14) took effect 31 July 2025. A privacy team review flags that the opt-out-of-profiling right and the question-and-answer right (unique to Minnesota) are not yet implemented in the Cloudflare Workers / D1 stack.

## Context

MCDPA thresholds (calendar year): ≥ 100,000 Minnesota consumers processed, OR ≥ 25,000 consumers AND > 25 % of gross revenue from selling personal data. Key differentiators:

- **Question-and-answer (Q&A) right** — consumers may ask any question about the controller's data practices; the controller must respond in plain language within 45 days. No other US state law has this right.
- **Opt-out of profiling** — includes profiling in "decisions that produce legal or similarly significant effects."
- **Sensitive-data opt-in** — race, ethnicity, religion, mental/physical health diagnosis, sexual orientation/gender identity, citizenship/immigration status, biometric identifiers, precise geolocation (< 1,750 ft), financial account numbers, union membership, data of children under 13.
- **Bona fide loyalty-program exception** — a controller may process sensitive data for a loyalty programme if the consumer receives meaningful benefits and can withdraw at any time; this exception is narrowly construed.
- **Data protection assessments** required for targeted advertising, sale, profiling with legal-significant effects, and sensitive-data processing.
- Enforcement: MN Attorney General; 30-day cure period until 31 July 2027.

## 1. D1 Schema

```sql
-- migrations/0012_mcdpa.sql
CREATE TABLE IF NOT EXISTS mcdpa_preferences (
  user_id           TEXT NOT NULL,
  opt_sale          INTEGER NOT NULL DEFAULT 0,
  opt_targeted_ads  INTEGER NOT NULL DEFAULT 0,
  opt_profiling     INTEGER NOT NULL DEFAULT 0,
  source            TEXT,                          -- 'explicit_ui' | 'GPC'
  updated_at        TEXT NOT NULL,
  PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS mcdpa_sensitive_consent (
  user_id       TEXT NOT NULL,
  data_category TEXT NOT NULL,
  opted_in      INTEGER NOT NULL DEFAULT 0,
  loyalty_prog  INTEGER NOT NULL DEFAULT 0,       -- 1 = bona fide loyalty programme exception
  captured_at   TEXT NOT NULL,
  PRIMARY KEY (user_id, data_category)
);

CREATE TABLE IF NOT EXISTS mcdpa_qa_log (
  question_id  TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  question     TEXT NOT NULL,
  received_at  TEXT NOT NULL,
  answered_at  TEXT,
  answer       TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'    -- 'pending' | 'answered' | 'extended'
);
```

## 2. GPC / Opt-Out Middleware

```typescript
// workers/mcdpa-optout.ts
export interface Env {
  DB: D1Database;
}

export async function applyMCDPAOptOuts(
  request: Request,
  env: Env,
  userId: string | null
): Promise<{ sale: boolean; targetedAds: boolean; profiling: boolean }> {
  const gpc = request.headers.get('Sec-GPC') === '1';

  let prefs = { opt_sale: 0, opt_targeted_ads: 0, opt_profiling: 0 };
  if (userId) {
    const row = await env.DB.prepare(
      'SELECT opt_sale, opt_targeted_ads, opt_profiling FROM mcdpa_preferences WHERE user_id = ?'
    ).bind(userId).first<typeof prefs>();
    if (row) prefs = row;

    // Persist GPC if not already stored
    if (gpc && !prefs.opt_sale) {
      await env.DB.prepare(
        `INSERT INTO mcdpa_preferences (user_id, opt_sale, opt_targeted_ads, opt_profiling, source, updated_at)
         VALUES (?, 1, 1, 1, 'GPC', CURRENT_TIMESTAMP)
         ON CONFLICT(user_id) DO UPDATE
         SET opt_sale=1, opt_targeted_ads=1, opt_profiling=1,
             source='GPC', updated_at=CURRENT_TIMESTAMP`
      ).bind(userId).run();
    }
  }

  return {
    sale:        gpc || prefs.opt_sale === 1,
    targetedAds: gpc || prefs.opt_targeted_ads === 1,
    profiling:   gpc || prefs.opt_profiling === 1,
  };
}
```

## 3. Sensitive-Data Consent with Loyalty-Programme Exception

```typescript
// workers/mcdpa-sensitive.ts
const MN_SENSITIVE = new Set([
  'race_ethnicity', 'religion', 'mental_health_diagnosis', 'physical_health_diagnosis',
  'sexual_orientation', 'gender_identity', 'citizenship_immigration',
  'biometric', 'precise_geolocation', 'financial_account', 'union_membership', 'minor_data'
]);

interface SensitiveCheck {
  allowed: boolean;
  basis: 'explicit_consent' | 'loyalty_programme' | 'denied' | 'not_sensitive';
}

export async function checkMNSensitive(
  env: Env,
  userId: string,
  category: string
): Promise<SensitiveCheck> {
  if (!MN_SENSITIVE.has(category)) {
    return { allowed: true, basis: 'not_sensitive' };
  }

  const row = await env.DB.prepare(
    `SELECT opted_in, loyalty_prog FROM mcdpa_sensitive_consent
     WHERE user_id = ? AND data_category = ?`
  ).bind(userId, category).first<{ opted_in: number; loyalty_prog: number }>();

  if (!row) return { allowed: false, basis: 'denied' };
  if (row.opted_in === 1) return { allowed: true, basis: 'explicit_consent' };
  if (row.loyalty_prog === 1) return { allowed: true, basis: 'loyalty_programme' };
  return { allowed: false, basis: 'denied' };
}
```

## 4. Question-and-Answer Right Handler

The Q&A right is unique to MCDPA. Implement a queue and a 45-day (extendable 45-day) response workflow.

```typescript
// workers/mcdpa-qa.ts
import { randomUUID } from 'node:crypto'; // available in Workers via globalThis.crypto

export async function submitMCDPAQuestion(
  env: Env,
  userId: string,
  question: string
): Promise<{ question_id: string; deadline: string }> {
  const questionId = crypto.randomUUID();
  const deadline = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `INSERT INTO mcdpa_qa_log (question_id, user_id, question, received_at, status)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'pending')`
  ).bind(questionId, userId, question).run();

  // Notify internal team (e.g., queue message or email trigger omitted for brevity)
  return { question_id: questionId, deadline };
}

export async function answerMCDPAQuestion(
  env: Env,
  questionId: string,
  answer: string
): Promise<void> {
  await env.DB.prepare(
    `UPDATE mcdpa_qa_log
     SET answer = ?, answered_at = CURRENT_TIMESTAMP, status = 'answered'
     WHERE question_id = ?`
  ).bind(answer, questionId).run();
}

export async function getOverdueQuestions(env: Env): Promise<unknown[]> {
  const rows = await env.DB.prepare(
    `SELECT question_id, user_id, question, received_at
     FROM mcdpa_qa_log
     WHERE status IN ('pending','extended')
       AND julianday('now') - julianday(received_at) > 45`
  ).all();
  return rows.results;
}
```

## 5. Data Protection Assessment Registry

```typescript
// workers/mcdpa-dpa-registry.ts
interface DPARecord {
  dpa_id:              string;
  processing_activity: string;
  risk_trigger:        'targeted_advertising' | 'sale' | 'profiling_legal_effect' | 'sensitive_data';
  benefits_outweigh:   boolean;
  approved_by:         string;
  approved_at:         string;
}

export async function upsertDPA(env: Env, record: DPARecord): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO mcdpa_dpa_registry
       (dpa_id, processing_activity, risk_trigger,
        benefits_outweigh, approved_by, approved_at)
     VALUES (?,?,?,?,?,?)`
  ).bind(
    record.dpa_id, record.processing_activity, record.risk_trigger,
    record.benefits_outweigh ? 1 : 0, record.approved_by, record.approved_at
  ).run();
}
```

```sql
CREATE TABLE IF NOT EXISTS mcdpa_dpa_registry (
  dpa_id              TEXT PRIMARY KEY,
  processing_activity TEXT NOT NULL,
  risk_trigger        TEXT NOT NULL,
  benefits_outweigh   INTEGER NOT NULL DEFAULT 0,
  approved_by         TEXT NOT NULL,
  approved_at         TEXT NOT NULL
);
```

## Anti-patterns

- **Conflating opt-out of "profiling" with opt-out of "automated decisions"** — MCDPA's profiling right specifically covers decisions with "legal or similarly significant effects"; analytics dashboards without decision outputs are generally outside scope.
- **Treating the loyalty-programme exception as broad** — it applies only when the consumer receives a "real and meaningful benefit" and the processing is disclosed at enrolment; using it as a blanket exemption for all personalisation will not survive scrutiny.
- **Not implementing the Q&A right** — this is legally distinct from a standard DSR; it must accept free-text questions, not only enumerated request types.
- **Mapping Minnesota GPC opt-outs only to sale** — MCDPA requires honouring GPC for sale, targeted advertising, and profiling simultaneously.

## Gotchas

- MCDPA's **30-day cure period sunsets 31 July 2027**; enforcement then becomes immediate.
- The **Q&A right deadline is 45 days, extendable once by another 45 days with written notice** — failure to send the extension notice makes the second 45-day window invalid.
- **IP-to-state geolocation** (using `CF-IPCountry` alone) is insufficient; Minnesota users behind VPNs or with inconsistent IP geo will be missed — supplement with declared state at account creation.
- Sensitive-data threshold for **precise geolocation is < 1,750 ft (≈ 533 m)** — street-level, not building-level; even anonymised mobility data may remain sensitive.

## Verification

```bash
# Overdue Q&A requests
wrangler d1 execute PROD_DB --command \
  "SELECT question_id, user_id, received_at FROM mcdpa_qa_log
   WHERE status='pending' AND julianday('now') - julianday(received_at) > 44"

# Opt-out coverage
wrangler d1 execute PROD_DB --command \
  "SELECT opt_sale, opt_targeted_ads, opt_profiling, COUNT(*)
   FROM mcdpa_preferences GROUP BY 1,2,3"

# Sensitive consent audit
wrangler d1 execute PROD_DB --command \
  "SELECT data_category, opted_in, loyalty_prog, COUNT(*)
   FROM mcdpa_sensitive_consent GROUP BY 1,2,3"
```

## Related

- `colorado-cpa-workers-d1.md`
- `connecticut-ctdpa-data-rights-workers.md`
- `iowa-cdpa-workers-d1.md`
- `data-minimization-workers-d1-pii-redaction.md`
- `maryland-modpa-workers-d1.md`

## Sources

- Minnesota Consumer Data Privacy Act, Minn. Stat. §§ 325O.01–325O.14, effective 31 July 2025
- MN Attorney General MCDPA Overview, June 2025
- IAPP US State Privacy Law Tracker — https://iapp.org
- Future of Privacy Forum MCDPA Analysis, 2024
