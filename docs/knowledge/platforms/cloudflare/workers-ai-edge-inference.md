# Cloudflare Workers AI — Edge Inference

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your AI features depend on centralized GPU clusters, adding 200-500ms
of latency for users far from the data center. Scaling inference
infrastructure requires managing GPU provisioning, autoscaling, and
load balancing. You need to run LLM inference, embeddings, or image
generation but cannot justify the cost and complexity of self-hosted GPU
infrastructure for moderate workloads.

## Context

Workers AI is Cloudflare's serverless AI inference platform that runs
models on GPUs deployed across Cloudflare's global edge network (300+
cities). Instead of managing GPU clusters, you call an API from a
Cloudflare Worker and pay per request. In 2026, Workers AI supports
50+ models across text generation (Llama 3/4, Mistral, Qwen, DeepSeek),
image generation (Stable Diffusion, FLUX), speech-to-text (Whisper),
embeddings, and classification. Typical inference latency is < 100ms
for edge-deployed models, compared to 300-500ms for centralized cloud
GPU services.

## Basic usage

```typescript
// Worker with AI inference
export default {
  async fetch(request, env) {
    const { prompt } = await request.json();

    const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: prompt },
      ],
      max_tokens: 512,
    });

    return Response.json(response);
  },
};
```

```toml
# wrangler.toml
[ai]
binding = "AI"
```

## Model categories

### Text generation (LLMs)

| Model | Parameters | Speed | Use case |
|---|---|---|---|
| `@cf/meta/llama-3.1-8b-instruct` | 8B | Fast | Chat, summarization |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 70B | Medium | Complex reasoning |
| `@cf/mistral/mistral-7b-instruct-v0.2` | 7B | Fast | Instruction following |
| `@cf/qwen/qwen2.5-coder-32b-instruct` | 32B | Medium | Code generation |
| `@cf/deepseek/deepseek-r1-distill-qwen-32b` | 32B | Medium | Reasoning tasks |

### Embeddings

```typescript
const embeddings = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
  text: ['Document text to embed', 'Another document'],
});
// Returns: { data: [{ values: [0.123, -0.456, ...] }] }
```

### Image generation

```typescript
const image = await env.AI.run('@cf/black-forest-labs/flux-1-schnell', {
  prompt: 'A mountain landscape at sunset',
  num_steps: 4,
});
// Returns: ReadableStream (PNG image)
```

### Speech-to-text

```typescript
const transcription = await env.AI.run('@cf/openai/whisper-large-v3-turbo', {
  audio: audioBuffer,
});
// Returns: { text: "Transcribed speech content" }
```

## Streaming responses

```typescript
const stream = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
  messages: [{ role: 'user', content: 'Explain quantum computing' }],
  stream: true,
});

return new Response(stream, {
  headers: { 'Content-Type': 'text/event-stream' },
});
```

## RAG pattern with Vectorize

```typescript
export default {
  async fetch(request, env) {
    const { query } = await request.json();

    // 1. Embed the query
    const queryEmbedding = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
      text: [query],
    });

    // 2. Search Vectorize for relevant documents
    const results = await env.VECTORIZE.query(
      queryEmbedding.data[0].values,
      { topK: 5, returnMetadata: 'all' }
    );

    // 3. Build context from results
    const context = results.matches
      .map((m) => m.metadata.text)
      .join('\n\n');

    // 4. Generate answer with context
    const answer = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        {
          role: 'system',
          content: `Answer based on this context:\n${context}`,
        },
        { role: 'user', content: query },
      ],
    });

    return Response.json(answer);
  },
};
```

## Pricing

| Tier | Included | Additional |
|---|---|---|
| **Free** | 10,000 Neurons/day | Not available |
| **Workers Paid** | 10,000 Neurons/day | $0.011 per 1,000 Neurons |

Neurons are a normalized unit — different models consume different
amounts of Neurons per request based on model size and input/output
tokens.

| Model category | Approximate Neurons per request |
|---|---|
| Small LLM (7-8B) | 50-200 |
| Large LLM (70B) | 500-2000 |
| Embeddings | 5-20 |
| Image generation | 100-500 |
| Whisper (speech) | 50-200 |

## Anti-patterns

- **Using Workers AI for high-throughput batch processing** — Workers AI
  is optimized for real-time inference, not batch jobs processing
  thousands of items. Use dedicated GPU infrastructure (RunPod, Modal)
  for batch workloads.
- **No caching** — identical prompts generate identical responses but
  consume GPU resources each time. Use AI Gateway or KV caching for
  repeated queries.
- **Choosing the largest model by default** — Llama 70B is 10x more
  expensive than Llama 8B. Start with smaller models and upgrade only
  if quality is insufficient for your use case.
- **Synchronous inference in hot paths** — AI inference adds latency.
  For latency-critical paths, run inference asynchronously (Queues,
  Durable Objects) and cache results.

## Gotchas

- **Model availability varies by PoP** — not all edge locations have
  GPUs. Requests may be routed to the nearest GPU-equipped location,
  adding latency compared to models that run on CPU.
- **Token limits** — each model has maximum input and output token
  limits. Llama 3.1 8B supports 8K context; larger models support
  more. Plan for context window constraints.
- **Rate limits** — free tier is limited to 10,000 Neurons/day. Paid
  tier has higher limits but still rate-limited per account. Contact
  Cloudflare for enterprise limits.
- **Model deprecation** — Cloudflare periodically updates model versions.
  Pin to specific model versions (`@cf/meta/llama-3.1-8b-instruct`)
  rather than aliases that may change.

## Verification

- AI binding is configured in wrangler.toml.
- Model selection matches the use case (size vs. quality trade-off).
- Streaming is enabled for user-facing text generation.
- Caching is implemented for repeated or similar queries.
- Error handling covers model unavailability and rate limits.
- Neuron usage is monitored against budget (free tier or paid).

## Related

- `documentation/docs/policies/cloudflare/workers-development-patterns.md`
- `documentation/docs/policies/cloudflare/vectorize-embeddings.md`
- `documentation/docs/policies/ai-ml/rag-retrieval-augmented-generation.md`

## Source URLs (verified 2026-08-16)

- Workers AI documentation — https://developers.cloudflare.com/workers-ai/
- Workers AI edge inference guide — https://mecanik.dev/en/posts/cloudflare-workers-ai-run-ai-models-at-the-edge-in-2026/
- Workers AI models catalog — https://developers.cloudflare.com/workers-ai/models/
- Architecting on Cloudflare — Workers AI — https://architectingoncloudflare.com/chapter-16/
