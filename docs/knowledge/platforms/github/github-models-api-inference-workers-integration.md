# GitHub Models API Inference from Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Calling Marketplace Models from Workers with Streaming and Fallback

GitHub Models exposes a growing catalogue of frontier and open-weight models—GPT-4o, Llama 3, Mistral, Phi-3, and others—through a unified OpenAI-compatible REST API authenticated with a GitHub personal access token or a GitHub App installation token. Calling that API from a Cloudflare Worker lets you ship AI-powered endpoints without managing GPU infrastructure, while keeping latency low by routing through Cloudflare's network.

The integration pattern follows three stages: token acquisition (from an environment binding or Workers Secrets), model selection with an optional runtime fallback chain, and streaming the server-sent event (SSE) response back to the caller. Because Workers use the standard Fetch API and the GitHub Models endpoint is OpenAI-compatible, the same code that calls `openai.chat.completions.create` maps directly to a plain `fetch` with `stream: true` and `TransformStream` handling.

Rate limits on GitHub Models differ by plan and model tier. Free-tier accounts allow roughly 150 requests per day for premium models and higher limits for standard ones. Enterprise accounts receive elevated quotas. When a `429` response arrives, the worker should log the `retry-after` header value and optionally fall back to Cloudflare Workers AI, which runs on Cloudflare's own GPU fleet and shares the same execution context with zero cold-start latency overhead.

## Context

- Runtime: Cloudflare Workers (ES modules format, `wrangler` 3.x)
- Models endpoint: `https://models.inference.ai.azure.com` (GitHub's hosted inference gateway)
- Auth: `GITHUB_TOKEN` Workers Secret bound as an environment variable
- Fallback: `@cloudflare/ai` binding (`env.AI`) running `@cf/meta/llama-3-8b-instruct`
- Streaming: SSE via `ReadableStream` + `TextDecoderStream`

## Model Selection and Configuration

Define a priority list at the top of the worker so the caller can pass a `model` hint or let the server pick the best available option:

```ts
// src/models.ts
export const MODEL_PRIORITY: string[] = [
  "gpt-4o",
  "gpt-4o-mini",
  "meta-llama-3-70b-instruct",
  "mistral-large",
];

export interface InferenceRequest {
  prompt: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
  stream?: boolean;
}

export function resolveModel(hint?: string): string {
  if (hint && MODEL_PRIORITY.includes(hint)) return hint;
  return MODEL_PRIORITY[0];
}
```

## Streaming Inference Handler

```ts
// src/index.ts
import { resolveModel, type InferenceRequest } from "./models";

const GITHUB_MODELS_URL = "https://models.inference.ai.azure.com/chat/completions";

export interface Env {
  GITHUB_TOKEN: string;
  AI: Ai; // Workers AI binding for fallback
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body: InferenceRequest = await request.json();
    const model = resolveModel(body.model);

    const payload = {
      model,
      messages: [{ role: "user", content: body.prompt }],
      max_tokens: body.maxTokens ?? 512,
      temperature: body.temperature ?? 0.7,
      stream: body.stream ?? true,
    };

    const ghResponse = await fetch(GITHUB_MODELS_URL, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      },
      body: JSON.stringify(payload),
    });

    if (ghResponse.status === 429) {
      const retryAfter = ghResponse.headers.get("retry-after") ?? "60";
      console.warn(`GitHub Models rate limited; retry-after=${retryAfter}s. Falling back to Workers AI.`);
      return fallbackToWorkersAI(env, body.prompt);
    }

    if (!ghResponse.ok) {
      const err = await ghResponse.text();
      return new Response(`Upstream error: ${err}`, { status: ghResponse.status });
    }

    // Pipe SSE stream directly to the client
    return new Response(ghResponse.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Model-Used": model,
      },
    });
  },
};

async function fallbackToWorkersAI(env: Env, prompt: string): Promise<Response> {
  const result = await env.AI.run("@cf/meta/llama-3-8b-instruct", {
    prompt,
    max_tokens: 512,
    stream: true,
  });

  return new Response(result as ReadableStream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Model-Used": "workers-ai-fallback",
      "X-Fallback-Reason": "github-models-rate-limited",
    },
  });
}
```

## Rate Limit Handling and Retry Budget

Track per-model usage in a Durable Object or KV namespace to implement client-side rate limiting before hitting the upstream 429:

```ts
// src/rateGuard.ts
export async function checkBudget(
  kv: KVNamespace,
  model: string,
  dailyLimit: number
): Promise<{ allowed: boolean; remaining: number }> {
  const today = new Date().toISOString().slice(0, 10);
  const key = `rate:${model}:${today}`;
  const raw = await kv.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= dailyLimit) return { allowed: false, remaining: 0 };

  await kv.put(key, String(count + 1), {
    expirationTtl: 86400, // expires after 24 h
  });
  return { allowed: true, remaining: dailyLimit - count - 1 };
}
```

```toml
# wrangler.toml
name = "github-models-proxy"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[vars]
DAILY_LIMIT_PREMIUM = "150"
DAILY_LIMIT_STANDARD = "1000"

[[kv_namespaces]]
binding = "RATE_KV"
id = "<your-kv-namespace-id>"

[ai]
binding = "AI"
```

## Anti-patterns

- Storing `GITHUB_TOKEN` in `wrangler.toml` vars — use `wrangler secret put GITHUB_TOKEN` instead
- Ignoring `retry-after` headers and hammering the endpoint in a tight loop
- Using a single long-lived personal access token shared across services; prefer GitHub App installation tokens with minimal scopes
- Buffering the entire SSE stream in the Worker before forwarding — this breaks streaming UX and wastes memory
- Calling `ghResponse.json()` when `stream: true` is set — the body will be an SSE text stream, not JSON

## Gotchas

- The GitHub Models endpoint base URL is Azure-hosted (`models.inference.ai.azure.com`), not `api.github.com`
- Model identifiers use Azure AI naming conventions (e.g., `gpt-4o` not `gpt-4-turbo`); verify exact IDs in the GitHub Models marketplace UI
- Workers AI streaming uses a slightly different SSE envelope than OpenAI's format — normalise if you need a uniform client interface
- GitHub Models tokens are scoped per user, not per org; enterprise SSO may require token re-authorisation
- `ReadableStream` piping in Workers does not buffer — if the client disconnects mid-stream the worker stops reading automatically

## Verification

```ts
// verify streaming roundtrip in a local miniflare test
import { unstable_dev } from "wrangler";
import { describe, it, expect, beforeAll, afterAll } from "vitest";

describe("github models proxy", () => {
  let worker: Awaited<ReturnType<typeof unstable_dev>>;

  beforeAll(async () => {
    worker = await unstable_dev("src/index.ts", { experimental: { disableExperimentalWarning: true } });
  });

  afterAll(() => worker.stop());

  it("returns streaming response with X-Model-Used header", async () => {
    const res = await worker.fetch("/", {
      method: "POST",
      body: JSON.stringify({ prompt: "hello", stream: true }),
      headers: { "Content-Type": "application/json" },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toMatch(/text\/event-stream/);
    expect(res.headers.get("x-model-used")).toBeTruthy();
  });
});
```

## Related

- `documentation/docs/policies/github/github-actions-cloudflare-deploy-workflow.md`
- `documentation/docs/policies/github/dependabot-auto-merge-workers-deps.md`
- `documentation/docs/policies/cloudflare/workers-ai-inference-patterns.md`

## Sources

- https://docs.github.com/en/github-models/prototyping-with-ai-models
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
