# ai-gateway-fallback-caching-streaming

Configuring Cloudflare AI Gateway for production resilience: provider
fallback (when OpenAI/Anthropic goes down), response caching (to cut costs
and latency), and streaming passthrough. This is the article for teams whose
AI features break when a single provider has an outage.

## Symptom

Your app calls an LLM API directly. One of these happens regularly:

```text
Error: 429 Too Many Requests (OpenAI rate limited)
Error: 500 Internal Server Error (Anthropic capacity issue)
Error: ETIMEDOUT (provider is down)
Error: Your bill has exceeded $X (surprise cost spike from repeated identical queries)
```

Users see error messages, your on-call engineer gets paged, and you have no
visibility into which provider is failing or how often.

## Solution: Route through AI Gateway

AI Gateway sits between your Worker and the LLM provider. It adds caching,
fallback, rate limiting, and observability — without changing your model
calling code significantly.

### Step 1: Create a gateway

```bash
npx wrangler ai-gateway create my-prod-gateway \
  --account-id $CLOUDFLARE_ACCOUNT_ID
```

Or via dashboard: **AI → AI Gateway → Create**.

### Step 2: Configure wrangler.toml

```toml
# wrangler.toml
name = "ai-app"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[ai_gates]]
binding = "AI_GATEWAY"
gateway = "my-prod-gateway"
```

### Step 3: Call models through the gateway

```typescript
interface Env {
  AI_GATEWAY: AiGateway;
  OPENAI_KEY: string;  // stored as secret
  ANTHROPIC_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json();

    // Call OpenAI THROUGH the gateway
    const response = await fetch("https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/openai/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.OPENAI_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "gpt-4o",
        messages: [{ role: "user", content: prompt }],
      }),
    });

    const result = await response.json();
    return Response.json(result);
  },
};
```

## Pattern 1: Multi-provider fallback

When the primary provider fails, automatically try the next one.

```typescript
async function callLLM(prompt: string, env: Env): Promise<string> {
  const providers = [
    {
      name: "openai",
      url: `https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/openai/chat/completions`,
      headers: { Authorization: `Bearer ${env.OPENAI_KEY}` },
      body: { model: "gpt-4o", messages: [{ role: "user", content: prompt }] },
      extract: (r: any) => r.choices[0].message.content,
    },
    {
      name: "anthropic",
      url: `https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/anthropic/v1/messages`,
      headers: {
        "x-api-key": env.ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: { model: "claude-3-5-sonnet-20241022", max_tokens: 1024, messages: [{ role: "user", content: prompt }] },
      extract: (r: any) => r.content[0].text,
    },
    {
      name: "workers-ai",
      // Workers AI doesn't need a key — call directly via binding
      url: null,  // handled separately below
      body: null,
      extract: null,
    },
  ];

  for (const provider of providers) {
    try {
      if (provider.name === "workers-ai") {
        // Fallback to Workers AI binding (no external dependency)
        const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", { prompt });
        return result.response ?? "";
      }

      const response = await fetch(provider.url!, {
        method: "POST",
        headers: { ...provider.headers, "Content-Type": "application/json" },
        body: JSON.stringify(provider.body),
        signal: AbortSignal.timeout(10000),  // 10s timeout per provider
      });

      if (!response.ok) {
        console.error(`Provider ${provider.name} returned ${response.status}`);
        continue;  // try next provider
      }

      const data = await response.json();
      return provider.extract!(data);
    } catch (error) {
      console.error(`Provider ${provider.name} failed:`, error);
      continue;
    }
  }

  throw new Error("All LLM providers failed");
}
```

## Pattern 2: Response caching (save money + reduce latency)

Identical prompts get cached responses. Huge cost savings for common queries.

```typescript
async function callWithCache(prompt: string, env: Env): Promise<string> {
  // The gateway URL with cache hints
  const response = await fetch(
    `https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/openai/chat/completions`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.OPENAI_KEY}`,
        "Content-Type": "application/json",
        // Enable caching for this request
        "cf-cache-age": "3600",  // cache for 1 hour
      },
      body: JSON.stringify({
        model: "gpt-4o",
        messages: [{ role: "user", content: prompt }],
      }),
    }
  );

  const cfCacheStatus = response.headers.get("cf-cache-status");
  console.log(`Cache status: ${cfCacheStatus}`);  // HIT, MISS, or BYPASS

  const data = await response.json();
  return data.choices[0].message.content;
}
```

**When to cache:**
- FAQ / help bot queries (users ask the same questions)
- Classification / moderation (same content classified repeatedly)
- Embeddings generation (same text → same vector)
- Translation of static content

**When NOT to cache:**
- Personalized responses (user-specific context)
- Time-sensitive queries ("what's the weather now")
- Creative generation (you want variety)

## Pattern 3: Streaming responses

Streaming is essential for UX — users see tokens as they're generated instead
of waiting 5-10s for a full response.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json();

    // Stream from provider through the gateway
    const response = await fetch(
      `https://gateway.ai.cloudflare.com/v1/<account>/<gateway>/openai/chat/completions`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.OPENAI_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "gpt-4o",
          messages: [{ role: "user", content: prompt }],
          stream: true,  // enable streaming
        }),
      }
    );

    // Pass the stream through to the client directly
    return new Response(response.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      },
    });
  },
};
```

## Gotchas

- **Gateway URLs are account-specific.** The `<account>` and `<gateway>` in
  the URL are YOUR account ID and gateway name. Copy-pasting from docs without
  replacing these gives 404s. Use the dashboard's "Copy URL" button.
- **Caching keys on the FULL request body.** If your prompt includes a
  timestamp or random ID, you'll never get cache hits. Strip variable
  components before sending if you want caching.
- **Streaming + caching are incompatible.** You can't cache a streaming
  response (it's an open connection, not a single response). Choose one.
- **Fallback adds latency.** If OpenAI times out at 10s, then Anthropic
  takes another 5s, your user waited 15s. Set aggressive timeouts per
  provider and parallelize if latency is critical (see below).
- **Workers AI as fallback is free but lower quality.** Llama 8B is fine for
  simple tasks but noticeably worse than GPT-4o for complex reasoning. Don't
  use it as your primary — use it as the last-resort fallback.
- **Rate limiting at the gateway level is separate from provider rate
  limits.** Set gateway-level limits to protect yourself from a single user
  or client exhausting your provider quota. Configure in dashboard.
- **Gateway logs are in a different place than Worker logs.** Gateway
  analytics (requests, cache hit rate, cost, latency by provider) are in
  **AI → AI Gateway → Analytics**, NOT in Workers Logs. Check both.
- **Parallel racing for lowest latency:**

```typescript
// Race providers in parallel, use whichever responds first
async function raceProviders(prompt: string, env: Env): Promise<string> {
  const promises = [
    callOpenAI(prompt, env),
    callAnthropic(prompt, env),
  ];

  // First successful response wins; cancel the rest
  for (const promise of promises) {
    try {
      const result = await promise;
      return result;
    } catch {
      continue;  // this provider failed, try the next
    }
  }
  throw new Error("All providers failed");
}
```

Warning: racing means you pay for all providers' compute, even though you
only use one result. Use only for latency-critical paths where cost is
secondary.

- **Don't put API keys in the gateway URL.** Keys go in the `Authorization`
  header, not the URL path. URLs appear in logs and analytics dashboards.
- **The gateway itself can be a single point of failure.** If Cloudflare's
  AI Gateway has an outage, all your AI calls fail even if providers are up.
  For maximum resilience, keep a code path that calls providers directly
  (bypassing the gateway) as an emergency fallback.
