# Saudi Arabia PDPL Data Protection on Cloudflare Workers / D1
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Your product handles personal data of individuals in the Kingdom of Saudi Arabia. The **Personal
Data Protection Law (PDPL)**, issued by Royal Decree M/19 (September 2021) and enforceable since
September 2023 under the implementing regulations (NDMO Regulation 1445-A), requires lawful
processing, data subject rights, breach notification to **SDAIA/NDMO** within **72 hours**, and
– critically – **data localisation** for certain categories of personal data. You need these
controls running on Cloudflare Workers + D1, using Cloudflare's KSA-compatible regions (Middle
East / UAE) where mandated.

## Context
SDAIA (Saudi Data & AI Authority) governs the PDPL; NDMO (National Data Management Office) issues
implementing regulations and handles enforcement. Key requirements:
- **Lawful processing**: consent or legitimate interest with documentation; sensitive data
  (health, genetic, biometric, credit, criminal, location) requires **explicit consent**.
- **Data localisation**: KSA-resident personal data that is sensitive, or collected by government
  entities, must be stored on infrastructure in KSA unless NDMO approves a transfer.
- **Cross-border transfers**: only to countries offering "adequate" protection (NDMO determination)
  or with NDMO approval; ad-hoc contractual safeguards must be filed.
- **Data subject rights**: right to access, rectification, deletion (with legitimate override),
  and restriction; controller must respond within **30 days**.
- **Breach notification**: to NDMO within **72 hours** of discovering a breach that may harm data
  subjects; and to affected individuals without undue delay.
- **DPO-equivalent (Privacy Officer)**: recommended; large-scale processors must appoint one.
- **DPIA**: required for high-risk processing (Art. 6 implementing regulation).
- Fines up to SAR 5 000 000 (approx. USD 1.3 M); criminal penalties for certain violations.

## Key Requirements — Lawful Basis and DPIA Register

```typescript
// worker/ksa-pdpl-processing.ts
export type KsaLawfulBasis =
  | 'consent'
  | 'contract'
  | 'legal_obligation'
  | 'vital_interests'
  | 'public_interest'
  | 'legitimate_interest';

interface ProcessingActivity {
  id: string;
  purpose: string;
  lawful_basis: KsaLawfulBasis;
  data_categories: string[];
  is_sensitive: boolean;     // health / genetic / biometric / credit / criminal / location
  requires_dpia: boolean;
  dpia_ref?: string;
  localisation_required: boolean;
  storage_region: string;    // e.g. 'ME-AE' for Middle East / UAE PoP
  updated_at?: string;
}

export async function upsertActivity(
  db: D1Database,
  act: ProcessingActivity,
): Promise<void> {
  if (act.is_sensitive && act.lawful_basis !== 'consent') {
    throw new Error(
      'KSA PDPL: sensitive personal data requires explicit consent as lawful basis',
    );
  }

  await db
    .prepare(
      `INSERT INTO ksa_processing_activities
         (id, purpose, lawful_basis, data_categories_json, is_sensitive,
          requires_dpia, dpia_ref, localisation_required, storage_region, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(id) DO UPDATE SET
         purpose                = excluded.purpose,
         lawful_basis           = excluded.lawful_basis,
         data_categories_json   = excluded.data_categories_json,
         is_sensitive           = excluded.is_sensitive,
         requires_dpia          = excluded.requires_dpia,
         dpia_ref               = excluded.dpia_ref,
         localisation_required  = excluded.localisation_required,
         storage_region         = excluded.storage_region,
         updated_at             = CURRENT_TIMESTAMP`,
    )
    .bind(
      act.id, act.purpose, act.lawful_basis,
      JSON.stringify(act.data_categories),
      act.is_sensitive ? 1 : 0,
      act.requires_dpia ? 1 : 0,
      act.dpia_ref ?? null,
      act.localisation_required ? 1 : 0,
      act.storage_region,
    )
    .run();
}
```

D1 schema:
```sql
CREATE TABLE IF NOT EXISTS ksa_processing_activities (
  id                     TEXT PRIMARY KEY,
  purpose                TEXT NOT NULL,
  lawful_basis           TEXT NOT NULL,
  data_categories_json   TEXT NOT NULL,
  is_sensitive           INTEGER NOT NULL DEFAULT 0,
  requires_dpia          INTEGER NOT NULL DEFAULT 0,
  dpia_ref               TEXT,
  localisation_required  INTEGER NOT NULL DEFAULT 0,
  storage_region         TEXT NOT NULL,
  updated_at             TEXT NOT NULL
);
```

## Data Subject Rights (Art. 4–8 PDPL — 30-day response window)

```typescript
// worker/ksa-pdpl-rights.ts
type KsaRightType = 'access' | 'rectify' | 'delete' | 'restrict';

export async function handleRight(
  db: D1Database,
  subjectId: string,
  rightType: KsaRightType,
  detail?: Record<string, string>,
): Promise<Response> {
  const deadline = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

  await db
    .prepare(
      `INSERT INTO ksa_rights_log
         (subject_id, right_type, detail_json, requested_at, response_deadline, completed_at)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, NULL)`,
    )
    .bind(subjectId, rightType, JSON.stringify(detail ?? {}), deadline)
    .run();

  if (rightType === 'access') {
    const rows = await db
      .prepare('SELECT * FROM personal_data WHERE subject_id = ?')
      .bind(subjectId)
      .all();
    return Response.json({ right: 'access', data: rows.results, deadline });
  }

  if (rightType === 'delete') {
    // Check if a legal override applies (legal obligation / public interest)
    const override = await db
      .prepare(
        `SELECT 1 FROM ksa_processing_activities
         WHERE lawful_basis IN ('legal_obligation','public_interest') LIMIT 1`,
      )
      .first();

    if (override) {
      return Response.json(
        { right: 'delete', status: 'denied', reason: 'legal_override' },
        { status: 200 },
      );
    }

    await db
      .prepare('DELETE FROM personal_data WHERE subject_id = ?')
      .bind(subjectId)
      .run();
    return Response.json({ right: 'delete', status: 'deleted' });
  }

  if (rightType === 'rectify' && detail) {
    for (const [field, value] of Object.entries(detail)) {
      await db
        .prepare(
          `UPDATE personal_data_fields SET value = ?, updated_at = CURRENT_TIMESTAMP
           WHERE subject_id = ? AND field = ?`,
        )
        .bind(value, subjectId, field)
        .run();
    }
    return Response.json({ right: 'rectify', updated: Object.keys(detail) });
  }

  return Response.json({ right: rightType, status: 'queued', deadline });
}
```

## Cross-Border Transfer Safeguards

```typescript
// worker/ksa-pdpl-transfers.ts
// Cloudflare Workers: route KSA-resident sensitive data to ME PoP
export async function routeToKsaRegion(request: Request): Promise<Response> {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;
  const country = cf?.country ?? 'unknown';

  if (country === 'SA') {
    // Force processing in ME region — use Cloudflare's regional hint header
    // In production, deploy a separate Worker in the ME region and proxy here
    const headers = new Headers(request.headers);
    headers.set('X-Data-Region', 'ME-AE');
    return fetch(request, { headers } as RequestInit);
  }

  return fetch(request);
}

export async function registerTransfer(
  db: D1Database,
  recipientCountry: string,
  purpose: string,
  safeguard: 'adequacy' | 'ndmo_approval' | 'contractual',
  ndmoApprovalRef?: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO ksa_transfer_log
         (recipient_country, purpose, safeguard, ndmo_approval_ref, registered_at)
       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(recipientCountry, purpose, safeguard, ndmoApprovalRef ?? null)
    .run();
}
```

## Breach Notification (Art. 19 PDPL — 72 h to NDMO)

```typescript
// worker/ksa-pdpl-breach.ts
export async function recordBreach(
  db: D1Database,
  id: string,
  description: string,
  dataCategories: string[],
  affectedCount: number,
  isSensitive: boolean,
): Promise<void> {
  const deadline = new Date(Date.now() + 72 * 60 * 60 * 1000).toISOString();

  await db
    .prepare(
      `INSERT INTO ksa_breach_log
         (id, description, data_categories_json, affected_count, is_sensitive,
          ndmo_deadline, discovered_at, notified_ndmo_at, notified_subjects_at)
       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, NULL)`,
    )
    .bind(
      id, description, JSON.stringify(dataCategories),
      affectedCount, isSensitive ? 1 : 0, deadline,
    )
    .run();
}

export async function checkOverdueNotifications(db: D1Database): Promise<void> {
  const overdue = await db
    .prepare(
      `SELECT id, ndmo_deadline FROM ksa_breach_log
       WHERE notified_ndmo_at IS NULL AND ndmo_deadline < CURRENT_TIMESTAMP`,
    )
    .all();

  for (const breach of overdue.results) {
    console.error(`[PDPL] OVERDUE NDMO notification — breach ${breach.id}`);
  }
}
```

D1 schema additions:
```sql
CREATE TABLE IF NOT EXISTS ksa_rights_log (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id        TEXT NOT NULL,
  right_type        TEXT NOT NULL,
  detail_json       TEXT NOT NULL DEFAULT '{}',
  requested_at      TEXT NOT NULL,
  response_deadline TEXT NOT NULL,
  completed_at      TEXT
);
CREATE TABLE IF NOT EXISTS ksa_transfer_log (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient_country   TEXT NOT NULL,
  purpose             TEXT NOT NULL,
  safeguard           TEXT NOT NULL,
  ndmo_approval_ref   TEXT,
  registered_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ksa_breach_log (
  id                    TEXT PRIMARY KEY,
  description           TEXT NOT NULL,
  data_categories_json  TEXT NOT NULL,
  affected_count        INTEGER NOT NULL DEFAULT 0,
  is_sensitive          INTEGER NOT NULL DEFAULT 0,
  ndmo_deadline         TEXT NOT NULL,
  discovered_at         TEXT NOT NULL,
  notified_ndmo_at      TEXT,
  notified_subjects_at  TEXT
);
```

## Anti-patterns
- Storing KSA-resident sensitive (health/biometric/credit/criminal) data in a Cloudflare PoP
  outside the Middle East without NDMO approval — data localisation is strictly enforced.
- Using legitimate interest as the lawful basis for sensitive data — only explicit consent applies.
- Relying on EU SCCs for cross-border transfers without checking NDMO's adequacy list — KSA does
  not automatically recognise EU SCCs.
- Responding to deletion requests without checking for legal override obligations first — PDPL
  Art. 8(b) allows retention when required by law.

## Gotchas
- Cloudflare's **Regional Services** (Smart Placement + region hints) lets you pin Worker
  execution to the Middle East region; pair this with D1 replication strategy to keep data at
  rest in the ME edge.
- The 72-hour NDMO clock runs from **discovery**, not from when incident response confirms the
  scope — do not wait for the full investigation.
- Privacy Officers are "recommended" but if your processing involves large-scale sensitive data or
  profiling, NDMO implementing regs effectively require one.
- The PDPL applies to any organisation processing data of KSA residents, regardless of where the
  organisation is located — extraterritorial reach mirrors GDPR Art. 3(2).

## Verification
```bash
# Sensitive activities without explicit consent as lawful basis
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, purpose, lawful_basis FROM ksa_processing_activities
             WHERE is_sensitive = 1 AND lawful_basis != 'consent';"

# Localisation-required activities stored outside ME
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, storage_region FROM ksa_processing_activities
             WHERE localisation_required = 1 AND storage_region NOT LIKE 'ME%';"

# Overdue NDMO breach notifications
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, ndmo_deadline FROM ksa_breach_log
             WHERE notified_ndmo_at IS NULL AND ndmo_deadline < datetime('now');"

# Rights requests near or past deadline
wrangler d1 execute <DB_NAME> \
  --command "SELECT subject_id, right_type, response_deadline FROM ksa_rights_log
             WHERE completed_at IS NULL AND response_deadline < datetime('now', '+3 days');"
```

## Related
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-localization-requirements.md`
- `gdpr-data-subject-rights-api.md`
- `gdpr-breach-notification-72h.md`
- `uae-pdpl-personal-data-workers.md`

## Sources
- PDPL Royal Decree M/19 (2021): https://sdaia.gov.sa/en/SDAIA/about/Pages/PersonalDataProtection.aspx
- NDMO Implementing Regulation 1445-A: https://ndmo.gov.sa/en/regulations
- SDAIA: https://sdaia.gov.sa/en/
- Cloudflare Regional Services: https://developers.cloudflare.com/data-localization/regional-services/
- Cloudflare D1: https://developers.cloudflare.com/d1/
