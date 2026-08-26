# EU AI Act Article 13: Transparency Obligations and AI Decision Logging in D1 for High-Risk Systems

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Cloudflare Workers AI inference endpoint serves a high-risk AI system under Annex III of the EU AI Act — a credit scoring model, a CV screening system, a medical device auxiliary, or a biometric categorisation pipeline. The deployer (an EU-based company using your API) asks for evidence that your system meets Article 13 transparency requirements: they need to be able to understand, interpret, and explain the AI's outputs to affected persons, and you need to provide adequate information to enable that.

---

## Context

**EU AI Act Article 13** (Transparency and provision of information to deployers) applies to **providers** of **high-risk AI systems** listed in Annex III. It requires that high-risk AI systems:

1. Are accompanied by instructions for use enabling deployers to understand the system's capabilities and limitations.
2. Are designed and developed to be sufficiently transparent that deployers can interpret the system's output and use it appropriately.
3. Provide information on: the intended purpose; the level of accuracy, robustness, and cybersecurity; any known/foreseeable circumstances in which the system may fail; the human oversight measures; the computational and hardware requirements; a description of the training data characteristics.

**Article 14** (Human oversight) requires that deployers are able to monitor the system's operation and intervene or override outputs.

**Article 26** (Obligations of deployers) requires deployers to use AI systems as instructed, monitor performance, and — where applicable — inform affected persons.

For the application engineer, this translates into: structured logging of every AI decision, explanations surfaced via API, a drift/anomaly detection layer, and an override/correction pipeline.

---

## Section 1 — D1 Schema for AI Decision Audit Log

Every inference that could affect a natural person must be logged with sufficient context to support post-hoc explanation and audit.

```sql
-- migrations/001_ai_act_schema.sql

CREATE TABLE ai_decision_log (
  id                 TEXT PRIMARY KEY,
  system_id          TEXT NOT NULL,       -- identifies which AI system/model
  system_version     TEXT NOT NULL,       -- model version / deployment hash
  inference_id       TEXT NOT NULL UNIQUE, -- UUID per inference call
  deployer_id        TEXT NOT NULL,        -- the deployer organisation
  subject_ref        TEXT,                 -- opaque reference to affected person (no raw PII)
  input_schema_hash  TEXT NOT NULL,        -- SHA-256 of input feature schema (not raw features)
  output_class       TEXT,                 -- predicted class or decision category
  output_score       REAL,                 -- confidence / probability score
  output_threshold   REAL,                 -- decision boundary applied
  final_decision     TEXT NOT NULL,        -- e.g. 'APPROVED', 'REJECTED', 'REFERRED_HUMAN'
  human_reviewed     INTEGER NOT NULL DEFAULT 0,  -- boolean
  human_override     INTEGER NOT NULL DEFAULT 0,  -- boolean
  override_reason    TEXT,
  latency_ms         INTEGER,
  called_at          TEXT NOT NULL DEFAULT (datetime('now')),
  -- Article 13(1)(b): logging fields for monitoring
  feature_drift_flag INTEGER NOT NULL DEFAULT 0,
  anomaly_flag       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ai_system_registry (
  id               TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  version          TEXT NOT NULL,
  annex_iii_category TEXT NOT NULL,   -- e.g. 'credit_scoring', 'employment_screening'
  risk_level       TEXT NOT NULL CHECK(risk_level IN ('high','limited','minimal')),
  intended_purpose TEXT NOT NULL,
  accuracy_metric  TEXT NOT NULL,     -- e.g. 'F1=0.94 on test set v2025-01'
  training_data_hash TEXT,            -- hash of training data manifest
  instructions_url TEXT NOT NULL,     -- Article 13(3): URL to instructions for use
  registered_at    TEXT NOT NULL DEFAULT (datetime('now')),
  deprecated_at    TEXT
);

CREATE TABLE ai_override_log (
  id              TEXT PRIMARY KEY,
  decision_id     TEXT NOT NULL REFERENCES ai_decision_log(id),
  operator_id     TEXT NOT NULL,
  original_output TEXT NOT NULL,
  corrected_output TEXT NOT NULL,
  reason          TEXT NOT NULL,
  evidence_refs   TEXT,              -- JSON array of document references
  overridden_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_decision_system   ON ai_decision_log(system_id, called_at);
CREATE INDEX idx_decision_deployer ON ai_decision_log(deployer_id, called_at);
CREATE INDEX idx_decision_subject  ON ai_decision_log(subject_ref, called_at);
```

---

## Section 2 — Workers AI Inference Wrapper with Structured Logging

Wrap every `env.AI.run()` call to capture the Article 13-required metadata before returning a response.

```typescript
// src/ai/inference-wrapper.ts
import { nanoid } from 'nanoid';

interface InferenceRequest<T> {
  systemId: string;
  systemVersion: string;
  deployerId: string;
  subjectRef?: string;           // opaque ID — never raw PII
  inputs: T;
  decisionThreshold?: number;
}

interface InferenceResult {
  inferenceId: string;
  outputClass?: string;
  outputScore?: number;
  finalDecision: string;
  explanation?: ExplanationPayload;
  humanReviewRequired: boolean;
  calledAt: string;
}

interface ExplanationPayload {
  topFeatures?: Array<{ feature: string; contribution: number }>;
  confidenceLevel: 'high' | 'medium' | 'low';
  decisionBoundary?: number;
  warningFlags: string[];
}

export async function runWithAudit<T extends Record<string, unknown>>(
  env: Env,
  request: InferenceRequest<T>
): Promise<InferenceResult> {
  const inferenceId = nanoid();
  const calledAt = new Date().toISOString();

  // Hash the input schema for logging (never log raw feature values that could re-identify)
  const schemaKeys = Object.keys(request.inputs).sort().join(',');
  const inputSchemaHash = await sha256Hex(schemaKeys);

  let outputClass: string | undefined;
  let outputScore: number | undefined;
  let finalDecision: string;
  let explanation: ExplanationPayload | undefined;
  let featureDriftFlag = 0;
  let anomalyFlag = 0;
  let latencyMs: number;

  const start = Date.now();
  try {
    // Workers AI inference
    const result = await env.AI.run(request.systemId as BaseAiTextClassificationModels, {
      text: JSON.stringify(request.inputs),
    }) as { label: string; score: number }[];

    latencyMs = Date.now() - start;

    const top = result.sort((a, b) => b.score - a.score)[0];
    outputClass = top.label;
    outputScore = top.score;

    const threshold = request.decisionThreshold ?? 0.5;
    const humanReviewRequired = outputScore < 0.7 && outputScore > 0.3;  // uncertainty band

    // Article 13(1)(b): flag low-confidence decisions for human oversight
    finalDecision = humanReviewRequired ? 'REFERRED_HUMAN' : (outputScore >= threshold ? 'APPROVED' : 'REJECTED');

    // Basic explanation (production: use SHAP/LIME via a secondary endpoint)
    explanation = {
      confidenceLevel: outputScore >= 0.8 ? 'high' : outputScore >= 0.6 ? 'medium' : 'low',
      decisionBoundary: threshold,
      warningFlags: humanReviewRequired ? ['LOW_CONFIDENCE_REQUIRES_HUMAN_REVIEW'] : [],
    };

    // Feature drift detection (compare input distribution to baseline — simplified)
    featureDriftFlag = await detectInputDrift(env, request.systemId, request.inputs) ? 1 : 0;
    if (featureDriftFlag) anomalyFlag = 1;

  } catch (err) {
    latencyMs = Date.now() - start;
    finalDecision = 'ERROR';
    anomalyFlag = 1;
    throw err;
  } finally {
    // Always write audit log — even on error (Article 13 audit trail)
    env.ctx.waitUntil(
      env.DB.prepare(`
        INSERT INTO ai_decision_log
          (id, system_id, system_version, inference_id, deployer_id, subject_ref,
           input_schema_hash, output_class, output_score, output_threshold,
           final_decision, latency_ms, called_at, feature_drift_flag, anomaly_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        nanoid(), request.systemId, request.systemVersion, inferenceId,
        request.deployerId, request.subjectRef ?? null, inputSchemaHash,
        outputClass ?? null, outputScore ?? null, request.decisionThreshold ?? 0.5,
        finalDecision, latencyMs, calledAt, featureDriftFlag, anomalyFlag
      ).run()
    );
  }

  return {
    inferenceId,
    outputClass,
    outputScore,
    finalDecision,
    explanation,
    humanReviewRequired: finalDecision === 'REFERRED_HUMAN',
    calledAt,
  };
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function detectInputDrift(env: Env, systemId: string, inputs: Record<string, unknown>): Promise<boolean> {
  // Simplified: check for unexpected null rates or out-of-range values
  const nullRate = Object.values(inputs).filter(v => v === null || v === undefined).length / Object.keys(inputs).length;
  return nullRate > 0.3;  // >30% null features is a drift signal
}
```

---

## Section 3 — Article 13 Instructions-for-Use API Endpoint

Deployers must be able to retrieve system metadata and instructions programmatically (for integration into their own conformity documentation).

```typescript
// src/ai/instructions-endpoint.ts
// GET /ai/systems/:systemId/instructions

export async function getSystemInstructions(
  request: Request,
  env: Env,
  systemId: string
): Promise<Response> {
  const system = await env.DB.prepare(`
    SELECT id, name, version, annex_iii_category, risk_level, intended_purpose,
           accuracy_metric, training_data_hash, instructions_url, registered_at
    FROM ai_system_registry
    WHERE id = ? AND deprecated_at IS NULL
  `).bind(systemId).first<{
    id: string; name: string; version: string; annex_iii_category: string;
    risk_level: string; intended_purpose: string; accuracy_metric: string;
    training_data_hash: string; instructions_url: string; registered_at: string;
  }>();

  if (!system) return new Response('AI system not found', { status: 404 });

  // Article 13(3) mandatory disclosure fields
  const instructions = {
    systemId: system.id,
    systemName: system.name,
    version: system.version,
    riskLevel: system.risk_level,
    annexIiiCategory: system.annex_iii_category,
    intendedPurpose: system.intended_purpose,
    capabilities: {
      accuracyMetric: system.accuracy_metric,
      trainingDataManifestHash: system.training_data_hash,
    },
    limitations: [
      'Model performance may degrade on demographic groups underrepresented in training data.',
      'Outputs should not be the sole basis for consequential decisions without human review.',
      'Input feature drift (detected automatically) triggers a REFERRED_HUMAN decision.',
    ],
    humanOversight: {
      mandatoryReviewTriggers: ['LOW_CONFIDENCE_REQUIRES_HUMAN_REVIEW', 'FEATURE_DRIFT_DETECTED'],
      overrideEndpoint: `/ai/decisions/{inferenceId}/override`,
      slaForHumanReview: '24h',
    },
    technicalRequirements: {
      apiVersion: 'v1',
      inputFormat: 'application/json',
      maxLatencyP99: '500ms',
    },
    instructionsUrl: system.instructions_url,
    registeredAt: system.registered_at,
  };

  return Response.json(instructions, {
    headers: { 'Cache-Control': 'public, max-age=3600' },
  });
}
```

---

## Section 4 — Human Override and Correction Pipeline (Article 14)

Article 14 requires that deployers can intervene, override, or switch off the system. Every override must be logged against the original decision.

```typescript
// src/ai/override-handler.ts
// POST /ai/decisions/:inferenceId/override

interface OverrideRequest {
  correctedOutput: string;
  reason: string;
  evidenceRefs?: string[];
}

export async function handleOverride(
  request: Request,
  env: Env,
  inferenceId: string
): Promise<Response> {
  const operator = await authenticateOperator(request, env);
  if (!operator) return new Response('Unauthorized', { status: 401 });

  const decision = await env.DB.prepare(
    'SELECT id, final_decision, deployer_id FROM ai_decision_log WHERE inference_id = ?'
  ).bind(inferenceId).first<{ id: string; final_decision: string; deployer_id: string }>();

  if (!decision) return new Response('Decision not found', { status: 404 });

  if (operator.deployerId !== decision.deployer_id) {
    return new Response('Forbidden — override restricted to originating deployer', { status: 403 });
  }

  const body = await request.json<OverrideRequest>();

  const overrideId = crypto.randomUUID();
  await env.DB.prepare(`
    INSERT INTO ai_override_log
      (id, decision_id, operator_id, original_output, corrected_output, reason, evidence_refs, overridden_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
  `).bind(
    overrideId,
    decision.id,
    operator.id,
    decision.final_decision,
    body.correctedOutput,
    body.reason,
    JSON.stringify(body.evidenceRefs ?? [])
  ).run();

  await env.DB.prepare(`
    UPDATE ai_decision_log
    SET human_reviewed = 1, human_override = 1, final_decision = ?
    WHERE id = ?
  `).bind(body.correctedOutput, decision.id).run();

  return Response.json({
    overrideId,
    inferenceId,
    originalDecision: decision.final_decision,
    correctedDecision: body.correctedOutput,
    loggedAt: new Date().toISOString(),
  }, { status: 201 });
}
```

---

## Section 5 — Performance Monitoring and Drift Detection (Article 13(1)(b))

Article 13 requires that the system logs information necessary to assess performance. Implement a Cron Trigger to calculate rolling accuracy and drift metrics.

```typescript
// src/ai/performance-monitor.ts
// wrangler.toml cron: "0 * * * *"  (hourly)

interface PerformanceSnapshot {
  systemId: string;
  windowStart: string;
  windowEnd: string;
  totalInferences: number;
  humanReferrals: number;
  humanOverrides: number;
  anomalyFlags: number;
  driftFlags: number;
  referralRate: number;
  overrideRate: number;
}

export async function computePerformanceSnapshot(env: Env): Promise<void> {
  const windowEnd = new Date().toISOString();
  const windowStart = new Date(Date.now() - 60 * 60 * 1000).toISOString();  // last 1 hour

  const { results } = await env.DB.prepare(`
    SELECT
      system_id,
      COUNT(*) AS total,
      SUM(CASE WHEN final_decision = 'REFERRED_HUMAN' THEN 1 ELSE 0 END) AS referrals,
      SUM(human_override) AS overrides,
      SUM(anomaly_flag) AS anomalies,
      SUM(feature_drift_flag) AS drifts
    FROM ai_decision_log
    WHERE called_at BETWEEN ? AND ?
    GROUP BY system_id
  `).bind(windowStart, windowEnd).all<{
    system_id: string; total: number; referrals: number;
    overrides: number; anomalies: number; drifts: number;
  }>();

  for (const row of results) {
    const snapshot: PerformanceSnapshot = {
      systemId: row.system_id,
      windowStart,
      windowEnd,
      totalInferences: row.total,
      humanReferrals: row.referrals,
      humanOverrides: row.overrides,
      anomalyFlags: row.anomalies,
      driftFlags: row.drifts,
      referralRate: row.referrals / row.total,
      overrideRate: row.overrides / row.total,
    };

    await env.DB.prepare(`
      INSERT INTO ai_performance_snapshots
        (id, system_id, window_start, window_end, total_inferences, human_referrals,
         human_overrides, anomaly_flags, drift_flags, referral_rate, override_rate)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      crypto.randomUUID(),
      snapshot.systemId, snapshot.windowStart, snapshot.windowEnd,
      snapshot.totalInferences, snapshot.humanReferrals, snapshot.humanOverrides,
      snapshot.anomalyFlags, snapshot.driftFlags,
      snapshot.referralRate, snapshot.overrideRate
    ).run();

    // Alert if override rate exceeds threshold (potential systematic model failure)
    if (snapshot.overrideRate > 0.1) {
      await env.ALERT_QUEUE.send({
        type: 'AI_HIGH_OVERRIDE_RATE',
        systemId: row.system_id,
        overrideRate: snapshot.overrideRate,
        windowEnd,
      });
    }
  }
}
```

---

## Section 6 — Deployer-Facing Explanation Report API

Article 13 + Recital 47 require that deployers can generate human-readable explanations to communicate to affected persons.

```typescript
// src/ai/explanation-report.ts
// GET /ai/decisions/:inferenceId/explanation

export async function getExplanationReport(
  request: Request,
  env: Env,
  inferenceId: string
): Promise<Response> {
  const decision = await env.DB.prepare(`
    SELECT d.*, s.name AS system_name, s.intended_purpose, s.instructions_url
    FROM ai_decision_log d
    JOIN ai_system_registry s ON s.id = d.system_id
    WHERE d.inference_id = ?
  `).bind(inferenceId).first<Record<string, unknown>>();

  if (!decision) return new Response('Decision not found', { status: 404 });

  const override = await env.DB.prepare(
    'SELECT corrected_output, reason, overridden_at FROM ai_override_log WHERE decision_id = ? LIMIT 1'
  ).bind(decision.id).first<{ corrected_output: string; reason: string; overridden_at: string }>();

  const report = {
    inferenceId,
    systemName: decision.system_name,
    intendedPurpose: decision.intended_purpose,
    decisionMade: decision.final_decision,
    confidenceScore: decision.output_score,
    decisionAt: decision.called_at,
    wasReferredToHuman: decision.final_decision === 'REFERRED_HUMAN' || !!override,
    humanOverride: override
      ? {
          correctedDecision: override.corrected_output,
          overriddenAt: override.overridden_at,
          reason: override.reason,
        }
      : null,
    warningFlags: [
      ...(decision.feature_drift_flag ? ['INPUT_DISTRIBUTION_ANOMALY_DETECTED'] : []),
      ...(decision.anomaly_flag ? ['SYSTEM_ANOMALY_FLAGGED'] : []),
    ],
    rightsInformation: {
      rightToHumanReview: 'You may request that a human review this decision. Contact: dpo@yourcompany.com',
      rightToExplanation: 'You have the right to receive a meaningful explanation of this decision under EU AI Act Article 86 and GDPR Article 22.',
      rightToContest: 'You may contest this decision. Submit your request to: privacy@yourcompany.com',
    },
    instructionsForUseUrl: decision.instructions_url,
    reportGeneratedAt: new Date().toISOString(),
  };

  return Response.json(report);
}
```

---

## Anti-Patterns

- **Logging raw feature values in `ai_decision_log`** — Input features for credit scoring or HR screening often contain sensitive personal data. Log only schema hashes and aggregate statistics, never raw values.
- **Treating low-confidence outputs as equivalent to high-confidence ones** — Article 14 human oversight means low-confidence decisions must route to `REFERRED_HUMAN`. Do not auto-approve on a 51% score.
- **Registering a model in the system registry once and never updating it** — Each retraining or fine-tuning constitutes a substantial modification under Article 2(1)(n). Update `system_version` and `training_data_hash` on every significant change.
- **Using Workers AI run() without specifying a pinned model version** — Model updates in Workers AI can change output distributions. Pin the model version via the `@cf/provider/model-name` specifier and test before promoting.

---

## Gotchas

- **Article 13 applies to providers, not deployers** — If you are a provider (you build and offer the AI system), you must produce the instructions for use. If you are a deployer (you use an AI system you did not build), your obligations fall under Article 26.
- **"High-risk" under Annex III is broader than it looks** — Credit scoring, recruitment screening, educational assessment, and law enforcement risk assessment are all Annex III categories. Read Article 6 and Annex III carefully before assuming your use case is "limited risk."
- **Article 13 transparency ≠ full XAI (Explainable AI)** — Article 13 requires that outputs are interpretable by deployers, not necessarily that mathematical feature attributions are surfaced to end users (that is more Article 86). Distinguish requirements for the deployer API from end-user rights.
- **The AI Act's Annex III list was amended in August 2024** — Verify your use case against the current Annex III as amended by the delegated acts; the original 2024 text has been updated.

---

## Verification Checklist

- [ ] Every `env.AI.run()` call is wrapped by `runWithAudit()` which writes to `ai_decision_log`.
- [ ] `ai_system_registry` has an entry for each deployed model with `instructions_url` populated.
- [ ] Low-confidence outputs (configurable uncertainty band) produce `final_decision = 'REFERRED_HUMAN'`.
- [ ] Feature drift detection fires `feature_drift_flag = 1` when input distribution is anomalous.
- [ ] Override endpoint enforces deployer-scoping (only the originating deployer can override).
- [ ] Hourly Cron Trigger computes performance snapshots and alerts on override rate > 10%.
- [ ] Explanation report endpoint is documented in the deployer integration guide.
- [ ] `subject_ref` in `ai_decision_log` is an opaque token — never raw email, name, or ID number.
- [ ] `ai_decision_log` retention period is documented and enforced (minimum: statute of limitations for claims in your jurisdiction).

---

## Related Articles

- `eu-ai-act-deployer-obligations-workers-ai-inference.md`
- `eu-ai-act-risk-classification-engineering.md`
- `automated-decision-making-profiling-transparency.md`
- `ai-dpia-data-protection-impact-assessment.md`
- `audit-log-mandatory.md`
- `gdpr-article-30-ropa-automation.md`

---

## Sources

- EU AI Act (Regulation (EU) 2024/1689), Article 13 (Transparency and provision of information to deployers)
- EU AI Act Article 14 (Human oversight)
- EU AI Act Article 26 (Obligations of deployers of high-risk AI systems)
- EU AI Act Article 86 (Right to explanation of individual decision-making)
- EU AI Act Annex III (High-risk AI systems), as amended August 2024
- Recital 47, EU AI Act
- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- EU AI Act text: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689
