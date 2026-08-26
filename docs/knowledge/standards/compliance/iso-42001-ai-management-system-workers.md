# ISO/IEC 42001:2023 AI Management System Controls — Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your organisation deploys AI-powered features via Cloudflare Workers AI and needs to demonstrate conformance to ISO/IEC 42001:2023 — the world's first internationally recognised AI management system standard — to enterprise customers and auditors who require third-party AI governance certification.

## Context
ISO/IEC 42001:2023 (published December 2023) specifies requirements for establishing, implementing, maintaining and continually improving an AI Management System (AIMS). It covers AI risk assessment, AI impact assessments, objective setting, and performance monitoring. The standard adopts the familiar Annex SL high-level structure used by ISO 27001 and ISO 9001, making it integrable into existing ISMS programmes. Certification is performed by accredited conformity assessment bodies; first-party (self-declaration) is also accepted. For Cloudflare Workers deployments, the key controls fall under Clauses 6 (planning), 8 (operation), and Annex A (AI-specific controls A.2–A.10).

## AI Risk Register (Clause 6.1)

ISO 42001 Clause 6.1 requires identification and treatment of AI-specific risks including safety, fairness, transparency, and robustness. Maintain a D1-backed risk register updated on each model deployment.

```typescript
// workers/ai-risk-register.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; }

type RiskCategory = "safety" | "fairness" | "transparency" | "robustness" | "privacy" | "security";
type RiskTreatment = "accept" | "mitigate" | "transfer" | "avoid";

interface AiRiskEntry {
  modelId: string;
  useCase: string;
  riskCategory: RiskCategory;
  description: string;
  likelihood: 1 | 2 | 3 | 4 | 5;
  impact: 1 | 2 | 3 | 4 | 5;
  treatment: RiskTreatment;
  mitigationNotes: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<AiRiskEntry>();
    const riskScore = body.likelihood * body.impact;
    const id = crypto.randomUUID();
    const now = new Date().toISOString();

    await env.DB.prepare(
      `INSERT INTO ai_risk_register
         (id, model_id, use_case, category, description, likelihood, impact, risk_score, treatment, mitigation_notes, reviewed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      id, body.modelId, body.useCase, body.riskCategory, body.description,
      body.likelihood, body.impact, riskScore, body.treatment, body.mitigationNotes, now
    ).run();

    const status = riskScore >= 15 ? "high" : riskScore >= 8 ? "medium" : "low";

    return new Response(JSON.stringify({ riskId: id, riskScore, status, iso42001Ref: "Clause 6.1" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## AI Impact Assessment (Annex A.6 — AI System Impact Assessment)

ISO 42001 Annex A.6 requires an impact assessment before deploying AI systems that affect individuals. The assessment records intended use, affected populations, and residual risks.

```typescript
// workers/ai-impact-assessment.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; }

interface ImpactAssessment {
  modelId: string;
  systemName: string;
  intendedPurpose: string;
  affectedPopulations: string[];
  potentialHarms: { category: string; severity: "low" | "medium" | "high" | "critical" }[];
  safeguards: string[];
  approvedBy: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<ImpactAssessment>();

    const criticalHarms = body.potentialHarms.filter(h => h.severity === "critical");
    if (criticalHarms.length > 0 && body.safeguards.length === 0) {
      return new Response(
        JSON.stringify({ error: "ISO 42001 Annex A.6: critical-severity harms require documented safeguards" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const id = crypto.randomUUID();
    const now = new Date().toISOString();

    await env.DB.prepare(
      `INSERT INTO ai_impact_assessments
         (id, model_id, system_name, purpose, populations, harms, safeguards, approved_by, assessed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      id, body.modelId, body.systemName, body.intendedPurpose,
      JSON.stringify(body.affectedPopulations), JSON.stringify(body.potentialHarms),
      JSON.stringify(body.safeguards), body.approvedBy, now
    ).run();

    return new Response(JSON.stringify({ assessmentId: id, assessedAt: now, iso42001Ref: "Annex A.6" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Workers AI Inference Logging (Clause 8.4 — AI System Operation)

ISO 42001 Clause 8.4 requires operational controls including logging of AI system inputs and outputs sufficient to support incident investigation and auditing.

```typescript
// workers/ai-inference-logger.ts
import { D1Database, Ai } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  AI: Ai;
  LOG_SAMPLING_RATE: string; // "0.10" for 10%
}

interface InferenceRequest {
  modelId: string;
  prompt: string;
  subjectRef?: string; // optional reference to subject for privacy-safe correlation
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.json<InferenceRequest>();
    const requestId = crypto.randomUUID();
    const startMs = Date.now();

    const result = await (env.AI as any).run(body.modelId, { prompt: body.prompt });

    const latencyMs = Date.now() - startMs;
    const samplingRate = parseFloat(env.LOG_SAMPLING_RATE ?? "0.1");
    const shouldLog = Math.random() < samplingRate;

    if (shouldLog) {
      // Truncate prompt/output to 512 chars to minimise PII exposure in logs
      await env.DB.prepare(
        `INSERT INTO ai_inference_log
           (id, model_id, prompt_excerpt, output_excerpt, latency_ms, subject_ref, logged_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        requestId, body.modelId,
        body.prompt.slice(0, 512),
        JSON.stringify(result).slice(0, 512),
        latencyMs,
        body.subjectRef ?? null,
        new Date().toISOString()
      ).run();
    }

    return new Response(JSON.stringify({ requestId, result, logged: shouldLog }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Model Performance Monitoring (Clause 9 — Performance Evaluation)

ISO 42001 Clause 9 requires measurement of AI system objectives including accuracy, fairness metrics, and drift. A scheduled cron Worker computes and stores KPIs for management review.

```typescript
// workers/ai-performance-monitor.ts
import { D1Database } from "@cloudflare/workers-types";

interface Env { DB: D1Database; }

interface PerformanceKpi {
  modelId: string;
  periodStart: string;
  periodEnd: string;
  totalInferences: number;
  avgLatencyMs: number;
  errorRate: number;
  fairnessScore?: number;   // domain-specific, 0–1
  driftFlag: boolean;
}

export async function computeAndStoreKpis(env: Env, modelId: string): Promise<void> {
  const periodEnd = new Date().toISOString();
  const periodStart = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  const stats = await env.DB.prepare(
    `SELECT COUNT(*) AS total, AVG(latency_ms) AS avg_latency
     FROM ai_inference_log WHERE model_id = ? AND logged_at BETWEEN ? AND ?`
  ).bind(modelId, periodStart, periodEnd).first<{ total: number; avg_latency: number }>();

  const errorStats = await env.DB.prepare(
    `SELECT COUNT(*) AS errors FROM ai_inference_log
     WHERE model_id = ? AND logged_at BETWEEN ? AND ? AND output_excerpt LIKE '%error%'`
  ).bind(modelId, periodStart, periodEnd).first<{ errors: number }>();

  const total = stats?.total ?? 0;
  const errorRate = total > 0 ? (errorStats?.errors ?? 0) / total : 0;
  const driftFlag = errorRate > 0.05; // alert if >5% error rate suggests drift

  const kpi: PerformanceKpi = {
    modelId, periodStart, periodEnd,
    totalInferences: total,
    avgLatencyMs: Math.round(stats?.avg_latency ?? 0),
    errorRate: Math.round(errorRate * 10000) / 10000,
    driftFlag,
  };

  await env.DB.prepare(
    `INSERT INTO ai_performance_kpis
       (model_id, period_start, period_end, total_inferences, avg_latency_ms, error_rate, drift_flag, recorded_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    kpi.modelId, kpi.periodStart, kpi.periodEnd, kpi.totalInferences,
    kpi.avgLatencyMs, kpi.errorRate, kpi.driftFlag ? 1 : 0, new Date().toISOString()
  ).run();

  if (driftFlag) {
    console.error(`[ISO-42001][DRIFT] Model ${modelId} error rate ${kpi.errorRate} exceeds threshold — management review required`);
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const models = await env.DB.prepare("SELECT DISTINCT model_id FROM ai_inference_log").all<{ model_id: string }>();
    for (const row of models.results) {
      await computeAndStoreKpis(env, row.model_id);
    }
  },
};
```

## Anti-patterns
- Treating ISO 42001 as equivalent to ISO 27001 — AI-specific risks (model bias, hallucination, adversarial inputs) require their own risk categories beyond InfoSec controls.
- Logging full prompts and outputs without truncation or redaction — PII in inference logs creates additional data-protection obligations.
- Skipping the impact assessment for "low-risk" AI features — ISO 42001 Annex A.6 applies to all systems affecting individuals, not just high-risk ones.
- Running performance monitoring only at certification time — Clause 9 requires continuous measurement with defined KPI thresholds.
- Conflating model card documentation (A.4) with the operational impact assessment (A.6) — both are required but serve different purposes.

## Gotchas
- ISO 42001 certification scope must explicitly name the AI systems in scope; Workers AI models used outside the certified scope create a gap.
- The standard references "AI system lifecycle" — include Workers deployment pipelines and model version change processes in your AIMS procedures.
- Fairness metrics are domain-specific; ISO 42001 does not prescribe which metric to use, but the chosen metric must be documented and justified.
- Drift detection in a Workers Cron requires that inference logs are retained long enough for trend analysis — set `DELETE FROM ai_inference_log WHERE logged_at < date('now','-90 days')` as a separate maintenance job.
- ISO 42001 Annex B provides implementation guidance on AI objectives that can inform your KPI definitions; it is normative guidance, not purely informational.

## Verification
1. POST a risk register entry with `likelihood: 5, impact: 3` — confirm `riskScore: 15` and `status: "high"` in the response.
2. POST an impact assessment with `criticalHarms` and an empty `safeguards` array — expect HTTP 400.
3. POST 10 inference requests with sampling rate 1.0 — confirm 10 rows appear in `ai_inference_log`.
4. Trigger the cron handler and query `ai_performance_kpis` — confirm rows exist with `drift_flag` computed.
5. Inject an inference log row with `output_excerpt LIKE '%error%'` and rerun cron — confirm `drift_flag = 1` when rate exceeds 5%.

## Related
- `/documentation/docs/policies/compliance/eu-ai-act.md`
- `/documentation/docs/policies/compliance/ai-dpia-data-protection-impact-assessment.md`
- `/documentation/docs/policies/compliance/ethics-ai-governance-framework.md`
- `/documentation/docs/policies/compliance/iso-27001-continuous-monitoring-automation-workers-d1.md`
- `/documentation/docs/policies/compliance/eu-ai-act-article-13-transparency-d1-logging.md`

## Sources
- ISO/IEC 42001:2023 AI Management Systems: https://www.iso.org/standard/81230.html
- ISO 42001 Annex SL integration guide: https://www.iso.org/
- NIST AI Risk Management Framework (AI RMF 1.0): https://www.nist.gov/system/files/documents/2023/01/26/AI%20RMF%201.0.pdf
