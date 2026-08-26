# llm-structured-output-json-mode

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

LLMs return prose, markdown fences, or truncated JSON instead of
a parseable object. Even with JSON mode enabled, values are
semantically wrong — hallucinated IDs, misformatted dates, or
required fields filled with empty strings. Parse failures surface
as `SyntaxError`, `ZodError`, or silent `undefined` at runtime.

## Context

Three API mechanisms exist for extracting structured data from an
LLM: JSON mode (valid JSON syntax only), structured outputs with
a response schema (enforce object shape), and function/tool use
(declare a callable action with typed parameters). Teams conflate
them and assume that schema compliance guarantees correctness.
It does not. A well-shaped JSON object can still carry
hallucinated values. A validation layer is always required.

## 1  Mechanism comparison

| Mechanism | Guarantees | Latency | Best for |
|-----------|------------|---------|----------|
| JSON mode | Valid JSON syntax | +0 ms | Quick extraction |
| Structured output | JSON + schema shape | +0 ms | Typed extraction |
| Function/tool call | Schema + dispatch | +1 RT | Actions, lookups |

OpenAI: `response_format={"type":"json_schema","strict":true}`.
Anthropic Messages API: pass a tool with `input_schema` and
`tool_choice={"type":"tool","name":"…"}` — the model is forced
to call that tool and fill the schema.

## 2  Zod validation in TypeScript

```typescript
import { z } from "zod";

const OrderSchema = z.object({
  orderId: z.string().regex(/^ORD-\d{5}$/),
  customerEmail: z.string().email().nullable(),
  intent: z.enum(["refund", "status", "cancel"])
            .default("status"),
});
type Order = z.infer<typeof OrderSchema>;

async function extractOrder(raw: string): Promise<Order> {
  const res = await openai.chat.completions.create({
    model: "gpt-4o",
    response_format: { type: "json_object" },
    messages: [
      {
        role: "system",
        content: "Return a JSON object with keys: "
                 + "orderId, customerEmail, intent.",
      },
      { role: "user", content: raw },
    ],
  });
  const text = res.choices[0].message.content ?? "{}";
  return OrderSchema.parse(JSON.parse(text));
}
```

## 3  Retry on parse failure

```typescript
async function extractWithRetry(
  raw: string,
  maxAttempts = 3,
): Promise<Order> {
  const messages: ChatMessage[] = [buildPrompt(raw)];

  for (let i = 0; i < maxAttempts; i++) {
    const res = await openai.chat.completions.create({
      model: "gpt-4o",
      response_format: { type: "json_object" },
      messages,
    });
    const text = res.choices[0].message.content ?? "{}";
    try {
      return OrderSchema.parse(JSON.parse(text));
    } catch (err) {
      // Feed the error back so the model can self-correct
      messages.push({ role: "assistant", content: text });
      messages.push({
        role: "user",
        content: `Validation failed: ${err}. `
                 + "Return corrected JSON only.",
      });
    }
  }
  throw new Error("LLM failed validation after 3 attempts");
}
```

## 4  Stripping markdown fences (safety net)

```typescript
function extractJson(text: string): unknown {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  const clean = (fenced ? fenced[1] : text).trim();
  return JSON.parse(clean);
}
```

Use this as a pre-parse step when the model is known to wrap
JSON in fences despite explicit instructions.

## 5  Schema design rules that cut hallucination

```typescript
// Good: flat, few required fields, short enum, descriptions
const GoodSchema = z.object({
  /** e.g. "ORD-12345" */
  orderId: z.string(),
  /** null when not present in the text */
  customerEmail: z.string().email().nullable(),
  intent: z.enum(["refund", "status", "cancel"]),
});

// Bad: deep nesting, 40-value enum, every field required
const BadSchema = z.object({
  order: z.object({            // extra nesting layer
    details: z.object({        // another layer
      id: z.string(),
      category: z.enum([...40 values...]),  // breaks sampling
    }),
  }),
});
```

Rules: prefer flat over nested; make only essential fields
required; keep enums to ≤10 values; add `.describe()` or
JSDoc to guide the model.

## Anti-patterns

- Activating JSON mode without mentioning JSON in the prompt.
  Many models ignore the flag when the prompt does not ask.
- Skipping Zod and accepting `any` — syntax is not semantics.
- Retrying without feeding the error back; the model repeats
  the same mistake.
- Using function calling just to force JSON output — adds a
  round-trip with no benefit over `response_format`.
- Deeply nested required schemas — each nesting level raises
  the hallucination rate on required fields.

## Gotchas

- JSON mode guarantees syntax only, not schema shape or truth.
- Strict mode forces a value for every required field; the model
  emits an empty string or guess when it does not know. Prefer
  optional fields with a `.nullable()` sentinel.
- Streaming + JSON mode yields partial JSON; buffer the full
  stream before calling `JSON.parse`.
- Schema tokens count against prompt budget on every call;
  a 60-field schema can cost more than the rest of the prompt.
- `""` vs `null` conflation: add a Zod `.transform` to
  normalize `""` to `null` for string fields.

## Verification

- Unit: `OrderSchema.parse(fixture)` passes with valid sample;
  throws `ZodError` on missing `orderId`.
- Integration: inject a malformed response via a test double;
  confirm the retry loop surfaces a corrected result.
- E2E: submit a real email; confirm `orderId` matches
  `/^ORD-\d{5}$/` and `intent` is a known enum value.

## Related

- `ai-ml/llm-structured-output-vs-function-calling.md`
- `ai-ml/llm-output-validation.md`
- `ai-ml/llm-retry-patterns.md`
- `ai-ml/llm-function-calling.md`
- `ai-ml/llm-output-parsing.md`

## Source URLs (verified 2026-08-17)

- https://platform.openai.com/docs/guides/structured-outputs
- https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- https://zod.dev/
- https://json-schema.org/specification
- https://platform.openai.com/docs/guides/text-generation/json-mode
