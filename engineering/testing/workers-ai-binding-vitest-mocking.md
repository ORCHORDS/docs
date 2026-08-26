# Workers AI Binding Mocking in Vitest

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Workers AI (`env.AI.run(...)`) calls a remote model inference endpoint that is unavailable and metered in unit tests. This article covers how to mock the `AI` binding in Vitest with deterministic responses so tests are fast, free, and offline-capable.

## Context
The `env.AI` binding provided by `@cloudflare/workers-types` exposes a `run(model, inputs)` method. In production, Cloudflare routes the call to its GPU fleet. In `@cloudflare/vitest-pool-workers`, the binding is present as a stub that throws unless overridden — this is intentional, since real inference in CI is expensive and non-deterministic. Teams mock the binding with `vi.fn()` or a thin fake class to control output per test.

## Declaring the Binding in Wrangler Config

```toml
# wrangler.toml
[ai]
binding = "AI"
```

```typescript
// src/types.ts
export interface Env {
  AI: Ai; // from @cloudflare/workers-types
}
```

## Creating a Reusable AI Fake

Define a typed fake that covers the most common Workers AI task shapes:

```typescript
// tests/fakes/fake-ai.ts
import type { Ai } from "@cloudflare/workers-types";

type RunInput = Parameters<Ai["run"]>[1];
type RunOutput = ReturnType<Ai["run"]>;

export class FakeAI implements Pick<Ai, "run"> {
  private handlers = new Map<string, (input: RunInput) => unknown>();

  onModel(model: string, handler: (input: RunInput) => unknown): this {
    this.handlers.set(model, handler);
    return this;
  }

  async run(model: string, input: RunInput): RunOutput {
    const handler = this.handlers.get(model);
    if (!handler) throw new Error(`FakeAI: no handler registered for model "${model}"`);
    return handler(input) as Awaited<RunOutput>;
  }
}
```

## Mocking Text Generation

```typescript
// tests/text-generation.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { FakeAI } from "./fakes/fake-ai";
import { summarise } from "../src/summarise";

describe("summarise()", () => {
  let fakeAI: FakeAI;

  beforeEach(() => {
    fakeAI = new FakeAI();
    // Replace the binding for this test run
    vi.spyOn(env, "AI", "get").mockReturnValue(fakeAI as unknown as Ai);
  });

  it("returns the model response verbatim", async () => {
    fakeAI.onModel("@cf/meta/llama-3-8b-instruct", () => ({
      response: "This is a summary.",
    }));

    const result = await summarise(env, "Long article text…");
    expect(result).toBe("This is a summary.");
  });

  it("truncates prompt to 2 048 tokens before sending", async () => {
    let capturedInput: unknown;
    fakeAI.onModel("@cf/meta/llama-3-8b-instruct", (input) => {
      capturedInput = input;
      return { response: "ok" };
    });

    const longText = "word ".repeat(3000);
    await summarise(env, longText);

    const messages = (capturedInput as { messages: { content: string }[] }).messages;
    const totalWords = messages.map((m) => m.content.split(" ").length).reduce((a, b) => a + b, 0);
    expect(totalWords).toBeLessThanOrEqual(2100); // approximate token budget
  });
});
```

## Mocking Embeddings

```typescript
// tests/embeddings.test.ts
import { it, expect, vi, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { FakeAI } from "./fakes/fake-ai";
import { embedDocuments } from "../src/embed";

const FAKE_VECTOR = Array.from({ length: 768 }, (_, i) => i / 768);

beforeEach(() => {
  const fakeAI = new FakeAI().onModel(
    "@cf/baai/bge-base-en-v1.5",
    (input) => ({
      data: (input as { text: string[] }).text.map(() => FAKE_VECTOR),
      shape: [(input as { text: string[] }).text.length, 768],
    })
  );
  vi.spyOn(env, "AI", "get").mockReturnValue(fakeAI as unknown as Ai);
});

it("returns one embedding vector per document", async () => {
  const vectors = await embedDocuments(env, ["doc a", "doc b", "doc c"]);
  expect(vectors).toHaveLength(3);
  vectors.forEach((v) => expect(v).toHaveLength(768));
});
```

## Testing Error Handling Paths

Simulate model unavailability to verify your Worker's fallback logic:

```typescript
// tests/ai-error-handling.test.ts
import { it, expect, vi, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { FakeAI } from "./fakes/fake-ai";
import { classifyWithFallback } from "../src/classify";

beforeEach(() => {
  const fakeAI = new FakeAI().onModel("@cf/huggingface/distilbert-sst2-int8", () => {
    throw new Error("model overloaded");
  });
  vi.spyOn(env, "AI", "get").mockReturnValue(fakeAI as unknown as Ai);
});

it("returns neutral classification when model throws", async () => {
  const label = await classifyWithFallback(env, "some text");
  expect(label).toBe("neutral");
});
```

## Testing Streaming Text Responses

Workers AI can return a `ReadableStream` for streaming inference. Fake the stream with a known sequence:

```typescript
// tests/streaming.test.ts
import { it, expect, vi } from "vitest";
import { env } from "cloudflare:test";
import { FakeAI } from "./fakes/fake-ai";
import { streamSummary } from "../src/stream-summary";

it("streams tokens from the model", async () => {
  const tokens = ["Hello", " world", "!"];
  const fakeAI = new FakeAI().onModel("@cf/meta/llama-3-8b-instruct", () => {
    const encoder = new TextEncoder();
    return new ReadableStream<Uint8Array>({
      start(controller) {
        for (const token of tokens) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ response: token })}\n\n`));
        }
        controller.close();
      },
    });
  });
  vi.spyOn(env, "AI", "get").mockReturnValue(fakeAI as unknown as Ai);

  const collected: string[] = [];
  const stream = await streamSummary(env, "summarise this");
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    collected.push(decoder.decode(value));
  }
  expect(collected.join("")).toContain("Hello");
});
```

## Anti-patterns
- Do not call `env.AI.run()` directly in tests without mocking — it will either throw or make a real network call depending on the runtime environment.
- Do not hardcode model names as plain strings scattered across tests; centralise them in a `models.ts` constant file so name changes propagate automatically.
- Avoid asserting exact AI output in integration tests against production models — responses are non-deterministic.

## Gotchas
- `vi.spyOn(env, "AI", "get")` works only when `env` is a plain object; if Miniflare wraps it in a Proxy, use `Object.defineProperty` instead.
- The `FakeAI` above does not implement every method on `Ai` (e.g. `gateway`, `fetch`) — extend it as needed or cast with `as unknown as Ai`.
- Workers AI streaming returns Server-Sent Events format; your fake must match this encoding for downstream SSE parsers to work correctly.
- Miniflare 3 may expose a real (but offline-erroring) `AI` binding — check `vitest-pool-workers` release notes for per-version behavior.

## Verification
`npx vitest run tests/text-generation.test.ts tests/embeddings.test.ts` — all tests should run offline in under a second. Use `--reporter=verbose` to confirm the fake is invoked and not the real binding.

## Related
- [vitest-cloudflare-pool-workers.md](vitest-cloudflare-pool-workers.md)
- [test-doubles-cloudflare-workers.md](test-doubles-cloudflare-workers.md)
- [workers-unit-testing-fetch-mocking.md](workers-unit-testing-fetch-mocking.md)
- [vitest-custom-matchers-workers-environment.md](vitest-custom-matchers-workers-environment.md)

## Sources
- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/workers-ai/models/
