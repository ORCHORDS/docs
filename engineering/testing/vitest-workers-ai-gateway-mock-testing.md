# Vitest Workers AI Gateway Mock Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare AI Gateway proxies inference requests to model providers (Workers AI, OpenAI, Anthropic) and adds caching, rate-limiting, and logging. On example project / example.com, the AI Gateway routes anonymous content-moderation calls and post-summary generation. Testing against the live gateway in CI introduces latency, incurs per-token cost, and makes test outcomes non-deterministic. Teams need a way to mock the gateway's HTTP interface at the Worker level without altering production code paths.

## Context

The AI Gateway endpoint is a standard HTTPS URL (`https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}/{model}`). Worker code calls it via `fetch`. The `@cloudflare/vitest-pool-workers` pool supports outbound fetch interception through `fetchMock` from `cloudflare:test`, which intercepts calls at the `fetch` global before they leave the runtime — no network required in tests.

## Test Setup

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          compatibilityDate: "2024-09-23",
          compatibilityFlags: ["nodejs_compat"],
          // Enable outbound fetch mocking
          fetchMock: true,
        },
      },
    },
  },
});
```

```toml
# wrangler.toml
[vars]
AI_GATEWAY_URL = "https://gateway.ai.cloudflare.com/v1/ACCOUNT_ID/example project-gateway"
```

Define a typed factory for AI Gateway mock responses:

```typescript
// src/ai/gateway-mock.ts
export interface ChatCompletionChoice {
  index: number;
  message: { role: string; content: string };
  finish_reason: string;
}

export interface MockCompletionResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: ChatCompletionChoice[];
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export function makeGatewayResponse(
  content: string,
  model = "gpt-4o-mini"
): MockCompletionResponse {
  return {
    id: `chatcmpl-test-${Date.now()}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop",
      },
    ],
    usage: { prompt_tokens: 20, completion_tokens: 10, total_tokens: 30 },
  };
}

export function makeGatewayErrorResponse(
  code: number,
  message: string
): Response {
  return new Response(
    JSON.stringify({ error: { message, type: "invalid_request_error", code } }),
    {
      status: code,
      headers: { "content-type": "application/json" },
    }
  );
}
```

## Test Cases

```typescript
// src/ai/moderation.test.ts
import { fetchMock, env } from "cloudflare:test";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { makeGatewayResponse, makeGatewayErrorResponse } from "./gateway-mock";
import { moderatePost } from "../src/ai/moderation";

const GATEWAY_BASE =
  "https://gateway.ai.cloudflare.com/v1/ACCOUNT_ID/example project-gateway";

describe("AI Gateway: content moderation", () => {
  beforeEach(() => {
    fetchMock.activate();
    fetchMock.disableNetConnect();
  });

  afterEach(() => {
    fetchMock.deactivate();
  });

  it("returns safe=true when the model labels content benign", async () => {
    fetchMock
      .get(GATEWAY_BASE)
      .intercept({ path: /openai\/chat\/completions/ })
      .reply(
        200,
        JSON.stringify(makeGatewayResponse('{"safe": true, "reason": null}')),
        { headers: { "content-type": "application/json" } }
      );

    const result = await moderatePost(env, {
      postId: "post-1",
      body: "Just vibes",
    });

    expect(result.safe).toBe(true);
    expect(result.reason).toBeNull();
  });

  it("returns safe=false and a reason for flagged content", async () => {
    fetchMock
      .get(GATEWAY_BASE)
      .intercept({ path: /openai\/chat\/completions/ })
      .reply(
        200,
        JSON.stringify(
          makeGatewayResponse(
            '{"safe": false, "reason": "harassment"}'
          )
        ),
        { headers: { "content-type": "application/json" } }
      );

    const result = await moderatePost(env, {
      postId: "post-2",
      body: "Some harmful text",
    });

    expect(result.safe).toBe(false);
    expect(result.reason).toBe("harassment");
  });

  it("throws a retryable error on 429 rate-limit from gateway", async () => {
    fetchMock
      .get(GATEWAY_BASE)
      .intercept({ path: /openai\/chat\/completions/ })
      .reply(
        429,
        JSON.stringify({
          error: { message: "Rate limit exceeded", type: "rate_limit_error" },
        }),
        {
          headers: {
            "content-type": "application/json",
            "retry-after": "2",
          },
        }
      );

    await expect(
      moderatePost(env, { postId: "post-3", body: "text" })
    ).rejects.toMatchObject({ retryable: true, retryAfter: 2 });
  });

  it("caches gateway response in KV on the first call", async () => {
    const mockContent = '{"safe": true, "reason": null}';
    fetchMock
      .get(GATEWAY_BASE)
      .intercept({ path: /openai\/chat\/completions/ })
      .reply(200, JSON.stringify(makeGatewayResponse(mockContent)), {
        headers: { "content-type": "application/json" },
      });

    await moderatePost(env, { postId: "post-4", body: "Cached content" });

    const cached = await env.KV.get("mod:post-4");
    expect(cached).not.toBeNull();
    const parsed = JSON.parse(cached!);
    expect(parsed.safe).toBe(true);
  });

  it("serves from KV cache without calling gateway on repeat request", async () => {
    await env.KV.put(
      "mod:post-5",
      JSON.stringify({ safe: true, reason: null }),
      { expirationTtl: 3600 }
    );

    // No fetchMock intercept registered — any outbound call would throw
    const result = await moderatePost(env, {
      postId: "post-5",
      body: "irrelevant",
    });
    expect(result.safe).toBe(true);
  });
});
```

## Assertions

Verify that the Worker sends the correct request headers to the AI Gateway (authentication, content-type, provider routing):

```typescript
it("sends the correct cf-aig-authorization header to the gateway", async () => {
  let capturedHeaders: Headers | null = null;

  fetchMock
    .get(GATEWAY_BASE)
    .intercept({ path: /openai\/chat\/completions/ })
    .reply((req) => {
      capturedHeaders = req.headers as unknown as Headers;
      return {
        status: 200,
        data: JSON.stringify(makeGatewayResponse('{"safe":true,"reason":null}')),
        headers: { "content-type": "application/json" },
      };
    });

  await moderatePost(env, { postId: "post-6", body: "test" });

  expect(capturedHeaders).not.toBeNull();
  expect(capturedHeaders!.get("cf-aig-authorization")).toMatch(/^Bearer /);
  expect(capturedHeaders!.get("content-type")).toBe("application/json");
});
```

## CI Integration

```yaml
# .github/workflows/test.yml
name: AI Gateway Mock Tests
on: [push, pull_request]

jobs:
  ai-gateway:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Run AI gateway mock tests
        run: pnpm vitest run src/ai/moderation.test.ts --reporter=verbose
        env:
          # No real Cloudflare credentials needed — all calls are mocked
          AI_GATEWAY_TOKEN: test-token
```

Use a separate Vitest project for AI tests so they can be skipped on non-AI branches:

```typescript
// vitest.config.ts — add an AI project
export default defineWorkersConfig({
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "ai",
          include: ["src/ai/**/*.test.ts"],
        },
      },
    ],
  },
});
```

## Anti-patterns

- Calling the real AI Gateway in tests — non-deterministic, slow, and costs tokens.
- Mocking `fetch` globally with `vi.fn()` outside the Workers pool — bypasses the runtime and misses Workers-specific fetch behaviours (Cloudflare headers, CF-Ray, etc.).
- Checking only the top-level `choices[0].message.content` string — validate that your JSON-parsing layer handles malformed model output gracefully with a mock returning invalid JSON.
- Leaving `fetchMock.activate()` without `fetchMock.deactivate()` in `afterEach` — leaks mock state into subsequent tests.
- Using `fetchMock.disableNetConnect()` without an intercept for every expected URL — causes confusing "Network connection not allowed" errors for unrelated internal fetch calls.

## Gotchas

- AI Gateway URLs differ by provider prefix (`openai`, `anthropic`, `workers-ai`) — ensure your intercept path matches the provider your Worker code targets.
- The `cf-aig-authorization` header for AI Gateway auth is distinct from the `Authorization` header used by the upstream provider.
- `fetchMock` intercepts at the global `fetch` level; if your code uses `env.AI.run(...)` (Workers AI binding), a separate binding mock via `vi.fn()` on `env.AI` is needed instead.
- Mock responses must be valid JSON with `content-type: application/json` or your JSON parsing code will throw before tests can assert on the business logic.
- Gateway caching headers (`cf-aig-cache-status`) are not set by fetchMock — if your code branches on cache status, mock those headers explicitly.

## Verification

```bash
pnpm vitest run src/ai/moderation.test.ts --reporter=verbose
# Expect: 6 tests pass, 0 network calls made

# Confirm no real requests by setting an impossible URL:
AI_GATEWAY_URL=https://does-not-exist.invalid pnpm vitest run src/ai/moderation.test.ts
# Should still pass (all calls intercepted)
```

## Related

- [workers-ai-binding-vitest-mocking.md](workers-ai-binding-vitest-mocking.md)
- [vitest-cloudflare-pool-workers.md](vitest-cloudflare-pool-workers.md)
- [vitest-workers-kv-namespace-isolation.md](vitest-workers-kv-namespace-isolation.md)
- [api-mock-fidelity-schema-locking.md](api-mock-fidelity-schema-locking.md)

## Sources

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/workers/testing/vitest-integration/fetch-mock/
- https://miniflare.dev/testing/fetch-mock
- https://developers.cloudflare.com/ai-gateway/providers/openai/
