# AI-Powered Duplicate Content Detection

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your platform accumulates duplicate and near-duplicate content through:
- Users reposting the same article with minor wording changes.
- Scrapers submitting syndicated content already in your database.
- Multi-account abuse where the same user submits variations of prohibited content.
- Automated content farms generating paraphrased versions of viral posts.

Exact-match deduplication (MD5/SHA-256 of full text) misses paraphrased and reformatted
duplicates. Edit-distance algorithms (Levenshtein, SimHash) scale poorly to millions of
documents and ignore semantic equivalence. Embedding-based similarity search with
Cloudflare Vectorize catches semantic duplicates at scale, with LLM confirmation for
borderline cases.

## Context

Duplicate detection uses a two-stage funnel:

**Stage 1 — Vector similarity search (fast, approximate):**
Generate an embedding of the new content → query Vectorize for the top-K most similar
vectors → retrieve candidates above a cosine similarity threshold (e.g. ≥ 0.88).

**Stage 2 — LLM confirmation (slower, precise):**
For candidates above the threshold, ask an LLM to confirm whether the pair is a
semantic duplicate, paraphrase, or genuinely distinct. This eliminates false positives
from topically similar but different content.

The funnel shape ensures the expensive LLM step runs on a tiny fraction of submissions
(only near-threshold candidates), keeping average latency under 500 ms.

For exact deduplication of short strings (titles, slugs), supplement with MinHash LSH
or a SHA-256 check on normalised text (lowercased, punctuation stripped, whitespace
collapsed) before invoking any AI.

## Stage 1: Embedding and Vector Search

```typescript
interface DuplicateCandidate {
  id: string;
  title: string;
  score: number;       // Cosine similarity, 0.0–1.0
  created_at: number;
}

async function findCandidates(
  ai: Ai,
  vectorize: VectorizeIndex,
  db: D1Database,
  content: string,
  topK = 5
): Promise<DuplicateCandidate[]> {
  // Generate embedding for new content
  // Use the title + first 512 chars of body for a focused fingerprint
  const fingerprint = content.slice(0, 512);

  const embeddingResponse = await ai.run(
    "@cf/baai/bge-base-en-v1.5",
    { text: [fingerprint] }
  ) as { data: number[][] };

  const queryVector = embeddingResponse.data[0];

  // Query Vectorize
  const results = await vectorize.query(queryVector, {
    topK,
    returnMetadata: "indexed",
  });

  if (!results.matches || results.matches.length === 0) return [];

  // Filter by similarity threshold
  const THRESHOLD = 0.88;
  const candidates = results.matches.filter((m) => m.score >= THRESHOLD);

  if (candidates.length === 0) return [];

  // Fetch metadata from D1 for candidates
  const ids = candidates.map((c) => `'${c.id}'`).join(",");
  const { results: rows } = await db
    .prepare(`SELECT id, title, created_at FROM content WHERE id IN (${ids})`)
    .all<{ id: string; title: string; created_at: number }>();

  const rowMap = new Map(rows.map((r) => [r.id, r]));

  return candidates
    .map((c) => {
      const row = rowMap.get(c.id);
      if (!row) return null;
      return { id: c.id, title: row.title, score: c.score, created_at: row.created_at };
    })
    .filter((x): x is DuplicateCandidate => x !== null);
}
```

## Stage 2: LLM Confirmation

```typescript
type DuplicateVerdict = "duplicate" | "paraphrase" | "distinct";

interface ConfirmationResult {
  verdict: DuplicateVerdict;
  confidence: number;       // 0.0–1.0
  explanation: string;
}

async function confirmDuplicate(
  ai: Ai,
  original: string,
  candidate: string
): Promise<ConfirmationResult> {
  const prompt =
    `Compare these two texts and determine if they are:\n` +
    `- "duplicate": essentially the same content with only trivial differences (formatting, typos)\n` +
    `- "paraphrase": the same information rewritten in different words\n` +
    `- "distinct": genuinely different content that happens to be topically related\n\n` +
    `Text A:\n"${original.slice(0, 800)}"\n\n` +
    `Text B:\n"${candidate.slice(0, 800)}"\n\n` +
    `Return JSON: {"verdict":"duplicate|paraphrase|distinct","confidence":<0.0-1.0>,"explanation":"<brief reason>"}`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    response_format: { type: "json_object" },
    max_tokens: 128,
    temperature: 0.0,
  });

  try {
    return JSON.parse((response as { response: string }).response) as ConfirmationResult;
  } catch {
    return { verdict: "distinct", confidence: 0.0, explanation: "parse error" };
  }
}
```

## Full Detection Pipeline

```typescript
interface DuplicateCheckResult {
  is_duplicate: boolean;
  verdict: DuplicateVerdict | "unique";
  best_match_id?: string;
  best_match_score?: number;
  confidence?: number;
  explanation?: string;
}

async function checkForDuplicates(
  ai: Ai,
  vectorize: VectorizeIndex,
  db: D1Database,
  contentId: string,
  content: string,
  title: string
): Promise<DuplicateCheckResult> {
  // 0. Exact title match (cheapest check)
  const exactRow = await db
    .prepare(
      "SELECT id FROM content WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) AND id != ? LIMIT 1"
    )
    .bind(title, contentId)
    .first<{ id: string }>();

  if (exactRow) {
    return {
      is_duplicate: true,
      verdict: "duplicate",
      best_match_id: exactRow.id,
      best_match_score: 1.0,
      confidence: 1.0,
      explanation: "Identical title match.",
    };
  }

  // 1. Vector similarity search
  const candidates = await findCandidates(ai, vectorize, db, `${title}\n\n${content}`);

  if (candidates.length === 0) {
    return { is_duplicate: false, verdict: "unique" };
  }

  // 2. LLM confirmation on top candidate (highest similarity score)
  const top = candidates[0];

  const candidateRow = await db
    .prepare("SELECT content FROM content WHERE id = ?")
    .bind(top.id)
    .first<{ content: string }>();

  if (!candidateRow) return { is_duplicate: false, verdict: "unique" };

  const confirmation = await confirmDuplicate(ai, content, candidateRow.content);

  return {
    is_duplicate: confirmation.verdict !== "distinct",
    verdict: confirmation.verdict,
    best_match_id: top.id,
    best_match_score: top.score,
    confidence: confirmation.confidence,
    explanation: confirmation.explanation,
  };
}
```

## Indexing New Content

After a piece of content passes the duplicate check and is accepted, index it in
Vectorize so future submissions can be checked against it:

```typescript
async function indexContent(
  ai: Ai,
  vectorize: VectorizeIndex,
  content: { id: string; title: string; body: string; created_at: number }
): Promise<void> {
  const fingerprint = `${content.title}\n\n${content.body.slice(0, 512)}`;

  const embeddingResponse = await ai.run(
    "@cf/baai/bge-base-en-v1.5",
    { text: [fingerprint] }
  ) as { data: number[][] };

  await vectorize.upsert([
    {
      id: content.id,
      values: embeddingResponse.data[0],
      metadata: {
        title: content.title.slice(0, 128),
        created_at: content.created_at,
      },
    },
  ]);
}
```

## Handling Paraphrases vs. True Duplicates

Different policy responses for different verdicts:

```typescript
async function handleDuplicateResult(
  result: DuplicateCheckResult,
  contentId: string,
  db: D1Database
): Promise<{ action: "accept" | "reject" | "flag"; message: string }> {
  if (!result.is_duplicate) {
    return { action: "accept", message: "Content is unique." };
  }

  switch (result.verdict) {
    case "duplicate":
      // Hard reject — exact or near-exact copy
      await db
        .prepare(
          "UPDATE content SET status='rejected', rejection_reason=? WHERE id=?"
        )
        .bind(`Duplicate of ${result.best_match_id}`, contentId)
        .run();
      return {
        action: "reject",
        message: `This content is a duplicate of an existing submission.`,
      };

    case "paraphrase":
      // Flag for human review — may be legitimate rewrite or may be evasion
      await db
        .prepare(
          "UPDATE content SET status='flagged', flag_reason=? WHERE id=?"
        )
        .bind(`Paraphrase of ${result.best_match_id} (confidence ${result.confidence?.toFixed(2)})`, contentId)
        .run();
      return {
        action: "flag",
        message: "Content has been submitted for review.",
      };

    default:
      return { action: "accept", message: "Content is unique." };
  }
}
```

## Threshold Tuning

The similarity threshold is the most critical configuration parameter:

| Threshold | Behaviour |
|---|---|
| ≥ 0.95 | Near-exact duplicates only; misses paraphrases |
| ≥ 0.88 | Good balance; catches paraphrases; ~5% false positive rate |
| ≥ 0.80 | Aggressive; flags topically similar content as duplicates |
| ≥ 0.70 | Too aggressive; flags unrelated content in same domain |

Calibrate by running a labelled sample (100–200 pairs you've manually marked as
duplicate/not-duplicate) and computing precision/recall at various thresholds.
Plot the PR curve and pick the threshold at your acceptable precision (e.g. P=0.95).

## Anti-patterns

- **Relying on a single embedding model for all content types.** BGE-base-en-v1.5 is
  optimised for English semantic similarity. For multilingual content, use a multilingual
  embedding model (`@cf/baai/bge-m3` or similar).
- **Checking duplicates after storage.** Embed and query Vectorize before persisting
  content. Retroactive deduplication requires a migration; prevention is cheaper.
- **Using cosine similarity alone as the rejection criterion.** Topically identical but
  legitimately different articles (two reporters covering the same event) will have high
  cosine similarity. Always run LLM confirmation for borderline cases.
- **Fingerprinting the full body without weighting the title.** Titles are highly
  discriminative. Prepend the title to the fingerprint text before embedding.
- **Not deleting vectors when content is deleted.** Orphaned vectors will cause false
  positives as the index grows. Call `vectorize.deleteByIds([id])` when content is removed.
- **Querying Vectorize synchronously in the request path for long content.** Embedding
  long documents takes 100–300 ms. Move to a Queue-based async check for articles > 1000
  words.

## Gotchas

- Vectorize `topK` is capped at 20 per query. For very dense vector spaces (millions of
  vectors), the true nearest neighbour may not appear in topK if the index's approximation
  misses it. Increase topK and decrease the threshold slightly for higher recall.
- `@cf/baai/bge-base-en-v1.5` generates 768-dimensional vectors. Vectorize indexes must
  be created with the matching dimensions: `wrangler vectorize create my-index --dimensions=768 --metric=cosine`.
- Cosine similarity in Vectorize is computed over L2-normalised vectors; scores are in
  [0, 1] (not [-1, 1]) for BGE models because BGE embeddings are already non-negative.
- The LLM confirmation step adds ~300–600 ms. Gate it behind the vector threshold to
  keep average latency under 200 ms for the typical (non-duplicate) case.
- When seeding the Vectorize index from an existing D1 table, batch upserts in groups of
  100 vectors to avoid hitting the 1000-vector-per-request limit.
- Workers AI embedding inference has a max input token limit (~512 tokens for BGE-base).
  Truncate or summarise content before embedding; use a sliding window with max-pooling
  for very long documents.

## Verification

```bash
# Index an article
curl -X POST https://api.example.com/content \
  -H "Content-Type: application/json" \
  -d '{"id":"art-001","title":"How to Build a RAG Pipeline","body":"A retrieval-augmented generation pipeline combines..."}'

# Submit an obvious paraphrase
curl -X POST https://api.example.com/content \
  -H "Content-Type: application/json" \
  -d '{"id":"art-002","title":"Building a RAG System: Step by Step","body":"Retrieval-augmented generation systems pair a vector store..."}'
# Expected response: {"action":"flag","verdict":"paraphrase","best_match_id":"art-001","best_match_score":0.92}

# Submit a distinct article
curl -X POST https://api.example.com/content \
  -H "Content-Type: application/json" \
  -d '{"id":"art-003","title":"Top 10 Hiking Trails in Patagonia","body":"Patagonia offers some of the world finest..."}'
# Expected response: {"action":"accept","verdict":"unique"}

# Verify Vectorize index count
wrangler vectorize info my-index
```

## Related

- `cloudflare-vectorize-patterns.md` — Vectorize index management and query patterns
- `embedding-generation-patterns.md` — embedding batch strategies and model selection
- `rag-vector-search.md` — vector search fundamentals used in similarity search
- `similarity-threshold-tuning.md` — calibrating cosine similarity thresholds
- `ai-content-moderation-pipeline.md` — combining duplicate detection with moderation
- `metadata-filtering-vectors.md` — filtering Vectorize results by metadata before similarity

## Sources

- Cloudflare Vectorize documentation: https://developers.cloudflare.com/vectorize/
- BAAI BGE model family: https://huggingface.co/BAAI/bge-base-en-v1.5
- Near-Duplicate Document Detection survey: https://arxiv.org/abs/2202.04862
- MinHash LSH for document deduplication: https://en.wikipedia.org/wiki/MinHash
- Cloudflare Workers AI embedding models: https://developers.cloudflare.com/workers-ai/models/
