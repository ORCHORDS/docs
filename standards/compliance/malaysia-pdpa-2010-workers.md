# Malaysia Personal Data Protection Act 2010 — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service processes personal data in the course of **commercial transactions** involving Malaysian residents, or your entity carries on business in Malaysia. The Malaysia Personal Data Protection Act 2010 (PDPA 2010), administered by the **Department of Personal Data Protection (JPDP)** under the Ministry of Communications, imposes notice, consent, security, and data-correction obligations. You need to implement these controls in Cloudflare Workers and D1 without a dedicated Malaysian origin server.

---

## Context

Malaysia's PDPA 2010 was the first personal data legislation in Southeast Asia. Important characteristics:

- **Scope**: Applies to data processors in Malaysia AND to processors outside Malaysia who use equipment in Malaysia for processing (s.3). Does **not** apply to the federal/state government.
- **Seven principles** (Part II): General, Notice and Choice, Disclosure, Security, Retention, Data Integrity, and Access.
- **Sensitive personal data** (s.4): health and medical condition, political opinions, religious beliefs or similar, offences/alleged offences, criminal proceedings/sentencing, genetic data — requires explicit consent.
- **Notice** (s.7): must be given at or before collection in Bahasa Malaysia or English.
- **Consent withdrawal** (s.38): data subject may withdraw at any time.
- **Data correction** (s.34–36): subject may request correction; controller must respond within **21 days**.
- **Cross-border transfers** (s.129): prohibited to countries on a whitelist published by the Minister unless the subject consents, a contract with adequate protection is in place, or a derogation applies.
- **Registration**: data processors in certain sectors must register with JPDP (Order 2013).
- **Sanctions**: fines up to MYR 500,000 and/or up to 3 years imprisonment.
- The PDPA Amendment Act 2024 (expected to come into force in stages through 2025–2026) introduces breach notification, a mandatory DPO for some sectors, and expanded rights.

---

## 1. Notice and Choice — Collection Point

PDPA s.7 requires notice at the point of collection. The Worker serves and logs the notice acknowledgement.

```typescript
// workers/malaysia-pdpa-notice.ts
import { Env } from './types';

interface NoticeAcknowledgement {
  id: string;
  dataSubjectId: string;
  noticeVersion: string;     // version of the notice text
  language: 'ms' | 'en';    // Bahasa Malaysia or English
  purposeList: string[];     // stated collection purposes
  acknowledgedAt: string;
  ipAddress: string;
  userAgent: string;
}

export async function recordNoticeAck(
  env: Env,
  dataSubjectId: string,
  noticeVersion: string,
  language: 'ms' | 'en',
  purposeList: string[],
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO malaysia_notice_log
     (id, data_subject_id, notice_version, language, purpose_list,
      acknowledged_at, ip_address, user_agent)
     VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?)`,
  ).bind(
    id, dataSubjectId, noticeVersion, language,
    JSON.stringify(purposeList),
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
    request.headers.get('User-Agent') ?? 'unknown',
  ).run();

  return id;
}
```

---

## 2. Sensitive Data Consent Gate

Before processing sensitive personal data (health, religion, political opinion, etc.), the controller must obtain explicit consent beyond general notice acknowledgement.

```typescript
// workers/malaysia-pdpa-sensitive-consent.ts
const SENSITIVE_CATEGORIES = [
  'health_medical', 'political_opinion', 'religious_belief',
  'offence_alleged', 'criminal_proceeding', 'genetic_data',
] as const;
type MalaysiaSensitiveCategory = typeof SENSITIVE_CATEGORIES[number];

interface SensitiveConsentRecord {
  id: string;
  dataSubjectId: string;
  categories: MalaysiaSensitiveCategory[];
  purpose: string;
  consentText: string;
  grantedAt: string;
  revokedAt: string | null;
}

export async function grantSensitiveConsent(
  env: Env,
  dataSubjectId: string,
  categories: MalaysiaSensitiveCategory[],
  purpose: string,
  consentText: string,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO malaysia_sensitive_consent
     (id, data_subject_id, categories, purpose, consent_text,
      granted_at, revoked_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'), NULL)`,
  ).bind(
    id, dataSubjectId,
    JSON.stringify(categories),
    purpose, consentText,
  ).run();

  return id;
}

export async function withdrawSensitiveConsent(
  env: Env,
  consentId: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE malaysia_sensitive_consent
     SET revoked_at = datetime('now')
     WHERE id = ? AND revoked_at IS NULL`,
  ).bind(consentId).run();
}

export async function hasActiveSensitiveConsent(
  env: Env,
  dataSubjectId: string,
  category: MalaysiaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM malaysia_sensitive_consent
     WHERE data_subject_id = ?
       AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(dataSubjectId, category).first();

  return row !== null;
}
```

---

## 3. Data Correction Request — 21-Day Window

PDPA s.34–36: a data subject may request correction; the controller must respond within **21 days**.

```typescript
// workers/malaysia-pdpa-correction.ts
interface CorrectionRequest {
  id: string;
  dataSubjectId: string;
  fieldName: string;
  currentValue: string;
  proposedValue: string;
  requestedAt: string;
  deadlineAt: string;     // 21 days from receipt
  status: 'pending' | 'applied' | 'refused';
  refusalReason: string | null;
  resolvedAt: string | null;
}

export async function submitCorrectionRequest(
  env: Env,
  dataSubjectId: string,
  fieldName: string,
  currentValue: string,
  proposedValue: string,
): Promise<CorrectionRequest> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now);
  deadline.setDate(deadline.getDate() + 21);

  const req: CorrectionRequest = {
    id, dataSubjectId, fieldName, currentValue, proposedValue,
    requestedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    status: 'pending',
    refusalReason: null,
    resolvedAt: null,
  };

  await env.DB.prepare(
    `INSERT INTO malaysia_correction_requests
     (id, data_subject_id, field_name, current_value, proposed_value,
      requested_at, deadline_at, status, refusal_reason, resolved_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL)`,
  ).bind(
    id, dataSubjectId, fieldName, currentValue, proposedValue,
    req.requestedAt, req.deadlineAt,
  ).run();

  return req;
}

// Cron check — alert when correction deadlines are within 48 h
export async function checkCorrectionDeadlines(env: Env): Promise<void> {
  const warnAt = new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString();

  const { results } = await env.DB.prepare(
    `SELECT id, data_subject_id, field_name, deadline_at
     FROM malaysia_correction_requests
     WHERE status = 'pending' AND deadline_at <= ?`,
  ).bind(warnAt).all<Pick<CorrectionRequest, 'id' | 'dataSubjectId' | 'fieldName' | 'deadlineAt'>>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'malaysia_correction_deadline_warning', ...r });
  }
}
```

---

## 4. Cross-Border Transfer Whitelist Guard (s.129)

Transfers are prohibited to countries NOT on the Ministerial whitelist unless a derogation applies.

```typescript
// workers/malaysia-pdpa-transfer.ts
// Whitelist per Personal Data Protection (Place of Transfer) Order 2017
// Maintain this in D1 and update when the Order is amended
const MALAYSIA_WHITELIST = new Set([
  'AU', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR',
  'GB', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL',
  'PL', 'PT', 'RO', 'SE', 'SI', 'SK', 'AT', 'AR', 'CA', 'CH', 'IL',
  'IS', 'JP', 'LI', 'NO', 'NZ', 'UY',
  // Check the latest Ministerial order for the authoritative list
]);

type TransferDerogation =
  | 'ministerial_whitelist' | 'explicit_consent'
  | 'contractual_necessity' | 'vital_interests' | 'legal_proceedings';

interface TransferAttempt {
  id: string;
  dataSubjectId: string;
  destinationCountry: string;
  approved: boolean;
  derogation: TransferDerogation | null;
  attemptedAt: string;
}

export async function checkMalaysiaTransfer(
  env: Env,
  dataSubjectId: string,
  destinationCountry: string,
  hasExplicitConsent: boolean,
  isContractualNecessity: boolean,
): Promise<{ approved: boolean; derogation: TransferDerogation | null }> {
  let approved = false;
  let derogation: TransferDerogation | null = null;

  if (MALAYSIA_WHITELIST.has(destinationCountry)) {
    approved = true;
    derogation = 'ministerial_whitelist';
  } else if (hasExplicitConsent) {
    approved = true;
    derogation = 'explicit_consent';
  } else if (isContractualNecessity) {
    approved = true;
    derogation = 'contractual_necessity';
  }

  await env.DB.prepare(
    `INSERT INTO malaysia_transfer_log
     (id, data_subject_id, destination_country, approved, derogation, attempted_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  ).bind(
    crypto.randomUUID(), dataSubjectId, destinationCountry,
    approved ? 1 : 0, derogation,
  ).run();

  return { approved, derogation };
}
```

---

## 5. Breach Notification (PDPA Amendment Act 2024)

The 2024 amendments introduce mandatory breach notification to JPDP and affected data subjects. Implementation mirrors GDPR's 72-hour window.

```typescript
// workers/malaysia-pdpa-breach.ts
interface MalaysiaBreachRecord {
  incidentId: string;
  discoveredAt: string;
  jpdpDeadlineAt: string;    // 72 h per Amendment Act 2024
  affectedCount: number;
  dataCategories: string[];
  involvesSensitiveData: boolean;
  jpdpNotifiedAt: string | null;
  subjectsNotifiedAt: string | null;
  internalReference: string;
}

export async function registerBreach(
  env: Env,
  affectedCount: number,
  dataCategories: string[],
  internalReference: string,
): Promise<MalaysiaBreachRecord> {
  const SENSITIVE = [
    'health_medical','political_opinion','religious_belief',
    'offence_alleged','criminal_proceeding','genetic_data',
  ];

  const now = new Date();
  const jpdpDeadline = new Date(now.getTime() + 72 * 60 * 60 * 1000);
  const involvesSensitiveData = dataCategories.some(c => SENSITIVE.includes(c));

  const record: MalaysiaBreachRecord = {
    incidentId: crypto.randomUUID(),
    discoveredAt: now.toISOString(),
    jpdpDeadlineAt: jpdpDeadline.toISOString(),
    affectedCount,
    dataCategories,
    involvesSensitiveData,
    jpdpNotifiedAt: null,
    subjectsNotifiedAt: null,
    internalReference,
  };

  await env.DB.prepare(
    `INSERT INTO malaysia_breach_log
     (incident_id, discovered_at, jpdp_deadline_at, affected_count,
      data_categories, involves_sensitive_data,
      jpdp_notified_at, subjects_notified_at, internal_reference)
     VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)`,
  ).bind(
    record.incidentId, record.discoveredAt, record.jpdpDeadlineAt,
    record.affectedCount, JSON.stringify(record.dataCategories),
    record.involvesSensitiveData ? 1 : 0, record.internalReference,
  ).run();

  return record;
}
```

---

## Anti-patterns

- **Assuming PDPA applies to non-commercial processing.** The Act explicitly covers data processing "in connection with a commercial transaction" — B2C and B2B apply; purely internal HR data has a separate exemption.
- **Omitting Bahasa Malaysia notice.** s.7 requires the notice to be in BM or English; an English-only notice for a Malay-speaking audience may be challenged.
- **Not maintaining the transfer whitelist in D1.** Hardcoding it in source means you'll miss Ministerial Order amendments; keep it as a table with an `effective_date` column.
- **Treating 21-day correction window as non-binding.** JPDP can prosecute failure to act on correction requests.

---

## Gotchas

- PDPA 2010 does **not** apply to the federal or state government, credit reporting agencies (governed by Credit Reporting Agencies Act 2010), or personal processing of personal data.
- The sectoral registration requirement (Order 2013) covers: communications, banking/finance, insurance, health, tourism, transport, education, direct sales, services, real estate, utilities. Check whether your sector falls in scope.
- The PDPA Amendment Act 2024 had not fully come into force across all provisions as of mid-2026 — confirm the commencement dates of each provision with Malaysian legal counsel.
- Cloudflare's **Singapore (SIN)** PoP is the nearest to Malaysia; there is no Kuala Lumpur PoP. The PDPA has no data-residency mandate — data may be processed outside Malaysia subject to the transfer rules.
- A "personal data processor" (who processes on behalf of a controller) in Malaysia is bound only by contract, not directly by PDPA; the controller remains liable to JPDP.

---

## Verification

```bash
# 1. Pending correction requests past 21-day deadline
wrangler d1 execute DB --command \
  "SELECT id, field_name, deadline_at FROM malaysia_correction_requests
   WHERE status = 'pending' AND deadline_at < datetime('now');"

# 2. Transfers to non-whitelisted countries without derogation
wrangler d1 execute DB --command \
  "SELECT * FROM malaysia_transfer_log WHERE approved = 0;"

# 3. Breach notifications not sent within 72 h
wrangler d1 execute DB --command \
  "SELECT incident_id, discovered_at, jpdp_deadline_at FROM malaysia_breach_log
   WHERE jpdp_notified_at IS NULL AND jpdp_deadline_at < datetime('now');"

# 4. Active sensitive consents by category
wrangler d1 execute DB --command \
  "SELECT data_subject_id, categories FROM malaysia_sensitive_consent
   WHERE revoked_at IS NULL;"
```

---

## Related

- `singapore-pdpa-workers-d1.md`
- `indonesia-pdp-law-workers-d1.md`
- `philippines-dpa-workers-d1.md`
- `cross-border-data-transfer-mechanisms.md`
- `data-retention-automated-deletion-workers.md`

---

## Sources

- Personal Data Protection Act 2010 (Act 709): https://www.pdp.gov.my/jpdpv2/assets/2019/01/Personal-Data-Protection-Act-2010.pdf
- Personal Data Protection (Place of Transfer) Order 2017: https://www.pdp.gov.my/
- Personal Data Protection (Registration of Data Processors) Order 2013: https://www.pdp.gov.my/
- PDPA Amendment Act 2024: https://www.pdp.gov.my/
- Cloudflare D1: https://developers.cloudflare.com/d1/
