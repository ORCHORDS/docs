# Workers AI Long Document Summarization Pipeline

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

You need to summarize PDF reports, legal contracts, or long articles that exceed the context window of available Workers AI models (typically 4k–32k tokens). A naive single-shot prompt fails with a context-length error or produces a hallucinated summary that ignores large portions of the text. You need a chunked, map-reduce summarization pipeline that runs entirely on Cloudflare's edge with no external dependencies.

## Context

Workers AI exposes text-generation models such as `@cf/meta/llama-3.1-8b-instruct` and `@cf/mistral/mistral-7b-instruct-v0.1` through the `env.AI.run()` binding. These models have a maximum context of approximately 4096–8192 tokens including the prompt template overhead. A map-reduce approach splits the document into overlapping chunks (map phase), summarizes each chunk individually, then synthesizes the chunk summaries into a final summary (reduce phase). Cloudflare Queues decouple the pipeline stages for documents too long to process in a single Worker invocation (50 ms CPU / 30 s wall-clock limits apply).

---

## 1. Document Chunking Utility

Chunk by approximate token count. A rough heuristic: 1 token ≈ 4 characters for English text.

```typescript
// src/chunker.ts
export interface Chunk {
  index: number;
  text: string;
  tokenEstimate: number;
}

const CHARS_PER_TOKEN = 4;

export function chunkDocument(
  text: string,
  maxTokens: number = 1500,   // leaves room for prompt template + model response
  overlapTokens: number = 150
): Chunk[] {
  const maxChars = maxTokens * CHARS_PER_TOKEN;
  const overlapChars = overlapTokens * CHARS_PER_TOKEN;
  const chunks: Chunk[] = [];

  // Split on paragraph boundaries first to avoid cutting mid-sentence
  const paragraphs = text.split(/\n\n+/);
  let current = '';
  let chunkIndex = 0;

  for (const para of paragraphs) {
    if ((current + '\n\n' + para).length > maxChars && current.length > 0) {
      chunks.push({
        index: chunkIndex++,
        text: current.trim(),
        tokenEstimate: Math.ceil(current.length / CHARS_PER_TOKEN),
      });
      // Overlap: keep the tail of the previous chunk
      current = current.slice(-overlapChars) + '\n\n' + para;
    } else {
      current = current ? current + '\n\n' + para : para;
    }
  }

  if (current.trim()) {
    chunks.push({ index: chunkIndex, text: current.trim(), tokenEstimate: Math.ceil(current.length / CHARS_PER_TOKEN) });
  }

  return chunks;
}
```

---

## 2. Map Phase — Chunk Summarization

Summarize each chunk individually. Use a concise prompt that instructs the model to preserve key facts, dates, and entities.

```typescript
// src/map-summarize.ts
import type { Env } from './types';

const MAP_PROMPT_TEMPLATE = `You are a precise summarizer. Summarize the following excerpt in 3-5 sentences.
Preserve all key facts, names, dates, and figures. Do not add information not present in the text.

EXCERPT:
{text}

SUMMARY:`;

export async function summarizeChunk(
  ai: Ai,
  chunkText: string,
  model: string = '@cf/meta/llama-3.1-8b-instruct'
): Promise<string> {
  const prompt = MAP_PROMPT_TEMPLATE.replace('{text}', chunkText);

  const response = await ai.run(model as Parameters<Ai['run']>[0], {
    prompt,
    max_tokens: 300,
    temperature: 0.1,   // low temperature for factual fidelity
  } as AiTextGenerationInput);

  if (typeof response === 'object' && 'response' in response) {
    return (response as { response: string }).response.trim();
  }
  return '';
}
```

---

## 3. Reduce Phase — Synthesis

Once all chunk summaries are collected, synthesize them into a coherent final summary.

```typescript
// src/reduce-summarize.ts

const REDUCE_PROMPT_TEMPLATE = `You are a precise summarizer. Below are summaries of sequential sections of a document.
Synthesize them into a single coherent summary of 5-8 sentences. Maintain logical flow and do not repeat information.

SECTION SUMMARIES:
{summaries}

FINAL SUMMARY:`;

export async function synthesizeSummaries(
  ai: Ai,
  chunkSummaries: string[],
  model: string = '@cf/meta/llama-3.1-8b-instruct'
): Promise<string> {
  // If the combined summaries are still too long, apply reduce recursively
  const combinedLength = chunkSummaries.join('\n\n').length;
  const MAX_REDUCE_CHARS = 6000;

  let summariesToReduce = chunkSummaries;
  while (summariesToReduce.join('\n\n').length > MAX_REDUCE_CHARS) {
    const half = Math.ceil(summariesToReduce.length / 2);
    const [left, right] = [summariesToReduce.slice(0, half), summariesToReduce.slice(half)];
    summariesToReduce = await Promise.all([
      synthesizeSummaries(ai, left, model),
      synthesizeSummaries(ai, right, model),
    ]);
  }

  const prompt = REDUCE_PROMPT_TEMPLATE.replace('{summaries}',
    summariesToReduce.map((s, i) => `[Section ${i + 1}]\n${s}`).join('\n\n')
  );

  const response = await ai.run(model as Parameters<Ai['run']>[0], {
    prompt,
    max_tokens: 500,
    temperature: 0.1,
  } as AiTextGenerationInput);

  if (typeof response === 'object' && 'response' in response) {
    return (response as { response: string }).response.trim();
  }
  return '';
}
```

---

## 4. Queue-Based Pipeline for Long Documents

Documents exceeding ~20 chunks cannot be processed within a single Worker invocation wall-clock limit. Use Cloudflare Queues to distribute the map phase across multiple Worker invocations.

```typescript
// src/summarization-pipeline.ts
import { chunkDocument } from './chunker';
import { summarizeChunk } from './map-summarize';
import { synthesizeSummaries } from './reduce-summarize';

export interface Env {
  AI: Ai;
  SUMMARIZE_QUEUE: Queue<{ jobId: string; chunkIndex: number; chunkText: string }>;
  KV: KVNamespace;  // stores partial results keyed by jobId
}

// Entry point: called when document is submitted
export async function startSummarizationJob(
  text: string,
  jobId: string,
  env: Env
): Promise<void> {
  const chunks = chunkDocument(text, 1500, 150);

  // Store job metadata
  await env.KV.put(`job:${jobId}:total`, String(chunks.length), { expirationTtl: 3600 });
  await env.KV.put(`job:${jobId}:done`, '0', { expirationTtl: 3600 });

  // Enqueue map tasks
  const messages = chunks.map(chunk => ({
    body: { jobId, chunkIndex: chunk.index, chunkText: chunk.text },
  }));
  await env.SUMMARIZE_QUEUE.sendBatch(messages);
}

// Queue consumer: processes one chunk per message
export const queueHandler = {
  async queue(batch: MessageBatch<{ jobId: string; chunkIndex: number; chunkText: string }>, env: Env) {
    for (const msg of batch.messages) {
      const { jobId, chunkIndex, chunkText } = msg.body;

      const summary = await summarizeChunk(env.AI, chunkText);
      await env.KV.put(`job:${jobId}:chunk:${chunkIndex}`, summary, { expirationTtl: 3600 });

      // Increment done counter
      const done = Number(await env.KV.get(`job:${jobId}:done`)) + 1;
      await env.KV.put(`job:${jobId}:done`, String(done), { expirationTtl: 3600 });
      const total = Number(await env.KV.get(`job:${jobId}:total`));

      if (done >= total) {
        // All chunks summarized — run reduce phase
        const chunkSummaries: string[] = [];
        for (let i = 0; i < total; i++) {
          const s = await env.KV.get(`job:${jobId}:chunk:${i}`) ?? '';
          chunkSummaries.push(s);
        }
        const finalSummary = await synthesizeSummaries(env.AI, chunkSummaries);
        await env.KV.put(`job:${jobId}:result`, finalSummary, { expirationTtl: 86400 });
      }

      msg.ack();
    }
  },
};
```

wrangler.toml additions:
```toml
[[queues.producers]]
queue = "summarize-chunks"
binding = "SUMMARIZE_QUEUE"

[[queues.consumers]]
queue = "summarize-chunks"
max_batch_size = 5
max_batch_timeout = 5
```

---

## 5. Synchronous Path for Short Documents

For documents under ~6000 tokens, skip queues and run map-reduce inline:

```typescript
export async function summarizeShortDocument(text: string, env: Env): Promise<string> {
  const chunks = chunkDocument(text, 1500, 150);
  if (chunks.length === 1) {
    return summarizeChunk(env.AI, chunks[0].text);
  }
  const chunkSummaries = await Promise.all(
    chunks.map(c => summarizeChunk(env.AI, c.text))
  );
  return synthesizeSummaries(env.AI, chunkSummaries);
}
```

---

## Anti-patterns

- **Single-shot summarization of long documents** — exceeds context limits and causes truncation without error, silently dropping the end of the document.
- **No overlap between chunks** — chunk boundaries that cut mid-paragraph lose context. Always use a 10-15% overlap window.
- **Parallelizing all map calls with `Promise.all`** — Workers AI rate limits apply per account; large batches hit 429s. Batch to 3-5 concurrent calls maximum.
- **Storing chunk summaries in-memory between queue messages** — Workers have no shared memory; always persist intermediate results to KV or D1.
- **Using high temperature for summarization** — hallucination risk rises with temperature; keep it at 0.0–0.2 for factual document summarization.

## Gotchas

- Workers AI `max_tokens` caps the response length of each model call, not the input length; exceed the input context and the Worker returns an error with status 400.
- `@cf/meta/llama-3.1-8b-instruct` has an effective context window of ~4096 tokens including the prompt template; with a 300-token response budget and prompt overhead, keep chunk input under 2000 tokens to be safe.
- KV `put` in a Queue consumer counts toward KV write limits; for very high throughput pipelines, use D1 instead as the result store.
- The recursive `synthesizeSummaries` fallback creates new Workers AI calls inside the reduce phase — monitor total invocation count against your Workers AI request quota.
- PDF text extraction is not built into Workers; extract text on the client side or use a Durable Object to call a third-party parsing API, then pass plain text to this pipeline.

## Verification

1. Call `chunkDocument` with a 10,000-character English text and assert `chunks.length > 1` and each chunk is under `maxChars`.
2. Run `summarizeChunk` with a 500-character paragraph in a local `wrangler dev` session and verify a non-empty string is returned within 10 seconds.
3. Submit a 5-chunk document via `startSummarizationJob`, wait for queue processing, and confirm `KV.get('job:{id}:result')` is non-null.
4. Verify overlap: the last `overlapChars` of chunk N should appear at the start of chunk N+1.

## Related

- `rag-document-chunking.md`
- `rag-chunking-strategies-embedding-models.md`
- `llm-for-summarization.md`
- `llm-context-window-cloudflare-workers.md`
- `workers-ai-queue-batch-processing.md`

## Sources

- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/llm/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/kv/
