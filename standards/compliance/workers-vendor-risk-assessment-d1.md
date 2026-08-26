# Third-Party Vendor Risk Assessment Tracking with Cloudflare Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Every SaaS company relies on third-party vendors: payment processors, cloud providers, analytics SDKs, support tools. A single compromised vendor can cascade into a major breach (e.g., SolarWinds, MOVEit). Without a programmatic vendor risk register, security teams manage this in spreadsheets that go stale, miss periodic review deadlines, and provide no machine-readable evidence for auditors.

This article builds a vendor risk assessment tracking system on Cloudflare Workers + D1 that: captures onboarding questionnaires, computes risk scores, classifies vendors into tiers (High/Medium/Low), schedules periodic reviews, and runs automated integration health checks.

## Context

Applies when:
- Your organisation is pursuing SOC 2 Type II and needs a vendor risk management section
- You exchange customer data with third parties and must document the controls they have in place
- Internal policy requires annual (or more frequent) vendor reviews with documented evidence
- You want to alert the security team when a vendor's health check starts failing

## Solution

### D1 Schema

```sql
CREATE TABLE IF NOT EXISTS vendor (
  id              TEXT PRIMARY KEY,   -- e.g. "vendor_stripe"
  name            TEXT NOT NULL,
  website         TEXT,
  category        TEXT NOT NULL,      -- PAYMENT | INFRASTRUCTURE | ANALYTICS | SUPPORT | OTHER
  data_access     TEXT NOT NULL,      -- NONE | ANONYMOUS | PSEUDONYMOUS | IDENTIFIED | SENSITIVE
  data_shared     TEXT,               -- description of data categories shared
  subprocessor    INTEGER NOT NULL DEFAULT 0,  -- 1 = GDPR sub-processor
  contact_email   TEXT,
  contract_expiry TEXT,               -- ISO date
  risk_tier       TEXT,               -- HIGH | MEDIUM | LOW (computed)
  risk_score      INTEGER,            -- 0-100
  last_reviewed   TEXT,
  next_review_due TEXT,
  status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|ACTIVE|SUSPENDED|OFFBOARDED
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vendor_questionnaire (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor_id    TEXT NOT NULL REFERENCES vendor(id),
  version      INTEGER NOT NULL DEFAULT 1,
  submitted_by TEXT NOT NULL,
  submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
  answers      TEXT NOT NULL,   -- JSON: {questionId: answer}
  score        INTEGER NOT NULL,
  risk_tier    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor_health_check (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor_id    TEXT NOT NULL REFERENCES vendor(id),
  checked_at   TEXT NOT NULL DEFAULT (datetime('now')),
  endpoint     TEXT NOT NULL,
  status_code  INTEGER,
  latency_ms   INTEGER,
  ok           INTEGER NOT NULL DEFAULT 0,
  error        TEXT
);

CREATE INDEX idx_vendor_tier       ON vendor(risk_tier);
CREATE INDEX idx_vendor_review_due ON vendor(next_review_due);
CREATE INDEX idx_vhc_vendor        ON vendor_health_check(vendor_id, checked_at);
```

### Risk scoring model

```typescript
// src/risk-scoring.ts

interface QuestionnaireAnswers {
  has_soc2: boolean;              // +20 if true (negative means subtract)
  has_iso27001: boolean;          // +15
  has_penetration_test: boolean;  // +10
  data_encrypted_at_rest: boolean; // +15
  data_encrypted_in_transit: boolean; // +10
  incident_response_plan: boolean; // +10
  sub_processors_documented: boolean; // +5
  data_residency_eu: boolean;     // +5 (lower risk for EU workloads)
  breach_in_last_2y: boolean;     // -30 if true (penalty)
  sla_uptime_pct: number;         // maps to 0–10 bonus
}

export function computeRiskScore(answers: QuestionnaireAnswers): number {
  let score = 50; // baseline
  if (answers.has_soc2)                  score += 20;
  if (answers.has_iso27001)              score += 15;
  if (answers.has_penetration_test)      score += 10;
  if (answers.data_encrypted_at_rest)    score += 15;
  if (answers.data_encrypted_in_transit) score += 10;
  if (answers.incident_response_plan)    score += 10;
  if (answers.sub_processors_documented) score += 5;
  if (answers.data_residency_eu)         score += 5;
  if (answers.breach_in_last_2y)         score -= 30;

  // SLA bonus: 0 at 99%, up to 10 at 99.99%
  const slaNormalised = Math.min(Math.max((answers.sla_uptime_pct - 99) / 0.0099, 0), 10);
  score += Math.round(slaNormalised);

  return Math.min(100, Math.max(0, score));
}

export function scoreToTier(score: number): 'HIGH' | 'MEDIUM' | 'LOW' {
  if (score >= 75) return 'LOW';
  if (score >= 50) return 'MEDIUM';
  return 'HIGH';
}

export function reviewIntervalDays(tier: 'HIGH' | 'MEDIUM' | 'LOW'): number {
  return tier === 'HIGH' ? 90 : tier === 'MEDIUM' ? 180 : 365;
}
```

### Worker: vendor-risk.ts

```typescript
import type { D1Database } from '@cloudflare/workers-types';
import { computeRiskScore, scoreToTier, reviewIntervalDays } from './risk-scoring';

export interface Env {
  DB: D1Database;
}

// ----- Vendor CRUD -----

interface VendorInput {
  id: string;
  name: string;
  website?: string;
  category: string;
  dataAccess: string;
  dataShared?: string;
  subprocessor?: boolean;
  contactEmail?: string;
  contractExpiry?: string;
}

export async function upsertVendor(db: D1Database, v: VendorInput): Promise<void> {
  await db
    .prepare(
      `INSERT INTO vendor
         (id, name, website, category, data_access, data_shared,
          subprocessor, contact_email, contract_expiry)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         name = excluded.name,
         category = excluded.category,
         data_access = excluded.data_access,
         updated_at = datetime('now')`
    )
    .bind(
      v.id, v.name, v.website ?? null, v.category, v.dataAccess,
      v.dataShared ?? null, v.subprocessor ? 1 : 0,
      v.contactEmail ?? null, v.contractExpiry ?? null
    )
    .run();
}

// ----- Questionnaire submission -----

export async function submitQuestionnaire(
  db: D1Database,
  vendorId: string,
  submittedBy: string,
  answers: Record<string, unknown>
): Promise<{ score: number; tier: string; nextReviewDue: string }> {
  const score = computeRiskScore(answers as Parameters<typeof computeRiskScore>[0]);
  const tier = scoreToTier(score);
  const intervalDays = reviewIntervalDays(tier);
  const nextReviewDue = new Date(
    Date.now() + intervalDays * 86_400_000
  ).toISOString().slice(0, 10);

  // Get current version number
  const last = await db
    .prepare('SELECT MAX(version) as v FROM vendor_questionnaire WHERE vendor_id = ?')
    .bind(vendorId)
    .first<{ v: number | null }>();
  const version = (last?.v ?? 0) + 1;

  await db
    .prepare(
      `INSERT INTO vendor_questionnaire
         (vendor_id, version, submitted_by, answers, score, risk_tier)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(vendorId, version, submittedBy, JSON.stringify(answers), score, tier)
    .run();

  await db
    .prepare(
      `UPDATE vendor SET
         risk_score = ?, risk_tier = ?, last_reviewed = date('now'),
         next_review_due = ?, status = 'ACTIVE', updated_at = datetime('now')
       WHERE id = ?`
    )
    .bind(score, tier, nextReviewDue, vendorId)
    .run();

  return { score, tier, nextReviewDue };
}

// ----- Health check runner -----

export async function runHealthCheck(
  db: D1Database,
  vendorId: string,
  endpoint: string
): Promise<{ ok: boolean; statusCode?: number; latencyMs: number }> {
  const start = Date.now();
  let statusCode: number | undefined;
  let error: string | undefined;
  let ok = false;

  try {
    const res = await fetch(endpoint, {
      method: 'HEAD',
      signal: AbortSignal.timeout(10_000),
    });
    statusCode = res.status;
    ok = res.ok;
  } catch (e) {
    error = String(e);
  }

  const latencyMs = Date.now() - start;

  await db
    .prepare(
      `INSERT INTO vendor_health_check
         (vendor_id, endpoint, status_code, latency_ms, ok, error)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(vendorId, endpoint, statusCode ?? null, latencyMs, ok ? 1 : 0, error ?? null)
    .run();

  return { ok, statusCode, latencyMs };
}

// ----- Due-for-review query -----

export async function getVendorsDueForReview(
  db: D1Database,
  withinDays = 7
): Promise<Array<{ id: string; name: string; risk_tier: string; next_review_due: string }>> {
  const cutoff = new Date(
    Date.now() + withinDays * 86_400_000
  ).toISOString().slice(0, 10);

  const rows = await db
    .prepare(
      `SELECT id, name, risk_tier, next_review_due
       FROM vendor
       WHERE next_review_due <= ? AND status = 'ACTIVE'
       ORDER BY next_review_due ASC`
    )
    .bind(cutoff)
    .all<{ id: string; name: string; risk_tier: string; next_review_due: string }>();

  return rows.results;
}

// ----- HTTP handler -----

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/vendors') {
      const body = await request.json<VendorInput>();
      await upsertVendor(env.DB, body);
      return Response.json({ ok: true }, { status: 201 });
    }

    const vendorMatch = url.pathname.match(/^\/vendors\/([^\/]+)(\/.*)?$/);

    if (vendorMatch && request.method === 'POST' && vendorMatch[2] === '/questionnaire') {
      const vendorId = vendorMatch[1];
      const { submittedBy, answers } = await request.json<{ submittedBy: string; answers: Record<string, unknown> }>();
      const result = await submitQuestionnaire(env.DB, vendorId, submittedBy, answers);
      return Response.json(result, { status: 201 });
    }

    if (vendorMatch && request.method === 'POST' && vendorMatch[2] === '/health-check') {
      const vendorId = vendorMatch[1];
      const { endpoint } = await request.json<{ endpoint: string }>();
      const result = await runHealthCheck(env.DB, vendorId, endpoint);
      return Response.json(result);
    }

    if (request.method === 'GET' && url.pathname === '/vendors/due-for-review') {
      const days = Number(url.searchParams.get('days') ?? 7);
      const vendors = await getVendorsDueForReview(env.DB, days);
      return Response.json(vendors);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

### Scheduled health-check sweep (Cron Trigger)

```typescript
// wrangler.toml: crons = ["0 * * * *"]  — run every hour

export async function scheduledHealthChecks(
  db: D1Database,
  healthEndpoints: Record<string, string>  // vendorId -> URL
): Promise<void> {
  for (const [vendorId, endpoint] of Object.entries(healthEndpoints)) {
    const result = await runHealthCheck(db, vendorId, endpoint);
    if (!result.ok) {
      // In production: send an alert via email or webhook
      console.error(`Vendor ${vendorId} health check FAILED: ${endpoint}`);
    }
  }
}
```

### Suspending a high-risk vendor

```typescript
export async function suspendVendor(
  db: D1Database,
  vendorId: string,
  reason: string
): Promise<void> {
  await db
    .prepare(
      `UPDATE vendor SET status = 'SUSPENDED', updated_at = datetime('now') WHERE id = ?`
    )
    .bind(vendorId)
    .run();
  console.warn(`Vendor ${vendorId} suspended: ${reason}`);
  // Trigger notification to procurement and security teams
}
```

## Anti-patterns

- **Never auto-activate a vendor without a completed questionnaire** — status should remain `PENDING` until at least one questionnaire version is submitted and reviewed.
- **Do not hardcode vendor health endpoints** — store them as vendor metadata or in environment config so they can be updated without a code deploy.
- **Do not treat a high SOC 2 score as a substitute for your own contractual controls** — risk score is an input to a human decision, not an automated approval gate.
- **Avoid running health checks from a single geographic region** — a vendor's CDN may be healthy in one region but failing in another. Use `ctx.waitUntil` to fan out checks via multiple Worker routes.

## Gotchas

- **The `AbortSignal.timeout` API** requires Workers compatibility date `2023-03-01` or later.
- **D1 foreign key constraints** are not enforced by default — run `PRAGMA foreign_keys = ON` at the start of each connection or use application-level validation.
- **Contract expiry alerts**: the cron trigger fires even if there are no expiring contracts. Filter for contracts expiring within 30 days inside the scheduled handler and only alert then.
- **Score drift**: if the questionnaire schema changes (new questions added), old scores are no longer comparable. Version the scoring model and store the model version alongside the score.

## Verification

```bash
# Onboard a vendor
curl -X POST https://vendor-risk.example.workers.dev/vendors \
  -H 'Content-Type: application/json' \
  -d '{"id":"vendor_stripe","name":"Stripe","category":"PAYMENT","dataAccess":"SENSITIVE","subprocessor":true}'

# Submit questionnaire
curl -X POST https://vendor-risk.example.workers.dev/vendors/vendor_stripe/questionnaire \
  -H 'Content-Type: application/json' \
  -d '{"submittedBy":"alice@example.com","answers":{"has_soc2":true,"has_iso27001":false,"has_penetration_test":true,"data_encrypted_at_rest":true,"data_encrypted_in_transit":true,"incident_response_plan":true,"sub_processors_documented":true,"data_residency_eu":false,"breach_in_last_2y":false,"sla_uptime_pct":99.99}}'
# Expected: {"score":95,"tier":"LOW","nextReviewDue":"2027-08-24"}

# List vendors due for review in the next 30 days
curl 'https://vendor-risk.example.workers.dev/vendors/due-for-review?days=30'

# Run a health check
curl -X POST https://vendor-risk.example.workers.dev/vendors/vendor_stripe/health-check \
  -H 'Content-Type: application/json' \
  -d '{"endpoint":"https://status.stripe.com"}'
```

## Related

- `workers-sox-financial-audit-trail-d1.md` — log vendor risk decisions as financial audit events
- `workers-data-classification-labels-d1.md` — classify data shared with each vendor
- `workers-privacy-impact-assessment-d1.md` — trigger a DPIA when a new HIGH-risk vendor is onboarded

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://csf.tools/reference/nist-cybersecurity-framework/id-sc/ (NIST CSF Supply Chain)
- https://www.aicpa.org/resources/article/soc-2-report (SOC 2 guidance)
