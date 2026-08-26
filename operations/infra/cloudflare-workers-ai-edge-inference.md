# Cloudflare Workers AI: Edge LLM Inference at Scale

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

An application calling a centralised LLM API (OpenAI, Anthropic) from a Cloudflare Worker
adds a North America round-trip to every inference call, regardless of where the user is.
Latency spikes to 500ms–2s for the first token. Cold requests that also include a database
call now have two sequential remote round-trips before any user-visible response arrives.
Streaming responses are bottlenecked by the latency to the single API origin.

Alternatively: an ML team wants to run a fine-tuned open-source model (Llama, Mistral,
Phi) without managing GPU infrastructure, scaling, or idle capacity — but inference
speed is still the constraint.

## Context

Cloudflare Workers AI is a serverless inference service embedded in Cloudflare's global
network. Models run on Cloudflare's GPU infrastructure distributed across data centres,
with requests routed to the nearest GPU cluster. The calling Worker runs on the same
edge node (or in an adjacent PoP), so the Worker-to-inference-backend latency is measured
in single-digit milliseconds rather than hundreds.

The Workers AI binding is declared in `wrangler.toml`, gives the Worker an `env.AI` object,
and is billed per neuron (Cloudflare's token-equivalent unit). There is no provisioning, no
pod warm-up, and no quota management beyond account-level rate limits.

Available model categories (2026):
- **Text generation**: `@cf/meta/llama-3.1-8b-instruct`, `@cf/meta/llama-3.3-70b-instruct-fp8-fast`, `@cf/mistral/mistral-7b-instruct-v0.1`
- **Text embeddings**: `@cf/baai/bge-base-en-v1.5`, `@cf/baai/bge-large-en-v1.5`
- **Image classification**: `@cf/microsoft/resnet-50`
- **Object detection**: `@cf/facebook/detr-resnet-50`
- **Image-to-text (vision)**: `@cf/llava-hf/llava-1.5-7b-hf`
- **Speech-to-text**: `@cf/openai/whisper`
- **Text-to-image**: `@cf/stabilityai/stable-diffusion-xl-base-1.0`
- **Translation**: `@cf/meta/m2m100-1.2b`

---

## Section 1: Basic Setup and Binding

```toml
# wrangler.toml
name = "ai-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[ai]
binding = "AI"
```

```typescript
// src/index.ts
export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json<{ prompt: string }>();

    const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: prompt },
      ],
    });

    return Response.json(response);
  },
};
```

Type definitions for the `Ai` binding are in `@cloudflare/workers-types`. Install:

```bash
npm install -D @cloudflare/workers-types
```

```json
// tsconfig.json
{
  "compilerOptions": {
    "types": ["@cloudflare/workers-types"]
  }
}
```

---

## Section 2: Streaming Responses

For text generation, streaming dramatically reduces time-to-first-token for the end user.
Workers AI supports streaming via the `stream: true` option, which returns a
`ReadableStream`.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { messages } = await request.json<{
      messages: RoleScopedChatInput[];
    }>();

    const stream = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages,
      stream: true,
      max_tokens: 1024,
      temperature: 0.7,
    });

    // Return as Server-Sent Events for the browser
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Transfer-Encoding': 'chunked',
        'Access-Control-Allow-Origin': '*',
      },
    });
  },
};
```

Client-side consumption:

```typescript
// Browser / client Worker
const response = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ messages }),
});

const reader = response.body!.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() ?? '';

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const data = line.slice(6);
    if (data === '[DONE]') return;

    try {
      const parsed = JSON.parse(data) as { response: string };
      process.stdout.write(parsed.response);
    } catch {
      // Partial SSE chunk, continue buffering
    }
  }
}
```

---

## Section 3: Embeddings for Semantic Search

Workers AI embeddings are the fastest path to adding semantic search to a Cloudflare-stack
application: embed in the Worker, store vectors in Vectorize (Cloudflare's vector database),
and query on the same edge node.

```toml
# wrangler.toml
[ai]
binding = "AI"

[[vectorize]]
binding = "VECTORIZE"
index_name = "products-index"
```

```typescript
// src/embeddings.ts
export async function embedText(env: Env, text: string): Promise<number[]> {
  const result = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [text],
  });
  return result.data[0];
}

export async function indexDocument(
  env: Env,
  id: string,
  text: string,
  metadata: Record<string, string>
): Promise<void> {
  const vector = await embedText(env, text);
  await env.VECTORIZE.upsert([{ id, values: vector, metadata }]);
}

export async function semanticSearch(
  env: Env,
  query: string,
  topK = 5
): Promise<VectorizeMatches> {
  const queryVector = await embedText(env, query);
  return env.VECTORIZE.query(queryVector, {
    topK,
    returnMetadata: 'all',
    returnValues: false,
  });
}
```

```typescript
// src/index.ts — search endpoint
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/search') {
      const q = url.searchParams.get('q');
      if (!q) return new Response('Missing q', { status: 400 });

      const results = await semanticSearch(env, q);
      return Response.json(results.matches.map((m) => ({
        id: m.id,
        score: m.score,
        ...m.metadata,
      })));
    }

    return new Response('Not found', { status: 404 });
  },
};
```

Create the Vectorize index before deploying:

```bash
wrangler vectorize create products-index \
  --dimensions 768 \
  --metric cosine
```

---

## Section 4: RAG Pattern — Retrieval-Augmented Generation

Combine semantic search with text generation to give the LLM grounded context from your
own data, preventing hallucination of facts that change (prices, product specs, policies).

```typescript
// src/rag.ts
export async function ragAnswer(
  env: Env,
  question: string
): Promise<string> {
  // Step 1: Retrieve relevant context
  const searchResults = await semanticSearch(env, question, 3);
  const context = searchResults.matches
    .map((m) => m.metadata?.content as string ?? '')
    .filter(Boolean)
    .join('\n\n---\n\n');

  if (!context) {
    return 'I do not have enough context to answer that question.';
  }

  // Step 2: Generate answer grounded in retrieved context
  const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content: `You are a helpful assistant. Answer questions using ONLY the provided context.
If the context does not contain the answer, say so. Do not make up information.

Context:
${context}`,
      },
      { role: 'user', content: question },
    ],
    max_tokens: 512,
    temperature: 0.1, // Low temperature for factual answers
  });

  return (result as { response: string }).response;
}
```

---

## Section 5: Caching Inference Responses

LLM inference is expensive. Cache deterministic prompts (FAQs, classification tasks, fixed
system prompts) in KV with a TTL that matches the acceptable staleness.

```typescript
// src/cached-inference.ts
export async function cachedClassify(
  env: Env,
  text: string,
  categories: string[]
): Promise<string> {
  // Normalise and hash the input for a stable cache key
  const cacheKey = `classify:${await sha256(
    JSON.stringify({ text: text.trim().toLowerCase(), categories: categories.sort() })
  )}`;

  // Try cache first
  const cached = await env.KV.get(cacheKey);
  if (cached) return cached;

  // Run inference
  const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content: `Classify the following text into exactly one category from this list: ${categories.join(', ')}.
Respond with ONLY the category name, nothing else.`,
      },
      { role: 'user', content: text },
    ],
    max_tokens: 20,
    temperature: 0,
  });

  const category = ((result as { response: string }).response).trim();

  // Cache for 24 hours — categories don't change often
  await env.KV.put(cacheKey, category, { expirationTtl: 86400 });
  return category;
}

async function sha256(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## Section 6: Cost Monitoring and Neuron Budget

Workers AI bills per **neuron** — Cloudflare's unit that abstracts GPU operations.
Different models consume different neuron rates per token.

```typescript
// Monitor inference cost with Workers Analytics Engine
export interface Env {
  AI: Ai;
  AE: AnalyticsEngineDataset;
}

async function runWithCostTracking(
  env: Env,
  model: string,
  messages: RoleScopedChatInput[]
): Promise<AiTextGenerationOutput> {
  const start = Date.now();

  const result = (await env.AI.run(model, { messages })) as AiTextGenerationOutput;

  const latencyMs = Date.now() - start;

  // Estimate neurons — consult Cloudflare docs for exact rates per model
  // As of 2026: llama-3.1-8b ≈ 0.011 neurons/token for text generation
  const estimatedNeurons = 0.011 * (messages.reduce((sum, m) => sum + m.content.length / 4, 0));

  env.AE.writeDataPoint({
    blobs: [model, 'inference'],
    doubles: [latencyMs, estimatedNeurons],
    indexes: [model],
  });

  return result;
}
```

Set up a cost alert using a Cloudflare Worker + PagerDuty if daily neuron consumption
exceeds a threshold:

```typescript
// cost-guard/src/index.ts — scheduled daily
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const usage = await fetchWorkersAIUsage(env);
    if (usage.neurons_today > env.DAILY_NEURON_BUDGET) {
      await triggerAlert(env, `Workers AI budget exceeded: ${usage.neurons_today} neurons`);
    }
  },
};
```

---

## Anti-Patterns

- **Not streaming for interactive use cases** — sending a full LLM response as a JSON body
  blocks the user for the full generation time (5–30 seconds for long outputs). Always
  stream for any user-facing text generation.
- **Using Workers AI for fine-tuned proprietary models** — Workers AI only serves
  Cloudflare-hosted models. If you need a fine-tuned model, use a Cloudflare Worker as an
  API proxy to your own GPU host (Runpod, Lambda, BentoML) and cache aggressively.
- **Running embedding generation on every request without caching** — embedding the same
  document on every search query wastes neurons. Pre-compute and store embeddings in
  Vectorize when content is ingested, not at query time.
- **No temperature control for classification** — classification prompts need `temperature: 0`
  for deterministic output. Any non-zero temperature will produce inconsistent category
  assignments from identical inputs.
- **Concatenating large contexts without chunking** — Workers AI has a context window limit
  per model. Exceeding it causes silent truncation or errors. Chunk documents at ingest time
  and store multiple Vectorize vectors per document.

---

## Gotchas

- Workers AI is subject to the Worker CPU time limit (50ms in bundled plan, 30s in paid
  plan). Inference for large models can take 5–15 seconds. You **must** be on the Workers
  Paid plan for AI inference workloads.
- The `stream: true` response returns raw SSE bytes from Cloudflare. The format uses the
  `[DONE]` sentinel. Parsing must handle partial chunks — do not assume each `TextDecoder`
  chunk is a complete SSE event.
- Workers AI responses are not deterministic even at `temperature: 0` due to floating-point
  non-determinism across GPU clusters. Do not use AI output as a cache key input.
- Vectorize index dimensions must match the embedding model output exactly. `bge-base-en-v1.5`
  outputs 768 dimensions; `bge-large-en-v1.5` outputs 1024. Creating the index with the
  wrong dimension count causes `upsert` failures.
- Workers AI `env.AI.run()` is not available in the Miniflare local dev environment without
  the `--remote` flag. Local development requires `wrangler dev --remote` to proxy AI calls
  to Cloudflare's edge.

---

## Verification

```bash
# Deploy and test inference
wrangler deploy

curl -s -X POST "https://ai-worker.example.workers.dev" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarise the CAP theorem in two sentences."}' \
  | jq '.response'

# Test streaming
curl -s -N -X POST "https://ai-worker.example.workers.dev/stream" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Count to 5"}]}'

# Check Vectorize index stats
wrangler vectorize info products-index

# List available Workers AI models
curl -sH "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/ai/models/search" \
  | jq '.result[] | .name'
```

---

## Related Articles

- `cloudflare-workers-limits-resource-planning.md` — CPU time limits for AI workloads
- `keda-cloudflare-queue-consumers.md` — async inference queuing patterns
- `cloudflare-durable-objects-stateful-edge.md` — per-session conversation history storage
- `cloudflare-cost-attribution-tagging.md` — tagging neuron spend by feature
- `workers-opentelemetry-tail-workers.md` — tracing inference latency

---

## Sources

- Workers AI documentation: https://developers.cloudflare.com/workers-ai/
- Workers AI models catalogue: https://developers.cloudflare.com/workers-ai/models/
- Vectorize documentation: https://developers.cloudflare.com/vectorize/
- Workers AI pricing (neurons): https://developers.cloudflare.com/workers-ai/platform/pricing/
- RAG with Workers AI tutorial: https://developers.cloudflare.com/workers-ai/tutorials/build-a-retrieval-augmented-generation-ai/
