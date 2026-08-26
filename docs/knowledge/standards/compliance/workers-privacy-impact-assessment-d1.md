# Privacy Impact Assessment (PIA) Workflow with Cloudflare Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

GDPR Article 35 mandates a Data Protection Impact Assessment (DPIA) before processing that is "likely to result in a high risk to the rights and freedoms of natural persons". Without a structured workflow, DPIAs are written inconsistently, lose track of open risk items, and sit in email threads where auditors cannot find them. Development teams delay launches because they cannot demonstrate that a DPIA exists and was approved.

This article builds a PIA/DPIA workflow engine on Cloudflare Workers + D1 that: triggers assessments on new project intake, maps data flows, identifies risks, assigns reviewers, tracks outcomes, and provides an auditor-facing report endpoint.

## Context

Applies when:
- Your organisation operates under GDPR, UK GDPR, or equivalent privacy law
- Engineering teams are launching features that involve new categories of personal data
- Your DPO (Data Protection Officer) needs a dashboard of pending DPIAs and their status
- You want to integrate PIA initiation into your project intake form or Jira/Linear workflow

A DPIA is mandatory when processing involves: systematic profiling, large-scale processing of special-category data, large-scale monitoring of public areas, or novel technologies with uncertain privacy risks (Article 35(3)).

## Solution

### D1 Schema

```sql
CREATE TABLE IF NOT EXISTS pia (
  id              TEXT PRIMARY KEY,          -- e.g. "pia_2026_001"
  title           TEXT NOT NULL,
  project_id      TEXT,                      -- link to external project tracker
  initiated_by    TEXT NOT NULL,
  dpo_assigned    TEXT,
  reviewer_ids    TEXT,                      -- JSON array of reviewer user IDs
  status          TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT|IN_REVIEW|APPROVED|REJECTED|ARCHIVED
  pia_type        TEXT NOT NULL DEFAULT 'PIA',    -- PIA | DPIA
  high_risk_flags TEXT,                      -- JSON array of GDPR Art.35 flags triggered
  outcome         TEXT,                      -- PROCEED|PROCEED_WITH_MITIGATIONS|HALT
  outcome_notes   TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  approved_at     TEXT,
  review_deadline TEXT
);

CREATE TABLE IF NOT EXISTS pia_data_flow (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  pia_id       TEXT NOT NULL REFERENCES pia(id),
  step_order   INTEGER NOT NULL,
  description  TEXT NOT NULL,
  data_categories TEXT NOT NULL,   -- JSON array: ["name","email","health_data"]
  actors       TEXT NOT NULL,      -- JSON array: systems/persons involved
  transfer_mechanism TEXT,         -- e.g. "SCCs", "Adequacy Decision"
  third_country INTEGER NOT NULL DEFAULT 0,  -- 1 if data leaves EEA
  lawful_basis TEXT NOT NULL,      -- CONSENT|CONTRACT|LEGAL_OBLIGATION|VITAL_INTERESTS|PUBLIC_TASK|LEGITIMATE_INTERESTS
  retention_days INTEGER,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pia_risk (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  pia_id        TEXT NOT NULL REFERENCES pia(id),
  risk_title    TEXT NOT NULL,
  description   TEXT NOT NULL,
  likelihood    INTEGER NOT NULL CHECK(likelihood BETWEEN 1 AND 5),
  impact        INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 5),
  risk_score    INTEGER GENERATED ALWAYS AS (likelihood * impact) VIRTUAL,
  risk_level    TEXT NOT NULL,     -- LOW|MEDIUM|HIGH|VERY_HIGH
  mitigation    TEXT,
  mitigation_status TEXT DEFAULT 'OPEN',  -- OPEN|IN_PROGRESS|CLOSED
  owner         TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pia_comment (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  pia_id     TEXT NOT NULL REFERENCES pia(id),
  author_id  TEXT NOT NULL,
  role       TEXT NOT NULL DEFAULT 'REVIEWER',  -- INITIATOR|DPO|REVIEWER|AUDITOR
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_pia_status   ON pia(status);
CREATE INDEX idx_pia_project  ON pia(project_id);
CREATE INDEX idx_pia_risk_pia ON pia_risk(pia_id);
```

### Worker: privacy-impact.ts

```typescript
import type { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
}

type PiaStatus = 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'REJECTED' | 'ARCHIVED';
type PiaType = 'PIA' | 'DPIA';
type LawfulBasis =
  | 'CONSENT'
  | 'CONTRACT'
  | 'LEGAL_OBLIGATION'
  | 'VITAL_INTERESTS'
  | 'PUBLIC_TASK'
  | 'LEGITIMATE_INTERESTS';

// ----- DPIA trigger evaluation -----

const DPIA_TRIGGERS: Array<{ flag: string; label: string }> = [
  { flag: 'SYSTEMATIC_PROFILING',   label: 'Systematic profiling with legal/significant effects' },
  { flag: 'LARGE_SCALE_SPECIAL',    label: 'Large-scale processing of special-category data' },
  { flag: 'PUBLIC_AREA_MONITORING', label: 'Systematic monitoring of publicly accessible areas' },
  { flag: 'NOVEL_TECHNOLOGY',       label: 'Use of novel technology with uncertain privacy risk' },
  { flag: 'CROSS_CONTEXT_COMBINE',  label: 'Combining data sets in ways individuals would not expect' },
  { flag: 'VULNERABLE_SUBJECTS',    label: 'Processing data of vulnerable individuals (children, patients)' },
  { flag: 'THIRD_COUNTRY_TRANSFER', label: 'Transfer of data to a third country without adequacy decision' },
];

export function evaluateDpiaRequired(flags: string[]): {
  required: boolean;
  triggeredFlags: Array<{ flag: string; label: string }>;
} {
  const triggered = DPIA_TRIGGERS.filter((t) => flags.includes(t.flag));
  // GDPR Art.35: DPIA required when 2+ WP29 criteria are met, or when any single criterion is especially severe
  const severeFlags = ['LARGE_SCALE_SPECIAL', 'PUBLIC_AREA_MONITORING', 'SYSTEMATIC_PROFILING'];
  const hasSevere = triggered.some((t) => severeFlags.includes(t.flag));
  return {
    required: triggered.length >= 2 || hasSevere,
    triggeredFlags: triggered,
  };
}

// ----- PIA lifecycle -----

function generatePiaId(): string {
  const year = new Date().getFullYear();
  const rand = Math.random().toString(36).slice(2, 7).toUpperCase();
  return `pia_${year}_${rand}`;
}

export async function initiatePia(
  db: D1Database,
  input: {
    title: string;
    projectId?: string;
    initiatedBy: string;
    dpoAssigned?: string;
    highRiskFlags?: string[];
    reviewDeadlineDays?: number;
  }
): Promise<{ id: string; piaType: PiaType; dpiaRequired: boolean }> {
  const flags = input.highRiskFlags ?? [];
  const { required: dpiaRequired, triggeredFlags } = evaluateDpiaRequired(flags);
  const piaType: PiaType = dpiaRequired ? 'DPIA' : 'PIA';
  const id = generatePiaId();

  const reviewDeadline = input.reviewDeadlineDays
    ? new Date(Date.now() + input.reviewDeadlineDays * 86_400_000).toISOString().slice(0, 10)
    : null;

  await db
    .prepare(
      `INSERT INTO pia
         (id, title, project_id, initiated_by, dpo_assigned, pia_type,
          high_risk_flags, review_deadline)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      id,
      input.title,
      input.projectId ?? null,
      input.initiatedBy,
      input.dpoAssigned ?? null,
      piaType,
      JSON.stringify(triggeredFlags.map((t) => t.flag)),
      reviewDeadline
    )
    .run();

  return { id, piaType, dpiaRequired };
}

export async function addDataFlow(
  db: D1Database,
  piaId: string,
  flow: {
    stepOrder: number;
    description: string;
    dataCategories: string[];
    actors: string[];
    lawfulBasis: LawfulBasis;
    transferMechanism?: string;
    thirdCountry?: boolean;
    retentionDays?: number;
  }
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pia_data_flow
         (pia_id, step_order, description, data_categories, actors,
          transfer_mechanism, third_country, lawful_basis, retention_days)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      piaId,
      flow.stepOrder,
      flow.description,
      JSON.stringify(flow.dataCategories),
      JSON.stringify(flow.actors),
      flow.transferMechanism ?? null,
      flow.thirdCountry ? 1 : 0,
      flow.lawfulBasis,
      flow.retentionDays ?? null
    )
    .run();
}

export async function addRisk(
  db: D1Database,
  piaId: string,
  risk: {
    riskTitle: string;
    description: string;
    likelihood: 1 | 2 | 3 | 4 | 5;
    impact: 1 | 2 | 3 | 4 | 5;
    mitigation?: string;
    owner?: string;
  }
): Promise<void> {
  const score = risk.likelihood * risk.impact;
  const riskLevel =
    score >= 20 ? 'VERY_HIGH' : score >= 12 ? 'HIGH' : score >= 6 ? 'MEDIUM' : 'LOW';

  await db
    .prepare(
      `INSERT INTO pia_risk
         (pia_id, risk_title, description, likelihood, impact, risk_level,
          mitigation, owner)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      piaId,
      risk.riskTitle,
      risk.description,
      risk.likelihood,
      risk.impact,
      riskLevel,
      risk.mitigation ?? null,
      risk.owner ?? null
    )
    .run();
}

export async function updatePiaStatus(
  db: D1Database,
  piaId: string,
  status: PiaStatus,
  options: { outcome?: string; outcomeNotes?: string } = {}
): Promise<void> {
  const approvedAt = status === 'APPROVED' ? new Date().toISOString() : null;
  await db
    .prepare(
      `UPDATE pia SET status = ?, outcome = ?, outcome_notes = ?,
         approved_at = COALESCE(?, approved_at), updated_at = datetime('now')
       WHERE id = ?`
    )
    .bind(
      status,
      options.outcome ?? null,
      options.outcomeNotes ?? null,
      approvedAt,
      piaId
    )
    .run();
}

export async function getPiaReport(db: D1Database, piaId: string): Promise<Record<string, unknown>> {
  const [header, flows, risks, comments] = await Promise.all([
    db.prepare('SELECT * FROM pia WHERE id = ?').bind(piaId).first(),
    db.prepare('SELECT * FROM pia_data_flow WHERE pia_id = ? ORDER BY step_order').bind(piaId).all(),
    db.prepare('SELECT * FROM pia_risk WHERE pia_id = ? ORDER BY risk_score DESC').bind(piaId).all(),
    db.prepare('SELECT * FROM pia_comment WHERE pia_id = ? ORDER BY created_at').bind(piaId).all(),
  ]);

  if (!header) throw new Error(`PIA ${piaId} not found`);

  return {
    pia: header,
    dataFlows: flows.results,
    risks: risks.results,
    riskSummary: {
      total: risks.results.length,
      openHigh: (risks.results as Array<{ risk_level: string; mitigation_status: string }>).filter(
        (r) => r.risk_level === 'HIGH' || r.risk_level === 'VERY_HIGH'
      ).filter((r) => r.mitigation_status === 'OPEN').length,
    },
    comments: comments.results,
  };
}

// ----- HTTP handler -----

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/pia') {
      const body = await request.json<Parameters<typeof initiatePia>[1]>();
      const result = await initiatePia(env.DB, body);
      return Response.json(result, { status: 201 });
    }

    const piaMatch = url.pathname.match(/^\/pia\/([^\/]+)(\/.*)?$/);

    if (piaMatch && request.method === 'GET' && !piaMatch[2]) {
      const report = await getPiaReport(env.DB, piaMatch[1]);
      return Response.json(report);
    }

    if (piaMatch && request.method === 'POST' && piaMatch[2] === '/data-flows') {
      const body = await request.json<Parameters<typeof addDataFlow>[2]>();
      await addDataFlow(env.DB, piaMatch[1], body);
      return Response.json({ ok: true }, { status: 201 });
    }

    if (piaMatch && request.method === 'POST' && piaMatch[2] === '/risks') {
      const body = await request.json<Parameters<typeof addRisk>[2]>();
      await addRisk(env.DB, piaMatch[1], body);
      return Response.json({ ok: true }, { status: 201 });
    }

    if (piaMatch && request.method === 'PATCH' && piaMatch[2] === '/status') {
      const body = await request.json<{ status: PiaStatus; outcome?: string; outcomeNotes?: string }>();
      await updatePiaStatus(env.DB, piaMatch[1], body.status, body);
      return Response.json({ ok: true });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

### Listing overdue PIAs for the DPO dashboard

```typescript
export async function getOverduePias(
  db: D1Database
): Promise<Array<Record<string, unknown>>> {
  const today = new Date().toISOString().slice(0, 10);
  const rows = await db
    .prepare(
      `SELECT id, title, pia_type, status, initiated_by, dpo_assigned, review_deadline
       FROM pia
       WHERE status IN ('DRAFT', 'IN_REVIEW')
         AND review_deadline IS NOT NULL
         AND review_deadline < ?
       ORDER BY review_deadline ASC`
    )
    .bind(today)
    .all();
  return rows.results;
}
```

## Anti-patterns

- **Never mark a PIA as APPROVED without DPO sign-off when DPIA is required** — GDPR Article 36 mandates prior consultation with the supervisory authority if the DPO determines the residual risk remains high after mitigation.
- **Do not scope a PIA to only the new feature** — the DPIA must describe the entire processing operation, including pre-existing data flows that interact with the new feature.
- **Avoid a binary risk matrix (HIGH/LOW only)** — use at least a 5×5 matrix so that medium risks are tracked and not silently ignored.
- **Do not delete rejected PIAs** — set status to REJECTED or ARCHIVED and retain for audit trail. Hard deletes break the chain of evidence.

## Gotchas

- **Generated columns (`VIRTUAL`)** in D1 require SQLite 3.31+ — Cloudflare's D1 runtime satisfies this, but local `better-sqlite3` dev environments may not. Test with `wrangler dev --remote` for schema parity.
- **Reviewer notification**: the handler does not send email; wire up a Queue or use `ctx.waitUntil(sendEmail(...))` in the `updatePiaStatus` path to notify reviewers when status changes to `IN_REVIEW`.
- **Data flow `actors` field** is stored as JSON — add a read-time parse to surface it as an array in the API response.
- **DPIA mandatory consultation**: if all risks are scored VERY_HIGH and no mitigations close them, GDPR requires notifying the supervisory authority before processing begins. Build an alert into the `updatePiaStatus` flow for this edge case.

## Verification

```bash
# Initiate a DPIA (two Art.35 flags triggered)
curl -X POST https://pia.example.workers.dev/pia \
  -H 'Content-Type: application/json' \
  -d '{"title":"Behavioural Ad Targeting V2","initiatedBy":"eng_team","highRiskFlags":["SYSTEMATIC_PROFILING","CROSS_CONTEXT_COMBINE"],"reviewDeadlineDays":14}'
# Expected: {"id":"pia_2026_XXXXX","piaType":"DPIA","dpiaRequired":true}

# Add a data flow step
curl -X POST https://pia.example.workers.dev/pia/pia_2026_XXXXX/data-flows \
  -H 'Content-Type: application/json' \
  -d '{"stepOrder":1,"description":"Collect browsing events via analytics SDK","dataCategories":["page_url","user_id","timestamp"],"actors":["browser","analytics-worker","D1"],"lawfulBasis":"CONSENT","retentionDays":90}'

# Add a risk
curl -X POST https://pia.example.workers.dev/pia/pia_2026_XXXXX/risks \
  -H 'Content-Type: application/json' \
  -d '{"riskTitle":"Re-identification via cross-context profiling","description":"Combining ad clicks with purchase history may re-identify pseudonymised users","likelihood":3,"impact":5,"mitigation":"Apply k-anonymity; minimum cohort size of 100","owner":"privacy_eng"}'

# Get full report
curl https://pia.example.workers.dev/pia/pia_2026_XXXXX
```

## Related

- `workers-data-classification-labels-d1.md` — feed classification inventory into data flow maps
- `workers-vendor-risk-assessment-d1.md` — trigger a DPIA when a HIGH-risk vendor is added
- `workers-cookie-consent-management-kv.md` — DPIA should cover consent mechanism itself

## Sources

- https://developers.cloudflare.com/d1/
- https://gdpr.eu/article-35-impact-assessment/
- https://edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201904_dataprotection_by_design_and_by_default_v2.0_en.pdf
- https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/accountability-and-governance/data-protection-impact-assessments/
