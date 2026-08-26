# Workers AI Text Classification Confidence Thresholding

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers AI text classifier returns a top label but you cannot trust predictions with low
certainty — misclassifications slip through, causing downstream routing errors, bad
moderation decisions, or stale category assignments. You need a principled way to set
per-class confidence floors, route uncertain inputs to a fallback, and track threshold
effectiveness over time.

---

## Context

Workers AI classification models (e.g. `@cf/huggingface/distilbert-sst-2-int8`,
`@cf/facebook/bart-large-mnli`) return a `scores` array parallel to `labels`. The raw
score is a softmax probability, but it is not well-calibrated out of the box: a score of
0.72 on one model may represent equivalent uncertainty to 0.91 on another. Treating every
top-scoring label as authoritative causes silent accuracy degradation.

Three common thresholding strategies:

1. **Global threshold** — a single floor for every class (simple, brittle).
2. **Per-class threshold** — different floors per label, tuned on a validation set.
3. **Margin threshold** — reject when `top_score − second_score < margin` (catches hedged
   predictions regardless of absolute score).

---

## Per-class Threshold Configuration in KV

Store thresholds in Workers KV so they can be updated without redeploying.

```typescript
// threshold-config.ts
export interface ClassThreshold {
  minScore: number;      // floor for this class
  minMargin?: number;    // optional margin vs runner-up
}

export type ThresholdMap = Record<string, ClassThreshold>;

export async function loadThresholds(
  kv: KVNamespace,
  modelKey: string
): Promise<ThresholdMap> {
  const raw = await kv.get(`thresholds:${modelKey}`, 'json');
  return (raw as ThresholdMap) ?? {};
}
```

Seed via Wrangler:

```bash
wrangler kv key put \
  --namespace-id $KV_ID \
  "thresholds:bart-mnli" \
  '{"POSITIVE":{"minScore":0.80},"NEGATIVE":{"minScore":0.75,"minMargin":0.15},"NEUTRAL":{"minScore":0.85}}'
```

---

## Classification with Threshold Enforcement

```typescript
// classify.ts
import { loadThresholds, ThresholdMap } from './threshold-config';

interface ClassificationResult {
  label: string;
  score: number;
  accepted: boolean;
  rejectionReason?: 'below_min_score' | 'below_margin';
}

export async function classifyWithThreshold(
  env: Env,
  text: string,
  modelKey: string = 'bart-mnli'
): Promise<ClassificationResult> {
  const [thresholds, result] = await Promise.all([
    loadThresholds(env.THRESHOLDS_KV, modelKey),
    env.AI.run('@cf/facebook/bart-large-mnli', {
      text,
      candidate_labels: ['POSITIVE', 'NEGATIVE', 'NEUTRAL'],
    }),
  ]);

  // Pair labels with scores, sort descending
  const ranked = result.labels
    .map((label: string, i: number) => ({ label, score: result.scores[i] }))
    .sort((a: any, b: any) => b.score - a.score);

  const top = ranked[0];
  const runnerUp = ranked[1];
  const cfg = thresholds[top.label] ?? { minScore: 0.70 };

  if (top.score < cfg.minScore) {
    return { ...top, accepted: false, rejectionReason: 'below_min_score' };
  }

  const margin = top.score - (runnerUp?.score ?? 0);
  if (cfg.minMargin !== undefined && margin < cfg.minMargin) {
    return { ...top, accepted: false, rejectionReason: 'below_margin' };
  }

  return { ...top, accepted: true };
}
```

---

## Fallback Routing for Rejected Predictions

When a prediction is rejected, route to a fallback rather than discarding the input.

```typescript
// worker.ts
import { classifyWithThreshold } from './classify';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { text } = await req.json<{ text: string }>();

    const result = await classifyWithThreshold(env, text);

    if (!result.accepted) {
      // Option A: queue for human review
      await env.REVIEW_QUEUE.send({ text, result });
      return Response.json({ status: 'queued_for_review', ...result });
    }

    // Option B: cascade to a more capable model on low-confidence
    if (result.score < 0.90) {
      const deepResult = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
        messages: [
          { role: 'system', content: 'Classify sentiment: POSITIVE, NEGATIVE, or NEUTRAL. Reply with one word.' },
          { role: 'user', content: text },
        ],
      });
      return Response.json({ source: 'cascade', label: deepResult.response?.trim(), score: null });
    }

    return Response.json({ status: 'accepted', ...result });
  },
};
```

---

## Threshold Calibration with D1 Audit Trail

Log every prediction to D1 so you can compute per-class accuracy and adjust thresholds.

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS classification_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),
  text_hash  TEXT    NOT NULL,
  model_key  TEXT    NOT NULL,
  top_label  TEXT    NOT NULL,
  top_score  REAL    NOT NULL,
  margin     REAL    NOT NULL,
  accepted   INTEGER NOT NULL,
  ground_truth TEXT                   -- filled later by human review
);

CREATE INDEX idx_cl_model_label ON classification_log(model_key, top_label);
```

```typescript
// audit.ts
export async function logPrediction(
  db: D1Database,
  textHash: string,
  modelKey: string,
  top: { label: string; score: number },
  margin: number,
  accepted: boolean
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO classification_log (text_hash, model_key, top_label, top_score, margin, accepted)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(textHash, modelKey, top.label, top.score, margin, accepted ? 1 : 0)
    .run();
}
```

Query to surface under-performing thresholds:

```sql
SELECT
  top_label,
  COUNT(*)                                   AS total,
  AVG(top_score)                             AS avg_score,
  SUM(CASE WHEN accepted = 0 THEN 1 ELSE 0 END) AS rejected,
  AVG(margin)                                AS avg_margin
FROM classification_log
WHERE model_key = 'bart-mnli'
  AND created_at > datetime('now', '-7 days')
GROUP BY top_label
ORDER BY rejected DESC;
```

---

## Anti-patterns

- **Using a single global threshold** — classes with naturally lower peak scores (e.g. NEUTRAL) will be over-rejected; high-confidence classes under-monitored.
- **Adjusting thresholds on production traffic without a holdout** — thresholds tuned on live data will overfit to recent distribution shifts.
- **Silently dropping rejected inputs** — rejected predictions are the most informative signal for threshold tuning; always log or queue them.
- **Ignoring the margin** — a score of 0.81 with a margin of 0.01 is much less reliable than a score of 0.75 with a margin of 0.40.

---

## Gotchas

- Workers AI models may return `scores` that do not sum to exactly 1.0 due to float
  precision; normalise before comparing if you compute margins manually.
- `@cf/facebook/bart-large-mnli` is a zero-shot model — scores are entailment probabilities
  against candidate labels, not posterior class probabilities. Avoid mixing its score
  semantics with a fine-tuned classifier's.
- KV reads add ~1–3 ms of latency; cache the threshold map in-memory for the duration of
  a Worker invocation to avoid repeated reads on batch payloads.
- Thresholds optimised for one distribution (e.g. support tickets) degrade when applied to
  another (e.g. social posts) — segment logs by source before tuning.

---

## Verification

1. Deploy the schema and run a batch of labelled test inputs through `classifyWithThreshold`.
2. Query D1 for per-class rejection rates; compare against expected rejection rates from
   your validation set.
3. Confirm that rejected inputs reach the review queue (or cascade model) and do not return
   a top-level `accepted: true` response.
4. Update a threshold in KV (`wrangler kv key put …`) and verify the change takes effect
   within one Worker invocation without redeployment.

---

## Related

- `workers-ai-text-classification-moderation.md`
- `workers-ai-classification-feedback-loop-d1.md`
- `ai-gateway-conditional-model-routing.md`
- `llm-for-classification.md`
- `similarity-threshold-tuning.md`

---

## Sources

- Cloudflare Workers AI — Text Classification: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Niculescu-Mizil & Caruana, "Predicting Good Probabilities with Supervised Learning", ICML 2005
