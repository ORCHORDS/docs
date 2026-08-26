# ai-gateway-dynamic-routing-evaluations

Using Cloudflare AI Gateway's unified control plane for dynamic model routing,
Evaluations (A/B testing model quality), and multi-provider failover. After the
AI Week 2025 unification, AI Gateway is the single entry point for all LLM
traffic — Workers AI, OpenAI, Anthropic, and 14+ providers — through one
OpenAI-compatible endpoint with caching, rate limiting, and observability.

## Symptom

You have a multi-model AI app that calls OpenAI for some requests and Anthropic
for others. Your code is littered with provider-specific SDKs, retry logic, and
fallback chains. When a provider has an outage, your app breaks for 10 minutes
before you notice and manually switch. You have no way to compare whether GPT-4
or Claude gives better results for your specific prompts — you just guess.

```typescript
// The mess before AI Gateway
if (provider === 'openai') {
  const client = new OpenAI({ apiKey: env.OPENAI_KEY });
  // ... OpenAI-specific call shape
} else if (provider === 'anthropic') {
  const client = new Anthropic({ apiKey: env.ANTHROPIC_KEY });
  // ... completely different call shape
}
// No caching. No rate limiting. No fallback. No metrics. No A/B testing.
```

## Background: AI Gateway unification (2025)

After AI Week 2025 (Aug 25-29, 2025), AI Gateway and Workers AI merged into a
single control plane. The gateway exposes an **OpenAI-compatible endpoint** that
routes to any provider, with unified billing, observability, and policy.

```text
┌──────────────┐
│ Your Worker   │  →  POST /openai/chat/completions (OpenAI shape, always)
│ (one client)  │      Authorization: Bearer $CF_API_TOKEN
└──────┬───────┘
        │
        ↓
┌────────────────────────────────────────────────┐
│              AI Gateway                        │
│  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ Caching   │  │ Rate     │  │ Dynamic     │  │
│  │ (dedup)   │  │ Limiting │  │ Routing     │  │
│  └──────────┘  └──────────┘  └──────┬──────┘  │
│                                     │          │
│  ┌──────────────────────────────────┐          │
│  │          Evaluations              │          │
│  │  (A/B test model quality)         │          │
│  └──────────────────────────────────┘          │
└─────────────────────────────────────────────────┘
        │                    │                │
        ↓                    ↓                ↓
  ┌──────────┐      ┌──────────────┐  ┌───────────┐
  │ Workers  │      │   OpenAI      │  │ Anthropic │
  │   AI     │      │  (external)   │  │ (external)│
  └──────────┘      └──────────────┘  └───────────┘
```

## Solution: Route all AI traffic through the gateway

### Step 1: Universal OpenAI-compatible call

No matter which backend model you want, the request shape is always OpenAI's.
The gateway routes based on the model name.

```typescript
interface Env {
  CF_API_TOKEN: string;  // Cloudflare API token with AI Gateway access
  ACCOUNT_ID: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { messages, model } = await req.json();

    // Single endpoint, OpenAI shape — gateway routes to the right provider
    const response = await fetch(
      `https://gateway.ai.cloudflare.com/v1/${env.ACCOUNT_ID}/my-gateway/openai/chat/completions`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: model || "gpt-4o",  // or "claude-3-5-sonnet", "@cf/llama-3.1-8b"
          messages,
        }),
      }
    );

    const result = await response.json();
    return Response.json(result);
  },
};
```

### Step 2: Dynamic routing with fallback chains

Configure the gateway to try Workers AI first (free, fast) and fall back to
OpenAI if Workers AI is unavailable or rate-limited.

```typescript
async function callWithFallback(prompt: string, env: Env): Promise<string> {
  const models = [
    "@cf/meta/llama-3.1-8b-instruct",  // Workers AI (free, fast)
    "gpt-4o-mini",                      // OpenAI (cheap fallback)
    "gpt-4o",                           // OpenAI (quality fallback)
  ];

  for (const model of models) {
    try {
      const res = await callGateway(model, prompt, env);
      if (res.ok) return await res.text();
    } catch (e) {
      console.log(`Model ${model} failed, trying next...`);
    }
  }
  throw new Error("All models failed");
}
```

### Step 3: Evaluations — A/B test model quality (beta)

Send the same prompt to two models and compare outputs to decide which is
better for your use case.

```typescript
async function evaluateModels(prompt: string, env: Env): Promise<void> {
  const candidates = ["gpt-4o", "claude-3-5-sonnet"];

  const results = await Promise.all(
    candidates.map(async (model) => {
      const res = await callGateway(model, prompt, env);
      return { model, output: await res.text() };
    })
  );

  // Send to Evaluations dashboard for human or automated scoring
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/ai-gateway/evaluations`,
    {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.CF_API_TOKEN}` },
      body: JSON.stringify({
        prompt,
        candidates: results,
        // scoring_criteria can be defined in the dashboard
      }),
    }
  );
}
```

### Step 4: Enable caching and rate limiting

```bash
# Caching: identical prompts return cached results (huge cost savings)
npx wrangler ai-gateway update my-gateway \
  --cache-ttl 3600  # cache identical requests for 1 hour

# Rate limiting: protect against runaway costs
npx wrangler ai-gateway update my-gateway \
  --rate-limit 100 \  # 100 requests per minute
  --rate-limit-interval 60
```

## Gotchas

- **Caching is exact-match only (prompt string hash).** Slightly different
  prompts (extra space, reordered words) bypass the cache. Normalize prompts
  before sending if you want cache hits — trim whitespace, sort JSON keys.
- **Cached responses don't reflect model updates.** If OpenAI updates GPT-4o
  mid-cache-window, you still get the old answer. Set cache TTL short enough
  to matter for your latency-sensitivity trade-off.
- **The gateway endpoint URL must include your account ID and gateway name.**
  A typo in either gives a 404 that looks like an auth error. Triple-check:
  `/v1/{account_id}/{gateway_name}/openai/chat/completions`.
- **Streaming responses need `stream: true` in the body.** The gateway
  supports SSE streaming, but you must set it in the request body (not just
  `Accept: text/event-stream`). Without it, the full response buffers.
- **Evaluations is beta — API surface may change.** Don't build critical
  infrastructure on the Evaluations endpoint without pinning the API version.
  The scoring model (human vs automated) is still evolving.
- **Rate limits are per-gateway, not per-model.** If your limit is 100/min and
  you split across 3 models, they share the 100 budget. Scale the limit to
  total expected traffic, not per-provider needs.
- **External provider API keys must be configured in the gateway dashboard.**
  The gateway needs your OpenAI/Anthropic keys to forward requests. Store them
  in the gateway config (or Cloudflare Secrets Store), not in Worker env vars
  — the gateway injects them, your Worker never sees the provider key.
- **Workers AI routing uses `@cf/` model prefixes.** Other providers use their
  native model names (`gpt-4o`, `claude-3-5-sonnet`). The prefix tells the
  gateway which backend to use. Get the prefix wrong and you get a model-not-
  found error from the wrong provider.
- **Failover is not automatic by default.** The gateway routes to the model
  you specify. If you want automatic fallback, you must either configure a
  fallback policy in the gateway dashboard or implement it in your Worker
  code (as shown in Step 2).
- **Billing is unified but costs differ by provider.** Workers AI billing goes
  through Cloudflare; OpenAI/Anthropic costs still hit their respective
  accounts. The gateway gives you unified observability, not unified billing
  for external providers.

## When to use the gateway vs. direct calls

### Use the gateway when:
- Multiple providers, unified logging/observability needed
- Caching identical prompts saves significant cost
- Rate limiting protects against budget overruns
- You want to A/B test models on real traffic

### Call providers directly when:
- Single provider, low volume, simplest possible code
- You need provider-specific features the gateway doesn't expose (e.g.,
  OpenAI's structured outputs with specific schema enforcement)
- Latency is critical and the gateway adds measurable overhead

## Sources

- [AI Gateway Unification — Blog](https://blog.cloudflare.com/workers-ai-gateway-unification/)
- [AI Week 2025 Recap — Blog](https://blog.cloudflare.com/ai-week-2025-wrapup/)
- [AI Gateway — Product Page](https://www.cloudflare.com/products/ai-gateway/)
- [AI Gateway — Docs](https://developers.cloudflare.com/ai-gateway/)
