# GDPR Data Processor Agreement Audit with D1 Evidence Store

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**

GDPR Article 28(3)(h) requires controllers to audit their data processors or commission audits on their behalf. Article 28(1) requires controllers to use only processors providing "sufficient guarantees" — and this must be re-evaluated periodically, not just at onboarding. Organisations running Cloudflare Workers need a mechanism to: store processor agreements (DPAs) and their key obligations, track assessment results, schedule periodic re-assessments, and produce regulator-ready evidence that due diligence is ongoing. This article models that workflow using D1 as the audit evidence store.

**Context**

A data processor (Art. 4(8)) processes personal data on the controller's behalf. Cloudflare itself acts as a processor to the controller who deploys Workers. Third-party processors invoked from Workers (payment processors, analytics SDKs, email providers, AI inference APIs) are sub-processors. Art. 28(4) requires the same obligations flow down to sub-processors. The DPA must include: processing subject matter and duration, nature and purpose, type of personal data, categories of data subjects, and the controller's obligations (Art. 28(3) (a)–(h)).

---

## D1 Schema for Processor Registry

```sql
-- migrations/0001_processor_registry.sql
CREATE TABLE IF NOT EXISTS processors (
  id             TEXT PRIMARY KEY,          -- uuid
  name           TEXT NOT NULL,
  role           TEXT NOT NULL,             -- processor | sub-processor
  dpa_signed_at  TEXT,
  dpa_version    TEXT,
  dpa_url        TEXT,                      -- internal document URL
  legal_basis    TEXT,                      -- Art.28 + SCCs | BCRs | adequacy
  processing_purposes TEXT NOT NULL,        -- comma-separated Art.28(3) subjects
  personal_data_types TEXT NOT NULL,        -- e.g. "email,IP,payment_data"
  data_subjects  TEXT NOT NULL,             -- e.g. "customers,employees"
  sub_processors TEXT,                      -- JSON array of sub-processor names
  next_review_at TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'active',
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processor_audits (
  id              TEXT PRIMARY KEY,
  processor_id    TEXT NOT NULL REFERENCES processors(id),
  audit_type      TEXT NOT NULL,   -- questionnaire | doc-review | on-site | third-party-cert
  auditor         TEXT NOT NULL,
  conducted_at    TEXT NOT NULL,
  outcome         TEXT NOT NULL,   -- pass | conditional-pass | fail
  findings        TEXT,            -- JSON array of finding objects
  remediation_due TEXT,
  closed_at       TEXT,
  evidence_url    TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_processor_next_review ON processors(next_review_at);
CREATE INDEX IF NOT EXISTS idx_audit_processor       ON processor_audits(processor_id);
CREATE INDEX IF NOT EXISTS idx_audit_outcome         ON processor_audits(outcome);
```

## Processor Registration Worker

```typescript
// workers/processor-registry/register.ts
export interface Env { PROCESSOR_DB: D1Database }

interface RegisterProcessorBody {
  name: string;
  role: 'processor' | 'sub-processor';
  dpaVersion: string;
  dpaUrl: string;
  legalBasis: string;
  processingPurposes: string[];
  personalDataTypes: string[];
  dataSubjects: string[];
  subProcessors?: string[];
  reviewIntervalDays?: number;   // default 365
}

export async function registerProcessor(
  body: RegisterProcessorBody,
  db: D1Database
): Promise<string> {
  const id = crypto.randomUUID();
  const reviewDays = body.reviewIntervalDays ?? 365;
  const nextReview = new Date(Date.now() + reviewDays * 86400 * 1000).toISOString();

  await db.prepare(`
    INSERT INTO processors
      (id, name, role, dpa_version, dpa_url, legal_basis,
       processing_purposes, personal_data_types, data_subjects,
       sub_processors, next_review_at)
    VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)
  `).bind(
    id, body.name, body.role, body.dpaVersion, body.dpaUrl, body.legalBasis,
    body.processingPurposes.join(','),
    body.personalDataTypes.join(','),
    body.dataSubjects.join(','),
    JSON.stringify(body.subProcessors ?? []),
    nextReview
  ).run();

  return id;
}
```

## Art. 28(3)(h) Audit Questionnaire Submission

```typescript
// workers/processor-registry/audit.ts
interface AuditFinding {
  control: string;     // e.g. "Art.28(3)(c) — sub-processor notification"
  severity: 'critical' | 'major' | 'minor' | 'observation';
  description: string;
  remediationRequired: boolean;
}

interface SubmitAuditBody {
  processorId: string;
  auditType: 'questionnaire' | 'doc-review' | 'on-site' | 'third-party-cert';
  auditor: string;
  conductedAt: string;
  findings: AuditFinding[];
  evidenceUrl?: string;
}

export async function submitAudit(
  body: SubmitAuditBody,
  db: D1Database
): Promise<{ auditId: string; outcome: string }> {
  const hasCritical = body.findings.some(f => f.severity === 'critical');
  const hasMajor    = body.findings.some(f => f.severity === 'major');
  const outcome = hasCritical ? 'fail' : hasMajor ? 'conditional-pass' : 'pass';

  const remediationDue = hasCritical || hasMajor
    ? new Date(Date.now() + 30 * 86400 * 1000).toISOString()  // 30-day remediation window
    : null;

  const auditId = crypto.randomUUID();

  await db.batch([
    db.prepare(`
      INSERT INTO processor_audits
        (id, processor_id, audit_type, auditor, conducted_at,
         outcome, findings, remediation_due, evidence_url)
      VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)
    `).bind(
      auditId, body.processorId, body.auditType, body.auditor, body.conductedAt,
      outcome, JSON.stringify(body.findings), remediationDue, body.evidenceUrl ?? null
    ),
    // Update processor status if audit failed
    ...(hasCritical ? [
      db.prepare(
        `UPDATE processors SET status = 'suspended' WHERE id = ?1`
      ).bind(body.processorId)
    ] : []),
    // Reset review clock on pass
    ...(outcome === 'pass' ? [
      db.prepare(
        `UPDATE processors SET next_review_at = datetime('now', '+365 days') WHERE id = ?1`
      ).bind(body.processorId)
    ] : [])
  ]);

  return { auditId, outcome };
}
```

## Scheduled Review Reminder

```typescript
// workers/processor-registry/scheduler.ts — Cron: 0 8 * * 1 (Monday 08:00 UTC)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Processors due for review in the next 30 days
    const { results } = await env.PROCESSOR_DB.prepare(`
      SELECT id, name, next_review_at, status
      FROM processors
      WHERE next_review_at < datetime('now', '+30 days')
        AND status = 'active'
      ORDER BY next_review_at ASC
    `).all<{ id: string; name: string; next_review_at: string; status: string }>();

    if (results.length === 0) return;

    // Overdue — processors past review date
    const overdue = results.filter(p => p.next_review_at < new Date().toISOString());

    await fetch(env.ALERT_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        summary: `GDPR Art.28 Processor Review — ${results.length} due, ${overdue.length} overdue`,
        due_soon: results,
      })
    });
  }
} satisfies ExportedHandler<Env>;
```

## Regulator Evidence Export

```typescript
// workers/processor-registry/export.ts
// Produce Art. 28 audit trail for DPA / supervisory authority requests
export async function buildAuditTrail(
  processorId: string,
  db: D1Database
): Promise<Record<string, unknown>> {
  const [processor, audits] = await Promise.all([
    db.prepare(`SELECT * FROM processors WHERE id = ?1`).bind(processorId).first(),
    db.prepare(
      `SELECT * FROM processor_audits WHERE processor_id = ?1 ORDER BY conducted_at DESC`
    ).bind(processorId).all(),
  ]);

  if (!processor) throw new Error('Processor not found');

  return {
    export_date: new Date().toISOString(),
    gdpr_basis: 'Article 28 — Controller due diligence obligation',
    processor,
    audit_history: audits.results,
    summary: {
      total_audits: audits.results.length,
      last_outcome: (audits.results[0] as Record<string, string>)?.outcome ?? 'not-yet-audited',
      open_findings: audits.results.flatMap(
        a => (JSON.parse((a as Record<string, string>).findings ?? '[]') as AuditFinding[])
             .filter(f => f.remediationRequired)
      ).length,
    }
  };
}
```

**Anti-patterns**

- Relying on the processor's own certifications (ISO 27001, SOC 2) as the sole Art. 28(3)(h) audit mechanism without verifying scope covers your processing activities — certifications are inputs to the assessment, not replacements for it.
- Storing DPAs only as file attachments outside D1 — the Worker needs queryable metadata (next review date, status) to automate scheduling; binary blobs belong in R2 with a D1 reference.
- Setting `next_review_at` to a fixed far-future date after a `conditional-pass` — conditional passes require re-audit after remediation, not a full 12-month cycle reset.
- Treating sub-processor lists as static after DPA signature — Art. 28(4) requires notification of sub-processor changes; store `sub_processors` as a versioned JSON column and diff on update.

**Gotchas**

- GDPR Art. 28(3)(h) gives the controller the *right* to audit, but most DPAs allow processors to substitute an independent third-party audit (e.g., ISO 27001 certificate). If you accept this, document the substitution decision in the audit record.
- Supervisory authorities increasingly request evidence of *periodic* re-assessment, not just onboarding DPA signature. The `processor_audits` table timestamps are your primary evidence.
- Sub-processors located outside the EEA require their own transfer mechanism (SCC, BCR, adequacy decision). Link this to `cross-border-data-transfer-mechanisms.md` in the processor record.
- Art. 28(9) requires DPAs to be "set out in writing, including in electronic form" — ensure `dpa_url` points to an immutable, timestamped copy (e.g., R2 object with versioning enabled).

**Verification**

```bash
# All active processors with overdue reviews
wrangler d1 execute PROCESSOR_DB --command \
  "SELECT name, next_review_at, status FROM processors
   WHERE next_review_at < datetime('now') AND status='active';"

# Open findings across all processors
wrangler d1 execute PROCESSOR_DB --command \
  "SELECT p.name, a.outcome, a.remediation_due
   FROM processor_audits a JOIN processors p ON a.processor_id = p.id
   WHERE a.closed_at IS NULL AND a.outcome != 'pass';"
```

**Related**

- `gdpr-dpa-standard-contractual-clauses.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `cross-border-data-transfer-mechanisms.md`
- `gdpr-article-30-ropa-automation.md`
- `vendor-security-assessment.md`
- `audit-log-mandatory.md`

**Sources**

- GDPR Article 28 — Processor obligations and controller duties
- GDPR Article 4(8) — Definition of processor
- EDPB Guidelines 07/2020 on the concepts of controller and processor
- European Data Protection Board — Recommendations 01/2020 on supplementary measures for transfers
- ICO Guidance — Using processors: getting the contract right (2023)
