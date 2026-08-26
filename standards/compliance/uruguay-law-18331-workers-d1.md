# Uruguay Law 18.331 (Personal Data Protection) — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform serves users in Uruguay and must comply with **Ley N° 18.331 de Protección de Datos Personales y Acción de Habeas Data** (2008) and its implementing Decree 414/009, regulated by the **Unidad Reguladora y de Control de Datos Personales (URCDP)**. Uruguay holds an EU Commission adequacy decision (since 2012), simplifying EU→UY transfers. This article covers consent management, database registration equivalents, subject-rights handling, and breach notification using Cloudflare Workers, D1, R2, and KV.

## Context

Uruguay Law 18.331 is one of the strongest privacy frameworks in Latin America and the first in the region to earn EU adequacy:

- **Consent (Art. 9)**: Must be free, express, informed, and unequivocal; written or electronic. Can be revoked at any time.
- **Sensitive data (Art. 18)**: Racial origin, political opinions, religion, union membership, health, sexuality — require explicit consent and are subject to heightened restrictions.
- **Database registration (Art. 22)**: All personal data databases must be registered with URCDP before use.
- **Transborder transfers (Art. 23)**: Permitted to adequate countries or with URCDP authorisation; Uruguay is itself adequate for EU purposes.
- **Data subject rights**: Access (habeas data), rectification, deletion, opposition — must be fulfilled within **5 business days**.
- **Breach notification**: No explicit statutory clock, but URCDP guidance recommends notification "without undue delay" (interpreted as ≤ 72 hours for significant incidents).
- **Sanctions**: URCDP can impose fines, suspend database operations, and publish violations.

---

## 1. Database Registration Tracking in KV

```typescript
// src/compliance/uy-db-registry.ts
import type { Env } from "../types";

interface URCDPRegistration {
  registrationNumber: string;
  databaseName: string;
  purposes: string[];
  dataCategories: string[];
  registeredAt: string;
  expiresAt: string; // annual renewal required
}

export async function recordURCDPRegistration(
  reg: URCDPRegistration,
  env: Env
): Promise<void> {
  await env.UY_COMPLIANCE_KV.put(
    `uy:db-reg:${reg.databaseName}`,
    JSON.stringify(reg),
    {
      // Alert before annual expiry; TTL slightly under 1 year so key disappears on lapse
      expirationTtl: 60 * 60 * 24 * 350,
    }
  );
}

export async function assertDatabaseRegistered(
  databaseName: string,
  env: Env
): Promise<void> {
  const reg = await env.UY_COMPLIANCE_KV.get(`uy:db-reg:${databaseName}`);
  if (!reg) {
    throw new Error(
      `UY_URCDP_NOT_REGISTERED: Database "${databaseName}" has no active URCDP registration.`
    );
  }
}
```

---

## 2. Consent Collection and Withdrawal

```typescript
// src/routes/uy-consent.ts
import type { Env } from "../types";

interface UYConsentPayload {
  userId: string;
  email: string;
  purposes: string[];
  sensitiveCategories?: string[]; // requires separate explicit consent
  consentVersion: string;
}

export async function collectUYConsent(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<UYConsentPayload>();

  // Sensitive categories need an explicit, separate flag
  if (body.sensitiveCategories && body.sensitiveCategories.length > 0) {
    const sensitiveFlag = request.headers.get("X-UY-Sensitive-Consent");
    if (sensitiveFlag !== "explicit") {
      return new Response(
        JSON.stringify({ error: "SENSITIVE_CONSENT_REQUIRED" }),
        { status: 422 }
      );
    }
  }

  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO uy_consent_log
       (user_id, email, purposes, sensitive_categories, consent_version, consented_at, withdrawn_at)
     VALUES (?, ?, ?, ?, ?, ?, NULL)
     ON CONFLICT(user_id) DO UPDATE SET
       purposes = excluded.purposes,
       sensitive_categories = excluded.sensitive_categories,
       consent_version = excluded.consent_version,
       consented_at = excluded.consented_at,
       withdrawn_at = NULL`
  )
    .bind(
      body.userId,
      body.email,
      JSON.stringify(body.purposes),
      JSON.stringify(body.sensitiveCategories ?? []),
      body.consentVersion,
      now
    )
    .run();

  return new Response(JSON.stringify({ ok: true, consentedAt: now }), {
    status: 201,
  });
}

export async function withdrawUYConsent(
  userId: string,
  env: Env
): Promise<Response> {
  await env.DB.prepare(
    `UPDATE uy_consent_log SET withdrawn_at = ? WHERE user_id = ?`
  )
    .bind(new Date().toISOString(), userId)
    .run();

  // Stop all non-essential processing
  await env.UY_COMPLIANCE_KV.put(`uy:consent-withdrawn:${userId}`, "1");

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
}
```

---

## 3. Habeas Data Rights Handler (5-Business-Day SLA)

```typescript
// src/routes/uy-dsr.ts
import type { Env } from "../types";

type UYDSRAction = "access" | "rectify" | "delete" | "oppose";

function businessDayDeadline(fromDate: Date, days: number): Date {
  // Simple approximation: add 7 calendar days per 5 business days
  const result = new Date(fromDate);
  result.setDate(result.getDate() + Math.ceil((days * 7) / 5));
  return result;
}

export async function handleUYHabeasData(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, action, correction } = await request.json<{
    userId: string;
    action: UYDSRAction;
    correction?: Record<string, unknown>;
  }>();

  const receivedAt = new Date();
  const respondBy = businessDayDeadline(receivedAt, 5).toISOString();

  // Create DSR ticket
  const ticketId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO uy_dsr_log (ticket_id, user_id, action, received_at, respond_by, status)
     VALUES (?, ?, ?, ?, ?, 'OPEN')`
  )
    .bind(ticketId, userId, action, receivedAt.toISOString(), respondBy)
    .run();

  if (action === "access") {
    const userData = await env.DB.prepare(
      `SELECT * FROM users WHERE id = ?`
    )
      .bind(userId)
      .first();
    await env.DB.prepare(
      `UPDATE uy_dsr_log SET status = 'FULFILLED', fulfilled_at = ? WHERE ticket_id = ?`
    )
      .bind(new Date().toISOString(), ticketId)
      .run();
    return new Response(JSON.stringify({ ticketId, data: userData }), {
      status: 200,
    });
  }

  if (action === "delete") {
    await env.DB.prepare(`DELETE FROM users WHERE id = ?`).bind(userId).run();
    await env.DB.prepare(`DELETE FROM uy_consent_log WHERE user_id = ?`)
      .bind(userId)
      .run();
    await env.DB.prepare(
      `UPDATE uy_dsr_log SET status = 'FULFILLED', fulfilled_at = ? WHERE ticket_id = ?`
    )
      .bind(new Date().toISOString(), ticketId)
      .run();
    return new Response(JSON.stringify({ ticketId, action: "deleted" }), {
      status: 200,
    });
  }

  // Async actions (rectify / oppose) enqueue for manual review
  await env.BREACH_QUEUE.send({ type: "UY_DSR", ticketId, userId, action, correction });
  return new Response(
    JSON.stringify({ ticketId, respondBy, status: "QUEUED" }),
    { status: 202 }
  );
}
```

---

## 4. Transborder Transfer Controls

```typescript
// src/middleware/uy-transborder.ts
import type { Env } from "../types";

// Countries with EU/UY mutual adequacy recognitions (verify current URCDP list)
const ADEQUATE_COUNTRIES = new Set([
  "EU", "GB", "CH", "NO", "IS", "LI", "CA", "NZ", "AR", "BR",
]);

export async function checkUYTransborder(
  destinationCountry: string,
  userId: string,
  env: Env
): Promise<void> {
  if (ADEQUATE_COUNTRIES.has(destinationCountry)) return;

  // Require explicit consent for transfer to non-adequate country
  const consent = await env.DB.prepare(
    `SELECT purposes FROM uy_consent_log
     WHERE user_id = ? AND withdrawn_at IS NULL`
  )
    .bind(userId)
    .first<{ purposes: string }>();

  const purposes: string[] = consent ? JSON.parse(consent.purposes) : [];
  if (!purposes.includes("international_transfer")) {
    throw new Error(
      `UY_TRANSBORDER_BLOCKED: No consent for transfer to ${destinationCountry}`
    );
  }

  await env.DB.prepare(
    `INSERT INTO uy_transfer_log (user_id, destination_country, transferred_at)
     VALUES (?, ?, ?)`
  )
    .bind(userId, destinationCountry, new Date().toISOString())
    .run();
}
```

---

## 5. Incident Reporting to URCDP

```typescript
// src/breach/uy-breach.ts
import type { Env } from "../types";

interface UYBreachRecord {
  incidentId: string;
  affectedSubjects: number;
  dataCategories: string[];
  containsSensitiveData: boolean;
  discoveredAt: string;
  description: string;
}

export async function logUYBreach(
  report: UYBreachRecord,
  env: Env
): Promise<void> {
  // URCDP guidance: notify without undue delay; 72 h benchmark for significant incidents
  const notifyByMs = report.containsSensitiveData || report.affectedSubjects > 500
    ? 72 * 60 * 60 * 1000   // 72 hours for significant incidents
    : 168 * 60 * 60 * 1000; // 7 days for minor incidents

  const notifyBy = new Date(
    new Date(report.discoveredAt).getTime() + notifyByMs
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO uy_breach_log
       (incident_id, affected_subjects, data_categories, contains_sensitive,
        discovered_at, notify_by, status)
     VALUES (?, ?, ?, ?, ?, ?, 'PENDING')`
  )
    .bind(
      report.incidentId,
      report.affectedSubjects,
      JSON.stringify(report.dataCategories),
      report.containsSensitiveData ? 1 : 0,
      report.discoveredAt,
      notifyBy
    )
    .run();

  await env.BREACH_QUEUE.send({
    regulator: "URCDP_UY",
    incidentId: report.incidentId,
    notifyBy,
  });
}
```

---

## Anti-patterns

- **Skipping URCDP database registration** because Uruguay has EU adequacy — adequacy covers transfers, not registration obligations; every operational database must still be registered.
- **Treating withdrawal of consent as immediate deletion** — Law 18.331 separates withdrawal (stops future processing) from the habeas data deletion right (removes stored data); implement both independently.
- **Ignoring sensitive-category heightened rules** — health, political opinion, and religious data require a separate explicit opt-in flag, not just a general consent checkbox.
- **Using the same 72-hour clock for all breaches** — URCDP guidance differentiates; scale the urgency to breach severity and number of affected subjects.

## Gotchas

- Uruguay's adequacy decision with the EU predates the current SCCs framework; transfers from EU to UY do not require additional SCCs, but document this in your ROPA to avoid auditor confusion.
- The "oppose" right (art. 13) covers direct marketing specifically — implement a do-not-contact flag that is checked synchronously before any outbound communication, not just during data processing.
- URCDP can impose database suspension as an interim measure before a final sanction — ensure your architecture can disable a specific user segment's data operations without a full deployment.
- Annual registration renewal is required; use KV TTL expiry alerts (Worker Cron Trigger checking for missing keys) to prompt renewal before lapses.

## Verification

```sql
-- Unregistered databases in use (manual cross-check with KV)
-- Run: wrangler kv key list --namespace-id=<UY_COMPLIANCE_KV> --prefix="uy:db-reg:"

-- Open DSR tickets past their respond_by deadline
SELECT ticket_id, user_id, action, respond_by
FROM uy_dsr_log
WHERE status = 'OPEN' AND respond_by < datetime('now');
-- Expected: 0 rows

-- Users with active consent but withdrawn flag in KV
SELECT c.user_id, c.consented_at
FROM uy_consent_log c
WHERE c.withdrawn_at IS NULL
-- Cross-reference with KV key uy:consent-withdrawn:<user_id>

-- Pending breach reports past notify_by
SELECT incident_id, notify_by
FROM uy_breach_log
WHERE status = 'PENDING' AND notify_by < datetime('now');
-- Expected: 0 rows
```

## Related

- `brazil-lgpd-data-subject-rights-workers-d1.md`
- `argentina-pdpa-data-localization-workers.md`
- `chile-data-protection-bill-workers-d1.md`
- `colombia-habeas-data-workers-d1-compliance.md`
- `peru-lpdp-workers-d1.md`
- `gdpr-dpa-standard-contractual-clauses.md`

## Sources

- Ley N° 18.331 de Protección de Datos Personales y Acción de Habeas Data (2008) — https://www.impo.com.uy/bases/leyes/18331-2008
- Decreto Reglamentario 414/009 — https://www.urcdp.gub.uy
- URCDP (Unidad Reguladora y de Control de Datos Personales) — https://www.gub.uy/unidad-reguladora-control-datos-personales/
- European Commission Uruguay adequacy decision (2012) — https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en
- IAPP Uruguay country profile — https://iapp.org/resources/article/uruguay/
