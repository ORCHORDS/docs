# Dominican Republic Law 172-13: Personal Data Compliance in Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You process personal data of Dominican Republic residents and must comply with Law 172-13 on Protection of Personal Data, supervised by the National Office for Data Protection (ONAP) under the Attorney General's office, with penalties up to DOP 150,000 and criminal liability for aggravated violations.

## Context
Law 172-13 (enacted 13 January 2013) is the Dominican Republic's primary data protection statute covering any automated or structured manual database containing personal data of DR residents. The law establishes ARCO rights (access, rectification, cancellation, opposition), mandates registration of personal data databases with ONAP, prohibits international transfers to countries without adequate protection, and distinguishes sensitive data (health, racial origin, religious beliefs, criminal records, political opinions, sexual life) requiring explicit consent. Workers handle ARCO request routing; D1 stores consent records, the database registry ledger, and the deletion audit trail.

## Database Registration and Consent Capture

Law 172-13 Arts. 27-32 require data controllers to register each personal data database with ONAP. Record this obligation alongside consent to give auditors a single evidence table.

```typescript
// src/dr-compliance.ts
interface Env {
  DB: D1Database;
}

interface OnapRegistration {
  database_name: string;
  controller_name: string;
  controller_rnc: string; // Dominican tax ID
  purpose: string;
  categories: string[];
  retention_years: number;
  international_transfers: boolean;
  transfer_destinations: string[]; // ISO 3166-1 alpha-2 codes
  registered_at: string;
  onap_registration_number?: string;
}

export async function logOnapRegistration(
  env: Env,
  reg: OnapRegistration
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO dr_database_registry
      (database_name, controller_name, controller_rnc, purpose,
       categories_json, retention_years, international_transfers,
       transfer_destinations_json, registered_at, onap_reg_number)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    reg.database_name,
    reg.controller_name,
    reg.controller_rnc,
    reg.purpose,
    JSON.stringify(reg.categories),
    reg.retention_years,
    reg.international_transfers ? 1 : 0,
    JSON.stringify(reg.transfer_destinations),
    reg.registered_at,
    reg.onap_registration_number ?? null
  ).run();
}

export async function recordDrConsent(
  env: Env,
  userId: string,
  purpose: string,
  isSensitive: boolean,
  ipAddress: string
): Promise<void> {
  // Art. 9: sensitive data requires express, written consent
  if (isSensitive) {
    await env.DB.prepare(`
      INSERT INTO dr_consents
        (user_id, purpose, is_sensitive, consent_type,
         consented_at, ip_address)
      VALUES (?, ?, 1, 'express_written', ?, ?)
    `).bind(userId, purpose, new Date().toISOString(), ipAddress).run();
  } else {
    await env.DB.prepare(`
      INSERT INTO dr_consents
        (user_id, purpose, is_sensitive, consent_type,
         consented_at, ip_address)
      VALUES (?, ?, 0, 'informed', ?, ?)
    `).bind(userId, purpose, new Date().toISOString(), ipAddress).run();
  }
}
```

## ARCO Rights Request Handler

Law 172-13 Arts. 15-26 grant subjects the right to access (within 5 working days), rectify, cancel, or oppose processing. The controller must respond within the statutory window.

```typescript
// src/dr-arco.ts
type ArcoType = 'access' | 'rectification' | 'cancellation' | 'opposition';

interface ArcoRequest {
  type: ArcoType;
  subject_id: string;
  subject_email: string;
  detail?: string;
  received_at: string;
}

const DR_RESPONSE_DAYS: Record<ArcoType, number> = {
  access: 5,         // Art. 16 — 5 working days
  rectification: 5,  // Art. 18
  cancellation: 5,   // Art. 22
  opposition: 5,     // Art. 25
};

export async function createArcoRequest(
  env: Env,
  req: ArcoRequest
): Promise<{ request_id: number; deadline: string }> {
  const deadline = new Date(req.received_at);
  // Add calendar days as a conservative proxy; implement working-days logic for production
  deadline.setDate(deadline.getDate() + DR_RESPONSE_DAYS[req.type] + 2);

  const result = await env.DB.prepare(`
    INSERT INTO dr_arco_requests
      (type, subject_id, subject_email, detail, received_at, deadline, status)
    VALUES (?, ?, ?, ?, ?, ?, 'pending')
    RETURNING id
  `).bind(
    req.type,
    req.subject_id,
    req.subject_email,
    req.detail ?? null,
    req.received_at,
    deadline.toISOString()
  ).first<{ id: number }>();

  return { request_id: result!.id, deadline: deadline.toISOString() };
}

export async function handleCancellationRequest(
  env: Env,
  subjectId: string,
  requestId: number
): Promise<void> {
  // Anonymise rather than hard-delete to preserve referential integrity
  await env.DB.batch([
    env.DB.prepare(`
      UPDATE users
      SET email = 'deleted+' || id || '@redacted.invalid',
          name = 'REDACTED',
          phone = NULL,
          address = NULL,
          deleted_at = ?
      WHERE id = ?
    `).bind(new Date().toISOString(), subjectId),

    env.DB.prepare(`
      UPDATE dr_arco_requests
      SET status = 'completed', completed_at = ?
      WHERE id = ?
    `).bind(new Date().toISOString(), requestId),
  ]);
}
```

## International Transfer Adequacy Gate

Law 172-13 Art. 34 prohibits transferring personal data to countries that do not provide an adequate level of protection. Block transfers to non-adequate destinations at the Workers edge.

```typescript
// src/dr-transfer-gate.ts
// Countries ONAP has recognised as adequate (illustrative — verify with current ONAP guidance)
const DR_ADEQUATE_COUNTRIES = new Set([
  'AR', 'UY', 'MX', 'CL', 'DO', // Latin America adequacy decisions
  'AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI',
  'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT',
  'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK', // EU member states
]);

export function assertDrAdequacy(destinationIso2: string): void {
  if (!DR_ADEQUATE_COUNTRIES.has(destinationIso2.toUpperCase())) {
    throw new Error(
      `DR Law 172-13 Art. 34: transfer to ${destinationIso2} blocked — ` +
        'destination lacks adequate data protection. Obtain explicit consent or ' +
        'execute a data transfer agreement approved by ONAP.'
    );
  }
}

export async function logInternationalTransfer(
  env: Env,
  userId: string,
  destination: string,
  purpose: string,
  legalBasis: 'adequacy' | 'consent' | 'contract' | 'onap_authorisation'
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO dr_transfer_log
      (user_id, destination_country, purpose, legal_basis, transferred_at)
    VALUES (?, ?, ?, ?, ?)
  `).bind(userId, destination, purpose, legalBasis, new Date().toISOString()).run();
}
```

## Anti-patterns
- Processing sensitive data (health, religion, politics, sexual life) without express written consent — Art. 9
- Failing to register personal data databases with ONAP before processing begins — Arts. 27-32
- Responding to ARCO requests beyond the 5 working-day statutory limit — Arts. 16, 18, 22, 25
- Transferring data to a non-adequate country via a third-party API without an ONAP-approved mechanism
- Storing criminal-record data without the specific legal authorisation required by Art. 9(3)
- Ignoring opposition requests when the subject objects to direct marketing — Art. 25

## Gotchas
- Law 172-13 covers both automated databases and structured manual filing systems
- ONAP can order the blocking or cancellation of a database and impose fines up to DOP 150,000 per violation
- Criminal liability applies to aggravated violations involving sensitive data — Art. 72
- A data subject opposition to direct marketing must be honoured without requiring justification
- The law pre-dates GDPR; ARCO request deadlines are shorter (5 working days) than GDPR's 30-day window
- "Adequate protection" determination rests with ONAP, not the EU adequacy list — check ONAP guidance separately

## Verification

```sql
-- Databases registered with ONAP
SELECT database_name, onap_reg_number, registered_at
FROM dr_database_registry
ORDER BY registered_at DESC;

-- ARCO requests approaching or past deadline
SELECT id, type, subject_email, received_at, deadline, status
FROM dr_arco_requests
WHERE status = 'pending'
  AND deadline <= DATE('now', '+2 days')
ORDER BY deadline ASC;

-- Sensitive data consents (must all be 'express_written')
SELECT user_id, purpose, consent_type, consented_at
FROM dr_consents
WHERE is_sensitive = 1
  AND consent_type != 'express_written';

-- International transfers lacking legal basis
SELECT user_id, destination_country, transferred_at
FROM dr_transfer_log
WHERE legal_basis IS NULL OR legal_basis = '';
```

## Related
- `cross-border-data-transfer-mechanisms.md`
- `latin-america-data-protection-overview.md`
- `gdpr-data-subject-rights-api.md`
- `colombia-habeas-data-workers-d1-compliance.md`
- `costa-rica-prodhab-data-protection-workers-d1.md`
- `uruguay-law-18331-workers-d1.md`

## Sources
- https://www.oas.org/es/sla/ddi/docs/DR-Ley172-13ProteccionDatosPersonales.pdf
- https://onap.gob.do/
- https://www.procuraduria.gob.do/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
