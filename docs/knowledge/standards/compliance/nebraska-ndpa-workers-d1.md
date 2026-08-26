# Nebraska Data Privacy Act (NDPA) — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of Nebraska residents and meets either threshold under Nebraska's Data Privacy Act (NDPA, LB 1074, Neb. Rev. Stat. §§ 87-301 et seq., effective 1 January 2025): (a) control or process personal data of 100,000+ Nebraska consumers during a calendar year, or (b) control or process data of 25,000+ Nebraska consumers while deriving over 25 % of gross revenue from the sale of personal data. The NDPA grants consumer access, correction, deletion, portability, and opt-out rights, and requires opt-in consent for sensitive data processing.

---

## Context

The NDPA is enforced exclusively by the Nebraska AG with no private right of action. Civil penalties reach USD 7,500 per violation. A **30-day right to cure** is available but has no stated sunset date. Key characteristics:

- **Revenue threshold at 25 %**: sits between Delaware (20 %) and most other states (50 %), meaning a mid-range monetisation model may trigger applicability earlier than expected.
- **Sensitive data** (§ 87-302(17)): racial/ethnic origin, religious beliefs, mental/physical health diagnosis or condition, sexual orientation, citizenship/immigration status, genetic or biometric data, children's data under 13, and precise geolocation.
- **No employee data exemption** explicitly provided — employment data processing should be reviewed carefully against the statute's scope.
- **Consumer rights**: access, correct, delete, port, and opt out of targeted advertising, sale of personal data, and profiling with legal or significant effects.
- **Response deadline**: 45 days; extensible by 45 additional days with consumer notice.
- **Data protection assessments** required before high-risk processing activities including targeted advertising, sale, profiling, and sensitive data processing.

---

## 1. Revenue-Based Threshold Monitoring

Nebraska's 25 % revenue threshold is lower than most peer laws. A Worker records sale-derived revenue periodically in D1 and evaluates applicability.

```typescript
// workers/ndpa-threshold-monitor.ts
import { Env } from './types';

interface NdpaThresholdResult {
  subject: boolean;
  nebraskaConsumers: number;
  saleRevenuePct: number;
  trigger: 'consumer_count' | 'revenue' | 'not_subject';
}

export async function evaluateNdpaThreshold(env: Env): Promise<NdpaThresholdResult> {
  const yearStart = `${new Date().getFullYear()}-01-01`;

  const consumerRow = await env.DB.prepare(
    `SELECT COUNT(DISTINCT consumer_id) AS cnt
     FROM consumer_events
     WHERE state_code = 'NE' AND occurred_at >= ?`,
  )
    .bind(yearStart)
    .first<{ cnt: number }>();

  const count = consumerRow?.cnt ?? 0;

  if (count >= 100000) {
    return { subject: true, nebraskaConsumers: count, saleRevenuePct: 0, trigger: 'consumer_count' };
  }

  if (count >= 25000) {
    const revRow = await env.DB.prepare(
      `SELECT sale_revenue_pct FROM annual_revenue_snapshots
       WHERE year = ? ORDER BY recorded_at DESC LIMIT 1`,
    )
      .bind(new Date().getFullYear())
      .first<{ sale_revenue_pct: number }>();

    const pct = revRow?.sale_revenue_pct ?? 0;
    if (pct > 25) {
      return { subject: true, nebraskaConsumers: count, saleRevenuePct: pct, trigger: 'revenue' };
    }
  }

  return { subject: false, nebraskaConsumers: count, saleRevenuePct: 0, trigger: 'not_subject' };
}
```

---

## 2. Consumer Rights Intake and Verification

The NDPA requires a reasonably accessible and reliable means of submitting consumer rights requests. The Worker validates identity via a signed JWT and records the request.

```typescript
// workers/ndpa-rights-intake.ts
import { Env } from './types';

type NdpaRight =
  | 'access'
  | 'correct'
  | 'delete'
  | 'port'
  | 'opt_out_targeted_advertising'
  | 'opt_out_sale'
  | 'opt_out_profiling';

interface NdpaRightsPayload {
  consumerId: string;
  right: NdpaRight;
  correctionData?: Record<string, unknown>;
}

export async function submitNdpaRightsRequest(
  env: Env,
  payload: NdpaRightsPayload,
): Promise<{ requestId: string; deadlineAt: string }> {
  const requestId = crypto.randomUUID();
  const deadlineAt = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `INSERT INTO ndpa_rights_requests
     (id, consumer_id, right_type, correction_json, status, submitted_at, deadline_at)
     VALUES (?, ?, ?, ?, 'open', datetime('now'), ?)`,
  )
    .bind(
      requestId,
      payload.consumerId,
      payload.right,
      JSON.stringify(payload.correctionData ?? {}),
      deadlineAt,
    )
    .run();

  await env.RIGHTS_QUEUE.send({ law: 'ndpa', requestId, right: payload.right });
  return { requestId, deadlineAt };
}

export async function resolveNdpaRightsRequest(
  env: Env,
  requestId: string,
  outcome: 'fulfilled' | 'denied' | 'extended',
  note?: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE ndpa_rights_requests
     SET status = ?, outcome_note = ?, resolved_at = datetime('now')
     WHERE id = ?`,
  )
    .bind(outcome, note ?? null, requestId)
    .run();
}
```

---

## 3. Sensitive Data Opt-In Gate

Nebraska requires explicit opt-in consent before processing sensitive personal data. The Worker enforces this gate at write time.

```typescript
// workers/ndpa-sensitive-gate.ts
import { Env } from './types';

type NdpaSensitiveCategory =
  | 'racial_ethnic_origin'
  | 'religious_beliefs'
  | 'mental_physical_health'
  | 'sexual_orientation'
  | 'citizenship_immigration'
  | 'genetic_data'
  | 'biometric_data'
  | 'childrens_data_under_13'
  | 'precise_geolocation';

export async function ndpaSensitiveGate(
  env: Env,
  consumerId: string,
  category: NdpaSensitiveCategory,
): Promise<void> {
  const consent = await env.DB.prepare(
    `SELECT 1 FROM ndpa_sensitive_consents
     WHERE consumer_id = ? AND category = ?
       AND revoked_at IS NULL AND expires_at > datetime('now')
     LIMIT 1`,
  )
    .bind(consumerId, category)
    .first<{ 1: number }>();

  if (!consent) {
    throw new Error(
      `NDPA: No valid opt-in consent for sensitive category "${category}" ` +
        `(consumer ${consumerId})`,
    );
  }
}

export async function grantNdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: NdpaSensitiveCategory,
  disclosureHash: string,
): Promise<void> {
  const expiresAt = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.prepare(
    `INSERT INTO ndpa_sensitive_consents
     (id, consumer_id, category, disclosure_hash, granted_at, expires_at)
     VALUES (?, ?, ?, ?, datetime('now'), ?)`,
  )
    .bind(crypto.randomUUID(), consumerId, category, disclosureHash, expiresAt)
    .run();
}
```

---

## 4. Opt-Out of Sale and Targeted Advertising

```typescript
// workers/ndpa-opt-out.ts
import { Env } from './types';

type NdpaOptOutScope = 'sale' | 'targeted_advertising' | 'profiling';

export async function recordNdpaOptOut(
  env: Env,
  consumerId: string,
  scopes: NdpaOptOutScope[],
  method: 'consumer_request' | 'gpc' | 'authorized_agent',
): Promise<void> {
  const stmt = env.DB.prepare(
    `INSERT OR REPLACE INTO ndpa_opt_outs
     (consumer_id, scope, method, recorded_at)
     VALUES (?, ?, ?, datetime('now'))`,
  );
  await env.DB.batch(scopes.map((s) => stmt.bind(consumerId, s, method)));
}

export async function isNdpaOptedOut(
  env: Env,
  consumerId: string,
  scope: NdpaOptOutScope,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM ndpa_opt_outs WHERE consumer_id = ? AND scope = ? LIMIT 1`,
  )
    .bind(consumerId, scope)
    .first<{ 1: number }>();
  return row !== null;
}
```

---

## 5. Data Protection Assessment Registry

The NDPA requires data protection assessments before processing activities that present heightened privacy risk.

```typescript
// workers/ndpa-dpa-registry.ts
import { Env } from './types';

type NdpaHighRiskActivity =
  | 'targeted_advertising'
  | 'sale_of_personal_data'
  | 'profiling_significant_effects'
  | 'sensitive_data_processing';

export async function registerNdpaDpa(
  env: Env,
  activity: NdpaHighRiskActivity,
  description: string,
  benefitsVsRisks: string,
  approvedBy: string,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO ndpa_dpas
     (id, activity, description, benefits_vs_risks, approved_by, assessed_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(id, activity, description, benefitsVsRisks, approvedBy)
    .run();
  return id;
}

export async function listNdpaDpas(
  env: Env,
  activity?: NdpaHighRiskActivity,
): Promise<{ id: string; activity: string; assessedAt: string }[]> {
  const rows = activity
    ? await env.DB.prepare(
        `SELECT id, activity, assessed_at FROM ndpa_dpas WHERE activity = ? ORDER BY assessed_at DESC`,
      )
        .bind(activity)
        .all<{ id: string; activity: string; assessed_at: string }>()
    : await env.DB.prepare(
        `SELECT id, activity, assessed_at FROM ndpa_dpas ORDER BY assessed_at DESC`,
      ).all<{ id: string; activity: string; assessed_at: string }>();

  return rows.results.map((r) => ({
    id: r.id,
    activity: r.activity,
    assessedAt: r.assessed_at,
  }));
}
```

---

## Anti-patterns

- **Using a 50 % revenue threshold**: Nebraska's revenue trigger is 25 % of gross revenue — a common misconfiguration from copy-pasting Virginia or Indiana logic.
- **Omitting profiling opt-out**: Nebraska explicitly requires opt-out of profiling for legal or significant effects as a standalone right separate from opt-out of targeted advertising.
- **Conflating employee data with consumer data**: Nebraska does not include a blanket employee data exemption, so internal analytics touching employee records may be in scope.
- **Skipping DPAs for sale activities**: every sale of personal data requires a prior data protection assessment — not just high-risk processing types.

---

## Gotchas

- **25 % revenue threshold is unusual**: when building multi-state opt-out logic, ensure the Nebraska revenue check uses the correct percentage — it is distinct from the 20 % (Delaware) and 50 % (Virginia, Indiana, Colorado) thresholds used elsewhere.
- **Cure window is open-ended** but the AG may decline to offer a cure opportunity if the violation is judged intentional or part of a pattern.
- **No GPC mandate at enactment**: the statute does not explicitly mention the Global Privacy Control, but implementing GPC recognition is prudent best practice given the FTC's position and peer AG enforcement patterns.
- **Anonymous example project posts vs. pseudonymous analytics**: post content on example project may be anonymous, but Nebraska consumers who interact with the platform generate event records (click, view, share) that constitute personal data if linkable to identifiable individuals, even indirectly through device identifiers.

---

## Verification

```sql
-- Verify Nebraska consumer count vs. 100,000 threshold
SELECT COUNT(DISTINCT consumer_id) AS ne_count
FROM consumer_events
WHERE state_code = 'NE'
  AND occurred_at >= datetime('now', 'start of year');

-- Check for open rights requests past the 45-day deadline
SELECT id, consumer_id, right_type, deadline_at
FROM ndpa_rights_requests
WHERE status = 'open'
  AND deadline_at < datetime('now');

-- Confirm at least one DPA exists for sale activity
SELECT id, assessed_at
FROM ndpa_dpas
WHERE activity = 'sale_of_personal_data'
ORDER BY assessed_at DESC
LIMIT 1;

-- Validate sensitive consent is not expired
SELECT category, expires_at
FROM ndpa_sensitive_consents
WHERE consumer_id = 'test-consumer-id'
  AND revoked_at IS NULL
  AND expires_at > datetime('now');
```

---

## Related

- `indiana-idcpa-workers-d1.md` — 25,000 + 50 % revenue variant for comparison
- `delaware-dpdpa-workers-d1.md` — 10,000 + 20 % revenue variant
- `vcdpa-virginia-consumer-data-protection-workers.md` — 25,000 + 50 % baseline
- `us-state-privacy-laws-2026-multi-state-compliance.md` — multi-state orchestration
- `data-retention-automated-deletion-workers.md` — deletion right fulfilment

---

## Sources

- Nebraska Legislative Bill 1074 (2024), Neb. Rev. Stat. §§ 87-301 – 87-320, effective 1 January 2025
- Nebraska AG Office — Consumer Protection: <https://ago.nebraska.gov/consumer-protection>
- IAPP US State Privacy Law Tracker: <https://iapp.org/resources/article/us-state-privacy-legislation-tracker/>
- National Conference of State Legislatures — Consumer Data Privacy Laws: <https://www.ncsl.org/technology-and-communication/consumer-data-protection-legislation>
