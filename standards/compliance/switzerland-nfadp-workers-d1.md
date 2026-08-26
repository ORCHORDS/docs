# Switzerland nFADP Data Protection on Cloudflare Workers / D1
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You operate a SaaS or API that processes personal data of Swiss residents. Switzerland's new
Federal Act on Data Protection (nFADP / revDSG) has been in force since 1 September 2023 and
carries fines up to CHF 250 000 for individuals and unlimited civil liability. You need records of
processing, DPIA triggers, data subject rights endpoints, breach notification within 72 hours, and
lawful cross-border transfer controls — all running on Cloudflare Workers + D1.

## Context
The nFADP (Bundesgesetz über den Datenschutz, SR 235.1) replaces the 1992 FADP and aligns closely
with GDPR. Notable Swiss-specific differences:
- Fines target **natural persons** (managers/employees), not corporations, up to CHF 250 000.
- Mandatory ROPA only for organisations processing data of >250 employees or carrying high-risk
  processing; encouraged for all others.
- Breach notification to **FDPIC** (Federal Data Protection and Information Commissioner) is
  required only when the breach is likely to cause **serious harm** to data subjects.
- Automated individual decisions require a **proactive disclosure** before the decision is taken.
- Profiling with high risk requires **explicit consent** (stricter than GDPR).
- Switzerland grants adequacy to EEA, UK, and ~15 other countries; all other transfers require
  Standard Contractual Clauses (SCCs) recognised by the Swiss Federal Council or binding corporate
  rules (BCR).

## Key Requirements — Records of Processing and DPIA

```typescript
// worker/nfadp-ropa.ts
interface RopaEntry {
  id: string;
  purpose: string;
  categories: string[];       // data categories
  subjects: string[];         // data subject groups
  recipients: string[];
  retention: string;
  transfers: { country: string; safeguard: string }[];
  highRisk: boolean;
  dpiaRef?: string;           // reference if DPIA conducted
}

export async function upsertRopa(db: D1Database, entry: RopaEntry): Promise<void> {
  await db
    .prepare(
      `INSERT INTO nfadp_ropa
         (id, purpose, categories_json, subjects_json, recipients_json,
          retention, transfers_json, high_risk, dpia_ref, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(id) DO UPDATE SET
         purpose        = excluded.purpose,
         categories_json= excluded.categories_json,
         subjects_json  = excluded.subjects_json,
         recipients_json= excluded.recipients_json,
         retention      = excluded.retention,
         transfers_json = excluded.transfers_json,
         high_risk      = excluded.high_risk,
         dpia_ref       = excluded.dpia_ref,
         updated_at     = CURRENT_TIMESTAMP`,
    )
    .bind(
      entry.id,
      entry.purpose,
      JSON.stringify(entry.categories),
      JSON.stringify(entry.subjects),
      JSON.stringify(entry.recipients),
      entry.retention,
      JSON.stringify(entry.transfers),
      entry.highRisk ? 1 : 0,
      entry.dpiaRef ?? null,
    )
    .run();
}

// DPIA trigger check — Art. 22 nFADP
export function requiresDpia(entry: RopaEntry): boolean {
  const highRiskIndicators = [
    entry.categories.some((c) =>
      ['health', 'biometric', 'genetic', 'religion', 'political', 'ethnicity'].includes(c),
    ),
    entry.highRisk,
    entry.subjects.includes('children'),
    entry.transfers.some((t) => t.safeguard === 'none'),
  ];
  return highRiskIndicators.filter(Boolean).length >= 2;
}
```

D1 schema:
```sql
CREATE TABLE IF NOT EXISTS nfadp_ropa (
  id              TEXT PRIMARY KEY,
  purpose         TEXT NOT NULL,
  categories_json TEXT NOT NULL,
  subjects_json   TEXT NOT NULL,
  recipients_json TEXT NOT NULL,
  retention       TEXT NOT NULL,
  transfers_json  TEXT NOT NULL,
  high_risk       INTEGER NOT NULL DEFAULT 0,
  dpia_ref        TEXT,
  updated_at      TEXT NOT NULL
);
```

## Data Subject Rights (Art. 25–27 nFADP)

```typescript
// worker/nfadp-rights.ts
export async function handleRightsRequest(
  request: Request,
  db: D1Database,
): Promise<Response> {
  const { type, subject_id } = await request.json<{
    type: 'access' | 'rectify' | 'delete' | 'restrict';
    subject_id: string;
  }>();

  if (type === 'access') {
    const rows = await db
      .prepare('SELECT * FROM user_data WHERE subject_id = ?')
      .bind(subject_id)
      .all();
    return Response.json({ data: rows.results });
  }

  if (type === 'delete') {
    // nFADP Art. 32 — right to destruction; log the action
    await db
      .prepare('DELETE FROM user_data WHERE subject_id = ?')
      .bind(subject_id)
      .run();
    await db
      .prepare(
        `INSERT INTO nfadp_rights_log (subject_id, type, processed_at)
         VALUES (?, 'delete', CURRENT_TIMESTAMP)`,
      )
      .bind(subject_id)
      .run();
    return Response.json({ status: 'deleted' });
  }

  return Response.json({ error: 'unsupported right type' }, { status: 400 });
}

// Automated decision disclosure — Art. 21 nFADP (must be BEFORE the decision)
export async function discloseAutomatedDecision(
  db: D1Database,
  subjectId: string,
  decisionType: string,
  logic: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO nfadp_auto_decision_log
         (subject_id, decision_type, logic_summary, disclosed_at)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(subjectId, decisionType, logic)
    .run();
}
```

## Breach Notification (Art. 24 nFADP)

```typescript
// worker/nfadp-breach.ts
interface BreachEvent {
  id: string;
  discovered_at: string;   // ISO 8601
  description: string;
  data_types: string[];
  affected_count: number;
  likely_serious_harm: boolean;
}

export async function recordBreach(db: D1Database, breach: BreachEvent): Promise<void> {
  const discoveredMs = new Date(breach.discovered_at).getTime();
  const deadlineMs   = discoveredMs + 72 * 60 * 60 * 1000;

  await db
    .prepare(
      `INSERT INTO nfadp_breach_log
         (id, discovered_at, description, data_types_json,
          affected_count, likely_serious_harm, notification_deadline, notified_fdpic)
       VALUES (?, ?, ?, ?, ?, ?, ?, 0)`,
    )
    .bind(
      breach.id,
      breach.discovered_at,
      breach.description,
      JSON.stringify(breach.data_types),
      breach.affected_count,
      breach.likely_serious_harm ? 1 : 0,
      new Date(deadlineMs).toISOString(),
    )
    .run();
}

// Cron: check for overdue FDPIC notifications
export async function checkBreachDeadlines(db: D1Database): Promise<void> {
  const overdue = await db
    .prepare(
      `SELECT * FROM nfadp_breach_log
       WHERE likely_serious_harm = 1
         AND notified_fdpic = 0
         AND notification_deadline < CURRENT_TIMESTAMP`,
    )
    .all<BreachEvent>();

  for (const breach of overdue.results) {
    console.error(`[nFADP] OVERDUE FDPIC notification — breach ${breach.id}`);
    // Trigger PagerDuty / webhook here
  }
}
```

D1 schema additions:
```sql
CREATE TABLE IF NOT EXISTS nfadp_breach_log (
  id                    TEXT PRIMARY KEY,
  discovered_at         TEXT NOT NULL,
  description           TEXT NOT NULL,
  data_types_json       TEXT NOT NULL,
  affected_count        INTEGER NOT NULL DEFAULT 0,
  likely_serious_harm   INTEGER NOT NULL DEFAULT 0,
  notification_deadline TEXT NOT NULL,
  notified_fdpic        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nfadp_rights_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id   TEXT NOT NULL,
  type         TEXT NOT NULL,
  processed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nfadp_auto_decision_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id    TEXT NOT NULL,
  decision_type TEXT NOT NULL,
  logic_summary TEXT NOT NULL,
  disclosed_at  TEXT NOT NULL
);
```

## Anti-patterns
- Notifying FDPIC for every breach regardless of harm likelihood — triggers unnecessary audits.
- Storing Swiss personal data in countries outside the Federal Council's adequacy list without SCCs.
- Charging for access requests (prohibited under Art. 25(5) nFADP).
- Running high-risk profiling without explicit consent (higher bar than legitimate interest).
- Skipping automated-decision disclosure; nFADP requires it **before** the decision, not after.

## Gotchas
- **Individual liability**: fines target the responsible employee/director, not the company — your
  DPO appointment does not shift liability unless they are the identified responsible person.
- **No DPO mandate** in nFADP, but designating a voluntary data protection advisor pauses the
  FDPIC's supervisory powers (Art. 10).
- The 72-hour clock runs from the moment your organisation becomes **aware**, not from when the
  breach started.
- Profiling with high risk of personality profile creation requires **explicit consent**; relying
  on legitimate interest is not permitted.
- SCCs must be the Swiss version (approved by Federal Council, latest version 2021) — EU SCCs are
  acceptable only if adjusted per the Swiss Addendum.

## Verification
```bash
# Confirm ROPA entries exist and high-risk ones have a DPIA reference
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, purpose, high_risk, dpia_ref FROM nfadp_ropa WHERE high_risk=1 AND dpia_ref IS NULL;"

# Find overdue breach notifications
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, notification_deadline FROM nfadp_breach_log
             WHERE likely_serious_harm=1 AND notified_fdpic=0
               AND notification_deadline < datetime('now');"

# List automated decision log entries in last 30 days
wrangler d1 execute <DB_NAME> \
  --command "SELECT * FROM nfadp_auto_decision_log
             WHERE disclosed_at > datetime('now','-30 days') LIMIT 20;"
```

## Related
- `gdpr-data-subject-rights-api.md`
- `gdpr-breach-notification-72h.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `iso-27001-continuous-monitoring-automation-workers-d1.md`
- `gdpr-dpa-standard-contractual-clauses.md`

## Sources
- nFADP (SR 235.1): https://www.fedlex.admin.ch/eli/cc/2022/491/en
- FDPIC guidance: https://www.edoeb.admin.ch/edoeb/en/path/to/project
- Swiss Federal Council adequacy list: https://www.edoeb.admin.ch/edoeb/en/path/to/project
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
