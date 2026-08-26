# Peru LPDP Personal Data Compliance on Cloudflare Workers / D1
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Your service processes personal data of Peruvian residents. Peru's **Ley 29733 – Ley de
Protección de Datos Personales (LPDP, 2011)** and its Regulation (Decreto Supremo 003-2013-JUS,
2013) require database registration with **ANPD**, ARCO rights (Acceso, Rectificación,
Cancelación, Oposición), sensitive-data restrictions, international transfer controls, and security
measures. Implementing these controls on Cloudflare Workers + D1 keeps you audit-ready for ANPD
inspections.

## Context
ANPD (Autoridad Nacional de Protección de Datos Personales) sits within the Ministry of Justice
and Human Rights (MINJUSDH). Key obligations under LPDP and its Regulation:
- **Database Registration (Art. 43 Reg.)**: Personal data banks (bancos de datos) must be
  registered in the **Registro Nacional de Protección de Datos Personales** before any processing
  begins. Two types: public and private.
- **ARCO rights (Arts. 18–27 LPDP)**: Titular (data subject) may request Access, Rectification,
  Cancellation, or Opposition. Controller must respond within **20 calendar days**; Cancellation
  must be effected within a further **10 calendar days**.
- **Sensitive data (Art. 13 LPDP)**: biometric, genetic, health, criminal, religious, political,
  philosophical, sexual data — requires **explicit written consent**.
- **Consent (Art. 5 LPDP)**: must be prior, informed, voluntary, and express; for sensitive data
  also **written** (authenticated).
- **International transfers (Art. 15 LPDP)**: require either a guarantee of "equivalent" level of
  protection or explicit consent, and must be notified to ANPD.
- **Security (Art. 39 Reg.)**: technical, legal, and organisational measures; security incidents
  must be reported to ANPD promptly (no fixed hour-clock; "immediately upon awareness" per
  interpretive guidance).
- Fines from 0.5 to 100 UIT (Unidad Impositiva Tributaria; 1 UIT = PEN 5 150 in 2026;
  max ≈ PEN 515 000 / USD 135 000).

## Key Requirements — Database Registration and Consent

```typescript
// worker/peru-lpdp-registration.ts
type BankType = 'public' | 'private';

interface DataBank {
  registration_code?: string;   // assigned by ANPD after registration
  bank_name: string;
  bank_type: BankType;
  purpose: string;
  data_categories: string[];
  sensitive_categories: string[];
  titular_count_estimate: number;
  responsible_party: string;
  address: string;
  registered_at?: string;       // date registration submitted to ANPD
}

export async function upsertDataBank(db: D1Database, bank: DataBank): Promise<void> {
  await db
    .prepare(
      `INSERT INTO peru_data_bank_registry
         (bank_name, bank_type, purpose, data_categories_json,
          sensitive_categories_json, titular_count_estimate,
          responsible_party, address, registration_code, registered_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(bank_name) DO UPDATE SET
         bank_type                = excluded.bank_type,
         purpose                  = excluded.purpose,
         data_categories_json     = excluded.data_categories_json,
         sensitive_categories_json= excluded.sensitive_categories_json,
         titular_count_estimate   = excluded.titular_count_estimate,
         responsible_party        = excluded.responsible_party,
         address                  = excluded.address,
         registration_code        = excluded.registration_code,
         registered_at            = excluded.registered_at,
         updated_at               = CURRENT_TIMESTAMP`,
    )
    .bind(
      bank.bank_name, bank.bank_type, bank.purpose,
      JSON.stringify(bank.data_categories),
      JSON.stringify(bank.sensitive_categories),
      bank.titular_count_estimate,
      bank.responsible_party, bank.address,
      bank.registration_code ?? null,
      bank.registered_at ?? null,
    )
    .run();
}

// Consent record — Art. 5 LPDP; sensitive data requires written consent
export async function recordConsent(
  db: D1Database,
  titularId: string,
  bankName: string,
  purposes: string[],
  hasSensitiveData: boolean,
  method: 'express' | 'written',
): Promise<void> {
  if (hasSensitiveData && method !== 'written') {
    throw new Error('LPDP: sensitive personal data requires written (authenticated) consent');
  }

  await db
    .prepare(
      `INSERT INTO peru_consent_log
         (titular_id, bank_name, purposes_json, has_sensitive_data, method, consented_at)
       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(titular_id, bank_name) DO UPDATE SET
         purposes_json     = excluded.purposes_json,
         has_sensitive_data= excluded.has_sensitive_data,
         method            = excluded.method,
         consented_at      = CURRENT_TIMESTAMP`,
    )
    .bind(
      titularId, bankName,
      JSON.stringify(purposes),
      hasSensitiveData ? 1 : 0,
      method,
    )
    .run();
}
```

D1 schema:
```sql
CREATE TABLE IF NOT EXISTS peru_data_bank_registry (
  bank_name                 TEXT PRIMARY KEY,
  bank_type                 TEXT NOT NULL CHECK (bank_type IN ('public','private')),
  purpose                   TEXT NOT NULL,
  data_categories_json      TEXT NOT NULL,
  sensitive_categories_json TEXT NOT NULL DEFAULT '[]',
  titular_count_estimate    INTEGER NOT NULL DEFAULT 0,
  responsible_party         TEXT NOT NULL,
  address                   TEXT NOT NULL,
  registration_code         TEXT,
  registered_at             TEXT,
  updated_at                TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS peru_consent_log (
  titular_id        TEXT NOT NULL,
  bank_name         TEXT NOT NULL,
  purposes_json     TEXT NOT NULL,
  has_sensitive_data INTEGER NOT NULL DEFAULT 0,
  method            TEXT NOT NULL,
  consented_at      TEXT NOT NULL,
  PRIMARY KEY (titular_id, bank_name)
);
```

## ARCO Rights Handler (Arts. 18–27 LPDP)

```typescript
// worker/peru-lpdp-arco.ts
type ArcoType = 'acceso' | 'rectificacion' | 'cancelacion' | 'oposicion';

export async function handleArco(
  db: D1Database,
  titularId: string,
  type: ArcoType,
  bankName: string,
  detail?: Record<string, string>,
): Promise<Response> {
  // 20-calendar-day response deadline (Art. 24 LPDP)
  const responseDeadline   = new Date(Date.now() + 20 * 24 * 60 * 60 * 1000).toISOString();
  // Cancellation must be executed within 10 more days (Art. 25 LPDP)
  const executionDeadline  = type === 'cancelacion'
    ? new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString()
    : null;

  await db
    .prepare(
      `INSERT INTO peru_arco_requests
         (titular_id, bank_name, type, detail_json,
          requested_at, response_deadline, execution_deadline, completed_at)
       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, NULL)`,
    )
    .bind(
      titularId, bankName, type,
      JSON.stringify(detail ?? {}),
      responseDeadline, executionDeadline,
    )
    .run();

  if (type === 'acceso') {
    const rows = await db
      .prepare('SELECT * FROM personal_data WHERE titular_id = ?')
      .bind(titularId)
      .all();
    return Response.json({ type: 'acceso', data: rows.results, deadline: responseDeadline });
  }

  if (type === 'cancelacion') {
    // Block first; scheduled job deletes after all legal retention obligations lapse
    await db
      .prepare(
        `UPDATE personal_data
         SET blocked = 1, blocked_at = CURRENT_TIMESTAMP
         WHERE titular_id = ?`,
      )
      .bind(titularId)
      .run();
    return Response.json({
      type: 'cancelacion',
      status: 'blocked_pending_deletion',
      execution_deadline: executionDeadline,
    });
  }

  if (type === 'rectificacion' && detail) {
    for (const [field, value] of Object.entries(detail)) {
      await db
        .prepare(
          `UPDATE personal_data_fields
           SET value = ?, updated_at = CURRENT_TIMESTAMP
           WHERE titular_id = ? AND field = ?`,
        )
        .bind(value, titularId, field)
        .run();
    }
    return Response.json({ type: 'rectificacion', updated: Object.keys(detail) });
  }

  if (type === 'oposicion') {
    await db
      .prepare(
        `INSERT INTO peru_opposition_log (titular_id, bank_name, registered_at)
         VALUES (?, ?, CURRENT_TIMESTAMP)
         ON CONFLICT(titular_id, bank_name) DO UPDATE SET registered_at = CURRENT_TIMESTAMP`,
      )
      .bind(titularId, bankName)
      .run();
    return Response.json({ type: 'oposicion', status: 'registered' });
  }

  return Response.json({ error: 'invalid ARCO type' }, { status: 400 });
}
```

## International Transfers (Art. 15 LPDP — Notify ANPD)

```typescript
// worker/peru-lpdp-transfers.ts
export async function registerInternationalTransfer(
  db: D1Database,
  recipientCountry: string,
  bankName: string,
  safeguard: 'adequacy' | 'explicit_consent' | 'contract_guarantee',
  anpdNotificationRef?: string,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO peru_transfer_log
         (recipient_country, bank_name, safeguard,
          anpd_notification_ref, registered_at)
       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(
      recipientCountry, bankName, safeguard,
      anpdNotificationRef ?? null,
    )
    .run();
}
```

## Security Incident Log (Art. 39 Reg. — Report to ANPD Promptly)

```typescript
// worker/peru-lpdp-incident.ts
export async function recordIncident(
  db: D1Database,
  id: string,
  bankName: string,
  description: string,
  dataCategories: string[],
  affectedCount: number,
  isSensitive: boolean,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO peru_incident_log
         (id, bank_name, description, data_categories_json,
          affected_count, is_sensitive,
          discovered_at, notified_anpd_at)
       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)`,
    )
    .bind(
      id, bankName, description,
      JSON.stringify(dataCategories),
      affectedCount, isSensitive ? 1 : 0,
    )
    .run();

  if (isSensitive || affectedCount > 1000) {
    console.warn(`[LPDP] HIGH-PRIORITY incident ${id} — notify ANPD immediately`);
  }
}
```

D1 schema additions:
```sql
CREATE TABLE IF NOT EXISTS peru_arco_requests (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  titular_id        TEXT NOT NULL,
  bank_name         TEXT NOT NULL,
  type              TEXT NOT NULL,
  detail_json       TEXT NOT NULL DEFAULT '{}',
  requested_at      TEXT NOT NULL,
  response_deadline TEXT NOT NULL,
  execution_deadline TEXT,
  completed_at      TEXT
);
CREATE TABLE IF NOT EXISTS peru_opposition_log (
  titular_id    TEXT NOT NULL,
  bank_name     TEXT NOT NULL,
  registered_at TEXT NOT NULL,
  PRIMARY KEY (titular_id, bank_name)
);
CREATE TABLE IF NOT EXISTS peru_transfer_log (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient_country      TEXT NOT NULL,
  bank_name              TEXT NOT NULL,
  safeguard              TEXT NOT NULL,
  anpd_notification_ref  TEXT,
  registered_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS peru_incident_log (
  id                   TEXT PRIMARY KEY,
  bank_name            TEXT NOT NULL,
  description          TEXT NOT NULL,
  data_categories_json TEXT NOT NULL,
  affected_count       INTEGER NOT NULL DEFAULT 0,
  is_sensitive         INTEGER NOT NULL DEFAULT 0,
  discovered_at        TEXT NOT NULL,
  notified_anpd_at     TEXT
);
```

## Anti-patterns
- Operating a private data bank without registering it with ANPD — Art. 43 Reg. requires
  registration **prior** to any processing; processing unregistered banks is a major violation.
- Relying on implicit/clickwrap consent for sensitive (health, biometric, criminal) data —
  LPDP Art. 13 requires explicit written consent.
- Responding to Cancellation requests with immediate deletion and ignoring the two-step
  (block first, then delete after retention obligations lapse) requirement.
- Transferring data internationally without notifying ANPD — Art. 15 and Reg. Art. 66 require
  prior notification even when consent is obtained.
- Treating the ARCO deadline as 20 business days — LPDP uses **calendar days**.

## Gotchas
- Cloudflare Workers process data in edge PoPs globally; if Peruvian law is interpreted to require
  in-country storage for sensitive data, use Cloudflare's **Regional Services** or D1 in a
  geographically targeted configuration (note: LPDP itself does not have an explicit localisation
  mandate, but ANPD guidance may evolve).
- The registration entry in ANPD's registry must be **updated** whenever the bank's purpose,
  responsible party, or data categories change materially — it is not a one-time filing.
- The 1 UIT fine reference moves yearly (PEN 5 150 in 2026) — track the Supreme Decree that sets
  the UIT each year to know your fine exposure.
- ARCO requests arriving by email or physical letter still start the 20-day clock from receipt
  date; build a unified intake queue.

## Verification
```bash
# Data banks without registration codes (likely unregistered)
wrangler d1 execute <DB_NAME> \
  --command "SELECT bank_name, bank_type, registered_at FROM peru_data_bank_registry
             WHERE registration_code IS NULL;"

# Sensitive consent records using non-written method
wrangler d1 execute <DB_NAME> \
  --command "SELECT titular_id, bank_name, method FROM peru_consent_log
             WHERE has_sensitive_data = 1 AND method != 'written';"

# Overdue ARCO response deadlines
wrangler d1 execute <DB_NAME> \
  --command "SELECT titular_id, type, response_deadline FROM peru_arco_requests
             WHERE completed_at IS NULL
               AND response_deadline < datetime('now') ORDER BY response_deadline;"

# International transfers without ANPD notification reference
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, recipient_country, safeguard FROM peru_transfer_log
             WHERE anpd_notification_ref IS NULL;"
```

## Related
- `argentina-pdpa-data-localization-workers.md`
- `mexico-lfpdppp-workers-d1.md`
- `gdpr-data-subject-rights-api.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-retention-automated-deletion-workers.md`

## Sources
- Ley 29733 LPDP: https://www.minjus.gob.pe/privacidad/
- DS 003-2013-JUS Regulation: https://cdn.www.gob.pe/uploads/document/file/2215738/DS-003-2013-JUS-RLPDP.pdf
- ANPD (MINJUSDH): https://www.minjusdh.gob.pe/anpd
- Registro Nacional de Bancos de Datos: https://registropd.minjusdh.gob.pe/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare Regional Services: https://developers.cloudflare.com/data-localization/regional-services/
