# Cloudflare Workers AI — Edge Inference and AI Gateway

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You are running AI inference through a centralized cloud provider
(OpenAI, Anthropic, AWS Bedrock) and every request incurs 100-300ms of
network latency before the model even starts processing. You have no
visibility into AI costs, no caching of repeated prompts, no fallback
when your primary provider has an outage, and no rate limiting to
prevent runaway costs. You want to run inference closer to users and
add an operational control plane around your AI API calls.

## Context

Cloudflare Workers AI provides serverless inference at the edge,
running 50+ open-source models (LLMs, image generation, embeddings,
speech-to-text, translation) on Cloudflare's global GPU network with no
infrastructure management. AI Gateway is a separate product that sits
in front of any AI provider (OpenAI, Anthropic, Azure, Workers AI) to
add caching, rate limiting, cost tracking, fallback routing, and
logging without code changes — just change the base URL. In 2026, the
standard pattern combines both: Workers AI for open-model inference at
the edge, and AI Gateway as the control plane for all AI traffic
regardless of provider.

## Workers AI

### Basic inference

```javascript
export default {
  async fetch(request, env) {
    const { prompt } = await request.json();

    const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: prompt },
      ],
      max_tokens: 512,
      temperature: 0.7,
    });

    return Response.json(response);
  },
};
```

### Streaming inference

```javascript
export default {
  async fetch(request, env) {
    const { prompt } = await request.json();

    const stream = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [{ role: 'user', content: prompt }],
      stream: true,
    });

    return new Response(stream, {
      headers: { 'Content-Type': 'text/event-stream' },
    });
  },
};
```

### Embeddings

```javascript
const embeddings = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
  text: ['What is machine learning?', 'How does AI work?'],
});

// Store in Vectorize for similarity search
await env.VECTORIZE_INDEX.upsert(
  embeddings.data.map((emb, i) => ({
    id: `doc-${i}`,
    values: emb,
    metadata: { source: 'knowledge-base' },
  }))
);
```

### Image generation

```javascript
const image = await env.AI.run('@cf/stabilityai/stable-diffusion-xl-base-1.0', {
  prompt: 'A serene mountain landscape at sunset',
  num_steps: 20,
});

return new Response(image, {
  headers: { 'Content-Type': 'image/png' },
});
```

## Available model categories

| Category | Example models | Use case |
|---|---|---|
| Text generation | Llama 3.1 8B, Mistral 7B, Gemma 2 | Chat, summarization, code gen |
| Text embeddings | BGE Base, GTE Base | Semantic search, RAG |
| Image generation | SDXL, Stable Diffusion | Content creation, thumbnails |
| Image classification | ResNet-50 | Content moderation, tagging |
| Speech-to-text | Whisper | Transcription, voice commands |
| Translation | M2M-100 | Multi-language content |
| Object detection | DETR | Image analysis, safety checks |

## AI Gateway

### Setup (zero code changes)

```javascript
// Before: direct OpenAI call
const response = await fetch('https://api.openai.com/v1/chat/completions', {
  headers: { Authorization: `Bearer ${OPENAI_KEY}` },
  body: JSON.stringify({ model: 'gpt-4o', messages }),
});

// After: route through AI Gateway (change base URL only)
const response = await fetch(
  'https://gateway.ai.cloudflare.com/v1/ACCOUNT_ID/my-gateway/openai/chat/completions',
  {
    headers: { Authorization: `Bearer ${OPENAI_KEY}` },
    body: JSON.stringify({ model: 'gpt-4o', messages }),
  }
);
```

### Features

```
Caching:
  → Cache identical prompt/model combinations
  → Configurable TTL (seconds to days)
  → Reduces cost and latency for repeated queries
  → Cache key includes: model, messages, temperature, max_tokens

Rate limiting:
  → Per-user or per-API-key limits
  → Sliding window or fixed window
  → Prevents runaway costs from loops or abuse

Cost tracking:
  → Real-time dashboard of token usage and cost
  → Per-model, per-gateway breakdown
  → Alerts on spending thresholds

Fallback routing:
  → Primary: OpenAI GPT-4o
  → Fallback 1: Anthropic Claude
  → Fallback 2: Workers AI Llama
  → Automatic failover on provider errors

Logging:
  → Full request/response logging
  → Prompt and completion storage
  → Searchable log explorer
  → Retention policies
```

### Fallback configuration

```javascript
const response = await fetch(
  `https://gateway.ai.cloudflare.com/v1/${ACCOUNT_ID}/my-gateway`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify([
      {
        provider: 'openai',
        endpoint: 'chat/completions',
        headers: { Authorization: `Bearer ${OPENAI_KEY}` },
        query: { model: 'gpt-4o', messages },
      },
      {
        provider: 'workers-ai',
        endpoint: '@cf/meta/llama-3.1-8b-instruct',
        query: { messages },
      },
    ]),
  }
);
```

## Pricing (2026)

```
Workers AI:
  → Free tier: 10,000 Neurons/day
  → Paid: per-Neuron pricing (varies by model)
  → Llama 3.1 8B: ~$0.011 per 1K input tokens
  → No GPU management, no cold starts on popular models

AI Gateway:
  → Free: 100,000 requests/day
  → Paid: included with Workers Paid plan
  → No per-token markup (pass-through to providers)
  → Caching saves on provider costs directly
```

## Anti-patterns

- **Using Workers AI for large-model tasks** — Workers AI runs
  smaller models (7B-70B parameters). Tasks requiring GPT-4-class
  reasoning should use AI Gateway with OpenAI/Anthropic as the
  provider, with Workers AI as a fallback for simpler tasks.
- **No caching for deterministic prompts** — repeated identical
  prompts (system instructions, classification tasks) should be
  cached. Without caching, you pay for the same inference repeatedly.
  Set temperature to 0 for cacheable responses.
- **Ignoring cost tracking** — AI costs can spike unexpectedly from
  loops, retries, or abuse. Use AI Gateway's cost tracking and
  alerts to monitor spending. Set rate limits to cap maximum spend.
- **Embedding without Vectorize** — generating embeddings with
  Workers AI but storing them in an external vector database. Use
  Cloudflare Vectorize for co-located embedding storage, eliminating
  the round trip to an external service.

## Gotchas

- **Model availability varies by PoP** — not all Workers AI models
  are available at every Cloudflare PoP. Less popular models may
  route to a regional GPU cluster, adding latency. Popular models
  (Llama 3.1 8B, Whisper) have the broadest availability.
- **Neuron pricing is model-dependent** — different models consume
  different numbers of Neurons per token. Compare per-token costs
  across models before committing to one.
- **AI Gateway caching is exact-match** — the cache key includes
  the full request body. A single character difference in the prompt
  is a cache miss. Normalize prompts before sending for better cache
  hit rates.
- **Streaming responses and caching** — streaming responses from AI
  Gateway are cached after the full response is received. The first
  request streams from the provider; subsequent cache hits return
  the full response at once (not streamed).

## Verification

- Workers AI runs open-model inference for latency-sensitive tasks.
- AI Gateway routes all AI provider traffic for visibility and control.
- Caching is enabled for deterministic prompts (temperature 0).
- Fallback routing is configured across multiple providers.
- Cost tracking alerts are set for spending thresholds.
- Rate limits prevent runaway AI costs from abuse or loops.

## Related

- `documentation/docs/policies/cloudflare/durable-objects-real-time-state.md`
- `documentation/docs/policies/ai-ml/llm-prompt-injection-defense.md`
- `documentation/docs/policies/performance/edge-computing-serverless-cdn-patterns.md`

## Source URLs (verified 2026-08-16)

- Cloudflare AI Capabilities Complete Guide 2026 — https://nomadx.ae/blog/cloudflare-ai-capabilities-complete-guide-2026/
- Workers AI: Inference at the Edge — https://architectingoncloudflare.com/chapter-16/
- Running AI Models on the Edge with Cloudflare Workers AI — https://www.davidmuraya.com/blog/cloudflare-workers-ai-guide/
- Cloudflare Workers AI Edge Inference Guide — https://zenvanriel.com/ai-engineer-blog/cloudflare-workers-ai/
