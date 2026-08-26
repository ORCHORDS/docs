# Workers AI: Multimodal Image Analysis with LLaVA

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to automatically describe, categorise, moderate, or generate alt-text for user-uploaded images — at the edge, without a dedicated GPU server or a third-party vision API. Use cases include product description generation for e-commerce, image moderation for UGC platforms, and accessibility alt-text for CMS uploads.

## Context

`@cf/llava-hf/llava-1.5-7b-hf` (referred to as LLaVA) is a multimodal model available on Workers AI that accepts a combination of an image and a text prompt and returns a text response. The model takes the image as a `number[]` of raw JPEG/PNG bytes — identical to the Whisper audio pattern — alongside a `prompt` string.

Common capabilities:
- **Captioning / description**: "Describe this image in one sentence."
- **Product metadata**: "List the product name, colour, and category visible in this image."
- **Alt-text generation**: "Generate a concise, descriptive alt-text for screen readers."
- **Moderation scoring**: "Does this image contain adult content, violence, or hate symbols? Answer YES or NO with a reason."
- **Structured JSON output**: wrap the prompt with a JSON schema request to parse results deterministically.

The worker fetches images from R2, invokes LLaVA, and returns or stores the analysis. For high-volume platforms, queue the analysis asynchronously (same pattern as speech-to-text).

## Solution

### 1. wrangler.toml

```toml
[[r2_buckets]]
  binding     = "IMAGE_BUCKET"
  bucket_name = "image-uploads"

[[ai]]
  binding = "AI"

[[d1_databases]]
  binding       = "DB"
  database_name = "image-analysis-db"
  database_id   = "<your-d1-id>"
```

### 2. Core analysis function

```typescript
// src/analyse.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  IMAGE_BUCKET: R2Bucket;
  AI: Ai;
  DB: D1Database;
}

interface LLaVAResult {
  description: string;
}

async function fetchImageBytes(bucket: R2Bucket, key: string): Promise<number[]> {
  const obj = await bucket.get(key);
  if (!obj) throw new Error(`Image not found in R2: ${key}`);

  const buffer = await obj.arrayBuffer();
  return [...new Uint8Array(buffer)]; // LLaVA requires number[]
}

export async function analyseImage(
  env: Env,
  r2Key: string,
  prompt: string
): Promise<string> {
  const image = await fetchImageBytes(env.IMAGE_BUCKET, r2Key);

  const result = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
    image,
    prompt,
    max_tokens: 512,
  }) as LLaVAResult;

  return result.description;
}
```

### 3. Product description generation

```typescript
// src/product-description.ts
export async function generateProductDescription(
  env: Env,
  r2Key: string
): Promise<Record<string, string>> {
  const structuredPrompt = `
Analyse this product image and respond ONLY with valid JSON in this exact format:
{
  "name": "<product name>",
  "category": "<category>",
  "colour": "<primary colour>",
  "material": "<material if visible or 'unknown'>",
  "description": "<one-sentence marketing description>"
}
Do not include any text outside the JSON object.
`.trim();

  const raw = await analyseImage(env, r2Key, structuredPrompt);

  // Extract JSON from the model response (LLaVA sometimes adds preamble)
  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error(`LLaVA did not return valid JSON: ${raw}`);

  return JSON.parse(jsonMatch[0]) as Record<string, string>;
}
```

### 4. Alt-text generation

```typescript
// src/alt-text.ts
export async function generateAltText(
  env: Env,
  r2Key: string
): Promise<string> {
  const prompt = [
    'Generate concise, descriptive alt-text for this image suitable for screen readers.',
    'Requirements:',
    '- Maximum 125 characters',
    '- Start with the most important element',
    '- Do not start with "Image of" or "Picture of"',
    '- Use plain, simple language',
    'Respond with ONLY the alt-text string, no quotes, no explanation.',
  ].join('\n');

  const raw = await analyseImage(env, r2Key, prompt);
  return raw.trim().slice(0, 125);
}
```

### 5. Image moderation scoring

```typescript
// src/moderation.ts
interface ModerationResult {
  safe: boolean;
  flags: string[];
  reason: string;
  score: number; // 0–100 risk score (derived from LLaVA text heuristics)
}

export async function moderateImage(
  env: Env,
  r2Key: string
): Promise<ModerationResult> {
  const prompt = `
You are a content moderation assistant. Examine this image for the following:
1. Adult/explicit content
2. Violence or gore
3. Hate symbols or extremist content
4. Spam or scam content

Respond ONLY with JSON in this format:
{
  "safe": true | false,
  "flags": ["<flag1>", "<flag2>"],
  "reason": "<brief explanation>",
  "risk_score": <0-100>
}
If none of the above are detected, return {"safe": true, "flags": [], "reason": "No violations detected", "risk_score": 0}.
`.trim();

  const raw = await analyseImage(env, r2Key, prompt);
  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    // Default to safe on parse failure to avoid false positives blocking legitimate content
    return { safe: true, flags: [], reason: 'Parse error — manual review recommended', score: 0 };
  }

  const parsed = JSON.parse(jsonMatch[0]) as {
    safe: boolean;
    flags: string[];
    reason: string;
    risk_score: number;
  };

  return {
    safe: parsed.safe,
    flags: parsed.flags ?? [],
    reason: parsed.reason ?? '',
    score: parsed.risk_score ?? 0,
  };
}
```

### 6. HTTP handler combining all analyses

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { r2Key, tasks } = await request.json<{
      r2Key: string;
      tasks: Array<'product' | 'alt_text' | 'moderate'>;
    }>();

    if (!r2Key || !tasks?.length) {
      return new Response(JSON.stringify({ error: 'r2Key and tasks[] are required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const results: Record<string, unknown> = {};

    // Run tasks sequentially to respect Workers AI rate limits
    for (const task of tasks) {
      try {
        if (task === 'product') results.product = await generateProductDescription(env, r2Key);
        if (task === 'alt_text') results.alt_text = await generateAltText(env, r2Key);
        if (task === 'moderate') results.moderation = await moderateImage(env, r2Key);
      } catch (err) {
        results[`${task}_error`] = String(err);
      }
    }

    // Optionally persist to D1
    await env.DB.prepare(
      `INSERT OR REPLACE INTO image_analyses (r2_key, results, created_at)
         VALUES (?, ?, datetime('now'))`
    ).bind(r2Key, JSON.stringify(results)).run();

    return new Response(JSON.stringify(results), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### 7. Vision prompt patterns (reference)

| Goal | Prompt pattern |
|------|-----------------|
| Caption | `"Describe this image in one sentence."` |
| Detail | `"List every object visible in this image."` |
| OCR | `"Extract all text visible in this image. Return only the text."` |
| Comparison | `"Compare these two images and list the differences."` |
| Classification | `"Classify this image into one of: [A, B, C]. Respond with only the class name."` |
| Structured | `"Respond ONLY with JSON: {\"field\": value}. No extra text."` |

## Implementation Details

- LLaVA 1.5 7B is instruction-tuned; wrapping prompts in `USER: ... ASSISTANT:` format improves output quality for structured tasks.
- Image size should be under 5 MB for best latency; larger images incur additional preprocessing time inside the model runtime.
- JSON extraction via regex (`/\{[\s\S]*\}/`) is necessary because LLaVA often prefixes its response with a preamble sentence.
- Running multiple tasks sequentially (product + alt_text + moderation) on the same image totals ~2–4 seconds end-to-end on Workers AI paid tier.
- The `max_tokens` parameter caps the response length; increase it for verbose tasks like full image descriptions, reduce it for binary (YES/NO) moderation answers.

## Anti-patterns

- **Passing image URLs instead of bytes**: LLaVA on Workers AI requires the raw bytes as a `number[]` — not an HTTP URL. Fetch from R2 first.
- **Relying on LLaVA for safety-critical moderation alone**: supplement with a dedicated `@cf/microsoft/resnet-50` or similar classification model for hard content gates.
- **Asking for multiple independent analyses in a single prompt**: the model conflates answers. Run one analysis per `AI.run` call for reliable structured output.
- **Not extracting JSON with regex**: if you call `JSON.parse(raw)` directly and the model adds preamble text, the parse throws. Always use the regex extraction pattern.

## Gotchas

- LLaVA is a single-image model — it accepts one image per invocation. For multi-image comparison, you must compose images server-side (e.g., side-by-side canvas) before calling the model.
- The `description` field name in the response is specific to the Workers AI LLaVA binding; do not confuse with generic OpenAI vision API response shapes.
- Memory usage with large PNG images can approach the 128 MB Worker limit; convert to JPEG (quality 85) before analysis when possible.
- LLaVA performs poorly on charts/graphs and structured data; for those, use dedicated OCR or chart-reading models.

## Verification

```bash
# Upload a test image to R2
wrangler r2 object put image-uploads/test.jpg --file=./test.jpg

# Analyse it
curl -X POST https://<worker>.workers.dev/analyse \
  -H 'Content-Type: application/json' \
  -d '{"r2Key":"test.jpg","tasks":["alt_text","moderate"]}'

# Expected:
# {"alt_text":"A red coffee mug on a wooden desk.","moderation":{"safe":true,...}}
```

## Related

- `documentation/categories/ai-ml/workers-ai-speech-to-text-r2.md` — async R2-backed analysis pipeline.
- `documentation/categories/ai-ml/workers-ai-content-moderation-gateway.md` — combining model outputs with AI Gateway rules.

## Sources

- Cloudflare Workers AI LLaVA model: https://developers.cloudflare.com/workers-ai/models/llava-1.5-7b-hf/
- Workers AI image classification: https://developers.cloudflare.com/workers-ai/models/resnet-50/
- R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
