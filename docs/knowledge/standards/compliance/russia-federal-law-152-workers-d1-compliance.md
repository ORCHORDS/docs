# Russia Federal Law 152-FZ Personal Data Compliance on Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your SaaS serves Russian users (ru-RU locale, .ru domains, or Russian payment instruments detected). Legal counsel flags that Federal Law No. 152-FZ "On Personal Data" requires personal data of Russian citizens to be **initially stored on servers located within Russia**. You need to understand what this means for a Cloudflare Workers + D1 architecture and implement a compliant processing pipeline without rewriting your entire stack.

---

## Context

Russia's Federal Law 152-FZ was amended in 2014 (effective 2015, tightened 2023) to require that operators collecting personal data of Russian citizens must **record, systematize, accumulate, store, clarify and retrieve** that data using databases located in the Russian Federation. Roskomnadzor (RKN) is the supervisory authority and maintains a register of violators — non-compliant foreign operators have faced blocking.

Key requirements:

| Obligation | Detail |
|---|---|
| Localisation | Primary DB for Russian-citizen PD must reside in Russia |
| Cross-border transfer | Allowed after local copy is established; adequate or consent-based |
| Registration | Notify RKN before processing starts (operator notification) |
| Retention | Data held no longer than processing purpose requires |
| Data subjects' rights | Access, correction, deletion (similar to GDPR but lighter) |
| Biometrics | Separate legal basis, stricter controls |

Cloudflare D1 currently has no Russian data-centre region. This means **D1 alone cannot be the primary store for Russian-citizen PD**. The compliant pattern is: Russian data lands in an operator-controlled Russian database first; only derived/aggregated or pseudonymised records flow to D1/Workers for global analytics.

---

## 1. Detecting Russian Data Subjects in Workers

```typescript
// src/middleware/russia-subject-detector.ts
export interface RussiaSignals {
  cfCountry: boolean;
  locale: boolean;
  phonePrefix: boolean;
  inn: boolean; // Russian tax ID format
}

export function detectRussianSubject(request: Request): RussiaSignals {
  const country = request.cf?.country ?? '';
  const acceptLang = request.headers.get('accept-language') ?? '';
  const phone = request.headers.get('x-user-phone') ?? '';
  const inn = request.headers.get('x-user-inn') ?? '';

  return {
    cfCountry: country === 'RU',
    locale: /ru(?:-RU)?/i.test(acceptLang),
    phonePrefix: /^\+7/.test(phone),
    // INN is 10 digits (legal entity) or 12 digits (individual)
    inn: /^\d{10}$|^\d{12}$/.test(inn),
  };
}

export function isRussianSubject(signals: RussiaSignals): boolean {
  // Any strong signal triggers localisation requirement
  return signals.cfCountry || signals.inn || signals.phonePrefix;
}
```

---

## 2. Routing Russian PD to the Domestic Database

Because D1 has no Russia region, Russian PD must go to an operator-controlled Russian VPS/database (e.g., Yandex Cloud, SberCloud, Selectel). Workers can proxy to a private upstream.

```typescript
// src/handlers/russian-data-router.ts
export interface Env {
  RUSSIA_DB_URL: string;          // https://ru-api.internal/pd
  RUSSIA_DB_TOKEN: string;        // Secret from Workers secret store
  D1: D1Database;                 // For non-Russian or anonymised data only
}

interface PersonalDataRecord {
  userId: string;
  email: string;
  phone?: string;
  createdAt: string;
  citizenship?: string;
}

export async function storePersonalData(
  env: Env,
  record: PersonalDataRecord,
  isRussian: boolean,
): Promise<{ id: string; stored: 'russia' | 'd1' }> {
  if (isRussian) {
    // Primary storage: Russian-located database
    const res = await fetch(`${env.RUSSIA_DB_URL}/personal-data`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.RUSSIA_DB_TOKEN}`,
      },
      body: JSON.stringify(record),
    });

    if (!res.ok) {
      throw new Error(`Russia DB write failed: ${res.status}`);
    }

    const { id } = await res.json<{ id: string }>();

    // Cross-border copy: pseudonymised record only (no direct PD)
    await env.D1.prepare(
      `INSERT OR IGNORE INTO users_global (id, country_flag, created_at)
       VALUES (?, 'RU', ?)`,
    )
      .bind(id, record.createdAt)
      .run();

    return { id, stored: 'russia' };
  }

  // Non-Russian subject: store directly in D1
  const result = await env.D1.prepare(
    `INSERT INTO users (email, phone, created_at) VALUES (?, ?, ?)
     RETURNING id`,
  )
    .bind(record.email, record.phone ?? null, record.createdAt)
    .run();

  const id = String(result.results[0].id);
  return { id, stored: 'd1' };
}
```

---

## 3. Cross-Border Transfer Controls

After the primary Russian DB holds the data, a cross-border transfer to D1 requires either:
- **Adequate country** determination by RKN (EU SCCs do not apply here — Russia has its own list), or
- **Data subject consent**, or
- **Contract necessity**

```typescript
// src/services/cross-border-transfer.ts

type TransferBasis =
  | 'adequate_country'   // RKN-approved list
  | 'consent'
  | 'contract_necessity'
  | 'vital_interests';

interface TransferRecord {
  transferId: string;
  dataSubjectId: string;
  destinationCountry: string;
  basis: TransferBasis;
  consentId?: string;
  transferredAt: string;
  pseudonymised: boolean;
}

export async function recordCrossBorderTransfer(
  db: D1Database,
  record: TransferRecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO cross_border_transfers
        (transfer_id, data_subject_id, destination_country, basis,
         consent_id, transferred_at, pseudonymised)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      record.transferId,
      record.dataSubjectId,
      record.destinationCountry,
      record.basis,
      record.consentId ?? null,
      record.transferredAt,
      record.pseudonymised ? 1 : 0,
    )
    .run();
}

// RKN-approved adequate countries (illustrative subset — verify current list)
const RKN_ADEQUATE_COUNTRIES = new Set([
  'DE', 'FR', 'GB', 'AT', 'BE', 'CH', 'IL', 'CA', 'AU',
]);

export function isAdequateCountry(isoCode: string): boolean {
  return RKN_ADEQUATE_COUNTRIES.has(isoCode.toUpperCase());
}
```

---

## 4. Data Subject Rights Endpoint

152-FZ grants rights to access, correction, and deletion. The operator must respond within **30 days** (10 business days for blocking requests).

```typescript
// src/handlers/data-subject-rights.ts

export async function handleAccessRequest(
  env: Env,
  userId: string,
  isRussian: boolean,
): Promise<Response> {
  if (isRussian) {
    // Fetch from Russian DB
    const res = await fetch(`${env.RUSSIA_DB_URL}/personal-data/${userId}`, {
      headers: { Authorization: `Bearer ${env.RUSSIA_DB_TOKEN}` },
    });
    if (!res.ok) return new Response('Not found', { status: 404 });
    const data = await res.json();
    return Response.json(data);
  }

  const row = await env.D1.prepare(
    'SELECT id, email, phone, created_at FROM users WHERE id = ?',
  )
    .bind(userId)
    .first();

  return row ? Response.json(row) : new Response('Not found', { status: 404 });
}

export async function handleErasureRequest(
  env: Env,
  db: D1Database,
  userId: string,
  isRussian: boolean,
): Promise<Response> {
  const erasedAt = new Date().toISOString();

  if (isRussian) {
    // Delete from Russian primary DB first
    await fetch(`${env.RUSSIA_DB_URL}/personal-data/${userId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${env.RUSSIA_DB_TOKEN}` },
    });
  }

  // Purge pseudonymised cross-border record from D1
  await db.prepare('DELETE FROM users_global WHERE id = ?').bind(userId).run();

  // Audit trail
  await db
    .prepare(
      `INSERT INTO erasure_log (user_id, erased_at, law)
       VALUES (?, ?, '152-FZ')`,
    )
    .bind(userId, erasedAt)
    .run();

  return new Response(null, { status: 204 });
}
```

---

## 5. Operator Notification Register (RKN Filing Support)

Before starting processing, operators must notify RKN. Workers can maintain a machine-readable record of processing activities to support that filing.

```typescript
// src/services/rkn-register.ts

interface ProcessingActivity {
  activityId: string;
  purpose: string;
  legalBasis: '6-1' | '6-2' | '6-3' | '6-4' | '6-5';  // 152-FZ Article 6 bases
  categories: string[];
  subjectCategories: string[];
  retentionDays: number;
  crossBorderTransfer: boolean;
  russianStorageLocation: string;  // e.g., "Selectel RU-MSK-1 / DC: Moscow"
  createdAt: string;
}

export async function upsertProcessingActivity(
  db: D1Database,
  activity: ProcessingActivity,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO rkn_register
        (activity_id, purpose, legal_basis, categories, subject_categories,
         retention_days, cross_border_transfer, russian_storage_location, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(activity_id) DO UPDATE SET
         purpose = excluded.purpose,
         legal_basis = excluded.legal_basis`,
    )
    .bind(
      activity.activityId,
      activity.purpose,
      activity.legalBasis,
      JSON.stringify(activity.categories),
      JSON.stringify(activity.subjectCategories),
      activity.retentionDays,
      activity.crossBorderTransfer ? 1 : 0,
      activity.russianStorageLocation,
      activity.createdAt,
    )
    .run();
}
```

---

## 6. Automated Retention Enforcement

```typescript
// src/cron/retention-enforcer.ts
export async function enforceRetention(env: Env): Promise<void> {
  // Purge from Russian DB via API
  const cutoffRU = new Date();
  cutoffRU.setDate(cutoffRU.getDate() - 365); // example: 1-year retention

  await fetch(`${env.RUSSIA_DB_URL}/personal-data/purge-before`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${env.RUSSIA_DB_TOKEN}`,
    },
    body: JSON.stringify({ before: cutoffRU.toISOString() }),
  });

  // Purge global pseudonymised records from D1
  await env.D1.prepare(
    `DELETE FROM users_global
     WHERE created_at < datetime('now', '-365 days')`,
  ).run();
}
```

---

## Anti-patterns

- **Storing Russian citizen PD in D1 as primary store** — D1 has no Russia region; this violates Article 18(5) of 152-FZ.
- **Assuming GDPR SCCs satisfy 152-FZ cross-border requirements** — Russia does not recognise EU SCCs; use consent or RKN adequate country list.
- **Sending biometric data cross-border without explicit consent** — biometrics have stricter rules under 152-FZ Article 11.
- **Omitting RKN notification** — filing is required before processing starts, not after.
- **Using only CF-IPCountry for residency determination** — IP geolocation is not sufficient; combine with phone prefix, INN, or declared residency.

---

## Gotchas

- **VPN users**: Russian VPN users may appear non-Russian; use a layered signal approach, not just CF-IPCountry.
- **Legal entity data**: 152-FZ applies only to natural persons; data about legal entities is not in scope.
- **Sensitive categories**: Health, biometric, racial/ethnic origin, and criminal records have additional restrictions even within Russia.
- **2023 amendments**: Penalties increased substantially; fines can reach 3% of annual Russian revenue for repeat violations.
- **Roskomnadzor blocking**: Non-compliant operators can have their domains blocked in Russia; check the RKN register regularly.

---

## Verification

```bash
# Confirm no Russian PD in D1 (check for direct email/phone columns)
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM users WHERE country_flag = 'RU' AND email IS NOT NULL"
# Expected: 0 (all Russian PD should only be in Russian DB)

# Check cross-border transfer log completeness
wrangler d1 execute YOUR_DB --command \
  "SELECT basis, COUNT(*) FROM cross_border_transfers GROUP BY basis"

# Check RKN register is populated
wrangler d1 execute YOUR_DB --command \
  "SELECT activity_id, purpose, russian_storage_location FROM rkn_register"

# Verify erasure log entries carry '152-FZ' tag
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM erasure_log WHERE law = '152-FZ'"
```

---

## Related

- `cross-border-data-transfer-cloudflare-workers.md`
- `data-localization-requirements.md`
- `gdpr-international-transfers-schrems2.md`
- `data-retention-automated-deletion-workers.md`
- `store-region-matrix.md`

---

## Sources

- Federal Law No. 152-FZ "On Personal Data", 2006 (as amended 2023): [consultant.ru](https://www.consultant.ru/document/cons_doc_LAW_61801/)
- Roskomnadzor operator notification guidance: [pd.rkn.gov.ru](https://pd.rkn.gov.ru)
- RKN Cross-Border Transfer Guidance (2022 Order No. 179)
- Russia Data Localisation — Article 18(5) 152-FZ
- Cloudflare D1 available locations: [developers.cloudflare.com/d1](https://developers.cloudflare.com/d1/reference/data-location/)
