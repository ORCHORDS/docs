# LLM Structured Output Extraction with Zod in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Workers AI and upstream LLMs return JSON that claims to match a schema but frequently violates it under load — extra
fields, wrong types, missing required keys. You need runtime schema enforcement with typed TypeScript output, retry
logic for schema violations, and no external dependencies that violate the Workers bundle size limit.

## Context

Zod is the de-facto TypeScript schema validation library and works in the Workers runtime with zero native-module
dependencies. Combining Zod with a JSON-mode LLM prompt creates a strongly-typed extraction pipeline: the LLM outputs
JSON, Zod parses and validates it, and on failure the validation error is fed back into a retry prompt. The pattern
eliminates manual `if typeof` guards downstream and surfaces schema drift early. Workers AI's
`@cf/meta/llama-3.1-8b-instruct` supports JSON-mode via a `response_format` parameter.

## Zod Schema Definition

Define your extraction schema once; derive TypeScript types from it automatically.

```typescript
import { z } from "zod";

// Product entity extracted from unstructured review text
export const ProductSchema = z.object({
  name: z.string().min(1),
  brand: z.string().optional(),
  rating: z.number().min(1).max(5),
  pros: z.array(z.string()).min(1).max(10),
  cons: z.array(z.string()).max(10),
  sentiment: z.enum(["positive", "neutral", "negative"]),
  price_mentioned: z.number().positive().optional(),
  verified_purchase: z.boolean(),
});

export type ProductExtraction = z.infer<typeof ProductSchema>;

// Zod transform: coerce stringified numbers that LLMs sometimes emit
export const ProductSchemaCoerced = z.object({
  name: z.string().min(1),
  brand: z.string().optional(),
  rating: z.coerce.number().min(1).max(5),
  pros: z.array(z.string()).min(1).max(10),
  cons: z.array(z.string()).max(10),
  sentiment: z.enum(["positive", "neutral", "negative"]),
  price_mentioned: z.coerce.number().positive().optional(),
  verified_purchase: z.coerce.boolean(),
});
```

## Extraction with Retry on Schema Violation

On a Zod parse failure, re-prompt the model with the exact validation errors to guide correction.

```typescript
import type { Ai } from "@cloudflare/ai";

interface Env {
  AI: Ai;
}

const SYSTEM_PROMPT = `You are a product review extraction engine.
Extract structured data from the provided review text and return ONLY valid JSON.
Do not include markdown fences, comments, or any text outside the JSON object.`;

function buildExtractionPrompt(review: string, priorErrors?: string): string {
  let prompt = `Extract product information from this review:\n\n${review}\n\n`;
  if (priorErrors) {
    prompt += `Your previous response failed validation with these errors:\n${priorErrors}\n\nFix the JSON and try again.`;
  }
  return prompt;
}

async function extractWithRetry(
  env: Env,
  review: string,
  maxAttempts = 3
): Promise<ProductExtraction> {
  let lastErrors: string | undefined;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const response = await (env.AI as any).run(
      "@cf/meta/llama-3.1-8b-instruct",
      {
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: buildExtractionPrompt(review, lastErrors),
          },
        ],
        response_format: { type: "json_object" },
        temperature: 0.0, // Deterministic output for extraction
        max_tokens: 512,
      }
    ) as { response: string };

    let parsed: unknown;
    try {
      parsed = JSON.parse(response.response);
    } catch {
      lastErrors = `Response was not valid JSON: ${response.response.slice(0, 100)}`;
      continue;
    }

    const result = ProductSchemaCoerced.safeParse(parsed);
    if (result.success) {
      return result.data as ProductExtraction;
    }

    // Format Zod errors for the retry prompt
    lastErrors = result.error.errors
      .map((e) => `  • ${e.path.join(".")}: ${e.message}`)
      .join("\n");

    console.warn(`Attempt ${attempt} failed validation:\n${lastErrors}`);
  }

  throw new Error(
    `Failed to extract valid structured output after ${maxAttempts} attempts. Last errors:\n${lastErrors}`
  );
}
```

## Batch Extraction and Error Aggregation

Run extraction concurrently for multiple reviews with bounded parallelism and collect failures separately.

```typescript
interface ExtractionResult {
  index: number;
  success: true;
  data: ProductExtraction;
}

interface ExtractionError {
  index: number;
  success: false;
  error: string;
}

async function batchExtract(
  env: Env,
  reviews: string[],
  concurrency = 5
): Promise<(ExtractionResult | ExtractionError)[]> {
  const results: (ExtractionResult | ExtractionError)[] = [];
  const queue = reviews.map((r, i) => ({ review: r, index: i }));

  while (queue.length > 0) {
    const batch = queue.splice(0, concurrency);
    const settled = await Promise.allSettled(
      batch.map(({ review, index }) =>
        extractWithRetry(env, review).then((data) => ({ index, data }))
      )
    );

    for (let i = 0; i < settled.length; i++) {
      const s = settled[i];
      if (s.status === "fulfilled") {
        results.push({ index: s.value.index, success: true, data: s.value.data });
      } else {
        results.push({
          index: batch[i].index,
          success: false,
          error: String(s.reason),
        });
      }
    }
  }

  return results.sort((a, b) => a.index - b.index);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { reviews } = (await request.json()) as { reviews: string[] };

    if (!Array.isArray(reviews) || reviews.length === 0) {
      return new Response("reviews array required", { status: 400 });
    }

    if (reviews.length > 50) {
      return new Response("Max 50 reviews per request", { status: 422 });
    }

    const results = await batchExtract(env, reviews);
    const successes = results.filter((r) => r.success);
    const failures = results.filter((r) => !r.success);

    return Response.json({
      total: reviews.length,
      succeeded: successes.length,
      failed: failures.length,
      results,
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Using `JSON.parse` output directly without validation — even with `response_format: json_object` the LLM may omit
  required fields or use wrong types, especially under high temperature.
- Re-prompting with the raw Zod error object — `JSON.stringify(error.errors)` produces noise; format a concise bullet
  list of path + message to maximise correction accuracy.
- Setting `concurrency` above 10 — Workers AI rate limits apply per account; flooding the binding causes 429s that
  are not automatically retried by the AI binding.

## Gotchas

- `response_format: { type: "json_object" }` is not supported by all Workers AI models. Check the model card before
  assuming it is available; for unsupported models, instruct JSON output via the system prompt and parse defensively.
- Zod's `z.coerce.boolean()` coerces the string `"false"` to `true` (truthy string). Use `z.preprocess` with an
  explicit check if the LLM might emit stringified booleans.
- Workers bundle size limit is 10 MB (compressed). Zod v3 adds ~13 KB gzipped — well within budget, but avoid
  importing from barrel files that pull in unused validators.

## Verification

```bash
# Test single extraction
curl -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{
    "reviews": [
      "I bought the AcmePro X3 for $129. Great battery life and fast charging. A bit heavy though. 4 out of 5 stars."
    ]
  }' | jq '.results[0].data'

# Expected keys: name, rating (number), pros (array), cons (array), sentiment, verified_purchase (bool)

# Force schema violation to test retry path (truncated review)
curl -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"reviews": ["."]}' | jq '.results[0].success'
# May return false if model cannot extract meaningful data — verify error field is populated
```

## Related

- `ai-ml/llm-structured-output.md`
- `ai-ml/llm-for-extraction.md`
- `ai-ml/llm-output-validation.md`
- `ai-ml/llm-json-mode.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://zod.dev/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/ai/
