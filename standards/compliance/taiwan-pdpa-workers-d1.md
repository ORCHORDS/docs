# Taiwan Personal Data Protection Act — Cloudflare Workers D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service collects, stores, or uses personal data of Taiwanese residents, or your entity is incorporated in Taiwan. The Taiwan Personal Data Protection Act (個人資料保護法, PDPA, enacted 2010, amended 2023) and its subordinate regulations impose consent, purpose-limitation, data-subject-rights, security, and cross-border-transfer obligations. You need to implement these controls in Cloudflare Workers without a dedicated Taiwanese origin server.

---

## Context

Taiwan's PDPA, administered by the **Personal Data Protection Commission (PDPC)** (established 2023 under the 2023 amendments), governs all automated and non-automated processing of personal data by both public and private entities. Key obligations:

- **Collection**: Must specify a specific, explicit purpose (目的) and have a lawful basis (consent, contract, legal obligation, vital interests, public interest, or legitimate interests — art. 6 for general data; art. 6(1) requires specific bases for sensitive data).
- **Sensitive ("special") data** (art. 6): medical history, disability, criminal records, sexual life, genetic data, health examination, race/ethnicity — collection requires explicit consent or specific statutory basis.
- **Data subject rights** (art. 10, 11): right of access, correction, deletion/cessation of processing, and objection.  Controllers must respond within **30 days** (extendable to 60 days with notice).
- **International transfers** (art. 21): the PDPC may restrict transfers to countries without "adequate" protection; controllers must comply with any such restriction orders.
- **Security** (art. 27): controllers must take "necessary security measures" appropriate to risk; subordinate regulations (施行細則) specify technical standards.
- **Breach notification**: the 2023 amendments require notification to affected individuals and the PDPC within **72 hours** of discovering a breach of sensitive data.
- **Sanctions** (art. 47–48): civil fines up to NTD 15 million; criminal penalties up to 5 years imprisonment for intentional violations.

---

## 1. Purpose Registry and Lawful Basis Enforcement

The PDPA ties each processing operation to a declared purpose code (目的代碼) published by the PDPC.

```typescript
// workers/taiwan-pdpa-purpose-registry.ts
import { Env } from './types';

// Common PDPC purpose codes (illustrative subset)
const VALID_PURPOSE_CODES = new Set([
  '040', // Financial business
  '069', // Electronic commerce
  '090', // Consumer, customer management and service
  '181', // Other business
  '152', // Advertising or commercial activity
]);

interface ProcessingRecord {
  id: string;
  dataSubjectId: string;
  purposeCode: string;
  purposeDescription: string;
  lawfulBasis: 'consent' | 'contract' | 'legal_obligation' | 'vital_interests' | 'public_interest' | 'legitimate_interests';
  dataCategories: string[];
  retentionDays: number;
  createdAt: string;
}

export async function registerProcessingActivity(
  env: Env,
  dataSubjectId: string,
  purposeCode: string,
  purposeDescription: string,
  lawfulBasis: ProcessingRecord['lawfulBasis'],
  dataCategories: string[],
  retentionDays: number,
): Promise<string> {
  if (!VALID_PURPOSE_CODES.has(purposeCode)) {
    throw new Error(`Invalid PDPC purpose code: ${purposeCode}`);
  }

  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO taiwan_processing_registry
     (id, data_subject_id, purpose_code, purpose_description, lawful_basis,
      data_categories, retention_days, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))`,
  ).bind(
    id, dataSubjectId, purposeCode, purposeDescription,
    lawfulBasis, JSON.stringify(dataCategories), retentionDays,
  ).run();

  return id;
}
```

---

## 2. Consent Management for Sensitive (Special) Data

Art. 6 sensitive data requires explicit written or equivalent consent; purpose must be stated at collection time.

```typescript
// workers/taiwan-pdpa-consent.ts
type SensitiveCategory =
  | 'medical_history' | 'disability' | 'criminal_record'
  | 'sexual_life' | 'genetic_data' | 'health_examination'
  | 'race_ethnicity';

interface TaiwanConsentRecord {
  id: string;
  dataSubjectId: string;
  sensitiveCategories: SensitiveCategory[];
  purposeCode: string;
  consentText: string;     // verbatim text shown, in Traditional Chinese or English
  grantedAt: string;
  revokedAt: string | null;
  collectionChannel: 'web_form' | 'api' | 'in_person' | 'paper';
  ipAddress: string;
}

export async function grantSensitiveConsent(
  env: Env,
  dataSubjectId: string,
  sensitiveCategories: SensitiveCategory[],
  purposeCode: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO taiwan_sensitive_consent
     (id, data_subject_id, sensitive_categories, purpose_code, consent_text,
      granted_at, revoked_at, collection_channel, ip_address)
     VALUES (?, ?, ?, ?, ?, datetime('now'), NULL, 'web_form', ?)`,
  ).bind(
    id, dataSubjectId, JSON.stringify(sensitiveCategories),
    purposeCode, consentText,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return id;
}

export async function revokeSensitiveConsent(env: Env, consentId: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE taiwan_sensitive_consent
     SET revoked_at = datetime('now')
     WHERE id = ? AND revoked_at IS NULL`,
  ).bind(consentId).run();
}
```

---

## 3. Data Subject Rights — 30-Day Response Window

Art. 10–11 give subjects the right to query, correct, delete, or object to processing. Controllers have 30 days (extendable to 60) to respond.

```typescript
// workers/taiwan-pdpa-dsr.ts
type TaiwanDSRType = 'inquiry' | 'correction' | 'deletion' | 'cessation' | 'objection';

interface TaiwanDSRTicket {
  id: string;
  dataSubjectId: string;
  requestType: TaiwanDSRType;
  receivedAt: string;
  deadlineAt: string;          // 30 days
  extendedDeadlineAt: string | null; // up to 60 days if notified
  status: 'open' | 'extended' | 'completed' | 'denied';
  fee: number;                 // PDPA allows controllers to charge a fee for inquiry copies
}

export async function openTaiwanDSR(
  env: Env,
  dataSubjectId: string,
  requestType: TaiwanDSRType,
  fee: number = 0,
): Promise<TaiwanDSRTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now);
  deadline.setDate(deadline.getDate() + 30);

  const ticket: TaiwanDSRTicket = {
    id, dataSubjectId, requestType,
    receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    extendedDeadlineAt: null,
    status: 'open',
    fee,
  };

  await env.DB.prepare(
    `INSERT INTO taiwan_dsr
     (id, data_subject_id, request_type, received_at, deadline_at,
      extended_deadline_at, status, fee)
     VALUES (?, ?, ?, ?, ?, NULL, 'open', ?)`,
  ).bind(
    id, dataSubjectId, requestType,
    ticket.receivedAt, ticket.deadlineAt, fee,
  ).run();

  return ticket;
}

export async function extendTaiwanDSR(env: Env, ticketId: string): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT received_at FROM taiwan_dsr WHERE id = ?`,
  ).bind(ticketId).first<{ received_at: string }>();

  if (!row) throw new Error('DSR not found');

  const extended = new Date(row.received_at);
  extended.setDate(extended.getDate() + 60); // max 60 days from receipt

  await env.DB.prepare(
    `UPDATE taiwan_dsr
     SET status = 'extended', extended_deadline_at = ?
     WHERE id = ?`,
  ).bind(extended.toISOString(), ticketId).run();
}
```

---

## 4. 72-Hour Breach Notification (2023 Amendment)

The 2023 amendments require notification to the PDPC and to affected individuals within 72 hours when sensitive data is breached.

```typescript
// workers/taiwan-pdpa-breach.ts
interface TaiwanBreachRecord {
  incidentId: string;
  discoveredAt: string;
  pdpcDeadlineAt: string;   // + 72 h
  affectedCount: number;
  involvesSensitiveData: boolean;
  dataCategories: string[];
  severityLevel: 'low' | 'medium' | 'high';
  pdpcNotifiedAt: string | null;
  affectedNotifiedAt: string | null;
}

export async function recordTaiwanBreach(
  env: Env,
  affectedCount: number,
  dataCategories: string[],
  severityLevel: TaiwanBreachRecord['severityLevel'],
): Promise<TaiwanBreachRecord> {
  const SENSITIVE: string[] = [
    'medical_history','disability','criminal_record',
    'sexual_life','genetic_data','health_examination','race_ethnicity',
  ];

  const now = new Date();
  const deadline = new Date(now.getTime() + 72 * 60 * 60 * 1000);
  const involvesSensitiveData = dataCategories.some(c => SENSITIVE.includes(c));

  const record: TaiwanBreachRecord = {
    incidentId: crypto.randomUUID(),
    discoveredAt: now.toISOString(),
    pdpcDeadlineAt: deadline.toISOString(),
    affectedCount,
    involvesSensitiveData,
    dataCategories,
    severityLevel,
    pdpcNotifiedAt: null,
    affectedNotifiedAt: null,
  };

  await env.DB.prepare(
    `INSERT INTO taiwan_breach_log
     (incident_id, discovered_at, pdpc_deadline_at, affected_count,
      involves_sensitive_data, data_categories, severity_level,
      pdpc_notified_at, affected_notified_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)`,
  ).bind(
    record.incidentId, record.discoveredAt, record.pdpcDeadlineAt,
    record.affectedCount, record.involvesSensitiveData ? 1 : 0,
    JSON.stringify(record.dataCategories), record.severityLevel,
  ).run();

  return record;
}
```

---

## 5. International Transfer Restriction Guard

The PDPC may issue orders restricting transfers to specific countries. This guard checks a D1-maintained restriction list before allowing outbound data flows.

```typescript
// workers/taiwan-pdpa-transfer.ts
interface TransferRestriction {
  country: string;
  restrictedAt: string;
  liftedAt: string | null;
  reason: string;
}

export async function isTransferAllowed(
  env: Env,
  destinationCountry: string,
): Promise<{ allowed: boolean; reason: string }> {
  const restriction = await env.DB.prepare(
    `SELECT country, reason FROM taiwan_transfer_restrictions
     WHERE country = ? AND lifted_at IS NULL`,
  ).bind(destinationCountry).first<Pick<TransferRestriction, 'country' | 'reason'>>();

  if (restriction) {
    return { allowed: false, reason: `PDPC restriction: ${restriction.reason}` };
  }

  return { allowed: true, reason: 'no_active_restriction' };
}

export async function addTransferRestriction(
  env: Env,
  country: string,
  reason: string,
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO taiwan_transfer_restrictions
     (country, restricted_at, lifted_at, reason)
     VALUES (?, datetime('now'), NULL, ?)`,
  ).bind(country, reason).run();
}

export async function liftTransferRestriction(env: Env, country: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE taiwan_transfer_restrictions SET lifted_at = datetime('now') WHERE country = ? AND lifted_at IS NULL`,
  ).bind(country).run();
}
```

---

## Anti-patterns

- **Using a single catch-all purpose code.** Each distinct processing activity must have its own declared purpose; mixing purposes violates the purpose-limitation principle (art. 5(2)).
- **Ignoring the fee mechanism.** The PDPA allows controllers to charge a cost-recovery fee for inquiry/copy requests — failing to codify this leads to unbounded operational load.
- **Treating deletion as soft-delete only.** Art. 11 deletion requires that data be permanently removed from all systems, not just flagged; audit the retention pipeline accordingly.
- **Forgetting subordinate regulations.** The Enforcement Rules (施行細則) and industry-specific regulations (finance, medical) add requirements on top of the PDPA.

---

## Gotchas

- The **PDPC** (個人資料保護委員會) is the new dedicated supervisory authority created by the 2023 amendments; prior enforcement was fragmented across sectoral regulators.
- Art. 28 provides civil liability: NTD 500–20,000 per affected person per violation; class actions are possible under art. 34.
- The 2023 amendment's 72-hour breach notification applies **only to sensitive data** breaches. General data breaches have a "without undue delay" standard.
- Cloudflare's **Tokyo (NRT)** and **Hong Kong (HKG)** PoPs are the nearest to Taiwan — neither places data residency within Taiwan. Check whether your use case requires Taiwanese territorial storage.
- Purpose codes are published by the PDPC and numbered; using an unlisted or incorrect code is itself a violation.

---

## Verification

```bash
# 1. Check DSR tickets past 30-day window
wrangler d1 execute DB --command \
  "SELECT id, request_type, deadline_at FROM taiwan_dsr
   WHERE status = 'open' AND deadline_at < datetime('now');"

# 2. Sensitive data consents without revocation for lapsed purposes
wrangler d1 execute DB --command \
  "SELECT id, data_subject_id, purpose_code FROM taiwan_sensitive_consent
   WHERE revoked_at IS NULL
   ORDER BY granted_at;"

# 3. Breach notifications not sent within 72 h
wrangler d1 execute DB --command \
  "SELECT incident_id, discovered_at, pdpc_deadline_at FROM taiwan_breach_log
   WHERE pdpc_notified_at IS NULL AND pdpc_deadline_at < datetime('now');"

# 4. Active transfer restrictions
wrangler d1 execute DB --command \
  "SELECT country, reason, restricted_at FROM taiwan_transfer_restrictions WHERE lifted_at IS NULL;"
```

---

## Related

- `cross-border-data-transfer-mechanisms.md`
- `gdpr-data-subject-rights-api.md`
- `singapore-pdpa-workers-d1.md`
- `appi-japan-compliance.md`
- `south-korea-pipa-workers.md`

---

## Sources

- Taiwan Personal Data Protection Act (2010, amended 2023): https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=I0050021
- PDPC Purpose Code List: https://www.pdpc.gov.tw/
- Taiwan PDPA Enforcement Rules: https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=I0050022
- Cloudflare Data Localization Suite: https://developers.cloudflare.com/data-localization/
