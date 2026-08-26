# EU AI Act Deployer Obligations for Workers AI Inference

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

You are building a product that calls Cloudflare Workers AI to run inference (text generation, image classification, embeddings, speech-to-text) and you deploy that output-driven feature to EU users. Under the EU AI Act (Regulation (EU) 2024/1689), you are an **AI system deployer** within the meaning of Article 3(4), not the provider of the underlying model. This creates a distinct set of obligations — particularly under Article 26 — that differ from those of Cloudflare (the model provider) and from those of the GPAI model upstream. Failing to implement these obligations by the relevant application dates risks fines of up to €15 million or 3 % of global annual turnover (Article 101(4)).

---

## Context

**Role mapping for a Workers AI deployment**

| Layer | Entity | EU AI Act role |
|---|---|---|
| Foundation model (e.g. `@cf/meta/llama-3.3-70b-instruct`) | Meta (model developer) | GPAI model provider (Chapter V) |
| Inference infrastructure (Workers AI) | Cloudflare | AI system provider (possibly) |
| Product wrapping the inference call | You | **AI system deployer** (Article 3(4)) |
| End user of your product | Your customer | Natural person subject to AI output |

The EU AI Act entered into force on 1 August 2024. The **deployer obligations under Article 26** apply from **2 August 2026** (24-month transition from entry into force) for **high-risk AI systems** listed in Annex III, and from **2 August 2025** (12-month transition) for systems used in the workplace context.

**When is a Workers AI–powered feature a high-risk AI system?**

High-risk classification applies when the system falls into Annex III categories, including:

- **Annex III §1** — Biometric identification (facial recognition via Workers AI vision models)
- **Annex III §3** — Education: systems that evaluate learners or determine access to education
- **Annex III §4** — Employment: CV screening, interview scoring, task monitoring
- **Annex III §5** — Essential services: creditworthiness assessment, risk scoring for insurance
- **Annex III §8** — Law enforcement: risk assessment of individuals

Generative AI features (e.g., a chatbot, content summarisation, code generation) that do not fall into Annex III categories are **general-purpose** deployments subject to the transparency obligations of Article 50, but not the full Article 26 deployer obligations.

---

## Article 26 Deployer Obligations Checklist

### 6.1 Use Within Intended Purpose (Article 26(1))

Deployers must use a high-risk AI system in accordance with the instructions of use provided by the provider (Cloudflare Workers AI model cards, system prompt guidelines).

```typescript
// src/ai-use-within-scope.ts
// Guards that the Workers AI model is called within its documented purpose

interface WorkersAiCallParams {
  model: string;
  prompt: string;
  useCase: 'content-generation' | 'classification' | 'cv-screening' | 'credit-scoring';
}

const HIGH_RISK_USE_CASES: Set<string> = new Set(['cv-screening', 'credit-scoring']);

const APPROVED_MODELS_PER_USE_CASE: Record<string, string[]> = {
  'content-generation': [
    '@cf/meta/llama-3.3-70b-instruct',
    '@cf/mistral/mistral-7b-instruct-v0.1',
  ],
  'classification': [
    '@cf/huggingface/distilbert-sst-2-int8',
  ],
  // High-risk use cases require explicit model approval plus deployer controls
  'cv-screening': [],   // Not permitted without a completed Annex III assessment
  'credit-scoring': [], // Not permitted without a completed Annex III assessment
};

export function assertModelIsApprovedForUseCase(params: WorkersAiCallParams): void {
  const approved = APPROVED_MODELS_PER_USE_CASE[params.useCase] ?? [];
  if (!approved.includes(params.model)) {
    throw new Error(
      `Model ${params.model} is not approved for use case '${params.useCase}'. ` +
      `EU AI Act Article 26(1): deployer must use AI system within intended purpose. ` +
      `High-risk use cases require a conformity assessment before deployment.`
    );
  }
  if (HIGH_RISK_USE_CASES.has(params.useCase)) {
    throw new Error(
      `Use case '${params.useCase}' is a high-risk Annex III category. ` +
      `Complete Article 26 deployer obligations and register in the EU database before calling.`
    );
  }
}
```

### 6.2 Human Oversight (Article 26(2))

High-risk AI deployers must assign oversight to natural persons with the competence, authority, and resources to intervene.

```typescript
// src/ai-human-oversight.ts

interface AiDecision {
  requestId:      string;
  model:          string;
  inputHash:      string;  // SHA-256 of the prompt (no raw PII)
  output:         string;
  confidence?:    number;
  useCase:        string;
  subjectId?:     string;  // ID of the natural person affected (pseudonymised)
  requiresReview: boolean;
  reviewedBy?:    string;
  reviewedAt?:    string;
  finalDecision?: 'accepted' | 'overridden' | 'deferred';
}

export async function logAiDecisionForOversight(
  env: Env,
  decision: AiDecision
): Promise<void> {
  // Flag decisions below confidence threshold for mandatory human review
  const flagForReview = (decision.confidence ?? 1.0) < 0.85 || decision.requiresReview;

  await env.DB.prepare(`
    INSERT INTO ai_decisions
      (request_id, model, input_hash, output_excerpt, confidence,
       use_case, subject_id, requires_review, reviewed_by,
       reviewed_at, final_decision, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
  `).bind(
    decision.requestId,
    decision.model,
    decision.inputHash,
    decision.output.slice(0, 500),
    decision.confidence ?? null,
    decision.useCase,
    decision.subjectId ?? null,
    flagForReview ? 1 : 0,
    decision.reviewedBy ?? null,
    decision.reviewedAt ?? null,
    decision.finalDecision ?? null,
  ).run();

  if (flagForReview) {
    // Alert the human oversight queue
    await env.OVERSIGHT_QUEUE.send({
      requestId: decision.requestId,
      useCase: decision.useCase,
      reason: decision.confidence !== undefined
        ? `Low confidence: ${(decision.confidence * 100).toFixed(1)}%`
        : 'Manual flag required',
    });
  }
}
```

### 6.3 Transparency to Natural Persons (Article 26(6) / Article 50)

Deployers must inform natural persons when they interact with or are subject to an AI system.

```typescript
// src/ai-transparency.ts

/**
 * Appends a mandatory transparency disclosure to API responses
 * where the output is presented to or about a natural person.
 * Satisfies EU AI Act Article 26(6) and Article 50(1).
 */
export function addTransparencyHeaders(
  response: Response,
  context: { model: string; useCase: string; highRisk: boolean }
): Response {
  const mutated = new Response(response.body, response);

  // Machine-readable header for API consumers
  mutated.headers.set('X-AI-System', 'true');
  mutated.headers.set('X-AI-Model', context.model);
  mutated.headers.set('X-AI-Use-Case', context.useCase);

  if (context.highRisk) {
    mutated.headers.set('X-AI-High-Risk', 'true');
    mutated.headers.set(
      'X-AI-Oversight-Contact',
      'ai-oversight@example.com'
    );
  }

  return mutated;
}

/** Disclosure text to embed in UI-facing responses (Article 50(1)) */
export const AI_DISCLOSURE_TEXT = {
  en: 'This result was generated or influenced by an automated AI system. ' +
      'You have the right to request human review of any decision that significantly affects you.',
  de: 'Dieses Ergebnis wurde durch ein automatisiertes KI-System erzeugt oder beeinflusst. ' +
      'Sie haben das Recht, eine menschliche Überprüfung jeder Entscheidung zu verlangen, die Sie wesentlich betrifft.',
  fr: 'Ce résultat a été généré ou influencé par un système d\'IA automatisé. ' +
      'Vous avez le droit de demander un examen humain de toute décision qui vous concerne de manière significative.',
};
```

---

## Recordkeeping and Logging (Article 26(5) and (7))

Deployers of high-risk AI systems must keep logs of the operation of the system to the extent that these logs are under the deployer's control.

```sql
-- migrations/0002_ai_oversight.sql

CREATE TABLE IF NOT EXISTS ai_decisions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id       TEXT    UNIQUE NOT NULL,
  model            TEXT    NOT NULL,
  input_hash       TEXT    NOT NULL,      -- SHA-256, never raw prompt
  output_excerpt   TEXT,
  confidence       REAL,
  use_case         TEXT    NOT NULL,
  subject_id       TEXT,                  -- Pseudonymised subject identifier
  requires_review  INTEGER NOT NULL DEFAULT 0,
  reviewed_by      TEXT,
  reviewed_at      TEXT,
  final_decision   TEXT CHECK(final_decision IN ('accepted','overridden','deferred',NULL)),
  created_at       INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Mandatory retention: Article 26(7) requires logs kept for at least the period
-- during which the AI system can produce legal effects, minimum 6 months;
-- recommended retention: match the statute of limitations (typically 3 years)
CREATE INDEX IF NOT EXISTS idx_ai_decisions_subject  ON ai_decisions(subject_id);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_review   ON ai_decisions(requires_review);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_created  ON ai_decisions(created_at);

-- Human oversight review queue
CREATE TABLE IF NOT EXISTS oversight_reviews (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id  TEXT NOT NULL REFERENCES ai_decisions(request_id),
  reason      TEXT NOT NULL,
  assigned_to TEXT,
  status      TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in-review','resolved')),
  resolution  TEXT,
  resolved_at TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## Data Protection Impact Assessment Integration (Article 26(9))

When a high-risk AI system is likely to result in high risk to natural persons under GDPR, deployers must conduct a DPIA before deployment. The DPIA and AI Act obligations overlap.

```typescript
// src/dpia-trigger.ts

interface DeploymentRiskProfile {
  usesPersonalData:       boolean;
  processesSpecialData:   boolean;  // GDPR Article 9
  makesAutomatedDecisions: boolean; // GDPR Article 22
  scaleOfProcessing:      'low' | 'medium' | 'high';
  annexIiiCategory:       string | null;
}

export function assessDpiaRequirement(profile: DeploymentRiskProfile): {
  dpiaRequired: boolean;
  reasons: string[];
} {
  const reasons: string[] = [];

  if (profile.makesAutomatedDecisions && profile.usesPersonalData) {
    reasons.push('GDPR Article 22: Automated decision-making about natural persons');
  }
  if (profile.processesSpecialData) {
    reasons.push('GDPR Article 35(3)(b): Large-scale processing of special category data');
  }
  if (profile.annexIiiCategory) {
    reasons.push(`EU AI Act Article 26(9): High-risk AI system (Annex III: ${profile.annexIiiCategory})`);
  }
  if (profile.scaleOfProcessing === 'high' && profile.usesPersonalData) {
    reasons.push('GDPR Article 35(3)(a): Systematic and extensive profiling at scale');
  }

  return { dpiaRequired: reasons.length > 0, reasons };
}
```

---

## Anti-patterns

- **Assuming Cloudflare (as Workers AI provider) holds all Article 26 obligations.** Cloudflare is the AI system provider; you, as the deployer, hold a separate and independent set of obligations under Article 26 that cannot be contracted away.
- **Skipping the Annex III assessment because the feature "just uses an LLM."** Annex III assessment depends on the *output's purpose and use*, not the underlying technology. An LLM that evaluates job applications is an Annex III §4 high-risk system.
- **Logging raw prompts containing personal data in the oversight log.** Store SHA-256 hashes of prompts, not raw content. The log itself becomes personal data under GDPR and subject to erasure obligations.
- **Setting `requiresReview = false` for all calls to avoid alerting overhead.** Article 26(2) requires genuine human oversight capability. A system that never triggers review is non-compliant regardless of performance.
- **Treating the transparency header as sufficient.** Machine-readable headers satisfy API-level disclosure but do not satisfy Article 50(1) end-user notification when the AI output is presented directly to a natural person in a UI.

---

## Gotchas

- **The Article 26 obligations apply from 2 August 2026 for most Annex III systems.** Workplace AI systems (Annex III §4) have an earlier application date: 2 August 2025.
- **Non-EU deployers are still in scope.** If your Workers deployment processes data about EU persons or your product is accessible in the EU market, the regulation applies regardless of where your company is incorporated.
- **Cloudflare's Workers AI model cards will describe the intended purpose of each model.** Review these before deployment; using a model for a purpose outside its model card description is a violation of Article 26(1).
- **The EU AI Act does not define a maximum inference latency.** However, Article 26(2) requires oversight to be feasible "in real-time" for systems making consequential decisions. Batch asynchronous processing is safer for high-risk use cases than synchronous real-time decisions.
- **Fines for Article 26 violations are tiered.** Non-compliance with deployer obligations: up to €15 million or 3 % of global annual turnover (Article 101(4)). Use of a prohibited AI practice: up to €35 million or 7 % (Article 101(1)).

---

## Verification

```bash
# 1. Check that all Workers AI model calls are logged
npx wrangler d1 execute prod-db \
  --command "SELECT model, use_case, COUNT(*) AS calls, SUM(requires_review) AS flagged FROM ai_decisions GROUP BY model, use_case;"

# 2. Verify no overdue oversight reviews
npx wrangler d1 execute prod-db \
  --command "SELECT COUNT(*) AS pending FROM oversight_reviews WHERE status='pending' AND created_at < unixepoch() - 86400;"

# 3. Confirm transparency headers are present
curl -i https://your-api.example.com/ai/generate -X POST -d '{"prompt":"hello"}' | grep X-AI-

# 4. Assert no prohibited use cases are deployed
grep -r 'cv-screening\|credit-scoring\|law-enforcement' src/ || echo "No prohibited use cases found"
```

---

## Related

- `eu-ai-act-annex-iii-high-risk-systems-2026.md` — full catalogue of Annex III high-risk categories
- `eu-ai-act-workplace-deployer-information-duty.md` — Article 26(7) information duty to workers
- `ai-dpia-data-protection-impact-assessment.md` — combined AI Act / GDPR DPIA methodology
- `automated-decision-making-profiling-transparency.md` — GDPR Article 22 obligations that overlap

---

## Sources

- EU AI Act (Regulation (EU) 2024/1689), Articles 3, 26, 50, 101
- EU AI Act Annex III — High-risk AI system categories
- EDPB Opinion 28/2024 on AI Act and GDPR interaction
- Cloudflare Workers AI model cards — https://developers.cloudflare.com/workers-ai/models/
- European Commission AI Office guidance for deployers (2025)
- Article 29 Working Party / EDPB Guidelines on automated decision-making (WP251rev01)
