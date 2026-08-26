# AI Gateway Fallback Model Chain Resilience

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Workers AI or third-party LLM calls fail intermittently under load: rate limit
429s from OpenAI, 503s from Anthropic, or timeouts on large context windows. You need
automatic retry-and-fallback logic that tries a cheaper or alternative model before
returning an error to the user, with all attempts logged in one place.

## Context

Cloudflare AI Gateway supports **provider fallbacks** natively: you configure an
ordered list of providers and models, and the gateway tries them in sequence when the
previous attempt fails. This is different from client-side retry logic because the
gateway handles the orchestration server-side — your Worker makes a single fetch call,
and AI Gateway manages the cascade.

The result is a resilient chain with unified logging and caching across all attempts,
without adding retry state machines to your Worker code.

---

## 1. AI Gateway URL Structure for Fallbacks

```typescript
// src/gateway.ts

// AI Gateway universal endpoint format:
// https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/

const GATEWAY_BASE =
  `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.GATEWAY_ID}`;

// For fallbacks, POST to the universal endpoint with a providers array
const FALLBACK_ENDPOINT = `${GATEWAY_BASE}`;
```

The universal endpoint accepts a `providers` array; the gateway tries each entry in
order until one succeeds.

---

## 2. Universal Endpoint Fallback Request

```typescript
// src/gateway.ts (continued)

interface GatewayProvider {
  provider: string;
  endpoint: string;
  headers: Record<string, string>;
  query: Record<string, unknown>;
}

export async function chatWithFallback(
  env: Env,
  userMessage: string
): Promise<string> {
  const providers: GatewayProvider[] = [
    // Primary: OpenAI GPT-4o-mini (fast, cheap)
    {
      provider: 'openai',
      endpoint: 'chat/completions',
      headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}` },
      query: {
        model: 'gpt-4o-mini',
        messages: [{ role: 'user', content: userMessage }],
        max_tokens: 512,
      },
    },
    // Fallback 1: Anthropic Claude Haiku (alternative provider)
    {
      provider: 'anthropic',
      endpoint: 'messages',
      headers: {
        'x-api-key': env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      query: {
        model: 'claude-haiku-4-5',
        max_tokens: 512,
        messages: [{ role: 'user', content: userMessage }],
      },
    },
    // Fallback 2: Workers AI Llama (no external API key required)
    {
      provider: 'workers-ai',
      endpoint: '@cf/meta/llama-3.1-8b-instruct',
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      query: {
        messages: [{ role: 'user', content: userMessage }],
        max_tokens: 512,
      },
    },
  ];

  const res = await fetch(
    `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.GATEWAY_ID}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(providers),
    }
  );

  if (!res.ok) {
    throw new Error(`All providers failed. Final status: ${res.status}`);
  }

  // Response shape matches whichever provider succeeded
  const data = await res.json<Record<string, unknown>>();

  // Normalise across OpenAI-compatible and Anthropic response shapes
  return extractContent(data);
}

function extractContent(data: Record<string, unknown>): string {
  // OpenAI / Workers AI shape
  const choices = data.choices as Array<{ message: { content: string } }> | undefined;
  if (choices?.[0]?.message?.content) return choices[0].message.content;

  // Anthropic shape
  const content = data.content as Array<{ text: string }> | undefined;
  if (content?.[0]?.text) return content[0].text;

  // Workers AI direct shape
  if (typeof data.response === 'string') return data.response;

  throw new Error('Cannot parse response from any provider');
}
```

---

## 3. Same-Provider Model Fallback (Workers AI only)

```typescript
// src/workers-ai-fallback.ts
// For Workers AI-only chains: try a large model first, fall back to a small one

export async function runWithModelFallback(
  ai: Ai,
  messages: { role: string; content: string }[],
  maxTokens = 512
): Promise<string> {
  const models = [
    '@cf/meta/llama-3.3-70b-instruct-fp8-fast', // primary: large model
    '@cf/meta/llama-3.1-8b-instruct',            // fallback: smaller, faster
  ];

  let lastError: Error | null = null;

  for (const model of models) {
    try {
      const result = await ai.run(model as Parameters<Ai['run']>[0], {
        messages,
        max_tokens: maxTokens,
      } as never);

      // Workers AI returns { response: string } for text-generation
      return (result as { response: string }).response;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      console.warn(`Model ${model} failed: ${lastError.message}. Trying next…`);
    }
  }

  throw lastError ?? new Error('All models failed');
}
```

---

## 4. AI Gateway Retry Configuration (wrangler.toml)

```toml
# wrangler.toml — AI Gateway binding (optional, for direct AI.run routing through gateway)
# Binds your Worker's AI.run calls through the AI Gateway automatically
[ai]
binding = "AI"

# Set the gateway via the Cloudflare dashboard or API:
# Dashboard: Workers & Pages > AI Gateway > your-gateway > Settings
# Enable: "Request retries" — retries 5xx errors up to 3 times with exponential backoff
# Enable: "Fallback providers" — configure per provider in the dashboard
```

---

## 5. Logging Which Provider Was Used

```typescript
// src/gateway.ts (continued)

export async function chatWithFallbackAndLog(
  env: Env,
  userMessage: string,
  requestId: string
): Promise<{ reply: string; provider: string }> {
  const res = await fetch(
    `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.GATEWAY_ID}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildProviders(env, userMessage)),
    }
  );

  // AI Gateway injects which provider was ultimately used in response headers
  const usedProvider = res.headers.get('cf-aig-provider') ?? 'unknown';

  await env.DB.prepare(
    'INSERT INTO inference_log (request_id, provider, status, ts) VALUES (?, ?, ?, ?)'
  )
    .bind(requestId, usedProvider, res.status, Date.now())
    .run();

  const data = await res.json<Record<string, unknown>>();
  return { reply: extractContent(data), provider: usedProvider };
}

function buildProviders(env: Env, userMessage: string) {
  // Returns the providers array (same as section 2 above)
  return [/* ... */];
}
```

---

## Anti-patterns

- **Building client-side retry loops** instead of using AI Gateway's server-side
  fallback — each retry from the client adds latency and burns the Worker's CPU time
  waiting; the gateway handles it without round-tripping the client.
- **Putting expensive models later in the chain** — the point of a fallback chain is
  that cheaper/faster options are tried first; putting GPT-4o as the last fallback
  means you only reach it after exhausting cheaper options, but you pay for the latency
  of the earlier failures.
- **Ignoring response shape differences** across providers — OpenAI and Anthropic have
  different JSON shapes; always normalise before returning to callers.
- **Hard-coding API keys in providers array** — pass them from `env` secrets only;
  never embed literal key strings in Worker source code.

---

## Gotchas

- The `cf-aig-provider` response header is only present when the request goes through
  AI Gateway; direct `ai.run()` calls do not set it.
- Workers AI as a fallback provider in the universal endpoint requires a Cloudflare API
  token with `Workers AI:Run` permission, not your account's global API key.
- AI Gateway's built-in retry configuration (dashboard setting) retries **the same
  provider** on 5xx; the `providers` array fallback is for **different providers**.
  Both mechanisms can be combined.
- The gateway's fallback does **not** catch 400 Bad Request errors (malformed payloads)
  — only 429, 500-series, and timeout failures trigger the cascade.
- Anthropic's response schema nests content differently from OpenAI — always test your
  `extractContent` normaliser against real API responses from each provider.

---

## Verification

```typescript
// Smoke test: force the primary to fail and confirm fallback fires
async function testFallbackChain(env: Env) {
  // Temporarily use an invalid key for the primary provider
  const result = await chatWithFallback(
    { ...env, OPENAI_API_KEY: 'invalid-key' },
    'What is 2 + 2?'
  );

  console.assert(
    result.includes('4') || result.length > 0,
    'Fallback provider must return a valid response'
  );
  console.log('Fallback chain verified. Response:', result.slice(0, 80));
}
```

---

## Related

- `ai-gateway-rate-limiting.md`
- `ai-gateway-logging.md`
- `ai-gateway-universal-endpoint-provider-normalization.md`
- `llm-fallback-provider-rotation.md`
- `llm-retry-patterns.md`

---

## Sources

- AI Gateway universal endpoint docs: https://developers.cloudflare.com/ai-gateway/providers/universal/
- AI Gateway fallback configuration: https://developers.cloudflare.com/ai-gateway/configuration/fallbacks/
- Anthropic messages API reference: https://docs.anthropic.com/en/api/messages
