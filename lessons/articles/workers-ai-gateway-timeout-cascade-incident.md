# Workers AI Gateway Timeout Cascade Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

AI-powered features (chat completions, summarisation, embedding generation) began returning
`504 Gateway Timeout` across every endpoint simultaneously. P99 latency climbed from ~1 s to
30 s before requests started failing. Downstream Workers that consumed the AI Gateway URL started
retrying, which multiplied in-flight requests until the entire AI surface was saturated.
The incident lasted 47 minutes; revenue-impacting features were dark for 31 of those minutes.

## Context

The team routed all third-party LLM calls through a single **Cloudflare AI Gateway** endpoint
(`https://gateway.ai.cloudflare.com/v1/<account>/<gateway-name>/…`). This gave unified caching,
rate-limit telemetry, and cost attribution. However every model provider—OpenAI, Anthropic, and
the in-Worker `Workers AI` binding—shared the same gateway slug. When the upstream provider hit
a brief degradation (~8 s elevated latency), the gateway queued requests. Workers have a 30 s
CPU/wall-clock budget; requests that queued past 25 s threw, and the retry logic re-entered the
queue, causing a fan-out cascade.

---

## AI Gateway URL Construction

```typescript
// src/lib/ai-gateway.ts
const GATEWAY_BASE =
  `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.AI_GATEWAY_SLUG}`;

export function openaiUrl(path: string): string {
  // Route OpenAI calls through the gateway
  return `${GATEWAY_BASE}/openai${path}`;
}

export function anthropicUrl(path: string): string {
  return `${GATEWAY_BASE}/anthropic${path}`;
}

// FIX: separate gateways per provider so one provider's slowness
// does not saturate the shared queue of another.
export function openaiUrlV2(path: string): string {
  return `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/openai-prod${path}`;
}
```

## Aggressive Retry Was the Multiplier

```typescript
// BEFORE — no timeout, exponential retry with no circuit breaker
async function callLLM(prompt: string): Promise<string> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await fetch(openaiUrl('/chat/completions'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.OPENAI_KEY}` },
      body: JSON.stringify({ model: 'gpt-4o', messages: [{ role: 'user', content: prompt }] }),
    });
    if (res.ok) return (await res.json()).choices[0].message.content;
    await new Promise(r => setTimeout(r, 2 ** attempt * 200));
  }
  throw new Error('LLM call failed');
}

// AFTER — AbortSignal timeout, jitter, max 2 attempts
async function callLLMSafe(
  prompt: string,
  ctx: ExecutionContext,
): Promise<string> {
  const MAX_ATTEMPTS = 2;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const signal = AbortSignal.timeout(8_000); // 8 s hard cap per attempt
    try {
      const res = await fetch(openaiUrl('/chat/completions'), {
        method: 'POST',
        signal,
        headers: { Authorization: `Bearer ${env.OPENAI_KEY}` },
        body: JSON.stringify({ model: 'gpt-4o', messages: [{ role: 'user', content: prompt }] }),
      });
      if (res.ok) return (await res.json()).choices[0].message.content;
      if (res.status < 500) throw new Error(`Non-retryable ${res.status}`);
    } catch (err) {
      if (attempt === MAX_ATTEMPTS - 1) throw err;
      // Jitter: base 1 s + up to 1 s random so retries don't align
      await new Promise(r => setTimeout(r, 1_000 + Math.random() * 1_000));
    }
  }
  throw new Error('unreachable');
}
```

## Circuit Breaker via Durable Object

```typescript
// src/do/circuit-breaker.ts
export class AICircuitBreaker extends DurableObject {
  private failures = 0;
  private openUntil = 0;

  async fetch(req: Request): Promise<Response> {
    const { pathname } = new URL(req.url);

    if (pathname === '/check') {
      if (Date.now() < this.openUntil) {
        return new Response('open', { status: 503 });
      }
      return new Response('closed');
    }

    if (pathname === '/record-failure') {
      this.failures++;
      if (this.failures >= 5) {
        this.openUntil = Date.now() + 30_000; // 30 s open window
        this.failures = 0;
      }
      return new Response('ok');
    }

    if (pathname === '/record-success') {
      this.failures = Math.max(0, this.failures - 1);
      return new Response('ok');
    }

    return new Response('not found', { status: 404 });
  }
}

// Usage in a Worker
async function guardedLLMCall(env: Env, prompt: string): Promise<string> {
  const cb = env.AI_CIRCUIT_BREAKER.get(env.AI_CIRCUIT_BREAKER.idFromName('openai'));
  const check = await cb.fetch(new Request('http://do/check'));
  if (check.status === 503) throw new Error('AI circuit open — fast fail');

  try {
    const result = await callLLMSafe(prompt, /* ctx */ {} as ExecutionContext);
    ctx.waitUntil(cb.fetch(new Request('http://do/record-success')));
    return result;
  } catch (err) {
    ctx.waitUntil(cb.fetch(new Request('http://do/record-failure')));
    throw err;
  }
}
```

## AI Gateway Cache-First for Identical Prompts

```typescript
// Gateway-level caching is configured in the dashboard, but you must
// set Cache-Control on the request to opt in per-call.
const res = await fetch(openaiUrl('/chat/completions'), {
  method: 'POST',
  headers: {
    'cf-aig-cache-ttl': '3600',       // cache identical requests for 1 h
    'cf-aig-skip-cache': 'false',
    Authorization: `Bearer ${env.OPENAI_KEY}`,
  },
  body: JSON.stringify({ model: 'gpt-4o', messages: [{ role: 'user', content: prompt }] }),
});
// Cached hits do not count against provider rate limits and
// return in ~10 ms instead of 1–3 s, which also insulates the
// Worker from upstream degradation.
```

## Fallback to Cheaper Model on Degradation

```typescript
async function callWithFallback(prompt: string): Promise<string> {
  try {
    return await callLLMSafe(prompt, ctx);
  } catch {
    // Degrade to a faster, cheaper model rather than returning an error
    const res = await fetch(openaiUrl('/chat/completions'), {
      method: 'POST',
      signal: AbortSignal.timeout(5_000),
      headers: { Authorization: `Bearer ${env.OPENAI_KEY}` },
      body: JSON.stringify({
        model: 'gpt-4o-mini',  // lower latency, lower cost
        messages: [{ role: 'user', content: prompt }],
      }),
    });
    if (!res.ok) throw new Error('fallback also failed');
    return (await res.json()).choices[0].message.content;
  }
}
```

---

## Anti-Patterns

- **Shared gateway slug for all providers.** One provider's latency spike saturates the shared
  queue and degrades unrelated models. Use one slug per upstream provider.
- **Unlimited retries without timeouts.** Each retry without an `AbortSignal` holds a Worker
  subrequest slot for the full 30 s budget, exhausting the 50-subrequest limit fast.
- **No circuit breaker.** Without a fast-fail mechanism, every incoming request tries the
  degraded path, amplifying load on the already-struggling gateway.
- **Treating AI Gateway as a transparent pass-through.** The gateway adds ~5–20 ms overhead;
  your per-request timeout budget must account for this.

## Gotchas

- `AbortSignal.timeout()` does not work inside `waitUntil` tasks — the signal fires when the
  Worker's isolate is suspended. Use `Promise.race` with a manual timeout instead.
- AI Gateway `cf-aig-cache-ttl` only caches identical request bodies. Any prompt variation
  (even whitespace) produces a cache miss.
- The AI Gateway logs show `provider_latency_ms` separately from `total_latency_ms`. Monitor
  both; a gap indicates gateway queueing.
- Circuit breaker state in a Durable Object is per-shard; an `idFromName` key must be stable
  and specific to one upstream (e.g. `'cb:openai'` not `'cb:ai'`).

## Verification

```bash
# Check AI Gateway analytics for error rate and latency percentiles
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/ai-gateway/gateways/$GW_ID/logs?limit=100" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '[.result[] | select(.response_status >= 500)]'

# Confirm per-provider gateway slugs exist
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/ai-gateway/gateways" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '[.result[].slug]'

# Smoke-test circuit breaker DO
wrangler dev --test-scheduled
# then curl http://localhost:8787/__test/circuit to assert state transitions
```

## Related

- `workers-ai-concurrent-model-call-cascade-timeout-incident.md`
- `workers-ai-rate-limit-exceeded-production-incident.md`
- `workers-subrequest-limit-fan-out-exceeded-incident.md`
- `circuit-breaker-prevents-cascade-failure.md`
- `timeouts-everywhere-no-exceptions.md`

## Sources

- Cloudflare AI Gateway docs: https://developers.cloudflare.com/ai-gateway/
- AI Gateway caching: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- Workers `AbortSignal.timeout`: https://developers.cloudflare.com/workers/runtime-apis/fetch/#abortsignal
- Circuit breaker pattern: https://martinfowler.com/bliki/CircuitBreaker.html
