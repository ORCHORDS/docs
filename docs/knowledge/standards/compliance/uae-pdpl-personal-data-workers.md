# UAE PDPL Personal Data Protection — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service processes personal data of individuals located in the United Arab Emirates, or you are an entity established in the UAE — including free-zone entities that have opted in. Federal Decree-Law No. 45 of 2021 on the Protection of Personal Data (UAE PDPL), supplemented by Cabinet Decision No. 33 of 2024 (implementing regulations), applies with enforcement by the UAE Data Office (UAEDO). Fines reach AED 5 million for standard violations and AED 20 million for gross violations. Key obligations include a legal basis for processing, data subject rights fulfilment, cross-border transfer controls, breach notification within 72 hours, and mandatory data processing records.

---

## Context

The UAE PDPL draws from GDPR concepts but differs in scope, exemptions, and enforcement:

- **Legal basis** (Art. 8): consent, contractual necessity, legal obligation, vital interests, public interest, or legitimate interests — broadly analogous to GDPR Art. 6.
- **Sensitive data** (Art. 1): health/medical data, genetic data, biometric data, credit and financial data, criminal conviction data, data related to children — requires **explicit consent** or a legal obligation/vital-interest basis.
- **Data subject rights** (Arts. 14–19): access, correction, deletion, restriction of processing, data portability, objection to processing including direct marketing.
- **Cross-border transfers** (Art. 22): transfers to third countries are permitted if the destination provides "adequate protection" as listed by the UAEDO, or by appropriate safeguards (contractual clauses approved by the UAEDO, binding corporate rules, or explicit consent).
- **Breach notification** (Art. 15 of Cabinet Decision 33/2024): notify the UAEDO within **72 hours** of becoming aware of a breach; notify affected data subjects without undue delay when the breach is likely to result in high risk.
- **Data Processing Records** (Art. 10): controllers must maintain records of processing activities; processors must maintain records on behalf of the controller.
- **DPO**: appointment is recommended for large-scale or sensitive-data processing; not yet mandatory under the current implementing regulations.
- **Enforcement**: the UAEDO (not courts) issues fines and remediation orders.

---

## 1. Consent Gate and Legal Basis Logging

All processing must be grounded in a valid legal basis; consent must be freely given, specific, informed, and unambiguous.

```typescript
// workers/uae-pdpl-consent.ts
import { Env } from './types';

type UaePdplBasis =
  | 'consent' | 'contract' | 'legal_obligation'
  | 'vital_interests' | 'public_interest' | 'legitimate_interests';

interface UaePdplConsentRecord {
  id: string;
  dataSubjectId: string;
  purpose: string;
  basis: UaePdplBasis;
  consentText: string | null;  // required when basis === 'consent'
  grantedAt: string;
  revokedAt: string | null;
  ipAddress: string;
  language: string;            // consent must be presented in a language understood by the data subject
}

export async function recordUaePdplLegalBasis(
  env: Env,
  dataSubjectId: string,
  purpose: string,
  basis: UaePdplBasis,
  consentText: string | null,
  request: Request,
): Promise<string> {
  if (basis === 'consent' && !consentText) {
    throw new Error('UAE PDPL: consent text is required when basis is consent');
  }

  const id = crypto.randomUUID();
  const lang = request.headers.get('Accept-Language')?.split(',')[0] ?? 'en';

  await env.DB.prepare(
    `INSERT INTO uae_pdpl_legal_basis
     (id, data_subject_id, purpose, basis, consent_text,
      granted_at, revoked_at, ip_address, language)
     VALUES (?, ?, ?, ?, ?, datetime('now'), NULL, ?, ?)`,
  ).bind(
    id, dataSubjectId, purpose, basis, consentText,
    request.headers.get('CF-Connecting-IP') ?? 'unknown', lang,
  ).run();

  return id;
}

export async function revokeUaePdplConsent(
  env: Env,
  dataSubjectId: string,
  purpose: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE uae_pdpl_legal_basis
     SET revoked_at = datetime('now')
     WHERE data_subject_id = ? AND purpose = ?
       AND basis = 'consent' AND revoked_at IS NULL`,
  ).bind(dataSubjectId, purpose).run();
}

export async function hasValidUaePdplBasis(
  env: Env,
  dataSubjectId: string,
  purpose: string,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT basis FROM uae_pdpl_legal_basis
     WHERE data_subject_id = ? AND purpose = ? AND revoked_at IS NULL
     LIMIT 1`,
  ).bind(dataSubjectId, purpose).first<{ basis: UaePdplBasis }>();

  if (!row) return false;
  // Non-consent bases remain valid until circumstances change
  if (row.basis !== 'consent') return true;
  return true; // consent was granted and not revoked
}
```

---

## 2. Cross-Border Transfer Controls

UAE PDPL requires either adequacy recognition, UAEDO-approved contractual clauses, or explicit consent before transferring personal data outside the UAE.

```typescript
// workers/uae-pdpl-cross-border.ts
// UAE Data Office adequacy list (illustrative; check current UAEDO publications)
const UAE_ADEQUATE_COUNTRIES = new Set([
  'AE', // within UAE — always permitted
  // UAEDO publishes its own adequacy list; populate from official source
]);

type UaeTransferMechanism =
  | 'adequacy' | 'contractual_clauses' | 'bcr' | 'explicit_consent' | 'vital_interests';

interface UaeCrossBorderRecord {
  id: string;
  dataSubjectId: string;
  destinationCountry: string;
  destinationEntity: string;
  mechanism: UaeTransferMechanism;
  contractReference: string | null;
  consentRecordId: string | null;
  transferredAt: string;
  dataCategories: string[];
}

export function isUaeAdequateDestination(countryCode: string): boolean {
  return UAE_ADEQUATE_COUNTRIES.has(countryCode.toUpperCase());
}

export async function recordUaeCrossBorderTransfer(
  env: Env,
  record: Omit<UaeCrossBorderRecord, 'id'>,
): Promise<string> {
  if (!isUaeAdequateDestination(record.destinationCountry) &&
      record.mechanism === 'adequacy') {
    throw new Error(
      `UAE PDPL: ${record.destinationCountry} is not on the UAEDO adequacy list`,
    );
  }

  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO uae_pdpl_cross_border_transfers
     (id, data_subject_id, destination_country, destination_entity,
      mechanism, contract_reference, consent_record_id,
      transferred_at, data_categories)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id, record.dataSubjectId, record.destinationCountry,
    record.destinationEntity, record.mechanism,
    record.contractReference, record.consentRecordId,
    record.transferredAt, JSON.stringify(record.dataCategories),
  ).run();

  return id;
}

// Edge guard: block transfers without a logged mechanism
export async function checkUaeTransferAllowed(
  env: Env,
  dataSubjectId: string,
  destinationCountry: string,
): Promise<boolean> {
  if (isUaeAdequateDestination(destinationCountry)) return true;

  const row = await env.DB.prepare(
    `SELECT 1 FROM uae_pdpl_cross_border_transfers
     WHERE data_subject_id = ? AND destination_country = ?
     LIMIT 1`,
  ).bind(dataSubjectId, destinationCountry).first();

  return row !== null;
}
```

---

## 3. Data Subject Rights — 30-Day Response Clock

UAE PDPL requires controllers to respond to data subject rights requests within 30 calendar days.

```typescript
// workers/uae-pdpl-dsr.ts
type UaePdplRight =
  | 'access' | 'correction' | 'deletion' | 'restriction'
  | 'portability' | 'objection' | 'objection_direct_marketing';

interface UaePdplDsrTicket {
  id: string;
  dataSubjectId: string;
  right: UaePdplRight;
  receivedAt: string;
  deadlineAt: string;  // 30 calendar days
  status: 'open' | 'completed' | 'denied' | 'extended';
  denialReason: string | null;
  extendedDeadlineAt: string | null;
}

export async function openUaePdplRequest(
  env: Env,
  dataSubjectId: string,
  right: UaePdplRight,
): Promise<UaePdplDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  // UAE PDPL: 30-day response period (shorter than GDPR's 30-day standard)
  const deadline = new Date(now.getTime() + 30 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO uae_pdpl_dsr
     (id, data_subject_id, right, received_at, deadline_at, status)
     VALUES (?, ?, ?, ?, ?, 'open')`,
  ).bind(id, dataSubjectId, right, now.toISOString(), deadline.toISOString()).run();

  return { id, dataSubjectId, right, receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(), status: 'open',
    denialReason: null, extendedDeadlineAt: null };
}

export async function alertUaePdplDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 3 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, data_subject_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS due
     FROM uae_pdpl_dsr
     WHERE status IN ('open','extended') AND due <= ?`,
  ).bind(horizon).all<{ id: string; data_subject_id: string; right: string; due: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'uae_pdpl_deadline_warning', ...r });
  }
}
```

---

## 4. Breach Notification — 72-Hour Clock

Breaches must be reported to the UAEDO within 72 hours of the controller becoming aware.

```typescript
// workers/uae-pdpl-breach.ts
type UaeBreachSeverity = 'low' | 'medium' | 'high' | 'critical';

interface UaePdplBreachRecord {
  id: string;
  discoveredAt: string;
  uaedoDeadlineAt: string;      // discoveredAt + 72 hours
  subjectNotificationRequiredBy: string | null; // when high risk to subjects
  nature: string;
  dataCategories: string[];
  approximateSubjectCount: number;
  severity: UaeBreachSeverity;
  uaedoNotifiedAt: string | null;
  subjectsNotifiedAt: string | null;
  containmentMeasures: string;
  status: 'open' | 'uaedo_notified' | 'subjects_notified' | 'closed';
}

export async function openUaePdplBreach(
  env: Env,
  breach: Omit<UaePdplBreachRecord, 'id' | 'uaedoDeadlineAt'>,
): Promise<string> {
  const id = crypto.randomUUID();
  const deadline72h = new Date(
    new Date(breach.discoveredAt).getTime() + 72 * 3_600_000,
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO uae_pdpl_breaches
     (id, discovered_at, uaedo_deadline_at, subject_notification_required_by,
      nature, data_categories, approximate_subject_count, severity,
      uaedo_notified_at, subjects_notified_at, containment_measures, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 'open')`,
  ).bind(
    id, breach.discoveredAt, deadline72h,
    breach.subjectNotificationRequiredBy,
    breach.nature, JSON.stringify(breach.dataCategories),
    breach.approximateSubjectCount, breach.severity,
    breach.containmentMeasures,
  ).run();

  // Immediately alert the compliance team
  await env.ALERTS_QUEUE.send({
    type: 'uae_pdpl_breach_72h_deadline',
    breachId: id,
    uaedoDeadline: deadline72h,
    severity: breach.severity,
  });

  return id;
}

export async function markUaedoNotified(
  env: Env,
  breachId: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE uae_pdpl_breaches
     SET uaedo_notified_at = datetime('now'), status = 'uaedo_notified'
     WHERE id = ?`,
  ).bind(breachId).run();
}
```

---

## 5. Data Processing Records (Record of Processing Activities)

Controllers must maintain processing records that the UAEDO can request during an investigation.

```typescript
// workers/uae-pdpl-ropa.ts
interface UaePdplRopaEntry {
  id: string;
  processingActivity: string;
  purpose: string;
  legalBasis: string;
  dataCategories: string[];
  dataSubjectCategories: string[];
  recipientCategories: string[];
  retentionPeriod: string;       // ISO-8601 duration
  crossBorderTransfers: string[];
  securityMeasures: string;
  createdAt: string;
  updatedAt: string;
}

export async function upsertRopaEntry(
  env: Env,
  entry: Omit<UaePdplRopaEntry, 'id' | 'createdAt' | 'updatedAt'>,
): Promise<string> {
  const existing = await env.DB.prepare(
    `SELECT id FROM uae_pdpl_ropa WHERE processing_activity = ? LIMIT 1`,
  ).bind(entry.processingActivity).first<{ id: string }>();

  if (existing) {
    await env.DB.prepare(
      `UPDATE uae_pdpl_ropa
       SET purpose = ?, legal_basis = ?, data_categories = ?,
           recipient_categories = ?, retention_period = ?,
           cross_border_transfers = ?, security_measures = ?,
           updated_at = datetime('now')
       WHERE id = ?`,
    ).bind(
      entry.purpose, entry.legalBasis,
      JSON.stringify(entry.dataCategories),
      JSON.stringify(entry.recipientCategories),
      entry.retentionPeriod,
      JSON.stringify(entry.crossBorderTransfers),
      entry.securityMeasures, existing.id,
    ).run();
    return existing.id;
  }

  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO uae_pdpl_ropa
     (id, processing_activity, purpose, legal_basis, data_categories,
      data_subject_categories, recipient_categories, retention_period,
      cross_border_transfers, security_measures, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))`,
  ).bind(
    id, entry.processingActivity, entry.purpose, entry.legalBasis,
    JSON.stringify(entry.dataCategories),
    JSON.stringify(entry.dataSubjectCategories),
    JSON.stringify(entry.recipientCategories),
    entry.retentionPeriod,
    JSON.stringify(entry.crossBorderTransfers),
    entry.securityMeasures,
  ).run();

  return id;
}
```

---

## Anti-patterns

- **Applying GDPR adequacy country lists as a proxy.** The UAEDO publishes its own adequacy list; EU-adequate countries are not automatically UAE-adequate and vice versa.
- **Using a 45-day DSR window.** UAE PDPL requires a 30-day response (shorter than GDPR's 30-day standard for simple requests and 90 days for complex); multi-state tooling defaults may overshoot.
- **Skipping breach notification for breaches below "high risk".** UAE PDPL requires UAEDO notification for all qualifying breaches within 72 hours — not just high-risk ones. High-risk breaches additionally require data subject notification.
- **Assuming free-zone entities are always exempt.** DIFC and ADGM have their own data protection laws (DIFC DPL 2020, ADGM DPP 2021) that operate in parallel; entities processing data of persons outside the free zone may face dual obligations.

---

## Gotchas

- DIFC (Dubai International Financial Centre) and ADGM (Abu Dhabi Global Market) operate their own regulatory frameworks; the Federal UAE PDPL does not apply within those zones to their registered entities, but may apply to cross-border processing.
- Credit and financial data is classified as sensitive data under UAE PDPL — unlike most peer laws — meaning fintech and banking platforms face opt-in consent requirements for financial analytics.
- The UAEDO is empowered to prescribe standard contractual clauses for cross-border transfers; verify the current approved form before executing transfer agreements.
- Arabic-language privacy notices may be required or expected by the UAEDO for consumer-facing services targeting UAE residents.
- The implementing Cabinet Decision 33/2024 refined and partially updated the decree-law obligations; always reference the most recent UAEDO-published guidance.

---

## Verification

```bash
# 1. Processing activities without valid legal basis records
wrangler d1 execute DB --command \
  "SELECT purpose, COUNT(*) AS total FROM uae_pdpl_legal_basis
   WHERE revoked_at IS NULL GROUP BY purpose ORDER BY total DESC;"

# 2. Cross-border transfers by mechanism
wrangler d1 execute DB --command \
  "SELECT destination_country, mechanism, COUNT(*) AS total
   FROM uae_pdpl_cross_border_transfers
   GROUP BY destination_country, mechanism;"

# 3. Open DSR tickets near 30-day deadline
wrangler d1 execute DB --command \
  "SELECT id, right, deadline_at FROM uae_pdpl_dsr
   WHERE status IN ('open','extended')
   AND deadline_at <= datetime('now', '+3 days');"

# 4. Breach notification compliance check
wrangler d1 execute DB --command \
  "SELECT id, discovered_at, uaedo_deadline_at, uaedo_notified_at, severity
   FROM uae_pdpl_breaches
   WHERE uaedo_notified_at IS NULL ORDER BY discovered_at DESC;"

# 5. ROPA entry count and last update
wrangler d1 execute DB --command \
  "SELECT processing_activity, updated_at FROM uae_pdpl_ropa
   ORDER BY updated_at DESC LIMIT 20;"
```

---

## Related

- `cross-border-data-transfer-mechanisms.md`
- `gdpr-international-transfers-schrems2.md`
- `gdpr-breach-notification-72h.md`
- `gdpr-article-30-ropa-automation.md`
- `saudi-arabia-pdpl-workers-implementation.md`

---

## Sources

- UAE Federal Decree-Law No. 45 of 2021 on Personal Data Protection: https://uaecabinet.ae/en/details/news/uae-cabinet-approves-federal-decree-law-on-personal-data-protection
- Cabinet Decision No. 33 of 2024 (Implementing Regulations): https://www.uaedataoffice.ae/en/legislation
- UAE Data Office (UAEDO) official site: https://www.uaedataoffice.ae/
- IAPP UAE PDPL Overview: https://iapp.org/resources/article/uae-pdpl/
- Cloudflare Workers D1 docs: https://developers.cloudflare.com/d1/
