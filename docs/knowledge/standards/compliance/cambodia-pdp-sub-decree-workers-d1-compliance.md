# Cambodia Personal Data Protection Sub-Decree (No. 56) Compliance on Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform operates in Cambodia — payments (KHQR, BAKONG), e-commerce, fintech, or gaming — and processes personal data of Cambodian users. Cambodia's Sub-Decree No. 56 on Personal Data Protection (adopted May 2022) imposes consent, cross-border transfer, breach notification, and data subject rights obligations enforced by the **Ministry of Interior** and **Ministry of Digital Economy and Society**. You need to implement compliance within your Cloudflare Workers + D1 stack before launching or expanding in the Cambodian market.

---

## Context

Cambodia Sub-Decree No. 56 (2022) is the primary personal data protection instrument in Cambodia, pending a comprehensive standalone PDP law (draft under review as of 2026). Key features:

| Requirement | Detail |
|---|---|
| Lawful basis | Consent, contractual necessity, legal obligation, vital interests, legitimate interest |
| Sensitive data | Health, biometrics, genetics, racial/ethnic origin, religion, criminal records, financial status — explicit consent |
| Cross-border transfers | Permitted with consent OR where destination ensures adequate protection |
| Breach notification | Notify competent authority promptly (guidance: 72 hours); notify subjects if high risk |
| Data subject rights | Access, correction, deletion, objection, portability |
| Data localization | Sub-Decree has localization guidance for certain sectors (financial, health); general rule: transfers permitted with adequate protection |
| Registration | Data controllers processing sensitive data must notify the competent authority |
| Security | Technical and organisational measures proportionate to risk |

The Sub-Decree was issued under Article 94 of Cambodia's Digital Economy and Digital Society Policy and complements the Law on Telecommunications and Financial Sector regulations from NBC (National Bank of Cambodia).

---

## 1. Detecting Cambodian Data Subjects

```typescript
// src/middleware/cambodia-subject-detector.ts

export interface CambodiaSignals {
  cfCountry: boolean;
  phonePrefix: boolean;
  nationalId: boolean;  // Cambodian National ID: 9 digits (older) or new 12-digit format
  locale: boolean;
}

export function detectCambodiaSubject(request: Request): CambodiaSignals {
  const country = request.cf?.country ?? '';
  const phone = request.headers.get('x-user-phone') ?? '';
  const nationalId = request.headers.get('x-user-national-id') ?? '';
  const acceptLang = request.headers.get('accept-language') ?? '';

  return {
    cfCountry: country === 'KH',
    phonePrefix: /^\+855/.test(phone),
    nationalId: /^\d{9}$|^\d{12}$/.test(nationalId),
    locale: /km(?:-KH)?/i.test(acceptLang),
  };
}

export function isCambodiaSubject(signals: CambodiaSignals): boolean {
  return signals.cfCountry || signals.phonePrefix || signals.nationalId;
}
```

---

## 2. Consent Management

The Sub-Decree requires consent to be freely given, specific, informed, unambiguous, and withdrawable. For sensitive data, consent must be explicit.

```typescript
// src/services/cambodia-consent.ts

type CambodiaSensitiveCategory =
  | 'health'
  | 'biometric'
  | 'genetic'
  | 'racial_ethnic_origin'
  | 'religion'
  | 'criminal_record'
  | 'financial_status'
  | 'sexual_orientation';

type CambodiaLegalBasis =
  | 'consent'
  | 'contractual_necessity'
  | 'legal_obligation'
  | 'vital_interests'
  | 'legitimate_interest';

interface CambodiaConsentRecord {
  consentId: string;
  subjectId: string;
  legalBasis: CambodiaLegalBasis;
  purposes: string[];
  sensitiveCategories: CambodiaSensitiveCategory[];
  grantedAt: string;
  withdrawnAt?: string;
  language: 'km' | 'en';
  noticeVersion: string;
  ipAddress?: string;
}

export async function recordCambodiaConsent(
  db: D1Database,
  record: CambodiaConsentRecord,
): Promise<void> {
  if (record.sensitiveCategories.length > 0 && record.legalBasis !== 'consent') {
    throw new Error(
      'Cambodia Sub-Decree No. 56: sensitive categories require explicit consent as legal basis',
    );
  }

  await db
    .prepare(
      `INSERT INTO cambodia_consents
        (consent_id, subject_id, legal_basis, purposes, sensitive_categories,
         granted_at, language, notice_version, ip_address)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      record.consentId,
      record.subjectId,
      record.legalBasis,
      JSON.stringify(record.purposes),
      JSON.stringify(record.sensitiveCategories),
      record.grantedAt,
      record.language,
      record.noticeVersion,
      record.ipAddress ?? null,
    )
    .run();
}

export async function withdrawCambodiaConsent(
  db: D1Database,
  consentId: string,
): Promise<void> {
  const withdrawnAt = new Date().toISOString();
  await db
    .prepare(
      `UPDATE cambodia_consents
       SET withdrawn_at = ?
       WHERE consent_id = ?`,
    )
    .bind(withdrawnAt, consentId)
    .run();
}
```

---

## 3. Financial Data Localisation (NBC Sector Requirements)

The National Bank of Cambodia (NBC) Prakas on Technology Risk Management requires payment and financial data to be processed or mirrored within Cambodia. Workers can enforce a routing check.

```typescript
// src/services/cambodia-financial-routing.ts

export interface Env {
  NBC_DB_URL: string;      // Cambodia-located financial data endpoint
  NBC_DB_TOKEN: string;
  D1: D1Database;
}

interface FinancialTransactionRecord {
  transactionId: string;
  customerId: string;
  amount: number;
  currency: string;
  bakongRef?: string;  // BAKONG system reference
  createdAt: string;
}

export async function storeFinancialRecord(
  env: Env,
  record: FinancialTransactionRecord,
  isCambodianSubject: boolean,
): Promise<{ stored: 'cambodia_primary' | 'd1_only' }> {
  if (isCambodianSubject) {
    // Primary: NBC-compliant Cambodia-located database
    const res = await fetch(`${env.NBC_DB_URL}/transactions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.NBC_DB_TOKEN}`,
      },
      body: JSON.stringify(record),
    });

    if (!res.ok) {
      throw new Error(`Cambodia primary DB write failed: ${res.status}`);
    }

    // Cross-border: anonymised aggregate reference only
    await env.D1.prepare(
      `INSERT OR IGNORE INTO transactions_global
        (transaction_id, country_flag, currency, created_at)
       VALUES (?, 'KH', ?, ?)`,
    )
      .bind(record.transactionId, record.currency, record.createdAt)
      .run();

    return { stored: 'cambodia_primary' };
  }

  // Non-Cambodian subject: store directly in D1
  await env.D1.prepare(
    `INSERT INTO transactions
      (transaction_id, customer_id, amount, currency, created_at)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(
      record.transactionId,
      record.customerId,
      record.amount,
      record.currency,
      record.createdAt,
    )
    .run();

  return { stored: 'd1_only' };
}
```

---

## 4. Cross-Border Transfer Controls

The Sub-Decree permits cross-border transfers with data subject consent or where the destination ensures adequate protection.

```typescript
// src/services/cambodia-cross-border.ts

// Countries Cambodia considers to offer adequate protection (verify with MDES/MOI)
const ADEQUATE_COUNTRIES = new Set([
  'JP', 'SG', 'AU', 'NZ', 'KR', 'GB', 'DE', 'FR', 'AT', 'CH', 'CA',
  'TH', 'MY', 'VN', 'ID',
]);

type CambodiaTransferMechanism =
  | 'adequate_country'
  | 'data_subject_consent'
  | 'contractual_necessity'
  | 'vital_interests';

interface TransferEntry {
  entryId: string;
  subjectId: string;
  destinationCountry: string;
  mechanism: CambodiaTransferMechanism;
  consentId?: string;
  dataCategories: string[];
  transferredAt: string;
  sector?: 'financial' | 'health' | 'general';
}

export async function validateAndLogCambodiaTransfer(
  db: D1Database,
  entry: TransferEntry,
): Promise<void> {
  if (
    entry.mechanism === 'adequate_country' &&
    !ADEQUATE_COUNTRIES.has(entry.destinationCountry)
  ) {
    throw new Error(
      `Cambodia Sub-Decree: ${entry.destinationCountry} not recognised as adequate; use consent`,
    );
  }

  if (entry.mechanism === 'data_subject_consent' && !entry.consentId) {
    throw new Error('Consent-based transfer requires consentId');
  }

  // Financial sector: check NBC authorisation separately
  if (entry.sector === 'financial') {
    console.warn(
      'Financial data cross-border transfer: verify NBC Prakas compliance separately',
    );
  }

  await db
    .prepare(
      `INSERT INTO cambodia_transfer_log
        (entry_id, subject_id, destination_country, mechanism, consent_id,
         data_categories, transferred_at, sector)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      entry.entryId,
      entry.subjectId,
      entry.destinationCountry,
      entry.mechanism,
      entry.consentId ?? null,
      JSON.stringify(entry.dataCategories),
      entry.transferredAt,
      entry.sector ?? 'general',
    )
    .run();
}
```

---

## 5. Breach Notification

Sub-Decree No. 56 requires prompt notification to the competent authority and to data subjects when the breach presents high risk. Best practice aligns with 72-hour target.

```typescript
// src/services/cambodia-breach.ts

type CambodiaBreachRisk = 'low' | 'medium' | 'high' | 'critical';

interface CambodiaBreachRecord {
  breachId: string;
  discoveredAt: string;
  affectedSubjects: number;
  dataCategories: string[];
  sensitiveDataInvolved: boolean;
  riskLevel: CambodiaBreachRisk;
  cause: string;
  remediationSteps: string;
  notifyDataSubjects: boolean;
  sector?: 'financial' | 'health' | 'general';
}

export async function logCambodiaBreachAndScheduleNotification(
  db: D1Database,
  breach: CambodiaBreachRecord,
): Promise<void> {
  const notificationTarget = new Date(breach.discoveredAt);
  notificationTarget.setHours(notificationTarget.getHours() + 72);

  // Financial sector: NBC must also be notified per Prakas requirements
  const requiresNBCNotification =
    breach.sector === 'financial' ||
    breach.dataCategories.includes('financial_data');

  await db
    .prepare(
      `INSERT INTO cambodia_breach_log
        (breach_id, discovered_at, notification_target, affected_subjects,
         data_categories, sensitive_data_involved, risk_level, cause,
         remediation_steps, notify_data_subjects, sector,
         requires_nbc_notification, mdes_notified_at, nbc_notified_at,
         subjects_notified_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)`,
    )
    .bind(
      breach.breachId,
      breach.discoveredAt,
      notificationTarget.toISOString(),
      breach.affectedSubjects,
      JSON.stringify(breach.dataCategories),
      breach.sensitiveDataInvolved ? 1 : 0,
      breach.riskLevel,
      breach.cause,
      breach.remediationSteps,
      breach.notifyDataSubjects ? 1 : 0,
      breach.sector ?? 'general',
      requiresNBCNotification ? 1 : 0,
    )
    .run();
}
```

---

## 6. Data Subject Rights Handler

Sub-Decree No. 56 establishes rights to access, correction, deletion, and objection. No explicit response deadline in the Sub-Decree; 30 days is the recommended practice.

```typescript
// src/handlers/cambodia-dsr.ts

type CambodiaDSRType = 'access' | 'correction' | 'deletion' | 'objection' | 'portability';

export async function createCambodiaDSRTicket(
  db: D1Database,
  requestId: string,
  type: CambodiaDSRType,
  subjectId: string,
): Promise<{ deadline: string }> {
  const receivedAt = new Date().toISOString();
  const deadline = new Date();
  deadline.setDate(deadline.getDate() + 30);

  await db
    .prepare(
      `INSERT INTO cambodia_dsr_log
        (request_id, type, subject_id, received_at, deadline, status)
       VALUES (?, ?, ?, ?, ?, 'pending')`,
    )
    .bind(requestId, type, subjectId, receivedAt, deadline.toISOString())
    .run();

  if (type === 'deletion') {
    await db
      .prepare(
        `UPDATE users
         SET email = NULL, phone = NULL, national_id = NULL, deleted_at = ?
         WHERE id = ?`,
      )
      .bind(receivedAt, subjectId)
      .run();

    // Purge Cambodian consent records
    await db
      .prepare(
        `UPDATE cambodia_consents
         SET withdrawn_at = ?
         WHERE subject_id = ? AND withdrawn_at IS NULL`,
      )
      .bind(receivedAt, subjectId)
      .run();

    await db
      .prepare(
        `UPDATE cambodia_dsr_log
         SET status = 'completed', completed_at = ?
         WHERE request_id = ?`,
      )
      .bind(receivedAt, requestId)
      .run();
  }

  return { deadline: deadline.toISOString() };
}
```

---

## Anti-patterns

- **Ignoring NBC Prakas for financial data** — Sub-Decree No. 56 is the general law; NBC's Prakas on Technology Risk Management has additional obligations for payment/banking platforms that coexist and may require local storage.
- **No Khmer-language privacy notice** — Notices to Cambodian subjects should be in Khmer; English-only is insufficient for user-facing disclosures.
- **Treating Sub-Decree as final legislation** — Cambodia is drafting a standalone Personal Data Protection Law; monitor for enactment and transitional provisions.
- **Conflating BAKONG data with general PD** — BAKONG (NBC's blockchain payment system) data has specific NBC security and audit requirements on top of Sub-Decree No. 56.
- **No competent authority identification** — The Sub-Decree assigns oversight to both the Ministry of Interior and MDES; determine which applies to your sector before building notification pipelines.

---

## Gotchas

- **Dual-ministry oversight**: Depending on sector (tech vs. public security), either MDES or the Ministry of Interior may be the competent authority.
- **ASEAN Data Management Framework**: Cambodia participates in the ASEAN cross-border data framework; align with ASEAN standard contractual clauses where applicable.
- **Gaming sector**: Cambodia has a growing online gaming industry; player data is personal data under Sub-Decree No. 56.
- **Sub-Decree enforcement immaturity**: Enforcement is still developing; invest in documentation now to demonstrate good-faith compliance as the framework matures.
- **Sensitive-data notification**: Controllers processing sensitive categories must notify the relevant ministry before starting; build this into your onboarding checklist.

---

## Verification

```bash
# Breach notification overdue check
wrangler d1 execute YOUR_DB --command \
  "SELECT breach_id, sector, notification_target
   FROM cambodia_breach_log
   WHERE mdes_notified_at IS NULL
     AND notification_target < datetime('now')"

# Check sensitive consent coverage
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM cambodia_consents
   WHERE json_array_length(sensitive_categories) > 0
     AND withdrawn_at IS NULL"

# Financial sector cross-border transfers
wrangler d1 execute YOUR_DB --command \
  "SELECT destination_country, mechanism, COUNT(*)
   FROM cambodia_transfer_log
   WHERE sector = 'financial'
   GROUP BY destination_country, mechanism"

# DSR ticket aging
wrangler d1 execute YOUR_DB --command \
  "SELECT type, status,
     AVG(julianday(completed_at) - julianday(received_at)) AS avg_days
   FROM cambodia_dsr_log GROUP BY type, status"
```

---

## Related

- `vietnam-decree-13-workers-d1-compliance.md`
- `indonesia-pdp-law-workers-d1.md`
- `thailand-pdpa-workers-d1-compliance.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-localization-requirements.md`

---

## Sources

- Cambodia Sub-Decree No. 56 on Personal Data Protection (2022): [mef.gov.kh](https://www.mef.gov.kh)
- NBC Prakas on Technology Risk Management for Banking and Financial Institutions
- ASEAN Data Management Framework and Model Contractual Clauses
- Cambodia Digital Economy and Digital Society Policy Framework 2021-2035
- Cloudflare D1 data location: [developers.cloudflare.com/d1](https://developers.cloudflare.com/d1/reference/data-location/)
