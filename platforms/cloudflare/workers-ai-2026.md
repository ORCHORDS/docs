# workers-ai-2026

**Issue:** Cloudflare Workers AI model catalog — current 2026 state
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://developers.cloudflare.com/workers-ai/models/)

## What

Workers AI is Cloudflare's serverless GPU inference
platform. As of August 2026 it hosts a curated catalog of
open-source + partner models across text generation,
embeddings, image generation, audio, and code, all run
on Cloudflare's network. Models are invoked via the
`@cf/<vendor>/<model>` naming convention.

**Source:** https://developers.cloudflare.com/workers-ai/models/

## Current 2026 model families

**Text generation (newest):**
- `@cf/zai-org/glm-5.2` — 262,144 token context, function calling, reasoning. Z.ai flagship agentic coding model.
- `@cf/moonshotai/kimi-k2.7-code` — 1T parameter MoE, 262.1K context, vision, multi-turn tool calling. Frontier coding.
- `@cf/moonshotai/kimi-k2.6` — predecessor
- `@cf/zai-org/glm-4.7-flash` — 131,072 context, lightweight
- `@cf/qwen/qwen3-30b-a3b-fp8` — 32K context, MoE (3B active)

**Embeddings (text → vector):**
- `@cf/qwen/qwen3-embedding-0.6b` — 1024 dims, 4096 input tokens, cosine
- `@cf/google/embeddinggemma-300m` — 768 dims, 512 input tokens, cosine, 100+ languages
- `@cf/baai/bge-m3` — multi-functionality, multi-linguality, multi-granularity
- `@cf/baai/bge-base-en-v1.5` — 768 dims
- `@cf/plamo-embedding-1b` — Japanese

**Image generation:**
- `@cf/black-forest-labs/flux-2-klein-4b` — ultra-fast distilled, real-time
- `@cf/black-forest-labs/flux-2-dev` — multi-reference support
- `@cf/black-forest-labs/flux-1-schnell` — 12B params, rectified flow transformer
- `@cf/runwayml/stable-diffusion-v1-5-img2img` — 1500 req/min
- `@cf/leonardo/phoenix-1.0` — text rendering, prompt coherence
- `@cf/leonardo/lucid-origin` — photorealism

**Audio:**
- `@cf/deepgram/nova-3` — speech-to-text
- `@cf/deepgram/aura-1` — text-to-speech, context-aware pacing

**Vision / multimodal:**
- `@cf/openai/gpt-4o` — text + image input
- GPT-4o, GPT-image-1, GPT-image-1.5 — OpenAI's multimodal

**Code / agentic:**
- GLM-5.2 + Kimi K2.7-Code are the flagship 2026 coding models on Workers AI

## OpenAI-compatible endpoints

Workers AI supports OpenAI-compatible endpoints:
- Text: `POST /v1/chat/completions` (works with `@cf/...` text models)
- Embeddings: `POST /v1/embeddings`

This means you can swap OpenAI calls for Workers AI by
changing the base URL and key — no code rewrite.

```ts
const r = await fetch("https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/v1/chat/completions", {
  method: "POST",
  headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
  body: JSON.stringify({ model: "@cf/moonshotai/kimi-k2.7-code", messages: [...] })
});
```

## Free tier + rate limits

- Free tier: includes Workers AI inference (limited neurons/month)
- Paid tier: pay-per-use, scales with model
- Some models (e.g. SDXL-Lightning) have per-minute rate limits
- Cloudflare-hosted models don't need partner API keys (Leonardo/Deepgram need their own)

## When to use Workers AI vs your own backends

- **Use Workers AI** when: you want zero-config open-source models, GPU inference at the edge, OpenAI-compatible API, no separate GPU ops
- **Use Anthropic / OpenAI / your own model** when: you need specific proprietary models (Claude, GPT-5.x), reasoning quality matters more than cost
- **Use the user's minimax backend (this repo's router)** when: you want a tiered fallback chain (minimax → claude-sdk → claude → deferred)

## Related
- `cloudflare/ai-gateway-best-practices.md` — AI Gateway sits in front of Workers AI
- `cloudflare/vectorize-best-practices.md` — vector store for Workers AI embeddings
- `packages/router/src/backends/ollama.js` — the local-model sibling (also runs in a Worker)
- `patterns/mcp-server-patterns.md` — Workers AI is a tool provider, MCP is the consumer surface
- `patterns/agent-cost-optimization.md` — Workers AI free tier as the "easy" tier in the routing chain
- `cloudflare/ai-search-2026.md` — the AI Search product built on Workers AI
