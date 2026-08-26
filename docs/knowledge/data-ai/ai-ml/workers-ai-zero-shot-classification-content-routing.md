# Workers AI Zero-Shot Classification for Content Routing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project ingests anonymous posts across many topic areas: politics, mental health,
relationships, humour, local events. Different downstream pipelines exist for each:
a debate-ranking pipeline, a crisis-escalation pipeline, a trending-topics aggregator,
etc. Previously, all routing was done with keyword lists maintained in a spreadsheet —
a fragile system that missed colloquial phrasing and mis-routed ambiguous posts.

Goal: replace keyword routing with zero-shot text classification on the Workers AI
inference layer so that each post is assigned one or more routing labels without a
trained task-specific model, without shipping user data off the edge, and with a
decision logged to D1 for audit and retraining.

---

## Context

Zero-shot classification uses a natural-language-inference (NLI) model to decide
whether a text "entails" a candidate label phrase. The Cloudflare Workers AI catalogue
includes `@cf/facebook/bart-large-mnli`, a BART model fine-tuned on MultiNLI that
accepts a sequence and a list of candidate labels and returns a probability score for
each label.

Routing use-cases on example project:
- **crisis**: post may describe self-harm or suicidal ideation → crisis pipeline
- **politics**: political discourse → debate-rank pipeline
- **local**: geographically scoped event → geo-aggregator
- **humour**: comedic or meme content → viral-trending pipeline
- **nsfw**: sexually explicit → age-gate pipeline

Because the platform is anonymous, routing decisions must be made on content alone —
no user history or profile signal is available.

---

## Basic Zero-Shot Routing

```typescript
// src/routes/classify.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  DB: D1Database;
}

export const ROUTING_LABELS = [
  "crisis or self-harm",
  "political debate",
  "local community event",
  "humour or memes",
  "sexually explicit content",
] as const;

export type RoutingLabel = (typeof ROUTING_LABELS)[number];

export interface ClassificationResult {
  postId: string;
  scores: Record<RoutingLabel, number>;
  primaryLabel: RoutingLabel;
  allAboveThreshold: RoutingLabel[];
}

const THRESHOLD = 0.55; // minimum score to consider a label active

export async function classifyPost(
  env: Env,
  postId: string,
  text: string
): Promise<ClassificationResult> {
  const result = await env.AI.run("@cf/facebook/bart-large-mnli", {
    text,
    candidate_labels: [...ROUTING_LABELS],
    // multi_label allows a post to match multiple categories
    multi_label: true,
  });

  // Map array results to a typed record
  const scores = Object.fromEntries(
    result.labels.map((label: string, i: number) => [label, result.scores[i]])
  ) as Record<RoutingLabel, number>;

  const primaryLabel = result.labels[0] as RoutingLabel; // highest-scoring

  const allAboveThreshold = result.labels.filter(
    (_: string, i: number) => result.scores[i] >= THRESHOLD
  ) as RoutingLabel[];

  return { postId, scores, primaryLabel, allAboveThreshold };
}
```

---

## Routing Dispatcher

```typescript
// src/routes/router.ts
import { classifyPost, ClassificationResult, Env } from "./classify";

type PipelineName =
  | "crisis-pipeline"
  | "debate-pipeline"
  | "geo-pipeline"
  | "viral-pipeline"
  | "age-gate-pipeline"
  | "default-pipeline";

const LABEL_TO_PIPELINE: Record<string, PipelineName> = {
  "crisis or self-harm": "crisis-pipeline",
  "political debate": "debate-pipeline",
  "local community event": "geo-pipeline",
  "humour or memes": "viral-pipeline",
  "sexually explicit content": "age-gate-pipeline",
};

export async function routePost(
  env: Env,
  postId: string,
  text: string,
  queue: Queue
): Promise<PipelineName[]> {
  const classification = await classifyPost(env, postId, text);

  // Determine pipelines; crisis always wins first position if present
  const pipelines: PipelineName[] = [];

  if (classification.allAboveThreshold.includes("crisis or self-harm")) {
    pipelines.push("crisis-pipeline");
  }

  for (const label of classification.allAboveThreshold) {
    const pipeline = LABEL_TO_PIPELINE[label];
    if (pipeline && !pipelines.includes(pipeline)) {
      pipelines.push(pipeline);
    }
  }

  if (pipelines.length === 0) {
    pipelines.push("default-pipeline");
  }

  // Enqueue routing decision for each target pipeline
  await queue.sendBatch(
    pipelines.map((pipeline) => ({
      body: { postId, pipeline, scores: classification.scores },
    }))
  );

  await persistRoutingDecision(env, postId, classification, pipelines);

  return pipelines;
}

async function persistRoutingDecision(
  env: Env,
  postId: string,
  classification: ClassificationResult,
  pipelines: PipelineName[]
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO routing_log
       (post_id, primary_label, pipelines, scores_json, classified_at)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(
      postId,
      classification.primaryLabel,
      JSON.stringify(pipelines),
      JSON.stringify(classification.scores),
      Date.now()
    )
    .run();
}
```

---

## Worker Entry Point

```typescript
// src/index.ts
import { Env } from "./routes/classify";
import { routePost } from "./routes/router";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { postId, text } = await request.json<{
      postId: string;
      text: string;
    }>();

    if (!postId || !text?.trim()) {
      return new Response(JSON.stringify({ error: "postId and text required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Truncate to 512 tokens worth of characters; BART-MNLI has a 1024-token limit
    // but longer inputs slow classification noticeably.
    const truncated = text.slice(0, 1800);

    const pipelines = await routePost(
      env,
      postId,
      truncated,
      (env as unknown as { ROUTING_QUEUE: Queue }).ROUTING_QUEUE
    );

    return new Response(JSON.stringify({ postId, pipelines }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## D1 Schema for Audit and Retraining

```sql
-- migrations/0010_routing_log.sql
CREATE TABLE IF NOT EXISTS routing_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id      TEXT    NOT NULL,
  primary_label TEXT   NOT NULL,
  pipelines    TEXT    NOT NULL,  -- JSON array
  scores_json  TEXT    NOT NULL,  -- JSON object
  classified_at INTEGER NOT NULL,
  human_label  TEXT,              -- filled in by moderation review
  is_correct   INTEGER            -- 0/1, set during retraining data curation
);

CREATE INDEX IF NOT EXISTS idx_routing_log_post_id
  ON routing_log (post_id);

CREATE INDEX IF NOT EXISTS idx_routing_log_classified_at
  ON routing_log (classified_at);
```

---

## Threshold Calibration with Human Labels

Pull routing decisions with human review labels from D1, compute per-label F1, and
adjust `THRESHOLD` accordingly:

```typescript
// scripts/calibrate-threshold.ts (runs locally against D1 REST API)
async function calibrateThreshold(db: D1Database, label: string) {
  const rows = await db
    .prepare(
      `SELECT scores_json, human_label FROM routing_log
       WHERE human_label IS NOT NULL AND is_correct IS NOT NULL`
    )
    .all<{ scores_json: string; human_label: string }>();

  const thresholds = Array.from({ length: 19 }, (_, i) => (i + 1) * 0.05);

  for (const threshold of thresholds) {
    let tp = 0, fp = 0, fn = 0;
    for (const row of rows.results) {
      const scores = JSON.parse(row.scores_json) as Record<string, number>;
      const predicted = (scores[label] ?? 0) >= threshold;
      const actual = row.human_label === label;
      if (predicted && actual) tp++;
      else if (predicted && !actual) fp++;
      else if (!predicted && actual) fn++;
    }
    const precision = tp / (tp + fp || 1);
    const recall = tp / (tp + fn || 1);
    const f1 = (2 * precision * recall) / (precision + recall || 1);
    console.log({ label, threshold, precision, recall, f1 });
  }
}
```

---

## Anti-patterns

- **Using zero-shot as a replacement for a fine-tuned model on high-stakes labels**
  (e.g. crisis). Zero-shot F1 for "crisis or self-harm" at 0.55 threshold typically
  sits around 0.72 on general text. For the crisis pipeline, add a second-pass fine-
  tuned binary classifier via Workers AI LoRA adapter after zero-shot triggers.
- **Sending full post text including attachments/URLs to BART-MNLI** — the model
  ignores non-text tokens but the token budget is consumed, degrading recall on the
  actual semantic content.
- **Using a single global threshold** for all labels — political content and crisis
  content have very different precision/recall trade-offs; calibrate per-label.
- **Skipping the routing log** — without the audit trail, you cannot build a retraining
  dataset or explain routing decisions to trust & safety teams.

---

## Gotchas

- `@cf/facebook/bart-large-mnli` has a ~1 024-token input limit. Inputs longer than
  ~700 words should be truncated to the first N characters or summarised first.
- `multi_label: true` scores are independent per label (sigmoid, not softmax), so the
  sum of all scores can exceed 1.0 — this is expected and correct.
- Label phrase wording matters significantly. "suicide or self-harm" outperforms
  "dangerous content" by ~12 F1 points for the crisis category on the MultiNLI-derived
  model. Treat label phrasing as a hyperparameter.
- Classification latency is ~120–280 ms at the edge; do not call this synchronously
  inside a user-facing request. Use a Cloudflare Queue consumer Worker instead.

---

## Verification

1. Create a test fixture of 20 posts with known labels.
2. Call the classify endpoint and assert `primaryLabel` matches expected label with
   score > 0.6 for all 20 fixtures.
3. Confirm `routing_log` rows are written for each call.
4. Enqueue a synthetic `crisis or self-harm` post and verify `crisis-pipeline` appears
   first in `pipelines`.
5. Query D1: `SELECT pipelines, COUNT(*) FROM routing_log GROUP BY pipelines` — confirm
   distribution matches expected label frequency for your corpus.

---

## Related

- `workers-ai-text-classification-moderation.md`
- `workers-ai-content-safety-classifier-pipeline.md`
- `llm-semantic-router-intent-classification-workers.md`
- `ai-content-moderation-pipeline.md`
- `workers-ai-toxicity-scoring-d1-audit-trail.md`

---

## Sources

- Workers AI BART-MNLI model: https://developers.cloudflare.com/workers-ai/models/bart-large-mnli/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- MultiNLI dataset & NLI classification: https://cims.nyu.edu/~sbowman/multinli/
- D1 REST API: https://developers.cloudflare.com/d1/platform/client-api/
