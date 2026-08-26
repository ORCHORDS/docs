# Workers AI JSON Schema Constrained Generation

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need Workers AI to return valid, typed JSON every time — not freeform text that happens to look like JSON — so downstream code can parse without try/catch gymnastics. Schema violations keep slipping through when you rely solely on prompt instructions.

## Context
Workers AI exposes a `response_format` field on chat-completion compatible models (e.g. `@cf/meta/llama-3.1-8b-instruct`) that mirrors the OpenAI JSON-mode API. When paired with a JSON Schema, the model's sampling is constrained at the token level so the output is guaranteed to be valid JSON matching the schema. This eliminates an entire class of parse-and-retry loops and cuts output-validation overhead significantly.

## Defining the Response Schema

Declare the schema as a plain object and pass it via `response_format`. The schema must be a valid JSON Schema draft-07 object with `type: "object"` at the top level.

```typescript
// src/schemas.ts
export const productSchema = {
  type: "object" as const,
  properties: {
    name:        { type: "string" },
    price:       { type: "number" },
    currency:    { type: "string", enum: ["USD", "EUR", "GBP"] },
    inStock:     { type: "boolean" },
    tags:        { type: "array", items: { type: "string" } },
    description: { type: "string", maxLength: 500 }
  },
  required: ["name", "price", "currency", "inStock"],
  additionalProperties: false
};

export type Product = {
  name: string;
  price: number;
  currency: "USD" | "EUR" | "GBP";
  inStock: boolean;
  tags?: string[];
  description?: string;
};
```

## Calling the Model with Schema Constraints

```typescript
// src/index.ts
import { productSchema, type Product } from "./schemas";

interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userInput } = await request.json<{ userInput: string }>();

    const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [
        {
          role: "system",
          content: [
            "Extract product information from the user's text.",
            "Return ONLY valid JSON matching the provided schema.",
            "If a required field cannot be determined, use a sensible default.",
          ].join(" "),
        },
        { role: "user", content: userInput },
      ],
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "product_extraction",
          schema: productSchema,
          strict: true,
        },
      },
      max_tokens: 512,
      temperature: 0.1,
    });

    // result.response is already valid JSON when schema constraints are active
    const product = JSON.parse(result.response) as Product;

    return Response.json({ product });
  },
};
```

## Layered Validation with Zod

Even with schema-constrained generation, validate at the application boundary for defense-in-depth and to get typed TypeScript values.

```typescript
import { z } from "zod";

const ProductSchema = z.object({
  name:        z.string().min(1).max(200),
  price:       z.number().positive(),
  currency:    z.enum(["USD", "EUR", "GBP"]),
  inStock:     z.boolean(),
  tags:        z.array(z.string()).max(20).optional(),
  description: z.string().max(500).optional(),
});

async function extractProduct(env: Env, text: string) {
  const raw = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: "Extract product info as JSON." },
      { role: "user",   content: text },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "product", schema: productSchema, strict: true },
    },
    max_tokens: 512,
    temperature: 0,
  });

  const parsed = ProductSchema.safeParse(JSON.parse(raw.response));

  if (!parsed.success) {
    // Log Zod errors for debugging schema drift
    console.error("Schema validation failed:", parsed.error.flatten());
    throw new Error("Model output failed application-level validation");
  }

  return parsed.data; // fully typed Product
}
```

## Handling Nested and Array Schemas

For complex nested structures, keep nesting shallow — deeply nested schemas increase the constraint graph and can slow sampling. Prefer flat objects joined by IDs when possible.

```typescript
const lineItemSchema = {
  type: "object" as const,
  properties: {
    sku:      { type: "string" },
    qty:      { type: "integer", minimum: 1 },
    unitPrice: { type: "number" },
  },
  required: ["sku", "qty", "unitPrice"],
  additionalProperties: false,
};

const orderSchema = {
  type: "object" as const,
  properties: {
    orderId:   { type: "string" },
    customer:  { type: "string" },
    lineItems: {
      type: "array",
      items: lineItemSchema,
      minItems: 1,
      maxItems: 50,
    },
    total:     { type: "number" },
  },
  required: ["orderId", "customer", "lineItems", "total"],
  additionalProperties: false,
};

async function extractOrder(env: Env, text: string) {
  const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: "Parse this order confirmation into JSON." },
      { role: "user",   content: text },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "order", schema: orderSchema, strict: true },
    },
    max_tokens: 1024,
    temperature: 0,
  });

  return JSON.parse(result.response);
}
```

## Streaming with Schema Constraints

Schema-constrained generation is compatible with streaming — the constraint engine operates token-by-token. Accumulate chunks before parsing.

```typescript
async function streamExtract(env: Env, text: string): Promise<Response> {
  const stream = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: "Extract as JSON." },
      { role: "user",   content: text },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "product", schema: productSchema, strict: true },
    },
    stream: true,
    max_tokens: 512,
  });

  // For streaming constrained output, buffer and parse at end
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();
  let accumulated = "";

  (async () => {
    for await (const chunk of stream as AsyncIterable<{ response?: string }>) {
      if (chunk.response) {
        accumulated += chunk.response;
        // Stream raw JSON tokens to client as-is
        await writer.write(encoder.encode(chunk.response));
      }
    }
    await writer.close();
  })();

  return new Response(readable, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
```

## Anti-patterns
- Relying on prompt-only instructions ("return JSON") without `response_format` — model can still emit prose before or after the JSON block
- Using `type: "json_object"` without a schema when you need a specific shape — you get valid JSON but not necessarily the right fields
- Setting `temperature > 0.3` for extraction tasks — higher entropy fights constraint compliance
- Putting `additionalProperties: true` and then checking for unexpected keys downstream — defeats the schema's purpose
- Nesting schemas more than 3 levels deep — the constraint graph becomes large and can hit Workers AI token budget limits

## Gotchas
- `strict: true` in `json_schema` rejects schemas with `additionalProperties` not explicitly set to `false` on some model builds — always set it explicitly
- `enum` arrays must contain only primitive values; objects in enums are not supported by the constraint engine
- Models smaller than 7B parameters may ignore schema constraints on complex nested objects even with `response_format` set — test with your exact model
- The `response_format` field is only honored on chat-completion compatible routes; bare `@cf/` text-generation models ignore it
- Zod's `.safeParse()` is cheaper than `.parse()` in a Workers environment — avoid throwing on parse errors when you can handle gracefully

## Verification
```bash
# Test constrained extraction via wrangler dev
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{"userInput": "Blue running shoes, $89.99, in stock, sizes 8-12"}'

# Confirm output is valid JSON and matches schema
# jq will exit non-zero if the response is malformed
curl -sX POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{"userInput": "Red dress, 45 EUR, out of stock"}' | jq '.product'

# Negative test: deliberately send ambiguous input and verify required fields still present
curl -sX POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{"userInput": "some random text with no product info"}' | jq 'has("price")'
```

## Related
- [llm-structured-output-vs-function-calling.md](llm-structured-output-vs-function-calling.md)
- [llm-structured-extraction-zod-workers.md](llm-structured-extraction-zod-workers.md)
- [llm-output-validation.md](llm-output-validation.md)
- [workers-ai-function-calling-agentic-patterns.md](workers-ai-function-calling-agentic-patterns.md)

## Sources
- Cloudflare Workers AI docs — response_format / JSON mode: https://developers.cloudflare.com/workers-ai/configuration/json-mode/
- OpenAI Structured Outputs guide (schema compatibility reference): https://platform.openai.com/docs/guides/structured-outputs
- Zod docs: https://zod.dev
