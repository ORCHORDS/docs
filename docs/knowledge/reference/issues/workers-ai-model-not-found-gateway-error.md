# Workers AI "Model not found" Error: Wrong Model ID Format or Missing @cf/ Prefix

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker throws an error when calling `env.AI.run()` with a Workers AI model:

```
Error: Model not found: mistral-7b-instruct-v0.1
Error: Model not found: llama-2-7b-chat-int8
Error: 1020 Access denied — when using AI Gateway with wrong model routing
Error: Model not found: @cf/meta/llama-2-7b-chat-int8-v2  (wrong version suffix)
```

Or through AI Gateway, requests return `504 Gateway Timeout` or `400 Bad Request` with an opaque JSON error body.

The model clearly exists — you can see it in the Cloudflare dashboard — but the runtime rejects the ID you're using.

---

## Context

- **Runtime**: Cloudflare Workers
- **Feature**: Workers AI (`env.AI.run()`), AI Gateway
- **Binding**: `AI` binding in `wrangler.toml`
- **Wrangler**: 3.x
- **TypeScript**: 5.x with `@cloudflare/workers-types` and `@cloudflare/ai`

---

## Root Cause

Workers AI model IDs follow a strict format:

```
@cf/<provider>/<model-name-and-version>
```

Examples:
- `@cf/meta/llama-3.1-8b-instruct`
- `@cf/mistral/mistral-7b-instruct-v0.1`
- `@cf/stabilityai/stable-diffusion-xl-base-1.0`
- `@cf/baai/bge-base-en-v1.5`

Three common failure modes:

1. **Missing `@cf/` prefix**: Using `llama-3.1-8b-instruct` instead of `@cf/meta/llama-3.1-8b-instruct`.
2. **Wrong or outdated version suffix**: Model IDs are versioned. `@cf/meta/llama-2-7b-chat-int8` may have been renamed or retired; the correct ID might be `@cf/meta/llama-2-7b-chat-int8` (exact match required — no partial matching).
3. **Incorrect provider segment**: `@cf/llama/llama-3.1-8b-instruct` instead of `@cf/meta/llama-3.1-8b-instruct`.

For AI Gateway, an additional failure mode is **incorrect gateway URL format** or **model ID in the gateway endpoint that doesn't match the binding call**. AI Gateway sits in front of Workers AI and validates model IDs independently.

Model IDs are **not inferred, normalized, or fuzzy-matched** by the runtime. An exact string match is required.

---

## Broken Code

```toml
# wrangler.toml
name = "my-ai-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"
```

```typescript
// src/index.ts — BROKEN: wrong model ID formats
import { Ai } from '@cloudflare/ai';

interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // BROKEN #1: missing @cf/ prefix and provider segment
    const response1 = await env.AI.run('llama-3.1-8b-instruct', {
      prompt: 'What is Cloudflare Workers?',
    });
    // => Error: Model not found: llama-3.1-8b-instruct

    // BROKEN #2: wrong provider name
    const response2 = await env.AI.run('@cf/llama/llama-3.1-8b-instruct', {
      prompt: 'Hello',
    });
    // => Error: Model not found: @cf/llama/llama-3.1-8b-instruct

    // BROKEN #3: retired/outdated model version
    const response3 = await env.AI.run('@cf/meta/llama-2-7b-chat-int8-v2', {
      prompt: 'Hello',
    });
    // => Error: Model not found: @cf/meta/llama-2-7b-chat-int8-v2

    return Response.json({ response1, response2, response3 });
  },
};
```

```typescript
// src/ai-gateway.ts — BROKEN: AI Gateway URL format error
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // BROKEN: gateway slug format wrong — missing account ID path segment
    const gatewayUrl = 'https://gateway.ai.cloudflare.com/my-gateway/workers-ai';

    const response = await fetch(`${gatewayUrl}/@cf/meta/llama-3.1-8b-instruct`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ prompt: 'Hello' }),
    });
    // => 400 Bad Request or 404 — wrong gateway URL structure

    return response;
  },
};
```

---

## Fix

### Step 1 — Get exact model IDs from the CLI

```bash
# List all available Workers AI models with their exact IDs
npx wrangler ai models list

# Filter for a specific model family
npx wrangler ai models list | grep llama
# => @cf/meta/llama-3.1-8b-instruct
# => @cf/meta/llama-3.2-11b-vision-instruct
# => @cf/meta/llama-2-7b-chat-int8
# => ...

# Or use the Cloudflare API directly
curl -s https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/models/search \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].name'
```

### Step 2 — Use exact model IDs with TypeScript types

```typescript
// src/index.ts — FIXED
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const modelPath = url.pathname;

    if (modelPath === '/chat') {
      // Exact model ID — @cf/provider/model-name-version
      const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
        messages: [
          { role: 'system', content: 'You are a helpful assistant.' },
          { role: 'user', content: 'Explain Cloudflare Workers in one sentence.' },
        ],
        max_tokens: 256,
      });
      return Response.json(result);
    }

    if (modelPath === '/embed') {
      // Embedding model — exact ID required
      const result = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
        text: ['Cloudflare Workers is a serverless platform.'],
      });
      return Response.json(result);
    }

    if (modelPath === '/image') {
      // Image generation — exact ID required
      const result = await env.AI.run(
        '@cf/stabilityai/stable-diffusion-xl-base-1.0',
        { prompt: 'A futuristic data center in the clouds' }
      );
      // Returns ReadableStream of image bytes
      return new Response(result, {
        headers: { 'Content-Type': 'image/png' },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};

interface Env {
  AI: Ai;
}
```

### Step 3 — Fix AI Gateway URL structure

```typescript
// src/ai-gateway.ts — FIXED
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Correct AI Gateway URL format:
    // https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_slug}/workers-ai/{model_id}
    const accountId = env.CF_ACCOUNT_ID;
    const gatewaySlug = 'my-gateway';
    const modelId = '@cf/meta/llama-3.1-8b-instruct';

    const gatewayUrl = [
      'https://gateway.ai.cloudflare.com/v1',
      accountId,
      gatewaySlug,
      'workers-ai',
      modelId,
    ].join('/');

    const response = await fetch(gatewayUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        messages: [
          { role: 'user', content: 'Hello from AI Gateway!' },
        ],
      }),
    });

    if (!response.ok) {
      const err = await response.text();
      return new Response(`Gateway error ${response.status}: ${err}`, {
        status: response.status,
      });
    }

    return Response.json(await response.json());
  },
};

interface Env {
  AI: Ai;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
}
```

### Step 4 — Use AI Gateway binding (preferred over direct HTTP)

```toml
# wrangler.toml — FIXED: use AI Gateway via binding
name = "my-ai-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"
gateway = { id = "my-gateway", skip_cache = false, cache_ttl = 3600 }
```

```typescript
// src/index.ts — FIXED: gateway configured in wrangler.toml, model ID exact
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // AI binding routes through AI Gateway automatically when configured
    const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [{ role: 'user', content: 'Hello!' }],
    });
    return Response.json(result);
  },
};

interface Env {
  AI: Ai;
}
```

---

## Verification

```bash
# 1. List models and confirm exact ID
npx wrangler ai models list | grep -i 'llama-3.1-8b'
# => @cf/meta/llama-3.1-8b-instruct

# 2. Test a model call directly via wrangler CLI
npx wrangler ai run @cf/meta/llama-3.1-8b-instruct '{"messages":[{"role":"user","content":"Hi"}]}'
# => {"response": "Hello! How can I help you today?"}

# 3. Run local dev and test
npx wrangler dev
curl -X POST http://localhost:8787/chat
# => {"response": "Cloudflare Workers is a serverless execution environment..."}

# 4. Check AI Gateway logs for model routing errors
# Dashboard: Cloudflare Dashboard > AI Gateway > your-gateway > Logs
# Look for: model_id field, status codes, latency

# 5. Tail worker logs for model errors
npx wrangler tail --format=pretty | grep -i 'model'
# Should show no "Model not found" errors

# 6. Verify gateway URL structure
curl -v 'https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/my-gateway/workers-ai/@cf/meta/llama-3.1-8b-instruct' \
  -H 'Authorization: Bearer $CF_API_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"test"}]}'
# => HTTP 200 with response JSON
```

---

## Anti-patterns

- Hard-coding model IDs from blog posts or tutorials without verifying against `wrangler ai models list` — model IDs change as new versions are released.
- Using short model names (e.g. `llama3`, `mistral`) and assuming the runtime resolves them.
- Constructing AI Gateway URLs by hand using guessed path formats — use the dashboard URL or the documented format exactly.
- Ignoring the AI Gateway logs — they show model routing, cache hits/misses, and error codes that are invisible in Worker logs.
- Using the `@cloudflare/ai` package's model constants without checking if they reflect currently available models.

---

## Gotchas

- `wrangler ai models list` shows **currently available** models; retired models are removed and will always return "Model not found" regardless of their previously valid ID.
- Model IDs that worked 6 months ago may be retired — Cloudflare updates the catalog regularly.
- The `@cf/` prefix is mandatory; the full three-part format `@cf/<provider>/<name>` is required.
- AI Gateway caches responses by model ID + request hash; a model ID typo that changes caching key may mask intermittent errors in AI Gateway logs.
- Workers AI in `wrangler dev` (local) sends requests to the real Cloudflare AI inference infrastructure — there is no local model serving. Costs and rate limits apply during local dev.
- The `cf.ai.models` TypeScript type union may lag behind the live model catalog; always cross-check with `wrangler ai models list`.

---

## Related

- `documentation/docs/policies/issues/workers-kv-binding-undefined-wrangler-toml.md`
- `documentation/docs/policies/issues/workers-fetch-null-body-consumed-error.md`
- `documentation/docs/policies/issues/d1-wrangler-local-remote-binding-mismatch.md`

---

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- https://developers.cloudflare.com/ai-gateway/get-started/
- https://developers.cloudflare.com/ai-gateway/providers/workersai/
- https://developers.cloudflare.com/workers/wrangler/commands/#ai
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
