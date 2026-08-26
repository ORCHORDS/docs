# Mexico LFPDPPP Privacy Compliance on Cloudflare Workers / D1
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Your product collects personal data from users in Mexico. The **Ley Federal de Protección de Datos
Personales en Posesión de los Particulares (LFPDPPP, 2010)** and its Regulation (Reglamento,
2011), plus INAI's "Lineamientos" (federal guidelines), impose Aviso de Privacidad obligations,
ARCO rights (Acceso, Rectificación, Cancelación, Oposición), sensitive-data restrictions, data
breach notification within **3 business days**, and cross-border transfer consent. You need all of
these wired into Cloudflare Workers + D1.

## Context
INAI (Instituto Nacional de Transparencia, Acceso a la Información y Protección de Datos
Personales) is the federal enforcement authority. Key obligations:
- **Aviso de Privacidad**: must be provided before or at the moment of data collection; simplified
  (short) notices are allowed for constrained channels (SMS, physical). A full notice is required
  for websites.
- **ARCO rights**: Data subjects may exercise Access, Rectification, Cancellation, or Opposition.
  The controller must respond within **20 business days** and execute within **15 more** (Art. 32).
- **Sensitive personal data**: race/ethnicity, health, religion, sexual orientation, philosophical
  beliefs, political opinions, biometrics, genetics — requires **written (explicit) consent**.
- **Data transfers**: transfers to third parties (including processors — "encargados") require
  either a Data Processing Agreement or explicit consent, unless the exception of Art. 37 applies.
- **International transfers**: require consent or guarantees of "adequate" protection; Mexico has
  no formal adequacy list — controllers must assess.
- **Breach notification to INAI**: within **3 business days** of becoming aware (Art. 20 Reg.).
- Fines range from MXN 100 to 320 000 daily minimum wages (~MXN 2 000 to 6.4 million).

## Key Requirements — Aviso de Privacidad Delivery and Consent

```typescript
// worker/mexico-lfpdppp-consent.ts
interface ConsentRecord {
  subject_id: string;
  aviso_version: string;    // version hash of published Aviso de Privacidad
  purposes: string[];
  sensitive_data: boolean;  // requires written/explicit consent
  consent_method: 'implicit' | 'explicit' | 'written';
  consented_at: string;     // ISO 8601
  ip_country: string;
}

export async function recordConsent(
  db: D1Database,
  record: ConsentRecord,
): Promise<void> {
  if (record.sensitive_data && record.consent_method !== 'written') {
    throw new Error('LFPDPPP: sensitive personal data requires written (explicit) consent');
  }

  await db
    .prepare(
      `INSERT INTO mexico_consent_log
         (subject_id, aviso_version, purposes_json, sensitive_data,
          consent_method, consented_at, ip_country)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(subject_id) DO UPDATE SET
         aviso_version  = excluded.aviso_version,
         purposes_json  = excluded.purposes_json,
         sensitive_data = excluded.sensitive_data,
         consent_method = excluded.consent_method,
         consented_at   = excluded.consented_at`,
    )
    .bind(
      record.subject_id,
      record.aviso_version,
      JSON.stringify(record.purposes),
      record.sensitive_data ? 1 : 0,
      record.consent_method,
      record.consented_at,
      record.ip_country,
    )
    .run();
}

// Serve the Aviso de Privacidad header link on every response
export function withAvisoHeader(response: Response, avisoUrl: string): Response {
  const headers = new Headers(response.headers);
  headers.set('X-Aviso-Privacidad', avisoUrl);
  return new Response(response.body, { ...response, headers });
}
```

D1 schema:
```sql
CREATE TABLE IF NOT EXISTS mexico_consent_log (
  subject_id     TEXT PRIMARY KEY,
  aviso_version  TEXT NOT NULL,
  purposes_json  TEXT NOT NULL,
  sensitive_data INTEGER NOT NULL DEFAULT 0,
  consent_method TEXT NOT NULL,
  consented_at   TEXT NOT NULL,
  ip_country     TEXT NOT NULL
);
```

## ARCO Rights Handler (Art. 29–35 LFPDPPP)

```typescript
// worker/mexico-lfpdppp-arco.ts
type ArcoType = 'acceso' | 'rectificacion' | 'cancelacion' | 'oposicion';

export async function handleArcoRequest(
  db: D1Database,
  subjectId: string,
  type: ArcoType,
  detail?: Record<string, string>,
): Promise<Response> {
  // Record the request — deadline tracking starts now
  await db
    .prepare(
      `INSERT INTO mexico_arco_requests
         (subject_id, type, detail_json, requested_at, response_deadline, executed_deadline)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP,
               datetime('now', '+20 days'),
               datetime('now', '+35 days'))`,
    )
    .bind(subjectId, type, JSON.stringify(detail ?? {}))
    .run();

  if (type === 'acceso') {
    const rows = await db
      .prepare('SELECT * FROM personal_data WHERE subject_id = ?')
      .bind(subjectId)
      .all();
    return Response.json({ type: 'acceso', data: rows.results });
  }

  if (type === 'cancelacion') {
    // Cancelación = suppression / erasure; LFPDPPP Art. 25 — blocked data first, delete on
    // expiry of legal retention period
    await db
      .prepare(
        `UPDATE personal_data SET blocked = 1, blocked_at = CURRENT_TIMESTAMP
         WHERE subject_id = ?`,
      )
      .bind(subjectId)
      .run();
    return Response.json({ type: 'cancelacion', status: 'blocked_pending_deletion' });
  }

  if (type === 'rectificacion' && detail) {
    for (const [field, value] of Object.entries(detail)) {
      await db
        .prepare(
          `UPDATE personal_data_fields SET value = ?, updated_at = CURRENT_TIMESTAMP
           WHERE subject_id = ? AND field = ?`,
        )
        .bind(value, subjectId, field)
        .run();
    }
    return Response.json({ type: 'rectificacion', status: 'updated', fields: Object.keys(detail) });
  }

  if (type === 'oposicion') {
    // Opposition to processing — record it; processing must cease within the execution window
    await db
      .prepare(
        `INSERT INTO mexico_opposition_log (subject_id, registered_at)
         VALUES (?, CURRENT_TIMESTAMP)
         ON CONFLICT(subject_id) DO UPDATE SET registered_at = CURRENT_TIMESTAMP`,
      )
      .bind(subjectId)
      .run();
    return Response.json({ type: 'oposicion', status: 'registered' });
  }

  return Response.json({ error: 'invalid ARCO type' }, { status: 400 });
}
```

## Data Transfer Agreement Check (Art. 37 LFPDPPP)

```typescript
// worker/mexico-lfpdppp-transfers.ts
interface TransferRecord {
  recipient_name: string;
  recipient_country: string;
  purpose: string;
  legal_basis: 'dpa' | 'consent' | 'art37_exception';
  exception_code?: string;   // e.g. 'art37_iv_legal_obligation'
  effective_from: string;
}

export async function registerTransfer(
  db: D1Database,
  transfer: TransferRecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO mexico_transfer_register
         (recipient_name, recipient_country, purpose,
          legal_basis, exception_code, effective_from, created_at)
       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(
      transfer.recipient_name,
      transfer.recipient_country,
      transfer.purpose,
      transfer.legal_basis,
      transfer.exception_code ?? null,
      transfer.effective_from,
    )
    .run();
}
```

## Breach Notification (Art. 20 Reglamento — 3 Business Days)

```typescript
// worker/mexico-lfpdppp-breach.ts
export async function recordBreach(
  db: D1Database,
  id: string,
  description: string,
  dataTypes: string[],
  affectedCount: number,
): Promise<void> {
  // 3 business days — approximate as 4 calendar days from discovery
  const deadline = new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString();

  await db
    .prepare(
      `INSERT INTO mexico_breach_log
         (id, description, data_types_json, affected_count,
          inai_deadline, discovered_at, notified_at)
       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)`,
    )
    .bind(id, description, JSON.stringify(dataTypes), affectedCount, deadline)
    .run();
}

export async function alertOverdueBreach(db: D1Database): Promise<void> {
  const overdue = await db
    .prepare(
      `SELECT id, inai_deadline FROM mexico_breach_log
       WHERE notified_at IS NULL AND inai_deadline < CURRENT_TIMESTAMP`,
    )
    .all();

  for (const row of overdue.results) {
    console.error(`[LFPDPPP] OVERDUE INAI notification — breach ${row.id}`);
  }
}
```

D1 schema additions:
```sql
CREATE TABLE IF NOT EXISTS mexico_arco_requests (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id       TEXT NOT NULL,
  type             TEXT NOT NULL,
  detail_json      TEXT NOT NULL DEFAULT '{}',
  requested_at     TEXT NOT NULL,
  response_deadline TEXT NOT NULL,   -- 20 business days
  executed_deadline TEXT NOT NULL    -- 35 business days
);
CREATE TABLE IF NOT EXISTS mexico_opposition_log (
  subject_id    TEXT PRIMARY KEY,
  registered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mexico_transfer_register (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient_name   TEXT NOT NULL,
  recipient_country TEXT NOT NULL,
  purpose          TEXT NOT NULL,
  legal_basis      TEXT NOT NULL,
  exception_code   TEXT,
  effective_from   TEXT NOT NULL,
  created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mexico_breach_log (
  id             TEXT PRIMARY KEY,
  description    TEXT NOT NULL,
  data_types_json TEXT NOT NULL,
  affected_count  INTEGER NOT NULL DEFAULT 0,
  inai_deadline  TEXT NOT NULL,
  discovered_at  TEXT NOT NULL,
  notified_at    TEXT
);
```

## Anti-patterns
- Publishing the Aviso de Privacidad only in English — LFPDPPP requires it in Spanish for Mexican
  residents (plain language, accessible format).
- Treating the "encargado" relationship as needing only a verbal agreement — a signed Data
  Processing Agreement (contrato de encargo) is mandatory.
- Using legitimate interest as a lawful basis for sensitive data — only written explicit consent or
  a statutory exception is valid.
- Starting the 20-business-day ARCO clock from when you validate the request rather than from
  receipt — INAI counts from receipt.
- Failing to inform affected individuals when their data is part of a breach (Art. 20 Reg. also
  requires subject notification when there is a significant risk of harm).

## Gotchas
- **Business days** (días hábiles) exclude Mexican national holidays — store the deadline as a
  calendar approximation (+4 days for breach) and verify manually near the boundary.
- The Cancelación right results in **data blocking first**, not immediate deletion; deletion occurs
  only after all legal retention obligations are satisfied.
- Mexico has no formal "adequacy" list for international transfers; INAI expects controllers to
  document their own adequacy assessment in the transfer register.
- The Aviso de Privacidad version must be tracked — if purposes change materially, a new Aviso
  must be published and prior consents may need re-capture.

## Verification
```bash
# ARCO requests approaching response deadline (next 5 days)
wrangler d1 execute <DB_NAME> \
  --command "SELECT subject_id, type, requested_at, response_deadline FROM mexico_arco_requests
             WHERE response_deadline < datetime('now', '+5 days')
               AND response_deadline > datetime('now') ORDER BY response_deadline;"

# Overdue INAI breach notifications
wrangler d1 execute <DB_NAME> \
  --command "SELECT id, inai_deadline FROM mexico_breach_log
             WHERE notified_at IS NULL AND inai_deadline < datetime('now');"

# Sensitive-data consents without 'written' method
wrangler d1 execute <DB_NAME> \
  --command "SELECT subject_id, consent_method FROM mexico_consent_log
             WHERE sensitive_data = 1 AND consent_method != 'written';"
```

## Related
- `gdpr-data-subject-rights-api.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-retention-automated-deletion-workers.md`
- `argentina-pdpa-data-localization-workers.md`

## Sources
- LFPDPPP text: https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf
- Reglamento LFPDPPP (2011): https://www.dof.gob.mx/nota_detalle.php?codigo=5212905&fecha=21/12/2011
- INAI: https://home.inai.org.mx/
- Lineamientos de Aviso de Privacidad: https://www.dof.gob.mx/nota_detalle.php?codigo=5284966&fecha=17/01/2013
- Cloudflare D1: https://developers.cloudflare.com/d1/
