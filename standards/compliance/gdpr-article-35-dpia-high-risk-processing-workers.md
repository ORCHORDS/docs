# GDPR Article 35 DPIA for High-Risk Processing with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**

GDPR Article 35 requires a Data Protection Impact Assessment (DPIA) before starting any processing "likely to result in a high risk" to individuals' rights and freedoms. Teams shipping new Workers features — real-time behavioural profiling, large-scale special-category data processing, systematic monitoring of employees — often skip or rush the DPIA, then face enforcement action when the DPA audits. This article provides a structured DPIA workflow implemented in Cloudflare Workers and D1: necessity and proportionality analysis, risk scoring, mitigation tracking, and DPO sign-off evidence — not AI-specific (see `ai-dpia-data-protection-impact-assessment.md`) but covering general high-risk processing scenarios.

**Context**

Art. 35(3) mandates a DPIA in at least three scenarios: (a) systematic and extensive profiling with automated decision-making, (b) large-scale processing of special category data (Art. 9), (c) systematic monitoring of public areas. EDPB Guidelines 09/2022 expanded this to nine criteria — processing any two triggers a DPIA obligation. A DPIA must describe: the processing and its purposes, the necessity and proportionality assessment, the risk assessment to data subjects, and the measures to address those risks (Art. 35(7)). If residual risk remains high after mitigation, Art. 36 requires prior consultation with the supervisory authority.

---

## D1 Schema for DPIA Registry

```sql
-- migrations/0001_dpia_registry.sql
CREATE TABLE IF NOT EXISTS dpias (
  id                TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  processing_owner  TEXT NOT NULL,
  dpo_email         TEXT NOT NULL,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  status            TEXT NOT NULL DEFAULT 'draft',  -- draft|review|approved|art36-required|rejected
  triggers          TEXT NOT NULL,    -- JSON array: which EDPB criteria triggered the DPIA
  processing_desc   TEXT NOT NULL,
  purposes          TEXT NOT NULL,
  lawful_basis      TEXT NOT NULL,
  necessity_score   INTEGER,          -- 1-5 necessity; 1-5 proportionality
  proportionality_score INTEGER,
  residual_risk     TEXT,             -- low|medium|high
  dpo_reviewed_at   TEXT,
  dpo_outcome       TEXT,             -- approved|rejected|art36-required
  art36_submitted_at TEXT,
  review_due_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dpia_risks (
  id          TEXT PRIMARY KEY,
  dpia_id     TEXT NOT NULL REFERENCES dpias(id),
  threat      TEXT NOT NULL,
  likelihood  INTEGER NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
  impact      INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 5),
  risk_score  INTEGER GENERATED ALWAYS AS (likelihood * impact) STORED,
  mitigations TEXT NOT NULL,   -- JSON array of mitigation measures
  residual_likelihood INTEGER,
  residual_impact     INTEGER,
  residual_score      INTEGER GENERATED ALWAYS AS (residual_likelihood * residual_impact) STORED,
  status      TEXT NOT NULL DEFAULT 'open'  -- open|mitigated|accepted
);

CREATE INDEX IF NOT EXISTS idx_dpia_status    ON dpias(status);
CREATE INDEX IF NOT EXISTS idx_dpia_review    ON dpias(review_due_at);
CREATE INDEX IF NOT EXISTS idx_risk_dpia      ON dpia_risks(dpia_id);
CREATE INDEX IF NOT EXISTS idx_risk_score     ON dpia_risks(residual_score);
```

## DPIA Trigger Checker

```typescript
// workers/dpia/trigger-check.ts
// EDPB WP248/Guidelines 09/2022 — nine criteria for mandatory DPIA
export const DPIA_TRIGGERS = {
  scoring_profiling:        'Scoring or profiling (Art.35(3)(a) — EDPB criterion 1)',
  automated_decisions:      'Automated decisions with legal/significant effect (Art.35(3)(a))',
  systematic_monitoring:    'Systematic monitoring of data subjects (Art.35(3)(c))',
  sensitive_data:           'Processing special category / criminal conviction data (Art.9/10)',
  large_scale:              'Large-scale processing',
  matched_combined_datasets:'Matching or combining datasets from multiple controllers',
  vulnerable_subjects:      'Data concerning vulnerable natural persons',
  innovative_technology:    'Use of innovative technology or novel application',
  blocking_rights:          'Processing that prevents data subjects from exercising a right',
} as const;

export type DpiaTrigger = keyof typeof DPIA_TRIGGERS;

export interface TriggerCheckResult {
  dpiaRequired: boolean;
  triggersFound: DpiaTrigger[];
  reason: string;
}

export function checkDpiaRequired(flags: Partial<Record<DpiaTrigger, boolean>>): TriggerCheckResult {
  const found = (Object.keys(flags) as DpiaTrigger[]).filter(k => flags[k]);
  // EDPB: two or more criteria → DPIA required
  const required = found.length >= 2;
  return {
    dpiaRequired: required,
    triggersFound: found,
    reason: required
      ? `${found.length} EDPB criteria met — DPIA mandatory under GDPR Art.35`
      : found.length === 1
        ? `1 EDPB criterion met — DPIA recommended but not strictly required`
        : 'No criteria met — DPIA not required for this processing activity',
  };
}
```

## DPIA Submission and Risk Entry Worker

```typescript
// workers/dpia/submit.ts
interface CreateDpiaBody {
  title: string;
  processingOwner: string;
  dpiaTriggersFlags: Partial<Record<DpiaTrigger, boolean>>;
  processingDesc: string;
  purposes: string;
  lawfulBasis: string;  // e.g. "Art.6(1)(f) — legitimate interest"
  reviewDays?: number;
}

export async function createDpia(
  body: CreateDpiaBody,
  db: D1Database,
  dpoPerson: string
): Promise<{ id: string; dpiaRequired: boolean }> {
  const check = checkDpiaRequired(body.dpiaTriggersFlags);

  if (!check.dpiaRequired) {
    return { id: 'not-required', dpiaRequired: false };
  }

  const id = crypto.randomUUID();
  const reviewDue = new Date(
    Date.now() + (body.reviewDays ?? 730) * 86400 * 1000  // default 2-year review
  ).toISOString();

  await db.prepare(`
    INSERT INTO dpias
      (id, title, processing_owner, dpo_email, triggers,
       processing_desc, purposes, lawful_basis, review_due_at)
    VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)
  `).bind(
    id, body.title, body.processingOwner, dpoPerson,
    JSON.stringify(check.triggersFound),
    body.processingDesc, body.purposes, body.lawfulBasis, reviewDue
  ).run();

  return { id, dpiaRequired: true };
}

interface RiskEntry {
  dpiaId: string;
  threat: string;
  likelihood: number;
  impact: number;
  mitigations: string[];
  residualLikelihood: number;
  residualImpact: number;
}

export async function addRisk(risk: RiskEntry, db: D1Database): Promise<string> {
  const id = crypto.randomUUID();
  await db.prepare(`
    INSERT INTO dpia_risks
      (id, dpia_id, threat, likelihood, impact, mitigations,
       residual_likelihood, residual_impact)
    VALUES (?1,?2,?3,?4,?5,?6,?7,?8)
  `).bind(
    id, risk.dpiaId, risk.threat, risk.likelihood, risk.impact,
    JSON.stringify(risk.mitigations), risk.residualLikelihood, risk.residualImpact
  ).run();
  return id;
}
```

## DPO Review and Residual Risk Calculation

```typescript
// workers/dpia/dpo-review.ts
export async function computeResidualRisk(
  dpiaId: string,
  db: D1Database
): Promise<'low' | 'medium' | 'high'> {
  const { results } = await db.prepare(`
    SELECT residual_score FROM dpia_risks
    WHERE dpia_id = ?1 AND status != 'accepted'
  `).bind(dpiaId).all<{ residual_score: number }>();

  if (results.length === 0) return 'low';

  const maxScore = Math.max(...results.map(r => r.residual_score));
  if (maxScore >= 16) return 'high';    // 4×4 or 5×5 grid
  if (maxScore >= 9)  return 'medium';
  return 'low';
}

export async function dpoApprove(
  dpiaId: string,
  outcome: 'approved' | 'rejected' | 'art36-required',
  db: D1Database
): Promise<void> {
  const residualRisk = await computeResidualRisk(dpiaId, db);

  // Art. 36 consultation required if risk remains "high" after mitigations
  const finalOutcome = residualRisk === 'high' ? 'art36-required' : outcome;

  await db.prepare(`
    UPDATE dpias
    SET dpo_reviewed_at = datetime('now'),
        dpo_outcome     = ?1,
        residual_risk   = ?2,
        status          = ?1
    WHERE id = ?3
  `).bind(finalOutcome, residualRisk, dpiaId).run();
}
```

## Art. 36 Prior Consultation Tracking

```typescript
// workers/dpia/art36.ts
// If residual risk is high, the DPA must be consulted before processing begins
export async function recordArt36Submission(
  dpiaId: string,
  dpaReference: string,
  db: D1Database
): Promise<void> {
  await db.prepare(`
    UPDATE dpias
    SET art36_submitted_at = datetime('now'),
        status = 'art36-required'
    WHERE id = ?1
  `).bind(dpiaId).run();

  // Log for audit trail — DPA has 8 weeks to respond (Art.36(2))
  await db.prepare(`
    INSERT INTO dpia_art36_log (id, dpia_id, dpa_reference, submitted_at, deadline_at)
    VALUES (?1,?2,?3,datetime('now'), datetime('now','+56 days'))
  `).bind(crypto.randomUUID(), dpiaId, dpaReference).run();
}
```

## Periodic DPIA Review Scheduler

```typescript
// workers/dpia/review-cron.ts — Cron: 0 7 * * 1
export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const { results } = await env.DPIA_DB.prepare(`
      SELECT id, title, processing_owner, review_due_at, residual_risk
      FROM dpias
      WHERE review_due_at < datetime('now', '+60 days')
        AND status IN ('approved', 'art36-required')
      ORDER BY review_due_at ASC
    `).all();

    if (!results.length) return;

    await fetch(env.DPO_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alert: 'GDPR Art.35 DPIA Review Due',
        count: results.length,
        items: results,
      })
    });
  }
} satisfies ExportedHandler<Env>;
```

**Anti-patterns**

- Completing the DPIA after launching the processing — Art. 35(1) requires the DPIA *before* starting; a retrospective DPIA is an enforcement finding, not a cure.
- Treating the DPIA as a one-time document — Art. 35(11) requires review "when there is a change of the risk represented by processing operations"; schedule periodic reviews via the Cron trigger.
- Using "high risk" as a pass/fail gate without quantifying residual risk — regulators expect a risk matrix with *before* and *after mitigation* scores, not just a narrative.
- Storing DPIA documents only in DPIA team email threads — the D1 registry provides queryable evidence; link documents to R2 with immutable URLs for audit purposes.

**Gotchas**

- EDPB Guidelines 09/2022 replaced the older WP248; supervisory authorities now expect the nine-criteria framework, not the older three-scenario-only interpretation.
- Art. 35(9) requires the controller to "seek the views of data subjects or their representatives" where appropriate — document whether this was done and why/why not in `processing_desc`.
- A DPIA for one purpose does not cover scope expansion; when a Worker is repurposed (e.g., analytics logs later used for fraud scoring), a new trigger assessment is required.
- Art. 36 prior consultation suspends the 8-week response clock only after the DPA acknowledges receipt — track `art36_submitted_at` separately from the DPA's acknowledgement date.

**Verification**

```bash
# All DPIAs with high residual risk
wrangler d1 execute DPIA_DB --command \
  "SELECT title, processing_owner, residual_risk, dpo_outcome FROM dpias WHERE residual_risk='high';"

# DPIAs overdue for periodic review
wrangler d1 execute DPIA_DB --command \
  "SELECT title, review_due_at FROM dpias WHERE review_due_at < datetime('now') AND status='approved';"

# Open risks with score >= 16 across all DPIAs
wrangler d1 execute DPIA_DB --command \
  "SELECT dpia_id, threat, residual_score FROM dpia_risks WHERE residual_score >= 16 AND status='open';"
```

**Related**

- `ai-dpia-data-protection-impact-assessment.md`
- `gdpr-legitimate-interest-balancing-test-workers.md`
- `gdpr-article-30-ropa-automation.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `automated-decision-making-profiling-transparency.md`
- `gdpr-dpo-role-requirements.md`

**Sources**

- GDPR Articles 35 and 36 — Data Protection Impact Assessment and Prior Consultation
- EDPB Guidelines 09/2022 on Data Protection Impact Assessment (replacing WP248)
- EDPB Guidelines 04/2019 on Article 25 — Data Protection by Design and by Default
- ICO Guidance — When do we need to do a DPIA? (2023)
- CNIL DPIA Methodology — PIA (Privacy Impact Assessment) Guide v3
