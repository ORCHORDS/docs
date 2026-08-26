# ml-inference-edge

**Issue:** ML inference at the edge — Workers AI + Vectorize
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have an ML model. You call OpenAI for inference. Each
call costs $0.01-0.10. At 1M requests/day, that's $10k-$100k/
day. You want to use a cheaper option. You try Workers AI.
The model is faster but less accurate. You compromise.

## Root cause
**ML inference has tradeoffs:**
- **Accuracy vs cost:** bigger model = more accurate = more
  expensive
- **Latency vs cost:** faster inference = more cost
- **Privacy vs centralization:** inference on user data is
  fine if the model is on your infrastructure
- **Customization vs ease:** custom model = better fit = more
  engineering

**Source:** Workers AI docs:
https://developers.cloudflare.com/workers-ai/

## The options for ML inference

### 1. OpenAI / Anthropic / Google (managed, expensive)
```ts
import OpenAI from 'openai';
const openai = new OpenAI({ apiKey: env.OPENAI_API_KEY });

const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Hello' }],
});
```

✅ **Best accuracy** (large models)
✅ **Easy to integrate**
❌ **$$$** ($0.01-$0.10 per call)
❌ **Latency** (500ms-2s per call)
❌ **Privacy** (your data goes to OpenAI's servers)

### 2. Workers AI (CF edge, cheap)
```ts
const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  messages: [{ role: 'user', content: 'Hello' }],
});
```

✅ **Cheap** ($0.01 per 1M tokens)
✅ **Fast** (50-200ms)
✅ **Privacy** (runs on CF's edge, no data leaves)
❌ **Smaller models** (7B vs GPT-4's 1T+)
❌ **Limited model selection**

### 3. Self-hosted on GPU (your infra, expensive upfront)
```ts
// Call your own inference server
const response = await fetch('https://inference.internal/v1/chat', {
  method: 'POST',
  body: JSON.stringify({ model: 'llama-2-70b', messages: [...] }),
});
```

✅ **Full control** (any model, any size)
✅ **Privacy** (your data stays)
❌ **$$$** (GPU instances: $1-5/hour)
❌ **Operations** (model serving, scaling, monitoring)

### 4. Quantized / distilled model on CPU (cheap, less accurate)
```ts
// Run a 7B int4 quantized model on a CPU
// ~10-50ms per query on a modern CPU
```

✅ **Cheap** (CPU is cheap)
✅ **Privacy** (your infra)
❌ **Less accurate** (quantization reduces accuracy)
❌ **Still needs infra**

## The decision matrix

| Use case | Use |
|---|---|
| Complex reasoning, highest accuracy | OpenAI / Anthropic |
| Simple tasks (classification, extraction) | Workers AI |
| Real-time inference at the edge | Workers AI + Vectorize |
| Custom model on your data | Self-hosted on GPU |
| Cost-sensitive, low-accuracy-tolerance | Quantized model on CPU |

## Workers AI model selection

CF Workers AI has many models. Common ones:

| Model | Use case | Size | Latency |
|---|---|---|---|
| `@cf/meta/llama-2-7b-chat-int8` | General chat | 7B | 100-200ms |
| `@cf/mistral/mistral-7b-instruct-v0.1` | General chat | 7B | 100-200ms |
| `@cf/google/embedding-gecko-300m` | Embeddings | 300M | 10-30ms |
| `@cf/openai/whisper` | Speech-to-text | 1.5B | 1-3s |
| `@cf/stabilityai/stable-diffusion-xl-base-1.0` | Image generation | 3.5B | 5-15s |

For most apps, the 7B chat models are the right choice for
cost + accuracy.

## Vectorize for semantic search

For "find similar" use cases:
```ts
// Generate an embedding
const embedding = await env.AI.run('@cf/google/embedding-gecko-300m', {
  text: 'How do I reset my password?',
});

// Search Vectorize
const results = await env.VECTORIZE.query(embedding.data[0], {
  topK: 5,
  filter: { tenant_id: 't_123' },
  returnMetadata: true,
});
```

The query is fast (~30ms) because the embedding is pre-
computed and the search is in-memory.

## The "RAG" pattern (Retrieval-Augmented Generation)

For Q&A chatbots, combine Vectorize + a chat model:
```ts
async function ragAnswer(query: string, env: Env): Promise<string> {
  // 1. Embed the query
  const queryEmbedding = await env.AI.run('@cf/google/embedding-gecko-300m', {
    text: query,
  });

  // 2. Find similar documents
  const docs = await env.VECTORIZE.query(queryEmbedding.data[0], {
    topK: 5,
  });

  // 3. Build the context
  const context = docs.matches.map(m => m.metadata.text).join('\n\n');

  // 4. Generate the answer
  const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
    messages: [
      { role: 'system', content: `Answer based on:\n${context}` },
      { role: 'user', content: query },
    ],
  });

  return response.response;
}
```

The RAG pattern gives the model relevant context, so the
answer is grounded in your data.

## The "fine-tuning" alternative

If Workers AI's models are not accurate enough, fine-tune
your own model:
1. Collect training data (user Q&A, your docs, etc.)
2. Fine-tune a base model (Llama, Mistral)
3. Deploy on Workers AI (CF supports fine-tuned models)

Fine-tuning is expensive (data labeling, compute) but
produces a model that fits your domain.

## The "edge inference" performance tips

1. **Cache embeddings** — they're expensive to compute
2. **Batch requests** — Workers AI supports batching
3. **Use the smallest model that works** — bigger is slower
4. **Pre-compute** when possible (not at request time)
5. **Stream** long responses (Workers AI supports streaming)

```ts
// Streaming
const stream = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  messages: [...],
  stream: true,
});
return new Response(stream, { headers: { 'content-type': 'text/event-stream' } });
```

## Verification
- **Test:** `test/workers-ai.test.ts > model returns expected
  output for test inputs` — passes
- **Live:** Inference latency p99 < 500ms
- **Audit:** Monthly review of model accuracy + cost

## Gotchas
- **Workers AI has rate limits** (per-minute, per-day). For
  high-volume apps, you may need to queue.
- **Workers AI models are not always updated.** The model
  version is pinned; you don't get auto-updates.
- **Embeddings have a cost** (1 per query). At 1M queries/
  day, that's $30/day just for embeddings.
- **Fine-tuning is a project, not a feature.** Plan for
  weeks of data labeling + training + evaluation.
- **The "best model" changes.** A model that's SOTA today
  is average in 6 months. Re-evaluate quarterly.

## Related
- `feature-store-decisions.md`
- `search-architecture.md`
- `cost-optimization-cloudflare.md`
- Workers AI: https://developers.cloudflare.com/workers-ai/
- Vectorize: https://developers.cloudflare.com/vectorize/
