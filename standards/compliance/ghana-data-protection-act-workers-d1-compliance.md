# Ghana Data Protection Act 2012 (Act 843) Compliance on Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform serves Ghanaian users — fintech (Mobile Money, GhIPSS), healthtech, e-government, or e-commerce — and processes personal data of Ghanaian residents. The Ghana Data Protection Act 2012 (Act 843) requires data controller registration with the Data Protection Commission (DPC), lawful basis for all processing, security controls, and data subject rights. You need to map these obligations to your Cloudflare Workers + D1 architecture and implement a compliant pipeline.

---

## Context

Ghana's Data Protection Act 2012 (Act 843) was the first comprehensive data protection law in sub-Saharan Africa. It is enforced by the **Data Protection Commission (DPC)**.

Key requirements:

| Obligation | Detail |
|---|---|
| Registration | Every data controller must register with the DPC before processing |
| Lawful basis | Consent, contractual necessity, legal obligation, vital interests, legitimate interest, public interest |
| Sensitive data | Health, religion, political views, sexual life, criminal convictions — additional safeguards |
| Data subject rights | Access, correction, objection, deletion (limited) |
| Cross-border transfers | Permitted to countries with adequate protection or with DPC approval |
| Security | Appropriate technical and organisational measures |
| Breach notification | Act 843 does not specify a deadline, but DPC guidance recommends prompt notification |
| Retention | No longer than necessary |

Act 843 is less prescriptive than GDPR in some areas (e.g., no explicit 72-hour breach window in the statute) but the DPC has issued guidance tightening obligations. Ghana is actively updating its framework toward an EU-adequate standard.

---

## 1. Data Controller Registration Check

Every data controller must register before starting processing. Workers can enforce a startup gate that checks whether registration is active.

```typescript
// src/middleware/ghana-dpc-registration-gate.ts

interface DPCRegistration {
  registrationNumber: string;
  expiresAt: string;  // DPC registrations must be renewed
  dataController: string;
  categories: string[];
}

// Store registration metadata in a KV binding or D1
export async function assertDPCRegistrationValid(
  db: D1Database,
): Promise<DPCRegistration> {
  const reg = await db
    .prepare(
      `SELECT registration_number, expires_at, data_controller, categories
       FROM dpc_registration
       ORDER BY expires_at DESC
       LIMIT 1`,
    )
    .first<{
      registration_number: string;
      expires_at: string;
      data_controller: string;
      categories: string;
    }>();

  if (!reg) {
    throw new Error('No DPC registration on file; processing not permitted');
  }

  const expiresAt = new Date(reg.expires_at);
  if (expiresAt < new Date()) {
    throw new Error(
      `DPC registration ${reg.registration_number} expired at ${reg.expires_at}`,
    );
  }

  return {
    registrationNumber: reg.registration_number,
    expiresAt: reg.expires_at,
    dataController: reg.data_controller,
    categories: JSON.parse(reg.categories) as string[],
  };
}

export async function upsertDPCRegistration(
  db: D1Database,
  reg: DPCRegistration,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO dpc_registration
        (registration_number, expires_at, data_controller, categories)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(registration_number) DO UPDATE SET
         expires_at = excluded.expires_at`,
    )
    .bind(
      reg.registrationNumber,
      reg.expiresAt,
      reg.dataController,
      JSON.stringify(reg.categories),
    )
    .run();
}
```

---

## 2. Detecting Ghanaian Data Subjects

```typescript
// src/middleware/ghana-subject-detector.ts

export interface GhanaSignals {
  cfCountry: boolean;
  phonePrefix: boolean;
  ghanaCardNumber: boolean;  // GhanaCard national ID (GHA-XXXXXXXXX-X format)
}

export function detectGhanaSubject(request: Request): GhanaSignals {
  const country = request.cf?.country ?? '';
  const phone = request.headers.get('x-user-phone') ?? '';
  const ghanaCard = request.headers.get('x-user-ghana-card') ?? '';

  return {
    cfCountry: country === 'GH',
    phonePrefix: /^\+233/.test(phone),
    // GhanaCard: GHA- followed by 9 digits, dash, 1 check digit
    ghanaCardNumber: /^GHA-\d{9}-\d$/.test(ghanaCard),
  };
}

export function isGhanaSubject(signals: GhanaSignals): boolean {
  return signals.cfCountry || signals.phonePrefix || signals.ghanaCardNumber;
}
```

---

## 3. Lawful Basis and Consent Management

Act 843 Section 17 requires one of six lawful bases. Consent must be informed and withdrawable.

```typescript
// src/services/ghana-consent.ts

type GhanaLawfulBasis =
  | 'consent'
  | 'contractual_necessity'
  | 'legal_obligation'
  | 'vital_interests'
  | 'legitimate_interest'
  | 'public_interest';

type GhanaSensitiveCategory =
  | 'health'
  | 'religion'
  | 'political_views'
  | 'sexual_life'
  | 'criminal_convictions'
  | 'race_or_ethnic_origin';

interface GhanaConsentRecord {
  consentId: string;
  subjectId: string;
  legalBasis: GhanaLawfulBasis;
  purposes: string[];
  sensitiveCategories: GhanaSensitiveCategory[];
  grantedAt: string;
  withdrawnAt?: string;
  noticeLanguage: string;
  noticeVersion: string;
}

export async function recordGhanaConsent(
  db: D1Database,
  record: GhanaConsentRecord,
): Promise<void> {
  // Sensitive data requires explicit consent under Act 843 s.33
  if (record.sensitiveCategories.length > 0 && record.legalBasis !== 'consent') {
    throw new Error(
      'Sensitive categories under Ghana DPA require explicit consent as the legal basis',
    );
  }

  await db
    .prepare(
      `INSERT INTO ghana_consents
        (consent_id, subject_id, legal_basis, purposes, sensitive_categories,
         granted_at, notice_language, notice_version)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      record.consentId,
      record.subjectId,
      record.legalBasis,
      JSON.stringify(record.purposes),
      JSON.stringify(record.sensitiveCategories),
      record.grantedAt,
      record.noticeLanguage,
      record.noticeVersion,
    )
    .run();
}

export async function withdrawGhanaConsent(
  db: D1Database,
  consentId: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE ghana_consents
       SET withdrawn_at = datetime('now')
       WHERE consent_id = ?`,
    )
    .bind(consentId)
    .run();
}
```

---

## 4. Data Subject Rights Handling

Act 843 grants rights to access (Section 25), correction (Section 26), and objection. The Act does not specify a statutory response period; DPC guidance suggests 21 days.

```typescript
// src/handlers/ghana-dsr.ts

type GhanaDSRType = 'access' | 'correction' | 'objection' | 'deletion';

interface GhanaDSRRequest {
  requestId: string;
  type: GhanaDSRType;
  subjectId: string;
  details?: string;
  receivedAt: string;
}

export async function createGhanaDSR(
  db: D1Database,
  req: GhanaDSRRequest,
): Promise<{ deadline: string }> {
  // DPC recommended: 21 days
  const deadline = new Date(req.receivedAt);
  deadline.setDate(deadline.getDate() + 21);

  await db
    .prepare(
      `INSERT INTO ghana_dsr_log
        (request_id, type, subject_id, details, received_at, deadline, status)
       VALUES (?, ?, ?, ?, ?, ?, 'pending')`,
    )
    .bind(
      req.requestId,
      req.type,
      req.subjectId,
      req.details ?? null,
      req.receivedAt,
      deadline.toISOString(),
    )
    .run();

  return { deadline: deadline.toISOString() };
}

export async function fulfillAccessRequest(
  db: D1Database,
  subjectId: string,
): Promise<Record<string, unknown>> {
  const user = await db
    .prepare(
      `SELECT id, email, phone, created_at, updated_at
       FROM users WHERE id = ?`,
    )
    .bind(subjectId)
    .first<Record<string, unknown>>();

  const consents = await db
    .prepare(
      `SELECT consent_id, legal_basis, purposes, granted_at, withdrawn_at
       FROM ghana_consents WHERE subject_id = ?`,
    )
    .bind(subjectId)
    .all();

  return {
    personalData: user,
    consentHistory: consents.results,
    exportedAt: new Date().toISOString(),
  };
}
```

---

## 5. Cross-Border Transfer Controls

Act 843 Section 39: transfers permitted only to countries with substantially similar data protection laws, or with DPC authorisation.

```typescript
// src/services/ghana-cross-border.ts

// Countries Ghana DPC considers to have adequate protection (verify with DPC)
const ADEQUATE_COUNTRIES = new Set([
  'GB', 'DE', 'FR', 'AT', 'BE', 'NL', 'SE', 'NO', 'CH', 'AU', 'CA', 'NZ',
  'JP', 'SG', 'ZA',  // South Africa has POPIA
]);

type GhanaTransferMechanism =
  | 'adequate_country'
  | 'dpc_authorisation'
  | 'data_subject_consent'
  | 'contractual_necessity';

interface GhanaTransferLog {
  transferId: string;
  subjectId: string;
  destinationCountry: string;
  mechanism: GhanaTransferMechanism;
  dpcAuthReference?: string;
  consentId?: string;
  dataCategories: string[];
  transferredAt: string;
}

export async function validateAndLogGhanaTransfer(
  db: D1Database,
  entry: GhanaTransferLog,
): Promise<void> {
  if (
    entry.mechanism === 'adequate_country' &&
    !ADEQUATE_COUNTRIES.has(entry.destinationCountry)
  ) {
    throw new Error(
      `Ghana DPC: ${entry.destinationCountry} not recognised as adequate; use dpc_authorisation or consent`,
    );
  }

  if (entry.mechanism === 'dpc_authorisation' && !entry.dpcAuthReference) {
    throw new Error('DPC authorisation mechanism requires dpcAuthReference');
  }

  await db
    .prepare(
      `INSERT INTO ghana_transfer_log
        (transfer_id, subject_id, destination_country, mechanism,
         dpc_auth_reference, consent_id, data_categories, transferred_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      entry.transferId,
      entry.subjectId,
      entry.destinationCountry,
      entry.mechanism,
      entry.dpcAuthReference ?? null,
      entry.consentId ?? null,
      JSON.stringify(entry.dataCategories),
      entry.transferredAt,
    )
    .run();
}
```

---

## 6. Breach Notification and Security Logging

Act 843 does not prescribe a specific breach notification deadline, but DPC expects prompt reporting. Align with 72-hour best practice.

```typescript
// src/services/ghana-breach.ts

interface GhanaBreach {
  breachId: string;
  discoveredAt: string;
  subjectsAffected: number;
  dataCategories: string[];
  cause: string;
  remediation: string;
  notifySubjects: boolean;
}

export async function logGhanaBreach(
  db: D1Database,
  breach: GhanaBreach,
): Promise<void> {
  const targetNotification = new Date(breach.discoveredAt);
  targetNotification.setHours(targetNotification.getHours() + 72);

  await db
    .prepare(
      `INSERT INTO ghana_breach_log
        (breach_id, discovered_at, target_notification, subjects_affected,
         data_categories, cause, remediation, notify_subjects,
         dpc_notified_at, subjects_notified_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)`,
    )
    .bind(
      breach.breachId,
      breach.discoveredAt,
      targetNotification.toISOString(),
      breach.subjectsAffected,
      JSON.stringify(breach.dataCategories),
      breach.cause,
      breach.remediation,
      breach.notifySubjects ? 1 : 0,
    )
    .run();
}

export async function markDPCNotified(
  db: D1Database,
  breachId: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE ghana_breach_log
       SET dpc_notified_at = datetime('now')
       WHERE breach_id = ?`,
    )
    .bind(breachId)
    .run();
}
```

---

## Anti-patterns

- **Processing before DPC registration** — Act 843 requires registration before processing begins; operating without a valid registration certificate is an offence.
- **Treating Act 843 as identical to GDPR** — Act 843 predates GDPR and differs in structure; some GDPR controls (e.g., DPO mandate) are not statutory requirements under Act 843.
- **No data subject access mechanism** — Act 843 Section 25 creates an enforceable right; failing to provide a mechanism exposes the controller to DPC action.
- **Transferring to US without DPC authorisation** — the US is not on Ghana's adequate country list; use consent or DPC approval.
- **Ignoring Mobile Money PII** — fintech platforms using GhIPSS, MTN MoMo, AirtelTigo Money handle sensitive financial PD; treat this under Act 843's financial data provisions.

---

## Gotchas

- **Registration renewal**: DPC registrations must be renewed annually; set a calendar reminder 60 days before expiry.
- **GhanaCard storage**: GhanaCard numbers are national identifiers; treat with the same care as government-issued ID numbers.
- **SSNIT numbers**: Social Security and National Insurance Trust (SSNIT) numbers are sensitive identifiers common in employment data.
- **Act 843 amendments**: Ghana has been working on an updated data protection bill to align with GDPR; monitor for legislative updates.
- **DPC enforcement**: The DPC has become more active in enforcement since 2020; ensure registration is visibly maintained.

---

## Verification

```bash
# Check DPC registration is valid and not expired
wrangler d1 execute YOUR_DB --command \
  "SELECT registration_number, data_controller, expires_at
   FROM dpc_registration
   WHERE expires_at > datetime('now')
   ORDER BY expires_at ASC"

# Sensitive category consent audit
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM ghana_consents
   WHERE json_array_length(sensitive_categories) > 0
     AND withdrawn_at IS NULL"

# Breach log overdue notifications
wrangler d1 execute YOUR_DB --command \
  "SELECT breach_id, discovered_at, target_notification
   FROM ghana_breach_log
   WHERE dpc_notified_at IS NULL
     AND target_notification < datetime('now')"

# Cross-border transfer summary
wrangler d1 execute YOUR_DB --command \
  "SELECT mechanism, COUNT(*) FROM ghana_transfer_log GROUP BY mechanism"
```

---

## Related

- `nigeria-ndpr-workers-d1.md`
- `south-africa-popia-workers-d1.md`
- `kenya-data-protection-act-workers-d1.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-retention-automated-deletion-workers.md`

---

## Sources

- Ghana Data Protection Act 2012 (Act 843): [ghainalegalinformation.org](https://ghainalegalinformation.org)
- Data Protection Commission Ghana: [dpc.gov.gh](https://www.dpc.gov.gh)
- DPC Data Controller Registration Guidelines (2020)
- Ghana DPC Guidance on Cross-Border Data Transfers
- Cloudflare D1 data location: [developers.cloudflare.com/d1](https://developers.cloudflare.com/d1/reference/data-location/)
