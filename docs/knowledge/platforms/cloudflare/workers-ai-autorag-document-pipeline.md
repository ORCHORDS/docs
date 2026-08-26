# Workers AI AutoRAG Document Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want a fully managed RAG (Retrieval-Augmented Generation) pipeline inside Cloudflare Workers without stitching together Vectorize, R2, and an embedding model manually. Workers AI AutoRAG ingests source documents from R2, chunks them, embeds them, and answers questions — all through a single binding with no external infra.

## Context

AutoRAG is a managed RAG feature in Workers AI that takes an R2 bucket as a source, runs periodic or on-demand indexing, and exposes both a search and a `/ai-search` query interface. The pipeline handles chunking strategy, embedding model selection, and vector storage internally. Workers bind to it via `env.MY_AUTORAG` and call `.search()` or `.aiSearch()`. This differs from composing Vectorize + AI bindings manually — AutoRAG owns the index lifecycle.

## Creating an AutoRAG Instance via Wrangler

```toml
# wrangler.toml
name = "my-rag-worker"
compatibility_date = "2025-11-01"

[[ai]]
binding = "AI"

[[autorag]]
binding = "MY_AUTORAG"
name = "my-docs-autorag"          # created via: wrangler autorag create my-docs-autorag

[[r2_buckets]]
binding = "DOCS_BUCKET"
bucket_name = "my-documents"
```

```bash
# Create the AutoRAG instance and link it to an R2 bucket
wrangler autorag create my-docs-autorag --r2-bucket my-documents
# Trigger an initial index run
wrangler autorag index my-docs-autorag
```

## Semantic Search Against the AutoRAG Index

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = await req.json<{ query: string }>();

    // Vector search only — returns scored document chunks
    const results = await env.MY_AUTORAG.search(query, {
      maxResults: 5,
      scoreThreshold: 0.7,  // cosine similarity floor
    });

    return Response.json(results);
  },
} satisfies ExportedHandler<Env>;

interface Env {
  MY_AUTORAG: AutoRAG;
}
```

## AI-Search: Grounded LLM Response

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = await req.json<{ query: string }>();

    // Retrieves chunks then calls an LLM with grounding context
    const answer = await env.MY_AUTORAG.aiSearch(query, {
      maxResults: 8,
      model: "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
      systemPrompt: "Answer only from the provided context. Say 'I don't know' if the context is insufficient.",
    });

    // answer.response   — LLM text
    // answer.sources    — [{filename, chunk, score}]
    return Response.json({
      answer: answer.response,
      sources: answer.sources.map((s) => ({ file: s.filename, score: s.score })),
    });
  },
} satisfies ExportedHandler<Env>;
```

## Streaming AI-Search Response

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = await req.json<{ query: string }>();

    const stream = await env.MY_AUTORAG.aiSearch(query, {
      stream: true,
      model: "@cf/meta/llama-3.1-8b-instruct",
    });

    // stream is a ReadableStream of SSE chunks
    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Triggering Re-index on R2 Upload Event

```typescript
// Triggered whenever a new PDF/MD lands in the source bucket
export default {
  async queue(batch: MessageBatch<R2Event>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;
      if (event.action === "PutObject") {
        // AutoRAG polls on a schedule, but explicit re-index keeps latency low
        await env.MY_AUTORAG.reindex();
        msg.ack();
      }
    }
  },
} satisfies ExportedHandler<Env>;

interface R2Event {
  action: string;
  object: { key: string };
}
```

## Anti-patterns

- Calling `aiSearch()` inside a CPU-bound loop — each call is a full LLM inference; batch or cache aggressively.
- Storing raw HTML in the source bucket; AutoRAG's chunker works best with Markdown, plain text, or PDF. Strip HTML before upload.
- Ignoring `scoreThreshold`; returning low-score chunks to an LLM inflates prompt tokens and degrades answer quality.
- Using AutoRAG for real-time data — it indexes on a schedule (or on explicit `reindex()`); it is not a live search engine.

## Gotchas

- AutoRAG indexes are eventually consistent; a document uploaded to R2 may not appear in search results until the next index cycle (typically minutes).
- `aiSearch()` counts both embedding and LLM inference tokens against your Workers AI quota; high-concurrency endpoints can exhaust limits quickly.
- The `model` parameter in `aiSearch()` must be a Workers AI text-generation model; passing an embedding model throws at runtime.
- Re-indexing is a heavy operation — calling `reindex()` on every R2 write will hit rate limits; debounce with a Queue or a Durable Object alarm.
- AutoRAG instances are per-account, not per-Worker; sharing an instance across Workers is intentional but means index updates affect all consumers simultaneously.

## Verification

```bash
# List AutoRAG instances
wrangler autorag list

# Check index status and last run time
wrangler autorag get my-docs-autorag

# Run a test query against the CLI
wrangler autorag search my-docs-autorag "how do I reset a password?"

# Tail logs from the Worker using the binding
wrangler tail my-rag-worker --format pretty
```

## Related

- `workers-ai-embedding-batch-vectorize-upsert.md` — manual Vectorize pipeline alternative
- `workers-ai-structured-output-tool-calling.md` — tool calling alongside RAG answers
- `cloudflare-r2-object-lifecycle-multipart.md` — managing source document lifecycle
- `r2-event-notifications.md` — R2 event triggers for reindex automation
- `workers-ai-2026.md` — Workers AI model catalog and billing overview

## Sources

- https://developers.cloudflare.com/workers-ai/features/autorag/
- https://developers.cloudflare.com/workers-ai/features/autorag/get-started/
- https://developers.cloudflare.com/workers-ai/features/autorag/configuration/
- https://blog.cloudflare.com/autorag-serverless-rag-on-cloudflare/
