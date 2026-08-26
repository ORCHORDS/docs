# Qatar Personal Data Privacy Protection Law Compliance on Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform operates in Qatar — fintech, healthcare, e-commerce, or government services — and processes personal data of Qatari residents. Qatar Law No. 13 of 2016 (Personal Data Privacy Protection Law, PDPPL) and its executive regulations impose consent, localization guidance, cross-border transfer controls, and breach notification obligations. You need to implement compliance in a Cloudflare Workers + D1 stack while navigating Qatar's National Cyber Security Agency (NCSA) requirements and the Qatar Financial Centre (QFC) data protection regime for financial entities.

---

## Context

Qatar has two overlapping data protection frameworks:

| Framework | Scope | Authority |
|---|---|---|
| Law No. 13 of 2016 (PDPPL) | All sectors, natural persons in Qatar | Ministry of Transport and Communications (MOTC) |
| QFC Data Protection Regulations 2021 | Entities registered in QFC | QFC Regulatory Authority (QFCRA) |

Key PDPPL requirements:

| Obligation | Detail |
|---|---|
| Lawful basis | Consent, contract, legal obligation, vital interests, public task, legitimate interest |
| Sensitive data | Health, genetics, religion, political views, sexual orientation — explicit consent required |
| Cross-border transfers | Only to countries with adequate protection or with MOTC approval |
| Breach notification | Notify MOTC "promptly" (target 72 hours); notify subjects if high risk |
| Data subject rights | Access, correction, deletion, restriction, objection, portability |
| Controller obligations | Register with MOTC; appoint data protection officer for high-risk processing |
| Retention | No longer than purpose requires; anonymise or delete thereafter |

The QFC regime is explicitly GDPR-inspired and applies stricter standards to financial services firms operating in the QFC free zone.

---

## 1. Dual-Regime Detection

```typescript
// src/middleware/qatar-regime-detector.ts

export interface QatarContext {
  isQatarResident: boolean;
  isQFCEntity: boolean;  // set by your business logic (entity type)
  signals: {
    cfCountry: boolean;
    phonePrefix: boolean;
    qatarNationalId: boolean;
  };
}

export function detectQatarContext(
  request: Request,
  entityType: 'qfc' | 'general',
): QatarContext {
  const country = request.cf?.country ?? '';
  const phone = request.headers.get('x-user-phone') ?? '';
  const nationalId = request.headers.get('x-user-national-id') ?? '';

  const signals = {
    cfCountry: country === 'QA',
    phonePrefix: /^\+974/.test(phone),
    // Qatar national ID: 11 digits
    qatarNationalId: /^\d{11}$/.test(nationalId),
  };

  return {
    isQatarResident: signals.cfCountry || signals.phonePrefix || signals.qatarNationalId,
    isQFCEntity: entityType === 'qfc',
    signals,
  };
}
```

---

## 2. Consent Recording for PDPPL

Qatar PDPPL requires consent to be documented. For sensitive categories, silence or inaction does not constitute consent.

```typescript
// src/services/qatar-consent.ts

type QatarSensitiveCategory =
  | 'health'
  | 'genetics'
  | 'religion'
  | 'political_views'
  | 'sexual_orientation'
  | 'criminal_record'
  | 'biometric';

type QatarLegalBasis =
  | 'consent'
  | 'contract'
  | 'legal_obligation'
  | 'vital_interests'
  | 'public_task'
  | 'legitimate_interest';

interface ConsentRecord {
  consentId: string;
  subjectId: string;
  basis: QatarLegalBasis;
  purposes: string[];
  sensitiveCategories: QatarSensitiveCategory[];
  grantedAt: string;
  withdrawnAt?: string;
  noticeVersion: string;
  language: 'ar' | 'en';
}

export async function recordQatarConsent(
  db: D1Database,
  record: ConsentRecord,
): Promise<void> {
  if (record.sensitiveCategories.length > 0 && record.basis !== 'consent') {
    throw new Error(
      'Sensitive categories under PDPPL require explicit consent as legal basis',
    );
  }

  await db
    .prepare(
      `INSERT INTO qatar_consents
        (consent_id, subject_id, basis, purposes, sensitive_categories,
         granted_at, notice_version, language)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      record.consentId,
      record.subjectId,
      record.basis,
      JSON.stringify(record.purposes),
      JSON.stringify(record.sensitiveCategories),
      record.grantedAt,
      record.noticeVersion,
      record.language,
    )
    .run();
}

export async function withdrawQatarConsent(
  db: D1Database,
  consentId: string,
): Promise<void> {
  const withdrawnAt = new Date().toISOString();
  await db
    .prepare(
      `UPDATE qatar_consents SET withdrawn_at = ? WHERE consent_id = ?`,
    )
    .bind(withdrawnAt, consentId)
    .run();
}
```

---

## 3. Cross-Border Transfer Controls

Qatar permits transfers to countries with adequate protection (as assessed by MOTC) or where the MOTC has given explicit approval. QFC entities additionally follow QFCRA adequacy decisions (closer to EU approach).

```typescript
// src/services/qatar-transfer-controls.ts

// MOTC adequate protection list (illustrative — verify current list with MOTC)
const MOTC_ADEQUATE_COUNTRIES = new Set([
  'GB', 'DE', 'FR', 'AT', 'BE', 'NL', 'CH', 'AU', 'CA', 'NZ', 'JP',
  'SG', 'KR', 'AE', 'BH',
]);

type TransferMechanism =
  | 'adequate_country'
  | 'motc_approval'
  | 'data_subject_consent'
  | 'contractual_necessity'
  | 'vital_interests';

interface TransferEntry {
  entryId: string;
  subjectId: string;
  destinationCountry: string;
  mechanism: TransferMechanism;
  approvalReference?: string;
  consentId?: string;
  dataCategories: string[];
  transferredAt: string;
  regime: 'pdppl' | 'qfc';
}

export async function validateAndRecordTransfer(
  db: D1Database,
  entry: TransferEntry,
): Promise<void> {
  if (
    entry.mechanism === 'adequate_country' &&
    !MOTC_ADEQUATE_COUNTRIES.has(entry.destinationCountry)
  ) {
    throw new Error(
      `Destination ${entry.destinationCountry} not on MOTC adequate list; use motc_approval or consent`,
    );
  }

  if (entry.mechanism === 'motc_approval' && !entry.approvalReference) {
    throw new Error('MOTC approval mechanism requires approvalReference');
  }

  await db
    .prepare(
      `INSERT INTO qatar_transfer_log
        (entry_id, subject_id, destination_country, mechanism,
         approval_reference, consent_id, data_categories,
         transferred_at, regime)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      entry.entryId,
      entry.subjectId,
      entry.destinationCountry,
      entry.mechanism,
      entry.approvalReference ?? null,
      entry.consentId ?? null,
      JSON.stringify(entry.dataCategories),
      entry.transferredAt,
      entry.regime,
    )
    .run();
}
```

---

## 4. Breach Notification

```typescript
// src/services/qatar-breach-handler.ts

type BreachRiskLevel = 'low' | 'medium' | 'high' | 'critical';

interface QatarBreach {
  breachId: string;
  discoveredAt: string;
  affectedSubjectsCount: number;
  dataCategories: string[];
  riskLevel: BreachRiskLevel;
  cause: string;
  containmentMeasures: string;
  regime: 'pdppl' | 'qfc';
}

export async function logQatarBreach(
  db: D1Database,
  breach: QatarBreach,
): Promise<void> {
  const notificationDeadline = new Date(breach.discoveredAt);
  notificationDeadline.setHours(notificationDeadline.getHours() + 72);

  // QFC entities must also notify QFCRA separately
  const requiresDualNotification = breach.regime === 'qfc';

  await db
    .prepare(
      `INSERT INTO qatar_breach_log
        (breach_id, discovered_at, notification_deadline, affected_subjects_count,
         data_categories, risk_level, cause, containment_measures, regime,
         requires_dual_notification, motc_notified_at, qfcra_notified_at,
         subjects_notified)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)`,
    )
    .bind(
      breach.breachId,
      breach.discoveredAt,
      notificationDeadline.toISOString(),
      breach.affectedSubjectsCount,
      JSON.stringify(breach.dataCategories),
      breach.riskLevel,
      breach.cause,
      breach.containmentMeasures,
      breach.regime,
      requiresDualNotification ? 1 : 0,
    )
    .run();
}

export async function markBreachNotified(
  db: D1Database,
  breachId: string,
  authority: 'motc' | 'qfcra',
  notifiedAt: string,
): Promise<void> {
  const column = authority === 'motc' ? 'motc_notified_at' : 'qfcra_notified_at';
  await db
    .prepare(`UPDATE qatar_breach_log SET ${column} = ? WHERE breach_id = ?`)
    .bind(notifiedAt, breachId)
    .run();
}
```

---

## 5. Data Subject Rights

PDPPL grants access, correction, deletion, and objection rights. Response deadline: 30 days (extendable by 30 days with notice).

```typescript
// src/handlers/qatar-dsr.ts

type QatarDSRType = 'access' | 'correction' | 'deletion' | 'objection' | 'portability' | 'restriction';

interface DSRRequest {
  requestId: string;
  type: QatarDSRType;
  subjectId: string;
  receivedAt: string;
  regime: 'pdppl' | 'qfc';
}

export async function createDSRTicket(
  db: D1Database,
  req: DSRRequest,
): Promise<string> {
  const deadline = new Date(req.receivedAt);
  deadline.setDate(deadline.getDate() + 30);

  await db
    .prepare(
      `INSERT INTO qatar_dsr_log
        (request_id, type, subject_id, received_at, deadline, regime, status)
       VALUES (?, ?, ?, ?, ?, ?, 'pending')`,
    )
    .bind(
      req.requestId,
      req.type,
      req.subjectId,
      req.receivedAt,
      deadline.toISOString(),
      req.regime,
    )
    .run();

  return deadline.toISOString();
}

export async function completeDSR(
  db: D1Database,
  requestId: string,
  notes: string,
): Promise<void> {
  const completedAt = new Date().toISOString();
  await db
    .prepare(
      `UPDATE qatar_dsr_log
       SET status = 'completed', completed_at = ?, notes = ?
       WHERE request_id = ?`,
    )
    .bind(completedAt, notes, requestId)
    .run();
}
```

---

## 6. QFC-Specific Enhanced Controls

QFC entities operate under a stricter GDPR-aligned regime with additional accountability requirements.

```typescript
// src/services/qfc-accountability.ts

interface QFCDPIARecord {
  dpiaId: string;
  processingActivity: string;
  riskAssessment: string;
  mitigationMeasures: string;
  dpoReviewedAt?: string;
  approvedAt?: string;
  nextReviewDate: string;
}

export async function recordQFCDPIA(
  db: D1Database,
  dpia: QFCDPIARecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO qfc_dpias
        (dpia_id, processing_activity, risk_assessment, mitigation_measures,
         dpo_reviewed_at, approved_at, next_review_date)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(dpia_id) DO UPDATE SET
         risk_assessment = excluded.risk_assessment,
         mitigation_measures = excluded.mitigation_measures,
         next_review_date = excluded.next_review_date`,
    )
    .bind(
      dpia.dpiaId,
      dpia.processingActivity,
      dpia.riskAssessment,
      dpia.mitigationMeasures,
      dpia.dpoReviewedAt ?? null,
      dpia.approvedAt ?? null,
      dpia.nextReviewDate,
    )
    .run();
}
```

---

## Anti-patterns

- **Conflating PDPPL and QFC regimes** — QFC entities must satisfy both; general entities only need PDPPL. Separate your logging tables or use a `regime` column.
- **Using legitimate interest for sensitive data** — PDPPL requires explicit consent for sensitive categories regardless of other bases.
- **Ignoring Arabic-language notice requirements** — Notices to Qatari residents must be in Arabic (or bilingual).
- **Storing without MOTC registration** — Processing that triggers registration thresholds requires registration before starting.
- **Assuming GDPR SCCs work for Qatar** — Qatar has its own adequacy assessment process; SCCs do not automatically satisfy Qatar requirements.

---

## Gotchas

- **Dual regimes for QFC entities**: QFC data protection regulations impose stricter, GDPR-like obligations. If your entity is registered in QFC (not mainland Qatar), apply both.
- **Large expatriate workforce**: Qatar's population is predominantly non-Qatari; PDPPL covers all natural persons whose data is processed in Qatar, regardless of nationality.
- **National ID sensitivity**: Qatar National IDs (QIDs) are treated as sensitive personal data; apply consent or contract basis before storing.
- **NCSA Cyber Framework**: Qatar's National Cyber Security Agency has additional security requirements for critical sectors (finance, health, energy) that overlap with PDPPL.
- **Retention defaults**: The PDPPL does not specify default retention periods by category; align with your purposes and document them in the register.

---

## Verification

```bash
# Breach notification overdue check
wrangler d1 execute YOUR_DB --command \
  "SELECT breach_id, regime, notification_deadline
   FROM qatar_breach_log
   WHERE motc_notified_at IS NULL
     AND notification_deadline < datetime('now')"

# Sensitive-category consent audit
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM qatar_consents
   WHERE json_array_length(sensitive_categories) > 0
     AND withdrawn_at IS NULL"

# Transfer mechanism breakdown
wrangler d1 execute YOUR_DB --command \
  "SELECT mechanism, regime, COUNT(*) FROM qatar_transfer_log GROUP BY mechanism, regime"

# DSR deadline compliance
wrangler d1 execute YOUR_DB --command \
  "SELECT type, status,
     AVG(julianday(completed_at) - julianday(received_at)) AS avg_days
   FROM qatar_dsr_log GROUP BY type, status"
```

---

## Related

- `bahrain-pdp-law-workers-d1-compliance.md`
- `uae-pdpl-personal-data-workers.md`
- `saudi-arabia-pdpl-workers-d1.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `gdpr-data-subject-rights-api.md`

---

## Sources

- Qatar Law No. 13 of 2016 (Personal Data Privacy Protection Law): [almeezan.qa](https://www.almeezan.qa)
- QFC Data Protection Regulations 2021: [qfcra.com](https://www.qfcra.com)
- Qatar NCSA Cybersecurity Framework: [ncsa.gov.qa](https://www.ncsa.gov.qa)
- Al Tamimi & Company Qatar PDPPL Analysis (2022)
- Cloudflare D1 data location: [developers.cloudflare.com/d1](https://developers.cloudflare.com/d1/reference/data-location/)
