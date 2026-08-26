# Sri Lanka Personal Data Protection Act 2022 — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You operate a service with users in Sri Lanka and must comply with the **Personal Data Protection Act No. 9 of 2022 (PDPA)**. The Act is enforced by the **Data Protection Authority of Sri Lanka (DPASL)**, which was formally established in 2023 with rules phased in through 2024–2026. This article covers consent architecture, cross-border transfer controls, Data Protection Impact Assessments (DPIAs), subject-rights fulfilment, and breach notification using Cloudflare Workers, D1, R2, and KV.

## Context

Sri Lanka's PDPA follows a GDPR-influenced model with local adaptations:

- **Lawful bases (Sec. 5)**: Consent, contract performance, legal obligation, vital interests, public task, legitimate interests — consent remains the default for commercial processing.
- **Sensitive personal data (Sec. 3)**: Race, ethnicity, political opinion, religion, trade union membership, health, biometric data, sexual orientation — heightened requirements.
- **Data subject rights**: Access (30 days), rectification, erasure, restriction, portability, objection.
- **DPO requirement**: Controllers whose core activities involve large-scale systematic monitoring or large-scale processing of sensitive data must appoint a DPO.
- **Cross-border transfers (Sec. 28)**: Only to countries with DPASL-assessed adequate protection, or with safeguards (standard clauses, BCRs), or consent. DPASL publishes an approved-country list.
- **Breach notification (Sec. 33)**: Notify DPASL within **72 hours** of becoming aware; notify data subjects "without undue delay" when high risk.
- **Penalties**: Up to LKR 10 million (controller) or LKR 2 million (processor) per violation; criminal liability for wilful violations.

---

## 1. Lawful Basis Registry in D1

```typescript
// src/compliance/lk-lawful-basis.ts
import type { Env } from "../types";

type LKLawfulBasis =
  | "consent"
  | "contract"
  | "legal_obligation"
  | "vital_interests"
  | "public_task"
  | "legitimate_interests";

interface LKProcessingRecord {
  processingId: string;
  purpose: string;
  lawfulBasis: LKLawfulBasis;
  dataCategories: string[];
  isSensitive: boolean;
  legitimateInterestAssessment?: string; // URL or document ID for LIA
  createdAt: string;
}

export async function registerLKProcessing(
  record: LKProcessingRecord,
  env: Env
): Promise<void> {
  if (record.isSensitive && record.lawfulBasis !== "consent" && record.lawfulBasis !== "vital_interests") {
    throw new Error(
      "LK_PDPA: Sensitive personal data requires explicit consent or vital interest basis."
    );
  }

  await env.DB.prepare(
    `INSERT OR REPLACE INTO lk_processing_activities
       (processing_id, purpose, lawful_basis, data_categories, is_sensitive,
        lia_document, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      record.processingId,
      record.purpose,
      record.lawfulBasis,
      JSON.stringify(record.dataCategories),
      record.isSensitive ? 1 : 0,
      record.legitimateInterestAssessment ?? null,
      record.createdAt
    )
    .run();
}
```

---

## 2. Consent Management for Sri Lankan Users

```typescript
// src/routes/lk-consent.ts
import type { Env } from "../types";

const LK_COUNTRY = "LK";

export function isSriLankanUser(request: Request): boolean {
  return (request.cf?.country as string) === LK_COUNTRY;
}

interface LKConsentBody {
  userId: string;
  email: string;
  purposes: string[];
  sensitiveConsent?: boolean; // must be true for sensitive-data processing
  consentVersion: string;
}

export async function collectLKConsent(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<LKConsentBody>();
  const consentedAt = new Date().toISOString();

  // Validate sensitive consent flag
  const sensitiveActivities = await env.DB.prepare(
    `SELECT COUNT(*) as cnt FROM lk_processing_activities
     WHERE is_sensitive = 1 AND processing_id IN (
       SELECT value FROM json_each(?)
     )`
  )
    .bind(JSON.stringify(body.purposes))
    .first<{ cnt: number }>();

  if ((sensitiveActivities?.cnt ?? 0) > 0 && !body.sensitiveConsent) {
    return new Response(
      JSON.stringify({ error: "LK_SENSITIVE_CONSENT_REQUIRED" }),
      { status: 422 }
    );
  }

  await env.DB.prepare(
    `INSERT INTO lk_consent_log
       (user_id, email, purposes, sensitive_consent, consent_version, consented_at)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       purposes = excluded.purposes,
       sensitive_consent = excluded.sensitive_consent,
       consent_version = excluded.consent_version,
       consented_at = excluded.consented_at,
       withdrawn_at = NULL`
  )
    .bind(
      body.userId,
      body.email,
      JSON.stringify(body.purposes),
      body.sensitiveConsent ? 1 : 0,
      body.consentVersion,
      consentedAt
    )
    .run();

  return new Response(JSON.stringify({ ok: true, consentedAt }), { status: 201 });
}
```

---

## 3. Cross-Border Transfer Enforcement

```typescript
// src/middleware/lk-transborder.ts
import type { Env } from "../types";

// DPASL-approved adequate countries (indicative — check DPASL official list)
const LK_ADEQUATE_COUNTRIES = new Set([
  "DE", "FR", "GB", "NL", "SE", "FI", "NO", "CH", "AU", "NZ", "CA", "JP", "SG",
]);

export async function enforceLKTransborder(
  destinationCountry: string,
  userId: string,
  env: Env
): Promise<void> {
  if (LK_ADEQUATE_COUNTRIES.has(destinationCountry)) return;

  // Check for consent-based transfer authorisation
  const consent = await env.DB.prepare(
    `SELECT purposes FROM lk_consent_log
     WHERE user_id = ? AND withdrawn_at IS NULL`
  )
    .bind(userId)
    .first<{ purposes: string }>();

  const purposes: string[] = consent ? JSON.parse(consent.purposes) : [];
  if (!purposes.includes("cross_border_transfer")) {
    throw new Error(
      `LK_TRANSBORDER_BLOCKED: No safeguard or consent for transfer to ${destinationCountry}`
    );
  }

  // Log the transfer for DPASL audit readiness
  await env.DB.prepare(
    `INSERT INTO lk_transfer_log (user_id, destination_country, safeguard, transferred_at)
     VALUES (?, ?, 'consent', ?)`
  )
    .bind(userId, destinationCountry, new Date().toISOString())
    .run();
}
```

---

## 4. Data Subject Rights (30-Day Response SLA)

```typescript
// src/routes/lk-dsr.ts
import type { Env } from "../types";

type LKRightAction = "access" | "rectify" | "erase" | "restrict" | "portability" | "object";

export async function handleLKSubjectRight(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, action, payload } = await request.json<{
    userId: string;
    action: LKRightAction;
    payload?: Record<string, unknown>;
  }>();

  const receivedAt = new Date();
  const respondBy = new Date(receivedAt.getTime() + 30 * 24 * 60 * 60 * 1000).toISOString();
  const ticketId = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO lk_dsr_log (ticket_id, user_id, action, received_at, respond_by, status)
     VALUES (?, ?, ?, ?, ?, 'OPEN')`
  )
    .bind(ticketId, userId, action, receivedAt.toISOString(), respondBy)
    .run();

  switch (action) {
    case "access": {
      const userData = await env.DB.prepare(`SELECT * FROM users WHERE id = ?`)
        .bind(userId)
        .first();
      const consentData = await env.DB.prepare(
        `SELECT * FROM lk_consent_log WHERE user_id = ?`
      )
        .bind(userId)
        .first();
      await closeDSR(ticketId, env);
      return new Response(
        JSON.stringify({ ticketId, data: { user: userData, consent: consentData } }),
        { status: 200 }
      );
    }
    case "erase": {
      await env.DB.prepare(`DELETE FROM users WHERE id = ?`).bind(userId).run();
      await env.DB.prepare(`DELETE FROM lk_consent_log WHERE user_id = ?`)
        .bind(userId)
        .run();
      // Purge R2 objects (profile images, exports)
      const r2List = await env.USER_BUCKET.list({ prefix: `users/${userId}/` });
      await Promise.all(r2List.objects.map((o) => env.USER_BUCKET.delete(o.key)));
      await closeDSR(ticketId, env);
      return new Response(JSON.stringify({ ticketId, action: "erased" }), { status: 200 });
    }
    case "portability": {
      const rows = await env.DB.prepare(`SELECT * FROM users WHERE id = ?`)
        .bind(userId)
        .all();
      const json = JSON.stringify(rows.results, null, 2);
      await env.USER_BUCKET.put(`exports/lk/${userId}/${ticketId}.json`, json, {
        httpMetadata: { contentType: "application/json" },
      });
      const exportUrl = await env.USER_BUCKET.createPresignedUrl
        ? `Stored at exports/lk/${userId}/${ticketId}.json`
        : `exports/lk/${userId}/${ticketId}.json`;
      await closeDSR(ticketId, env);
      return new Response(JSON.stringify({ ticketId, exportPath: exportUrl }), { status: 200 });
    }
    default:
      await env.BREACH_QUEUE.send({ type: "LK_DSR", ticketId, userId, action, payload });
      return new Response(JSON.stringify({ ticketId, respondBy, status: "QUEUED" }), {
        status: 202,
      });
  }
}

async function closeDSR(ticketId: string, env: Env): Promise<void> {
  await env.DB.prepare(
    `UPDATE lk_dsr_log SET status = 'FULFILLED', fulfilled_at = ? WHERE ticket_id = ?`
  )
    .bind(new Date().toISOString(), ticketId)
    .run();
}
```

---

## 5. 72-Hour Breach Notification to DPASL

```typescript
// src/breach/lk-breach.ts
import type { Env } from "../types";

export interface LKBreachEvent {
  incidentId: string;
  affectedCount: number;
  containsSensitiveData: boolean;
  dataCategories: string[];
  discoveredAt: string;
  description: string;
}

export async function recordLKBreach(
  event: LKBreachEvent,
  env: Env
): Promise<void> {
  const notifyDPASLBy = new Date(
    new Date(event.discoveredAt).getTime() + 72 * 60 * 60 * 1000
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO lk_breach_log
       (incident_id, affected_count, contains_sensitive, data_categories,
        discovered_at, dpasl_notify_by, subject_notification_required, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')`
  )
    .bind(
      event.incidentId,
      event.affectedCount,
      event.containsSensitiveData ? 1 : 0,
      JSON.stringify(event.dataCategories),
      event.discoveredAt,
      notifyDPASLBy,
      event.containsSensitiveData || event.affectedCount > 100 ? 1 : 0
    )
    .run();

  await env.BREACH_QUEUE.send({
    regulator: "DPASL_LK",
    incidentId: event.incidentId,
    notifyDPASLBy,
  });
}
```

---

## Anti-patterns

- **Conflating Sri Lanka's 30-day DSR deadline with GDPR's 30-day calendar-day clock** — the PDPA deadline is calendar days, not business days; start the clock at time of receipt.
- **Processing sensitive data under legitimate interests** — the Act restricts sensitive personal data to consent or vital interests only; legitimate interests is not an available basis.
- **Omitting a DPO appointment** when running analytics at scale on LK user data — if your core activity involves systematic monitoring of individuals at scale, a DPO is mandatory.
- **Using a shared consent record across jurisdictions without a country flag** — DPASL may audit consent records; ensure LK consent records are distinguishable from other regional records.

## Gotchas

- The DPASL phased implementation means some obligations (e.g., mandatory DPIA thresholds) may be enacted by regulatory notice after the Act's commencement — subscribe to DPASL notices.
- Sri Lanka uses a Sinhala and Tamil language base; privacy notices served to LK users should be available in both languages alongside English to satisfy the "informed" consent standard.
- PDPA Sec. 28 transfer rules do not yet have a published adequate-country list as of mid-2026 — in the interim, obtain explicit consent for all non-local transfers and document this approach.
- Cloudflare's nearest PoPs for LK traffic are Singapore and Mumbai; data processed in those PoPs still routes through Cloudflare's network, which counts as a cross-border transfer.

## Verification

```sql
-- DSR tickets approaching 30-day deadline without fulfilment
SELECT ticket_id, user_id, action, respond_by
FROM lk_dsr_log
WHERE status = 'OPEN'
  AND respond_by < datetime('now', '+2 days');
-- Expected: 0 rows (investigate any matches immediately)

-- Sensitive processing activities without explicit consent basis
SELECT pa.processing_id, pa.purpose
FROM lk_processing_activities pa
WHERE pa.is_sensitive = 1
  AND pa.lawful_basis NOT IN ('consent', 'vital_interests');
-- Expected: 0 rows

-- Breach notifications past 72-hour DPASL window
SELECT incident_id, dpasl_notify_by, status
FROM lk_breach_log
WHERE status = 'PENDING'
  AND dpasl_notify_by < datetime('now');
-- Expected: 0 rows
```

## Related

- `india-dpdp-rules-2025-compliance.md`
- `singapore-pdpa-workers-d1.md`
- `malaysia-pdpa-2010-workers.md`
- `philippines-dpa-workers-d1.md`
- `indonesia-pdp-law-workers-d1.md`
- `gdpr-data-subject-rights-api.md`

## Sources

- Personal Data Protection Act No. 9 of 2022 (Sri Lanka) — https://www.parliament.lk/uploads/documents/paperspresented/personal-data-protection-bill-e.pdf
- Data Protection Authority of Sri Lanka (DPASL) — https://www.pdpa.gov.lk/
- IAPP Sri Lanka country profile — https://iapp.org/resources/article/sri-lanka/
- Ministry of Technology, Sri Lanka — commencement gazettes 2023–2024
