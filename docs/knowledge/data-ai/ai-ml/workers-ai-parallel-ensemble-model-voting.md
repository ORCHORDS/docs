# Workers AI Parallel Ensemble Model Voting for Classification

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Single-model classification is brittle: one model's blind spots produce wrong labels that flow downstream unchecked. Running the same input through multiple smaller models in parallel and aggregating their votes produces higher accuracy than any individual model, especially for ambiguous content moderation, sentiment, or intent classification tasks — and on Workers AI it costs less than one call to a frontier model.

## Context

Cloudflare Workers supports `Promise.allSettled` over multiple `env.AI.run()` calls in the same request. Each call runs in parallel on Workers AI's distributed inference infrastructure. The ensemble strategy — majority vote, weighted vote, or confidence-threshold veto — is computed in the Worker after all responses return. D1 logs per-model votes and the final decision for later analysis and model drift detection.

---

## 1. Model Registry — Define the Ensemble

```typescript
// src/ensemble/models.ts
export interface EnsembleMember {
  model: string;
  weight: number;           // influence in weighted vote; 1.0 = equal
  timeoutMs: number;
}

export const SENTIMENT_ENSEMBLE: EnsembleMember[] = [
  { model: '@cf/huggingface/distilbert-sst-2-int8', weight: 1.0, timeoutMs: 3000 },
  { model: '@cf/microsoft/deberta-v3-small-fc', weight: 1.2, timeoutMs: 4000 },
  { model: '@cf/cardiffnlp/twitter-roberta-base-sentiment-latest', weight: 0.9, timeoutMs: 3500 },
];

export const CONTENT_MODERATION_ENSEMBLE: EnsembleMember[] = [
  { model: '@cf/meta/llama-guard-3-8b', weight: 1.5, timeoutMs: 5000 },
  { model: '@cf/mistral/mistral-7b-instruct-v0.2-lora', weight: 1.0, timeoutMs: 4000 },
];
```

---

## 2. Parallel Inference Runner with Timeout Per Model

```typescript
// src/ensemble/runner.ts
import type { Env } from '../types';
import type { EnsembleMember } from './models';

export interface ModelVote {
  model: string;
  label: string;
  score: number;    // confidence 0–1
  latencyMs: number;
  error?: string;
}

export async function runEnsemble(
  env: Env,
  members: EnsembleMember[],
  input: Record<string, unknown>,
): Promise<ModelVote[]> {
  const tasks = members.map(async (member): Promise<ModelVote> => {
    const start = Date.now();
    try {
      const signal = AbortSignal.timeout(member.timeoutMs);
      const result = await Promise.race([
        env.AI.run(member.model as Parameters<typeof env.AI.run>[0], input),
        new Promise<never>((_, reject) =>
          signal.addEventListener('abort', () => reject(new Error('timeout')), { once: true }),
        ),
      ]);

      // Normalise different response shapes across models
      const label =
        (result as { label?: string; predicted_label?: string }).label ??
        (result as { predicted_label?: string }).predicted_label ??
        'unknown';
      const score =
        (result as { score?: number; confidence?: number }).score ??
        (result as { confidence?: number }).confidence ??
        0.5;

      return { model: member.model, label, score, latencyMs: Date.now() - start };
    } catch (err) {
      return {
        model: member.model,
        label: 'error',
        score: 0,
        latencyMs: Date.now() - start,
        error: String(err),
      };
    }
  });

  return Promise.all(tasks);
}
```

---

## 3. Voting Strategies

```typescript
// src/ensemble/voting.ts
import type { EnsembleMember } from './models';
import type { ModelVote } from './runner';

export type VotingStrategy = 'majority' | 'weighted' | 'confidence-veto';

export interface EnsembleDecision {
  label: string;
  confidence: number;
  strategy: VotingStrategy;
  agreement: number;   // 0–1: fraction of non-errored models that agreed
  votes: ModelVote[];
}

export function aggregate(
  votes: ModelVote[],
  members: EnsembleMember[],
  strategy: VotingStrategy = 'weighted',
): EnsembleDecision {
  const valid = votes.filter((v) => v.label !== 'error');
  if (!valid.length) {
    return { label: 'error', confidence: 0, strategy, agreement: 0, votes };
  }

  const weightMap = Object.fromEntries(members.map((m) => [m.model, m.weight]));

  if (strategy === 'majority') {
    const counts: Record<string, number> = {};
    for (const v of valid) counts[v.label] = (counts[v.label] ?? 0) + 1;
    const topLabel = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
    return {
      label: topLabel,
      confidence: counts[topLabel] / valid.length,
      strategy,
      agreement: counts[topLabel] / valid.length,
      votes,
    };
  }

  if (strategy === 'weighted') {
    const scores: Record<string, number> = {};
    for (const v of valid) {
      const w = weightMap[v.model] ?? 1.0;
      scores[v.label] = (scores[v.label] ?? 0) + v.score * w;
    }
    const topLabel = Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
    const total = Object.values(scores).reduce((s, x) => s + x, 0);
    const agreement = valid.filter((v) => v.label === topLabel).length / valid.length;
    return { label: topLabel, confidence: scores[topLabel] / total, strategy, agreement, votes };
  }

  // confidence-veto: any model that exceeds threshold 0.92 can veto
  const VETO_THRESHOLD = 0.92;
  const veto = valid.find((v) => v.score >= VETO_THRESHOLD);
  if (veto) {
    return { label: veto.label, confidence: veto.score, strategy, agreement: 1, votes };
  }
  // Fall back to weighted if no veto
  return aggregate(votes, members, 'weighted');
}
```

---

## 4. D1 Audit Log for Drift Detection

```typescript
// src/ensemble/audit.ts
import type { Env } from '../types';
import type { EnsembleDecision } from './voting';
import type { ModelVote } from './runner';

export async function logDecision(
  env: Env,
  inputHash: string,
  decision: EnsembleDecision,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO ensemble_log
       (input_hash, final_label, confidence, agreement, strategy, votes_json, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, unixepoch())`,
  )
    .bind(
      inputHash,
      decision.label,
      decision.confidence,
      decision.agreement,
      decision.strategy,
      JSON.stringify(decision.votes),
    )
    .run();
}

// SQL to create the table
// CREATE TABLE ensemble_log (
//   id          INTEGER PRIMARY KEY AUTOINCREMENT,
//   input_hash  TEXT NOT NULL,
//   final_label TEXT NOT NULL,
//   confidence  REAL,
//   agreement   REAL,
//   strategy    TEXT,
//   votes_json  TEXT,
//   created_at  INTEGER
// );
```

---

## 5. Fetch Handler — Putting It Together

```typescript
// src/index.ts
import { SENTIMENT_ENSEMBLE } from './ensemble/models';
import { runEnsemble } from './ensemble/runner';
import { aggregate } from './ensemble/voting';
import { logDecision } from './ensemble/audit';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const { text } = await request.json<{ text: string }>();
    if (!text?.trim()) return new Response('Missing text', { status: 400 });

    const input = { text };
    const votes = await runEnsemble(env, SENTIMENT_ENSEMBLE, input);
    const decision = aggregate(votes, SENTIMENT_ENSEMBLE, 'weighted');

    // Hash input for deduplication in logs (no PII stored)
    const hashBuffer = await crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(text),
    );
    const inputHash = Array.from(new Uint8Array(hashBuffer))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('')
      .slice(0, 16);

    await logDecision(env, inputHash, decision);

    return Response.json(decision);
  },
};
```

---

## Anti-patterns

- Awaiting models sequentially — negates the entire latency benefit; always use `Promise.all` or `Promise.allSettled`.
- Treating a single-model error as a hard failure — non-errored models can still form a quorum; filter errors before voting.
- Storing raw input text in D1 for audit — use a hash; raw text can be PII and bloat the table.
- Using models with very different label schemas without normalisation — a model returning `POSITIVE` and another returning `positive` produce split votes on what is the same label; normalise to lowercase.

## Gotchas

- Workers AI `env.AI.run()` does not natively support `AbortSignal`; the `Promise.race` pattern shown above is the correct workaround.
- Classification models on Workers AI have varying output shapes (`label`/`score`, `predicted_label`/`confidence`); always normalise.
- `Promise.allSettled` vs `Promise.all` — use `Promise.all` here because errors are handled inside each task; `allSettled` adds unnecessary wrapper objects.
- Ensemble latency is bounded by the slowest non-timed-out model, not the sum; set per-model `timeoutMs` lower than the fetch handler's effective deadline.

## Verification

```bash
# Test ensemble endpoint
curl -X POST https://<worker>.workers.dev/classify \
  -H "Content-Type: application/json" \
  -d '{"text": "This product is absolutely terrible and I want a refund"}'

# Expected: { label: "NEGATIVE", confidence: ~0.9, agreement: ~0.9 }

# Query audit log for low-agreement decisions (model drift signal)
wrangler d1 execute DB --command \
  "SELECT final_label, AVG(agreement), COUNT(*) FROM ensemble_log
   WHERE created_at > unixepoch() - 86400
   GROUP BY final_label ORDER BY AVG(agreement) ASC"
```

## Related

- `workers-ai-text-classification-moderation.md`
- `llm-for-classification.md`
- `llm-ab-testing.md`
- `model-cascade-cheap-first-routing.md`
- `ai-gateway-multi-provider-ab-testing.md`

## Sources

- Cloudflare Workers AI classification models reference
- Ensemble learning — majority and weighted voting literature
- Workers AI binding API reference (`env.AI.run`)
