# Workers AI Binding Local Mock Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker calls `env.AI.run('@cf/meta/llama-3.1-8b-instruct', { messages })` and you want to run unit and integration tests locally without hitting the real Workers AI inference endpoint, without burning AI usage credits, and without network access in CI. Vitest with Miniflare supports mocking most bindings natively, but the AI binding (`Ai`) has no built-in local emulator and requires a deliberate mock strategy.

## Context

The Workers AI binding (`Ai`) is a Cloudflare-proprietary runtime binding that proxies inference calls to Cloudflare's GPU fleet. In local development (`wrangler dev`), it can be proxied to the real endpoint with `--remote`, but that requires authentication and incurs latency and cost. For fast, deterministic unit tests the right approach is to inject a typed mock at the test layer. Miniflare v3/v4 exposes a `serviceBindings` override mechanism; for the AI binding specifically, a hand-crafted mock object that satisfies the `Ai` interface is injected into the vitest environment.

## 1. The Ai Interface Shape

The `@cloudflare/workers-types` package declares `Ai` as a callable interface:

```typescript
// What we need to satisfy in tests
interface AiRunResult {
  response?: string
  choices?: Array<{ message: { content: string } }>
  data?: number[][]   // for embeddings
}

interface MockAi {
  run(
    model: string,
    inputs: Record<string, unknown>,
    options?: { gateway?: { id: string } }
  ): Promise<AiRunResult | ReadableStream>
}
```

A simple factory function produces deterministic mock responses keyed by model:

```typescript
// test/mocks/ai.ts
import type { Ai } from '@cloudflare/workers-types'

type ModelName = Parameters<Ai['run']>[0]

export function createMockAi(
  responses: Partial<Record<string, unknown>> = {}
): Ai {
  return {
    async run(model: ModelName, inputs: Record<string, unknown>) {
      const preset = responses[model]
      if (preset !== undefined) {
        return preset as ReturnType<Ai['run']>
      }
      // Default stub by model category
      if (model.includes('embed')) {
        return { data: [[0.1, 0.2, 0.3]] } as ReturnType<Ai['run']>
      }
      return {
        response: `[mock response for ${model}]`,
      } as ReturnType<Ai['run']>
    },
  } as unknown as Ai
}
```

## 2. Injecting the Mock via Miniflare in vitest

Configure `vitest.config.ts` to inject the mock AI binding into every test Worker:

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config'
import { createMockAi } from './test/mocks/ai'

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        miniflare: {
          // Inject the mock directly as an object binding
          // The AI binding name must match wrangler.toml `binding = "AI"`
          bindings: {
            // Non-standard: pass a JS object as a binding mock
          },
          // Use serviceBindings to override AI calls
          serviceBindings: {
            // Not applicable for AI — use the env override below
          },
        },
        wranglerConfigPath: './wrangler.toml',
        // Override environment bindings for tests
        overrides: {
          AI: createMockAi({
            '@cf/meta/llama-3.1-8b-instruct': {
              response: 'The answer is 42.',
            },
            '@cf/baai/bge-small-en-v1.5': {
              data: [[0.12, 0.87, 0.34, 0.56]],
            },
          }),
        },
      },
    },
  },
})
```

When Miniflare's `overrides` is unavailable (older versions), inject via `SELF.fetch` wrapping — see section 4.

## 3. Unit Testing AI-Dependent Handlers

Write tests that assert on the mock's deterministic output:

```typescript
// workers/api/src/ai-handler.test.ts
import { env, SELF } from 'cloudflare:test'
import { describe, it, expect, vi } from 'vitest'

describe('POST /summarize', () => {
  it('returns AI summary for given text', async () => {
    const res = await SELF.fetch('http://localhost/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: 'Hello world this is a long document.' }),
    })

    expect(res.status).toBe(200)
    const body = await res.json<{ summary: string }>()
    // Mock returns "The answer is 42." — assert the handler wraps it correctly
    expect(body.summary).toBe('The answer is 42.')
  })

  it('handles model error gracefully', async () => {
    // Temporarily override the mock to throw
    vi.spyOn(env.AI, 'run').mockRejectedValueOnce(new Error('Model overloaded'))

    const res = await SELF.fetch('http://localhost/summarize', {
      method: 'POST',
      body: JSON.stringify({ text: 'test' }),
    })
    expect(res.status).toBe(503)
  })
})
```

## 4. Fallback: Wrapping fetch for Environments Without Miniflare Overrides

When running tests outside the Workers pool (e.g., pure Node.js unit tests), inject the mock as a constructor argument:

```typescript
// workers/api/src/summarize.ts
export async function summarize(
  text: string,
  ai: Pick<Ai, 'run'>
): Promise<string> {
  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [{ role: 'user', content: `Summarize: ${text}` }],
  })
  return (result as { response: string }).response
}
```

```typescript
// Pure vitest (no Workers pool) test
import { describe, it, expect } from 'vitest'
import { summarize } from './summarize'
import { createMockAi } from '../../test/mocks/ai'

describe('summarize()', () => {
  it('delegates to AI binding', async () => {
    const ai = createMockAi({ '@cf/meta/llama-3.1-8b-instruct': { response: 'Short.' } })
    const result = await summarize('Long text...', ai)
    expect(result).toBe('Short.')
  })
})
```

This decoupled design keeps business logic testable without any Cloudflare runtime dependency.

## 5. Streaming Response Mocking

Workers AI supports streaming text generation. Mock a `ReadableStream` for streaming tests:

```typescript
// test/mocks/ai.ts (streaming variant)
export function createStreamingMockAi(chunks: string[]): Ai {
  return {
    async run(_model: string, _inputs: unknown) {
      const encoder = new TextEncoder()
      return new ReadableStream({
        start(controller) {
          for (const chunk of chunks) {
            controller.enqueue(
              encoder.encode(
                `data: ${JSON.stringify({ response: chunk })}\n\n`
              )
            )
          }
          controller.close()
        },
      })
    },
  } as unknown as Ai
}
```

```typescript
it('streams response tokens', async () => {
  const streamAi = createStreamingMockAi(['Hello', ' world', '!'])
  const result = await streamAi.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [{ role: 'user', content: 'Hi' }],
    stream: true,
  })
  expect(result).toBeInstanceOf(ReadableStream)
})
```

## Anti-patterns

- **Using `wrangler dev --remote` in CI for AI tests.** This is slow (cold start + inference latency), costs money, and fails without credentials. Always mock AI in CI.
- **Mocking at the `fetch` level with `msw`.** The AI binding is not HTTP-based in the Workers runtime — MSW intercepts outbound `fetch` calls, not binding invocations. Mock the `Ai` object directly.
- **Returning `any` from the mock.** Type the mock as `Ai` (using `as unknown as Ai`) to catch interface drift when `@cloudflare/workers-types` updates the `Ai` type.
- **Sharing a single mock instance across tests.** Use a factory function so each test gets a fresh mock; shared state between tests causes flaky results.

## Gotchas

- The `Ai` interface in `@cloudflare/workers-types` is versioned. After a `workers-types` upgrade, check that the `run` signature (especially the model name union type) still matches your mock.
- Workers AI streaming uses Server-Sent Events format (`data: {...}\n\n`), not newline-delimited JSON. Ensure streaming mocks replicate the SSE framing if the handler parses it.
- `vi.spyOn(env.AI, 'run')` only works if the binding is exposed as a plain object (which the Workers test pool does). Service bindings and native Cloudflare proxy objects may not be spyable.
- Gateway configuration (`options.gateway`) is ignored by the mock but must not throw — ensure the mock accepts and discards the third argument.

## Verification

```bash
# Run AI-related tests with the mock (no network)
pnpm --filter @example project/api vitest run --reporter verbose src/ai-handler.test.ts

# Confirm no real AI calls escape to the network in CI
# Set env var to block outbound in test:
WORKERS_AI_GATEWAY="" pnpm --filter @example project/api vitest run

# Type-check the mock against the real Ai interface
pnpm --filter @example project/api tsc --noEmit
```

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `vitest-workers-environment-custom-fetch-mock.md`
- `miniflare-storage-backend-testing.md`
- `wrangler-dev-local-mocking.md`
- `msw-external-api-mocking-workers-tests.md`

## Sources

- https://developers.cloudflare.com/workers-ai/configuration/bindings/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://developers.cloudflare.com/workers-ai/models/
