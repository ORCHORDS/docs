# Indiana Consumer Data Protection Act (IDCPA) — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of Indiana residents and meets either threshold under Indiana's Consumer Data Protection Act (IDCPA, Senate Enrolled Act 5, Ind. Code §§ 24-15 et seq., effective 1 January 2026): (a) control or process personal data of 100,000+ Indiana consumers during a calendar year, or (b) control or process data of 25,000+ Indiana consumers while deriving over 50 % of gross revenue from the sale of personal data. The IDCPA grants consumers rights to access, correct, delete, and port their data, requires opt-in consent for sensitive data processing, and mandates data protection assessments before high-risk activities.

---

## Context

The IDCPA is enforced exclusively by the Indiana AG; there is no private right of action. Civil penalties reach USD 7,500 per intentional violation. The IDCPA provides a **30-day right to cure** with no sunset date — controllers must remedy deficiencies within 30 days of written notice before the AG may file suit. Key provisions:

- **Consumer rights**: access, correct, delete, port (machine-readable format), and opt out of targeted advertising, sale, and automated decision-making profiling with legal or substantial effects.
- **Sensitive data** (§ 24-15-2-13): racial/ethnic origin, religious beliefs, mental/physical health diagnosis, sexual orientation, citizenship/immigration status, genetic or biometric data, children's data under 13, precise geolocation — requires **opt-in consent**.
- **Data protection assessments** required before: targeted advertising, sale, profiling with legal/substantial effects, sensitive data processing, and any other high-risk processing.
- **Response deadline**: 45 days from verifiable consumer request; extendable by 45 days with notice when reasonably necessary.
- **Minimum security**: implement reasonable administrative, technical, and physical data security practices.

---

## 1. Consumer Rights Request Intake

Authenticated consumers submit rights requests via a Worker endpoint. The Worker validates identity, records the request in D1, and queues fulfilment.

```typescript
// workers/idcpa-rights-intake.ts
import { Env } from './types';

type IdcpaRightType =
  | 'access'
  | 'correct'
  | 'delete'
  | 'port'
  | 'opt_out_sale'
  | 'opt_out_targeted_ads'
  | 'opt_out_profiling';

interface RightsRequest {
  consumerId: string;
  right: IdcpaRightType;
  details?: Record<string, unknown>;
}

export async function handleIdcpaRightsRequest(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<RightsRequest>();
  const { consumerId, right, details } = body;

  if (!consumerId || !right) {
    return new Response(JSON.stringify({ error: 'consumerId and right are required' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const requestId = crypto.randomUUID();
  // Deadline: 45 days from submission
  const deadlineAt = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `INSERT INTO idcpa_rights_requests
     (id, consumer_id, right_type, details_json, status, submitted_at, deadline_at)
     VALUES (?, ?, ?, ?, 'pending', datetime('now'), ?)`,
  )
    .bind(requestId, consumerId, right, JSON.stringify(details ?? {}), deadlineAt)
    .run();

  await env.RIGHTS_QUEUE.send({ requestId, consumerId, right });

  return new Response(JSON.stringify({ requestId, deadlineAt }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## 2. Opt-Out of Sale and Targeted Advertising

The IDCPA requires honouring consumer opt-outs from sale and targeted advertising, including recognition of Universal Opt-Out Mechanisms (UOMs) such as the Global Privacy Control when the AG designates one.

```typescript
// workers/idcpa-opt-out.ts
import { Env } from './types';

type IdcpaOptOutScope = 'sale' | 'targeted_advertising' | 'profiling';

export async function recordIdcpaOptOut(
  env: Env,
  consumerId: string,
  scopes: IdcpaOptOutScope[],
  source: 'consumer_request' | 'gpc' | 'agent',
): Promise<void> {
  const stmt = env.DB.prepare(
    `INSERT OR REPLACE INTO idcpa_opt_outs
     (consumer_id, scope, source, recorded_at)
     VALUES (?, ?, ?, datetime('now'))`,
  );
  const batch = scopes.map((scope) => stmt.bind(consumerId, scope, source));
  await env.DB.batch(batch);
}

export async function isIdcpaOptedOut(
  env: Env,
  consumerId: string,
  scope: IdcpaOptOutScope,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM idcpa_opt_outs WHERE consumer_id = ? AND scope = ? LIMIT 1`,
  )
    .bind(consumerId, scope)
    .first<{ 1: number }>();
  return row !== null;
}

// Middleware: check GPC header and auto-record opt-out
export async function idcpaGpcMiddleware(
  env: Env,
  request: Request,
  consumerId: string | null,
): Promise<void> {
  if (request.headers.get('Sec-GPC') === '1' && consumerId) {
    await recordIdcpaOptOut(env, consumerId, ['sale', 'targeted_advertising'], 'gpc');
  }
}
```

---

## 3. Sensitive Data Opt-In Consent

Processing sensitive personal data of Indiana consumers requires affirmative opt-in consent. The Worker gates sensitive data writes behind a recorded consent check.

```typescript
// workers/idcpa-sensitive-consent.ts
import { Env } from './types';

type SensitiveCategory =
  | 'racial_ethnic_origin'
  | 'religious_beliefs'
  | 'mental_physical_health'
  | 'sexual_orientation'
  | 'citizenship_immigration'
  | 'genetic_data'
  | 'biometric_data'
  | 'childrens_data'
  | 'precise_geolocation';

export async function hasIdcpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: SensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM idcpa_sensitive_consents
     WHERE consumer_id = ? AND category = ?
       AND revoked_at IS NULL
       AND expires_at > datetime('now')
     LIMIT 1`,
  )
    .bind(consumerId, category)
    .first<{ 1: number }>();
  return row !== null;
}

export async function recordIdcpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: SensitiveCategory,
  consentText: string,
): Promise<void> {
  // Consent expires in 12 months; re-obtain annually
  const expiresAt = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.prepare(
    `INSERT INTO idcpa_sensitive_consents
     (id, consumer_id, category, consent_text_hash, granted_at, expires_at)
     VALUES (?, ?, ?, ?, datetime('now'), ?)`,
  )
    .bind(
      crypto.randomUUID(),
      consumerId,
      category,
      await hashString(consentText),
      expiresAt,
    )
    .run();
}

async function hashString(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## 4. Data Protection Assessment (DPA) Registry

Before initiating high-risk processing activities, controllers must complete a data protection assessment. The Worker registers assessments in D1 as an audit-ready record.

```typescript
// workers/idcpa-dpa-registry.ts
import { Env } from './types';

type DpaActivity =
  | 'targeted_advertising'
  | 'sale_of_personal_data'
  | 'profiling_legal_effects'
  | 'sensitive_data_processing'
  | 'other_high_risk';

interface DpaRecord {
  activity: DpaActivity;
  description: string;
  benefits: string;
  risks: string;
  mitigations: string;
  approvedBy: string;
}

export async function registerIdcpaDpa(
  env: Env,
  dpa: DpaRecord,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO idcpa_data_protection_assessments
     (id, activity, description, benefits, risks, mitigations,
      approved_by, assessed_at, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), 'approved')`,
  )
    .bind(
      id,
      dpa.activity,
      dpa.description,
      dpa.benefits,
      dpa.risks,
      dpa.mitigations,
      dpa.approvedBy,
    )
    .run();
  return id;
}
```

---

## 5. Deadline Monitor and Escalation

The IDCPA requires responses within 45 days. A scheduled Worker polls for overdue requests and escalates.

```typescript
// workers/idcpa-deadline-monitor.ts
import { Env } from './types';

export async function runIdcpaDeadlineMonitor(env: Env): Promise<void> {
  const overdue = await env.DB.prepare(
    `SELECT id, consumer_id, right_type, deadline_at
     FROM idcpa_rights_requests
     WHERE status = 'pending'
       AND deadline_at < datetime('now')
       AND escalated_at IS NULL`,
  ).all<{ id: string; consumer_id: string; right_type: string; deadline_at: string }>();

  for (const row of overdue.results) {
    await env.DB.prepare(
      `UPDATE idcpa_rights_requests
       SET escalated_at = datetime('now'), status = 'escalated'
       WHERE id = ?`,
    )
      .bind(row.id)
      .run();

    await env.ALERTS_QUEUE.send({
      type: 'idcpa_deadline_breach',
      requestId: row.id,
      consumerId: row.consumer_id,
      rightType: row.right_type,
      deadlineAt: row.deadline_at,
    });
  }
}
```

---

## Anti-patterns

- **Requiring account creation to submit a rights request**: the IDCPA requires a reasonable verification method — authenticated account is acceptable but cannot be the sole channel if the consumer lacks an account.
- **Treating opt-out of profiling separately from sale/targeted-ads opt-out**: a consumer who opts out of targeted advertising must also be excluded from profiling feeding that advertising.
- **Reusing sensitive-data consent indefinitely**: obtain fresh consent at least annually and when the processing purpose materially changes.
- **Using the 30-day cure window as a compliance strategy**: the AG may characterise a pattern of cured-then-repeat violations as bad faith, removing cure protection.

---

## Gotchas

- **Effective date is 1 January 2026** — not 2023 or 2024; the IDCPA is one of the later-effective US state laws.
- **Cure period has no sunset**: unlike Colorado, Indiana's cure provision does not expire, but AG discretion may override it for intentional or repeated violations.
- **Employee data exemption**: employment-related data processing is exempt from many IDCPA obligations through at least 2027 under the existing exemption.
- **No GPC mandate at enactment**: the IDCPA does not explicitly mandate GPC recognition, but the AG may designate UOMs by rule; monitor AG rulemaking and implement proactively.
- **Anonymous data**: the example project platform's anonymised posts fall outside IDCPA scope only if re-identification is not reasonably possible; pseudonymous identifiers (user IDs still linkable to persons) are still personal data.

---

## Verification

```sql
-- Confirm opt-out table is populated for test consumer
SELECT scope, source, recorded_at
FROM idcpa_opt_outs
WHERE consumer_id = 'test-consumer-id';

-- Confirm no overdue requests older than 45 days
SELECT COUNT(*) AS overdue
FROM idcpa_rights_requests
WHERE status = 'pending'
  AND deadline_at < datetime('now');

-- Confirm sensitive consent exists before processing
SELECT category, granted_at, expires_at
FROM idcpa_sensitive_consents
WHERE consumer_id = 'test-consumer-id'
  AND revoked_at IS NULL
  AND expires_at > datetime('now');
```

---

## Related

- `colorado-cpa-workers-d1.md` — similar opt-in sensitive data and DPA requirements
- `connecticut-ctdpa-data-rights-workers.md` — comparable 45-day response window
- `us-state-privacy-laws-2026-multi-state-compliance.md` — multi-state orchestration layer
- `gdpr-consent-management-cloudflare-workers.md` — consent record patterns
- `data-retention-automated-deletion-workers.md` — delete-right fulfilment pipeline

---

## Sources

- Indiana Senate Enrolled Act 5 (2022), codified at Ind. Code §§ 24-15-1-1 through 24-15-7-1, effective 1 January 2026
- Indiana AG Consumer Protection Division: <https://www.in.gov/attorneygeneral/consumer-protection-division/>
- IAPP US State Privacy Law Tracker: <https://iapp.org/resources/article/us-state-privacy-legislation-tracker/>
- Future of Privacy Forum — IDCPA Summary: <https://fpf.org/>
