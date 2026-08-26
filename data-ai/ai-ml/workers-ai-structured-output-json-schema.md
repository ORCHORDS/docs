# Workers AI Structured Output with JSON Schema

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need deterministic, machine-readable JSON from an LLM inside a Cloudflare Worker — not freeform prose that requires brittle regex parsing. Using `response_format` with a JSON Schema definition forces the model to emit only valid structured output, which you then validate with Zod and cache in KV to avoid redundant inference costs.

---

## Context

Cloudflare Workers AI exposes `response_format` on compatible models such as `@cf/meta/llama-3.1-8b-instruct`. Setting `type: "json_schema"` and supplying a schema object instructs the model to constrain its token sampling to valid JSON matching that shape. The raw response is still a string, so you must parse and validate it before trusting it downstream. A Zod schema is the idiomatic TypeScript way to perform that validation and derive the result type simultaneously. When the parse fails (model hallucinated an invalid structure) a simple retry loop with a clearer prompt usually recovers within one additional call. Caching the validated result in Workers KV under a deterministic key (e.g. SHA-256 of the input) prevents burning inference quota on repeated identical requests.

---

## Section 1 — wrangler.toml

```toml
name = "structured-output-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "CACHE"
id = "YOUR_KV_NAMESPACE_ID"
```

## Section 2 — Worker implementation

```typescript
import { Ai } from "@cloudflare/workers-types";
import { z } from "zod";

export interface Env {
  AI: Ai;
  CACHE: KVNamespace;
}

// Zod schema — single source of truth for both runtime validation and TypeScript types
const ProductSchema = z.object({
  name: z.string(),
  price: z.number().positive(),
  currency: z.enum(["USD", "EUR", "GBP"]),
  inStock: z.boolean(),
  tags: z.array(z.string()).max(10),
});
type Product = z.infer<typeof ProductSchema>;

// JSON Schema derived manually (keep in sync with ProductSchema).
// Workers AI requires a plain JSON Schema object, not a Zod schema.
const productJsonSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    price: { type: "number", minimum: 0, exclusiveMinimum: true },
    currency: { type: "string", enum: ["USD", "EUR", "GBP"] },
    inStock: { type: "boolean" },
    tags: { type: "array", items: { type: "string" }, maxItems: 10 },
  },
  required: ["name", "price", "currency", "inStock", "tags"],
  additionalProperties: false,
};

async function hashInput(input: string): Promise<string> {
  const encoded = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function inferStructured(
  ai: Ai,
  prompt: string,
  attempt = 0
): Promise<Product> {
  const MAX_ATTEMPTS = 3;

  const clarification =
    attempt > 0
      ? " IMPORTANT: your previous response was not valid JSON matching the schema. Respond ONLY with the JSON object."
      : "";

  const response = (await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "system",
        content:
          "You extract product information from text. Always respond with a single JSON object — no markdown fences, no extra text." +
          clarification,
      },
      { role: "user", content: prompt },
    ],
    response_format: {
      type: "json_schema",
      json_schema: {
        name: "product",
        schema: productJsonSchema,
        strict: true,
      },
    },
  })) as { response: string };

  let parsed: unknown;
  try {
    parsed = JSON.parse(response.response);
  } catch {
    if (attempt < MAX_ATTEMPTS) return inferStructured(ai, prompt, attempt + 1);
    throw new Error(`Model did not return valid JSON after ${MAX_ATTEMPTS} attempts`);
  }

  const result = ProductSchema.safeParse(parsed);
  if (!result.success) {
    if (attempt < MAX_ATTEMPTS) return inferStructured(ai, prompt, attempt + 1);
    throw new Error(
      `Schema validation failed after ${MAX_ATTEMPTS} attempts: ${result.error.message}`
    );
  }

  return result.data;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.text();
    const cacheKey = await hashInput(body);

    // Check KV cache first (TTL: 1 hour)
    const cached = await env.CACHE.get(cacheKey, "json");
    if (cached) {
      return Response.json({ product: cached, source: "cache" });
    }

    try {
      const product = await inferStructured(env.AI, body);

      // Store validated result in KV for 3600 seconds
      await env.CACHE.put(cacheKey, JSON.stringify(product), {
        expirationTtl: 3600,
      });

      return Response.json({ product, source: "inference" });
    } catch (err) {
      return Response.json(
        { error: (err as Error).message },
        { status: 422 }
      );
    }
  },
};
```

## Section 3 — Type-safe schema sync helper

```typescript
// scripts/gen-json-schema.ts — run with `npx tsx scripts/gen-json-schema.ts`
// Keeps the JSON Schema in sync with the Zod schema using zod-to-json-schema.
import { zodToJsonSchema } from "zod-to-json-schema";
import { ProductSchema } from "../src/index";
import fs from "node:fs";

const jsonSchema = zodToJsonSchema(ProductSchema, {
  name: "product",
  strictUnions: true,
});

fs.writeFileSync(
  "src/product-schema.json",
  JSON.stringify(jsonSchema, null, 2)
);
console.log("product-schema.json written");
```

---

## Anti-patterns

- **Trusting the model's raw string** — Always parse with `JSON.parse` and validate with Zod; the model can still emit near-valid JSON with wrong types even with `response_format` set.
- **No retry on parse failure** — A single hard error on first failure causes unnecessary 422s; one or two retries with an escalated prompt recovers the vast majority of cases.
- **Caching before validation** — Only cache after `ProductSchema.safeParse` succeeds; caching an invalid payload propagates corruption for the full TTL.
- **Embedding the JSON Schema inline without a single source of truth** — Divergence between the Zod schema and the JSON Schema passed to the model leads to silent mismatches; use `zod-to-json-schema` to derive one from the other.

---

## Gotchas

- `strict: true` inside `json_schema` is honoured by some model revisions but silently ignored by others — always run your own Zod validation regardless.
- `@cf/meta/llama-3.1-8b-instruct` may hallucinate extra wrapper keys (e.g. `{ "product": { ... } }`); add a pre-parse unwrap step if you observe this in staging.
- KV `get` with `"json"` deserialises automatically but returns `null` on a cache miss — distinguish `null` (miss) from `{ inStock: false }` (valid cached value).
- Workers AI inference latency can exceed 10 s on cold paths; set a 30 s Worker `maxDuration` in `wrangler.toml` under `[limits]` if needed.

---

## Verification

```bash
# Start local dev
npx wrangler dev --remote

# POST a product description
curl -X POST http://localhost:8787 \
  -H 'Content-Type: text/plain' \
  -d 'Blue wireless headphones, $49.99 USD, currently in stock, tags: audio, bluetooth'

# Expected: { "product": { "name": "...", "price": 49.99, ... }, "source": "inference" }

# Second identical request should hit KV cache
curl -X POST http://localhost:8787 \
  -H 'Content-Type: text/plain' \
  -d 'Blue wireless headphones, $49.99 USD, currently in stock, tags: audio, bluetooth'

# Expected: { ..., "source": "cache" }
```

---

## Related

- `workers-ai-tool-calling-d1-queries.md`
- `workers-ai-streaming-response-sse.md`

---

## Sources

- Cloudflare Workers AI REST API — https://developers.cloudflare.com/workers-ai/
- Zod documentation — https://zod.dev
- zod-to-json-schema — https://github.com/StefanTerdell/zod-to-json-schema
