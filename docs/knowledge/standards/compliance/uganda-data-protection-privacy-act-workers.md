# Uganda Data Protection and Privacy Act 2019 — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform has users in Uganda and must comply with the **Data Protection and Privacy Act 2019 (DPPA)** and its **Data Protection and Privacy Regulations 2021**. The Act is administered by the **Personal Data Protection Office (PDPO)** under the National Information Technology Authority – Uganda (NITA-U). This article covers collector registration, consent flows, cross-border transfer controls, subject rights handling, and breach notification using Cloudflare Workers, D1, R2, and KV.

## Context

Uganda's DPPA is the first comprehensive data protection law in East Africa and draws on the EU GDPR framework:

- **Data collector/processor registration (Sec. 23, Reg. 4)**: Every data collector and processor must register with PDPO before commencing operations. Registration must be renewed annually.
- **Consent (Sec. 13)**: Must be informed, voluntary, specific, and unambiguous. Withdrawal must be as easy as granting.
- **Sensitive personal data (Sec. 2)**: Race, political opinion, religion, health, sexuality, criminal record — requires explicit consent unless statutory exception applies.
- **Cross-border transfers (Sec. 19)**: Only to countries with adequate protection as determined by the PDPO, or with consent, or contractual safeguards.
- **Data subject rights (Sec. 12–18)**: Access, rectification, erasure, objection, portability — must be fulfilled within **21 days**.
- **Breach notification (Reg. 18)**: Notify PDPO within **48 hours** of a breach; notify affected subjects where risk of harm is high.
- **Penalties**: UGX 250,000 (individual) to UGX 2,000,000 (company) per violation; criminal fines up to UGX 5,000,000 or 3 years imprisonment for wilful breach.

---

## 1. Collector/Processor Registration Tracking

```typescript
// src/compliance/ug-registration.ts
import type { Env } from "../types";

interface UGPDPORegistration {
  registrationNumber: string;
  registrationType: "collector" | "processor" | "both";
  entityName: string;
  registeredAt: string;
  expiresAt: string; // annual renewal
  dpoContact: string;
}

export async function storeUGRegistration(
  reg: UGPDPORegistration,
  env: Env
): Promise<void> {
  await env.UG_COMPLIANCE_KV.put(
    "ug:pdpo-registration",
    JSON.stringify(reg),
    // Alert ~2 weeks before expiry by setting TTL slightly under 350 days
    { expirationTtl: 60 * 60 * 24 * 350 }
  );

  await env.DB.prepare(
    `INSERT OR REPLACE INTO ug_registration_log
       (reg_number, reg_type, entity_name, registered_at, expires_at, dpo_contact)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(
      reg.registrationNumber,
      reg.registrationType,
      reg.entityName,
      reg.registeredAt,
      reg.expiresAt,
      reg.dpoContact
    )
    .run();
}

export async function assertUGRegistrationValid(env: Env): Promise<void> {
  const reg = await env.UG_COMPLIANCE_KV.get("ug:pdpo-registration");
  if (!reg) {
    throw new Error(
      "UG_DPPA: No active PDPO registration found. " +
        "Operations must cease until registration is renewed."
    );
  }
  const parsed: UGPDPORegistration = JSON.parse(reg);
  if (new Date(parsed.expiresAt) < new Date()) {
    throw new Error(`UG_DPPA: PDPO registration expired at ${parsed.expiresAt}.`);
  }
}
```

---

## 2. Consent Collection and Withdrawal

```typescript
// src/routes/ug-consent.ts
import type { Env } from "../types";

const UG_COUNTRY = "UG";

interface UGConsentBody {
  userId: string;
  email: string;
  purposes: string[];
  sensitiveCategories?: string[];
  consentVersion: string;
}

export function isUgandanUser(request: Request): boolean {
  return (request.cf?.country as string) === UG_COUNTRY;
}

export async function collectUGConsent(
  request: Request,
  env: Env
): Promise<Response> {
  // Verify registration before any data collection
  await assertUGRegistrationValid(env);

  const body = await request.json<UGConsentBody>();

  // Sensitive data requires a separate explicit consent signal
  if (body.sensitiveCategories && body.sensitiveCategories.length > 0) {
    const explicitHeader = request.headers.get("X-UG-Explicit-Consent");
    if (explicitHeader !== "true") {
      return new Response(
        JSON.stringify({ error: "UG_SENSITIVE_EXPLICIT_CONSENT_REQUIRED" }),
        { status: 422 }
      );
    }
  }

  const consentedAt = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO ug_consent_log
       (user_id, email, purposes, sensitive_categories, consent_version, consented_at)
     VALUES (?, ?, ?, ?, ?, ?)
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
      consentedAt
    )
    .run();

  return new Response(JSON.stringify({ ok: true, consentedAt }), { status: 201 });
}

async function assertUGRegistrationValid(env: Env): Promise<void> {
  const reg = await env.UG_COMPLIANCE_KV.get("ug:pdpo-registration");
  if (!reg) throw new Error("UG_DPPA: PDPO registration missing.");
}

export async function withdrawUGConsent(userId: string, env: Env): Promise<Response> {
  await env.DB.prepare(
    `UPDATE ug_consent_log SET withdrawn_at = ? WHERE user_id = ?`
  )
    .bind(new Date().toISOString(), userId)
    .run();
  await env.UG_COMPLIANCE_KV.put(`ug:consent-withdrawn:${userId}`, "1");
  return new Response(JSON.stringify({ ok: true }), { status: 200 });
}
```

---

## 3. Cross-Border Transfer Controls

```typescript
// src/middleware/ug-transborder.ts
import type { Env } from "../types";

// Countries with PDPO-recognised adequate protection (illustrative — verify PDPO list)
const UG_ADEQUATE_COUNTRIES = new Set([
  "KE", "TZ", "RW", "ZA", "NG", "GH", // EAC + African Union members with laws
  "DE", "FR", "GB", "NL", "SE",        // EU/EEA
  "AU", "NZ", "CA", "JP",
]);

export async function enforceUGTransborder(
  destinationCountry: string,
  userId: string,
  env: Env
): Promise<void> {
  if (UG_ADEQUATE_COUNTRIES.has(destinationCountry)) return;

  const consent = await env.DB.prepare(
    `SELECT purposes FROM ug_consent_log
     WHERE user_id = ? AND withdrawn_at IS NULL`
  )
    .bind(userId)
    .first<{ purposes: string }>();

  const purposes: string[] = consent ? JSON.parse(consent.purposes) : [];
  if (!purposes.includes("international_transfer")) {
    throw new Error(
      `UG_TRANSBORDER_BLOCKED: No consent or safeguard for transfer to ${destinationCountry}`
    );
  }

  await env.DB.prepare(
    `INSERT INTO ug_transfer_log (user_id, destination_country, basis, transferred_at)
     VALUES (?, ?, 'consent', ?)`
  )
    .bind(userId, destinationCountry, new Date().toISOString())
    .run();
}
```

---

## 4. Data Subject Rights (21-Day SLA)

```typescript
// src/routes/ug-dsr.ts
import type { Env } from "../types";

type UGRightAction = "access" | "rectify" | "erase" | "object" | "portability";

export async function handleUGSubjectRight(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, action, updates } = await request.json<{
    userId: string;
    action: UGRightAction;
    updates?: Record<string, unknown>;
  }>();

  const receivedAt = new Date();
  // DPPA: 21 calendar days
  const respondBy = new Date(
    receivedAt.getTime() + 21 * 24 * 60 * 60 * 1000
  ).toISOString();
  const ticketId = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO ug_dsr_log (ticket_id, user_id, action, received_at, respond_by, status)
     VALUES (?, ?, ?, ?, ?, 'OPEN')`
  )
    .bind(ticketId, userId, action, receivedAt.toISOString(), respondBy)
    .run();

  switch (action) {
    case "access": {
      const [user, consent, transfers] = await Promise.all([
        env.DB.prepare(`SELECT * FROM users WHERE id = ?`).bind(userId).first(),
        env.DB.prepare(`SELECT * FROM ug_consent_log WHERE user_id = ?`).bind(userId).first(),
        env.DB.prepare(`SELECT * FROM ug_transfer_log WHERE user_id = ?`).bind(userId).all(),
      ]);
      await fulfillDSR(ticketId, env);
      return new Response(
        JSON.stringify({ ticketId, data: { user, consent, transfers: transfers.results } }),
        { status: 200 }
      );
    }
    case "erase": {
      await env.DB.prepare(`DELETE FROM users WHERE id = ?`).bind(userId).run();
      await env.DB.prepare(`DELETE FROM ug_consent_log WHERE user_id = ?`).bind(userId).run();
      const r2Objects = await env.USER_BUCKET.list({ prefix: `users/${userId}/` });
      await Promise.all(r2Objects.objects.map((o) => env.USER_BUCKET.delete(o.key)));
      await env.UG_COMPLIANCE_KV.delete(`ug:consent-withdrawn:${userId}`);
      await fulfillDSR(ticketId, env);
      return new Response(JSON.stringify({ ticketId, action: "erased" }), { status: 200 });
    }
    default:
      await env.BREACH_QUEUE.send({ type: "UG_DSR", ticketId, userId, action, updates });
      return new Response(
        JSON.stringify({ ticketId, respondBy, status: "QUEUED" }),
        { status: 202 }
      );
  }
}

async function fulfillDSR(ticketId: string, env: Env): Promise<void> {
  await env.DB.prepare(
    `UPDATE ug_dsr_log SET status = 'FULFILLED', fulfilled_at = ? WHERE ticket_id = ?`
  )
    .bind(new Date().toISOString(), ticketId)
    .run();
}
```

---

## 5. 48-Hour Breach Notification to PDPO

```typescript
// src/breach/ug-breach.ts
import type { Env } from "../types";

export interface UGBreachEvent {
  incidentId: string;
  affectedCount: number;
  containsSensitiveData: boolean;
  dataCategories: string[];
  discoveredAt: string;
  mitigationActions: string[];
}

export async function recordUGBreach(
  event: UGBreachEvent,
  env: Env
): Promise<void> {
  // DPPA Reg. 18: notify PDPO within 48 hours
  const notifyPDPOBy = new Date(
    new Date(event.discoveredAt).getTime() + 48 * 60 * 60 * 1000
  ).toISOString();

  // Notify subjects if high risk (sensitive data or large scale)
  const subjectNotificationRequired =
    event.containsSensitiveData || event.affectedCount > 200;

  await env.DB.prepare(
    `INSERT INTO ug_breach_log
       (incident_id, affected_count, contains_sensitive, data_categories,
        discovered_at, pdpo_notify_by, subject_notification_required,
        mitigation_actions, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')`
  )
    .bind(
      event.incidentId,
      event.affectedCount,
      event.containsSensitiveData ? 1 : 0,
      JSON.stringify(event.dataCategories),
      event.discoveredAt,
      notifyPDPOBy,
      subjectNotificationRequired ? 1 : 0,
      JSON.stringify(event.mitigationActions)
    )
    .run();

  await env.BREACH_QUEUE.send({
    regulator: "PDPO_UG",
    incidentId: event.incidentId,
    notifyPDPOBy,
    subjectNotificationRequired,
  });
}
```

---

## Anti-patterns

- **Starting data collection before PDPO registration is confirmed** — Sec. 23 makes registration a precondition; fines apply from the first collection, not just after a breach.
- **Relying on "legitimate interests" for any processing** — the Ugandan DPPA does not enumerate legitimate interests as a standalone lawful basis in the same way as GDPR; default to consent.
- **Setting the breach notification clock to 72 hours (GDPR habit)** — Uganda mandates 48 hours to PDPO; missing this by 24 hours due to confusion is a reportable violation.
- **Accepting a single consent checkbox that covers both regular and sensitive data** — sensitive categories must have a clearly separate, explicit opt-in mechanism with distinct visual treatment.

## Gotchas

- Uganda's PDPO can conduct investigations on its own motion — even without a complaint — if a breach is reported in media; ensure your response process includes a media-monitoring trigger.
- The 21-day DSR response clock includes weekends and public holidays; there is no business-day carve-out in the Regulations.
- Registration renewal is annual; KV key expiry (350 days) provides a soft alert but your Cron Trigger should proactively verify the expiry date stored in D1 and alert via queue 30 days out.
- Data processors (not just collectors) must independently register; if you act as a processor for a Ugandan controller, you share registration obligations.
- Cloudflare's Nairobi PoP routes UG traffic; data egress from Nairobi to EU PoPs for processing is a transborder transfer requiring documentation.

## Verification

```sql
-- DSR tickets nearing 21-day deadline
SELECT ticket_id, user_id, action, respond_by
FROM ug_dsr_log
WHERE status = 'OPEN'
  AND respond_by < datetime('now', '+3 days');
-- Expected: 0 rows

-- Breach reports past 48-hour PDPO window
SELECT incident_id, pdpo_notify_by
FROM ug_breach_log
WHERE status = 'PENDING'
  AND pdpo_notify_by < datetime('now');
-- Expected: 0 rows

-- Verify registration KV key exists
-- wrangler kv key get --namespace-id=<UG_COMPLIANCE_KV> "ug:pdpo-registration"

-- Users without consent records
SELECT u.id, u.email
FROM users u
LEFT JOIN ug_consent_log c ON c.user_id = u.id
WHERE u.country = 'UG' AND c.user_id IS NULL;
-- Expected: 0 rows
```

## Related

- `kenya-data-protection-act-workers-d1.md`
- `nigeria-ndpr-workers-d1.md`
- `ghana-data-protection-act-workers-d1-compliance.md`
- `south-africa-popia-workers-d1.md`
- `audit-log-mandatory.md`
- `cross-border-data-transfer-cloudflare-workers.md`

## Sources

- Data Protection and Privacy Act 2019 (Uganda) — Act No. 9 of 2019 — https://www.ulii.org/ug/legislation/act/2019/9/
- Data Protection and Privacy Regulations 2021 — Statutory Instrument No. 2 of 2021
- NITA-Uganda / Personal Data Protection Office — https://www.nita.go.ug/
- IAPP Uganda country profile — https://iapp.org/resources/article/uganda/
- African Union Convention on Cyber Security and Personal Data Protection (Malabo Convention) context
