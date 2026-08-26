# Workers AI Gateway Semantic Cache for LLM Cost and Latency Reduction

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

LLM API calls are expensive and slow. Users submitting near-identical prompts—"summarize this article" vs "give me a summary of this article"—bypass the deterministic Cache API entirely because the request body differs. Costs balloon; p99 latency stays pinned at 2–5 s even when the answer is semantically the same as a recent response.

## Context

Cloudflare AI Gateway sits as a proxy between your Worker and any upstream LLM provider (OpenAI, Anthropic, Workers AI, etc.). Beyond logging and rate-limiting it offers **semantic caching**: it embeds incoming prompts with a small embedding model and compares against a vector index of cached prompt-response pairs. Requests whose similarity score exceeds a configurable threshold receive the cached response without hitting the upstream provider. Cache hits are typically < 50 ms versus 1–5 s for live inference.

Semantic cache is enabled per-gateway in the Cloudflare dashboard and is configurable through the `cf-aig-cache-ttl` and `cf-aig-skip-cache` request headers from the Worker side.

---

## Configuring the AI Gateway Endpoint in a Worker

```typescript
// wrangler.toml binding
// [ai]
// binding = "AI"
// gateway = { id = "my-llm-gateway" }

interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json<{ prompt: string }>();

    const response = await env.AI.run(
      "@cf/meta/llama-3.1-8b-instruct",
      { messages: [{ role: "user", content: prompt }] },
      {
        gateway: {
          id: "my-llm-gateway",
          // Semantic cache TTL in seconds (default: 3600)
          cacheTtl: 86_400,
          // Skip cache for this request if needed
          skipCache: false,
        },
      }
    );

    return Response.json(response);
  },
} satisfies ExportedHandler<Env>;
```

---

## Setting Cache Headers for External LLM Providers

For non-Workers-AI providers routed through the AI Gateway URL:

```typescript
const GATEWAY_URL =
  "https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/openai";

async function callWithSemanticCache(
  prompt: string,
  sessionId: string
): Promise<string> {
  const response = await fetch(`${GATEWAY_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      // Semantic cache TTL: 24 hours
      "cf-aig-cache-ttl": "86400",
      // Scope cache to session to avoid cross-user leakage of personalised content
      "cf-aig-cache-key": `session:${sessionId}`,
      // Skip cache for requests flagged as sensitive
      // "cf-aig-skip-cache": "true",
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
    }),
  });

  const data = await response.json<{ choices: { message: { content: string } }[] }>();
  // "cf-cache-status" header is "HIT" | "MISS" | "BYPASS"
  const cacheStatus = response.headers.get("cf-cache-status") ?? "UNKNOWN";
  console.log(`AI Gateway cache: ${cacheStatus}`);

  return data.choices[0].message.content;
}
```

---

## Partitioning Cache Keys by User Context

Semantic cache is global by default. For personalised outputs (user-specific tone, account data) partition with a cache key prefix to prevent cross-user leakage:

```typescript
async function personalizedCompletion(
  env: Env,
  userId: string,
  tier: "free" | "pro",
  prompt: string
): Promise<string> {
  // Only cache-share across users for tier-generic prompts
  const cacheScope = tier === "pro" ? `user:${userId}` : `tier:free`;

  const res = await fetch(`${GATEWAY_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      "cf-aig-cache-ttl": tier === "pro" ? "3600" : "86400",
      "cf-aig-cache-key": cacheScope,
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
      // Lower temperature → more deterministic → higher cache hit rate
      temperature: tier === "pro" ? 0.7 : 0.2,
    }),
  });

  const data = await res.json<{ choices: { message: { content: string } }[] }>();
  return data.choices[0].message.content;
}
```

---

## Streaming Responses and Cache Interaction

Semantic cache returns the full cached response as a non-streaming body even if the original request used streaming. Handle both gracefully:

```typescript
async function streamOrCached(prompt: string): Promise<ReadableStream<Uint8Array>> {
  const res = await fetch(`${GATEWAY_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      "cf-aig-cache-ttl": "3600",
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
      stream: true,
    }),
  });

  const cacheStatus = res.headers.get("cf-cache-status");

  if (cacheStatus === "HIT") {
    // Gateway returns full JSON on a cache hit; wrap as SSE for consistency
    const text = await res.text();
    const encoder = new TextEncoder();
    return new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(`data: ${text}\n\ndata: [DONE]\n\n`));
        controller.close();
      },
    });
  }

  // MISS: pass through the live SSE stream
  return res.body!;
}
```

---

## Measuring Cache Hit Rate via AI Gateway Analytics

```typescript
// Query AI Gateway GraphQL Analytics to monitor semantic cache efficiency
async function getGatewayAnalytics(accountId: string, gatewayId: string, apiToken: string) {
  const query = `
    query {
      viewer {
        accounts(filter: { accountTag: "${accountId}" }) {
          aiGatewayRequestsAdaptiveGroups(
            filter: {
              gatewayId: "${gatewayId}"
              datetime_geq: "${new Date(Date.now() - 86_400_000).toISOString()}"
            }
            limit: 1
          ) {
            sum {
              requests
              cachedRequests
              tokensIn
              tokensOut
            }
          }
        }
      }
    }
  `;

  const res = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiToken}`,
    },
    body: JSON.stringify({ query }),
  });

  const { data } = await res.json<{ data: unknown }>();
  return data;
}
```

---

## Anti-patterns

- **Similarity threshold too low** (`< 0.85`): semantically unrelated prompts match; users get wrong answers. Default is 0.95—only lower after measuring false-positive rate in logs.
- **Caching PII-containing prompts without key scoping**: a prompt with a user's name or account number could be returned to a different user. Always scope `cf-aig-cache-key` to the user or session when prompts may contain personal data.
- **Setting `stream: true` and expecting cached responses to stream**: the gateway returns the full body on a HIT. Build the client to handle both SSE and JSON payloads.
- **Ignoring `cf-cache-status` in metrics**: without tracking HIT/MISS you cannot measure ROI or detect threshold regressions.

## Gotchas

- Semantic cache is **per-gateway**, not per-model. If you route GPT-4o and Llama through the same gateway ID, prompt embeddings from one model's responses may match the other model's cache—producing mismatched outputs. Use separate gateway IDs per model family.
- Cache TTL resets on every **HIT**, not from first insert. A heavily queried cached response may live indefinitely unless you set `cf-aig-cache-ttl` to an absolute value that fits your content freshness requirement.
- Streaming responses (`stream: true`) that result in a cache MISS do **not** get written to the semantic cache unless the Worker also reads the full body before forwarding. Gateway caches only complete responses.
- `cf-aig-cache-key` overrides are additive with the gateway's built-in key (model + provider). You cannot strip the model from the key.

## Verification

```bash
# Check cache status on a sample request via curl
curl -s -D - https://gateway.ai.cloudflare.com/v1/{account}/{gw}/openai/chat/completions \
  -H "Authorization: Bearer $OPENAI_KEY" \
  -H "Content-Type: application/json" \
  -H "cf-aig-cache-ttl: 3600" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"What is 2+2?"}]}' \
  | grep -i "cf-cache-status"
# Expected: cf-cache-status: MISS on first call, HIT on repeat with similar prompt
```

Run the same prompt twice; verify the second call returns `cf-cache-status: HIT` and latency drops below 100 ms. Monitor the AI Gateway dashboard **Caching** tab for 24-hour hit rate—target ≥ 30 % for FAQ-style workloads.

## Related

- `workers-ai-inference-response-caching.md`
- `workers-ai-batch-inference-throughput.md`
- `workers-ai-token-streaming-latency.md`
- `cache-api-stale-if-error-fallback.md`
- `workers-llm-streaming-responses.md`

## Sources

- Cloudflare AI Gateway docs – Semantic Cache: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- Cloudflare AI Gateway docs – Cache Headers: https://developers.cloudflare.com/ai-gateway/configuration/cache-headers/
- Workers AI Binding with Gateway: https://developers.cloudflare.com/workers-ai/configuration/ai-gateway/
