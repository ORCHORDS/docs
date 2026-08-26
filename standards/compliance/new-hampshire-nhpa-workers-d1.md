# New Hampshire Privacy Act (NHPA) — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of New Hampshire residents and meets either threshold under New Hampshire's Privacy Act (NHPA, HB 1091, RSA 507-H, effective 1 January 2025): (a) control or process personal data of 35,000+ New Hampshire consumers per calendar year, or (b) control or process data of 10,000+ New Hampshire consumers while deriving over 25 % of gross revenue from the sale of personal data. The NHPA grants consumers access, correction, deletion, and portability rights, opt-out rights for sale, targeted advertising, and profiling, and requires opt-in consent for sensitive data.

---

## Context

The NHPA is enforced exclusively by the New Hampshire AG with no private right of action. Penalties reach USD 10,000 per violation. A **60-day right to cure** applies but expired on 31 December 2025 — after that date the AG may proceed without prior written notice. Notable characteristics:

- **Low consumer-count threshold**: 35,000 consumers (matching Delaware), combined with only a 10,000 + 25 % revenue alternate — one of the lower combined thresholds among US state laws.
- **Sensitive data** (RSA 507-H:1 XVII): racial/ethnic origin, religious beliefs, mental/physical health diagnosis, sexual orientation, citizenship/immigration status, genetic data, biometric data, children's data under 13, precise geolocation — requires **opt-in consent**.
- **Consumer rights**: access, correct, delete, port (structured, commonly used, machine-readable), opt out of targeted advertising, sale, and profiling with legal or substantially similar effects.
- **Response deadline**: 45 days from a verifiable consumer request; extensible once by 45 days with consumer notice.
- **Authorised agent**: consumers may use authorised agents to submit opt-out requests; controllers may request reasonable proof of authorisation.
- **Data protection assessments**: required before targeted advertising, sale, profiling with legal effects, sensitive data processing, or other processing with heightened risk.

---

## 1. Low-Threshold Consumer Count Monitor

At 35,000 consumers (primary) and 10,000 + 25 % revenue (alternate), monitoring must be more frequent than for 100,000-threshold states.

```typescript
// workers/nhpa-threshold-monitor.ts
import { Env } from './types';

interface NhpaThreshold {
  subject: boolean;
  nhConsumers: number;
  saleRevenuePct: number;
  trigger: 'consumer_count' | 'revenue' | 'not_subject';
}

export async function evaluateNhpaThreshold(env: Env): Promise<NhpaThreshold> {
  const yearStart = `${new Date().getFullYear()}-01-01`;

  const countRow = await env.DB.prepare(
    `SELECT COUNT(DISTINCT consumer_id) AS cnt
     FROM consumer_events
     WHERE state_code = 'NH' AND occurred_at >= ?`,
  )
    .bind(yearStart)
    .first<{ cnt: number }>();

  const count = countRow?.cnt ?? 0;

  if (count >= 35000) {
    return { subject: true, nhConsumers: count, saleRevenuePct: 0, trigger: 'consumer_count' };
  }

  if (count >= 10000) {
    const revRow = await env.DB.prepare(
      `SELECT sale_revenue_pct FROM annual_revenue_snapshots
       WHERE year = ? ORDER BY recorded_at DESC LIMIT 1`,
    )
      .bind(new Date().getFullYear())
      .first<{ sale_revenue_pct: number }>();

    const pct = revRow?.sale_revenue_pct ?? 0;
    if (pct > 25) {
      return { subject: true, nhConsumers: count, saleRevenuePct: pct, trigger: 'revenue' };
    }
  }

  return { subject: false, nhConsumers: count, saleRevenuePct: 0, trigger: 'not_subject' };
}
```

---

## 2. Sensitive Data Opt-In Consent Management

```typescript
// workers/nhpa-sensitive-consent.ts
import { Env } from './types';

type NhpaSensitiveCategory =
  | 'racial_ethnic_origin'
  | 'religious_beliefs'
  | 'mental_physical_health'
  | 'sexual_orientation'
  | 'citizenship_immigration'
  | 'genetic_data'
  | 'biometric_data'
  | 'childrens_data_under_13'
  | 'precise_geolocation';

export async function assertNhpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: NhpaSensitiveCategory,
): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM nhpa_sensitive_consents
     WHERE consumer_id = ? AND category = ?
       AND revoked_at IS NULL AND expires_at > datetime('now')
     LIMIT 1`,
  )
    .bind(consumerId, category)
    .first<{ 1: number }>();

  if (!row) {
    throw new Error(
      `NHPA: opt-in consent required for sensitive category "${category}" ` +
        `but not found for consumer ${consumerId}`,
    );
  }
}

export async function recordNhpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: NhpaSensitiveCategory,
  uiTextHash: string,
): Promise<void> {
  const expiresAt = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.prepare(
    `INSERT INTO nhpa_sensitive_consents
     (id, consumer_id, category, ui_text_hash, granted_at, expires_at)
     VALUES (?, ?, ?, ?, datetime('now'), ?)`,
  )
    .bind(crypto.randomUUID(), consumerId, category, uiTextHash, expiresAt)
    .run();
}

export async function revokeNhpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: NhpaSensitiveCategory,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE nhpa_sensitive_consents
     SET revoked_at = datetime('now')
     WHERE consumer_id = ? AND category = ? AND revoked_at IS NULL`,
  )
    .bind(consumerId, category)
    .run();
}
```

---

## 3. Opt-Out of Sale, Targeted Advertising, and Profiling

The NHPA opt-out rights are standalone — a consumer may exercise any one independently. The Worker handles each scope in isolation.

```typescript
// workers/nhpa-opt-out.ts
import { Env } from './types';

type NhpaOptOutScope = 'sale' | 'targeted_advertising' | 'profiling';

export async function recordNhpaOptOut(
  env: Env,
  consumerId: string,
  scopes: NhpaOptOutScope[],
  via: 'consumer_direct' | 'authorized_agent' | 'gpc',
  agentProofRef?: string,
): Promise<void> {
  const stmt = env.DB.prepare(
    `INSERT OR REPLACE INTO nhpa_opt_outs
     (consumer_id, scope, via, agent_proof_ref, recorded_at)
     VALUES (?, ?, ?, ?, datetime('now'))`,
  );
  await env.DB.batch(
    scopes.map((scope) => stmt.bind(consumerId, scope, via, agentProofRef ?? null)),
  );
}

export async function clearNhpaOptOut(
  env: Env,
  consumerId: string,
  scope: NhpaOptOutScope,
): Promise<void> {
  // Only clear if consumer opts back in — must be consumer-initiated
  await env.DB.prepare(
    `DELETE FROM nhpa_opt_outs WHERE consumer_id = ? AND scope = ?`,
  )
    .bind(consumerId, scope)
    .run();
}

export async function nhpaOptOutStatus(
  env: Env,
  consumerId: string,
): Promise<Record<NhpaOptOutScope, boolean>> {
  const rows = await env.DB.prepare(
    `SELECT scope FROM nhpa_opt_outs WHERE consumer_id = ?`,
  )
    .bind(consumerId)
    .all<{ scope: NhpaOptOutScope }>();

  const result: Record<NhpaOptOutScope, boolean> = {
    sale: false,
    targeted_advertising: false,
    profiling: false,
  };
  for (const row of rows.results) {
    result[row.scope] = true;
  }
  return result;
}
```

---

## 4. Authorised Agent Verification

The NHPA allows consumers to designate authorised agents for opt-out requests. The Worker validates agent proof before processing.

```typescript
// workers/nhpa-agent-verification.ts
import { Env } from './types';

interface AgentProof {
  agentId: string;
  consumerId: string;
  proofType: 'signed_letter' | 'poa' | 'account_delegation';
  proofRef: string; // R2 object key or external document ID
  verifiedAt?: string;
}

export async function recordAgentProof(
  env: Env,
  proof: AgentProof,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO nhpa_agent_proofs
     (id, agent_id, consumer_id, proof_type, proof_ref, submitted_at, verified_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'), ?)`,
  )
    .bind(
      crypto.randomUUID(),
      proof.agentId,
      proof.consumerId,
      proof.proofType,
      proof.proofRef,
      proof.verifiedAt ?? null,
    )
    .run();
}

export async function isAgentAuthorised(
  env: Env,
  agentId: string,
  consumerId: string,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM nhpa_agent_proofs
     WHERE agent_id = ? AND consumer_id = ? AND verified_at IS NOT NULL
     LIMIT 1`,
  )
    .bind(agentId, consumerId)
    .first<{ 1: number }>();
  return row !== null;
}
```

---

## 5. Data Protection Assessment Registry and Scheduled Cron

A Cloudflare Workers cron trigger runs monthly to confirm all active high-risk processing activities have a current, non-expired DPA on record.

```typescript
// workers/nhpa-dpa-audit.ts
import { Env } from './types';

type NhpaHighRiskActivity =
  | 'targeted_advertising'
  | 'sale'
  | 'profiling_legal_effects'
  | 'sensitive_data_processing';

export async function upsertNhpaDpa(
  env: Env,
  activity: NhpaHighRiskActivity,
  summary: string,
  approver: string,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO nhpa_dpas
     (id, activity, summary, approver, assessed_at, review_due_at)
     VALUES (?, ?, ?, ?, datetime('now'), datetime('now', '+12 months'))`,
  )
    .bind(id, activity, summary, approver)
    .run();
  return id;
}

// Cron: alert on DPAs due for review
export async function nhpaDpaReviewCron(env: Env): Promise<void> {
  const dueSoon = await env.DB.prepare(
    `SELECT id, activity, review_due_at
     FROM nhpa_dpas
     WHERE review_due_at < datetime('now', '+30 days')
       AND archived_at IS NULL
     ORDER BY review_due_at ASC`,
  ).all<{ id: string; activity: string; review_due_at: string }>();

  for (const dpa of dueSoon.results) {
    await env.ALERTS_QUEUE.send({
      type: 'nhpa_dpa_review_due',
      dpaId: dpa.id,
      activity: dpa.activity,
      reviewDueAt: dpa.review_due_at,
    });
  }
}
```

---

## Anti-patterns

- **Using a 100,000-consumer threshold**: New Hampshire's primary threshold is 35,000 — using the higher figure common in Iowa, Texas, or Indiana means you may be operating without required controls.
- **Dismissing authorised agent requests without good reason**: the NHPA allows requiring reasonable proof of authorisation, but flat refusal of all agent requests is non-compliant; implement the proof-verification flow.
- **Re-engaging targeted advertising immediately after an opt-out is withdrawn**: the NHPA requires the controller to honour an opt-out promptly; re-opt-in must be consumer-initiated and confirmed.
- **Skipping DPAs for platform features launched incrementally**: every new product feature involving targeted advertising or profiling requires its own assessment before launch, not retroactively.

---

## Gotchas

- **Cure period expired 31 December 2025**: as of 2026-08-23, the AG may enforce immediately — no cure right applies to current violations.
- **25 % revenue threshold (not 50 %)**: the alternate trigger is 10,000 consumers + 25 % revenue, matching Nebraska rather than the 50 % threshold used in Indiana, Virginia, or Texas.
- **example project anonymous-post data**: the NHPA, like peer laws, still reaches metadata (timestamps, engagement signals, device tokens) associated with anonymous post activity if those records are reasonably linkable to a natural person.
- **GPC**: the NHPA does not explicitly mandate GPC recognition at enactment; however, implementing GPC opt-out handling proactively reduces litigation and AG inquiry risk as multi-state GPC mandates expand.
- **Biometric data from reaction images**: if example project uses facial-reaction features or emoji overlays processed via image analysis, this is biometric data under the NHPA and requires opt-in consent.

---

## Verification

```sql
-- Check NH consumer count against the 35,000 threshold
SELECT COUNT(DISTINCT consumer_id) AS nh_consumers
FROM consumer_events
WHERE state_code = 'NH'
  AND occurred_at >= datetime('now', 'start of year');

-- Verify no open rights requests are past the 45-day deadline
SELECT id, right_type, deadline_at
FROM nhpa_rights_requests
WHERE status = 'open'
  AND deadline_at < datetime('now');

-- Confirm active DPAs exist for all high-risk activities
SELECT activity, MAX(assessed_at) AS latest_assessment
FROM nhpa_dpas
WHERE archived_at IS NULL
GROUP BY activity;

-- List agent proofs awaiting verification
SELECT id, agent_id, consumer_id, proof_type, submitted_at
FROM nhpa_agent_proofs
WHERE verified_at IS NULL;
```

---

## Related

- `delaware-dpdpa-workers-d1.md` — same 35,000 primary threshold; 20 % revenue trigger
- `nebraska-ndpa-workers-d1.md` — 100,000 / 10,000 + 25 % revenue structure
- `connecticut-ctdpa-data-rights-workers.md` — comparable rights framework
- `us-state-privacy-laws-2026-multi-state-compliance.md` — multi-state orchestration
- `gdpr-right-to-erasure-d1-r2-pipeline.md` — deletion fulfilment patterns

---

## Sources

- New Hampshire HB 1091 (2024), RSA Chapter 507-H, effective 1 January 2025
- New Hampshire AG Office — Consumer Protection Bureau: <https://www.doj.nh.gov/consumer-protection/>
- IAPP US State Privacy Law Tracker: <https://iapp.org/resources/article/us-state-privacy-legislation-tracker/>
- National Conference of State Legislatures — Consumer Data Privacy Laws: <https://www.ncsl.org/technology-and-communication/consumer-data-protection-legislation>
