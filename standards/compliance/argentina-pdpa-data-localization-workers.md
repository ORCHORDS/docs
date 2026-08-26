# Argentina PDPA Data Localization — Cloudflare Workers D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service stores or processes personal data of Argentine residents. The Argentine Personal Data Protection Law (Ley 25.326 — PDPA) and its 2021–2024 reform proposals impose restrictions on cross-border data transfers and require registration with the Agencia de Acceso a la Información Pública (AAIP). You need to enforce transfer controls, honour subject-rights requests within statutory deadlines, and produce audit evidence — all from Cloudflare Workers without a dedicated origin server in Argentina.

---

## Context

Argentina's PDPA (Ley 25.326, 2000) was the first Latin-American law to earn EU adequacy status. Key obligations:

- **Informed consent** before collecting sensitive personal data (art. 5–6).
- **Data subject rights**: access (art. 14), rectification/update/deletion/confidentiality (art. 16) — rights must be satisfied within **5 business days** of written request.
- **Database registration**: automated personal-data files must be registered with the AAIP (art. 21–22).
- **Cross-border transfers** to countries with inadequate protection are prohibited unless the AAIP authorises the transfer or the data owner consents (art. 12).
- **Security**: controllers must adopt technical and organisational measures appropriate to the risk (art. 9).
- **Sanctions**: AAIP can issue warnings, fines (up to ~ARS 3 million under the current scale), and suspension orders.

The 2021 draft reform (never enacted as of mid-2026 but influential on AAIP guidance) would align Argentina closer to GDPR: explicit consent, data-breach notification within 72 hours, DPO appointment for high-risk processors.

Cloudflare's regional data-residency controls (Data Localization Suite) let you pin D1 and KV to specific regions; use **Workers for Platforms** to keep Argentine data within Cloudflare's South-American PoPs or route it to an origin within Argentina.

---

## 1. Consent Gate for Sensitive Data

Argentine law art. 7 treats health, sexual orientation, religious, and political data as "sensitive" — explicit informed consent is required before collection.

```typescript
// workers/argentina-consent-gate.ts
import { Env } from './types';

const SENSITIVE_CATEGORIES = [
  'health', 'sexual_orientation', 'religious_belief',
  'political_opinion', 'union_membership', 'biometric',
] as const;
type SensitiveCategory = typeof SENSITIVE_CATEGORIES[number];

interface ConsentRecord {
  userId: string;
  category: SensitiveCategory;
  grantedAt: string;   // ISO-8601
  ipAddress: string;
  userAgent: string;
  consentText: string; // verbatim text shown to user
}

export async function recordArgentinaConsent(
  env: Env,
  userId: string,
  category: SensitiveCategory,
  consentText: string,
  request: Request,
): Promise<void> {
  const record: ConsentRecord = {
    userId,
    category,
    grantedAt: new Date().toISOString(),
    ipAddress: request.headers.get('CF-Connecting-IP') ?? 'unknown',
    userAgent: request.headers.get('User-Agent') ?? 'unknown',
    consentText,
  };

  await env.DB.prepare(
    `INSERT INTO argentina_consent_log
     (user_id, category, granted_at, ip_address, user_agent, consent_text)
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).bind(
    record.userId, record.category, record.grantedAt,
    record.ipAddress, record.userAgent, record.consentText,
  ).run();
}

export async function hasSensitiveConsent(
  env: Env,
  userId: string,
  category: SensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM argentina_consent_log
     WHERE user_id = ? AND category = ? AND revoked_at IS NULL
     ORDER BY granted_at DESC LIMIT 1`,
  ).bind(userId, category).first();
  return row !== null;
}
```

---

## 2. Data Subject Rights — 5-Business-Day Clock

Art. 14 and 16 require the controller to respond within 5 business days. A D1-backed queue tracks open requests and fires an alert when the deadline approaches.

```typescript
// workers/argentina-dsr-tracker.ts
interface DSRRequest {
  id: string;
  userId: string;
  requestType: 'access' | 'rectification' | 'deletion' | 'confidentiality';
  receivedAt: string;
  deadlineAt: string;   // 5 Argentine business days
  status: 'pending' | 'in_progress' | 'completed' | 'denied';
}

function addArgentinaBusinessDays(from: Date, days: number): Date {
  // Argentine public holidays not enumerated here — maintain a holiday table
  const result = new Date(from);
  let added = 0;
  while (added < days) {
    result.setDate(result.getDate() + 1);
    const dow = result.getDay(); // 0=Sun, 6=Sat
    if (dow !== 0 && dow !== 6) added++;
  }
  return result;
}

export async function openDSRRequest(
  env: Env,
  userId: string,
  requestType: DSRRequest['requestType'],
): Promise<string> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = addArgentinaBusinessDays(now, 5);

  await env.DB.prepare(
    `INSERT INTO argentina_dsr_requests
     (id, user_id, request_type, received_at, deadline_at, status)
     VALUES (?, ?, ?, ?, ?, 'pending')`,
  ).bind(id, userId, requestType, now.toISOString(), deadline.toISOString()).run();

  return id;
}

// Scheduled handler — run every 6 hours via Cron Trigger
export async function checkDSRDeadlines(env: Env): Promise<void> {
  const warnAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(); // 24 h warning
  const { results } = await env.DB.prepare(
    `SELECT id, user_id, request_type, deadline_at FROM argentina_dsr_requests
     WHERE status IN ('pending','in_progress') AND deadline_at <= ?`,
  ).bind(warnAt).all<Pick<DSRRequest,'id'|'userId'|'requestType'|'deadlineAt'>>();

  for (const row of results) {
    await env.ALERTS_QUEUE.send({
      type: 'argentina_dsr_deadline_warning',
      requestId: row.id,
      userId: row.user_id,
      requestType: row.request_type,
      deadlineAt: row.deadline_at,
    });
  }
}
```

---

## 3. Cross-Border Transfer Guard

Art. 12 prohibits transfers to countries without "adequate" protection. Maintain an allow-list and block or log any transfer attempt that falls outside it.

```typescript
// workers/argentina-transfer-guard.ts
// Countries with AAIP-recognised adequate protection (as of 2026)
const ADEQUATE_COUNTRIES = new Set([
  'EU', 'UK', 'CH', 'IL', 'CA', 'UY', 'NZ',
  // Add others as AAIP updates the list
]);

interface TransferAttempt {
  dataSubjectId: string;
  destinationCountry: string;
  dataCategories: string[];
  timestamp: string;
  allowed: boolean;
  reason: string;
}

export async function guardCrossBorderTransfer(
  env: Env,
  dataSubjectId: string,
  destinationCountry: string,
  dataCategories: string[],
  hasExplicitConsent: boolean,
): Promise<{ allowed: boolean; reason: string }> {
  let allowed: boolean;
  let reason: string;

  if (ADEQUATE_COUNTRIES.has(destinationCountry)) {
    allowed = true;
    reason = 'destination_has_adequate_protection';
  } else if (hasExplicitConsent) {
    allowed = true;
    reason = 'data_subject_explicit_consent';
  } else {
    allowed = false;
    reason = 'no_legal_basis_for_transfer';
  }

  await env.DB.prepare(
    `INSERT INTO argentina_transfer_log
     (data_subject_id, destination_country, data_categories, timestamp, allowed, reason)
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).bind(
    dataSubjectId,
    destinationCountry,
    JSON.stringify(dataCategories),
    new Date().toISOString(),
    allowed ? 1 : 0,
    reason,
  ).run();

  return { allowed, reason };
}
```

---

## 4. AAIP Database Registration Helper

Art. 21 requires controllers to register their personal-data databases with the AAIP. This helper keeps a machine-readable registry that mirrors the AAIP form fields and can export a submission artefact.

```typescript
// workers/argentina-aaip-registry.ts
interface AaipDatabaseRecord {
  registrationId: string;
  databaseName: string;
  purpose: string;
  dataCategories: string[];
  recipientTypes: string[];
  internationalTransfers: boolean;
  securityMeasures: string[];
  ownerName: string;
  ownerCuit: string;   // Tax ID
  createdAt: string;
  lastReviewedAt: string;
}

export async function registerDatabase(
  env: Env,
  record: Omit<AaipDatabaseRecord, 'registrationId' | 'createdAt' | 'lastReviewedAt'>,
): Promise<string> {
  const id = crypto.randomUUID();
  const now = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO aaip_registry
     (id, database_name, purpose, data_categories, recipient_types,
      international_transfers, security_measures, owner_name, owner_cuit,
      created_at, last_reviewed_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id, record.databaseName, record.purpose,
    JSON.stringify(record.dataCategories),
    JSON.stringify(record.recipientTypes),
    record.internationalTransfers ? 1 : 0,
    JSON.stringify(record.securityMeasures),
    record.ownerName, record.ownerCuit, now, now,
  ).run();

  return id;
}

export async function exportAaipSubmission(env: Env): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT * FROM aaip_registry ORDER BY created_at`,
  ).all<AaipDatabaseRecord>();

  return new Response(JSON.stringify({ databases: results, exportedAt: new Date().toISOString() }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## 5. Security Incident Notification (AAIP Guidance 2023)

Although the 2021 reform draft was not enacted, AAIP guidance recommends notifying the agency of breaches affecting sensitive data within 72 hours.

```typescript
// workers/argentina-breach-notifier.ts
interface BreachEvent {
  incidentId: string;
  detectedAt: string;
  affectedCount: number;
  dataCategories: string[];
  isSensitiveData: boolean;
  containmentActions: string[];
  notifiedAaip: boolean;
  notificationDeadlineAt: string;
}

export async function recordBreach(
  env: Env,
  affectedCount: number,
  dataCategories: string[],
  containmentActions: string[],
): Promise<BreachEvent> {
  const now = new Date();
  const deadline = new Date(now.getTime() + 72 * 60 * 60 * 1000);
  const isSensitiveData = dataCategories.some(c =>
    ['health','biometric','political_opinion','sexual_orientation'].includes(c),
  );

  const event: BreachEvent = {
    incidentId: crypto.randomUUID(),
    detectedAt: now.toISOString(),
    affectedCount,
    dataCategories,
    isSensitiveData,
    containmentActions,
    notifiedAaip: false,
    notificationDeadlineAt: deadline.toISOString(),
  };

  await env.DB.prepare(
    `INSERT INTO argentina_breach_log
     (incident_id, detected_at, affected_count, data_categories,
      is_sensitive_data, containment_actions, notified_aaip, notification_deadline_at)
     VALUES (?, ?, ?, ?, ?, ?, 0, ?)`,
  ).bind(
    event.incidentId, event.detectedAt, event.affectedCount,
    JSON.stringify(event.dataCategories), event.isSensitiveData ? 1 : 0,
    JSON.stringify(event.containmentActions), event.notificationDeadlineAt,
  ).run();

  return event;
}
```

---

## Anti-patterns

- **Assuming EU-adequacy means no compliance work.** Argentina's adequacy decision predates GDPR — the AAIP's own requirements (consent, registration, 5-day rights window) are independent obligations.
- **Skipping AAIP database registration.** Art. 21 fines apply even when data processing is otherwise lawful.
- **Using soft-delete for erasure requests.** "Confidentiality" (blocking) is a separate right from deletion; both must be tracked separately.
- **Hardcoding the adequate-countries list.** AAIP updates the list; fetch it from a D1 table maintained by your compliance team.

---

## Gotchas

- The 5-business-day deadline counts from **receipt of the written request** — a logged email or form submission, not the date you open a ticket.
- Argentine "sensitive" categories partially differ from GDPR special categories: union membership and criminal records are sensitive; genetic data is not explicitly enumerated in the current law (reform would change this).
- Cloudflare's Data Localization Suite can pin D1 to PoPs in São Paulo (GRU), which is the nearest cluster to Argentina. There is no Buenos Aires PoP as of 2026 — confirm acceptable latency with legal counsel.
- The AAIP can investigate on its own motion; external complaints are not required to trigger an audit.

---

## Verification

```bash
# 1. Confirm consent records exist for each sensitive category
wrangler d1 execute DB --command \
  "SELECT category, COUNT(*) AS c FROM argentina_consent_log GROUP BY category;"

# 2. Check for DSR requests past deadline
wrangler d1 execute DB --command \
  "SELECT id, request_type, deadline_at FROM argentina_dsr_requests
   WHERE status NOT IN ('completed','denied')
   AND deadline_at < datetime('now');"

# 3. Verify transfer log has no unauthorised entries
wrangler d1 execute DB --command \
  "SELECT * FROM argentina_transfer_log WHERE allowed = 0;"

# 4. Confirm AAIP registry has at least one entry
wrangler d1 execute DB --command "SELECT COUNT(*) FROM aaip_registry;"
```

---

## Related

- `cross-border-data-transfer-mechanisms.md`
- `data-localization-requirements.md`
- `gdpr-data-subject-rights-api.md`
- `lgpd-brazil-compliance.md`
- `data-retention-automated-deletion-workers.md`

---

## Sources

- Ley 25.326 (Argentina Personal Data Protection Law, 2000): https://www.argentina.gob.ar/normativa/nacional/ley-25326-64790
- AAIP Resolution 47/2018 (cross-border transfer guidelines): https://www.argentina.gob.ar/aaip
- AAIP Cybersecurity Breach Guidance (2023): https://www.argentina.gob.ar/aaip/datospersonales
- Cloudflare Data Localization Suite: https://developers.cloudflare.com/data-localization/
- Cloudflare D1 Documentation: https://developers.cloudflare.com/d1/
