# Israel Privacy Protection Act Compliance on Cloudflare Workers / D1
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Your application processes personal data of Israeli residents. Israel's Privacy Protection Act
(PPA) 5741-1981, supplemented by the Privacy Protection Regulations (Data Security) 5777-2017 and
Amendment 14 reforms (2024), creates obligations around database registration, three-tier data
security levels, data subject access/correction rights, and breach reporting to the **Israel Law,
Information, and Technology Authority (ILITA)**. You need these controls implemented on Cloudflare
Workers + D1.

## Context
Israel has EU **adequacy status** under GDPR (renewed 2024), so EU SCCs are not required for
transfers to Israel. The PPA framework:
- **Database Registration**: Databases held by public bodies, or containing >10 000 records,
  sensitive data, or data used for direct marketing, must be registered with the Registrar of
  Databases (ILITA).
- **Data Security Regulations (2017)**: Three database security levels — **Basic**, **Medium**,
  **High** — determined by sensitivity and scale. Each level mandates specific controls
  (encryption, logging, access reviews, pen-testing).
- **ARCO-equivalent rights**: Right of access (Art. 13 PPA) and right of correction (Art. 14).
- **Sensitive data categories**: medical, financial, criminal convictions, religious/political
  opinions, sexual behaviour — require heightened protection.
- **Amendment 14 (2024)**: Strengthens breach notification (72 hours to ILITA for medium/high
  databases), introduces data-breach civil liability, and tightens direct-marketing consent.
- Fines up to ILS 3 200 000; criminal liability for database owners and managers.

## Key Requirements — Database Registration and Security Level

```typescript
// worker/israel-ppa-db-meta.ts
export type SecurityLevel = 'basic' | 'medium' | 'high';

interface DatabaseMeta {
  db_name: string;
  registration_number?: string; // from ILITA registry
  security_level: SecurityLevel;
  sensitive_categories: string[];
  record_count_estimate: number;
  data_manager_name: string;
  registered_at?: string;
}

export function classifySecurityLevel(meta: Omit<DatabaseMeta, 'security_level'>): SecurityLevel {
  const hasSensitive = meta.sensitive_categories.length > 0;
  const isLarge      = meta.record_count_estimate > 100_000;
  const isMedium     = meta.record_count_estimate > 10_000;

  if (hasSensitive && isLarge) return 'high';
  if (hasSensitive || isLarge) return 'medium';
  if (isMedium)                return 'medium';
  return 'basic';
}

export async function upsertDbMeta(db: D1Database, meta: DatabaseMeta): Promise<void> {
  await db
    .prepare(
      `INSERT INTO israel_db_registry
         (db_name, registration_number, security_level,
          sensitive_categories_json, record_count_estimate,
          data_manager_name, registered_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(db_name) DO UPDATE SET
         registration_number    = excluded.registration_number,
         security_level         = excluded.security_level,
         sensitive_categories_json = excluded.sensitive_categories_json,
         record_count_estimate  = excluded.record_count_estimate,
         data_manager_name      = excluded.data_manager_name,
         registered_at          = excluded.registered_at,
         updated_at             = CURRENT_TIMESTAMP`,
    )
    .bind(
      meta.db_name,
      meta.registration_number ?? null,
      meta.security_level,
      JSON.stringify(meta.sensitive_categories),
      meta.record_count_estimate,
      meta.data_manager_name,
      meta.registered_at ?? null,
    )
    .run();
}
```

D1 schema:
```sql
CREATE TABLE IF NOT EXISTS israel_db_registry (
  db_name                    TEXT PRIMARY KEY,
  registration_number        TEXT,
  security_level             TEXT NOT NULL CHECK (security_level IN ('basic','medium','high')),
  sensitive_categories_json  TEXT NOT NULL DEFAULT '[]',
  record_count_estimate      INTEGER NOT NULL DEFAULT 0,
  data_manager_name          TEXT NOT NULL,
  registered_at              TEXT,
  updated_at                 TEXT NOT NULL
);
```

## Data Subject Rights — Access and Correction (Art. 13–14 PPA)

```typescript
// worker/israel-ppa-rights.ts
export async function handleAccessRequest(
  db: D1Database,
  subjectId: string,
): Promise<Response> {
  const rows = await db
    .prepare(
      `SELECT field_name, field_value, collected_at
       FROM personal_data_fields
       WHERE subject_id = ?`,
    )
    .bind(subjectId)
    .all();

  await db
    .prepare(
      `INSERT INTO israel_ppa_rights_log (subject_id, type, processed_at)
       VALUES (?, 'access', CURRENT_TIMESTAMP)`,
    )
    .bind(subjectId)
    .run();

  // PPA Art. 13: must respond within 30 days
  return Response.json(
    { subject_id: subjectId, data: rows.results },
    { headers: { 'X-PPA-Request-Type': 'access' } },
  );
}

export async function handleCorrectionRequest(
  db: D1Database,
  subjectId: string,
  field: string,
  newValue: string,
): Promise<Response> {
  const { meta } = await db
    .prepare(
      `UPDATE personal_data_fields SET field_value = ?, updated_at = CURRENT_TIMESTAMP
       WHERE subject_id = ? AND field_name = ?`,
    )
    .bind(newValue, subjectId, field)
    .run();

  await db
    .prepare(
      `INSERT INTO israel_ppa_rights_log (subject_id, type, detail, processed_at)
       VALUES (?, 'correction', ?, CURRENT_TIMESTAMP)`,
    )
    .bind(subjectId, `${field} updated`)
    .run();

  if (meta.changes === 0) {
    return Response.json({ error: 'field not found' }, { status: 404 });
  }
  return Response.json({ status: 'corrected', field, subject_id: subjectId });
}

// Direct-marketing opt-out — Amendment 14 requires consent; honour opt-outs immediately
export async function optOutDirectMarketing(
  db: D1Database,
  subjectId: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO marketing_opt_outs (subject_id, opted_out_at)
       VALUES (?, CURRENT_TIMESTAMP)
       ON CONFLICT(subject_id) DO UPDATE SET opted_out_at = CURRENT_TIMESTAMP`,
    )
    .bind(subjectId)
    .run();
}
```

## Breach Notification (Amendment 14 — 72 h for Medium/High databases)

```typescript
// worker/israel-ppa-breach.ts
interface BreachReport {
  id: string;
  db_name: string;
  security_level: SecurityLevel;
  discovered_at: string;   // ISO 8601
  description: string;
  data_categories: string[];
  affected_count: number;
}

export async function recordBreach(db: D1Database, report: BreachReport): Promise<void> {
  const discoveredMs   = new Date(report.discovered_at).getTime();
  const ilita_deadline = new Date(discoveredMs + 72 * 60 * 60 * 1000).toISOString();
  // Basic level: no mandatory notification; medium/high: 72 h
  const requiresNotification = report.security_level !== 'basic';

  await db
    .prepare(
      `INSERT INTO israel_ppa_breach_log
         (id, db_name, security_level, discovered_at, description,
          data_categories_json, affected_count, requires_ilita_notification,
          ilita_deadline, notified_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)`,
    )
    .bind(
      report.id,
      report.db_name,
      report.security_level,
      report.discovered_at,
      report.description,
      JSON.stringify(report.data_categories),
      report.affected_count,
      requiresNotification ? 1 : 0,
      requiresNotification ? ilita_deadline : null,
    )
    .run();
}

// Scheduled job: alert on overdue ILITA notifications
export async function alertOverdueNotifications(db: D1Database): Promise<void> {
  const overdue = await db
    .prepare(
      `SELECT id, db_name, ilita_deadline FROM israel_ppa_breach_log
       WHERE requires_ilita_notification = 1
         AND notified_at IS NULL
         AND ilita_deadline < CURRENT_TIMESTAMP`,
    )
    .all();

  for (const row of overdue.results) {
    console.error(`[PPA] OVERDUE ILITA notification — breach ${row.id} in db ${row.db_name}`);
  }
}
```

D1 schema additions:
```sql
CREATE TABLE IF NOT EXISTS israel_ppa_rights_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id   TEXT NOT NULL,
  type         TEXT NOT NULL,
  detail       TEXT,
  processed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS israel_ppa_breach_log (
  id                         TEXT PRIMARY KEY,
  db_name                    TEXT NOT NULL,
  security_level             TEXT NOT NULL,
  discovered_at              TEXT NOT NULL,
  description                TEXT NOT NULL,
  data_categories_json       TEXT NOT NULL,
  affected_count             INTEGER NOT NULL DEFAULT 0,
  requires_ilita_notification INTEGER NOT NULL DEFAULT 0,
  ilita_deadline             TEXT,
  notified_at                TEXT
);
CREATE TABLE IF NOT EXISTS marketing_opt_outs (
  subject_id   TEXT PRIMARY KEY,
  opted_out_at TEXT NOT NULL
);
```

## Anti-patterns
- Operating a registered-category database without submitting it to ILITA's Registrar — class B
  offence under Art. 8 PPA.
- Applying Basic-level security controls to a Medium/High database — data security regulations
  mandate graduated controls; auditors look for pen-test evidence and access-review logs.
- Treating Amendment 14's 72-hour window as optional — it is now statutory for medium/high DBs.
- Sending direct-marketing messages to Israeli residents without recording affirmative consent —
  Amendment 14 aligns this with GDPR-level consent requirements.

## Gotchas
- ILITA's Registrar uses a **separate online form** for database registration; the security-level
  classification must appear on the form and be updated whenever the database changes materially.
- The 30-day response window for access requests runs from the **request date**, not from when
  you acknowledge it.
- Sensitive data (medical, financial, criminal) stored in Cloudflare R2 blobs still counts towards
  the database record total for classification purposes.
- Israel's adequacy status with the EU means no SCCs needed going EU → IL, but IL → third-country
  transfers still require consent or a contractual guarantee under PPA Art. 23.

## Verification
```bash
# Find databases without registration numbers (likely unregistered)
wrangler d1 execute <DB_NAME> \
  --command "SELECT db_name, security_level FROM israel_db_registry
             WHERE registration_number IS NULL;"

# Overdue ILITA notifications
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, db_name, ilita_deadline FROM israel_ppa_breach_log
             WHERE requires_ilita_notification=1 AND notified_at IS NULL
               AND ilita_deadline < datetime('now');"

# Marketing opt-outs rate
wrangler d1 execute <DB_NAME> \
  --command "SELECT COUNT(*) as opt_outs FROM marketing_opt_outs;"
```

## Related
- `gdpr-data-subject-rights-api.md`
- `gdpr-breach-notification-72h.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-retention-automated-deletion-workers.md`

## Sources
- Privacy Protection Act 5741-1981: https://www.gov.il/en/departments/topics/privacy-protection
- Privacy Protection Regulations (Data Security) 5777-2017: https://www.gov.il/he/Departments/Guides/guidelines-data-security
- ILITA: https://www.gov.il/en/departments/the_privacy_protection_authority
- Amendment 14 summary: https://www.gov.il/en/departments/news/amendment14-privacy
- Cloudflare D1: https://developers.cloudflare.com/d1/
