# Pakistan Personal Data Protection Bill (PDPB) — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of individuals in Pakistan and may be subject to Pakistan's Personal Data Protection Bill (PDPB), most recently passed by the National Assembly in 2023 and pending final Senate enactment and Presidential assent (distinct from PECA 2016, which covers cybercrime, not personal-data rights). Even ahead of formal commencement, implementing PDPB-aligned controls is prudent: the PDPB establishes a National Commission for Personal Data Protection (NCPDP), requires lawful bases for processing, introduces sensitive-data and cross-border transfer controls, and grants data subjects rights to access, correct, delete, and object to processing.

---

## Context

Pakistan's PDPB is modelled on GDPR principles adapted for Pakistan's legal and regulatory environment. Key characteristics:

- **Enforcement body**: National Commission for Personal Data Protection (NCPDP); fines up to PKR 25 million (approx. USD 90,000) for general violations and PKR 100 million for sensitive-data violations.
- **Lawful bases**: consent, contract, legal obligation, vital interests, public task, and legitimate interests — substantially mirroring GDPR Article 6.
- **Sensitive personal data**: racial/ethnic origin, religion, political opinions, trade union membership, health/medical data, biometric data, genetic data, sexual orientation, criminal convictions — requires explicit consent as the lawful basis.
- **Cross-border transfers**: permitted only to countries deemed adequate by the NCPDP, or via approved safeguards (contractual clauses, binding corporate rules, or explicit consent).
- **Data localisation**: the PDPB may require certain categories of personal data to be stored on servers located in Pakistan; the NCPDP is empowered to issue category-specific orders. Monitor NCPDP instruments closely.
- **Data subject rights**: access, correction, deletion, portability, and objection to processing.
- **Privacy notices**: must be provided at or before collection in clear, accessible language.
- **Data protection officers (DPOs)**: required for significant-scale or sensitive-data processors — appointment must be registered with the NCPDP.

> **Note**: As of 2026-08-23, the PDPB has not received Presidential assent. This article reflects the enacted text of the 2023 Bill. Monitor the NCPDP gazette for commencement notifications and subsidiary regulations before relying on specific thresholds.

---

## 1. Lawful-Basis Tracking per Processing Activity

The PDPB mirrors GDPR's requirement to record and rely on a lawful basis for each processing activity. The Worker stores the basis in D1 alongside the processing record.

```typescript
// workers/pdpb-lawful-basis.ts
import { Env } from './types';

type PdpbLawfulBasis =
  | 'consent'
  | 'contract'
  | 'legal_obligation'
  | 'vital_interests'
  | 'public_task'
  | 'legitimate_interests';

interface ProcessingRecord {
  processingId: string;
  consumerId: string;
  purpose: string;
  basis: PdpbLawfulBasis;
  basisDetail?: string; // e.g., legitimate interest balancing test reference
}

export async function recordPdpbProcessing(
  env: Env,
  record: ProcessingRecord,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO pdpb_processing_records
     (id, consumer_id, purpose, basis, basis_detail, recorded_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(
      record.processingId,
      record.consumerId,
      record.purpose,
      record.basis,
      record.basisDetail ?? null,
    )
    .run();
}

export async function assertPdpbLawfulBasis(
  env: Env,
  consumerId: string,
  purpose: string,
): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT basis FROM pdpb_processing_records
     WHERE consumer_id = ? AND purpose = ?
     ORDER BY recorded_at DESC LIMIT 1`,
  )
    .bind(consumerId, purpose)
    .first<{ basis: PdpbLawfulBasis }>();

  if (!row) {
    throw new Error(
      `PDPB: No lawful basis recorded for processing "${purpose}" of consumer ${consumerId}`,
    );
  }
}
```

---

## 2. Consent Management for General and Sensitive Data

Sensitive personal data under the PDPB requires explicit (opt-in) consent; general processing may rely on the broader consent definition. Both types are stored separately to support auditing.

```typescript
// workers/pdpb-consent-manager.ts
import { Env } from './types';

type PdpbSensitiveCategory =
  | 'racial_ethnic_origin'
  | 'religion_beliefs'
  | 'political_opinions'
  | 'trade_union_membership'
  | 'health_medical'
  | 'biometric'
  | 'genetic'
  | 'sexual_orientation'
  | 'criminal_convictions';

export async function recordPdpbConsent(
  env: Env,
  consumerId: string,
  purpose: string,
  isSensitive: false,
  consentTextHash: string,
): Promise<void>;
export async function recordPdpbConsent(
  env: Env,
  consumerId: string,
  purpose: string,
  isSensitive: true,
  consentTextHash: string,
  sensitiveCategory: PdpbSensitiveCategory,
): Promise<void>;
export async function recordPdpbConsent(
  env: Env,
  consumerId: string,
  purpose: string,
  isSensitive: boolean,
  consentTextHash: string,
  sensitiveCategory?: PdpbSensitiveCategory,
): Promise<void> {
  const expiresAt = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.prepare(
    `INSERT INTO pdpb_consents
     (id, consumer_id, purpose, is_sensitive, sensitive_category,
      consent_text_hash, granted_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  )
    .bind(
      crypto.randomUUID(),
      consumerId,
      purpose,
      isSensitive ? 1 : 0,
      sensitiveCategory ?? null,
      consentTextHash,
      expiresAt,
    )
    .run();
}

export async function hasPdpbConsent(
  env: Env,
  consumerId: string,
  purpose: string,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM pdpb_consents
     WHERE consumer_id = ? AND purpose = ?
       AND revoked_at IS NULL AND expires_at > datetime('now')
     LIMIT 1`,
  )
    .bind(consumerId, purpose)
    .first<{ 1: number }>();
  return row !== null;
}

export async function revokePdpbConsent(
  env: Env,
  consumerId: string,
  purpose: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE pdpb_consents
     SET revoked_at = datetime('now')
     WHERE consumer_id = ? AND purpose = ? AND revoked_at IS NULL`,
  )
    .bind(consumerId, purpose)
    .run();
}
```

---

## 3. Cross-Border Transfer Controls

The PDPB restricts transfers of personal data out of Pakistan unless the receiving country is deemed adequate or approved safeguards are in place. The Worker checks a D1 allowlist before forwarding personal data to external services.

```typescript
// workers/pdpb-transfer-guard.ts
import { Env } from './types';

type TransferSafeguard =
  | 'adequacy_decision'
  | 'standard_contractual_clauses'
  | 'binding_corporate_rules'
  | 'explicit_consent'
  | 'vital_interests';

interface TransferCountryRecord {
  countryCode: string;
  safeguard: TransferSafeguard;
  referenceDoc?: string;
  approvedAt: string;
  expiresAt?: string;
}

export async function isPdpbTransferApproved(
  env: Env,
  destinationCountryCode: string,
): Promise<{ approved: boolean; safeguard: TransferSafeguard | null }> {
  const row = await env.DB.prepare(
    `SELECT safeguard FROM pdpb_transfer_allowlist
     WHERE country_code = ?
       AND (expires_at IS NULL OR expires_at > datetime('now'))
     ORDER BY approved_at DESC LIMIT 1`,
  )
    .bind(destinationCountryCode.toUpperCase())
    .first<{ safeguard: TransferSafeguard }>();

  if (!row) return { approved: false, safeguard: null };
  return { approved: true, safeguard: row.safeguard };
}

export async function registerPdpbTransferSafeguard(
  env: Env,
  record: TransferCountryRecord,
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO pdpb_transfer_allowlist
     (country_code, safeguard, reference_doc, approved_at, expires_at)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(
      record.countryCode.toUpperCase(),
      record.safeguard,
      record.referenceDoc ?? null,
      record.approvedAt,
      record.expiresAt ?? null,
    )
    .run();
}

// Guard used in data-forwarding Workers
export async function pdpbTransferGuard(
  env: Env,
  destinationCountry: string,
  consumerId: string,
  purpose: string,
): Promise<void> {
  const { approved, safeguard } = await isPdpbTransferApproved(env, destinationCountry);
  if (!approved) {
    throw new Error(
      `PDPB: Transfer of personal data (consumer: ${consumerId}, purpose: ${purpose}) ` +
        `to ${destinationCountry} is not approved — no adequate country decision or safeguard on file`,
    );
  }
  // Log the transfer for audit
  await env.DB.prepare(
    `INSERT INTO pdpb_transfer_log
     (id, consumer_id, destination_country, safeguard, purpose, transferred_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(crypto.randomUUID(), consumerId, destinationCountry.toUpperCase(), safeguard, purpose)
    .run();
}
```

---

## 4. Data Subject Rights — Access and Deletion

```typescript
// workers/pdpb-subject-rights.ts
import { Env } from './types';

type PdpbRight = 'access' | 'correct' | 'delete' | 'port' | 'object';

export async function submitPdpbRightsRequest(
  env: Env,
  consumerId: string,
  right: PdpbRight,
  detail?: Record<string, unknown>,
): Promise<{ requestId: string }> {
  const requestId = crypto.randomUUID();
  // PDPB does not prescribe a specific day limit; 30 days is the GDPR-aligned default
  const deadline = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `INSERT INTO pdpb_rights_requests
     (id, consumer_id, right_type, detail_json, status, submitted_at, deadline_at)
     VALUES (?, ?, ?, ?, 'open', datetime('now'), ?)`,
  )
    .bind(requestId, consumerId, right, JSON.stringify(detail ?? {}), deadline)
    .run();

  await env.RIGHTS_QUEUE.send({ law: 'pdpb', requestId, consumerId, right });
  return { requestId };
}

export async function exportPdpbConsumerData(
  env: Env,
  consumerId: string,
): Promise<Record<string, unknown>> {
  const [profile, consents, processing, transfers] = await Promise.all([
    env.DB.prepare(
      `SELECT * FROM consumer_profiles WHERE consumer_id = ?`,
    ).bind(consumerId).first(),
    env.DB.prepare(
      `SELECT purpose, is_sensitive, granted_at, revoked_at FROM pdpb_consents WHERE consumer_id = ?`,
    ).bind(consumerId).all(),
    env.DB.prepare(
      `SELECT purpose, basis, recorded_at FROM pdpb_processing_records WHERE consumer_id = ?`,
    ).bind(consumerId).all(),
    env.DB.prepare(
      `SELECT destination_country, safeguard, purpose, transferred_at FROM pdpb_transfer_log WHERE consumer_id = ?`,
    ).bind(consumerId).all(),
  ]);

  return { profile, consents: consents.results, processing: processing.results, transfers: transfers.results };
}
```

---

## 5. Privacy Notice Version Control

The PDPB requires privacy notices to be provided at or before data collection. The Worker records which version of the notice each consumer acknowledged.

```typescript
// workers/pdpb-notice-versioning.ts
import { Env } from './types';

export async function recordPdpbNoticeAck(
  env: Env,
  consumerId: string,
  noticeVersion: string,
  channel: 'web' | 'mobile' | 'api',
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO pdpb_notice_acknowledgements
     (id, consumer_id, notice_version, channel, acknowledged_at)
     VALUES (?, ?, ?, ?, datetime('now'))`,
  )
    .bind(crypto.randomUUID(), consumerId, noticeVersion, channel)
    .run();
}

export async function currentNoticeVersion(env: Env): Promise<string> {
  const row = await env.DB.prepare(
    `SELECT version FROM pdpb_notice_versions
     WHERE published_at <= datetime('now')
     ORDER BY published_at DESC LIMIT 1`,
  ).first<{ version: string }>();
  if (!row) throw new Error('PDPB: No published privacy notice version found');
  return row.version;
}

export async function hasAcknowledgedCurrentNotice(
  env: Env,
  consumerId: string,
): Promise<boolean> {
  const current = await currentNoticeVersion(env);
  const row = await env.DB.prepare(
    `SELECT 1 FROM pdpb_notice_acknowledgements
     WHERE consumer_id = ? AND notice_version = ? LIMIT 1`,
  )
    .bind(consumerId, current)
    .first<{ 1: number }>();
  return row !== null;
}
```

---

## Anti-patterns

- **Treating PDPB as identical to PECA 2016**: Pakistan's PECA (Prevention of Electronic Crimes Act) governs cybercrime and content takedowns — the PDPB is a separate personal-data protection law. Conflating the two leads to missing data-subject rights obligations.
- **Proceeding without commencement monitoring**: the PDPB has not yet commenced as of 2026-08-23; relying on an assumed commencement date without monitoring the NCPDP gazette risks both early over-compliance cost and late-start penalties.
- **Ignoring data-localisation risk**: the NCPDP is empowered to issue sectoral data-localisation orders; cross-border transfer controls must be designed to accommodate a server-in-Pakistan requirement for specific data categories.
- **Using implicit consent for sensitive data**: the PDPB requires explicit, affirmative consent for each sensitive-data category — a bundled click-through consent is not sufficient.

---

## Gotchas

- **Bill vs. enacted law**: as of the knowledge cutoff date, the PDPB awaits Presidential assent. Verify current status via the National Assembly of Pakistan website before relying on specific penalty thresholds.
- **Urdu-language privacy notices**: the PDPB may require notices in Urdu (Pakistan's national language) in addition to English, particularly for consumer-facing platforms; design your notice template to support both languages.
- **Cloudflare data centres**: Cloudflare's edge may route Pakistani user traffic through data centres outside Pakistan. If the NCPDP issues a localisation order for the data you process, you may need Cloudflare Smart Placement or a dedicated regional bucket to satisfy it.
- **DPO registration**: if the PDPB's commencement triggers DPO obligations for your scale of processing, the DPO appointment must be registered with the NCPDP — failure to register is an independent violation.
- **example project in Pakistan**: anonymous social platforms attract content-moderation scrutiny under PECA alongside PDPB personal-data obligations. Ensure legal counsel reviews both regimes concurrently.

---

## Verification

```sql
-- Confirm lawful basis is recorded for each active processing purpose
SELECT purpose, COUNT(DISTINCT basis) AS basis_count
FROM pdpb_processing_records
GROUP BY purpose;

-- List cross-border transfers lacking an approved safeguard
SELECT t.destination_country, t.purpose, t.transferred_at
FROM pdpb_transfer_log t
LEFT JOIN pdpb_transfer_allowlist a
  ON a.country_code = t.destination_country
    AND (a.expires_at IS NULL OR a.expires_at > datetime('now'))
WHERE a.country_code IS NULL;

-- Verify consumers have acknowledged the current privacy notice
SELECT COUNT(*) AS missing_ack
FROM consumer_profiles cp
WHERE NOT EXISTS (
  SELECT 1 FROM pdpb_notice_acknowledgements na
  WHERE na.consumer_id = cp.consumer_id
    AND na.notice_version = (
      SELECT version FROM pdpb_notice_versions
      ORDER BY published_at DESC LIMIT 1
    )
);
```

---

## Related

- `pakistan-peca-content-moderation-workers.md` — Pakistan's cybercrime / content-moderation law (separate from PDPB)
- `gdpr-consent-management-cloudflare-workers.md` — GDPR-aligned consent patterns that PDPB resembles
- `cross-border-data-transfer-cloudflare-workers.md` — transfer mechanism implementation
- `gdpr-data-subject-rights-api.md` — subject-rights API patterns reusable for PDPB
- `data-localization-requirements.md` — localisation controls for jurisdictions with residency mandates

---

## Sources

- Pakistan Personal Data Protection Bill 2023 (National Assembly of Pakistan): <https://na.gov.pk/>
- Pakistan Ministry of IT and Telecom — Digital Policy: <https://moitt.gov.pk/>
- IAPP Global Privacy Law Tracker: <https://iapp.org/resources/article/global-privacy-law-tracker/>
- Future of Privacy Forum — Asia-Pacific Privacy Overview: <https://fpf.org/>
- Cloudflare Network Map (data centre locations): <https://www.cloudflare.com/network/>
