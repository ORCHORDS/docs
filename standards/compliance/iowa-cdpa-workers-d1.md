# Iowa Consumer Data Protection Act (CDPA) — Cloudflare Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your platform serves consumers in Iowa and must comply with the **Iowa Consumer Data Protection Act (SF 262, enacted March 2023, effective January 1, 2025)**. Iowa's CDPA is enforced exclusively by the **Iowa Attorney General** with no private right of action. The law is one of the more controller-friendly US state privacy laws (closer to Virginia VCDPA than Colorado CPA), with no data minimisation obligation and an opt-out (rather than opt-in) model for data sales and targeted advertising. This article covers controller obligations, opt-out processing, sensitive-data consent, and data subject rights using Cloudflare Workers, D1, and KV.

## Context

Key Iowa CDPA provisions:

- **Applicability**: Controllers that (a) conduct business in Iowa or produce products/services targeted to Iowa residents AND either (b) process personal data of 100,000+ Iowa consumers annually, or (c) process data of 25,000+ Iowa consumers AND derive >50% of gross revenue from selling personal data.
- **No data minimisation or purpose limitation obligations** — unlike Colorado/Connecticut CDPAs.
- **Sensitive data (Sec. 715D.2)**: Racial/ethnic origin, religious beliefs, mental/physical health diagnosis, sexuality, citizenship/immigration status, biometrics, genetic data, precise geolocation, and children's data. Sensitive processing requires **opt-in consent**.
- **Opt-out rights (Sec. 715D.4)**: Consumers can opt out of (1) sale of personal data and (2) processing for targeted advertising. No opt-out for profiling.
- **No right to correct/rectify** — Iowa is notably absent from including a correction right.
- **DSR response time**: **90 days** (extendable by 45 days with notice); far longer than GDPR.
- **Breach notification**: Governed separately by Iowa Code Ch. 715C (within 30 to 45 days depending on scope).
- **Cure period**: 90-day cure opportunity before AG enforcement; no cure available for repeat violations.

---

## 1. Applicability Check at the Edge

```typescript
// src/middleware/ia-gate.ts
import type { Env } from "../types";

const IA_STATE = "IA";
const IA_COUNTRY = "US";

export function isIowaConsumer(request: Request): boolean {
  const country = request.cf?.country as string | undefined;
  const region = request.cf?.region as string | undefined;
  return country === IA_COUNTRY && region === IA_STATE;
}

export async function incrementIAConsumerCount(
  userId: string,
  env: Env
): Promise<void> {
  // Track unique Iowa consumers per calendar year for applicability threshold
  const year = new Date().getFullYear().toString();
  const key = `ia:consumers:${year}`;
  const existing = await env.IA_PRIVACY_KV.get(key, "json") as Set<string> | null;
  const set: Set<string> = existing ? new Set(existing as unknown as string[]) : new Set();
  set.add(userId);
  await env.IA_PRIVACY_KV.put(key, JSON.stringify([...set]), {
    expirationTtl: 60 * 60 * 24 * 400, // keep 13 months for cross-year audit
  });
}

export async function checkIACDPAApplicability(env: Env): Promise<{
  applicable: boolean;
  uniqueConsumers: number;
}> {
  const year = new Date().getFullYear().toString();
  const data = await env.IA_PRIVACY_KV.get(`ia:consumers:${year}`, "json") as string[] | null;
  const uniqueConsumers = data ? data.length : 0;
  return {
    applicable: uniqueConsumers >= 100_000,
    uniqueConsumers,
  };
}
```

---

## 2. Sensitive Data Opt-In Consent

```typescript
// src/routes/ia-consent.ts
import type { Env } from "../types";

// Iowa CDPA sensitive categories (Sec. 715D.1(11))
type IASensitiveCategory =
  | "racial_ethnic_origin"
  | "religious_beliefs"
  | "mental_health_diagnosis"
  | "physical_health_diagnosis"
  | "sexual_orientation"
  | "citizenship_immigration"
  | "biometric"
  | "genetic"
  | "precise_geolocation"
  | "children_data";

interface IAConsentBody {
  userId: string;
  sensitiveCategories: IASensitiveCategory[];
  consentVersion: string;
}

export async function collectIASensitiveConsent(
  request: Request,
  env: Env
): Promise<Response> {
  if (!isIowaConsumerFromHeaders(request)) {
    return new Response(JSON.stringify({ skipped: "not_iowa_consumer" }), { status: 200 });
  }

  const body = await request.json<IAConsentBody>();
  const consentedAt = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO ia_sensitive_consent
       (user_id, sensitive_categories, consent_version, consented_at)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       sensitive_categories = excluded.sensitive_categories,
       consent_version = excluded.consent_version,
       consented_at = excluded.consented_at,
       withdrawn_at = NULL`
  )
    .bind(
      body.userId,
      JSON.stringify(body.sensitiveCategories),
      body.consentVersion,
      consentedAt
    )
    .run();

  return new Response(JSON.stringify({ ok: true, consentedAt }), { status: 201 });
}

function isIowaConsumerFromHeaders(request: Request): boolean {
  return (
    (request.cf?.country as string) === "US" &&
    (request.cf?.region as string) === "IA"
  );
}
```

---

## 3. Sale and Targeted Advertising Opt-Out

```typescript
// src/routes/ia-optout.ts
import type { Env } from "../types";

type IAOptOutType = "data_sale" | "targeted_advertising";

export async function handleIAOptOut(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, optOutTypes } = await request.json<{
    userId: string;
    optOutTypes: IAOptOutType[];
  }>();

  const optOutAt = new Date().toISOString();

  for (const type of optOutTypes) {
    // Store in KV for fast edge-level enforcement
    await env.IA_PRIVACY_KV.put(
      `ia:optout:${type}:${userId}`,
      JSON.stringify({ optOutAt, userId, type })
    );
  }

  // Durable record in D1
  await env.DB.prepare(
    `INSERT INTO ia_optout_log (user_id, opt_out_types, opted_out_at)
     VALUES (?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       opt_out_types = excluded.opt_out_types,
       opted_out_at = excluded.opted_out_at`
  )
    .bind(userId, JSON.stringify(optOutTypes), optOutAt)
    .run();

  return new Response(JSON.stringify({ ok: true, optOutAt }), { status: 200 });
}

// Fast edge check — call before every ad/sale operation
export async function isIAOptedOut(
  userId: string,
  type: IAOptOutType,
  env: Env
): Promise<boolean> {
  const val = await env.IA_PRIVACY_KV.get(`ia:optout:${type}:${userId}`);
  return val !== null;
}
```

---

## 4. Data Subject Rights Handler (90-Day SLA)

```typescript
// src/routes/ia-dsr.ts
import type { Env } from "../types";

// Iowa CDPA: access, deletion, portability; NO correction right
type IARightAction = "access" | "delete" | "portability";

export async function handleIASubjectRight(
  request: Request,
  env: Env
): Promise<Response> {
  const { userId, action } = await request.json<{
    userId: string;
    action: IARightAction;
  }>();

  const receivedAt = new Date();
  // Iowa: 90-day response window (extendable to 135 days with notice)
  const respondBy = new Date(
    receivedAt.getTime() + 90 * 24 * 60 * 60 * 1000
  ).toISOString();
  const ticketId = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO ia_dsr_log (ticket_id, user_id, action, received_at, respond_by, status)
     VALUES (?, ?, ?, ?, ?, 'OPEN')`
  )
    .bind(ticketId, userId, action, receivedAt.toISOString(), respondBy)
    .run();

  switch (action) {
    case "access": {
      const userData = await env.DB.prepare(`SELECT * FROM users WHERE id = ?`)
        .bind(userId)
        .first();
      const optOut = await env.DB.prepare(
        `SELECT opt_out_types FROM ia_optout_log WHERE user_id = ?`
      )
        .bind(userId)
        .first<{ opt_out_types: string }>();
      const sensitiveConsent = await env.DB.prepare(
        `SELECT sensitive_categories FROM ia_sensitive_consent WHERE user_id = ?`
      )
        .bind(userId)
        .first<{ sensitive_categories: string }>();
      await closeIADSR(ticketId, env);
      return new Response(
        JSON.stringify({
          ticketId,
          data: {
            user: userData,
            optOutTypes: optOut ? JSON.parse(optOut.opt_out_types) : [],
            sensitiveConsent: sensitiveConsent
              ? JSON.parse(sensitiveConsent.sensitive_categories)
              : [],
          },
        }),
        { status: 200 }
      );
    }
    case "delete": {
      await env.DB.prepare(`DELETE FROM users WHERE id = ?`).bind(userId).run();
      await env.DB.prepare(`DELETE FROM ia_sensitive_consent WHERE user_id = ?`)
        .bind(userId)
        .run();
      await env.DB.prepare(`DELETE FROM ia_optout_log WHERE user_id = ?`)
        .bind(userId)
        .run();
      // Clear KV opt-out flags
      await Promise.all([
        env.IA_PRIVACY_KV.delete(`ia:optout:data_sale:${userId}`),
        env.IA_PRIVACY_KV.delete(`ia:optout:targeted_advertising:${userId}`),
      ]);
      await closeIADSR(ticketId, env);
      return new Response(JSON.stringify({ ticketId, action: "deleted" }), { status: 200 });
    }
    case "portability": {
      const rows = await env.DB.prepare(`SELECT * FROM users WHERE id = ?`)
        .bind(userId)
        .all();
      const key = `exports/ia/${userId}/${ticketId}.json`;
      await env.USER_BUCKET.put(key, JSON.stringify(rows.results), {
        httpMetadata: { contentType: "application/json" },
      });
      await closeIADSR(ticketId, env);
      return new Response(JSON.stringify({ ticketId, exportPath: key }), { status: 200 });
    }
    default:
      return new Response(JSON.stringify({ error: "unsupported_action" }), { status: 400 });
  }
}

async function closeIADSR(ticketId: string, env: Env): Promise<void> {
  await env.DB.prepare(
    `UPDATE ia_dsr_log SET status = 'FULFILLED', fulfilled_at = ? WHERE ticket_id = ?`
  )
    .bind(new Date().toISOString(), ticketId)
    .run();
}
```

---

## 5. Iowa Breach Notification (Iowa Code Ch. 715C)

```typescript
// src/breach/ia-breach.ts
import type { Env } from "../types";

export interface IABreachEvent {
  incidentId: string;
  affectedIowaResidents: number;
  dataCategories: string[];
  includesFinancialOrSSN: boolean;
  discoveredAt: string;
}

export async function recordIABreach(
  event: IABreachEvent,
  env: Env
): Promise<void> {
  // Iowa 715C: notify AG and consumers within 30 days (up to 45 if investigation ongoing)
  // Financial data / SSN triggers mandatory AG notification regardless of count
  const notifyWindowDays = event.includesFinancialOrSSN ? 30 : 45;
  const notifyBy = new Date(
    new Date(event.discoveredAt).getTime() + notifyWindowDays * 24 * 60 * 60 * 1000
  ).toISOString();

  await env.DB.prepare(
    `INSERT INTO ia_breach_log
       (incident_id, affected_iowa_residents, data_categories,
        includes_financial_or_ssn, discovered_at, notify_by, status)
     VALUES (?, ?, ?, ?, ?, ?, 'PENDING')`
  )
    .bind(
      event.incidentId,
      event.affectedIowaResidents,
      JSON.stringify(event.dataCategories),
      event.includesFinancialOrSSN ? 1 : 0,
      event.discoveredAt,
      notifyBy
    )
    .run();

  await env.BREACH_QUEUE.send({
    regulator: "IOWA_AG",
    incidentId: event.incidentId,
    notifyBy,
  });
}
```

---

## Anti-patterns

- **Implementing a correction/rectification endpoint and labelling it Iowa CDPA compliance** — Iowa's CDPA deliberately omits the right to correct; building it as an Iowa right creates false consumer expectations and audit confusion; separate it as a voluntary feature.
- **Applying Iowa CDPA opt-outs to all US consumers** — Iowa's opt-out rights apply only to Iowa-resident consumers; a blanket national opt-out system should be implemented separately and flagged by state.
- **Assuming no data minimisation means no retention limits** — Iowa CDPA omits minimisation as a statutory obligation, but Iowa common law negligence claims and AG enforcement discretion can still penalise unreasonably long retention.
- **Conflating Iowa CDPA with Iowa 715C breach law** — the CDPA governs consumer rights; 715C governs breach notification; they have different triggers, timescales, and notification recipients.

## Gotchas

- The 90-day response window is one of the longest in US state privacy law — do not let it become de facto negligence; acknowledge requests within 10 days and respond well before the deadline.
- Precise geolocation (within 1,750 feet / ~533 metres) is sensitive data requiring opt-in consent — this is a common oversight for mapping or delivery features.
- Children's data (defined as data of consumers the controller knows to be under 13) is sensitive under Iowa CDPA and triggers COPPA concurrently — enforce both.
- Iowa's 90-day cure period before AG enforcement is generous but applies per violation series, not per violation — a systematic pattern forfeits the cure opportunity.
- Global Privacy Control (GPC) signals: Iowa CDPA does not mandate that GPC browser signals be honoured (unlike Colorado/California) — but honouring them is a defensible safe harbour.

## Verification

```sql
-- Open DSR tickets past 90-day deadline
SELECT ticket_id, user_id, action, respond_by
FROM ia_dsr_log
WHERE status = 'OPEN'
  AND respond_by < datetime('now');
-- Expected: 0 rows

-- Iowa users with sensitive data processed but no consent record
SELECT u.id, u.email
FROM users u
LEFT JOIN ia_sensitive_consent c ON c.user_id = u.id
WHERE u.state = 'IA'
  AND u.has_sensitive_data = 1
  AND c.user_id IS NULL;
-- Expected: 0 rows

-- Breach notifications past notify_by window
SELECT incident_id, notify_by
FROM ia_breach_log
WHERE status = 'PENDING'
  AND notify_by < datetime('now');
-- Expected: 0 rows

-- Check annual Iowa consumer count vs. threshold
-- wrangler kv key get --namespace-id=<IA_PRIVACY_KV> "ia:consumers:2026"
```

## Related

- `vcdpa-virginia-consumer-data-protection-workers.md`
- `utah-ucpa-privacy-compliance-workers-d1.md`
- `tennessee-ipa-workers-d1.md`
- `montana-mcdpa-consumer-rights-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `ccpa-opt-out.md`

## Sources

- Iowa SF 262 — Consumer Data Protection Act (signed 29 March 2023, effective 1 Jan 2025) — https://www.legis.iowa.gov/legislation/BillBook?ba=SF+262&ga=90
- Iowa Code Chapter 715C — Security Breach Notification — https://www.legis.iowa.gov/law/iowaCode/sections?codeChapter=715C
- Iowa Attorney General Consumer Protection — https://www.iowaattorneygeneral.gov/
- IAPP Iowa CDPA comparison — https://iapp.org/resources/article/us-state-privacy-legislation-tracker/
- Future of Privacy Forum Iowa CDPA analysis — https://fpf.org/
