# LLM-Powered Content Tagging and Categorization Pipeline

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You have a corpus of unstructured content—blog posts, support tickets, product reviews,
user uploads—and need to attach structured metadata (tags, categories, topics, entities)
so it can be filtered, searched, and recommended. Manual tagging is slow and inconsistent.
Rule-based approaches break down with linguistic variety. LLMs can extract rich, accurate
taxonomy labels in a single inference call with structured output, replacing hours of
editorial work with milliseconds of edge compute.

## Context

Content tagging pipelines typically run in two modes:

**Synchronous (inline):** Content is tagged immediately on write, before it's persisted.
Latency budget: ~2 s. Suitable for short text (titles, summaries, reviews < 500 tokens).

**Asynchronous (queue-based):** Content is queued after write and processed by a
background Worker. Latency budget: seconds to minutes. Suitable for long-form content
(articles, transcripts > 500 tokens).

Both modes use the same LLM call; they differ in when and where it's invoked.

A taxonomy should be defined up-front and injected into the system prompt. Open-ended
tag generation produces inconsistent, hard-to-query labels ("AI/ML", "AI", "machine
learning", "artificial intelligence" are the same concept to a human, but four different
values in a WHERE clause).

## Defining a Closed Taxonomy

Store your taxonomy in D1 (or KV for static taxonomies). The model selects from this
list rather than inventing labels.

```sql
-- D1 schema
CREATE TABLE categories (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  parent_slug TEXT,
  display_name TEXT NOT NULL
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  category_slug TEXT NOT NULL REFERENCES categories(slug),
  display_name TEXT NOT NULL
);
```

Load allowed tags at request time:

```typescript
async function loadTaxonomy(db: D1Database): Promise<string[]> {
  const { results } = await db
    .prepare("SELECT slug FROM tags ORDER BY slug")
    .all<{ slug: string }>();
  return results.map((r) => r.slug);
}
```

## Synchronous Tagging on Content Write

```typescript
interface TaggingResult {
  category: string;
  tags: string[];
  confidence: "high" | "medium" | "low";
  language: string;
}

async function tagContent(
  ai: Ai,
  content: string,
  taxonomy: string[]
): Promise<TaggingResult> {
  const systemPrompt = `
You are a content classification assistant. Classify the given text and return JSON only.

Available categories: tutorials, news, opinion, product-review, case-study, reference

Available tags (select up to 8, only from this list):
${taxonomy.join(", ")}

Return this exact JSON schema:
{
  "category": "<one category from the list above>",
  "tags": ["<tag1>", "<tag2>"],
  "confidence": "<high|medium|low>",
  "language": "<ISO 639-1 code e.g. en, es, fr>"
}

Rules:
- Select ONLY tags from the provided list. Never invent new tags.
- Choose 3–8 tags; prefer specificity over breadth.
- Set confidence=low if the text is ambiguous or off-topic for the taxonomy.
- language is the language of the content, not the taxonomy.
`.trim();

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: `Classify this content:\n\n${content.slice(0, 4000)}`,
      },
    ],
    response_format: { type: "json_object" },
    max_tokens: 256,
    temperature: 0.1, // Low temperature for deterministic classification
  });

  const raw = (response as { response: string }).response;

  try {
    const parsed = JSON.parse(raw) as TaggingResult;
    // Validate against taxonomy
    parsed.tags = parsed.tags.filter((t) => taxonomy.includes(t));
    return parsed;
  } catch {
    // Fallback on parse failure
    return { category: "uncategorized", tags: [], confidence: "low", language: "en" };
  }
}
```

## Asynchronous Pipeline with Queues

For long content, enqueue after write and process in a consumer Worker:

```typescript
// Producer (API handler)
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const body = await request.json<{ id: string; content: string }>();

    // Persist content first (untagged)
    await env.DB.prepare(
      "INSERT INTO articles (id, content, status) VALUES (?, ?, 'pending')"
    )
      .bind(body.id, body.content)
      .run();

    // Enqueue tagging job
    await env.TAGGING_QUEUE.send({
      articleId: body.id,
      contentPreview: body.content.slice(0, 200),
    });

    return Response.json({ id: body.id, status: "pending" }, { status: 202 });
  },
};
```

```typescript
// Consumer Worker (queue handler)
export default {
  async queue(batch: MessageBatch<{ articleId: string }>, env: Env): Promise<void> {
    const taxonomy = await loadTaxonomy(env.DB);

    for (const message of batch.messages) {
      const { articleId } = message.body;

      try {
        const row = await env.DB.prepare(
          "SELECT content FROM articles WHERE id = ?"
        )
          .bind(articleId)
          .first<{ content: string }>();

        if (!row) { message.ack(); continue; }

        const result = await tagContent(env.AI, row.content, taxonomy);

        await env.DB.prepare(
          `UPDATE articles
           SET category = ?, tags = ?, tag_confidence = ?, language = ?, status = 'tagged'
           WHERE id = ?`
        )
          .bind(
            result.category,
            JSON.stringify(result.tags),
            result.confidence,
            result.language,
            articleId
          )
          .run();

        message.ack();
      } catch (err) {
        // Retry on failure (up to queue's maxRetries)
        message.retry();
      }
    }
  },
};
```

## Hierarchical / Multi-level Categorization

For deep taxonomies (e.g. IAB Content Taxonomy), use a two-pass approach to keep the
prompt manageable:

**Pass 1:** Classify into top-level category (10–20 options).

**Pass 2:** Given the top-level category, classify into subcategory (10–30 options in
that branch).

```typescript
async function hierarchicalTag(
  ai: Ai,
  content: string,
  taxonomy: Record<string, string[]>
): Promise<{ top: string; sub: string }> {
  const topCategories = Object.keys(taxonomy);

  // Pass 1
  const pass1 = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "user",
        content:
          `Classify into ONE category. Options: ${topCategories.join(", ")}\n\n` +
          `Text: ${content.slice(0, 1000)}\n\nReply with only the category name.`,
      },
    ],
    max_tokens: 32,
    temperature: 0.0,
  });

  const top = ((pass1 as { response: string }).response ?? "").trim();
  const subcategories = taxonomy[top] ?? [];

  if (subcategories.length === 0) return { top, sub: "" };

  // Pass 2
  const pass2 = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "user",
        content:
          `Category is "${top}". Pick ONE subcategory: ${subcategories.join(", ")}\n\n` +
          `Text: ${content.slice(0, 1000)}\n\nReply with only the subcategory name.`,
      },
    ],
    max_tokens: 32,
    temperature: 0.0,
  });

  const sub = ((pass2 as { response: string }).response ?? "").trim();
  return { top, sub };
}
```

## Batch Tagging for Backfills

When tagging existing content at scale, batch requests through a Queue with concurrency
limits to avoid hitting Workers AI rate limits:

```typescript
// Seed backfill queue from a D1 cursor
async function seedBackfill(db: D1Database, queue: Queue): Promise<void> {
  let cursor: string | undefined;
  do {
    const { results, meta } = await db
      .prepare(
        "SELECT id FROM articles WHERE status = 'pending' ORDER BY id LIMIT 100"
      )
      .all<{ id: string }>();

    const messages = results.map((r) => ({ body: { articleId: r.id } }));
    if (messages.length > 0) await queue.sendBatch(messages);

    cursor = results.length === 100 ? results[99].id : undefined;
  } while (cursor);
}
```

Queue consumer automatically rate-limits via `max_concurrency` in `wrangler.toml`:

```toml
[[queues.consumers]]
queue = "tagging-queue"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
max_concurrency = 5  # Max concurrent consumer invocations
```

## Anti-patterns

- **Open-ended tag generation.** Without a closed taxonomy, the model invents synonyms and
  partial labels that fragment your data. Always constrain to an enumerated list.
- **Tagging on every read.** Compute tags once on write, store in D1. Never call the LLM
  on every read request.
- **Embedding the full taxonomy in every token budget.** If your taxonomy has thousands
  of tags, chunk it into category-scoped subsets and do hierarchical tagging.
- **Ignoring confidence scores.** Low-confidence results should be flagged for human
  review rather than published automatically.
- **Using temperature > 0.2 for classification.** Higher temperatures increase tag
  diversity but reduce consistency; classification is a retrieval task, not a generation
  task.
- **Treating tag arrays as sets.** JSON column storage means you can't use SQL IN on tags
  without a JSON_EACH join. Materialise tags into a junction table if you need filter queries.

## Gotchas

- `response_format: { type: "json_object" }` does not guarantee schema compliance—it only
  ensures valid JSON. Validate and coerce the response before storing.
- Workers AI `@cf/meta/llama-3.1-8b-instruct` has a 4096-token context window. Truncate
  long content before sending; consider summarising first for very long documents.
- Queue retries replay the entire `queue()` handler. Make the handler idempotent by
  checking `status = 'tagged'` before processing.
- D1 JSON functions (`json_each`, `json_extract`) require SQLite 3.38+; D1 uses an
  embedded SQLite so functions are available but syntax differs from PostgreSQL's `@>`.
- Taxonomy drift: when you add or rename tags, existing content is labelled with stale
  values. Run a re-tagging migration job and version your taxonomy.
- LLM hallucination of out-of-taxonomy tags drops to near-zero with `temperature=0.0`
  and explicit "never invent tags" instructions, but never fully to zero. Always filter.

## Verification

```bash
# Post a test article and inspect tags
curl -X POST https://api.example.com/articles \
  -H "Content-Type: application/json" \
  -d '{"id":"test-001","content":"A tutorial on building RAG pipelines with Cloudflare Vectorize and Workers AI."}'

# Poll for tagged status
curl https://api.example.com/articles/test-001 | jq '{status, category, tags, tag_confidence}'
# Expected:
# { "status": "tagged", "category": "tutorials", "tags": ["rag","vectorize","workers-ai","cloudflare"], "tag_confidence": "high" }

# Verify D1 storage
wrangler d1 execute my-db --command \
  "SELECT category, tags, tag_confidence FROM articles WHERE id='test-001';"
```

## Related

- `llm-for-classification.md` — lower-level LLM classification patterns
- `llm-structured-output-json-mode.md` — enforcing structured responses from LLMs
- `retrieval-augmented-generation-d1-vectorize.md` — tag-augmented semantic search
- `llm-batch-processing.md` — batch patterns for high-volume tagging workloads
- `llm-quality-scoring-pipeline-d1.md` — storing and querying LLM-generated scores in D1

## Sources

- Cloudflare Workers AI — Supported Models: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- IAB Tech Lab Content Taxonomy: https://iabtechlab.com/standards/content-taxonomy/
- Cloudflare D1 JSON functions: https://developers.cloudflare.com/d1/platform/sql-statements/
