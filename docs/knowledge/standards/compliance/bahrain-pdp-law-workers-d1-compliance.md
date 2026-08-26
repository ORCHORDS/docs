# Bahrain Personal Data Protection Law (PDPL) Compliance on Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform processes personal data of Bahraini residents — banking, e-commerce, healthcare, or government services. The Bahrain Personal Data Protection Law (PDPL — Legislative Decree No. 30 of 2018, effective 2019) requires lawful processing, explicit consent for sensitive data, cross-border transfer controls, and mandatory breach notification. You need to validate that your Cloudflare Workers + D1 stack is compliant before onboarding Bahraini enterprise clients or obtaining your PDPL registration.

---

## Context

The Bahrain PDPL is overseen by the **Personal Data Protection Authority (PDPA)** under the Ministry of Justice, Islamic Affairs and Waqf. It is broadly aligned with GDPR principles but has Bahrain-specific requirements:

| Requirement | Detail |
|---|---|
| Lawful basis | Consent, contract, legal obligation, vital interests, public interest, legitimate interest |
| Sensitive data | Health, religion, political opinion, criminal records — require explicit consent |
| Cross-border transfers | Permitted to countries with adequate protection OR with data subject consent |
| Breach notification | Notify PDPA "without undue delay" (guidance suggests 72 hours) |
| Data subject rights | Access, correction, deletion, objection, portability |
| Controller registration | Mandatory registration with PDPA for certain processing categories |
| DPO | Required for public bodies and high-risk processing |
| Retention | No longer than necessary for stated purpose |

Bahrain is listed as having adequate protection by several jurisdictions, making it a useful cross-border relay point for MENA-region data.

---

## 1. Detecting Bahraini Data Subjects and Residents

```typescript
// src/middleware/bahrain-subject-detector.ts

export interface BahrainSignals {
  cfCountry: boolean;
  phonePrefix: boolean;
  cpr: boolean;  // Central Population Register — 9-digit BH national ID
  locale: boolean;
}

export function detectBahrainSubject(request: Request): BahrainSignals {
  const country = request.cf?.country ?? '';
  const phone = request.headers.get('x-user-phone') ?? '';
  const cpr = request.headers.get('x-user-cpr') ?? '';
  const acceptLang = request.headers.get('accept-language') ?? '';

  return {
    cfCountry: country === 'BH',
    phonePrefix: /^\+973/.test(phone),
    // Bahrain CPR: 9 digits, first digit = century (7 = 1900s, 8 = 2000s)
    cpr: /^[78]\d{8}$/.test(cpr),
    locale: /ar(?:-BH)?/i.test(acceptLang),
  };
}

export function isBahrainSubject(signals: BahrainSignals): boolean {
  return signals.cfCountry || signals.cpr || signals.phonePrefix;
}
```

---

## 2. Consent Management for PDPL

The PDPL requires consent to be freely given, specific, informed and unambiguous. Sensitive categories require explicit (opt-in) consent.

```typescript
// src/services/bahrain-consent.ts

type SensitiveCategory =
  | 'health'
  | 'religion'
  | 'political_opinion'
  | 'biometric'
  | 'criminal_record'
  | 'sexual_orientation';

interface PDPLConsentRecord {
  consentId: string;
  dataSubjectId: string;
  purposes: string[];
  sensitiveCategories: SensitiveCategory[];
  grantedAt: string;
  withdrawnAt?: string;
  ipAddress?: string;
  userAgent?: string;
  version: string; // consent notice version
}

export async function recordConsent(
  db: D1Database,
  record: PDPLConsentRecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pdpl_consents
        (consent_id, data_subject_id, purposes, sensitive_categories,
         granted_at, ip_address, user_agent, notice_version)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      record.consentId,
      record.dataSubjectId,
      JSON.stringify(record.purposes),
      JSON.stringify(record.sensitiveCategories),
      record.grantedAt,
      record.ipAddress ?? null,
      record.userAgent ?? null,
      record.version,
    )
    .run();
}

export async function withdrawConsent(
  db: D1Database,
  consentId: string,
  withdrawnAt: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE pdpl_consents SET withdrawn_at = ? WHERE consent_id = ?`,
    )
    .bind(withdrawnAt, consentId)
    .run();
}

export async function hasValidConsent(
  db: D1Database,
  dataSubjectId: string,
  purpose: string,
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT consent_id FROM pdpl_consents
       WHERE data_subject_id = ?
         AND json_each.value = ?
         AND withdrawn_at IS NULL
       LIMIT 1`,
    )
    .bind(dataSubjectId, purpose)
    .first();
  return row !== null;
}
```

---

## 3. Lawful Basis Register

```typescript
// src/services/lawful-basis-register.ts

type PDPLLawfulBasis =
  | 'consent'
  | 'contract'
  | 'legal_obligation'
  | 'vital_interests'
  | 'public_interest'
  | 'legitimate_interest';

interface ProcessingActivity {
  activityId: string;
  name: string;
  purpose: string;
  legalBasis: PDPLLawfulBasis;
  sensitiveData: boolean;
  sensitiveCategories?: string[];
  dataSubjectCategories: string[];
  retentionDays: number;
  crossBorderTransfer: boolean;
  destinationCountries?: string[];
  createdAt: string;
}

export async function registerProcessingActivity(
  db: D1Database,
  activity: ProcessingActivity,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pdpl_processing_register
        (activity_id, name, purpose, legal_basis, sensitive_data,
         sensitive_categories, data_subject_categories, retention_days,
         cross_border_transfer, destination_countries, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(activity_id) DO UPDATE SET
         purpose = excluded.purpose,
         legal_basis = excluded.legal_basis,
         retention_days = excluded.retention_days`,
    )
    .bind(
      activity.activityId,
      activity.name,
      activity.purpose,
      activity.legalBasis,
      activity.sensitiveData ? 1 : 0,
      JSON.stringify(activity.sensitiveCategories ?? []),
      JSON.stringify(activity.dataSubjectCategories),
      activity.retentionDays,
      activity.crossBorderTransfer ? 1 : 0,
      JSON.stringify(activity.destinationCountries ?? []),
      activity.createdAt,
    )
    .run();
}
```

---

## 4. Cross-Border Transfer Safeguards

Bahrain permits cross-border transfers to countries with adequate data protection, or with data subject consent, or under contractual arrangements approved by the PDPA.

```typescript
// src/services/bahrain-cross-border.ts

// Countries with adequate protection recognised by Bahrain PDPA (illustrative — verify)
const ADEQUATE_COUNTRIES = new Set([
  'GB', 'DE', 'FR', 'AT', 'BE', 'NL', 'SE', 'NO', 'CH', 'CA', 'AU', 'NZ',
  'JP', 'KR', 'SG', 'AE',
]);

type TransferMechanism =
  | 'adequate_country'
  | 'data_subject_consent'
  | 'contractual_clauses'
  | 'vital_interests'
  | 'public_interest';

interface TransferAuditEntry {
  entryId: string;
  dataSubjectId: string;
  destinationCountry: string;
  mechanism: TransferMechanism;
  consentId?: string;
  contractReference?: string;
  transferredAt: string;
  dataCategories: string[];
}

export async function validateAndLogTransfer(
  db: D1Database,
  entry: TransferAuditEntry,
): Promise<void> {
  if (entry.mechanism === 'adequate_country') {
    if (!ADEQUATE_COUNTRIES.has(entry.destinationCountry)) {
      throw new Error(
        `Country ${entry.destinationCountry} is not on Bahrain PDPA adequate list`,
      );
    }
  }

  if (entry.mechanism === 'data_subject_consent' && !entry.consentId) {
    throw new Error('Consent-based transfer requires a consentId reference');
  }

  await db
    .prepare(
      `INSERT INTO pdpl_transfer_log
        (entry_id, data_subject_id, destination_country, mechanism,
         consent_id, contract_reference, transferred_at, data_categories)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      entry.entryId,
      entry.dataSubjectId,
      entry.destinationCountry,
      entry.mechanism,
      entry.consentId ?? null,
      entry.contractReference ?? null,
      entry.transferredAt,
      JSON.stringify(entry.dataCategories),
    )
    .run();
}
```

---

## 5. Breach Notification Pipeline

The PDPL requires notification to the PDPA without undue delay (target 72 hours) and to affected data subjects when the breach is likely to result in high risk.

```typescript
// src/services/bahrain-breach-notification.ts

type BreachSeverity = 'low' | 'medium' | 'high' | 'critical';

interface BreachRecord {
  breachId: string;
  discoveredAt: string;
  affectedSubjectsEstimate: number;
  affectedDataCategories: string[];
  severity: BreachSeverity;
  description: string;
  containmentActions: string;
  notifyDataSubjects: boolean;
}

export async function logBreach(
  db: D1Database,
  breach: BreachRecord,
): Promise<void> {
  const notificationDeadline = new Date(breach.discoveredAt);
  notificationDeadline.setHours(notificationDeadline.getHours() + 72);

  await db
    .prepare(
      `INSERT INTO pdpl_breach_log
        (breach_id, discovered_at, notification_deadline, affected_subjects_estimate,
         affected_data_categories, severity, description, containment_actions,
         notify_data_subjects, pdpa_notified_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)`,
    )
    .bind(
      breach.breachId,
      breach.discoveredAt,
      notificationDeadline.toISOString(),
      breach.affectedSubjectsEstimate,
      JSON.stringify(breach.affectedDataCategories),
      breach.severity,
      breach.description,
      breach.containmentActions,
      breach.notifyDataSubjects ? 1 : 0,
    )
    .run();
}

export async function markPDPANotified(
  db: D1Database,
  breachId: string,
  notifiedAt: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE pdpl_breach_log SET pdpa_notified_at = ? WHERE breach_id = ?`,
    )
    .bind(notifiedAt, breachId)
    .run();
}

export async function getOverdueNotifications(
  db: D1Database,
): Promise<unknown[]> {
  const result = await db
    .prepare(
      `SELECT breach_id, discovered_at, notification_deadline
       FROM pdpl_breach_log
       WHERE pdpa_notified_at IS NULL
         AND notification_deadline < datetime('now')`,
    )
    .all();
  return result.results;
}
```

---

## 6. Data Subject Rights Handler

```typescript
// src/handlers/bahrain-dsr.ts

export async function handleBahrainDSR(
  env: Env,
  request: Request,
): Promise<Response> {
  const { type, subjectId } = await request.json<{
    type: 'access' | 'correction' | 'deletion' | 'objection' | 'portability';
    subjectId: string;
  }>();

  const receivedAt = new Date().toISOString();
  // PDPL: respond within 30 days
  const deadline = new Date();
  deadline.setDate(deadline.getDate() + 30);

  await env.D1.prepare(
    `INSERT INTO pdpl_dsr_log
      (request_type, subject_id, received_at, deadline, status)
     VALUES (?, ?, ?, ?, 'pending')`,
  )
    .bind(type, subjectId, receivedAt, deadline.toISOString())
    .run();

  if (type === 'deletion') {
    await env.D1.prepare(
      `UPDATE users SET email = NULL, phone = NULL, deleted_at = ?
       WHERE id = ?`,
    )
      .bind(receivedAt, subjectId)
      .run();

    await env.D1.prepare(
      `UPDATE pdpl_dsr_log SET status = 'completed', completed_at = ?
       WHERE subject_id = ? AND request_type = 'deletion'`,
    )
      .bind(receivedAt, subjectId)
      .run();
  }

  return Response.json({
    acknowledged: true,
    deadline: deadline.toISOString(),
  });
}
```

---

## Anti-patterns

- **Treating Bahrain PDPL as identical to GDPR** — similar structure but different authority, different adequate country list, different deadlines; do not copy-paste GDPR procedures.
- **Omitting controller registration** — certain categories of processing require registration with the PDPA before starting.
- **Storing sensitive data (health/religion) without explicit consent** — legitimate interest is NOT a valid basis for sensitive categories.
- **Using email marketing without consent** — Bahrain has no separate e-privacy law, but PDPL consent applies to direct marketing.
- **Missing Arabic-language data subject notice** — notices must be provided in a language the data subject understands; Arabic is expected for Bahraini residents.

---

## Gotchas

- **CPR number as PD**: The Bahraini CPR (national ID) is personal data; treat it as a sensitive identifier.
- **Expatriate residents**: Bahrain has a large expatriate population; PDPL applies to any personal data processed in Bahrain, not just Bahraini nationals.
- **Government data sharing**: Bahrain's PDPL has a wide public interest exception that government-adjacent platforms often misapply.
- **PDPA registration fee**: The PDPA charges a registration fee; budget accordingly.
- **Adequate country list evolution**: The PDPA list can change; pin a version in your transfer log and schedule quarterly reviews.

---

## Verification

```bash
# Check breach log for overdue PDPA notifications
wrangler d1 execute YOUR_DB --command \
  "SELECT breach_id, discovered_at, notification_deadline
   FROM pdpl_breach_log
   WHERE pdpa_notified_at IS NULL
     AND notification_deadline < datetime('now')"

# Confirm sensitive-category consents are recorded
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM pdpl_consents
   WHERE json_array_length(sensitive_categories) > 0
     AND withdrawn_at IS NULL"

# Verify cross-border transfers all have a mechanism
wrangler d1 execute YOUR_DB --command \
  "SELECT mechanism, COUNT(*) FROM pdpl_transfer_log GROUP BY mechanism"

# DSR response time compliance
wrangler d1 execute YOUR_DB --command \
  "SELECT AVG(julianday(completed_at) - julianday(received_at)) AS avg_days
   FROM pdpl_dsr_log WHERE status = 'completed'"
```

---

## Related

- `gdpr-data-subject-rights-api.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `gdpr-breach-notification-72h.md`
- `saudi-arabia-pdpl-workers-d1.md`
- `uae-pdpl-personal-data-workers.md`

---

## Sources

- Bahrain Legislative Decree No. 30 of 2018 (PDPL): [legalaffairs.gov.bh](https://www.legalaffairs.gov.bh)
- Personal Data Protection Authority (PDPA) Bahrain: [pdpa.gov.bh](https://www.pdpa.gov.bh)
- PDPL Executive Regulations (2019)
- Bahrain Data Protection — Al Tamimi & Company analysis (2019)
- Cloudflare D1 data location: [developers.cloudflare.com/d1](https://developers.cloudflare.com/d1/reference/data-location/)
