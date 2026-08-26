# Mauritius Data Protection Act 2017 — Workers & D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project application processes personal data of Mauritius residents or is operated by a Mauritius-registered entity. The Data Protection Act 2017 (DPA 2017, Act No. 20 of 2017), which replaced the 2004 act and mirrors GDPR closely, obliges controllers and processors to register with the Data Protection Office (DPO-MU), obtain consent, honour data-subject rights, and report breaches within 72 hours. A compliance audit identifies gaps in the Cloudflare Workers / D1 implementation.

## Context

The DPA 2017 applies to any controller established in Mauritius or processing data of persons in Mauritius where the processing is related to offering goods/services or monitoring behaviour. Key obligations:

- **Registration** — controllers and processors must register with the Data Protection Office (Mauritius) before processing begins.
- **Lawful basis** — consent, contract, legal obligation, vital interests, public task, or legitimate interests (GDPR-aligned Article 6 equivalents).
- **Sensitive data** — health, racial/ethnic origin, political opinions, religious beliefs, trade-union membership, genetic/biometric data, sex life/sexual orientation; requires explicit consent unless a statutory exemption applies.
- **Data subject rights** — access, rectification, erasure, restriction, objection, portability (automated decisions), automated-decision-making safeguards.
- **Breach notification** — controller must notify the Data Protection Commissioner (now Director, DPO-MU) within 72 hours; notify data subjects "without undue delay" when high risk.
- **Cross-border transfers** — allowed to countries with adequate protection (EU, UK post-adequacy) or via safeguards (SCCs, BCRs, explicit consent).
- **DPO appointment** — mandatory for large-scale processing of special-category data or systematic monitoring; voluntary otherwise.
- Mauritius received EU GDPR adequacy status in 2021 (mutual adequacy).
- Penalties: up to MUR 3 million (≈ USD 65,000) per offence; criminal sanctions possible.

## 1. Registration Status Flag in KV

Record registration acknowledgement and renewal date so Workers can enforce a kill-switch if registration lapses.

```typescript
// workers/mu-dpa-registration.ts
export interface Env {
  KV: KVNamespace;
  DB: D1Database;
}

interface RegistrationStatus {
  registered:    boolean;
  reg_number:    string;
  expiry_date:   string;   // ISO date
  dpo_appointed: boolean;
}

export async function getMURegistrationStatus(env: Env): Promise<RegistrationStatus | null> {
  const raw = await env.KV.get('mu_dpa_registration', 'json');
  return raw as RegistrationStatus | null;
}

export async function assertMURegistration(env: Env): Promise<void> {
  const status = await getMURegistrationStatus(env);
  if (!status?.registered) {
    throw new Error('MU DPA 2017: controller registration with DPO-MU is required before processing');
  }
  const expiry = new Date(status.expiry_date);
  if (expiry < new Date()) {
    throw new Error(`MU DPA 2017: registration expired on ${status.expiry_date} — renew with DPO-MU`);
  }
}
```

Store via wrangler:
```bash
wrangler kv key put mu_dpa_registration \
  '{"registered":true,"reg_number":"DPO-2025-1234","expiry_date":"2026-12-31","dpo_appointed":true}' \
  --binding KV --env production
```

## 2. Consent Management (DPA 2017 Section 24)

DPA 2017 consent must be freely given, specific, informed, and unambiguous; withdrawable at any time.

```typescript
// workers/mu-dpa-consent.ts
interface ConsentRecord {
  user_id:      string;
  purpose:      string;
  lawful_basis: 'consent' | 'contract' | 'legal_obligation' | 'vital_interests' | 'public_task' | 'legitimate_interests';
  sensitive:    boolean;
  granted:      boolean;
  version:      string;   // privacy-notice version at time of consent
  captured_at:  string;
  withdrawn_at: string | null;
}

export async function recordConsent(
  env: Env,
  record: Omit<ConsentRecord, 'captured_at' | 'withdrawn_at'>
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO mu_dpa_consent
       (user_id, purpose, lawful_basis, sensitive, granted, version, captured_at, withdrawn_at)
     VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,NULL)
     ON CONFLICT(user_id, purpose) DO UPDATE
     SET lawful_basis=excluded.lawful_basis, granted=excluded.granted,
         version=excluded.version, captured_at=CURRENT_TIMESTAMP, withdrawn_at=NULL`
  ).bind(
    record.user_id, record.purpose, record.lawful_basis,
    record.sensitive ? 1 : 0, record.granted ? 1 : 0, record.version
  ).run();
}

export async function withdrawConsent(env: Env, userId: string, purpose: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE mu_dpa_consent
     SET granted = 0, withdrawn_at = CURRENT_TIMESTAMP
     WHERE user_id = ? AND purpose = ?`
  ).bind(userId, purpose).run();
}

export async function hasValidConsent(env: Env, userId: string, purpose: string): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT granted FROM mu_dpa_consent
     WHERE user_id = ? AND purpose = ? AND withdrawn_at IS NULL`
  ).bind(userId, purpose).first<{ granted: number }>();
  return row?.granted === 1;
}
```

```sql
CREATE TABLE IF NOT EXISTS mu_dpa_consent (
  user_id      TEXT NOT NULL,
  purpose      TEXT NOT NULL,
  lawful_basis TEXT NOT NULL,
  sensitive    INTEGER NOT NULL DEFAULT 0,
  granted      INTEGER NOT NULL DEFAULT 0,
  version      TEXT NOT NULL,
  captured_at  TEXT NOT NULL,
  withdrawn_at TEXT,
  PRIMARY KEY (user_id, purpose)
);
```

## 3. Data Subject Rights (72-Hour Breach + 30-Day DSR Deadline)

DPA 2017 requires DSR responses within 28 days (extendable to 56 with notice — similar to GDPR's 30-day baseline).

```typescript
// workers/mu-dpa-dsr.ts
type MURight = 'access' | 'rectification' | 'erasure' | 'restriction' | 'objection' | 'portability';

export async function handleMURight(
  env: Env,
  requestId: string,
  userId: string,
  right: MURight,
  payload?: Record<string, unknown>
): Promise<Record<string, unknown>> {
  await env.DB.prepare(
    `INSERT OR IGNORE INTO mu_dpa_dsr_log
       (request_id, user_id, right_type, received_at, deadline, status)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP,
             datetime(CURRENT_TIMESTAMP, '+28 days'), 'pending')`
  ).bind(requestId, userId, right).run();

  let result: Record<string, unknown> = {};

  if (right === 'access' || right === 'portability') {
    const rows = await env.DB.prepare('SELECT * FROM user_data WHERE user_id = ?')
      .bind(userId).all();
    result = { records: rows.results };
  } else if (right === 'erasure') {
    await env.DB.batch([
      env.DB.prepare('DELETE FROM user_data WHERE user_id = ?').bind(userId),
      env.DB.prepare('DELETE FROM mu_dpa_consent WHERE user_id = ?').bind(userId),
    ]);
    result = { erased: true };
  } else if (right === 'rectification' && payload) {
    const sets = Object.keys(payload).map(k => `${k} = ?`).join(', ');
    await env.DB.prepare(`UPDATE user_data SET ${sets} WHERE user_id = ?`)
      .bind(...Object.values(payload), userId).run();
    result = { rectified: true };
  }

  await env.DB.prepare(
    `UPDATE mu_dpa_dsr_log SET status='completed', completed_at=CURRENT_TIMESTAMP
     WHERE request_id = ?`
  ).bind(requestId).run();

  return result;
}
```

## 4. Breach Notification Pipeline (72-Hour Clock)

```typescript
// workers/mu-dpa-breach.ts
interface BreachEvent {
  breach_id:      string;
  description:    string;
  categories:     string[];   // types of data affected
  approx_subjects: number;
  discovered_at:  string;
  risk_level:     'high' | 'medium' | 'low';
}

export async function logBreach(env: Env, breach: BreachEvent): Promise<void> {
  const notifyDPODeadline = new Date(
    new Date(breach.discovered_at).getTime() + 72 * 60 * 60 * 1000
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO mu_dpa_breach_log
       (breach_id, description, categories, approx_subjects,
        discovered_at, risk_level, notify_dpo_by, notified_at)
     VALUES (?,?,?,?,?,?,?,NULL)`
  ).bind(
    breach.breach_id, breach.description,
    JSON.stringify(breach.categories), breach.approx_subjects,
    breach.discovered_at, breach.risk_level, notifyDPODeadline
  ).run();

  // Trigger alert if < 6 h remain on 72-h clock
  const remaining = new Date(notifyDPODeadline).getTime() - Date.now();
  if (remaining < 6 * 60 * 60 * 1000) {
    console.error(`MU DPA 2017 BREACH ALERT: notify DPO-MU by ${notifyDPODeadline}`);
  }
}
```

## 5. Cross-Border Transfer Gate

Mauritius controllers may transfer to EU/UK/EEA (mutual adequacy). Other destinations require SCCs or explicit consent.

```typescript
// workers/mu-dpa-transfers.ts
const MU_ADEQUATE_DESTINATIONS = new Set([
  'EU', 'EEA', 'UK', 'CH', 'CA', 'NZ', 'JP', 'KR', 'AR', 'UY', 'IL'
]);

export function assertTransferLawful(destination: string, mechanism?: string): void {
  if (MU_ADEQUATE_DESTINATIONS.has(destination)) return;
  if (mechanism && ['SCC', 'BCR', 'explicit_consent', 'vital_interests'].includes(mechanism)) return;
  throw new Error(
    `MU DPA 2017: cross-border transfer to '${destination}' requires adequacy, SCCs, BCRs, or explicit consent`
  );
}
```

## Anti-patterns

- **Starting processing before registration** — the DPA 2017 imposes a pre-processing registration obligation; there is no grace period.
- **Relying solely on GDPR SCCs** — Mauritius has its own model clauses issued by DPO-MU; while EU SCCs are accepted as equivalent safeguards, confirm with DPO-MU guidance.
- **Treating Mauritius as GDPR-compliant by default** — while the laws are closely aligned, the local authority (DPO-MU) enforces the domestic Act and has its own forms and deadlines.
- **Logging sensitive-data processing without explicit consent** — health, biometric, and racial-origin data require explicit consent (Section 29); legitimate interests do not override this.

## Gotchas

- **DPO-MU registration must be renewed annually** (or on material change to processing); set a KV-based reminder 60 days before expiry.
- **Breach notification goes to the Data Protection Commissioner within 72 hours**; if the Commissioner cannot be reached electronically, a hard-copy submission is required.
- The **28-day DSR response window** is shorter than GDPR's 30-day window; configure deadline calculations accordingly.
- Mauritius's **adequacy with the EU** (Decision of 19 January 2021) means EU SCCs may not be needed for MU → EU flows, but controllers must still document the transfer basis.

## Verification

```bash
# Registration status
wrangler kv key get mu_dpa_registration --binding KV --env production

# Overdue DSRs (> 28 days)
wrangler d1 execute PROD_DB --command \
  "SELECT request_id, right_type, received_at, deadline
   FROM mu_dpa_dsr_log
   WHERE status = 'pending' AND julianday('now') > julianday(deadline)"

# Open breach notifications
wrangler d1 execute PROD_DB --command \
  "SELECT breach_id, risk_level, discovered_at, notify_dpo_by, notified_at
   FROM mu_dpa_breach_log WHERE notified_at IS NULL"
```

## Related

- `gdpr-breach-notification-72h.md`
- `gdpr-data-subject-rights-api.md`
- `cross-border-data-transfer-mechanisms.md`
- `gdpr-dpa-standard-contractual-clauses.md`
- `data-retention-automated-deletion-workers.md`

## Sources

- Data Protection Act 2017 (Act No. 20 of 2017), Republic of Mauritius
- Data Protection Office (Mauritius) — https://dataprotection.govmu.org
- EU Adequacy Decision for Mauritius, Commission Decision of 19 January 2021, OJ L 17/1
- IAPP Country Guide: Mauritius — https://iapp.org
