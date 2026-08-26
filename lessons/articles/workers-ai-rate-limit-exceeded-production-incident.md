# Workers AI Rate Limit Exceeded — Production Incident (Postmortem)

- Date: 2026-08-22
- Author: example.com
- Status: production

## Summary

During a traffic spike driven by a viral social-media mention, the Workers AI inference
endpoint began returning `429 Too Many Requests` for all requests within 4 minutes of the
spike onset. The absence of any rate-limit handling in the calling Worker caused those errors
to propagate directly to users as 500 responses, degrading AI-powered features for 23 minutes.
The fix combined exponential backoff with retry, AI Gateway for quota management and fallback
routing, and a circuit-breaker that downgrades gracefully rather than failing hard.

## Timeline / What Happened

- **14:02 UTC** — A high-profile creator shares a link to example.com on a platform with
  12 M followers. Traffic begins climbing steeply.
- **14:06 UTC** — Workers AI model `@cf/mistral/mistral-7b-instruct-v0.1` begins returning
  `429` responses. The on-call engineer's phone does not alert yet — the error rate threshold
  alarm requires a 5-minute sustained breach.
- **14:08 UTC** — AI-powered chord-suggestion feature shows "Something went wrong" to all
  users. Users start posting complaints. Error rate breaches the alarm threshold.
- **14:09 UTC** — PagerDuty fires. On-call acknowledges.
- **14:14 UTC** — On-call traces the 500s to the Workers AI call site; confirms 429 is the
  upstream cause.
- **14:19 UTC** — Temporary mitigation: feature flag `AI_SUGGESTIONS_ENABLED` toggled to
  `false`, hiding the feature entirely. User-visible errors stop.
- **14:25 UTC** — Fix deployed: AI Gateway with fallback model routing added; exponential
  backoff in the Worker. Feature flag re-enabled.
- **14:31 UTC** — Incident resolved. AI suggestions returning successfully under load.

## Root Cause

The Worker called Workers AI with no error handling beyond a generic `try/catch` that returned
a 500. No retry, no backoff, no awareness of the `429` status code specifically.

```typescript
// BEFORE — no rate-limit awareness
export async function getChordSuggestion(
  env: Env,
  prompt: string
): Promise<string> {
  // BUG: if AI returns 429 this throws and the caller gets a 500
  const result = await env.AI.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [{ role: "user", content: prompt }],
  });

  return (result as { response: string }).response;
}
```

Workers AI free-tier and standard-tier accounts share a global rate limit per model per
Cloudflare account. During the traffic spike, the account-level quota was exhausted in under
4 minutes. Because every Worker invocation hit the model directly — with no caching of
identical or similar prompts, no request coalescing, and no fallback path — the entire feature
failed immediately once the quota ran out.

Additionally, there was no capacity planning for AI inference: no estimate of requests/minute
at peak, no understanding of the account's Workers AI rate limits, and no alerts on the
`cf_workers_ai_requests_total` metric approaching the quota boundary.

## Fix Applied

**1. Exponential backoff with jitter on 429.**

```typescript
// AFTER — retries with backoff on rate-limit responses
async function runWithBackoff(
  ai: Ai,
  model: string,
  messages: { role: string; content: string }[],
  maxAttempts = 3
): Promise<string> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const result = await ai.run(model as Parameters<Ai["run"]>[0], { messages } as never) as { response: string };
      return result.response;
    } catch (err: unknown) {
      const isRateLimit =
        err instanceof Error && err.message.includes("429");
      if (!isRateLimit || attempt === maxAttempts - 1) throw err;

      // Exponential backoff: 200ms, 400ms, 800ms + up to 100ms jitter
      const delay = 200 * Math.pow(2, attempt) + Math.random() * 100;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  throw new Error("unreachable");
}
```

**2. AI Gateway with fallback model routing.** The AI Gateway binding in `wrangler.toml` now
sits in front of all model calls and routes `429` responses from the primary model to a
cheaper fallback model before the Worker sees the error.

```toml
# wrangler.toml
[[ai_gateway]]
id = "orchords-ai-gw"
```

```typescript
// AFTER — AI Gateway binding with fallback
export async function getChordSuggestion(
  env: Env,
  prompt: string
): Promise<string | null> {
  const messages = [{ role: "user" as const, content: prompt }];

  // Primary: best model via AI Gateway (Gateway handles fallback to secondary model)
  try {
    return await runWithBackoff(
      env.AI,
      "@cf/mistral/mistral-7b-instruct-v0.1",
      messages
    );
  } catch (primaryErr) {
    // Gateway fallback already tried; attempt smallest model as last resort
    try {
      const fallback = await env.AI.run(
        "@cf/tinyllama/tinyllama-1.1b-chat-v1.0",
        { messages } as never
      ) as { response: string };
      return fallback.response;
    } catch {
      // Circuit open: return null, caller shows degraded UI instead of error
      return null;
    }
  }
}
```

**3. Caller degrades gracefully when `null` is returned.**

```typescript
// In the request handler
const suggestion = await getChordSuggestion(env, prompt);
if (suggestion === null) {
  return Response.json(
    { suggestion: null, degraded: true, message: "AI suggestions temporarily unavailable" },
    { status: 200 } // 200 so the client shows UI, not an error state
  );
}
return Response.json({ suggestion, degraded: false });
```

**4. Prompt-level caching** with KV to reduce redundant AI calls for frequently repeated
prompts (identical chord progressions asked by multiple users).

```typescript
const cacheKey = `ai:chord:${hashPrompt(prompt)}`;
const cached = await env.KV.get(cacheKey);
if (cached) return cached;

const suggestion = await getChordSuggestion(env, prompt);
if (suggestion) {
  await env.KV.put(cacheKey, suggestion, { expirationTtl: 300 }); // 5 min
}
```

## Prevention Checklist

- [ ] Every Workers AI call site handles `429` explicitly — never let it bubble as a 500.
- [ ] AI Gateway binding is configured for every model used in production.
- [ ] A fallback model (smaller, lower-cost) is defined for every primary model.
- [ ] All AI-powered features implement graceful degradation (return `degraded: true`,
      not an error) when the AI layer is unavailable.
- [ ] KV or Cache API caches AI responses for identical inputs for at least 5 minutes.
- [ ] Alert on Workers AI 429 rate before the account quota is fully exhausted (set threshold
      at 70% of known quota).
- [ ] Capacity planning doc updated before each expected traffic event: estimate peak
      AI requests/min and compare to account quota.
- [ ] Load test AI path with 10x expected peak before launches or viral campaigns.

## Lesson Learned

Workers AI shares account-level quotas across all Workers — a traffic spike in one feature
can exhaust the quota for all AI features simultaneously. Treating AI inference as an
infallible dependency with unlimited capacity is a category error; it must be treated like any
other external API with a rate limit: with backoff, circuit-breaking, fallback paths, and
graceful degradation. Capacity planning for AI inference is different from capacity planning
for compute — the constraint is not CPU or memory but tokens-per-minute quota, and that must
be estimated and monitored explicitly.

## Anti-patterns This Exposed

- Calling Workers AI without any `429`-specific error handling.
- No fallback model defined — single model failure = feature failure.
- No prompt-level caching, causing redundant inference calls under load.
- Surfacing upstream `429` as a user-visible `500` instead of a degraded-but-functional UI.
- No pre-event capacity review against AI quota limits before enabling viral sharing.

## Related

- `rate-limit-before-you-need-it.md`
- `rate-limiter-misconfiguration-outage.md`
- `workers-cpu-time-premature-optimization.md`
- `circuit-breaker-prevents-cascade-failure.md`
- `ai-cost-finops-2026.md`

## Sources

- Cloudflare Workers AI docs — Rate limits and quotas
- Cloudflare AI Gateway docs — Fallback models and caching
- AWS Architecture Blog — Exponential backoff and jitter
