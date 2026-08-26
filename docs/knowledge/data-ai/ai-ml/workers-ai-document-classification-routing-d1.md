# Workers AI Document Classification and Routing with D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Inbound documents (emails, support tickets, contracts, news articles) arrive at a single endpoint and must be classified into categories (e.g., "legal", "billing", "technical", "spam") and then routed to the correct downstream handler—a Queue, a Webhook, or a D1 table partition—without manual triage and without a long-running Python classification server.

## Context

Workers AI provides zero-shot text classification via `@cf/facebook/bart-large-mnli` (Zero Shot Classification) and multi-label classification via the embeddings + cosine-similarity pattern. A hybrid approach: use the zero-shot model for high-confidence decisions and fall back to embedding-similarity against a D1 label centroid table for edge cases. D1 stores the routing log and label centroids. Cloudflare Queues deliver to downstream handlers by label.

---

## 1. Architecture

```
POST /classify  (document text)
      │
      ▼
Zero-Shot Classifier (BART-MNLI)
      │
      ├── confidence ≥ 0.75 ──► route immediately
      │
      └── confidence < 0.75 ──► Embedding similarity vs D1 label centroids
                                          │
                                          ▼
                                 Best centroid match
                                          │
                                          ▼
                          D1  classification_log INSERT
                          Queue.send(label-specific queue)
```

---

## 2. Wrangler Configuration

```toml
[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "doc-routing"
database_id = "YOUR_D1_ID"

[[queues.producers]]
binding = "LEGAL_QUEUE"
queue = "docs-legal"

[[queues.producers]]
binding = "BILLING_QUEUE"
queue = "docs-billing"

[[queues.producers]]
binding = "TECHNICAL_QUEUE"
queue = "docs-technical"

[[queues.producers]]
binding = "SPAM_QUEUE"
queue = "docs-spam"
```

---

## 3. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS label_centroids (
  label       TEXT PRIMARY KEY,
  centroid    TEXT NOT NULL,  -- JSON array of float32[]
  doc_count   INTEGER DEFAULT 0,
  updated_at  INTEGER
);

CREATE TABLE IF NOT EXISTS classification_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id      TEXT NOT NULL,
  input_hash  TEXT,          -- SHA-256 of first 500 chars for dedup
  label       TEXT NOT NULL,
  confidence  REAL NOT NULL,
  method      TEXT NOT NULL, -- 'zero_shot' | 'centroid'
  routed_to   TEXT,          -- queue name
  classified_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_label_classified ON classification_log(label, classified_at);
```

---

## 4. Label Configuration

```typescript
// Define candidate labels and their associated queues
const LABEL_CONFIG: Record<
  string,
  { description: string; queueKey: keyof Env }
> = {
  legal: {
    description: "contracts, NDAs, compliance documents, legal notices",
    queueKey: "LEGAL_QUEUE",
  },
  billing: {
    description: "invoices, payment disputes, subscription questions, refunds",
    queueKey: "BILLING_QUEUE",
  },
  technical: {
    description: "bug reports, feature requests, API errors, integration help",
    queueKey: "TECHNICAL_QUEUE",
  },
  spam: {
    description: "unsolicited commercial messages, scams, irrelevant content",
    queueKey: "SPAM_QUEUE",
  },
};

const CANDIDATE_LABELS = Object.keys(LABEL_CONFIG);
const ZERO_SHOT_THRESHOLD = 0.75;
```

---

## 5. Zero-Shot Classification

```typescript
interface Env {
  AI: Ai;
  DB: D1Database;
  LEGAL_QUEUE: Queue;
  BILLING_QUEUE: Queue;
  TECHNICAL_QUEUE: Queue;
  SPAM_QUEUE: Queue;
}

interface ClassificationResult {
  label: string;
  confidence: number;
  method: "zero_shot" | "centroid";
}

async function zeroShotClassify(
  text: string,
  env: Env
): Promise<{ label: string; score: number } | null> {
  const truncated = text.slice(0, 1024); // BART MNLI context limit
  const result = await env.AI.run("@cf/facebook/bart-large-mnli", {
    text: truncated,
    candidate_labels: CANDIDATE_LABELS,
  });

  // result: { sequence: string; labels: string[]; scores: number[] }
  const res = result as { labels: string[]; scores: number[] };
  const topIdx = 0; // scores are sorted descending
  return { label: res.labels[topIdx], score: res.scores[topIdx] };
}
```

---

## 6. Centroid Fallback Classifier

```typescript
async function embed(text: string, env: Env): Promise<number[]> {
  const result = await env.AI.run("@cf/baai/bge-small-en-v1.5", {
    text: [text.slice(0, 1000)],
  });
  return (result as { data: number[][] }).data[0];
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    magA += a[i] * a[i];
    magB += b[i] * b[i];
  }
  return dot / (Math.sqrt(magA) * Math.sqrt(magB) + 1e-10);
}

async function centroidClassify(
  text: string,
  env: Env
): Promise<{ label: string; score: number } | null> {
  const centroids = await env.DB.prepare(
    "SELECT label, centroid FROM label_centroids"
  ).all<{ label: string; centroid: string }>();

  if (centroids.results.length === 0) return null;

  const vector = await embed(text, env);

  let bestLabel = "";
  let bestScore = -Infinity;

  for (const row of centroids.results) {
    const centroidVec: number[] = JSON.parse(row.centroid);
    const score = cosineSimilarity(vector, centroidVec);
    if (score > bestScore) {
      bestScore = score;
      bestLabel = row.label;
    }
  }

  return { label: bestLabel, score: bestScore };
}
```

---

## 7. Routing and Logging

```typescript
async function routeDocument(
  docId: string,
  text: string,
  label: string,
  env: Env
): Promise<void> {
  const config = LABEL_CONFIG[label];
  if (!config) return;

  const queue = env[config.queueKey] as Queue;
  await queue.send({ docId, label, text: text.slice(0, 4096) });
}

async function classify(
  docId: string,
  text: string,
  env: Env
): Promise<ClassificationResult> {
  // Attempt zero-shot first
  const zs = await zeroShotClassify(text, env);

  if (zs && zs.score >= ZERO_SHOT_THRESHOLD) {
    return { label: zs.label, confidence: zs.score, method: "zero_shot" };
  }

  // Fall back to centroid similarity
  const centroid = await centroidClassify(text, env);
  if (centroid) {
    return { label: centroid.label, confidence: centroid.score, method: "centroid" };
  }

  // Last resort: use zero-shot top result even if below threshold
  return {
    label: zs?.label ?? "technical",
    confidence: zs?.score ?? 0,
    method: "zero_shot",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });

    const { docId, text } = (await request.json()) as { docId: string; text: string };
    if (!docId || !text) return new Response("docId and text required", { status: 400 });

    const result = await classify(docId, text, env);

    // Route to the appropriate queue
    await routeDocument(docId, text, result.label, env);

    // Log the classification decision
    await env.DB.prepare(
      `INSERT INTO classification_log
         (doc_id, label, confidence, method, routed_to, classified_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      docId,
      result.label,
      result.confidence,
      result.method,
      LABEL_CONFIG[result.label]?.queueKey ?? "none",
      Date.now()
    ).run();

    return Response.json(result);
  },
};
```

---

## 8. Updating Label Centroids (Admin Endpoint)

```typescript
// Call this when labelled examples are added to improve centroid quality.
// Centroid = mean of all labelled embedding vectors for that label.
export async function updateCentroid(
  label: string,
  exampleTexts: string[],
  env: Env
): Promise<void> {
  const vectors = await Promise.all(
    exampleTexts.map((t) => embed(t, env))
  );
  const dim = vectors[0].length;
  const centroid = new Array(dim).fill(0);
  for (const v of vectors) {
    for (let i = 0; i < dim; i++) centroid[i] += v[i] / vectors.length;
  }

  await env.DB.prepare(
    `INSERT INTO label_centroids (label, centroid, doc_count, updated_at)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(label) DO UPDATE SET
       centroid=excluded.centroid, doc_count=excluded.doc_count, updated_at=excluded.updated_at`
  ).bind(label, JSON.stringify(centroid), exampleTexts.length, Date.now()).run();
}
```

---

## Anti-patterns

- **Running BART-MNLI on texts > 1024 tokens** — the model silently truncates; chunk long documents and aggregate per-chunk scores (majority vote or average).
- **Storing full document text in `classification_log`** — log only the doc_id and label; retrieve the full text from the source system when needed.
- **Hard-coding confidence thresholds without measurement** — measure precision/recall per label on a held-out set; thresholds should differ by label (spam typically needs higher confidence than technical).
- **Ignoring the centroid fallback path** — zero-shot models degrade on short or ambiguous texts; centroid fallback using domain-specific examples consistently improves accuracy for unusual inputs.

---

## Gotchas

- `@cf/facebook/bart-large-mnli` returns `labels` and `scores` in descending score order, so `labels[0]` is always the top prediction—no need to sort.
- Centroid vectors stored as JSON in D1 TEXT columns inflate row size: 768-dim float32 as JSON ≈ 4–6 KB per row. For >100 labels, consider packing vectors as base64 binary blobs.
- Queue `send()` is fire-and-forget; if routing must be transactional with the D1 log, write the log first and treat queue failure as an alert trigger.
- Zero-shot classification is slower (~300–800 ms) than embedding similarity (~50–100 ms). Cache zero-shot results for identical texts using KV with a short TTL.

---

## Verification

```bash
# Test legal document
curl -X POST https://your-worker.example.com \
  -H "Content-Type: application/json" \
  -d '{"docId":"doc-001","text":"This Non-Disclosure Agreement is entered into by the parties below..."}'
# Expected: {"label":"legal","confidence":>0.85,"method":"zero_shot"}

# Check routing log
wrangler d1 execute doc-routing \
  --command "SELECT label, method, confidence FROM classification_log ORDER BY classified_at DESC LIMIT 5"
```

---

## Related

- `workers-ai-text-classification-moderation.md`
- `workers-ai-classification-feedback-loop-d1.md`
- `workers-ai-content-safety-classifier-pipeline.md`
- `llm-semantic-router-intent-classification-workers.md`
- `workers-ai-queue-batch-processing.md`

---

## Sources

- BART-MNLI zero-shot paper: https://arxiv.org/abs/1909.00161
- Cloudflare Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Zero-shot classification best practices: https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.ZeroShotClassificationPipeline
