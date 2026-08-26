# Workers AI JSON Mode: Structured Output with Zod Validation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need deterministic, schema-validated JSON from an LLM inside a Cloudflare Worker. Free-form text responses break downstream parsing and cause silent data-loss bugs in production. Workers AI's `response_format` option forces the model into JSON mode, and Zod validates the shape before you trust it.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Binding: `AI` (Workers AI)
- Model: `@cf/meta/llama-3.1-8b-instruct`
- Validation: `zod` v3 (bundled with your worker via wrangler)
- Pattern: request → AI JSON mode → Zod parse → retry on failure (max 3)

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "structured-ai"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"
```

## Section 2: Zod Schema Definition

Define your expected output shape once; reuse it for both the prompt and runtime validation.

```typescript
// src/schema.ts
import { z } from 'zod';

export const ProductSchema = z.object({
  name: z.string().min(1),
  category: z.enum(['electronics', 'clothing', 'food', 'other']),
  price_usd: z.number().positive(),
  in_stock: z.boolean(),
  tags: z.array(z.string()).max(5),
});

export type Product = z.infer<typeof ProductSchema>;

// Build a prompt-friendly schema description for the model
export const PRODUCT_SCHEMA_DESCRIPTION = `{
  "name": "string (product name)",
  "category": "electronics | clothing | food | other",
  "price_usd": "number (positive float)",
  "in_stock": "boolean",
  "tags": "array of strings, max 5 items"
}`;
```

## Section 3: JSON Mode Inference with Retry

```typescript
// src/ai-json.ts
import { Ai } from '@cloudflare/workers-types';
import { ZodError, ZodSchema } from 'zod';

export interface JsonModeOptions<T> {
  ai: Ai;
  model: string;
  systemPrompt: string;
  userMessage: string;
  schema: ZodSchema<T>;
  schemaDescription: string;
  maxRetries?: number;
}

export async function runJsonMode<T>(opts: JsonModeOptions<T>): Promise<T> {
  const {
    ai,
    model,
    systemPrompt,
    userMessage,
    schema,
    schemaDescription,
    maxRetries = 3,
  } = opts;

  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const retryHint =
      attempt > 1
        ? `\n\nPrevious attempt failed with: ${lastError?.message}. Return ONLY valid JSON matching the schema.`
        : '';

    const response = await ai.run(model as '@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        {
          role: 'system',
          content: `${systemPrompt}\n\nYou MUST respond with a single JSON object matching this schema:\n${schemaDescription}\nDo not include markdown, explanation, or extra text.${retryHint}`,
        },
        { role: 'user', content: userMessage },
      ],
      response_format: { type: 'json_object' },
      max_tokens: 512,
      temperature: 0.1, // low temperature for deterministic structure
    });

    const raw = (response as { response?: string }).response ?? '';

    try {
      const parsed = JSON.parse(raw.trim());
      const validated = schema.parse(parsed);
      return validated;
    } catch (err) {
      if (err instanceof ZodError) {
        lastError = new Error(`Zod validation failed: ${err.message}`);
      } else if (err instanceof SyntaxError) {
        lastError = new Error(`JSON parse failed on: ${raw.slice(0, 120)}`);
      } else {
        throw err;
      }
      console.warn(`[json-mode] attempt ${attempt}/${maxRetries} failed:`, lastError.message);
    }
  }

  throw new Error(`[json-mode] all ${maxRetries} attempts failed. Last error: ${lastError?.message}`);
}
```

## Section 4: Worker Entry Point

```typescript
// src/index.ts
import { runJsonMode } from './ai-json';
import { ProductSchema, PRODUCT_SCHEMA_DESCRIPTION } from './schema';

export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('POST a JSON body with { "description": "..." }', { status: 405 });
    }

    let description: string;
    try {
      const body = await request.json<{ description: string }>();
      description = body.description?.trim();
      if (!description) throw new Error('empty');
    } catch {
      return new Response('Invalid request body', { status: 400 });
    }

    try {
      const product = await runJsonMode({
        ai: env.AI,
        model: '@cf/meta/llama-3.1-8b-instruct',
        systemPrompt: 'You are a product data extraction assistant.',
        userMessage: `Extract product information from this text:\n${description}`,
        schema: ProductSchema,
        schemaDescription: PRODUCT_SCHEMA_DESCRIPTION,
        maxRetries: 3,
      });

      return Response.json({ ok: true, product });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return Response.json({ ok: false, error: message }, { status: 422 });
    }
  },
};
```

## Anti-patterns

- Do NOT rely on `response_format` alone without Zod — the model can still emit structurally wrong JSON that satisfies `json_object` but violates your domain schema.
- Do NOT set `temperature: 1.0` with JSON mode — higher temperatures increase malformed output probability.
- Do NOT parse `response` before checking it exists; Workers AI returns `{ response: string }` but the key may be absent on error.
- Do NOT skip the retry loop in production — even with `response_format`, parse failures occur ~2–5% of the time on smaller models.
- Do NOT embed the full Zod schema toString() in the prompt — write a concise human-readable description instead.

## Gotchas

- `response_format: { type: 'json_object' }` is supported only on instruction-tuned models; check the Workers AI model catalog before switching models.
- The `response` field is a raw string, not a pre-parsed object, even in JSON mode.
- Llama 3.1 8B may wrap the JSON in markdown fences (` ```json `) despite `json_object` mode on some prompt shapes — add a `.replace(/```[a-z]*\n?/g, '')` strip if you observe this.
- Zod's `.parse()` throws synchronously; wrap in try/catch, not `.catch()` on a promise.
- Workers AI free tier has per-minute neuron limits; batch retries can exhaust quota quickly.

## Verification

```bash
# Deploy
npx wrangler deploy

# Happy path
curl -X POST https://structured-ai.<your-subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"description": "Sony WH-1000XM5 wireless headphones, $279.99, available now, noise cancelling bluetooth"}'
# Expected: { ok: true, product: { name: "...", category: "electronics", price_usd: 279.99, in_stock: true, tags: [...] } }

# Validation failure path (model will retry up to 3 times, then 422)
curl -X POST https://structured-ai.<your-subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"description": "asdf"}'

# Local dev
npx wrangler dev --remote
```

## Related

- `documentation/docs/policies/ai-ml/workers-ai-function-calling-multi-step.md`
- `documentation/docs/policies/ai-ml/workers-ai-prompt-caching-kv-cost-reduction.md`
- `documentation/docs/policies/ai-ml/workers-ai-rag-reranking-vectorize.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/workers-ai/configuration/json-mode/
- https://zod.dev/
- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
