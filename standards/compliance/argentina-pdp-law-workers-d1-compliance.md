# Argentina Personal Data Protection Law 25.326 — Cloudflare Workers + D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project processes personal data of Argentine users. Argentina's Ley de Protección de Datos Personales N° 25.326 (LPDP, 2000) is enforced by the AAIP (Agencia de Acceso a la Información Pública, formerly DNPDP). Argentina holds **EU adequacy** status, meaning SCCs are not required for EU→AR transfers, and Argentine law itself restricts outbound transfers to countries without equivalent protection. A companion article (`argentina-pdpa-data-localization-workers.md`) covers data localisation only; this article covers the full LPDP compliance posture including consent, data subject rights, sensitive data, database registration, and cross-border transfer obligations.

---

## Context

Key LPDP pillars for a pseudonymous social platform:

- **Consent** (Art. 5): must be free, express, and informed. Exceptions: contractual necessity, legal obligation, vital interests, public interest, legitimate interest (as interpreted by AAIP Disposición 11-E/2006).
- **Sensitive data** (Art. 2 & 7): racial/ethnic origin, political opinions, religious beliefs, union membership, health, sexual life — requires explicit written consent; collection for discriminatory purposes is prohibited.
- **Database registration** (Art. 21): every database containing personal data of Argentine residents must be registered with AAIP.
- **Data subject rights** (Art. 14-16): access (free, once per year), rectification/update, deletion (suppresión), objection to processing.
- **Cross-border transfers** (Art. 12): prohibited to countries without an "adequate" protection level unless AAIP grants an exception.
- **Sanctions** (Art. 31-39): mild (warning/suspension), serious (fines), very serious (5-year registration ban, database deletion order).

---

## 1 — Database Registration Stub

```typescript
// src/ar/database-registry.ts
// Art. 21 LPDP: every "archivo, registro, base o banco de datos" holding personal
// data of Argentine residents must be formally registered with AAIP.
// Registration is done via AAIP's online portal: https://www.argentina.gob.ar/aaip
// This module produces the registration manifest to submit.

export interface RegistrationManifest {
  database_name: string;
  controller: string;
  cuit: string;                    // Argentine tax ID of the controller
  purpose: string;
  categories: string[];
  recipients: string[];
  cross_border: boolean;
  contact_email: string;
}

export function buildRegistrationManifest(): RegistrationManifest {
  return {
    database_name: 'example project_PLATFORM_USERS',
    controller: 'example project Platform S.A.S.',
    cuit: process.env.AR_CUIT ?? '',
    purpose: 'Operation of an anonymous social discussion platform',
    categories: ['pseudonymous_handle', 'hashed_email', 'post_content', 'ip_country'],
    recipients: ['Cloudflare Inc. (infrastructure)'],
    cross_border: true,
    contact_email: 'privacidad@example project.example.com',
  };
}
```

---

## 2 — Consent Capture with LPDP Art. 5 Requirements

```typescript
// src/ar/consent.ts
// Consent must be: libre (free), expresa (express), informada (informed).
// For sensitive data: also written (escrita).

export interface LPDPConsentRecord {
  account_id: string;
  purpose: string;
  is_sensitive: boolean;
  consent_text_shown: string;  // verbatim text the user consented to
  consent_ts: number;
  ip_country_at_consent: string;
  withdrawn_ts?: number;
}

export async function recordConsent(
  db: D1Database,
  record: LPDPConsentRecord,
): Promise<void> {
  const id = crypto.randomUUID();
  await db.prepare(
    `INSERT INTO ar_consent_records
     (id, account_id, purpose, is_sensitive, consent_text_hash, consent_ts, ip_country)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id,
    record.account_id,
    record.purpose,
    record.is_sensitive ? 1 : 0,
    await sha256(record.consent_text_shown),
    record.consent_ts,
    record.ip_country_at_consent,
  ).run();
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function withdrawConsent(
  db: D1Database,
  accountId: string,
  purpose: string,
): Promise<void> {
  await db.prepare(
    `UPDATE ar_consent_records SET withdrawn_ts = ?
     WHERE account_id = ? AND purpose = ? AND withdrawn_ts IS NULL`,
  ).bind(Math.floor(Date.now() / 1000), accountId, purpose).run();
}
```

---

## 3 — Data Subject Rights: Access (Art. 14)

```typescript
// src/ar/art14-access.ts
// Art. 14: the data subject may request, free of charge, the information held about them.
// The controller must respond within 5 business days of receipt of the request.
// The right may be exercised once per calendar year (or at any time if legitimate interest shown).

export async function fulfillAccess(
  db: D1Database,
  accountId: string,
): Promise<Record<string, unknown>> {
  const lastRequest = await db.prepare(
    `SELECT requested_at FROM ar_dsr_log
     WHERE account_id = ? AND right_type = 'access'
     ORDER BY requested_at DESC LIMIT 1`,
  ).bind(accountId).first<{ requested_at: number }>();

  const now = Math.floor(Date.now() / 1000);
  const ONE_YEAR = 365 * 24 * 3600;
  if (lastRequest && now - lastRequest.requested_at < ONE_YEAR) {
    return {
      error: 'annual_limit_reached',
      next_eligible_at: new Date((lastRequest.requested_at + ONE_YEAR) * 1000).toISOString(),
    };
  }

  const [profile, consents, posts] = await Promise.all([
    db.prepare(`SELECT pseudonym, email_hash, created_at FROM accounts WHERE id = ?`)
      .bind(accountId).first(),
    db.prepare(`SELECT purpose, is_sensitive, consent_ts FROM ar_consent_records WHERE account_id = ?`)
      .bind(accountId).all(),
    db.prepare(`SELECT post_id, body_hash, created_at FROM posts WHERE account_id = ?`)
      .bind(accountId).all(),
  ]);

  await db.prepare(
    `INSERT INTO ar_dsr_log (account_id, right_type, requested_at) VALUES (?, 'access', ?)`,
  ).bind(accountId, now).run();

  return {
    law: 'Argentina LPDP 25.326 Art.14',
    response_deadline_business_days: 5,
    generated_at: new Date().toISOString(),
    profile,
    consents: consents.results,
    posts: posts.results,
  };
}
```

---

## 4 — Rectification and Deletion (Art. 15 & 16)

```typescript
// src/ar/art15-16-rectification-deletion.ts

export async function rectifyData(
  db: D1Database,
  accountId: string,
  field: 'pseudonym' | 'email_hash',
  newValue: string,
): Promise<void> {
  const stmts: Record<string, string> = {
    pseudonym:  `UPDATE accounts SET pseudonym  = ?, updated_at = ? WHERE id = ?`,
    email_hash: `UPDATE accounts SET email_hash = ?, updated_at = ? WHERE id = ?`,
  };
  await db.batch([
    db.prepare(stmts[field]).bind(newValue, Math.floor(Date.now() / 1000), accountId),
    db.prepare(
      `INSERT INTO ar_dsr_log (account_id, right_type, requested_at) VALUES (?, 'rectification', ?)`,
    ).bind(accountId, Math.floor(Date.now() / 1000)),
  ]);
}

export async function deleteAccount(
  db: D1Database,
  accountId: string,
): Promise<{ deleted: boolean; reason?: string }> {
  // Art. 16 par. 5: deletion may be refused if data is legally required (e.g. court order)
  const hold = await db.prepare(
    `SELECT id FROM legal_holds WHERE account_id = ? LIMIT 1`,
  ).bind(accountId).first();

  if (hold) {
    await db.prepare(
      `INSERT INTO ar_dsr_log (account_id, right_type, requested_at, outcome)
       VALUES (?, 'deletion', ?, 'refused_legal_hold')`,
    ).bind(accountId, Math.floor(Date.now() / 1000)).run();
    return { deleted: false, reason: 'legal_hold_active' };
  }

  await db.batch([
    db.prepare(`DELETE FROM posts WHERE account_id = ?`).bind(accountId),
    db.prepare(`DELETE FROM ar_consent_records WHERE account_id = ?`).bind(accountId),
    db.prepare(`DELETE FROM accounts WHERE id = ?`).bind(accountId),
    db.prepare(
      `INSERT INTO ar_dsr_log (account_id, right_type, requested_at, outcome)
       VALUES (?, 'deletion', ?, 'completed')`,
    ).bind(accountId, Math.floor(Date.now() / 1000)),
    db.prepare(
      `INSERT INTO deletion_audit (account_id, law, ts) VALUES (?, 'AR-LPDP-25326', ?)`,
    ).bind(accountId, Math.floor(Date.now() / 1000)),
  ]);
  return { deleted: true };
}
```

---

## 5 — Cross-Border Transfer Enforcement (Art. 12)

```typescript
// src/ar/transfer-guard.ts
// Art. 12 LPDP: international transfer is prohibited to countries without
// "adequate protection" (equivalent to Argentine law) or AAIP exception.
// Argentina itself has EU adequacy, so EU→AR flows are fine.
// AR→third-country requires checking AAIP's approved country list.

// AAIP Disposición 60-E/2016 — countries recognised as adequate by AAIP
const AAIP_ADEQUATE_COUNTRIES = new Set([
  'EU', 'EEA', 'CH', 'IL', 'CA', 'NZ', 'JP', 'KR', 'UK',
]);

export interface TransferContext {
  destinationIso2: string;
  hasDpa: boolean;         // Data Processing Agreement with AAIP-approved SCCs
  hasAaipExemption: boolean;
}

export function assertTransferLawful(ctx: TransferContext): void {
  if (AAIP_ADEQUATE_COUNTRIES.has(ctx.destinationIso2)) return;
  if (ctx.hasDpa) return;
  if (ctx.hasAaipExemption) return;
  throw new Error(
    `AR LPDP Art. 12 — Transfer to ${ctx.destinationIso2} prohibited without AAIP approval or DPA.`,
  );
}

export async function logCrossBorderTransfer(
  db: D1Database,
  accountId: string,
  destination: string,
  basis: string,
): Promise<void> {
  await db.prepare(
    `INSERT INTO ar_cross_border_log (account_id, destination, basis, ts)
     VALUES (?, ?, ?, ?)`,
  ).bind(accountId, destination, basis, Math.floor(Date.now() / 1000)).run();
}
```

---

## 6 — Objection Right (Art. 27 par. 3) and AAIP Complaint Intake

```typescript
// src/ar/objection.ts
// Art. 27(3): data subjects may object to processing for marketing/profiling.
// Controller must cease processing within 5 business days of objection.

export async function recordObjection(
  db: D1Database,
  accountId: string,
  purpose: string,
): Promise<void> {
  const deadline = Math.floor(Date.now() / 1000) + 5 * 24 * 3600; // 5 calendar days
  await db.prepare(
    `INSERT INTO ar_objections (account_id, purpose, objected_at, cease_by)
     VALUES (?, ?, ?, ?)`,
  ).bind(accountId, purpose, Math.floor(Date.now() / 1000), deadline).run();
}

export async function processingAllowed(
  db: D1Database,
  accountId: string,
  purpose: string,
): Promise<boolean> {
  const objection = await db.prepare(
    `SELECT id FROM ar_objections WHERE account_id = ? AND purpose = ? LIMIT 1`,
  ).bind(accountId, purpose).first();
  return !objection;
}
```

---

## Anti-patterns

- **Omitting database registration**: AAIP actively audits registered databases; operating an unregistered database is itself a violation independent of any data breach.
- **Using opt-out consent for sensitive data**: Health, sexual life, political opinion data requires opt-in (explicit written consent). A pre-ticked checkbox is unlawful.
- **Transferring to non-adequate countries without AAIP exception**: Unlike GDPR SCCs which are self-certifying, LPDP Art. 12 requires AAIP to explicitly authorise transfers to non-adequate countries or that the receiving country's law provides equivalent protection.
- **Ignoring the 5-business-day response window for DSR**: GDPR practitioners often default to 30 days; Argentina's window is shorter for access (5 days) and objections (5 days to cease processing).

---

## Gotchas

- **Annual access limit**: Art. 14 allows only one free access request per year unless the data subject demonstrates legitimate interest for more frequent requests.
- **Sensitive data includes trade union membership**: Relevant if example project hosts labour-activism discussions and users identify themselves as members.
- **Controller ≠ processor distinction is present but less developed than GDPR**: LPDP focuses on the "responsable del archivo" (controller); processor obligations are managed by contract rather than a separate regulatory regime.
- **Pending reform (Draft Law 2023)**: A modernisation bill updating LPDP to align more closely with GDPR is under Senate consideration as of August 2026 — monitor AAIP announcements.

---

## Verification

```bash
# Check AR consent records exist
wrangler d1 execute example project_DB \
  --command "SELECT COUNT(*) FROM ar_consent_records;"

# Check overdue objections (should be zero)
wrangler d1 execute example project_DB \
  --command "SELECT account_id, purpose FROM ar_objections WHERE cease_by < unixepoch();"

# DSR log summary
wrangler d1 execute example project_DB \
  --command "SELECT right_type, outcome, COUNT(*) FROM ar_dsr_log GROUP BY right_type, outcome;"
```

---

## Related

- `argentina-pdpa-data-localization-workers.md` — Data localisation obligations under LPDP
- `brazil-lgpd-data-subject-rights-workers-d1.md` — DSR patterns applicable to LATAM context
- `chile-data-protection-bill-workers-d1.md` — Adjacent LATAM regime (Law 21.719)
- `cross-border-data-transfer-mechanisms.md` — SCC and adequacy decision overview

---

## Sources

- Argentina LPDP Law 25.326 (2000): <https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/norma.htm>
- AAIP — Agencia de Acceso a la Información Pública: <https://www.argentina.gob.ar/aaip>
- AAIP Disposición 60-E/2016 — Transfer adequacy list
- AAIP Disposición 11-E/2006 — Consent and legitimate interest guidance
- EU Commission — Adequacy decision for Argentina (2003): <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003D0490>
