# Workers AI: Structured Output and Tool Calling

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need deterministic, schema-validated JSON from a Workers AI model — no free-text parsing,
no ad-hoc regex extraction. You also want the model to invoke predefined functions as part of
a reasoning chain without leaving the Cloudflare edge. Standard `ai.run()` calls return
unstructured strings; parsing them is fragile and breaks on edge cases.

## Context

Workers AI exposes `@cf/meta/llama-3.3-70b-instruct` and compatible models via the `AI`
binding. Two complementary capabilities ship in 2025–2026:

- **Structured output** (`response_format: { type: "json_schema", json_schema: { … } }`) —
  constrained decoding masks invalid tokens so the model can only emit JSON that matches your
  schema. `strict: true` is required to activate enforcement.
- **Tool calling** (`tools: […]`) — when the model decides a function call is needed it emits
  a `tool_calls` array instead of text. You execute the function and feed the result back;
  the model then produces the final answer.

Both features are model-specific. As of 2026-08, `llama-3.3-70b-instruct`,
`mistral-7b-instruct-v0.2`, and `qwen2.5-72b-instruct` support them. Check the
[model catalog](https://developers.cloudflare.com/workers-ai/models/) for the
`function_calling` and `json_output` capability tags before relying on either.

CPU budget is 30 s on Unbound Workers; deep tool-call chains eat this fast. Cap loops at
3 hops, or hand off to Workflows for longer orchestrations.

## Structured Output with JSON Schema

```typescript
// src/structured.ts
import type { Ai } from "@cloudflare/workers-types";

interface Env { AI: Ai; }

const productSchema = {
  type: "object" as const,
  properties: {
    name:    { type: "string" },
    price:   { type: "number" },
    inStock: { type: "boolean" },
    tags:    { type: "array", items: { type: "string" } },
  },
  required: ["name", "price", "inStock", "tags"],
  additionalProperties: false,
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { description } = await req.json<{ description: string }>();

    const result = await env.AI.run("@cf/meta/llama-3.3-70b-instruct", {
      messages: [
        { role: "system", content: "Extract product details from the user text." },
        { role: "user",   content: description },
      ],
      response_format: {
        type: "json_schema",
        json_schema: {
          name:   "product",
          strict: true,         // required — disabling silently drops enforcement
          schema: productSchema,
        },
      },
      max_tokens: 512,
    });

    // result.response is a JSON string guaranteed to satisfy productSchema
    const product = JSON.parse(result.response as string);
    return Response.json(product);
  },
};
```

## Tool Calling — Single Hop

```typescript
// src/tool-single.ts
import type { Ai, AiTextGenerationInput } from "@cloudflare/workers-types";

interface Env { AI: Ai; }

const tools: AiTextGenerationInput["tools"] = [
  {
    type: "function",
    function: {
      name: "get_weather",
      description: "Return current weather for a city.",
      parameters: {
        type: "object",
        properties: {
          city:  { type: "string", description: "City name" },
          units: { type: "string", enum: ["celsius", "fahrenheit"] },
        },
        required: ["city"],
      },
    },
  },
];

async function run(env: Env, userMessage: string): Promise<string> {
  const messages: AiTextGenerationInput["messages"] = [
    { role: "user", content: userMessage },
  ];

  const first = await env.AI.run("@cf/meta/llama-3.3-70b-instruct", {
    messages, tools, max_tokens: 512,
  });

  if (!first.tool_calls?.length) {
    // Model answered directly — no function required
    return first.response as string;
  }

  const call = first.tool_calls[0];
  const args = JSON.parse(call.function.arguments) as { city: string; units?: string };
  const weather = await fetchWeather(args.city, args.units ?? "celsius");

  // Provide tool result and get the final answer
  messages.push({ role: "assistant", content: null, tool_calls: first.tool_calls });
  messages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(weather) });

  const second = await env.AI.run("@cf/meta/llama-3.3-70b-instruct", {
    messages, max_tokens: 512,
  });

  return second.response as string;
}

async function fetchWeather(city: string, units: string) {
  // Replace with a real upstream call or KV cache
  return { city, temp: 22, units, condition: "partly cloudy" };
}
```

## Multi-Tool Loop with Depth Guard

```typescript
// src/tool-loop.ts
import type { Ai, AiTextGenerationInput } from "@cloudflare/workers-types";

const MAX_HOPS = 3;

type ToolHandler = (args: Record<string, unknown>) => Promise<unknown>;

async function toolLoop(
  ai: Ai,
  messages: AiTextGenerationInput["messages"],
  tools: AiTextGenerationInput["tools"],
  handlers: Record<string, ToolHandler>,
): Promise<string> {
  for (let hop = 0; hop < MAX_HOPS; hop++) {
    const res = await ai.run("@cf/meta/llama-3.3-70b-instruct", {
      messages, tools, max_tokens: 1024,
    });

    if (!res.tool_calls?.length) {
      return res.response as string;
    }

    messages.push({ role: "assistant", content: null, tool_calls: res.tool_calls });

    for (const call of res.tool_calls) {
      const handler = handlers[call.function.name];
      if (!handler) throw new Error(`Unknown tool: ${call.function.name}`);
      const result = await handler(JSON.parse(call.function.arguments));
      messages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(result) });
    }
  }

  throw new Error(`Tool loop exceeded ${MAX_HOPS} hops`);
}
```

## Combining Tool Calling with Structured Output

Tool calling and structured output are mutually exclusive per request: `response_format` prevents
the model from emitting `tool_calls`. The idiomatic pattern is a two-phase approach — collect
data via a tool loop, then reshape the accumulated answer into a schema:

```typescript
// src/two-phase.ts
async function collectThenShape(
  ai: Ai,
  userQuery: string,
  tools: AiTextGenerationInput["tools"],
  handlers: Record<string, ToolHandler>,
  outputSchema: object,
): Promise<unknown> {
  const messages: AiTextGenerationInput["messages"] = [
    { role: "user", content: userQuery },
  ];

  // Phase 1: free-form tool calling to gather facts
  const rawAnswer = await toolLoop(ai, messages, tools, handlers);

  // Phase 2: structured extraction from the collected text
  const shaped = await ai.run("@cf/meta/llama-3.3-70b-instruct", {
    messages: [
      { role: "system", content: "Extract the requested fields as JSON from the text." },
      { role: "user",   content: rawAnswer },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "result", strict: true, schema: outputSchema },
    },
    max_tokens: 512,
  });

  return JSON.parse(shaped.response as string);
}
```

## Anti-patterns

- Setting `strict: false` — constrained decoding is disabled; the model can emit invalid JSON.
- Parsing `result.response` before checking `result.tool_calls` — when a tool is requested,
  `response` is `null` or an empty string and `JSON.parse` throws.
- Passing large upstream payloads as tool results — every round-trip re-tokenises the full
  message history; keep tool result payloads under 2 KB.
- Setting `stream: true` alongside `response_format` — streaming and constrained decoding are
  incompatible; the request fails at runtime.

## Gotchas

- `tool_call_id` must be echoed verbatim in the `role: "tool"` message; a mismatch causes a
  model-side error on most implementations.
- JSON Schema `additionalProperties: false` is required for `strict: true`; omitting it
  silently downgrades enforcement on some model versions.
- Tool names must match `^[a-zA-Z0-9_-]{1,64}$`; spaces or dots cause silent truncation.
- The schema itself consumes tokens and counts against `max_tokens`; budget 200–400 extra
  tokens for schemas with more than five properties.

## Verification

```bash
# Smoke-test structured output
curl -X POST https://your-worker.example.com/extract \
  -H "Content-Type: application/json" \
  -d '{"description":"Blue wireless headphones $49.99, 3 left, tags: audio bluetooth"}'
# Expected: {"name":"Blue wireless headphones","price":49.99,"inStock":true,"tags":["audio","bluetooth"]}

# Validate schema compliance locally
npx ajv validate -s schema.json -d response.json --strict=false
```

## Related

- `workers-ai-edge-inference.md`
- `workers-ai-embedding-batch-vectorize-upsert.md`
- `workers-ai-inference-gateway.md`
- `workflows-parallel-step-execution.md`
- `ai-gateway-best-practices.md`

## Sources

- https://developers.cloudflare.com/workers-ai/function-calling/
- https://developers.cloudflare.com/workers-ai/configuration/json-mode/
- https://developers.cloudflare.com/workers-ai/models/llama-3.3-70b-instruct/
