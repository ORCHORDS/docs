# Vectorize Semantic Deduplication in a Content Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A content ingestion pipeline receives articles, support tickets, or product descriptions from multiple sources. Many items are near-duplicates—same concept, different wording. Exact-string deduplication misses them; you need semantic similarity gating before writing to D1 and upserting to Vectorize so the index stays clean and retrieval quality remains high.

## Context

Vectorize stores dense float32 embeddings and supports cosine/dot-product nearest-neighbour search. By querying Vectorize for the top-1 neighbour before each insert, you can compare the similarity score against a configurable threshold. Items above the threshold are flagged as duplicates and routed to a review queue; items below are ingested normally. The pattern runs entirely at the edge: Workers AI generates embeddings, Vectorize holds the index, D1 stores metadata and dedup audit rows.

---

## 1. Architecture

```
Inbound item (fetch / Queue message)
      │
      ▼
Workers AI  ──embed──►  Vectorize.query(topK=1)
                              │
               similarity ≥ threshold?
               ┌──── yes ────►  D1 dedup_log INSERT (duplicate, skip)
               │
               └──── no  ────►  Vectorize.upsert  +  D1 content INSERT
```

---

## 2. Wrangler Bindings

```toml
[ai]
binding = "AI"

[[vectorize]]
binding = "CONTENT_IDX"
index_name = "content-dedup"

[[d1_databases]]
binding = "DB"
database_name = "content-pipeline"
database_id = "YOUR_D1_ID"
```

---

## 3. Embedding Helper

```typescript
interface Env {
  AI: Ai;
  CONTENT_IDX: VectorizeIndex;
  DB: D1Database;
}

async function embed(text: string, env: Env): Promise<number[]> {
  const result = await env.AI.run("@cf/baai/bge-small-en-v1.5", {
    text: [text],
  });
  // result.data is float32[][]
  return (result as { data: number[][] }).data[0];
}
```

---

## 4. Deduplication Gate

```typescript
const SIMILARITY_THRESHOLD = 0.92; // cosine; tune per domain
const EMBED_FIELD_MAX_CHARS = 1000; // truncate before embedding

function buildEmbedText(item: ContentItem): string {
  // Concatenate title + first N chars of body for stable embedding surface
  return `${item.title}\n${item.body.slice(0, EMBED_FIELD_MAX_CHARS)}`;
}

async function isDuplicate(
  vector: number[],
  env: Env
): Promise<{ duplicate: boolean; nearestId: string | null; score: number }> {
  const results = await env.CONTENT_IDX.query(vector, {
    topK: 1,
    returnMetadata: "none",
  });

  if (results.matches.length === 0) {
    return { duplicate: false, nearestId: null, score: 0 };
  }

  const top = results.matches[0];
  const score = top.score; // cosine similarity in [0,1]
  return {
    duplicate: score >= SIMILARITY_THRESHOLD,
    nearestId: top.id,
    score,
  };
}
```

---

## 5. Ingest Handler

```typescript
interface ContentItem {
  id: string;
  title: string;
  body: string;
  source: string;
  createdAt: number;
}

export async function ingestItem(item: ContentItem, env: Env): Promise<void> {
  const embedText = buildEmbedText(item);
  const vector = await embed(embedText, env);

  const { duplicate, nearestId, score } = await isDuplicate(vector, env);

  if (duplicate) {
    // Log the duplicate for audit / potential merge
    await env.DB.prepare(
      `INSERT INTO dedup_log (candidate_id, nearest_id, score, source, checked_at)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(item.id, nearestId, score, item.source, Date.now()).run();
    console.log(`Duplicate skipped: ${item.id} → ${nearestId} (score ${score.toFixed(4)})`);
    return;
  }

  // Insert metadata to D1
  await env.DB.prepare(
    `INSERT INTO content (id, title, body, source, created_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(id) DO NOTHING`
  ).bind(item.id, item.title, item.body, item.source, item.createdAt).run();

  // Upsert embedding to Vectorize
  await env.CONTENT_IDX.upsert([
    {
      id: item.id,
      values: vector,
      metadata: { source: item.source, title: item.title.slice(0, 64) },
    },
  ]);
}
```

---

## 6. Queue Consumer Entry Point

```typescript
interface QueueMessage {
  item: ContentItem;
}

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    // Process sequentially to avoid Vectorize write contention on small indices
    for (const msg of batch.messages) {
      try {
        await ingestItem(msg.body.item, env);
        msg.ack();
      } catch (err) {
        console.error(`Ingest error for ${msg.body.item.id}:`, err);
        msg.retry();
      }
    }
  },
};
```

---

## 7. Threshold Calibration Script (run offline)

```typescript
// Run against a labelled sample: pairs marked (duplicate | unique)
// Output: precision/recall curve per threshold
async function calibrateThreshold(
  labelledPairs: Array<{ a: string; b: string; label: "dup" | "unique" }>,
  env: Env
) {
  const thresholds = [0.80, 0.85, 0.88, 0.90, 0.92, 0.95];
  for (const t of thresholds) {
    let tp = 0, fp = 0, tn = 0, fn = 0;
    for (const { a, b, label } of labelledPairs) {
      const va = await embed(a, env);
      const vb = await embed(b, env);
      // Dot product of unit vectors = cosine similarity
      const score = va.reduce((s, v, i) => s + v * vb[i], 0);
      const pred = score >= t ? "dup" : "unique";
      if (pred === "dup" && label === "dup") tp++;
      else if (pred === "dup" && label === "unique") fp++;
      else if (pred === "unique" && label === "unique") tn++;
      else fn++;
    }
    const precision = tp / (tp + fp) || 0;
    const recall = tp / (tp + fn) || 0;
    console.log(`t=${t}: precision=${precision.toFixed(3)} recall=${recall.toFixed(3)}`);
  }
}
```

---

## Anti-patterns

- **Using exact-string hashing as the only dedup layer** — misses paraphrases, translations, reformatted copies.
- **Setting threshold < 0.85** — BGE-small produces high baseline similarities for unrelated short texts; calibrate on domain-specific sample pairs.
- **Embedding the full body** — long documents produce averaged embeddings that lose discriminative signal; truncate to title + first ~1000 characters.
- **Upserting before the D1 write succeeds** — Vectorize upserts are eventually consistent but not transactional with D1; write D1 first so a crash doesn't leave orphaned vectors.

---

## Gotchas

- Vectorize `query` is approximate (ANN); it may miss the true nearest neighbour if the index is very large and `ef` is low. For dedup, a missed near-duplicate is safer than a false positive that discards unique content. Prefer recall over precision by lowering `topK` and raising threshold.
- `@cf/baai/bge-small-en-v1.5` outputs L2-normalised vectors, so dot product equals cosine similarity—no extra normalisation needed.
- Vectorize upsert is idempotent by `id`; re-ingesting the same item after an earlier success is safe.
- The dedup check adds one Vectorize query per item. At high throughput (>500 items/s) batch your embed calls and query in parallel, but be aware of Workers AI rate limits.

---

## Verification

```bash
# After ingesting 1000 items, check dedup rate
wrangler d1 execute content-pipeline \
  --command "SELECT COUNT(*) as dupes FROM dedup_log WHERE score >= 0.92"

# Spot-check a near-duplicate pair
wrangler d1 execute content-pipeline \
  --command "SELECT candidate_id, nearest_id, score FROM dedup_log ORDER BY score DESC LIMIT 10"
```

Target: dedup rate 5–15% for typical editorial content pipelines. Rates above 30% suggest the threshold is too low.

---

## Related

- `ai-duplicate-content-detection.md`
- `vectorize-approximate-nearest-neighbor-tuning.md`
- `vectorize-batch-upsert-incremental-sync.md`
- `embedding-batching.md`
- `similarity-threshold-tuning.md`

---

## Sources

- Cloudflare Vectorize docs: https://developers.cloudflare.com/vectorize/
- BGE model card: https://huggingface.co/BAAI/bge-small-en-v1.5
- ANN accuracy vs. threshold trade-offs: https://www.pinecone.io/learn/what-is-similarity-search/
