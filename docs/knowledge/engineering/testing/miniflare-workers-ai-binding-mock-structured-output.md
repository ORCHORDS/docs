# Miniflare Workers AI Binding Mock Structured Output

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker calls `env.AI.run()` to generate structured JSON from a language model (e.g., `@cf/meta/llama-3.1-8b-instruct` with `response_format: { type: "json_object" }`). Unit tests that hit the real Workers AI binding are slow (network round-trips), non-deterministic (model output varies), and consume inference quota in CI. You need a Miniflare-compatible mock for `env.AI` that returns deterministic structured output so you can test your Worker's JSON-parsing logic, error handling, and downstream data transformations reliably.

## Context

Workers AI is exposed as an `Ai` binding with a single `run()` method. Its TypeScript interface (from `@cloudflare/workers-types`) is:

```typescript
interface Ai {
  run<M extends keyof AiModels>(
    model: M,
    inputs: AiModels[M]["inputs"],
    options?: AiOptions
  ): Promise<AiModels[M]["outputs"]>;
}
```

Miniflare 3.x does not ship a built-in Workers AI simulation — it has no local model inference engine. The correct approach is to inject a mock implementation via Miniflare's `serviceBindings` or by replacing the binding with a custom class in the `bindings` option. This article covers both patterns and shows how to test structured-output parsing, retry-on-malformed-JSON, and tool-call payloads.

## 1. Defining the Worker

```typescript
// src/worker.ts
export interface Env {
  AI: Ai;
}

export interface ExtractedEvent {
  title: string;
  date: string;       // ISO 8601
  location: string;
  attendees: string[];
}

export interface ExtractionResult {
  events: ExtractedEvent[];
  confidence: number; // 0–1
}

const SYSTEM_PROMPT = `You are an event extractor. Given text, return a JSON object
matching the schema: { events: [{title, date, location, attendees[]}], confidence }.
Respond ONLY with valid JSON.`;

export async function extractEvents(
  env: Env,
  text: string
): Promise<ExtractionResult> {
  const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: text },
    ],
    response_format: { type: "json_object" },
    max_tokens: 512,
  });

  // The model may return { response: "..." } wrapping the JSON string
  const raw =
    typeof response === "string" ? response : (response as { response: string }).response;

  let parsed: ExtractionResult;
  try {
    parsed = JSON.parse(raw) as ExtractionResult;
  } catch {
    throw new Error(`AI returned non-JSON output: ${raw.slice(0, 200)}`);
  }

  if (!Array.isArray(parsed.events)) {
    throw new Error("AI response missing `events` array");
  }

  return parsed;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { text } = await req.json<{ text: string }>();
    const result = await extractEvents(env, text);
    return Response.json(result);
  },
};
```

## 2. Miniflare Mock: Simple Binding Object

```typescript
// test/helpers/ai-mock.ts
import type { AiModels } from "@cloudflare/workers-types";

export type AiRunFn = <M extends keyof AiModels>(
  model: M,
  inputs: AiModels[M]["inputs"]
) => Promise<AiModels[M]["outputs"]>;

export function createAiMock(responses: Map<string, unknown>): { run: AiRunFn } {
  return {
    run: async (model, _inputs) => {
      const fixture = responses.get(model);
      if (fixture === undefined) {
        throw new Error(`AI mock: no fixture for model "${model}"`);
      }
      // Workers AI wraps text output in { response: string }
      return { response: typeof fixture === "string" ? fixture : JSON.stringify(fixture) } as AiModels[typeof model]["outputs"];
    },
  };
}
```

## 3. Driving extractEvents Directly (Unit-Level)

```typescript
// test/extract-events.unit.test.ts
import { describe, it, expect } from "vitest";
import { extractEvents } from "../src/worker";
import { createAiMock } from "./helpers/ai-mock";

describe("extractEvents", () => {
  it("parses well-formed structured output", async () => {
    const fixture = {
      events: [
        {
          title: "Q3 Planning",
          date: "2026-09-01",
          location: "Berlin HQ",
          attendees: ["alice@example.com", "bob@example.com"],
        },
      ],
      confidence: 0.92,
    };

    const ai = createAiMock(new Map([["@cf/meta/llama-3.1-8b-instruct", fixture]]));
    const result = await extractEvents({ AI: ai as Ai }, "Schedule the Q3 planning meeting…");

    expect(result.events).toHaveLength(1);
    expect(result.events[0].title).toBe("Q3 Planning");
    expect(result.confidence).toBeGreaterThan(0.5);
  });

  it("throws when AI returns non-JSON", async () => {
    const ai = createAiMock(new Map([["@cf/meta/llama-3.1-8b-instruct", "Sure, here you go!"]]));

    await expect(
      extractEvents({ AI: ai as Ai }, "any text")
    ).rejects.toThrow("AI returned non-JSON output");
  });

  it("throws when events array is absent", async () => {
    const ai = createAiMock(
      new Map([["@cf/meta/llama-3.1-8b-instruct", { confidence: 0.8 }]])
    );

    await expect(
      extractEvents({ AI: ai as Ai }, "any text")
    ).rejects.toThrow("AI response missing `events` array");
  });

  it("handles empty events list gracefully", async () => {
    const ai = createAiMock(
      new Map([["@cf/meta/llama-3.1-8b-instruct", { events: [], confidence: 0.1 }]])
    );
    const result = await extractEvents({ AI: ai as Ai }, "no events here");
    expect(result.events).toEqual([]);
  });
});
```

## 4. Integration Test via Miniflare with Injected Binding

```typescript
// test/extract-events.integration.test.ts
import { Miniflare } from "miniflare";
import { describe, it, beforeEach, afterEach, expect } from "vitest";

let mf: Miniflare;

beforeEach(async () => {
  mf = new Miniflare({
    scriptPath: "./dist/worker.js",
    modules: true,
    // Inject the AI binding as a plain object via `serviceBindings` shim.
    // Miniflare allows arbitrary objects in bindings for Worker-level testing.
    bindings: {
      // Serialised fixture — the Worker receives this via env.AI
      __AI_FIXTURE__: JSON.stringify({
        events: [
          { title: "Board Meeting", date: "2026-10-01", location: "NYC", attendees: [] },
        ],
        confidence: 0.88,
      }),
    },
    // Wrap the real Worker in a shim that replaces env.AI with a mock
    // by pre-processing the bindings. Alternatively, use the approach below.
    compatibilityFlags: ["nodejs_compat"],
  });
  await mf.ready;
});

afterEach(() => mf.dispose());
```

> Note: Because Miniflare doesn't natively support the `Ai` class, the cleanest integration approach is to build a small shim Worker entry-point for tests:

```typescript
// src/worker.test-shim.ts  (built separately for test builds)
import worker, { extractEvents } from "./worker";

export default {
  async fetch(req: Request, env: { __AI_FIXTURE__: string } & Omit<Env, "AI">): Promise<Response> {
    const fixture = JSON.parse(env.__AI_FIXTURE__);
    const mockAI = {
      run: async () => ({ response: JSON.stringify(fixture) }),
    } as unknown as Ai;
    return worker.fetch(req, { ...env, AI: mockAI });
  },
};
```

## 5. Model-Routing Test: Multiple Models

```typescript
// test/model-routing.test.ts
import { describe, it, expect, vi } from "vitest";
import { extractEvents } from "../src/worker";

it("selects the correct model based on input length", async () => {
  const runSpy = vi.fn().mockResolvedValue({
    response: JSON.stringify({ events: [], confidence: 0 }),
  });
  const ai = { run: runSpy } as unknown as Ai;

  const longText = "x".repeat(10_000);
  await extractEvents({ AI: ai }, longText);

  // Assert the Worker chose the large-context model for long inputs
  expect(runSpy).toHaveBeenCalledWith(
    "@cf/meta/llama-3.1-70b-instruct",
    expect.objectContaining({ messages: expect.any(Array) }),
    expect.anything()
  );
});
```

## 6. Structured Output Schema Validation in Tests

```typescript
// test/output-schema.test.ts
import { describe, it, expect } from "vitest";
import Ajv from "ajv";
import addFormats from "ajv-formats";
import { extractEvents } from "../src/worker";
import { createAiMock } from "./helpers/ai-mock";

const ajv = new Ajv({ allErrors: true });
addFormats(ajv);

const RESULT_SCHEMA = {
  type: "object",
  required: ["events", "confidence"],
  properties: {
    events: {
      type: "array",
      items: {
        type: "object",
        required: ["title", "date", "location", "attendees"],
        properties: {
          title: { type: "string", minLength: 1 },
          date: { type: "string", format: "date" },
          location: { type: "string" },
          attendees: { type: "array", items: { type: "string", format: "email" } },
        },
      },
    },
    confidence: { type: "number", minimum: 0, maximum: 1 },
  },
};

const validate = ajv.compile(RESULT_SCHEMA);

describe("structured output schema", () => {
  it("validates that extracted output matches declared schema", async () => {
    const ai = createAiMock(
      new Map([
        [
          "@cf/meta/llama-3.1-8b-instruct",
          {
            events: [
              {
                title: "Kickoff",
                date: "2026-11-01",
                location: "Remote",
                attendees: ["charlie@example.com"],
              },
            ],
            confidence: 0.75,
          },
        ],
      ])
    );
    const result = await extractEvents({ AI: ai as Ai }, "Kickoff meeting…");
    const valid = validate(result);
    expect(valid, JSON.stringify(validate.errors)).toBe(true);
  });
});
```

## Anti-patterns

- **Hitting the real Workers AI in CI**: Non-deterministic, slow (400–2000 ms per call), and burns inference quota with every test run.
- **Mocking `env.AI.run` at the module level with `vi.mock`**: This works for Vitest unit tests but doesn't exercise Miniflare's binding injection path; the integration path is untested.
- **Assuming `response` is always a plain string**: Some models return structured objects directly (e.g., embedding models return `{ shape, data }`). Type-check the response before JSON.parse.
- **Not testing the malformed-JSON error path**: Production models occasionally produce truncated output; your Worker must handle that gracefully.
- **Using `any` for mock AI type**: Cast through `unknown` to catch interface mismatches at compile time (`{ run: runSpy } as unknown as Ai`).

## Gotchas

- `@cloudflare/workers-types` types for `AiModels` are periodically updated when new models are released. Pin the version in `package.json` and update intentionally.
- Workers AI `response_format: { type: "json_object" }` does NOT guarantee a JSON response from every model — only models that explicitly support it. Your Worker should always try/catch `JSON.parse`.
- Miniflare's `bindings` option accepts only serialisable values (strings, numbers, booleans) for KV/D1/R2-style bindings. For arbitrary objects, inject via the shim pattern shown in section 4, not via `bindings`.
- The `max_tokens` limit applies to the model's output window. Structured output for large schemas may be truncated; test with fixtures that are near the limit.

## Verification

```bash
# Unit tests — no Miniflare needed
npx vitest run test/extract-events.unit.test.ts test/output-schema.test.ts --reporter=verbose

# Integration test with Miniflare shim
npx wrangler build --entry src/worker.test-shim.ts --dry-run --outdir dist
npx vitest run test/extract-events.integration.test.ts --reporter=verbose
```

## Related

- `workers-ai-binding-vitest-mocking.md` — Vitest pool workers approach to AI binding mocks
- `vitest-workers-ai-gateway-mock-testing.md` — mocking the AI Gateway proxy layer
- `llm-evaluation-testing.md` — evaluating output quality, not just structure

## Sources

- Workers AI binding reference: https://developers.cloudflare.com/workers-ai/get-started/workers-binding/
- Workers AI structured output: https://developers.cloudflare.com/workers-ai/features/structured-outputs/
- Miniflare programmatic API: https://miniflare.dev/get-started/programmatic
