# Workers AI Text Classification & Content Moderation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need an automated content moderation pipeline that scores user-submitted text for sentiment and toxicity using Workers AI, routes flagged content to a human review queue via Workers Queues, persists every moderation decision (including overrides) in D1, and allows switching between two classifier models via a KV feature flag for A/B testing.

---

## Context

`@cf/huggingface/distilbert-sst-2-int8` is a fast, quantised sentiment classifier that returns `POSITIVE`/`NEGATIVE` labels with confidence scores. Toxicity detection can be layered on top by running the same model against a rephrased prompt or by using a second specialised model. Workers Queues provide a durable buffer between the real-time classification step and the slower human-review workflow. D1 stores every decision with a full audit trail so that human overrides are recorded alongside the original model verdict. A KV flag (`model:classifier`) lets you route a percentage of traffic to an experimental model without redeploying the Worker.

---

## Section 1 — wrangler.toml / Config

```toml
name = "moderation-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "FLAGS_KV"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "moderation"
database_id = "<your-d1-database-id>"

[[queues.producers]]
binding = "REVIEW_QUEUE"
queue = "human-review"

[[queues.consumers]]
queue = "human-review"
max_batch_size = 10
max_batch_timeout = 30
max_retries = 3

[vars]
TOXICITY_THRESHOLD = "0.75"
DEFAULT_MODEL = "@cf/huggingface/distilbert-sst-2-int8"
ALT_MODEL = "@cf/huggingface/distilbert-sst-2-int8" # swap for experimental model
FLAG_ROLLOUT_PERCENT = "10" # % of traffic sent to ALT_MODEL
```

## Section 2 — Worker implementation

```typescript
interface Env {
  AI: Ai;
  FLAGS_KV: KVNamespace;
  DB: D1Database;
  REVIEW_QUEUE: Queue;
  TOXICITY_THRESHOLD: string;
  DEFAULT_MODEL: string;
  ALT_MODEL: string;
  FLAG_ROLLOUT_PERCENT: string;
}

interface ClassifierOutput {
  label: string;  // 'POSITIVE' | 'NEGATIVE'
  score: number;  // 0–1
}

interface ModerationDecision {
  id: string;
  content_id: string;
  text_snippet: string;
  model: string;
  label: string;
  score: number;
  is_toxic: boolean;
  routed_to_review: boolean;
  human_verdict?: string;
  override_reason?: string;
  created_at: string;
  reviewed_at?: string;
}

// ─── Feature flag: pick model per request ─────────────────────────────────────

async function pickModel(
  kv: KVNamespace,
  defaultModel: string,
  altModel: string,
  rolloutPercent: number
): Promise<string> {
  // Check for an explicit KV override first
  const override = await kv.get('model:classifier');
  if (override === 'alt') return altModel;
  if (override === 'default') return defaultModel;

  // Percentage-based rollout using a random coin flip
  return Math.random() * 100 < rolloutPercent ? altModel : defaultModel;
}

// ─── Classification ───────────────────────────────────────────────────────────

async function classify(
  ai: Ai,
  model: string,
  text: string
): Promise<ClassifierOutput> {
  const results = (await ai.run(model as '@cf/huggingface/distilbert-sst-2-int8', {
    text,
  })) as ClassifierOutput[];
  // The binding returns an array sorted by score descending; take the top label.
  return results[0];
}

// ─── D1 helpers ───────────────────────────────────────────────────────────────

async function insertDecision(
  db: D1Database,
  decision: ModerationDecision
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO moderation_decisions
         (id, content_id, text_snippet, model, label, score, is_toxic,
          routed_to_review, human_verdict, override_reason, created_at, reviewed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      decision.id,
      decision.content_id,
      decision.text_snippet,
      decision.model,
      decision.label,
      decision.score,
      decision.is_toxic ? 1 : 0,
      decision.routed_to_review ? 1 : 0,
      decision.human_verdict ?? null,
      decision.override_reason ?? null,
      decision.created_at,
      decision.reviewed_at ?? null
    )
    .run();
}

async function updateDecision(
  db: D1Database,
  id: string,
  verdict: string,
  reason: string
): Promise<void> {
  await db
    .prepare(
      `UPDATE moderation_decisions
       SET human_verdict = ?, override_reason = ?, reviewed_at = ?
       WHERE id = ?`
    )
    .bind(verdict, reason, new Date().toISOString(), id)
    .run();
}

// ─── Route handlers ───────────────────────────────────────────────────────────

async function handleModerate(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ content_id: string; text: string }>();
  if (!body.content_id || !body.text) {
    return new Response(
      JSON.stringify({ error: '`content_id` and `text` are required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const rollout = parseInt(env.FLAG_ROLLOUT_PERCENT, 10);
  const model = await pickModel(env.FLAGS_KV, env.DEFAULT_MODEL, env.ALT_MODEL, rollout);
  const threshold = parseFloat(env.TOXICITY_THRESHOLD);

  const { label, score } = await classify(env.AI, model, body.text);

  // Treat NEGATIVE with high confidence as potentially toxic
  const is_toxic = label === 'NEGATIVE' && score >= threshold;
  const routed_to_review = is_toxic;

  const decision: ModerationDecision = {
    id: crypto.randomUUID(),
    content_id: body.content_id,
    text_snippet: body.text.slice(0, 500), // store first 500 chars
    model,
    label,
    score,
    is_toxic,
    routed_to_review,
    created_at: new Date().toISOString(),
  };

  // Persist decision
  await insertDecision(env.DB, decision);

  // Enqueue for human review if flagged
  if (routed_to_review) {
    await env.REVIEW_QUEUE.send({
      decision_id: decision.id,
      content_id: body.content_id,
      label,
      score,
      text_snippet: decision.text_snippet,
    });
  }

  return Response.json({
    decision_id: decision.id,
    label,
    score,
    is_toxic,
    routed_to_review,
    model,
  });
}

async function handleOverride(request: Request, env: Env): Promise<Response> {
  const { decision_id, verdict, reason } = await request.json<{
    decision_id: string;
    verdict: 'approved' | 'rejected';
    reason: string;
  }>();

  if (!decision_id || !verdict || !reason) {
    return new Response(
      JSON.stringify({ error: '`decision_id`, `verdict`, and `reason` are required' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  await updateDecision(env.DB, decision_id, verdict, reason);
  return Response.json({ updated: true, decision_id });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === '/moderate') {
      return handleModerate(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/override') {
      return handleOverride(request, env);
    }
    return new Response('Not found', { status: 404 });
  },

  // Queue consumer: process batches from the human-review queue
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const payload = message.body as {
        decision_id: string;
        content_id: string;
        label: string;
        score: number;
        text_snippet: string;
      };

      // Example: call an external review webhook
      try {
        await fetch('https://review.internal/api/flag', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        message.ack();
      } catch (err) {
        // Retry: leave message unacknowledged so Queues retries it
        console.error('Review webhook failed', err);
        message.retry();
      }
    }
  },
};
```

## Section 3 — A/B testing model comparison & analytics

```typescript
// Query A/B model accuracy from D1 after human reviews are complete
async function modelComparisonReport(db: D1Database): Promise<Response> {
  const { results } = await db
    .prepare(
      `SELECT
         model,
         COUNT(*) AS total,
         SUM(CASE WHEN human_verdict IS NOT NULL THEN 1 ELSE 0 END) AS reviewed,
         SUM(CASE WHEN human_verdict = 'approved' AND is_toxic = 0 THEN 1
                  WHEN human_verdict = 'rejected' AND is_toxic = 1 THEN 1
                  ELSE 0 END) AS correct,
         ROUND(AVG(score), 4) AS avg_score
       FROM moderation_decisions
       WHERE created_at >= datetime('now', '-7 days')
       GROUP BY model
       ORDER BY model`
    )
    .all();

  return Response.json({ report: results });
}

// Flip KV feature flag (call from an admin endpoint or Wrangler CLI)
async function setModelFlag(kv: KVNamespace, flag: 'default' | 'alt' | 'rollout'): Promise<void> {
  if (flag === 'rollout') {
    await kv.delete('model:classifier'); // revert to percentage-based rollout
    return;
  }
  await kv.put('model:classifier', flag);
}

export { modelComparisonReport, setModelFlag };
```

---

## Anti-patterns

- **Using sentiment label alone as a toxicity signal** — `NEGATIVE` sentiment ≠ toxic content. A message saying "I'm sad today" is NEGATIVE but not toxic. Layer multiple signals or use a dedicated toxicity model.
- **Blocking the request until human review completes** — Human review is asynchronous; route flagged content to a queue and return a fast decision to the caller immediately.
- **Storing full user text in D1 without truncation** — Long text bloats the decisions table. Store a safe truncated snippet and reference the original content by `content_id`.
- **Hardcoding the model name** — Use an env var and a KV override so you can swap models without redeploying.

---

## Gotchas

- `distilbert-sst-2-int8` is trained on movie reviews; it may misclassify domain-specific text (e.g., technical jargon). Validate accuracy on your corpus before using the score threshold in production.
- Workers Queues `message.retry()` without a delay will retry immediately; set `max_retries` in `wrangler.toml` to avoid infinite retry loops.
- D1 booleans are stored as `INTEGER` (0/1); cast them back in application code.
- Queue consumers run in a separate isolate from the fetch handler; they share bindings but not in-memory state.
- KV reads in every request add ~1 ms latency; cache the flag value in the Worker's module-level scope with a short TTL if latency is critical.

---

## Verification

```bash
# Create infrastructure
npx wrangler d1 create moderation
npx wrangler d1 execute moderation --command "
  CREATE TABLE IF NOT EXISTS moderation_decisions (
    id TEXT PRIMARY KEY, content_id TEXT NOT NULL,
    text_snippet TEXT NOT NULL, model TEXT NOT NULL,
    label TEXT NOT NULL, score REAL NOT NULL,
    is_toxic INTEGER NOT NULL DEFAULT 0,
    routed_to_review INTEGER NOT NULL DEFAULT 0,
    human_verdict TEXT, override_reason TEXT,
    created_at TEXT NOT NULL, reviewed_at TEXT
  );"
npx wrangler queues create human-review
npx wrangler deploy

# Moderate benign text
curl -X POST https://moderation-worker.<your-subdomain>.workers.dev/moderate \
  -H 'Content-Type: application/json' \
  -d '{"content_id":"post-1","text":"I love this product, great experience!"}'

# Moderate potentially toxic text
curl -X POST https://moderation-worker.<your-subdomain>.workers.dev/moderate \
  -H 'Content-Type: application/json' \
  -d '{"content_id":"post-2","text":"This is absolutely terrible and I hate it."}'

# Submit human override
curl -X POST https://moderation-worker.<your-subdomain>.workers.dev/override \
  -H 'Content-Type: application/json' \
  -d '{"decision_id":"<uuid>","verdict":"approved","reason":"Negative but not toxic"}'
```

---

## Related

- `workers-ai-embeddings-vectorize-semantic-search.md`
- `workers-ai-whisper-speech-to-text.md`
- `workers-ai-translation-multilingual.md`

---

## Sources

- Workers AI DistilBERT SST-2 — https://developers.cloudflare.com/workers-ai/models/distilbert-sst-2-int8/
- Workers Queues — https://developers.cloudflare.com/queues/
- D1 Database — https://developers.cloudflare.com/d1/
- KV Namespace — https://developers.cloudflare.com/kv/
