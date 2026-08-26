# Kenya Data Protection Act — Cloudflare Workers D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service processes personal data of Kenyan residents or operates from Kenya. The Kenya Data Protection Act 2019 (DPA 2019) and its subsidiary regulations — the Data Protection (General) Regulations 2021, the Data Protection (Complaints Handling Procedure and Enforcement) Regulations 2021, and the Data Protection (Registration of Data Controllers and Processors) Regulations 2021 — impose consent, breach-notification, data-subject-rights, and registration obligations on your Cloudflare Workers stack.

---

## Context

Kenya's Office of the Data Protection Commissioner (ODPC) was established under DPA 2019 and became fully operational in 2021. Key obligations:

- **Lawful basis** (s.30): consent, contract, legal obligation, vital interests, public interest, or legitimate interests — consent must be explicit for sensitive data.
- **Sensitive data** (s.2): includes health, race/ethnicity, political opinion, religion, trade-union membership, biometric, genetic, and sex-life data.
- **Data-subject rights** (s.26–34): access, rectification, deletion, restriction, objection, data portability, and a right not to be subject to solely automated decisions.
- **Breach notification** (s.43): notify ODPC within **72 hours** of becoming aware of a breach; notify affected persons without undue delay.
- **Cross-border transfers** (s.49): allowed to countries with adequate protection, using appropriate safeguards (SCCs, binding corporate rules), or with consent.
- **Registration** (Reg. 2021): all data controllers and processors processing personal data of Kenyan residents must register with ODPC; renewal is annual.
- **Sanctions**: fines up to KES 5 million or 1 % of annual global turnover, whichever is higher; criminal liability for directors.

---

## 1. Consent Collection and Storage

```typescript
// workers/kenya-dpa-consent.ts
import { Env } from './types';

type LawfulBasis =
  | 'consent' | 'contract' | 'legal_obligation'
  | 'vital_interests' | 'public_interest' | 'legitimate_interests';

type SensitiveCategory =
  | 'health' | 'race_ethnicity' | 'political_opinion'
  | 'religion' | 'trade_union' | 'biometric' | 'genetic' | 'sex_life';

interface ConsentRecord {
  id: string;
  dataSubjectId: string;
  purpose: string;
  lawfulBasis: LawfulBasis;
  sensitiveCategories: SensitiveCategory[];
  consentText: string;
  grantedAt: string;
  revokedAt: string | null;
  ipAddress: string;
}

export async function recordConsent(
  env: Env,
  dataSubjectId: string,
  purpose: string,
  sensitiveCategories: SensitiveCategory[],
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO kenya_consent
     (id, data_subject_id, purpose, lawful_basis, sensitive_categories,
      consent_text, granted_at, revoked_at, ip_address)
     VALUES (?, ?, ?, 'consent', ?, ?, datetime('now'), NULL, ?)`,
  ).bind(
    id, dataSubjectId, purpose,
    JSON.stringify(sensitiveCategories),
    consentText,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return id;
}

export async function revokeConsent(env: Env, consentId: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE kenya_consent SET revoked_at = datetime('now') WHERE id = ? AND revoked_at IS NULL`,
  ).bind(consentId).run();
}
```

---

## 2. Data Subject Rights (s.26–34) — 30-Day Response Clock

The DPA 2019 requires the controller to respond to data subject requests within **30 days** (extendable by a further 30 days with notice).

```typescript
// workers/kenya-dsr.ts
type DSRType =
  | 'access' | 'rectification' | 'erasure'
  | 'restriction' | 'objection' | 'portability' | 'no_automated_decision';

interface DSRTicket {
  id: string;
  dataSubjectId: string;
  requestType: DSRType;
  receivedAt: string;
  deadlineAt: string;       // 30 days
  extendedDeadlineAt: string | null;
  status: 'open' | 'extended' | 'completed' | 'denied';
  denialReason: string | null;
}

export async function openDSR(
  env: Env,
  dataSubjectId: string,
  requestType: DSRType,
): Promise<DSRTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now);
  deadline.setDate(deadline.getDate() + 30);

  const ticket: DSRTicket = {
    id, dataSubjectId, requestType,
    receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    extendedDeadlineAt: null,
    status: 'open',
    denialReason: null,
  };

  await env.DB.prepare(
    `INSERT INTO kenya_dsr
     (id, data_subject_id, request_type, received_at, deadline_at,
      extended_deadline_at, status, denial_reason)
     VALUES (?, ?, ?, ?, ?, NULL, 'open', NULL)`,
  ).bind(id, dataSubjectId, requestType, ticket.receivedAt, ticket.deadlineAt).run();

  return ticket;
}

export async function extendDSR(env: Env, ticketId: string): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT deadline_at FROM kenya_dsr WHERE id = ?`,
  ).bind(ticketId).first<{ deadline_at: string }>();

  if (!row) throw new Error('DSR ticket not found');

  const extended = new Date(row.deadline_at);
  extended.setDate(extended.getDate() + 30);

  await env.DB.prepare(
    `UPDATE kenya_dsr
     SET status = 'extended', extended_deadline_at = ?
     WHERE id = ?`,
  ).bind(extended.toISOString(), ticketId).run();
}

// Cron trigger: check for approaching deadlines every 12 hours
export async function alertDSRDeadlines(env: Env): Promise<void> {
  const warnBefore = new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString();

  const { results } = await env.DB.prepare(
    `SELECT id, data_subject_id, request_type, deadline_at, extended_deadline_at, status
     FROM kenya_dsr
     WHERE status IN ('open','extended')
       AND COALESCE(extended_deadline_at, deadline_at) <= ?`,
  ).bind(warnBefore).all<DSRTicket>();

  for (const ticket of results) {
    await env.ALERTS_QUEUE.send({ type: 'kenya_dsr_deadline_warning', ticket });
  }
}
```

---

## 3. Breach Notification — 72-Hour ODPC Clock

```typescript
// workers/kenya-breach-notification.ts
interface BreachRecord {
  incidentId: string;
  discoveredAt: string;
  odpcDeadlineAt: string;   // discovered + 72 h
  affectedCount: number;
  sensitiveDataInvolved: boolean;
  dataCategories: string[];
  riskAssessment: 'low' | 'medium' | 'high';
  odpcNotifiedAt: string | null;
  subjectsNotifiedAt: string | null;
  containmentSteps: string[];
}

export async function registerBreach(
  env: Env,
  affectedCount: number,
  dataCategories: string[],
  riskAssessment: BreachRecord['riskAssessment'],
  containmentSteps: string[],
): Promise<BreachRecord> {
  const now = new Date();
  const deadline = new Date(now.getTime() + 72 * 60 * 60 * 1000);
  const sensitiveDataInvolved = dataCategories.some(c =>
    ['health','race_ethnicity','biometric','genetic'].includes(c),
  );

  const record: BreachRecord = {
    incidentId: crypto.randomUUID(),
    discoveredAt: now.toISOString(),
    odpcDeadlineAt: deadline.toISOString(),
    affectedCount,
    sensitiveDataInvolved,
    dataCategories,
    riskAssessment,
    odpcNotifiedAt: null,
    subjectsNotifiedAt: null,
    containmentSteps,
  };

  await env.DB.prepare(
    `INSERT INTO kenya_breach_log
     (incident_id, discovered_at, odpc_deadline_at, affected_count,
      sensitive_data_involved, data_categories, risk_assessment,
      odpc_notified_at, subjects_notified_at, containment_steps)
     VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)`,
  ).bind(
    record.incidentId, record.discoveredAt, record.odpcDeadlineAt,
    record.affectedCount, record.sensitiveDataInvolved ? 1 : 0,
    JSON.stringify(record.dataCategories), record.riskAssessment,
    JSON.stringify(record.containmentSteps),
  ).run();

  return record;
}
```

---

## 4. Cross-Border Transfer Controls (s.49)

```typescript
// workers/kenya-transfer-guard.ts
// Countries ODPC has recognised as providing adequate protection (illustrative — check ODPC site)
const ADEQUATE_DESTINATIONS = new Set(['EU', 'UK', 'CA', 'UY', 'IL']);

type TransferMechanism =
  | 'adequate_country' | 'standard_contractual_clauses'
  | 'binding_corporate_rules' | 'explicit_consent' | 'vital_interests';

interface TransferRecord {
  id: string;
  dataSubjectId: string;
  destinationCountry: string;
  mechanism: TransferMechanism;
  dataCategories: string[];
  transferredAt: string;
  approved: boolean;
}

export async function requestTransfer(
  env: Env,
  dataSubjectId: string,
  destinationCountry: string,
  dataCategories: string[],
  explicitConsent: boolean,
  contractualSafeguards: boolean,
): Promise<{ approved: boolean; mechanism: TransferMechanism }> {
  let approved = false;
  let mechanism: TransferMechanism = 'standard_contractual_clauses';

  if (ADEQUATE_DESTINATIONS.has(destinationCountry)) {
    approved = true;
    mechanism = 'adequate_country';
  } else if (contractualSafeguards) {
    approved = true;
    mechanism = 'standard_contractual_clauses';
  } else if (explicitConsent) {
    approved = true;
    mechanism = 'explicit_consent';
  }

  await env.DB.prepare(
    `INSERT INTO kenya_transfer_log
     (id, data_subject_id, destination_country, mechanism,
      data_categories, transferred_at, approved)
     VALUES (?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    crypto.randomUUID(), dataSubjectId, destinationCountry,
    mechanism, JSON.stringify(dataCategories), approved ? 1 : 0,
  ).run();

  return { approved, mechanism };
}
```

---

## 5. ODPC Registration Reminder

Annual ODPC registration must be renewed. A Cron Trigger fires 60 days before expiry.

```typescript
// workers/kenya-odpc-registration.ts
interface RegistrationRecord {
  registrationNumber: string;
  entityName: string;
  registeredAt: string;
  expiresAt: string;       // one year from registration
  reminderSent60d: boolean;
  reminderSent14d: boolean;
}

export async function checkRegistrationExpiry(env: Env): Promise<void> {
  const in60Days = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString();
  const in14Days = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString();

  const { results: soon60 } = await env.DB.prepare(
    `SELECT registration_number, entity_name, expires_at
     FROM kenya_odpc_registration
     WHERE expires_at <= ? AND reminder_sent_60d = 0`,
  ).bind(in60Days).all<{ registration_number: string; entity_name: string; expires_at: string }>();

  for (const row of soon60) {
    await env.ALERTS_QUEUE.send({ type: 'kenya_odpc_renewal_60d', ...row });
    await env.DB.prepare(
      `UPDATE kenya_odpc_registration SET reminder_sent_60d = 1 WHERE registration_number = ?`,
    ).bind(row.registration_number).run();
  }

  const { results: soon14 } = await env.DB.prepare(
    `SELECT registration_number, entity_name, expires_at
     FROM kenya_odpc_registration
     WHERE expires_at <= ? AND reminder_sent_14d = 0`,
  ).bind(in14Days).all<{ registration_number: string; entity_name: string; expires_at: string }>();

  for (const row of soon14) {
    await env.ALERTS_QUEUE.send({ type: 'kenya_odpc_renewal_14d', ...row });
    await env.DB.prepare(
      `UPDATE kenya_odpc_registration SET reminder_sent_14d = 1 WHERE registration_number = ?`,
    ).bind(row.registration_number).run();
  }
}
```

---

## Anti-patterns

- **Treating Kenya like a lesser-known jurisdiction.** ODPC has issued enforcement decisions and fines; non-compliance is not "low risk".
- **Relying on legitimate interests for sensitive data.** s.30(3) requires explicit consent for sensitive categories — legitimate interests is not available.
- **Missing the registration requirement.** Both controllers AND processors must register if they process data of Kenyan residents.
- **Conflating "breach notification" with "breach to subjects only".** s.43 requires notifying ODPC first within 72 h; subjects come second but "without undue delay".

---

## Gotchas

- The 30-day DSR window runs from **receipt** of the request, not from identity verification; initiate verification immediately on receipt.
- The DPA 2019 covers **processing** (including storage, retrieval, transfer) not just collection — a Worker that merely reads and transforms Kenyan personal data is a processor.
- "Adequate protection" countries are listed by ODPC; the list is not identical to the EU's list. Check the ODPC website regularly.
- Cloudflare's Johannesburg (JNB) PoP is the nearest to Nairobi. The ODPC has not mandated data residency within Kenya as of mid-2026, but the draft regulations under review may change this.
- Criminal liability (up to KES 3 million and 10 years imprisonment) applies to **natural persons** who are directors or officers of the offending entity.

---

## Verification

```bash
# 1. Open DSR requests past 30-day deadline
wrangler d1 execute DB --command \
  "SELECT id, request_type, deadline_at FROM kenya_dsr
   WHERE status IN ('open') AND deadline_at < datetime('now');"

# 2. Breaches where ODPC not notified within 72 h
wrangler d1 execute DB --command \
  "SELECT incident_id, discovered_at, odpc_deadline_at FROM kenya_breach_log
   WHERE odpc_notified_at IS NULL AND odpc_deadline_at < datetime('now');"

# 3. Transfers with no approved mechanism
wrangler d1 execute DB --command \
  "SELECT * FROM kenya_transfer_log WHERE approved = 0;"

# 4. ODPC registration expiry check
wrangler d1 execute DB --command \
  "SELECT registration_number, entity_name, expires_at FROM kenya_odpc_registration
   WHERE expires_at < datetime('now', '+90 days');"
```

---

## Related

- `cross-border-data-transfer-mechanisms.md`
- `gdpr-breach-notification-72h.md`
- `gdpr-data-subject-rights-api.md`
- `south-africa-popia-workers-d1.md`
- `data-retention-automated-deletion-workers.md`

---

## Sources

- Kenya Data Protection Act 2019: https://www.odpc.go.ke/dpa/
- Data Protection (General) Regulations 2021: https://www.odpc.go.ke/regulations/
- Data Protection (Registration) Regulations 2021: https://www.odpc.go.ke/registration/
- ODPC Enforcement Decisions: https://www.odpc.go.ke/enforcement/
- Cloudflare D1 Documentation: https://developers.cloudflare.com/d1/
