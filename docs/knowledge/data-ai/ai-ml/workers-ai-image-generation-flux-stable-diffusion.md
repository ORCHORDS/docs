# Workers AI Image Generation with Flux and Stable Diffusion

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You need to generate images on-demand from user prompts or automated pipelines—product
mockups, user-avatar placeholders, blog hero images, dynamic OG images—without standing
up a GPU server or paying per-seat SaaS pricing. Cloudflare Workers AI exposes text-to-image
models (Flux, Stable Diffusion families) at the edge with pay-per-invocation billing and no
cold-start provisioning.

## Context

Workers AI hosts several image-generation models under the
`@cf/` namespace. As of mid-2026 the catalogue includes:

| Model binding string | Architecture | Notable strengths |
|---|---|---|
| `@cf/black-forest-labs/flux-1-schnell` | Flux.1 Schnell | Fastest, 4-step distilled, great for real-time |
| `@cf/stabilityai/stable-diffusion-xl-base-1.0` | SDXL 1.0 | High detail, broad community support |
| `@cf/runwayml/stable-diffusion-v1-5-img2img` | SD 1.5 img2img | Image variation / style transfer |
| `@cf/runwayml/stable-diffusion-v1-5-inpainting` | SD 1.5 inpaint | Masked in-painting |
| `@cf/bytedance/stable-diffusion-xl-lightning` | SDXL Lightning | 4-step SDXL distillation, quality/speed balance |

All models accept JSON inputs and return a raw PNG byte stream (not base64). The Worker
receives `ArrayBuffer` directly from `AI.run()`.

Request limits are enforced per account per day (free: 10 k neurons; paid: per-usage).
Image generation consumes far more "neurons" than text inference—plan accordingly.

## Calling the Model from a Worker

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt, negative_prompt, num_steps, guidance } =
      await request.json<{
        prompt: string;
        negative_prompt?: string;
        num_steps?: number;   // 1-8 for Schnell, 20-50 for SDXL
        guidance?: number;    // CFG scale, 1-20
      }>();

    const imageBytes = await env.AI.run(
      "@cf/black-forest-labs/flux-1-schnell",
      {
        prompt,
        negative_prompt: negative_prompt ?? "",
        num_steps: num_steps ?? 4,
        guidance: guidance ?? 3.5,
        width: 1024,
        height: 1024,
      }
    );

    return new Response(imageBytes, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=3600",
      },
    });
  },
};
```

Bind the AI namespace in `wrangler.toml`:

```toml
[ai]
binding = "AI"
```

## Caching Generated Images in R2

Re-generating the same prompt wastes neurons and adds latency. Cache results in R2 keyed
on a deterministic hash of the generation parameters.

```typescript
import { createHash } from "crypto"; // available in Workers runtime

async function getCacheKey(params: GenerationParams): Promise<string> {
  const canonical = JSON.stringify({
    model: params.model,
    prompt: params.prompt,
    negative_prompt: params.negative_prompt ?? "",
    width: params.width ?? 1024,
    height: params.height ?? 1024,
    num_steps: params.num_steps ?? 4,
    guidance: params.guidance ?? 3.5,
    seed: params.seed ?? -1,
  });
  // Workers SubtleCrypto
  const msgBuffer = new TextEncoder().encode(canonical);
  const hashBuffer = await crypto.subtle.digest("SHA-256", msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function generateWithCache(
  ai: Ai,
  r2: R2Bucket,
  params: GenerationParams
): Promise<ArrayBuffer> {
  const key = `img-gen/${await getCacheKey(params)}.png`;

  // Try R2 first
  const cached = await r2.get(key);
  if (cached) return cached.arrayBuffer();

  // Generate
  const bytes = await ai.run(params.model, params) as ArrayBuffer;

  // Store asynchronously (don't block the response)
  // Use waitUntil in the calling handler
  await r2.put(key, bytes, {
    httpMetadata: { contentType: "image/png" },
    customMetadata: { prompt: params.prompt.slice(0, 512) },
  });

  return bytes;
}
```

Pass `ctx.waitUntil(r2.put(...))` when you want non-blocking write behaviour.

## Dynamic OG Image Generation

A common use-case: generate Open Graph preview images for blog posts at request time,
cache in R2 + KV, serve from the edge.

```typescript
// Generate OG image for article
async function generateOgImage(
  slug: string,
  title: string,
  env: Env
): Promise<string> {
  const kvKey = `og:${slug}`;
  const existing = await env.KV.get(kvKey);
  if (existing) return existing; // R2 public URL

  const prompt =
    `High-quality blog hero image for an article titled "${title}". ` +
    "Clean, modern design, vibrant colors, no text overlays, professional photography style.";

  const bytes = await env.AI.run("@cf/black-forest-labs/flux-1-schnell", {
    prompt,
    num_steps: 4,
    guidance: 3.5,
    width: 1200,
    height: 630, // OG image standard
  });

  const r2Key = `og-images/${slug}.png`;
  await env.R2.put(r2Key, bytes, {
    httpMetadata: { contentType: "image/png" },
  });

  const publicUrl = `https://assets.example.com/${r2Key}`;
  await env.KV.put(kvKey, publicUrl, { expirationTtl: 86400 * 30 });
  return publicUrl;
}
```

## Img2Img and Inpainting

For variation generation or style transfer, use the img2img model. Input images must be
base64-encoded PNG/JPEG.

```typescript
async function img2img(
  ai: Ai,
  sourceImage: ArrayBuffer,
  prompt: string
): Promise<ArrayBuffer> {
  const base64 = btoa(
    String.fromCharCode(...new Uint8Array(sourceImage))
  );

  return await ai.run(
    "@cf/runwayml/stable-diffusion-v1-5-img2img",
    {
      prompt,
      image: base64,
      strength: 0.75, // 0 = preserve source, 1 = ignore source
      num_steps: 20,
      guidance: 7.5,
    }
  ) as ArrayBuffer;
}
```

For inpainting, additionally supply a `mask` (base64 PNG, white = area to regenerate):

```typescript
await ai.run("@cf/runwayml/stable-diffusion-v1-5-inpainting", {
  prompt: "a golden retriever sitting on a park bench",
  image: base64Image,
  mask: base64Mask,
  num_steps: 20,
  guidance: 7.5,
  strength: 0.99,
});
```

## Prompt Engineering for Consistent Outputs

Quality prompts follow a structure: **subject → style → lighting → camera → quality
tokens**.

```
"A minimalist product shot of wireless headphones on a white marble surface,
 studio lighting, soft shadows, top-down perspective, 8k, commercial photography,
 highly detailed"
```

Negative prompts reject common failure modes:

```
"blurry, low quality, distorted, extra fingers, text, watermark, cropped,
 out of frame, jpeg artifacts, low resolution"
```

Use `seed` for reproducibility. Seeds are integers 0–4294967295. The same seed +
same prompt + same model = identical output (deterministic on Workers AI infra).

## Anti-patterns

- **Generating large images without caching.** Every invocation consumes neurons. Always
  check R2/KV before calling `AI.run()`.
- **Returning raw bytes without Content-Type.** Browsers will prompt download instead of
  rendering. Always set `Content-Type: image/png`.
- **Using high step counts with Flux Schnell.** Flux Schnell is a 4-step distilled
  model; increasing `num_steps` above 8 does not improve quality and wastes compute.
- **Passing user prompts directly without sanitisation.** Inject a safety prefix or run
  prompts through a classification step before image generation to prevent NSFW output.
- **Blocking the response on R2 write.** Use `ctx.waitUntil()` to cache after responding.
- **Ignoring neuron quotas.** Image gen consumes orders of magnitude more neurons than
  text inference. Monitor via AI Gateway or Workers Analytics.

## Gotchas

- The `AI.run()` return type for image models is `ReadableStream | ArrayBuffer`, not a
  structured JSON object. Type-cast appropriately in TypeScript.
- `width` and `height` must be multiples of 64 for SDXL and multiples of 8 for SD 1.5.
  Invalid dimensions cause a 400 error.
- Flux Schnell is optimised for `num_steps=4` with `guidance=3.5`. Changing these
  significantly degrades output or causes inference errors.
- R2 public access requires a custom domain or pre-signed URL. Raw R2 buckets are not
  publicly accessible by default.
- The Workers free plan has a hard limit on AI neurons per day. Image generation will
  silently fail with a 429 once that limit is hit; always handle 429s.
- `btoa()` in Workers is available globally but breaks on binary data above ~16 MB.
  Use `TextDecoder` + chunked encoding for large payloads.
- SDXL Lightning and Flux Schnell are both distilled models—CFG guidance values above
  ~4 produce over-saturated or blown-out images.

## Verification

```bash
# Generate a test image via curl
curl -X POST https://your-worker.workers.dev/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a red fox in a snowy forest","num_steps":4}' \
  --output test.png

# Check PNG header
file test.png
# Expected: test.png: PNG image data, 1024 x 1024, ...

# Verify R2 caching (second request should be faster)
time curl -X POST https://your-worker.workers.dev/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a red fox in a snowy forest","num_steps":4}' \
  --output test2.png

# Compare checksums (should be identical with same seed)
sha256sum test.png test2.png
```

Check neuron consumption in the Cloudflare dashboard under
**AI > Usage** or via the AI Gateway metrics panel.

## Related

- `ai-gateway-request-caching-cost-control.md` — cache AI responses to reduce neuron spend
- `workers-ai-multimodal-image-text-classification.md` — classify images returned from generation
- `ai-content-moderation-nsfw-detection-workers.md` — filter unsafe prompts before image gen
- `ai-cold-start-patterns.md` — warm-up strategies for latency-sensitive generation
- `embedding-generation-patterns.md` — pair image embeddings with Vectorize for similarity search

## Sources

- Cloudflare Workers AI docs — Text-to-Image models: https://developers.cloudflare.com/workers-ai/models/
- Black Forest Labs Flux.1 model card: https://huggingface.co/black-forest-labs/FLUX.1-schnell
- Stability AI SDXL model card: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- Cloudflare Blog — "Announcing support for image generation in Workers AI" (2024)
- Cloudflare R2 public access docs: https://developers.cloudflare.com/r2/buckets/public-buckets/
