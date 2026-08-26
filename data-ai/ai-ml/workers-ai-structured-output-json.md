# Structured JSON Output from Workers AI LLMs

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need deterministic, machine-readable JSON from a large language model hosted on Workers AI. Free-form text responses are unpredictable; your downstream code cannot reliably parse them. You want schema-enforced output with automatic retry on parse failure.

## Context

Workers AI exposes the `response_format` parameter for compatible models (e.g. `@cf/meta/llama-3.1-8b-instruct`, `@cf/mistral/mistral-7b-instruct-v0.1`). Combined with a tight system prompt and Zod schema validation, you can extract structured data — product metadata, entity lists, classification labels — without a dedicated fine-tuned model.

Key constraints:
- `response_format: { type: 'json_object' }` is supported only on chat-completion style endpoints.
- The model still has a chance of hallucinating extra keys; always validate with Zod.
- Token budget matters: a 128-token JSON schema description saves retries.

## Solution

### 1. Define the Zod schema

```typescript
// src/schemas/product.ts
import { z } from 'zod';

export const ProductSchema = z.object({
  name: z.string().min(1).max(200),
  brand: z.string().optional(),
  price: z.number().nonnegative().optional(),
  currency: z.string().length(3).optional(),   // ISO 4217
  categories: z.array(z.string()).max(10),
  in_stock: z.boolean(),
  sku: z.string().optional(),
  description_summary: z.string().max(500),
});

export type Product = z.infer<typeof ProductSchema>;
```

### 2. System prompt engineering for JSON

```typescript
// src/prompts/product.ts
export function buildSystemPrompt(): string {
  return [
    'You are a product data extraction assistant.',
    'Your ONLY output must be a single valid JSON object matching this schema:',
    '{',
    '  "name": string,           // product title, required',
    '  "brand": string | null,   // brand name or null',
    '  "price": number | null,   // numeric price or null',
    '  "currency": string | null,// 3-letter ISO code or null',
    '  "categories": string[],   // up to 10 category strings',
    '  "in_stock": boolean,      // inventory status, required',
    '  "sku": string | null,     // SKU code or null',
    '  "description_summary": string // ≤500 char summary, required',
    '}',
    'Do NOT include markdown fences, explanations, or extra keys.',
    'If a field cannot be determined, use null or [] as appropriate.',
  ].join('\n');
}
```

### 3. Workers AI call with response_format

```typescript
// src/lib/extract.ts
import type { Ai } from '@cloudflare/workers-types';
import { ProductSchema, type Product } from '../schemas/product';
import { buildSystemPrompt } from '../prompts/product';

const MAX_RETRIES = 3;

export async function extractProduct(
  ai: Ai,
  rawText: string,
): Promise<Product> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: buildSystemPrompt() },
        {
          role: 'user',
          content: `Extract product data from the following text:\n\n${rawText}`,
        },
      ],
      response_format: { type: 'json_object' },
      max_tokens: 512,
      temperature: 0,   // deterministic
    });

    const raw = (response as { response?: string }).response ?? '';

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      lastError = new Error(`JSON.parse failed on attempt ${attempt}: ${raw.slice(0, 200)}`);
      continue;
    }

    const result = ProductSchema.safeParse(parsed);
    if (result.success) {
      return result.data;
    }

    lastError = new Error(
      `Zod validation failed on attempt ${attempt}: ${result.error.message}`,
    );
  }

  throw lastError;
}
```

### 4. Worker entry point

```typescript
// src/index.ts
import { extractProduct } from './lib/extract';

export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('POST only', { status: 405 });
    }

    const body = await request.text();
    if (!body) {
      return new Response('Empty body', { status: 400 });
    }

    try {
      const product = await extractProduct(env.AI, body);
      return Response.json(product);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return Response.json({ error: message }, { status: 422 });
    }
  },
};
```

### 5. wrangler.jsonc binding

```jsonc
// wrangler.jsonc
{
  "name": "product-extractor",
  "main": "src/index.ts",
  "compatibility_date": "2025-09-01",
  "ai": {
    "binding": "AI"
  }
}
```

## Implementation Details

### Token budget for schema descriptions

Include the schema in the system prompt, not the user prompt, so it does not consume user-turn tokens on repeated calls and the model treats it as a standing instruction. Keep field comments terse — aim for the schema block to fit within 200 tokens.

### Retry strategy

Retry on any of:
- `JSON.parse` throws (model leaked markdown or text)
- Zod parse returns `.success === false`
- Network timeout from Workers AI (treat as transient)

Do not retry indefinitely. Three attempts with `temperature: 0` are almost always sufficient; a fourth retry rarely recovers from a systematic prompt problem.

### Partial extraction

If you only care about a subset of fields, remove the rest from the schema and the system prompt. Fewer fields reduce hallucination surface and speed up generation.

### Model selection

| Model | JSON reliability | Speed | Notes |
|---|---|---|---|
| `@cf/meta/llama-3.1-8b-instruct` | High | Fast | Good default |
| `@cf/mistral/mistral-7b-instruct-v0.1` | Medium | Fast | Older, less reliable |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Very high | Slower | Use when accuracy critical |

## Anti-patterns

- **Asking for JSON in the user prompt only**: models trained on instruction-following expect system-level directives for output format constraints.
- **Parsing without validation**: `JSON.parse` succeeds for `{}` — always run the Zod parse.
- **High temperature for extraction**: use `temperature: 0` or close to it; creativity is the enemy of structured output.
- **Embedding the raw schema type string**: TypeScript types are stripped at runtime; always write the schema inline as a comment block or JSON Schema object.
- **Trusting `response_format` alone**: the model can still produce invalid JSON in edge cases; the retry loop is non-optional.

## Gotchas

- `response_format` is ignored silently on models that do not support it — check the Workers AI model catalog before relying on it.
- Workers AI adds its own instruction tokens; your effective context window is smaller than the raw model context.
- Zod `.optional()` fields will be `undefined` in TypeScript but the LLM may return `null` — use `.nullish()` or `.optional().nullable()` if you want to accept both.
- Very long input text may push the model past its context window and truncate the output mid-JSON. Chunk or summarize inputs exceeding ~2000 tokens before extraction.

## Verification

```bash
# Deploy
npx wrangler deploy

# Smoke test
curl -X POST https://product-extractor.<account>.workers.dev \
  -H 'Content-Type: text/plain' \
  --data 'Nike Air Max 90 Running Shoe - White/Black, Size 10. Price: $129.99. SKU: NK-AM90-WB-10. In stock.'

# Expected: valid JSON matching ProductSchema
# { "name": "Nike Air Max 90 Running Shoe", "brand": "Nike", "price": 129.99, ... }

# Validate schema locally
npx ts-node -e "
import { ProductSchema } from './src/schemas/product';
const sample = JSON.parse(process.argv[1]);
console.log(ProductSchema.safeParse(sample));
"
```

## Related

- `workers-ai-function-calling-tools.md` — multi-turn structured interactions
- `workers-ai-rag-vectorize-d1.md` — feeding extracted structured data into RAG
- Cloudflare Workers AI docs: Text Generation
- Zod documentation: https://zod.dev

## Sources

- Cloudflare Workers AI — Text Generation: https://developers.cloudflare.com/workers-ai/models/text-generation/
- Workers AI response_format parameter documentation
- Zod v3 schema validation library
