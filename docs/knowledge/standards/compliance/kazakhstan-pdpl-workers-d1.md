# Kazakhstan Personal Data Protection Law — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You operate a service with users in Kazakhstan and need to comply with the Republic of Kazakhstan Law on Personal Data and Its Protection (No. 94-V, 2013, amended 2021). Kazakhstan mandates **data localization**: personal data of Kazakhstani citizens must be stored in databases physically located in the Republic of Kazakhstan. This article shows how to implement localization gates, cross-border transfer controls, and subject-rights endpoints using Cloudflare Workers, D1, R2, and KV.

## Context

Kazakhstan's personal data law is enforced by the **Committee on Information Security** under the Ministry of Digital Development, Innovation and Aerospace Industry (MDDIA). Key obligations:

- **Article 26**: Personal data of Kazakhstani residents must be recorded, systematised, accumulated, stored, and retrieved using databases physically located in Kazakhstan.
- **Transborder transfer (Article 22)**: Allowed only to countries with "adequate" protection or with explicit consent; requires prior notification to the regulator for transfers to non-adequate countries.
- **Breach notification**: Notify MDDIA and affected subjects within **3 business days**.
- **Operator registration**: Operators collecting personal data must register with MDDIA before processing starts.
- **Consent**: Written (including electronic) consent is required before processing; special categories require explicit consent.
- Cloudflare has no data centre in Kazakhstan; you must run a **primary KZ store** on a Kazakhstani IaaS provider and sync a shadow record to Workers/D1 for processing only after verifying the primary store exists.

---

## 1. Geo-Routing: Detect Kazakhstani Users at the Edge

```typescript
// src/middleware/kz-gate.ts
import type { Env } from "../types";

const KZ_COUNTRY = "KZ";

export function isKazakhUser(request: Request): boolean {
  const country = request.cf?.country as string | undefined;
  return country === KZ_COUNTRY;
}

export async function requireKZLocalStore(
  request: Request,
  env: Env
): Promise<Response | null> {
  if (!isKazakhUser(request)) return null;

  // Confirm the primary KZ store record reference exists in KV
  const url = new URL(request.url);
  const userId = url.searchParams.get("user_id") ?? "";
  if (!userId) return null;

  const kzRef = await env.KZ_LOCALSTORE_KV.get(`kz:ref:${userId}`);
  if (!kzRef) {
    return new Response(
      JSON.stringify({
        error: "KZ_LOCALIZATION_REQUIRED",
        message:
          "Primary data store in Kazakhstan not provisioned for this user.",
      }),
      { status: 451, headers: { "Content-Type": "application/json" } }
    );
  }
  return null; // proceed
}
```

---

## 2. Consent Collection and Storage

```typescript
// src/routes/consent.ts
import type { Env } from "../types";

interface KZConsentRecord {
  userId: string;
  email: string;
  purposes: string[];
  consentedAt: string; // ISO-8601
  ipCountry: string;
  consentVersion: string;
}

export async function handleKZConsent(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    userId: string;
    email: string;
    purposes: string[];
    consentVersion: string;
  }>();

  const country = (request.cf?.country as string) ?? "XX";
  const record: KZConsentRecord = {
    ...body,
    consentedAt: new Date().toISOString(),
    ipCountry: country,
    consentVersion: body.consentVersion,
  };

  // Store consent proof in D1
  const stmt = env.DB.prepare(`
    INSERT INTO kz_consent_log
      (user_id, email, purposes, consented_at, ip_country, consent_version)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
      purposes = excluded.purposes,
      consented_at = excluded.consented_at,
      consent_version = excluded.consent_version
  `);
  await stmt
    .bind(
      record.userId,
      record.email,
      JSON.stringify(record.purposes),
      record.consentedAt,
      record.ipCountry,
      record.consentVersion
    )
    .run();

  // Mark KZ localization reference (points to external KZ IaaS record ID)
  await env.KZ_LOCALSTORE_KV.put(
    `kz:ref:${record.userId}`,
    JSON.stringify({ provisioned: true, consentedAt: record.consentedAt }),
    { expirationTtl: 60 * 60 * 24 * 365 * 5 } // 5 years
  );

  return new Response(JSON.stringify({ ok: true }), { status: 201 });
}
```

---

## 3. Transborder Transfer Gate

```typescript
// src/middleware/transborder.ts
import type { Env } from "../types";

// Kazakhstan MDDIA adequate-country list (illustrative — verify current list)
const ADEQUATE_COUNTRIES = new Set([
  "DE", "FR", "GB", "NL", "SE", "FI", "NO", "CH", "BY", "RU", "KG", "TJ", "UZ", "AM",
]);

export async function enforceTransborderPolicy(
  destinationCountry: string,
  userId: string,
  env: Env
): Promise<void> {
  if (ADEQUATE_COUNTRIES.has(destinationCountry)) return; // allowed

  // Non-adequate country — require explicit consent for transborder transfer
  const row = await env.DB.prepare(
    `SELECT purposes FROM kz_consent_log WHERE user_id = ?`
  )
    .bind(userId)
    .first<{ purposes: string }>();

  if (!row) throw new Error("KZ_TRANSBORDER_NO_CONSENT");

  const purposes: string[] = JSON.parse(row.purposes);
  if (!purposes.includes("transborder_transfer")) {
    throw new Error("KZ_TRANSBORDER_CONSENT_MISSING");
  }
  // Log the transfer for MDDIA audit
  await env.DB.prepare(
    `INSERT INTO kz_transfer_log (user_id, destination_country, transferred_at)
     VALUES (?, ?, ?)`
  )
    .bind(userId, destinationCountry, new Date().toISOString())
    .run();
}
```

---

## 4. Breach Notification (3-Business-Day Window)

```typescript
// src/breach/kz-notify.ts
import type { Env } from "../types";

export interface KZBreachReport {
  incidentId: string;
  affectedCount: number;
  dataCategories: string[];
  discoveredAt: string;
  description: string;
}

export async function createKZBreachRecord(
  report: KZBreachReport,
  env: Env
): Promise<void> {
  const deadlineMs = 3 * 24 * 60 * 60 * 1000; // 3 business days ≈ 72 h business time
  const notifyByIso = new Date(
    new Date(report.discoveredAt).getTime() + deadlineMs
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO kz_breach_log
       (incident_id, affected_count, data_categories, discovered_at, notify_by, status)
     VALUES (?, ?, ?, ?, ?, 'PENDING')`
  )
    .bind(
      report.incidentId,
      report.affectedCount,
      JSON.stringify(report.dataCategories),
      report.discoveredAt,
      notifyByIso
    )
    .run();

  // Enqueue MDDIA notification job
  await env.BREACH_QUEUE.send({
    regulator: "MDDIA_KZ",
    incidentId: report.incidentId,
    notifyBy: notifyByIso,
  });
}
```

---

## 5. Data Subject Rights Endpoint

```typescript
// src/routes/dsr-kz.ts
import type { Env } from "../types";

export async function handleKZDSR(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, action } = await request.json<{
    userId: string;
    action: "access" | "delete" | "restrict";
  }>();

  if (action === "delete") {
    // Delete from D1
    await env.DB.prepare(`DELETE FROM users WHERE id = ? AND country = 'KZ'`)
      .bind(userId)
      .run();
    await env.DB.prepare(`DELETE FROM kz_consent_log WHERE user_id = ?`)
      .bind(userId)
      .run();
    // Remove KV localization reference
    await env.KZ_LOCALSTORE_KV.delete(`kz:ref:${userId}`);
    // Instruct KZ IaaS primary store deletion via queue
    await env.BREACH_QUEUE.send({ action: "KZ_PRIMARY_DELETE", userId });
    return new Response(JSON.stringify({ ok: true, action: "deleted" }), { status: 200 });
  }

  if (action === "access") {
    const row = await env.DB.prepare(
      `SELECT * FROM users WHERE id = ? AND country = 'KZ'`
    )
      .bind(userId)
      .first();
    return new Response(JSON.stringify({ data: row }), { status: 200 });
  }

  return new Response(JSON.stringify({ error: "unsupported_action" }), { status: 400 });
}
```

---

## Anti-patterns

- **Storing KZ citizen data only in Cloudflare D1 without a Kazakhstan-resident primary store** — this violates Article 26 localisation regardless of any contractual arrangement.
- **Using IP geolocation alone** to determine residency — citizenship/registration determines KZ data subject status, not current IP. Collect residency declaration at sign-up.
- **Assuming Russia's adequate-country status is permanent** — the list changes; hard-code adequate countries in KV/D1 so it can be updated without a deployment.
- **Missing the 3-business-day breach window** — do not conflate with GDPR's 72-calendar-hour rule; Kazakhstan counts business days.

## Gotchas

- Kazakhstan uses both Cyrillic and Latin scripts in official documents; store names in both forms where provided to avoid mismatches during regulator audits.
- The 2021 amendments added requirements for operators processing biometric data to register separate databases — maintain a distinct D1 table per category.
- MDDIA can conduct on-site inspections of the primary database infrastructure; Cloudflare's infrastructure cannot satisfy this — the KZ IaaS contract must explicitly grant regulator inspection rights.
- Operator registration (before first collection) is a precondition; starting collection before registration risks fines of up to 500 Monthly Calculation Indices (MCI).

## Verification

```sql
-- Confirm consent records exist for all KZ users
SELECT u.id, u.email, k.consented_at, k.purposes
FROM users u
LEFT JOIN kz_consent_log k ON k.user_id = u.id
WHERE u.country = 'KZ' AND k.user_id IS NULL;
-- Expected: 0 rows

-- Check open breach notifications past their notify_by deadline
SELECT incident_id, notify_by, status
FROM kz_breach_log
WHERE status = 'PENDING' AND notify_by < datetime('now');
-- Expected: 0 rows

-- Verify KZ localization references in KV (run via Wrangler)
-- wrangler kv key list --namespace-id=<KZ_LOCALSTORE_KV_ID> --prefix="kz:ref:"
```

## Related

- `russia-federal-law-152-workers-d1-compliance.md`
- `uzbekistan-pdpl` (not yet published)
- `cross-border-data-transfer-cloudflare-workers.md`
- `data-localization-requirements.md`
- `audit-log-mandatory.md`

## Sources

- Law of the Republic of Kazakhstan No. 94-V "On Personal Data and Its Protection" (21 May 2013, amended 2021) — adilet.zan.kz
- MDDIA Committee on Information Security guidance — https://www.gov.kz/memleket/entities/mdai
- Cloudflare network map (no KZ PoP as data store) — https://www.cloudflare.com/network/
- IAPP Kazakhstan country profile — https://iapp.org/resources/article/kazakhstan/
