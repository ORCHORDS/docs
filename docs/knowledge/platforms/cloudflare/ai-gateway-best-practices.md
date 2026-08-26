# ai-gateway-best-practices

**Issue:** AI Gateway — observability, caching, routing
**Date:** 2026-08-09
**Status:** documented

## Symptom
You use multiple AI providers (OpenAI, Workers AI,
Anthropic). You don't know which is faster. You don't
know which is cheaper. You don't know which is more
reliable. You wish you had a single layer.

## Root cause
**Multiple providers need a gateway.** Use AI
Gateway.

**Source:** CF AI Gateway:
https://developers.cloudflare.com/ai-gateway/

## The "AI Gateway" concept

AI Gateway is a unified AI control plane:
- **Unified billing:** One credit balance
- **Caching:** Repeat queries are free
- **Rate limiting:** Per key
- **Request retries:** Automatic
- **Observability:** Per-provider metrics
- **User Insights:** Spend + anomaly detection
- **Cloudflare Access:** Identity-aware controls

The gateway is the control plane.

## The "binding" pattern

For the binding:
```toml
[ai]
binding = "AI"
```

The binding is in `wrangler.toml`.

## The "Workers AI via gateway" pattern

For Workers AI:
```ts
const response = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  prompt: 'Hello',
  gateway: { id: 'my-gateway' },
});
```

The gateway is specified.

## The "OpenAI via gateway" pattern

For OpenAI:
```ts
const response = await fetch('https://gateway.ai.cloudflare.com/v1/openai/chat/completions', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${env.OPENAI_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'gpt-4o',
    messages: [{ role: 'user', content: 'Hello' }],
  }),
});
```

The OpenAI request goes through the gateway.

## The "caching" pattern

For caching:
```ts
const response = await env.AI.run(
  '@cf/meta/llama-2-7b-chat-int8',
  { prompt: 'Hello' },
  {
    gateway: {
      id: 'my-gateway',
      cache: { enabled: true, ttl: 3600 },  // 1 hour
    },
  },
);
```

Identical requests return the cached response.

## The "rate limit" pattern

For rate limiting:
```ts
const response = await env.AI.run(
  '@cf/meta/llama-2-7b-chat-int8',
  { prompt: 'Hello' },
  {
    gateway: {
      id: 'my-gateway',
      rateLimit: { requests: 100, period: '1m' },
    },
  },
);
```

The rate limit is enforced.

## The "retry" pattern

For retry:
```ts
const response = await env.AI.run(
  '@cf/meta/llama-2-7b-chat-int8',
  { prompt: 'Hello' },
  {
    gateway: {
      id: 'my-gateway',
      retries: { maxAttempts: 3, backoff: 'exponential' },
    },
  },
);
```

The request is retried.

## The "User Insights" pattern

For spend + anomaly detection:
- **Spend by user:** Per-user cost
- **Anomaly detection:** Unusual usage
- **Available at no extra cost**

The insights are in the AI Gateway dashboard.

## The "Cloudflare Access" pattern

For identity-aware controls:
- **Protect gateway:** Put behind Access
- **Identity in logs:** Per-user attribution
- **Spend controls:** Per user

The gateway is secured.

## The "unified billing" pattern

For unified billing:
- **Workers AI + 3rd party:** One balance
- **Prepaid credits:** Set budget
- **Frontier model access:** Without Paid plan
- **50 req/min/model:** Per model rate limit

The billing is unified.

**Source:** Unified billing:
https://developers.cloudflare.com/changelog/product-group/ai/

## The "AI Gateway observability" pattern

For observability:
- **Request volume:** Per provider
- **Error rate:** Per provider
- **Latency:** Per provider
- **Token usage:** Per model
- **Cost:** Per provider
- **Cache hit rate:** Per gateway

The metrics are in the dashboard.

## The "AI Gateway cost" pattern

For cost:
- **Gateway itself:** Free
- **AI inference:** Provider rates
- **Cache hit:** Free
- **Cache miss:** Provider rates

The gateway is free; you pay for the AI.

## The "AI Gateway vs direct" choice

| Use case | Use |
|---|---|
| **Multiple providers** | Gateway |
| **Single provider** | Direct or Gateway |
| **Need observability** | Gateway |
| **Need caching** | Gateway |
| **Need rate limit** | Gateway |
| **Simple use** | Direct |

For most apps, **Gateway** is the right answer.

## The "AI Gateway anti-pattern" anti-patterns

### 1. No observability
- **Issue:** Don't know cost
- **Fix:** AI Gateway

### 2. No caching
- **Issue:** Repeat work
- **Fix:** Gateway cache

### 3. No retry
- **Issue:** Transient failure
- **Fix:** Gateway retry

### 4. No rate limit
- **Issue:** Cost blowout
- **Fix:** Gateway rate limit

### 5. No anomaly detection
- **Issue:** Compromised key
- **Fix:** User Insights

## Verification
- **Test:** Caching works
- **Test:** Rate limit works
- **Test:** Retry works
- **Live:** Cost is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no observability" anti-pattern.** Use
  Gateway.
- **The "no caching" anti-pattern.** Enable cache.
- **The "no rate limit" anti-pattern.** Set limit.

## Related
- `cloudflare/workers-best-practices.md`
- `cloudflare/vectorize-best-practices.md`
- `feature-cookbook-ai-ml-detail.md`
- `feature-cookbook-cost-optimization.md`
- AI Gateway: https://developers.cloudflare.com/ai-gateway/
- AI changelog: https://developers.cloudflare.com/changelog/product-group/ai/
