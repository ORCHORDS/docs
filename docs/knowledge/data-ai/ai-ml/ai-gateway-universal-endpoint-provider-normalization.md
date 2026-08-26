# AI Gateway Universal Endpoint and Provider Normalization

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your application calls multiple LLM providers—OpenAI for GPT-4o, Anthropic for Claude,
Google for Gemini, and Cloudflare Workers AI for on-premise-like inference—each with
different base URLs, authentication headers, request shapes, and error formats. Rotating
providers for cost or availability reasons requires changes scattered across the codebase.
You need a single, stable endpoint that hides provider differences, logs every call in
one place, and lets you change the backend without touching application code.

## Context

Cloudflare AI Gateway acts as a reverse proxy in front of any supported LLM provider.
You replace the provider's base URL with your AI Gateway URL and send otherwise identical
API calls. The Gateway:
- Forwards requests to the real provider, injecting the provider API key from its own
  secrets store.
- Logs request/response metadata (latency, token counts, cost estimate) to the Gateway
  dashboard and optionally to Logpush.
- Applies rate limits, caching, and fallback logic configured in the dashboard or via
  the REST API.
- Exposes a single analytics surface across all providers.

This article covers the "universal endpoint" pattern: routing all providers through one
Gateway using provider-aware URL construction, centralised key management, and
transparent fallback chains.

## Gateway URL Construction

Every provider exposes the same structural URL pattern through AI Gateway:

```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_name}/{provider}/{provider_path}
```

| Provider           | Provider slug  | Example path                          |
|--------------------|----------------|---------------------------------------|
| OpenAI             | `openai`       | `chat/completions`                    |
| Anthropic          | `anthropic`    | `v1/messages`                         |
| Google AI Studio   | `google-ai-studio` | `v1beta/models/{model}:generateContent` |
| Workers AI         | `workers-ai`   | `@cf/meta/llama-3.1-8b-instruct`     |
| Azure OpenAI       | `azure-openai` | `openai/deployments/{dep}/chat/completions` |

```typescript
// src/gateway.ts — build provider-aware URLs
const ACCOUNT_ID  = "your_account_id";
const GATEWAY     = "prod-gateway";
const BASE        = `https://gateway.ai.cloudflare.com/v1/${ACCOUNT_ID}/${GATEWAY}`;

export const providerUrl = {
  openai: (path: string) => `${BASE}/openai/${path}`,
  anthropic: (path: string) => `${BASE}/anthropic/${path}`,
  workersAi: (model: string) => `${BASE}/workers-ai/${model}`,
  googleAi: (model: string, method: string) =>
    `${BASE}/google-ai-studio/v1beta/models/${model}:${method}`,
} as const;
```

## Unified Provider Client

Build a thin normalisation layer so the rest of the codebase calls one function:

```typescript
// src/llm-client.ts
import { providerUrl } from "./gateway";

export type ProviderName = "openai" | "anthropic" | "workers-ai";

export interface ChatCompletionRequest {
  provider: ProviderName;
  model: string;
  systemPrompt?: string;
  userMessage: string;
  maxTokens?: number;
  temperature?: number;
}

export interface ChatCompletionResponse {
  text: string;
  inputTokens: number;
  outputTokens: number;
  provider: ProviderName;
  model: string;
}

/** Normalise OpenAI-compatible response shape. */
function parseOpenAI(body: Record<string, unknown>, model: string): ChatCompletionResponse {
  const choice = (body.choices as { message: { content: string } }[])[0];
  const usage = body.usage as { prompt_tokens: number; completion_tokens: number };
  return {
    text: choice.message.content,
    inputTokens: usage.prompt_tokens,
    outputTokens: usage.completion_tokens,
    provider: "openai",
    model,
  };
}

/** Normalise Anthropic Messages response shape. */
function parseAnthropic(body: Record<string, unknown>, model: string): ChatCompletionResponse {
  const content = (body.content as { type: string; text: string }[]).find(
    (b) => b.type === "text",
  );
  const usage = body.usage as { input_tokens: number; output_tokens: number };
  return {
    text: content?.text ?? "",
    inputTokens: usage.input_tokens,
    outputTokens: usage.output_tokens,
    provider: "anthropic",
    model,
  };
}

/** Normalise Workers AI response shape. */
function parseWorkersAI(body: Record<string, unknown>, model: string): ChatCompletionResponse {
  const result = body.result as { response: string };
  return {
    text: result.response,
    inputTokens: 0,   // Workers AI does not return token counts in the response body
    outputTokens: 0,
    provider: "workers-ai",
    model,
  };
}

/** Route a unified request through AI Gateway to the selected provider. */
export async function chatCompletion(
  req: ChatCompletionRequest,
  apiKeys: Record<ProviderName, string>,
): Promise<ChatCompletionResponse> {
  const { provider, model, systemPrompt, userMessage, maxTokens = 512, temperature = 0.7 } = req;

  let url: string;
  let headers: Record<string, string>;
  let body: unknown;

  switch (provider) {
    case "openai":
      url = providerUrl.openai("chat/completions");
      headers = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKeys.openai}`,
      };
      body = {
        model,
        messages: [
          ...(systemPrompt ? [{ role: "system", content: systemPrompt }] : []),
          { role: "user", content: userMessage },
        ],
        max_tokens: maxTokens,
        temperature,
      };
      break;

    case "anthropic":
      url = providerUrl.anthropic("v1/messages");
      headers = {
        "Content-Type": "application/json",
        "x-api-key": apiKeys.anthropic,
        "anthropic-version": "2023-06-01",
      };
      body = {
        model,
        system: systemPrompt,
        messages: [{ role: "user", content: userMessage }],
        max_tokens: maxTokens,
      };
      break;

    case "workers-ai":
      url = providerUrl.workersAi(model);
      headers = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKeys["workers-ai"]}`,
      };
      body = {
        messages: [
          ...(systemPrompt ? [{ role: "system", content: systemPrompt }] : []),
          { role: "user", content: userMessage },
        ],
        max_tokens: maxTokens,
        temperature,
      };
      break;

    default:
      throw new Error(`Unsupported provider: ${provider}`);
  }

  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`[${provider}] HTTP ${response.status}: ${errText}`);
  }

  const json = (await response.json()) as Record<string, unknown>;

  switch (provider) {
    case "openai":    return parseOpenAI(json, model);
    case "anthropic": return parseAnthropic(json, model);
    case "workers-ai": return parseWorkersAI(json, model);
    default: throw new Error("unreachable");
  }
}
```

## Fallback Chain via the Gateway Config API

AI Gateway supports ordered fallback chains configured declaratively. When the primary
provider fails (5xx, timeout, or rate-limit), the Gateway tries the next entry
automatically—without any client-side retry logic:

```typescript
// scripts/configure-fallback.ts  (run in CI, not in Worker)
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const TOKEN      = process.env.CF_API_TOKEN!;
const GATEWAY    = "prod-gateway";

// Retrieve the gateway config via REST
const resp = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai-gateway/gateways/${GATEWAY}`,
  { headers: { Authorization: `Bearer ${TOKEN}` } },
);
console.log(await resp.json());

// The fallback chain is expressed in the request body when using the
// "universal endpoint" payload format (single POST to the gateway):
const universalPayload = [
  {
    provider: "openai",
    endpoint: "chat/completions",
    headers: { Authorization: `Bearer ${process.env.OPENAI_KEY}` },
    query: {
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "Hello" }],
      max_tokens: 100,
    },
  },
  {
    provider: "anthropic",
    endpoint: "v1/messages",
    headers: {
      "x-api-key": process.env.ANTHROPIC_KEY,
      "anthropic-version": "2023-06-01",
    },
    query: {
      model: "claude-3-5-haiku-20241022",
      messages: [{ role: "user", content: "Hello" }],
      max_tokens: 100,
    },
  },
  {
    provider: "workers-ai",
    endpoint: "@cf/meta/llama-3.1-8b-instruct",
    headers: { Authorization: `Bearer ${process.env.CF_API_TOKEN}` },
    query: {
      messages: [{ role: "user", content: "Hello" }],
      max_tokens: 100,
    },
  },
];

const fallbackResp = await fetch(
  `https://gateway.ai.cloudflare.com/v1/${ACCOUNT_ID}/${GATEWAY}`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(universalPayload),
  },
);
console.log(await fallbackResp.json());
```

The Gateway tries each entry in order; the first successful response is returned to
the caller. Failures are logged against the specific provider in the dashboard.

## Anti-patterns

- **Embedding provider API keys in Worker source or wrangler.jsonc env vars (unencrypted)**:
  use `wrangler secret put` so keys are stored encrypted and never appear in the
  deployed bundle.
- **Building provider-specific retry logic in application code**: the Gateway's native
  fallback chain handles provider failures; application-level retries duplicate this
  and can cause thundering-herd loops.
- **Pointing the Gateway URL at a staging provider during production deployments**:
  Gateway names are global to the account; always use separate gateways (`prod-gateway`,
  `staging-gateway`) for different environments.
- **Ignoring per-provider token count differences**: OpenAI and Anthropic return token
  counts in response bodies; Workers AI does not. Budget tracking must handle the
  zero-token case for Workers AI or use AI Gateway's analytics instead.

## Gotchas

- **Gateway caching applies to all providers**: if caching is enabled on the gateway
  and you switch providers in the fallback chain, a cached response from OpenAI may be
  returned even after OpenAI fails and the fallback switches to Anthropic. Disable
  caching or scope cache keys to the provider when using fallback chains.
- **Anthropic `system` field**: unlike OpenAI's `system` role message, Anthropic uses
  a top-level `system` string field. The normalisation layer above handles this but
  third-party SDK wrappers often do not.
- **Workers AI response nesting**: the Workers AI response via AI Gateway wraps the
  model output under `{ "result": { "response": "..." }, "success": true }`. Parse
  `body.result.response`, not `body.response`.
- **Rate limits are per-gateway, not per-provider**: a gateway-level rate limit blocks
  all providers at once. Use separate gateways if you want per-provider limits.

## Verification

```bash
# Direct provider call through gateway — OpenAI path
curl -s -X POST \
  "https://gateway.ai.cloudflare.com/v1/${CF_ACCOUNT_ID}/prod-gateway/openai/chat/completions" \
  -H "Authorization: Bearer ${OPENAI_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ping"}],"max_tokens":5}' \
  | jq .choices[0].message.content

# Anthropic path
curl -s -X POST \
  "https://gateway.ai.cloudflare.com/v1/${CF_ACCOUNT_ID}/prod-gateway/anthropic/v1/messages" \
  -H "x-api-key: ${ANTHROPIC_KEY}" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","messages":[{"role":"user","content":"ping"}],"max_tokens":5}' \
  | jq .content[0].text

# Workers AI path
curl -s -X POST \
  "https://gateway.ai.cloudflare.com/v1/${CF_ACCOUNT_ID}/prod-gateway/workers-ai/@cf/meta/llama-3.1-8b-instruct" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"ping"}],"max_tokens":5}' \
  | jq .result.response

# Check gateway logs for all three providers in one view
wrangler ai gateway logs --gateway prod-gateway --limit 10 | jq '.[] | {provider, latency, status}'
```

## Related

- `ai-gateway-caching.md`
- `ai-gateway-logging.md`
- `ai-gateway-rate-limiting.md`
- `llm-fallback-provider-rotation.md`
- `llm-provider-abstraction.md`
- `cloudflare-ai-gateway-observability.md`
- `ai-cost-monitoring.md`

## Sources

- AI Gateway universal endpoint: https://developers.cloudflare.com/ai-gateway/providers/
- AI Gateway fallback configuration: https://developers.cloudflare.com/ai-gateway/configuration/fallbacks/
- AI Gateway REST API: https://developers.cloudflare.com/api/operations/ai-gateway-list-ai-gateways
- Workers AI via AI Gateway: https://developers.cloudflare.com/ai-gateway/providers/workersai/
