# Workers AI Image Generation Prompt Optimization with R2 Gallery Storage

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Image generation with Flux or Stable Diffusion is sensitive to prompt wording, negative prompts, aspect ratio, and guidance scale. Ad-hoc experimentation is slow; generated images disappear when the response stream ends; and there is no record of which prompt variants produced which results. A prompt optimization pipeline stores every generated image in R2 with its full prompt metadata, then exposes a gallery endpoint that lets you compare variants and promote winners to a KV prompt registry.

## Context

Workers AI exposes `@cf/black-forest-labs/flux-1-schnell` and `@cf/stabilityai/stable-diffusion-xl-base-1.0` via `env.AI.run()`. Both return image bytes that must be stored externally — Workers responses are ephemeral. R2 is the natural sink: images are stored with a deterministic key derived from a hash of the prompt parameters, preventing duplicate generation. KV holds the canonical "winning" prompt variants indexed by use-case slug. D1 stores generation metadata (prompt, seed, model, width, height, score, R2 key) for analysis.

---

## 1. Prompt Template System

```typescript
// src/prompts/templates.ts
export interface PromptParams {
  subject: string;
  style: string;
  lighting?: string;
  negativePrompt?: string;
  seed?: number;
  guidanceScale?: number;
  width?: number;
  height?: number;
}

export function buildPositivePrompt(p: PromptParams): string {
  const parts = [
    p.subject,
    p.style,
    p.lighting ?? 'soft natural lighting',
    'highly detailed, sharp focus, professional quality',
  ];
  return parts.join(', ');
}

// Stable Diffusion negative prompt best practices
export const DEFAULT_NEGATIVE =
  'blurry, low quality, distorted, deformed, ugly, bad anatomy, ' +
  'watermark, signature, text, duplicate, morbid, mutilated';

export function hashParams(p: PromptParams, model: string): string {
  const key = JSON.stringify({ ...p, model });
  // Simple deterministic hash for R2 key uniqueness
  let h = 5381;
  for (const c of key) h = ((h << 5) + h) ^ c.charCodeAt(0);
  return (h >>> 0).toString(16).padStart(8, '0');
}
```

---

## 2. Generation Handler — Produce Image, Write to R2, Log to D1

```typescript
// src/handlers/generate.ts
import { buildPositivePrompt, DEFAULT_NEGATIVE, hashParams } from '../prompts/templates';
import type { Env } from '../types';
import type { PromptParams } from '../prompts/templates';

export async function handleGenerate(
  request: Request,
  env: Env,
): Promise<Response> {
  const params = await request.json<PromptParams & { model?: string }>();
  const model = params.model ?? '@cf/black-forest-labs/flux-1-schnell';
  const positivePrompt = buildPositivePrompt(params);
  const negativePrompt = params.negativePrompt ?? DEFAULT_NEGATIVE;
  const seed = params.seed ?? Math.floor(Math.random() * 2 ** 32);

  const r2Key = `gallery/${hashParams(params, model)}-${seed}.png`;

  // Check cache — skip generation if identical params already exist
  const existing = await env.IMAGE_BUCKET.head(r2Key);
  if (existing) {
    return Response.json({ r2Key, cached: true, url: `/gallery/${r2Key}` });
  }

  // Run inference
  const result = await env.AI.run(model as Parameters<typeof env.AI.run>[0], {
    prompt: positivePrompt,
    negative_prompt: negativePrompt,
    seed,
    num_inference_steps: 4,    // Flux Schnell optimal
    guidance_scale: params.guidanceScale ?? 7.5,
    width: params.width ?? 1024,
    height: params.height ?? 1024,
  });

  const imageBytes =
    result instanceof Uint8Array
      ? result
      : new Uint8Array(result as ArrayBuffer);

  // Persist to R2
  await env.IMAGE_BUCKET.put(r2Key, imageBytes, {
    httpMetadata: { contentType: 'image/png' },
    customMetadata: {
      prompt: positivePrompt,
      negativePrompt,
      seed: String(seed),
      model,
      width: String(params.width ?? 1024),
      height: String(params.height ?? 1024),
    },
  });

  // Log generation metadata to D1
  await env.DB.prepare(
    `INSERT INTO image_generations
       (r2_key, model, positive_prompt, negative_prompt, seed,
        width, height, guidance_scale, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, unixepoch())`,
  )
    .bind(
      r2Key,
      model,
      positivePrompt,
      negativePrompt,
      seed,
      params.width ?? 1024,
      params.height ?? 1024,
      params.guidanceScale ?? 7.5,
    )
    .run();

  return Response.json({ r2Key, cached: false, url: `/gallery/${r2Key}` }, { status: 201 });
}
```

---

## 3. Gallery Retrieval — Serve Images from R2

```typescript
// src/handlers/gallery.ts
import type { Env } from '../types';

export async function handleGalleryImage(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  // Strip /gallery/ prefix
  const r2Key = url.pathname.replace(/^\/gallery\//, '');
  if (!r2Key) return new Response('Not found', { status: 404 });

  const obj = await env.IMAGE_BUCKET.get(r2Key);
  if (!obj) return new Response('Not found', { status: 404 });

  const headers = new Headers();
  headers.set('Content-Type', 'image/png');
  headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  obj.writeHttpMetadata(headers);

  return new Response(obj.body, { headers });
}

export async function handleGalleryList(
  _request: Request,
  env: Env,
): Promise<Response> {
  const rows = await env.DB.prepare(
    `SELECT r2_key, model, positive_prompt, seed, width, height,
            guidance_scale, score, created_at
     FROM image_generations
     ORDER BY created_at DESC LIMIT 50`,
  ).all<{
    r2_key: string;
    model: string;
    positive_prompt: string;
    seed: number;
    width: number;
    height: number;
    guidance_scale: number;
    score: number | null;
    created_at: number;
  }>();

  return Response.json(rows.results.map((r) => ({
    ...r,
    url: `/gallery/${r.r2_key}`,
    createdAt: new Date(r.created_at * 1000).toISOString(),
  })));
}
```

---

## 4. Promote Winning Prompt to KV Registry

```typescript
// src/handlers/promote.ts
import type { Env } from '../types';

export async function handlePromote(
  request: Request,
  env: Env,
): Promise<Response> {
  const { r2Key, slug, score } = await request.json<{
    r2Key: string;
    slug: string;     // e.g. "hero-banner-dark"
    score: number;    // human rating 1–5
  }>();

  // Read metadata stored on the R2 object
  const obj = await env.IMAGE_BUCKET.head(r2Key);
  if (!obj) return new Response('Image not found', { status: 404 });

  const promptData = {
    r2Key,
    positivePrompt: obj.customMetadata?.prompt,
    negativePrompt: obj.customMetadata?.negativePrompt,
    seed: obj.customMetadata?.seed,
    model: obj.customMetadata?.model,
    promotedAt: new Date().toISOString(),
  };

  // Write to KV — keyed by slug for easy lookup
  await env.PROMPT_REGISTRY.put(
    `prompt:${slug}`,
    JSON.stringify(promptData),
    { expirationTtl: 60 * 60 * 24 * 90 }, // 90-day TTL; refresh on re-promotion
  );

  // Record score in D1 for analytics
  await env.DB.prepare(
    `UPDATE image_generations SET score = ?2 WHERE r2_key = ?1`,
  )
    .bind(r2Key, score)
    .run();

  return Response.json({ slug, promoted: true });
}
```

---

## 5. D1 Schema

```sql
-- migrations/0001_image_generations.sql
CREATE TABLE IF NOT EXISTS image_generations (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  r2_key          TEXT UNIQUE NOT NULL,
  model           TEXT NOT NULL,
  positive_prompt TEXT NOT NULL,
  negative_prompt TEXT,
  seed            INTEGER,
  width           INTEGER,
  height          INTEGER,
  guidance_scale  REAL,
  score           REAL,         -- human rating 1–5; NULL until rated
  created_at      INTEGER NOT NULL
);

CREATE INDEX idx_ig_model ON image_generations (model, created_at DESC);
CREATE INDEX idx_ig_score ON image_generations (score DESC) WHERE score IS NOT NULL;
```

---

## Anti-patterns

- Returning image bytes directly from the Worker response without R2 persistence — images cannot be retrieved after the response stream closes; always write to R2 first.
- Using a random UUID as the R2 key instead of a content-addressed hash — identical prompts generate duplicate images and waste storage and inference quota.
- Storing large image blobs in D1 — D1 row limit is 1 MB; image bytes belong in R2; D1 holds only metadata.
- Setting `num_inference_steps > 8` on Flux Schnell — the model is distilled for 1–4 steps; more steps do not improve quality and waste inference time.

## Gotchas

- `env.AI.run()` for image models returns either a `Uint8Array` or an `ArrayBuffer` depending on the model version; always normalise with `new Uint8Array(result)`.
- R2 `put` on an existing key silently overwrites; use `head` first to implement content-addressed deduplication.
- KV `expirationTtl` minimum is 60 seconds; values below that are silently rounded up.
- Flux Schnell ignores `negative_prompt` — only SDXL models honour it; pass an empty string for Flux to avoid unexpected behaviour.

## Verification

```bash
# Generate an image
curl -X POST https://<worker>.workers.dev/generate \
  -H "Content-Type: application/json" \
  -d '{"subject":"a red fox in a forest","style":"photorealistic","seed":42}'

# Retrieve gallery list
curl https://<worker>.workers.dev/gallery

# Open image in browser
open "https://<worker>.workers.dev/gallery/<R2_KEY>"

# Promote a winner
curl -X POST https://<worker>.workers.dev/promote \
  -H "Content-Type: application/json" \
  -d '{"r2Key":"gallery/abc123-42.png","slug":"fox-hero","score":5}'

# Verify KV entry
wrangler kv key get "prompt:fox-hero" --binding PROMPT_REGISTRY
```

## Related

- `workers-ai-image-generation-flux-stable-diffusion.md`
- `workers-ai-embeddings-batch-r2.md`
- `prompt-versioning.md`
- `prompt-engineering-fundamentals.md`
- `ai-feature-flag-patterns.md`

## Sources

- Cloudflare Workers AI — Flux-1-schnell and SDXL model cards
- R2 object metadata and custom metadata API reference
- Cloudflare KV TTL and expiration documentation
- D1 storage limits reference
