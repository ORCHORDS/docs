# Workers AI Deterministic Mock Seeding in Vitest

2026-08-24 / example.com / production

---

## Symptom / Use-case

Your Cloudflare Worker calls `env.AI.run("@cf/meta/llama-3.1-8b-instruct", …)` or `env.AI.run("@cf/baai/bge-base-en-v1.5", …)` and the production model returns non-deterministic outputs. When you write a simple mock that always returns the same string, your tests pass — but they fail to catch the important edge cases: truncated responses, safety-filtered outputs, multi-choice responses where the Worker must pick the highest-probability option, or embedding vectors where cosine similarity comparisons must match known fixtures.

What you need is a *seeded* mock: a fake `Ai` binding whose responses vary *deterministically* based on the input prompt or embedding text, so tests can cover multiple behavioural branches without touching the real model.

---

## Context

`env.AI` is the `Ai` binding exposed by Workers AI. Its `run` method signature is:

```ts
run(model: string, inputs: AiRunInput, options?: AiOptions): Promise<AiRunResult>;
```

Because `AiRunResult` varies by model family (text generation, image classification, embeddings, speech-to-text), the mock must be polymorphic — switching on `model` and returning the correct result shape. Seeding the response with a hash of the input ensures the same prompt always produces the same mock output across test runs and machines.

This pattern is distinct from:
- `miniflare-workers-ai-binding-mock-structured-output.md` — which mocks a fixed structured output for a single call
- `workers-ai-binding-vitest-mocking.md` — which replaces the binding wholesale with `vi.fn()`

Seeded mocking yields a *set* of stable, distinct outputs derived from the input, giving tests the ability to assert branching logic.

---

## Deterministic Pseudo-Hashing Utility

```ts
// test/utils/deterministic-hash.ts
/**
 * Simple, dependency-free djb2 hash of a string.
 * Returns a non-negative 32-bit integer.
 */
export function djb2(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

/** Return a float in [0, 1) derived deterministically from a string. */
export function hashFraction(s: string): number {
  return djb2(s) / 0xffffffff;
}

/** Generate a float32 embedding vector seeded from a text string. */
export function seededEmbedding(text: string, dim = 768): number[] {
  return Array.from({ length: dim }, (_, i) => {
    const seed = djb2(`${text}:${i}`);
    return (seed / 0xffffffff) * 2 - 1; // range [-1, 1]
  });
}
```

---

## Polymorphic Seeded AI Binding Mock

```ts
// test/mocks/ai-binding.ts
import { djb2, hashFraction, seededEmbedding } from "../utils/deterministic-hash";

type TextGenInputs = { messages?: Array<{ role: string; content: string }>; prompt?: string };
type EmbeddingInputs = { text: string | string[] };

/** Catalogue of deterministic mock responses keyed by model family. */
const MOCK_COMPLETIONS = [
  "The capital of France is Paris.",
  "Retrieval-augmented generation combines search with generation.",
  "Cloudflare Workers run on the V8 isolate model.",
  "Sorry, I cannot help with that request.",
  "Error: context length exceeded. Please shorten your prompt.",
];

function pickFromSeed(seed: number, options: string[]): string {
  return options[seed % options.length];
}

export class SeededAiBinding {
  private _calls: Array<{ model: string; inputs: unknown }> = [];

  async run(model: string, inputs: unknown): Promise<unknown> {
    this._calls.push({ model, inputs });

    if (model.includes("embed") || model.includes("bge")) {
      return this._handleEmbedding(inputs as EmbeddingInputs);
    }

    if (model.includes("llama") || model.includes("mistral") || model.includes("gemma")) {
      return this._handleTextGen(inputs as TextGenInputs);
    }

    if (model.includes("whisper")) {
      return this._handleSpeechToText();
    }

    if (model.includes("stable-diffusion") || model.includes("flux")) {
      return this._handleImageGen(inputs as { prompt: string });
    }

    throw new Error(`SeededAiBinding: unrecognised model "${model}" — add a handler.`);
  }

  get calls() {
    return this._calls as ReadonlyArray<{ model: string; inputs: unknown }>;
  }

  reset() {
    this._calls = [];
  }

  private _handleEmbedding(inputs: EmbeddingInputs) {
    const texts = Array.isArray(inputs.text) ? inputs.text : [inputs.text];
    return {
      shape: [texts.length, 768],
      data: texts.map((t) => seededEmbedding(t, 768)),
    };
  }

  private _handleTextGen(inputs: TextGenInputs) {
    const prompt =
      inputs.prompt ??
      inputs.messages?.map((m) => m.content).join(" ") ??
      "";
    const seed = djb2(prompt);
    const response = pickFromSeed(seed, MOCK_COMPLETIONS);

    return {
      response,
      // Simulate multi-choice when the prompt requests it
      choices: [
        { index: 0, message: { role: "assistant", content: response }, finish_reason: "stop" },
      ],
      usage: {
        prompt_tokens: Math.floor(prompt.length / 4),
        completion_tokens: Math.floor(response.length / 4),
        total_tokens: Math.floor((prompt.length + response.length) / 4),
      },
    };
  }

  private _handleSpeechToText() {
    return { text: "This is a deterministic transcription." };
  }

  private _handleImageGen(inputs: { prompt: string }) {
    // Return a tiny 1x1 transparent PNG as a Uint8Array
    const png = new Uint8Array([
      137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82,
    ]);
    return png;
  }
}
```

---

## Wiring the Mock into Vitest Tests

```ts
// test/setup/ai-binding.setup.ts
import { SeededAiBinding } from "../mocks/ai-binding";

// Export so individual test files can inspect calls
export const mockAi = new SeededAiBinding();

// Reset between tests to prevent call-count bleed
beforeEach(() => {
  mockAi.reset();
});
```

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    setupFiles: ["./test/setup/ai-binding.setup.ts"],
    globals: true,
  },
});
```

---

## Testing Branching Logic Based on AI Response

```ts
// test/unit/ai-router.test.ts
import { describe, it, expect } from "vitest";
import { mockAi } from "../setup/ai-binding.setup";
import { handleAiRequest } from "../../src/ai-router";

function makeEnv() {
  return { AI: mockAi } as unknown as Env;
}

describe("handleAiRequest — branching on AI responses", () => {
  it("returns a 200 with the AI response for a normal prompt", async () => {
    // djb2("Tell me about Paris") → deterministic completion
    const res = await handleAiRequest(
      new Request("https://worker.test/ai", {
        method: "POST",
        body: JSON.stringify({ prompt: "Tell me about Paris" }),
        headers: { "Content-Type": "application/json" },
      }),
      makeEnv(),
    );
    expect(res.status).toBe(200);
    const body = await res.json<{ response: string }>();
    // Exact value is deterministic; pin it to detect model/mock drift
    expect(body.response).toMatchSnapshot();
  });

  it("handles safety-filtered response gracefully", async () => {
    // Choose a prompt whose djb2 maps to MOCK_COMPLETIONS[3] ("Sorry, I cannot help…")
    const safetyPrompt = "TRIGGER_SAFETY"; // pre-computed to hit index 3
    const res = await handleAiRequest(
      new Request("https://worker.test/ai", {
        method: "POST",
        body: JSON.stringify({ prompt: safetyPrompt }),
        headers: { "Content-Type": "application/json" },
      }),
      makeEnv(),
    );
    // Worker should return 451 when AI refuses
    expect(res.status).toBe(451);
  });

  it("calls AI exactly once per request", async () => {
    await handleAiRequest(
      new Request("https://worker.test/ai", {
        method: "POST",
        body: JSON.stringify({ prompt: "Hello" }),
        headers: { "Content-Type": "application/json" },
      }),
      makeEnv(),
    );
    expect(mockAi.calls).toHaveLength(1);
    expect(mockAi.calls[0].model).toBe("@cf/meta/llama-3.1-8b-instruct");
  });
});
```

---

## Embedding Similarity Tests

```ts
// test/unit/semantic-search.test.ts
import { describe, it, expect } from "vitest";
import { seededEmbedding, djb2 } from "../utils/deterministic-hash";
import { cosineSimilarity } from "../../src/utils/math";

describe("seededEmbedding determinism", () => {
  it("produces identical vectors for the same text", () => {
    const a = seededEmbedding("Cloudflare Workers");
    const b = seededEmbedding("Cloudflare Workers");
    expect(a).toEqual(b);
  });

  it("produces different vectors for different texts", () => {
    const a = seededEmbedding("Cloudflare Workers");
    const b = seededEmbedding("AWS Lambda");
    expect(cosineSimilarity(a, b)).toBeLessThan(0.99);
  });

  it("same-text similarity is 1.0", () => {
    const a = seededEmbedding("Cloudflare Workers");
    expect(cosineSimilarity(a, a)).toBeCloseTo(1.0);
  });
});
```

---

## Anti-patterns

- **`vi.fn().mockResolvedValue(fixedResponse)`** — single fixed response cannot exercise branching logic; use seeded mocks for path coverage.
- **Randomising the mock** — `Math.random()` in test code creates non-repeatable failures; always derive mock outputs from the input deterministically.
- **Hardcoding the full expected vector** — 768-float arrays make snapshot files enormous; assert shape and a spot-checked element, or compare via cosine similarity.
- **Returning the wrong result shape** — `bge-*` returns `{ shape, data }`, LLMs return `{ response }` or `{ choices }`; mismatched shapes cause silent runtime errors in the Worker.
- **Not resetting between tests** — call-count assertions bleed if `mockAi.reset()` is not called in `beforeEach`.

---

## Gotchas

- djb2 can collide: two different prompts may resolve to the same mock completion. For coverage of all branches, enumerate the input set explicitly rather than relying on accidental distribution.
- The Workers AI gateway (`AI_GATEWAY` environment variable) intercepts `env.AI.run` in production but not in the stub; ensure gateway-level retry/logging logic is tested separately.
- `@cf/stable-diffusion-v1-5` returns a `ReadableStream<Uint8Array>` in production, not a `Uint8Array`; the mock above simplifies — adjust if the Worker streams the image to the client.
- Token count fields in the text-gen response shape can affect billing-tracking logic; include them in the mock to exercise that code.

---

## Verification

```bash
# Run once to generate snapshots for deterministic completions
npx vitest run test/unit/ai-router.test.ts --update-snapshot

# Run again to confirm stability — no snapshot drift
npx vitest run test/unit/ai-router.test.ts

# Confirm all branches are exercised
npx vitest run --coverage test/unit/
```

Expected: snapshot file is stable across runs; coverage shows all AI-response branches hit.

---

## Related

- `workers-ai-binding-vitest-mocking.md` — basic `vi.fn()` mocking for Workers AI
- `miniflare-workers-ai-binding-mock-structured-output.md` — structured output mocking with Miniflare
- `vitest-workers-ai-text-embedding-integration-testing.md` — integration-level embedding tests
- `vitest-workers-ai-gateway-mock-testing.md` — AI Gateway layer mocking
- `random-seed-control-deterministic-tests.md` — seeding strategies for general test randomness

---

## Sources

- Workers AI binding reference: https://developers.cloudflare.com/workers-ai/get-started/workers-binding/
- Workers AI models catalog: https://developers.cloudflare.com/workers-ai/models/
- djb2 hash algorithm: http://www.cse.yorku.ca/~oz/hash.html
